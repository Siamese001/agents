"""Canonical apps_research GateMesh/Exit authorization for apps_rg handoff."""

from __future__ import annotations

import hashlib
import json
import copy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from apps_research.integrations.apps_rg_handoff import (
    persist_apps_rg_targeting_brief_artifacts,
    validate_apps_rg_handoff_sidecar,
)
from apps_research.config.model_pins import (
    apps_rg_handoff_judge_pin,
    company_brief_generation_pin,
)
from apps_rg.prerequisites.briefing_validator import (
    validate_apps_research_handoff,
)
from apps_rg.runtime.bindings.briefing_u0_signals import (
    briefing_supplied_at_u0,
)

_VALID_BRIEF = (
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


@dataclass(frozen=True)
class _Record:
    run_id: str
    topic: str
    company_brief_text: str
    fec_run_context: dict
    confidence_score: float = 0.91
    support_coverage: float = 0.88
    hop_terminal_error: str = ""
    trace_id: str = ""


def _provider_evidence(pin, *, trace_id: str, suffix: str) -> dict:
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


def _sidecar(
    brief: str,
    *,
    x2_status: str = "PASS",
    trace_id: str = "trace-fixture",
) -> dict:
    score = 0.91 if x2_status == "PASS" else 0.0
    generation_pin = company_brief_generation_pin()
    judge_pin = apps_rg_handoff_judge_pin()
    return {
        "brief_text_sha256": hashlib.sha256(brief.strip().encode("utf-8")).hexdigest(),
        "generation_provider": generation_pin.provider,
        "generation_model_requested": generation_pin.model,
        "generation_model": generation_pin.model,
        "generation_reasoning_effort": generation_pin.reasoning_effort,
        "generation_model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
        "generation_provider_evidence": _provider_evidence(
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
            "status": x2_status,
            "score": score,
            "verdict": x2_status,
            "provider_status": f"MODEL_BACKED_{x2_status}",
            "provider_evidence": _provider_evidence(
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


def _record(run_id: str, *, x2_status: str = "PASS") -> _Record:
    return _Record(
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        topic="Anthropic",
        company_brief_text=_VALID_BRIEF,
        fec_run_context={
            "company_brief": {
                "apps_rg_targeting_brief_sidecar": _sidecar(
                    _VALID_BRIEF,
                    x2_status=x2_status,
                    trace_id=f"trace-{run_id}",
                )
            }
        },
    )


def _record_for_identity(
    *,
    run_id: str,
    trace_id: str,
    request_id: str,
    tenant_id: str = "default",
) -> SimpleNamespace:
    """Return observed-evidence fixture data rebound to one test ingress identity."""
    base = _record(run_id)
    context = copy.deepcopy(base.fec_run_context)
    sidecar = context["company_brief"]["apps_rg_targeting_brief_sidecar"]
    evidence_rows = (
        sidecar["generation_provider_evidence"],
        sidecar["x2_judge_receipt"]["provider_evidence"],
    )
    for receipt in evidence_rows:
        receipt["trace_id"] = trace_id
        event = receipt["ledger_event"]
        event["trace_id"] = trace_id
        event.pop("event_digest", None)
        event["event_digest"] = hashlib.sha256(
            json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        receipt["ledger_event_digest"] = event["event_digest"]
    return SimpleNamespace(
        **{
            **base.__dict__,
            "request_id": request_id,
            "parent_run_id": run_id,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "fec_run_context": context,
        }
    )


def test_handoff_rejects_generation_reasoning_effort_drift() -> None:
    sidecar = _sidecar(_VALID_BRIEF)
    sidecar["generation_reasoning_effort"] = "low"

    eligible, reason = validate_apps_rg_handoff_sidecar(
        sidecar,
        expected_brief_sha=hashlib.sha256(
            _VALID_BRIEF.strip().encode("utf-8")
        ).hexdigest(),
    )

    assert eligible is False
    assert reason == "generation_reasoning_effort_mismatch"


def test_handoff_rejects_malformed_provider_event_digest() -> None:
    sidecar = _sidecar(_VALID_BRIEF)
    sidecar["generation_provider_evidence"]["ledger_event_digest"] = "not-a-digest"

    eligible, reason = validate_apps_rg_handoff_sidecar(
        sidecar,
        expected_brief_sha=hashlib.sha256(
            _VALID_BRIEF.strip().encode("utf-8")
        ).hexdigest(),
    )

    assert eligible is False
    assert reason == "generation_provider_evidence_invalid"


def test_handoff_rejects_provider_event_that_does_not_match_observed_model() -> None:
    brief = _VALID_BRIEF
    sidecar = _sidecar(brief, trace_id="trace-forged-event")
    sidecar["generation_provider_evidence"]["ledger_event"][
        "observed_model"
    ] = "forged-model"

    valid, reason = validate_apps_rg_handoff_sidecar(
        sidecar,
        expected_brief_sha=hashlib.sha256(brief.strip().encode("utf-8")).hexdigest(),
    )

    assert valid is False
    assert reason == "generation_provider_evidence_invalid"


def test_publisher_writes_brief_only_after_canonical_x3d(tmp_path: Path) -> None:
    jd = "Lead partner solution architecture for Claude."
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=_record("canonical-allow"),
        target_company="Anthropic",
        target_role="Manager Applied AI Architecture Partnerships",
        jd_text=jd,
        runs_root=tmp_path / "runs",
    )

    assert bundle.briefing_path.is_file()
    assert bundle.gate_mesh_path and bundle.gate_mesh_path.is_file()
    assert bundle.exit_review_path and bundle.exit_review_path.is_file()
    assert bundle.exit_disposition_path and bundle.exit_disposition_path.is_file()
    assert bundle.runtime_exhaust_path and bundle.runtime_exhaust_path.is_file()
    assert bundle.handoff_v2_path and bundle.handoff_v2_path.is_file()
    assert bundle.commit_manifest_path and bundle.commit_manifest_path.is_file()
    assert bundle.u0_receipt_path and bundle.u0_receipt_path.is_file()
    assert bundle.brief_sha256.startswith("sha256:")
    assert bundle.result_metadata_digest.startswith("sha256:")
    assert bundle.bundle_manifest_digest.startswith("sha256:")

    handoff = bundle.envelope
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "config/certification/schemas/apps_research_apps_rg_handoff.v2.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(handoff)
    assert handoff["schema_version"] == "apps_research.apps_rg_handoff.v2"
    assert handoff["exit_authorization"]["x3_code"] == "X3D_ALLOW_FINISH"
    assert handoff["identity"]["brief_sha256"] == bundle.brief_sha256
    assert handoff["model_observations"]["generation"]["observed_model"] == (
        company_brief_generation_pin().model
    )
    assert handoff["model_observations"]["generation"]["reasoning_effort"] == (
        company_brief_generation_pin().reasoning_effort
    )
    assert handoff["model_observations"]["judge"]["observed_model"] == (
        apps_rg_handoff_judge_pin().model
    )
    assert handoff["model_observations"]["judge"]["reasoning_effort"] == "high"
    provider_evidence_path = bundle.run_dir / "provider_attempt_evidence.json"
    otel_snapshot_path = (
        bundle.run_dir / "apps_research_handoff_otel_trace_snapshot.json"
    )
    assert provider_evidence_path.is_file()
    assert otel_snapshot_path.is_file()
    provider_evidence = json.loads(provider_evidence_path.read_text(encoding="utf-8"))
    assert provider_evidence["status"] == "PASS"
    assert {row["role"] for row in provider_evidence["attempts"]} == {
        company_brief_generation_pin().role,
        apps_rg_handoff_judge_pin().role,
    }
    assert all(row["overall_success"] is True for row in provider_evidence["attempts"])
    assert json.loads(otel_snapshot_path.read_text(encoding="utf-8"))["trace_id"] == (
        handoff["identity"]["trace_root"]
    )
    assert set(handoff["mandatory_gate_receipts"]) == {
        "G5",
        "G6",
        "G7",
        "G21",
        "G24",
        "G26",
    }
    assert all(
        row["status"] == "PASS"
        for row in handoff["mandatory_gate_receipts"].values()
    )
    assert not (bundle.run_dir / "apps_research_briefing_envelope.json").exists()
    consumer_validation = validate_apps_research_handoff(
        brief_ref=str(bundle.briefing_path),
        jd_ref=jd,
        require_observed=True,
        require_x1_x3_authorization=True,
        require_canonical_exit=True,
    )
    assert consumer_validation.valid, consumer_validation.reason
    persisted_consumer_receipt = (
        bundle.run_dir / "apps_research_handoff_validation_receipt.json"
    )
    assert persisted_consumer_receipt.is_file()
    assert json.loads(persisted_consumer_receipt.read_text())["status"] == "PASS"


def test_consumer_treats_long_inline_json_jd_as_text(tmp_path: Path) -> None:
    jd = json.dumps({"description": "architecture " * 450}, sort_keys=True)
    assert len(jd) > 4096
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=_record("long-inline-jd"),
        target_company="Anthropic",
        target_role="Manager Applied AI Architecture Partnerships",
        jd_text=jd,
        runs_root=tmp_path / "runs",
    )

    validation = validate_apps_research_handoff(
        brief_ref=str(bundle.briefing_path),
        jd_ref=jd,
        require_observed=True,
        require_x1_x3_authorization=True,
        require_canonical_exit=True,
    )

    assert validation.valid, validation.reason


def test_consumer_rejects_handoff_otel_capture_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps_model_telemetry import otel_runtime

    monkeypatch.setattr(
        otel_runtime,
        "capture_collector_snapshot",
        lambda **kwargs: {
            "schema_version": "apps.otel_trace_snapshot.v3",
            "trace_id": kwargs["trace_id"],
            "boundary": kwargs["boundary"],
            "status": "SOURCE_UNREADABLE",
            "spans": [],
        },
    )
    jd = "Lead partner solution architecture for Claude."
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=_record("otel-capture-failure"),
        target_company="Anthropic",
        target_role="Manager Applied AI Architecture Partnerships",
        jd_text=jd,
        runs_root=tmp_path / "runs",
    )

    validation = validate_apps_research_handoff(
        brief_ref=str(bundle.briefing_path),
        jd_ref=jd,
        require_observed=True,
        require_x1_x3_authorization=True,
        require_canonical_exit=True,
    )

    assert validation.valid is False
    assert "apps_research_handoff_otel_status_invalid" in validation.reason


def test_unknown_x2_never_publishes_briefing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    with pytest.raises(RuntimeError, match="canonical Exit"):
        persist_apps_rg_targeting_brief_artifacts(
            record=_record("canonical-unknown", x2_status="UNKNOWN"),
            target_company="Anthropic",
            target_role="Manager Applied AI Architecture Partnerships",
            jd_text="Lead partner solution architecture for Claude.",
            runs_root=runs_root,
        )

    assert not (runs_root / "canonical-unknown").exists()
    assert not (runs_root / "canonical-unknown" / "briefing.md").exists()


def test_consumer_rejects_tampered_exit_receipt(tmp_path: Path) -> None:
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=_record("tamper"),
        target_company="Anthropic",
        target_role="Manager",
        jd_text="JD",
        runs_root=tmp_path / "runs",
    )
    receipt = json.loads(bundle.exit_disposition_path.read_text(encoding="utf-8"))
    receipt["unknown_count"] = 1
    bundle.exit_disposition_path.write_text(
        json.dumps(receipt, sort_keys=True),
        encoding="utf-8",
    )

    validation = validate_apps_research_handoff(
        brief_ref=str(bundle.briefing_path),
        jd_ref="JD",
        require_observed=True,
        require_x1_x3_authorization=True,
        require_canonical_exit=True,
    )
    assert not validation.valid
    assert "exit_authorization_receipt_sha256_mismatch" in validation.reason
    assert "persisted_exit_unknown_count_nonzero" in validation.reason


def test_u0_signal_requires_canonical_exit_for_auto_research(tmp_path: Path) -> None:
    manual = tmp_path / "manual.md"
    manual.write_text(_VALID_BRIEF, encoding="utf-8")
    assert briefing_supplied_at_u0(
        {
            "briefing_artifact_ref": str(manual),
            "auto_research_internal": False,
        }
    )
    assert not briefing_supplied_at_u0(
        {
            "briefing_artifact_ref": str(manual),
            "auto_research_internal": True,
            "job_description_text": "JD",
        }
    )

    jd = "Lead partner solution architecture for Claude."
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=_record("u0-accepted"),
        target_company="Anthropic",
        target_role="Manager Applied AI Architecture Partnerships",
        jd_text=jd,
        runs_root=tmp_path / "runs",
    )
    assert briefing_supplied_at_u0(
        {
            "briefing_artifact_ref": str(bundle.briefing_path),
            "manual_brief_path": str(bundle.briefing_path),
            "auto_research_internal": True,
            "research_via": "apps_research",
            "job_description_text": jd,
        }
    )


def test_u0_binding_reaches_authorized_briefing_signal() -> None:
    source = Path("src/apps_rg/runtime/bindings/u0_binding.py").read_text(
        encoding="utf-8"
    )
    assert "briefing_supplied_at_u0(app_payload)" in source


def test_v2_consumer_rejects_tampered_committed_brief_bytes(tmp_path: Path) -> None:
    jd = "Lead partner solution architecture for Claude."
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=_record("v2-byte-tamper"),
        target_company="Anthropic",
        target_role="Manager Applied AI Architecture Partnerships",
        jd_text=jd,
        runs_root=tmp_path / "runs",
    )
    bundle.briefing_path.write_bytes(bundle.briefing_path.read_bytes() + b"tamper")

    validation = validate_apps_research_handoff(
        brief_ref=str(bundle.briefing_path),
        jd_ref=jd,
        require_observed=True,
        require_canonical_exit=True,
    )

    assert not validation.valid
    assert "artifact_byte_length_mismatch:briefing.md" in validation.reason
    assert "brief_sha256_mismatch" in validation.reason


def test_v2_consumer_rejects_missing_commit_marker(tmp_path: Path) -> None:
    jd = "Lead partner solution architecture for Claude."
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=_record("v2-marker-missing"),
        target_company="Anthropic",
        target_role="Manager Applied AI Architecture Partnerships",
        jd_text=jd,
        runs_root=tmp_path / "runs",
    )
    assert bundle.commit_manifest_path is not None
    bundle.commit_manifest_path.unlink()

    validation = validate_apps_research_handoff(
        brief_ref=str(bundle.briefing_path),
        jd_ref=jd,
        require_observed=True,
        require_canonical_exit=True,
    )

    assert not validation.valid
    assert "missing_commit_marker" in validation.reason


def test_v2_consumer_rejects_target_identity_mismatch(tmp_path: Path) -> None:
    jd = "Lead partner solution architecture for Claude."
    bundle = persist_apps_rg_targeting_brief_artifacts(
        record=_record("v2-target-mismatch"),
        target_company="Anthropic",
        target_role="Manager Applied AI Architecture Partnerships",
        jd_text=jd,
        runs_root=tmp_path / "runs",
    )

    validation = validate_apps_research_handoff(
        brief_ref=str(bundle.briefing_path),
        jd_ref=jd,
        require_observed=True,
        require_canonical_exit=True,
        expected_target_company="Different Company",
        expected_target_role="Manager Applied AI Architecture Partnerships",
    )

    assert not validation.valid
    assert "identity_target_company_context_mismatch" in validation.reason


def test_consumer_rejects_legacy_only_product_handoff(tmp_path: Path) -> None:
    brief = tmp_path / "briefing.md"
    brief.write_text(_VALID_BRIEF, encoding="utf-8")
    (tmp_path / "apps_research_briefing_envelope.json").write_text(
        json.dumps(
            {
                "schema_version": "apps_research.apps_rg_briefing_envelope.v1",
                "producer_app": "apps_research",
                "consumer_app": "apps_rg",
            }
        ),
        encoding="utf-8",
    )

    validation = validate_apps_research_handoff(
        brief_ref=str(brief),
        require_observed=True,
        require_canonical_exit=True,
    )

    assert not validation.valid
    assert validation.reason == "legacy_only_handoff_rejected"


def test_atomic_publisher_never_exposes_final_directory_before_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apps_research.integrations.apps_rg_handoff as handoff

    original = handoff._write_fsync

    def fail_on_marker(path: Path, payload: bytes) -> None:
        if path.name == "bundle_commit_manifest.json":
            raise OSError("simulated marker write failure")
        original(path, payload)

    monkeypatch.setattr(handoff, "_write_fsync", fail_on_marker)
    runs_root = tmp_path / "runs"
    with pytest.raises(OSError, match="simulated marker write failure"):
        persist_apps_rg_targeting_brief_artifacts(
            record=_record("atomic-marker-failure"),
            target_company="Anthropic",
            target_role="Manager Applied AI Architecture Partnerships",
            jd_text="Lead partner solution architecture for Claude.",
            runs_root=runs_root,
        )

    assert not (runs_root / "atomic-marker-failure").exists()
    assert not list(runs_root.glob(".atomic-marker-failure.staging-*"))
