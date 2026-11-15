"""apps-test-model: APP CONTRACT.

R3R4 whole-run reachability with apps_research delegation enabled.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid as uuid_module
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps_research.config.model_pins import (
    apps_rg_handoff_judge_pin,
    company_brief_generation_pin,
)
from apps_research.integrations.apps_rg_handoff import (
    persist_apps_rg_targeting_brief_artifacts,
)
from apps_rg.integrations.apps_research_bridge import EvidenceItem, ResearchResult
from apps_rg.integrations.managed_research_delegation import (
    ResearchDispatchFailure,
    ResumeBriefingReady,
)
from apps_rg.prerequisites.briefing_validator import validate_apps_research_handoff
from apps_rg.repository_layout import resolve_apps_rg_path
from apps_rg.runtime.dispatch.spine_stage_receipts import (
    FILENAME_DELEGATED_BRIEFING,
    FILENAME_L1_PLANNING_CAPSULE,
    FILENAME_PLAN_EXECUTION_RECEIPT,
    FILENAME_PLAN_REPLAN_DECISION,
    FILENAME_RESEARCH_BRIDGE_REQUEST,
    FILENAME_RESEARCH_BRIDGE_RESPONSE,
    FILENAME_SPINE_MANIFEST,
)
from apps_rg.runtime.mandatory_run_outputs import MANDATORY_OUTPUT_HARD_STOP_GATE_ID
from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import (
    ROUTE_FAMILY_R3R4,
    apps_research_handoff_authorized,
    briefing_input_present,
    research_delegation_enabled,
    should_delegate_apps_research,
)
from apps_rg.runtime.section_failure_forensics import E2E_SECTION_FORENSICS_GATE_ID

_REQUEST_UUID = uuid_module.UUID("11111111-1111-1111-1111-111111111111")
_RUN_UUID = uuid_module.UUID("22222222-2222-2222-2222-222222222222")
_TRACE_UUID = uuid_module.UUID("33333333-3333-3333-3333-333333333333")
_JD_TEXT = "Target JD text for route-decision pytest."
_CANONICAL_BRIEF_TEXT = (
    "Anthropic - Manager Applied AI Architecture Partnerships targeting brief\n"
    "| Manager Applied AI Architecture Partnerships | band | Reports to Partnerships |\n\n"
    "## JD Complement\n"
    "- Company DNA centers on safe frontier AI deployment with partner-led enterprise adoption.\n"
    "- Operating model favors technical architecture depth paired with ecosystem motion.\n\n"
    "## Company DNA & Operating Model\n"
    "- Company DNA emphasizes research-to-product translation for enterprise AI systems.\n"
    "- Operating model blends platform architecture and leadership decision rights.\n\n"
    "## Company Strategy & Operating Pressure\n"
    "- Strategy pressure focuses on scaling trusted AI adoption through partner ecosystems.\n"
    "- Recent urgency centers on durable enterprise deployment and platform governance.\n\n"
    "## Leadership & Stakeholder Map\n"
    "- Leadership stakeholders need architects who translate roadmap into technical close.\n"
    "- Stakeholder map spans partnerships, platform, data, and customer architecture teams.\n\n"
    "## AI, Data, Platform, Architecture Signals\n"
    "- AI platform signal favors secure integration, evaluation loops, and data governance.\n"
    "- Architecture signal points to reusable enterprise deployment patterns.\n\n"
    "## Partnership / Ecosystem Motion\n"
    "- Co-sell motion depends on joint solution design, enablement, and technical close.\n"
    "- Partner ecosystem signal includes GSI and ISV channels supporting adoption.\n\n"
    "## Recent Events & Urgency\n"
    "- Recent events create urgency for forward-looking enterprise AI operating models.\n"
    "- Urgency supports positioning around safe deployment and measurable adoption.\n\n"
    "## apps_rg Positioning Themes\n"
    "- Positioning should connect platform architecture, partner delivery, and trust.\n"
    "- Themes remain targeting context and never become proof for resume claims.\n\n"
    "## apps_lic Outreach Angles\n"
    "- Outreach can emphasize ecosystem revenue, enablement, and adoption motion.\n"
    "- Outreach mirrors company strategy without copying JD responsibilities.\n\n"
    "## Do Not Use As Proof\n"
    "- This briefing is targeting context only and cannot support candidate claims.\n"
)


def _build_provider_evidence(pin, *, trace_id: str, suffix: str) -> dict:
    receipt = {
        "schema_version": "apps_research.provider_attempt_validation.v1",
        "gateway_id": "apps_research.provider_gateway_v1",
        "role": pin.role,
        "provider": pin.provider,
        "requested_model": pin.model,
        "observed_model": pin.model,
        "reasoning_effort": pin.reasoning_effort,
        "attempt_id": f"attempt-{suffix}",
        "logical_attempt_id": f"run:logical:{suffix}",
        "transport_attempt_id": f"run:logical:{suffix}:transport:1",
        "run_id": "run",
        "trace_id": trace_id,
        "request_digest": suffix * 64,
        "provider_response_id": f"response-{suffix}",
        "lifecycle": {
            "local_dispatch_started": True,
            "request_bytes_sent": False,
            "response_headers_received": pin.provider == "google_gemini",
            "first_byte_received": pin.provider == "google_gemini",
            "sdk_response_returned": pin.provider == "external_openai",
            "remote_outcome": "PROVIDER_RESPONDED",
        },
        "transport_response_received": True,
        "response_schema_valid": True,
        "model_pin_valid": True,
        "application_output_valid": True,
        "overall_success": True,
        "terminal_status": "SUCCESS",
        "validation_reason": "ALL_VALIDATIONS_PASSED",
        "usage": {},
    }
    event = {
        "schema_version": "apps.external_model_usage_event.v1",
        "gateway_id": "apps_research.provider_gateway_v1",
        "provider_role": pin.role,
        "provider": pin.provider,
        "requested_model": pin.model,
        "observed_model": pin.model,
        "request_digest": receipt["request_digest"],
        "outcome": "SUCCESS",
        "transport_response_received": True,
        "response_schema_valid": True,
        "model_pin_valid": True,
        "application_output_valid": True,
        "overall_success": True,
        "attempt_id": receipt["attempt_id"],
        "logical_attempt_id": receipt["logical_attempt_id"],
        "transport_attempt_id": receipt["transport_attempt_id"],
        "trace_id": trace_id,
    }
    event["event_digest"] = hashlib.sha256(
        json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    receipt["ledger_event_digest"] = event["event_digest"]
    receipt["ledger_event"] = event
    return receipt


def _build_canonical_handoff_record(
    *,
    run_id: str,
    trace_id: str,
    request_id: str,
    tenant_id: str = "default",
) -> SimpleNamespace:
    generation_pin = company_brief_generation_pin()
    judge_pin = apps_rg_handoff_judge_pin()
    sidecar = {
        "brief_text_sha256": hashlib.sha256(
            _CANONICAL_BRIEF_TEXT.strip().encode("utf-8")
        ).hexdigest(),
        "generation_provider": generation_pin.provider,
        "generation_model_requested": generation_pin.model,
        "generation_model": generation_pin.model,
        "generation_reasoning_effort": generation_pin.reasoning_effort,
        "generation_model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
        "generation_provider_evidence": _build_provider_evidence(
            generation_pin,
            trace_id=trace_id,
            suffix="a",
        ),
        "provider_call_attempted": True,
        "handoff_eligible": True,
        "reason": "ok",
        "x2_judge_receipt": {
            "schema_version": "apps_research.apps_rg_handoff_x2_judge_receipt.v1",
            "gate_id": "X2_RESEARCH_SEMANTIC_GATE",
            "judge_name": judge_pin.provider_key,
            "judge_provider": judge_pin.provider,
            "judge_model_requested": judge_pin.model,
            "judge_model": judge_pin.model,
            "thinking_level": judge_pin.reasoning_effort,
            "model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
            "threshold": 0.75,
            "model_backed": True,
            "status": "PASS",
            "score": 0.91,
            "verdict": "PASS",
            "provider_status": "MODEL_BACKED_PASS",
            "provider_evidence": _build_provider_evidence(
                judge_pin,
                trace_id=trace_id,
                suffix="b",
            ),
        },
        "role_archetype": "partnerships",
        "required_sections_present": ["jd complement"],
        "missing_sections": [],
        "source_families_present": ["overview", "partner_ecosystem"],
        "source_families_missing": [],
        "signal_terms_present": ["company dna", "co-sell"],
        "signal_terms_missing": [],
        "source_register": [
            {"family": "overview", "has_content": True, "char_count": 500},
            {"family": "partner_ecosystem", "has_content": True, "char_count": 500},
        ],
    }
    return SimpleNamespace(
        run_id=run_id,
        request_id=request_id,
        parent_run_id=run_id,
        trace_id=trace_id,
        tenant_id=tenant_id,
        topic="Anthropic",
        company_brief_text=_CANONICAL_BRIEF_TEXT,
        fec_run_context={
            "company_brief": {
                "apps_rg_targeting_brief_sidecar": copy.deepcopy(sidecar),
            }
        },
        confidence_score=0.91,
        support_coverage=0.88,
        hop_terminal_error="",
    )


def _publish_observed_fixture_result(
    *,
    runs_root: Path,
    target_company: str,
    target_role: str,
    request_id: str,
    run_id: str,
    trace_id: str,
    tenant_id: str = "default",
    jd_text: str = _JD_TEXT,
) -> ResearchResult:
    producer_record = _build_canonical_handoff_record(
        run_id=run_id,
        trace_id=trace_id,
        request_id=request_id,
        tenant_id=tenant_id,
    )
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=producer_record,
        target_company=target_company,
        target_role=target_role,
        jd_text=jd_text,
        runs_root=runs_root,
    )
    return ResearchResult(
        run_id=run_id,
        trace_id=trace_id,
        request_id=request_id,
        is_blocked=False,
        block_reason="",
        is_stale=False,
        age_days=0.0,
        evidence_items=(
            EvidenceItem(
                source_id="observed-fixture",
                label="Observed provider fixture",
                uri="test://observed-provider-fixture",
                source_type="provider_response",
                field_ref="company_brief",
                confidence=0.91,
            ),
        ),
        confidence_score=producer_record.confidence_score,
        result_hash=bundle.bundle_manifest_digest,
        company_brief_hash=bundle.brief_sha256,
        fetch_duration_ms=0.0,
        audit_ref=str(bundle.run_dir),
        research_artifact_dir=str(bundle.run_dir),
        briefing_artifact_path=str(bundle.briefing_path),
        company_brief_text=producer_record.company_brief_text,
        apps_research_handoff_envelope=bundle.envelope,
        brief_sha256=bundle.brief_sha256,
        result_metadata_digest=bundle.result_metadata_digest,
        bundle_manifest_digest=bundle.bundle_manifest_digest,
        apps_research_u0_receipt=json.loads(bundle.u0_receipt_path.read_text(encoding="utf-8")),
    )


class _ObservedFixtureBridge:
    def __init__(
        self,
        *,
        artifact_runs_root: Path,
        capability_ref: str = "apps_research.v1",
        confidence_score: float = 0.88,
    ) -> None:
        del capability_ref, confidence_score
        self._artifact_runs_root = artifact_runs_root

    def fetch(self, **kwargs) -> ResearchResult:
        return _publish_observed_fixture_result(
            runs_root=self._artifact_runs_root,
            target_company=kwargs["company_name"],
            target_role=kwargs["job_title"],
            request_id=kwargs["request_id"],
            run_id=kwargs["run_id"],
            trace_id=kwargs["trace_id"],
            jd_text=kwargs.get("job_description_text") or _JD_TEXT,
        )


@pytest.mark.parametrize(
    ("x3_code", "expected_fault"),
    [
        ("X3D_ALLOW_FINISH", "FRESH_PREFLIGHT_REQUIRED_FOR_PRODUCT_AUTHORIZATION"),
        ("X3D", "PRODUCT_X3D_ALLOW_FINISH_REQUIRED"),
        ("X3C", "PRODUCT_X3D_ALLOW_FINISH_REQUIRED"),
        ("EXIT_OK", "PRODUCT_X3D_ALLOW_FINISH_REQUIRED"),
        ("EXIT_PARTIAL", "PRODUCT_X3D_ALLOW_FINISH_REQUIRED"),
        ("ALLOW", "PRODUCT_X3D_ALLOW_FINISH_REQUIRED"),
    ],
)
def test_product_x3_taxonomy_rejects_legacy_success_aliases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    x3_code: str,
    expected_fault: str,
) -> None:
    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome
    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-x3-taxonomy"
        request_id = "req-x3-taxonomy"
        x3_disposition = x3_code
        fault = ""
        terminal_r5 = False

    def _fake_spine(**kwargs: object) -> _FakeResult:
        art = Path(kwargs["artifact_dir"])
        art.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps({"chain_kind": "R4_SINGLE_ACTION", "route_family": "R4_SINGLE_ACTION"}),
            encoding="utf-8",
        )
        return _FakeResult()

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.whole_run_exit.emit_whole_run_exit_review_packet",
        lambda **kwargs: {"x3_disposition": x3_code},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.orchestration.ResumeRunRecoveryAgent.ResumeRunRecoveryAgent.can_attempt_recovery",
        lambda self, *args, **kwargs: False,
    )

    brief, jd = _write_authorized_apps_research_handoff(tmp_path)
    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief=str(brief),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / f"run_{x3_code}"),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["product_authorized"] is False
    assert result["fault"] == expected_fault


@pytest.fixture(autouse=True)
def _stable_cli_run_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the fixture's v2 parent identity equal to the current CLI run."""
    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _UuidProxy:
        def __init__(self) -> None:
            self._values = iter((_REQUEST_UUID, _RUN_UUID, _TRACE_UUID))

        def uuid4(self) -> uuid_module.UUID:
            try:
                return next(self._values)
            except StopIteration:
                return uuid_module.uuid4()

    monkeypatch.setattr(orch, "uuid", _UuidProxy())
    monkeypatch.setattr(
        "apps_rg.integrations.apps_research_bridge.AppsResearchBridge",
        _ObservedFixtureBridge,
    )
    monkeypatch.setattr(
        "apps_rg.integrations.apps_research_bridge.MockAppsResearchBridge",
        _ObservedFixtureBridge,
    )


def test_research_enabled_when_brief_missing_and_auto_research_on() -> None:
    assert research_delegation_enabled(auto_research_internal=True, research_via=None)
    assert should_delegate_apps_research(
        route_family=ROUTE_FAMILY_R3R4,
        manual_brief="",
        auto_research_internal=True,
        research_via=None,
    )


def _write_authorized_apps_research_handoff(
    tmp_path: Path,
    *,
    target_company: str = "Anthropic",
    target_role: str = "Manager of Applied AI Architecture, Partnerships",
    request_id: str = f"req-{_REQUEST_UUID.hex}",
    run_id: str = str(_RUN_UUID),
    trace_id: str = str(_TRACE_UUID),
) -> tuple[Path, Path]:
    jd_text = _JD_TEXT
    jd = tmp_path / "jd.txt"
    jd.write_text(jd_text, encoding="utf-8")
    result = _publish_observed_fixture_result(
        runs_root=tmp_path / "authorized_handoff_runs",
        target_company=target_company,
        target_role=target_role,
        request_id=request_id,
        run_id=run_id,
        trace_id=trace_id,
        jd_text=jd_text,
    )
    assert not result.is_blocked, result.block_reason
    return Path(result.briefing_artifact_path), jd


def test_no_delegation_when_auto_research_disabled_and_brief_present(tmp_path: Path) -> None:
    brief = tmp_path / "brief.txt"
    brief.write_text("Existing briefing content.\n", encoding="utf-8")
    assert briefing_input_present(str(brief))
    assert not should_delegate_apps_research(
        route_family=ROUTE_FAMILY_R3R4,
        manual_brief=str(brief),
        auto_research_internal=False,
        research_via=None,
    )


def test_auto_research_static_brief_requires_delegation() -> None:
    brief = Path("tests/fixtures/apps_rg/brief_anthropic_partnerships_2026.json")
    assert briefing_input_present(str(brief))
    assert should_delegate_apps_research(
        route_family=ROUTE_FAMILY_R3R4,
        manual_brief=str(brief),
        auto_research_internal=True,
        research_via=None,
        jd_ref="apps_rg/config/targeting/jd_anthropic_partnerships_2026.json",
    )


def test_auto_research_authorized_handoff_skips_delegation(tmp_path: Path) -> None:
    brief, jd = _write_authorized_apps_research_handoff(tmp_path)
    assert apps_research_handoff_authorized(str(brief), jd_ref=str(jd))
    assert not should_delegate_apps_research(
        route_family=ROUTE_FAMILY_R3R4,
        manual_brief=str(brief),
        auto_research_internal=True,
        research_via=None,
        jd_ref=str(jd),
    )


def test_whole_run_static_json_is_replaced_by_delegated_brief(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-static-json"
        request_id = "req-static-json"
        x3_disposition = "X3A"
        fault = "L2_EXECUTION_ERROR:test"
        terminal_r5 = False

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome

    captured: dict[str, object] = {}

    def _fake_spine(**kwargs: object) -> _FakeResult:
        captured["raw_request"] = kwargs["raw_request"]
        captured["front_continuation"] = kwargs["front_continuation"]
        art = Path(kwargs["artifact_dir"])
        art.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps({"chain_kind": "R4_SINGLE_ACTION", "route_family": "R4_SINGLE_ACTION"}),
            encoding="utf-8",
        )
        return _FakeResult()

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )

    brief_json = Path("tests/fixtures/apps_rg/brief_anthropic_partnerships_2026.json")
    jd_json = resolve_apps_rg_path(
        None, "config", "targeting", "jd_anthropic_partnerships_2026.json"
    )
    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd_json),
        job_description_text=jd_json.read_text(encoding="utf-8"),
        manual_brief=str(brief_json),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "static_json_run"),
        require_fresh_preflight=False,
    )

    raw_request = captured["raw_request"]
    assert isinstance(raw_request, dict)
    assert result["route_decision"]["research_delegation_executed"] is True
    producer_brief = Path(raw_request["manual_brief"])
    assert producer_brief.is_file()
    assert (
        producer_brief.parent / "apps_research_apps_rg_handoff_v2.json"
    ).is_file()
    assert raw_request["manual_brief"] != str(brief_json)
    assert raw_request["briefing_artifact_ref"] == raw_request["manual_brief"]
    front_continuation = captured["front_continuation"]
    assert isinstance(front_continuation, dict)
    validated = front_continuation["validated_request"]
    plan = front_continuation["plan_contract"]
    route = front_continuation["route_contract"]
    assert validated.request_id == plan.request_id == route.request_id
    assert validated.run_id == plan.run_id == route.run_id
    assert validated.app_payload["briefing_artifact_ref"] == raw_request["manual_brief"]
    assert front_continuation["execution_route_id"] == "R4_SINGLE_ACTION"
    research_ref_path = (
        tmp_path / "static_json_run" / "research" / "research_artifact_ref.json"
    )
    research_ref = json.loads(research_ref_path.read_text(encoding="utf-8"))
    assert Path(research_ref["research_artifact_dir"]).is_dir()
    assert Path(research_ref["research_briefing_path"]).is_file()
    assert Path(research_ref["research_briefing_path"]) == producer_brief
    assert Path(research_ref["research_company_brief_path"]).is_file()
    assert Path(research_ref["research_handoff_v2_path"]).is_file()
    plan_execution_receipt = json.loads(
        (tmp_path / "static_json_run" / FILENAME_PLAN_EXECUTION_RECEIPT).read_text(
            encoding="utf-8"
        )
    )
    assert plan_execution_receipt["emission"]["wave"] == "W1"
    assert plan_execution_receipt["summary"]["all_planned_units_reconciled"] is True
    plan_replan_decision = json.loads(
        (tmp_path / "static_json_run" / FILENAME_PLAN_REPLAN_DECISION).read_text(
            encoding="utf-8"
        )
    )
    assert (tmp_path / "static_json_run" / FILENAME_L1_PLANNING_CAPSULE).is_file()
    assert plan_replan_decision["replan_status"] == "NO_ACTIONABLE_REPLAN"
    assert plan_replan_decision["replan_revision"] is None
    assert plan_replan_decision["parent_plan"]["capsule_ref"] == FILENAME_L1_PLANNING_CAPSULE


def test_whole_run_redelegates_a_foreign_handoff_before_u0(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An otherwise-valid old handoff must not skip a new run's research hop."""

    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome
    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-foreign-handoff"
        request_id = "req-foreign-handoff"
        x3_disposition = "X3A"
        fault = "L2_EXECUTION_ERROR:test"
        terminal_r5 = False

    captured: dict[str, object] = {}

    def _fake_spine(**kwargs: object) -> _FakeResult:
        captured["raw_request"] = kwargs["raw_request"]
        captured["front_continuation"] = kwargs["front_continuation"]
        art = Path(kwargs["artifact_dir"])
        art.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps(
                {
                    "chain_kind": "R4_SINGLE_ACTION",
                    "route_family": "R4_SINGLE_ACTION",
                }
            ),
            encoding="utf-8",
        )
        return _FakeResult()

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )

    foreign_brief, jd = _write_authorized_apps_research_handoff(
        tmp_path,
        request_id="req-foreign-handoff",
        run_id="44444444-4444-4444-4444-444444444444",
        trace_id="55555555-5555-5555-5555-555555555555",
    )
    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief=str(foreign_brief),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "foreign_handoff_run"),
        require_fresh_preflight=False,
    )

    assert result["route_decision"]["research_delegation_executed"] is True
    raw_request = captured["raw_request"]
    assert isinstance(raw_request, dict)
    fresh_brief = Path(str(raw_request["manual_brief"]))
    assert fresh_brief != foreign_brief
    assert fresh_brief.is_file()

    continuation = captured["front_continuation"]
    assert isinstance(continuation, dict)
    validated = continuation["validated_request"]
    validation = validate_apps_research_handoff(
        brief_ref=str(fresh_brief),
        jd_ref=str(jd),
        require_observed=True,
        require_x1_x3_authorization=True,
        require_canonical_exit=True,
        expected_target_company="Anthropic",
        expected_target_role="Manager of Applied AI Architecture, Partnerships",
        expected_parent_run_id=validated.run_id,
        expected_request_id=validated.request_id,
        expected_trace_root=validated.trace_id,
        expected_tenant_id=validated.tenant_id,
    )
    assert validation.valid, validation.reason


def test_whole_run_research_failure_fails_closed_with_manual_brief(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-research-fallback"
        request_id = "req-research-fallback"
        x3_disposition = "X3A"
        fault = "L2_EXECUTION_ERROR:test"
        terminal_r5 = False

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome

    def _fake_spine(**kwargs: object) -> _FakeResult:
        pytest.fail("draft spine must not run after apps_research failure")

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.integrations.managed_research_delegation.dispatch_resume_research_briefing",
        lambda req, **_kwargs: ResearchDispatchFailure(
            request_id=req.request_id,
            run_id=req.run_id,
            trace_id=req.trace_id,
            r5_reason_code="APPS_RESEARCH_BLOCKED",
            detail="apps_research blocked in pytest",
            dispatch_duration_ms=1.0,
        ),
    )
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )

    brief = tmp_path / "manual_brief.md"
    brief.write_text("Manual Anthropic partner briefing with usable targeting context.", encoding="utf-8")
    jd = tmp_path / "jd.txt"
    jd.write_text("Run-specific JD for applied AI architecture partnerships.", encoding="utf-8")
    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        manual_brief=str(brief),
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "fallback_run"),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["execution_status"] == "failed"
    assert result["fault"] == "APPS_RESEARCH_BLOCKED"
    assert not (tmp_path / "fallback_run" / "research" / "manual_brief_fallback_receipt.json").exists()
    spine = json.loads((tmp_path / "fallback_run" / FILENAME_SPINE_MANIFEST).read_text(encoding="utf-8"))
    route_decision = spine["route_decision"]
    assert route_decision["research_delegation_executed"] is True
    assert route_decision["research_failure"] == "APPS_RESEARCH_BLOCKED"
    assert "research_fallback_to_manual_brief" not in route_decision


def test_whole_run_u0_rejection_emits_terminal_closeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")
    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    run_dir = tmp_path / "full_resume_u0_rejected"
    jd = tmp_path / "jd.txt"
    jd.write_text("Run-specific partnerships job description.", encoding="utf-8")

    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        manual_brief="",
        auto_research_internal=False,
        artifact_dir=str(run_dir),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["fault"].startswith("U0_REJECTED:")
    assert result["completion_status"] == "BLOCKED"
    assert Path(result["e2e_stage_ledger"]).is_file()
    assert (run_dir / "APPS_RG_MANDATORY_RUN_OUTPUT.json").is_file()
    assert (run_dir / "01_BCG_executive_output.md").is_file()


def test_research_hop_rejects_ready_result_without_producer_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")
    from apps_rg.integrations import managed_research_delegation as delegation
    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    outcome = ResumeBriefingReady(
        request_id="req-missing-artifact",
        run_id="run-missing-artifact",
        trace_id="trace-missing-artifact",
        briefing_text="Valid in-memory briefing that was never persisted by apps_research.",
        research_run_id="research-run-missing-artifact",
        research_evidence_count=1,
        confidence_score=0.91,
        research_artifact_dir="",
        result_hash="sha256:test",
        evidence_lineage=(),
        apps_research_handoff_envelope={"briefing_path": "", "company_brief_path": ""},
        dispatch_duration_ms=1.0,
    )
    monkeypatch.setattr(
        "apps_rg.integrations.apps_research_bridge.AppsResearchBridge",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        delegation,
        "dispatch_resume_research_briefing",
        lambda *_args, **_kwargs: outcome,
    )
    monkeypatch.setattr(
        orch,
        "run_integrated_single_action_spine",
        lambda **_kwargs: pytest.fail("draft spine must not run when producer artifact is missing"),
    )

    run_dir = tmp_path / "run"
    jd = tmp_path / "jd.txt"
    jd.write_text(_JD_TEXT, encoding="utf-8")
    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief="",
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(run_dir),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["fault"] == "APPS_RESEARCH_ARTIFACT_MISSING"
    bridge_response = json.loads(
        (run_dir / FILENAME_RESEARCH_BRIDGE_RESPONSE).read_text(encoding="utf-8")
    )
    assert bridge_response["r5_reason_code"] == "APPS_RESEARCH_ARTIFACT_MISSING"
    assert not (run_dir / FILENAME_DELEGATED_BRIEFING).exists()


def test_whole_run_route_mismatch_fails_closed_when_apps_research_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch
    _, jd = _write_authorized_apps_research_handoff(tmp_path)

    def _fake_spine(**kwargs: object) -> object:
        pytest.fail("draft spine must not run when apps_research-required routing mismatches")

    def _simple_route(plan: object) -> SimpleNamespace:
        return SimpleNamespace(
            route_id="R3_SIMPLE_GROUNDED_READ",
            route_family="R3_SIMPLE_GROUNDED_READ",
            execution_form="single_action",
            l3_required=True,
            grounding_required=True,
            route_profile_ref="test://route-profile/simple",
            reason_codes=("pytest_route_mismatch",),
            request_id=getattr(plan, "request_id", "req-route-mismatch"),
            run_id=getattr(plan, "run_id", "run-route-mismatch"),
            trace_id=getattr(plan, "trace_id", "trace-route-mismatch"),
        )

    monkeypatch.setattr(orch, "l0_route_apps_rg", _simple_route)
    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )

    brief = tmp_path / "manual_brief.md"
    brief.write_text("Static manual briefing that was not produced by apps_research.", encoding="utf-8")
    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        manual_brief=str(brief),
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "route_mismatch_run"),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["execution_status"] == "failed"
    assert result["fault"] == "APPS_RESEARCH_ROUTE_MISMATCH"
    assert result["route_family"] == "R3_SIMPLE_GROUNDED_READ"
    spine = json.loads((tmp_path / "route_mismatch_run" / FILENAME_SPINE_MANIFEST).read_text(encoding="utf-8"))
    route_decision = spine["route_decision"]
    assert route_decision["research_delegation_executed"] is True
    assert route_decision["research_failure"] == "APPS_RESEARCH_ROUTE_MISMATCH"
    assert route_decision["research_failure_reason"] == (
        "apps_research_completed_before_non_managed_route_R3_SIMPLE_GROUNDED_READ"
    )


def test_whole_run_r3r4_reachable_without_research_delegation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-1"
        request_id = "req-1"
        x3_disposition = "X3A"
        fault = "L2_EXECUTION_ERROR:AggregationPreflightError:test"
        terminal_r5 = False

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome

    def _fake_spine(**kwargs: object) -> _FakeResult:
        art = Path(kwargs["artifact_dir"])
        art.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps({"chain_kind": "R4_SINGLE_ACTION", "route_family": "R4_SINGLE_ACTION"}),
            encoding="utf-8",
        )
        return _FakeResult()

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )

    brief, jd = _write_authorized_apps_research_handoff(
        tmp_path,
        target_company="Brown & Brown",
        target_role="SVP IT Strategy",
    )

    result = orch.run_whole_run_with_route_governance(
        target_company="Brown & Brown",
        target_role="SVP IT Strategy",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief=str(brief),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "full_resume_test01"),
        require_fresh_preflight=False,
    )

    assert result["route_family"] == ROUTE_FAMILY_R3R4
    assert result["research_delegation_executed"] is False
    art = Path(result["artifact_dir"])
    assert (art / FILENAME_SPINE_MANIFEST).is_file()
    assert not (art / FILENAME_RESEARCH_BRIDGE_REQUEST).exists()
    assert not (art / FILENAME_RESEARCH_BRIDGE_RESPONSE).exists()
    assert not (art / FILENAME_DELEGATED_BRIEFING).exists()

    spine = json.loads((art / FILENAME_SPINE_MANIFEST).read_text(encoding="utf-8"))
    assert spine["proof_authority"] == "spine_run_manifest.json"
    assert spine["draft_leg_proof_scope"] == "draft_leg_only"
    assert spine["route_family"] == ROUTE_FAMILY_R3R4

    r4 = json.loads((art / "r4_run_manifest.json").read_text(encoding="utf-8"))
    assert r4.get("apps_rg_proof_scope") == "draft_leg_only"
    assert r4.get("apps_rg_orchestration_manifest_ref") == FILENAME_SPINE_MANIFEST

    route_decision = result["route_decision"]
    assert route_decision["route_family"] == ROUTE_FAMILY_R3R4
    assert route_decision["briefing_input_present"] is True


def test_whole_run_custom_artifact_dir_emits_output_gates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-custom"
        request_id = "req-custom"
        x3_disposition = "X3A"
        fault = "L2_EXECUTION_ERROR:PoolSelectorUnavailableError:test"
        terminal_r5 = False

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome

    def _fake_spine(**kwargs: object) -> _FakeResult:
        art = Path(kwargs["artifact_dir"])
        lane = art / "modular_r4" / "sections" / "competencies"
        lane.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps({"chain_kind": "R4_SINGLE_ACTION", "route_family": "R4_SINGLE_ACTION"}),
            encoding="utf-8",
        )
        (lane / "integrated_lane_pre_run_failure.json").write_text(
            json.dumps({"blocker": "EXECUTED_X3A"}),
            encoding="utf-8",
        )
        return _FakeResult()

    status_calls: list[Path] = []
    mandatory_calls: list[Path] = []
    review_calls: list[Path] = []

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_run_section_status.emit_full_run_section_status",
        lambda run_root, **kwargs: status_calls.append(Path(run_root))
        or {"markdown_path": str(Path(run_root) / "FULL_RUN_SECTION_STATUS.md")},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.mandatory_run_outputs.emit_mandatory_run_outputs",
        lambda run_root, **kwargs: mandatory_calls.append(Path(run_root))
        or {
            "json_path": Path(run_root) / "APPS_RG_MANDATORY_RUN_OUTPUT.json",
            "markdown_path": Path(run_root) / "02_section_lane_summary_table.md",
            "bcg_markdown_path": Path(run_root) / "01_BCG_executive_output.md",
        },
    )
    monkeypatch.setattr(
        orch,
        "emit_full_resume_review_bundle",
        lambda run_root: review_calls.append(Path(run_root)) or Path(run_root) / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )

    brief, jd = _write_authorized_apps_research_handoff(tmp_path)

    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief=str(brief),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "anthropic_custom_run"),
        require_fresh_preflight=False,
    )

    art = Path(result["artifact_dir"])
    assert status_calls == [art]
    assert mandatory_calls == [art]
    assert review_calls == [art]
    assert result["bcg_executive_output_md"].endswith("01_BCG_executive_output.md")


def test_whole_run_hard_fails_without_complete_section_forensics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-missing-forensics"
        request_id = "req-missing-forensics"
        x3_disposition = "X3A"
        fault = "L2_EXECUTION_ERROR:test"
        terminal_r5 = False

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome

    def _fake_spine(**kwargs: object) -> _FakeResult:
        art = Path(kwargs["artifact_dir"])
        art.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps({"chain_kind": "R4_SINGLE_ACTION", "route_family": "R4_SINGLE_ACTION"}),
            encoding="utf-8",
        )
        return _FakeResult()

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_run_section_status.emit_full_run_section_status",
        lambda *a, **k: {"markdown_path": str(tmp_path / "FULL_RUN_SECTION_STATUS.md")},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.mandatory_run_outputs.emit_mandatory_run_outputs",
        lambda run_root, **kwargs: {
            "json_path": Path(run_root) / "APPS_RG_MANDATORY_RUN_OUTPUT.json",
            "markdown_path": Path(run_root) / "02_section_lane_summary_table.md",
            "bcg_markdown_path": Path(run_root) / "01_BCG_executive_output.md",
            "mandatory_output_gate": {
                "gate_id": MANDATORY_OUTPUT_HARD_STOP_GATE_ID,
                "required": True,
                "pass": False,
                "errors": ["comparison:headline:invalid:comparison_incomplete"],
            },
            "payload": {
                "section_failure_forensics": {
                    "gate_id": E2E_SECTION_FORENSICS_GATE_ID,
                    "required": True,
                    "pass": False,
                    "missing_or_incomplete": [{"section_id": "headline"}],
                }
            },
        },
    )

    brief, jd = _write_authorized_apps_research_handoff(tmp_path)

    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief=str(brief),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "full_resume_missing_forensics"),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["execution_status"] == "failed"
    assert result["outcome_authorized"] is False
    assert result["fault"] == "L2_EXECUTION_ERROR:test"
    assert result["completion_fault"] == E2E_SECTION_FORENSICS_GATE_ID
    assert result["x3_disposition"] == "X3A_DENY_REROUTE"
    assert result["core_x3_disposition"] == "X3A"
    assert result["completion_status"] == "BLOCKED"


def test_whole_run_fails_when_exec_summary_judge_not_certified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-certified-looking"
        request_id = "req-certified-looking"
        x3_disposition = "X3D"
        fault = ""
        terminal_r5 = False

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome

    def _fake_spine(**kwargs: object) -> _FakeResult:
        art = Path(kwargs["artifact_dir"])
        es_dir = art / "lanes" / "executive_summary"
        es_dir.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps({"chain_kind": "R4_SINGLE_ACTION", "route_family": "R4_SINGLE_ACTION"}),
            encoding="utf-8",
        )
        (es_dir / "x3_disposition.json").write_text(
            json.dumps(
                {
                    "x3_code": "X3_REVIEW_JUDGE_SOFT_FAIL",
                    "pass": False,
                    "publish_disposition": "judge_certification_required",
                    "x1d_certified": False,
                    "blocking_judge_ids": ["gemini_pro"],
                }
            ),
            encoding="utf-8",
        )
        (es_dir / "publish_disposition.json").write_text(
            json.dumps(
                {
                    "publish_disposition": "judge_certification_required",
                    "x1d_certified": False,
                    "blocking_judge_ids": ["gemini_pro"],
                }
            ),
            encoding="utf-8",
        )
        return _FakeResult()

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )

    brief, jd = _write_authorized_apps_research_handoff(tmp_path)

    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief=str(brief),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "full_resume_test02"),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["execution_status"] == "failed"
    assert result["outcome_authorized"] is False
    assert result["x3_disposition"] == "X3_REVIEW_JUDGE_SOFT_FAIL"
    assert result["core_x3_disposition"] == "X3D"
    assert result["completion_disposition"] == "X3_REVIEW_JUDGE_SOFT_FAIL"
    assert result["executive_summary_certification_block"]["blocking_judge_ids"] == ["gemini_pro"]


def test_whole_run_success_requires_post_x3_uwg_eval_l6(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-success"
        request_id = "req-success"
        x3_disposition = "X3D_ALLOW_FINISH"
        fault = ""
        terminal_r5 = False

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome

    def _fake_spine(**kwargs: object) -> _FakeResult:
        art = Path(kwargs["artifact_dir"])
        art.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps({"chain_kind": "R4_SINGLE_ACTION", "route_family": "R4_SINGLE_ACTION"}),
            encoding="utf-8",
        )
        (art / "apps_rg_how_trace.json").write_text("{}", encoding="utf-8")
        return _FakeResult()

    post_x3_calls: list[Path] = []
    output_contract_calls: list[Path] = []

    def _fake_emit_final_resume_product_outputs(run_root: Path, **kwargs: object) -> dict[str, object]:
        root = Path(run_root)
        output_contract_calls.append(root)
        (root / "outputs").mkdir(parents=True, exist_ok=True)
        (root / "outputs" / "resume.docx").write_bytes(b"fake-docx")
        (root / "FINAL_RESUME_OUTPUT.txt").write_text(
            "Applied AI architecture leader\n",
            encoding="utf-8",
        )
        (root / "FINAL_RESUME_OUTPUT.json").write_text(
            json.dumps({"resume": "Applied AI architecture leader"}),
            encoding="utf-8",
        )
        assembly = root / "modular_r4" / "final_resume_assembly" / "final_resume.json"
        assembly.parent.mkdir(parents=True, exist_ok=True)
        assembly.write_text(
            json.dumps({"resume": "Applied AI architecture leader"}),
            encoding="utf-8",
        )
        (root / "apps_rg_output_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "apps_rg_output_manifest.v1",
                    "resume_docx_relpath": "outputs/resume.docx",
                    "docx_verified": True,
                    "required_artifacts": {
                        "resume_docx": "verified",
                        "docx_verified": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        return {"status": "PASS", "manifest_path": str(root / "apps_rg_output_manifest.json")}

    def _fake_post_x3(**kwargs: object) -> dict[str, object]:
        art = Path(kwargs["artifact_dir"])
        manifest = json.loads((art / "apps_rg_output_manifest.json").read_text(encoding="utf-8"))
        assert manifest["docx_verified"] is True
        assert manifest["required_artifacts"]["resume_docx"] == "verified"
        post_x3_calls.append(art)
        return {
            "completed": True,
            "product_authorized": True,
            "pipeline_complete": True,
            "x3_to_uwg_to_eval_to_l6_completed": True,
            "durable_promotion_committed": True,
            "uwg": {"artifacts": {"uwg_commit_receipt": "uwg/uwg_commit_receipt.json"}},
            "fact_vector_writeback": {"status": "PASS"},
            "apps_eval": {
                "eval_record_ref": str(art / "apps_eval" / "eval_record.json"),
                "coverage_summary": {
                    "release_blocked": False,
                    "coverage_complete": True,
                },
            },
            "l6_shadow": {
                "l6_shadow_bridge_ref": str(art / "apps_eval" / "l6_shadow_bridge.json"),
                "grain_parity_status": "PASS",
                "apps_eval_rows_bound": True,
            },
        }

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.final_resume_outputs.emit_final_resume_product_outputs",
        _fake_emit_final_resume_product_outputs,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_run_section_status.emit_full_run_section_status",
        lambda *a, **k: {"markdown_path": str(tmp_path / "FULL_RUN_SECTION_STATUS.md")},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.post_x3_completion.complete_apps_rg_post_x3",
        _fake_post_x3,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.whole_run_exit.emit_whole_run_exit_review_packet",
        lambda **kwargs: {"x3_disposition": "X3D_ALLOW_FINISH"},
    )

    brief, jd = _write_authorized_apps_research_handoff(tmp_path)

    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief=str(brief),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "full_resume_success01"),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["outcome_authorized"] is False
    assert result["product_authorized"] is False
    assert result["pipeline_complete"] is False
    assert result["observability_repair_required"] is False
    assert output_contract_calls == [tmp_path / "full_resume_success01"]
    assert post_x3_calls == []
    assert result["fault"] == "FRESH_PREFLIGHT_REQUIRED_FOR_PRODUCT_AUTHORIZATION"


def test_whole_run_blocks_when_post_x3_l6_bridge_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPS_RG_MOCK_RESEARCH", "1")
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")

    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    class _FakeResult:
        run_id = "draft-run-no-l6"
        request_id = "req-no-l6"
        x3_disposition = "X3D_ALLOW_FINISH"
        fault = ""
        terminal_r5 = False

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome

    def _fake_spine(**kwargs: object) -> _FakeResult:
        art = Path(kwargs["artifact_dir"])
        art.mkdir(parents=True, exist_ok=True)
        (art / "r4_run_manifest.json").write_text(
            json.dumps({"chain_kind": "R4_SINGLE_ACTION", "route_family": "R4_SINGLE_ACTION"}),
            encoding="utf-8",
        )
        return _FakeResult()

    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fake_spine)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_run_section_status.emit_full_run_section_status",
        lambda *a, **k: {"markdown_path": str(tmp_path / "FULL_RUN_SECTION_STATUS.md")},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.full_resume_review_bundle.emit_full_resume_review_bundle",
        lambda run_root: run_root / "review_bundle.zip",
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.post_x3_completion.complete_apps_rg_post_x3",
        lambda **kwargs: {
            "completed": True,
            "product_authorized": True,
            "pipeline_complete": False,
            "observability_repair_required": True,
            "x3_to_uwg_to_eval_to_l6_completed": False,
            "failure_stage": "l6_shadow_bridge",
        },
    )
    monkeypatch.setattr(
        "apps_rg.runtime.whole_run_exit.emit_whole_run_exit_review_packet",
        lambda **kwargs: {"x3_disposition": "X3D_ALLOW_FINISH"},
    )

    brief, jd = _write_authorized_apps_research_handoff(tmp_path)

    result = orch.run_whole_run_with_route_governance(
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd=str(jd),
        job_description_text=_JD_TEXT,
        manual_brief=str(brief),
        source_resume_text="Experienced applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        auto_research_internal=True,
        artifact_dir=str(tmp_path / "full_resume_no_l6"),
        require_fresh_preflight=False,
    )

    assert result["exit_status"] == "error"
    assert result["outcome_authorized"] is False
    assert result["product_authorized"] is False
    assert result["pipeline_complete"] is False
    assert result["observability_repair_required"] is False
    assert result["fault"] == "FRESH_PREFLIGHT_REQUIRED_FOR_PRODUCT_AUTHORIZATION"
