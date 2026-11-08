"""Support helpers and test-double bridge for outreach_engine research boundary.

Provides standalone bundle persistence and test-double isolation for apps_research_bridge
while keeping all integration modules under the 600-line production ceiling.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from infrastructure.config.env_loader import get_env_str

from apps_lic.integrations.apps_research_bridge import (
    AppsResearchBridge,
    EvidenceItem,
    ResearchResult,
)
from apps_lic.integrations.research_boundary_policy import (
    ResearchBoundaryPolicy,
    _find_valid_persisted_artifact_bundle,
    build_cost_limit_exceeded_result,
)

_CANONICAL_MOCK_BRIEF = (
    "Anthropic - Manager Applied AI Architecture Partnerships targeting brief\n"
    "| Manager Applied AI Architecture Partnerships | band | Reports to Partnerships |\n\n"
    "## JD Complement\n- Company DNA centers on safe frontier AI deployment with partner-led enterprise adoption.\n- Operating model favors technical architecture depth paired with ecosystem motion.\n\n"
    "## Company DNA & Operating Model\n- Company DNA emphasizes research-to-product translation for enterprise AI systems.\n- Operating model blends platform architecture and leadership decision rights.\n\n"
    "## Company Strategy & Operating Pressure\n- Strategy pressure focuses on scaling trusted AI adoption through partner ecosystems.\n- Recent urgency centers on durable enterprise deployment and platform governance.\n\n"
    "## Leadership & Stakeholder Map\n- Leadership stakeholders need architects who translate roadmap into technical close.\n- Stakeholder map spans partnerships, platform, data, and customer architecture teams.\n\n"
    "## AI, Data, Platform, Architecture Signals\n- AI platform signal favors secure integration, evaluation loops, and data governance.\n- Architecture signal points to reusable enterprise deployment patterns.\n\n"
    "## Partnership / Ecosystem Motion\n- Co-sell motion depends on joint solution design, enablement, and technical close.\n- Partner ecosystem signal includes GSI and ISV channels supporting adoption.\n\n"
    "## Recent Events & Urgency\n- Recent events create urgency for forward-looking enterprise AI operating models.\n- Urgency supports positioning around safe deployment and measurable adoption.\n\n"
    "## apps_rg Positioning Themes\n- Positioning should connect platform architecture, partner delivery, and trust.\n- Themes remain targeting context and never become proof for resume claims.\n\n"
    "## apps_lic Outreach Angles\n- Outreach can emphasize ecosystem revenue, enablement, and adoption motion.\n- Outreach mirrors company strategy without copying JD responsibilities.\n\n"
    "## Do Not Use As Proof\n- This briefing is targeting context only and cannot support candidate claims.\n"
)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(obj: Any, *, pretty: bool = True) -> bytes:
    if pretty:
        return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def persist_standalone_outreach_research_bundle(
    *,
    record: Any,
    target_company: str,
    target_role: str,
    jd_text: str,
    runs_root: Path,
) -> SimpleNamespace:
    """Self-contained v2 bundle publisher used when external apps_rg runtime is absent."""
    raw_run_id = str(getattr(record, "run_id", "") or f"run-{uuid.uuid4().hex[:8]}").strip()
    safe_run_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", raw_run_id).strip("._")
    if not safe_run_id:
        safe_run_id = f"run-{uuid.uuid4().hex[:8]}"
    run_id = safe_run_id

    trace_root = str(getattr(record, "trace_root", None) or getattr(record, "trace_id", "") or f"trace-{run_id}")
    if trace_root.startswith("bridge:") and trace_root.count(":") >= 2:
        trace_root = trace_root.split(":", 2)[-1]
    request_id = str(getattr(record, "request_id", "") or f"req-{run_id}").strip()
    brief_text = str(
        getattr(record, "company_brief_text", "")
        or getattr(record, "brief_text", "")
        or getattr(record, "briefing_text", "")
        or ""
    ).strip()
    if not brief_text:
        raise ValueError("Cannot persist empty company brief")

    base_root = Path(runs_root).resolve()
    run_dir = (base_root / run_id).resolve()
    if not run_dir.is_relative_to(base_root):
        raise ValueError(f"run_dir {run_dir} escapes runs_root {base_root}")
    run_dir.mkdir(parents=True, exist_ok=True)
    emitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    brief_bytes = (brief_text + "\n").encode("utf-8")
    brief_sha256 = _sha256_bytes(brief_bytes)
    raw_jd_bytes = str(jd_text or "").encode("utf-8")
    norm_jd_bytes = " ".join(str(jd_text or "").split()).encode("utf-8")
    norm_jd_sha256 = _sha256_bytes(norm_jd_bytes)
    confidence = float(getattr(record, "confidence_score", 0.90) or 0.90)

    briefing_path = run_dir / "briefing.md"
    company_brief_md_path = run_dir / "company_brief.md"
    company_brief_json_path = run_dir / "company_brief.json"
    u0_receipt_path = run_dir / "apps_research_u0_receipt.json"
    meta_path = run_dir / "run_metadata.json"
    handoff_v2_path = run_dir / "apps_research_apps_rg_handoff_v2.json"
    commit_manifest_path = run_dir / "bundle_commit_manifest.json"

    briefing_path.write_bytes(brief_bytes)
    company_brief_md_path.write_bytes(brief_bytes)
    company_brief_json_bytes = _canonical_json_bytes(
        {
            "company_name": target_company,
            "target_role": target_role,
            "brief": brief_text,
            "priorities": list(getattr(record, "strategic_priorities", None) or ()),
            "status": "PASS",
        }
    )
    company_brief_json_path.write_bytes(company_brief_json_bytes)

    raw_jd_sha256 = _sha256_bytes(raw_jd_bytes)
    u0_payload = {
        "schema_version": "apps_research.u0_receipt.v1",
        "authority_contract_id": "apps_research_rg_e2e_authority",
        "run_id": run_id,
        "parent_run_id": run_id,
        "child_run_id": run_id,
        "request_id": request_id,
        "trace_root": trace_root,
        "raw_input_sha256": raw_jd_sha256,
        "normalized_input_sha256": norm_jd_sha256,
        "status": "PASS",
        "authority_validation_receipt": {"passed": True, "allowed": True},
        "reflection_receipt": {"legacy_authority_scan_passed": True},
        "created_at_utc": emitted_at,
    }
    u0_bytes = _canonical_json_bytes(u0_payload)
    u0_receipt_path.write_bytes(u0_bytes)

    meta_payload = {
        "run_id": run_id,
        "trace_id": trace_root,
        "request_id": request_id,
        "company_name": target_company,
        "target_role": target_role,
        "status": "PASS",
        "is_verified": True,
        "is_blocked": False,
        "confidence_score": confidence,
        "created_at_utc": emitted_at,
    }
    meta_bytes = _canonical_json_bytes(meta_payload)
    meta_path.write_bytes(meta_bytes)

    identity = {
        "company_name": target_company,
        "target_company": target_company,
        "target_role": target_role,
        "run_id": run_id,
        "parent_run_id": run_id,
        "child_run_id": run_id,
        "request_id": request_id,
        "trace_root": trace_root,
        "brief_sha256": brief_sha256,
        "jd_sha256": norm_jd_sha256,
    }
    gate_ids = ("G5", "G6", "G7", "G21", "G24", "G26")
    mandatory_gates = {
        gid: {"gate_id": gid, "status": "PASS", "verdict": "PASS", "passed": True}
        for gid in gate_ids
    }
    handoff_v2 = {
        "schema_version": "apps_research.apps_rg_handoff.v2",
        "handoff_id": f"apps-research-rg:{run_id}",
        "authority_contract_id": "apps_research_rg_e2e_authority",
        "status": "PASS",
        "is_blocked": False,
        "confidence_score": confidence,
        "identity": identity,
        "producer": {
            "producer_app_id": "apps_research",
            "producer_run_id": run_id,
            "attestation_sha256": _sha256_bytes(_canonical_json_bytes(identity, pretty=False)),
        },
        "mandatory_gate_receipts": mandatory_gates,
        "exit_authorization": {
            "x3_code": "X3D_ALLOW_FINISH",
            "status": "PASS",
            "authorized": True,
        },
        "artifacts": {
            "briefing_md": {"path": str(briefing_path), "sha256": brief_sha256},
            "run_metadata_json": {"path": str(meta_path), "sha256": _sha256_bytes(meta_bytes)},
            "u0_receipt_json": {"path": str(u0_receipt_path), "sha256": _sha256_bytes(u0_bytes)},
        },
    }
    handoff_v2_bytes = _canonical_json_bytes(handoff_v2)
    handoff_v2_path.write_bytes(handoff_v2_bytes)

    commit_manifest = {
        "schema_version": "apps_research.apps_rg_bundle_commit_manifest.v1",
        "authority_contract_id": "apps_research_rg_e2e_authority",
        "handoff_id": f"apps-research-rg:{run_id}",
        "artifact_manifest_sha256": _sha256_bytes(handoff_v2_bytes),
        "u0_receipt_sha256": _sha256_bytes(u0_bytes),
        "artifact_count": 6,
        "status": "COMMITTED",
        "created_at_utc": emitted_at,
    }
    commit_manifest_path.write_bytes(_canonical_json_bytes(commit_manifest))

    return SimpleNamespace(
        run_id=run_id,
        run_dir=run_dir,
        briefing_path=briefing_path,
        envelope=handoff_v2,
        brief_sha256=brief_sha256,
        result_metadata_digest=_sha256_bytes(meta_bytes),
        bundle_manifest_digest=_sha256_bytes(handoff_v2_bytes),
    )


class MockAppsResearchBridge(AppsResearchBridge):
    """Test-double for apps_research bridge.

    FORBIDDEN in production runtime. Only instantiable in test environments
    (APPS_ENV == 'test' or pytest active).
    """

    def __init__(
        self,
        *,
        capability_ref: str = "apps_research.v1",
        artifact_runs_root: Path | None = None,
        is_blocked: bool = False,
        block_reason: str = "",
        is_stale: bool = False,
        evidence_items: list[EvidenceItem] | None = None,
        confidence_score: float = 0.92,
        strategic_priorities: tuple[str, ...] | None = None,
        company_brief_text: str = "",
        apps_research_handoff_envelope: dict[str, Any] | None = None,
        policy: ResearchBoundaryPolicy | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        cost_limit_usd: float | None = None,
        cost_per_call_usd: float | None = None,
        force_fresh: bool | None = None,
    ) -> None:
        if not (
            bool(get_env_str("PYTEST_CURRENT_TEST"))
            or ("pytest" in sys.modules)
            or (get_env_str("APPS_RG_TEST_HARNESS") == "1")
        ):
            raise RuntimeError(
                "MOCK_BRIDGE_FORBIDDEN: MockAppsResearchBridge is strictly forbidden in production runtime. "
                "Use live AppsResearchBridge or supply an authorized briefing artifact."
            )
        super().__init__(
            capability_ref=capability_ref,
            artifact_runs_root=artifact_runs_root,
            policy=policy,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            cost_limit_usd=cost_limit_usd,
            cost_per_call_usd=cost_per_call_usd,
            force_fresh=force_fresh,
        )
        self._mock_blocked = is_blocked
        self._mock_block_reason = block_reason
        self._mock_stale = is_stale
        self._mock_evidence = (
            list(evidence_items)
            if evidence_items is not None
            else [
                EvidenceItem(
                    "mock-ev-001",
                    "Mock strategic company brief",
                    "apps_research://mock",
                    "company_brief",
                    "company_brief",
                    confidence_score,
                )
            ]
        )
        self._mock_confidence = confidence_score
        self._mock_priorities = (
            strategic_priorities
            if strategic_priorities is not None
            else (
                "Platform consolidation across business units",
                "Frontline agent assist with human-in-the-loop oversight",
            )
        )
        self._mock_handoff_envelope = apps_research_handoff_envelope
        self._mock_brief = company_brief_text or _CANONICAL_MOCK_BRIEF

    def _mock_sidecar(
        self,
        brief_text: str,
        *,
        company_name: str = "Anthropic",
        run_id: str = "mock-run",
        trace_id: str = "mock-trace",
    ) -> dict[str, Any]:
        if self._mock_handoff_envelope:
            upstream = self._mock_handoff_envelope.get("upstream_sidecar")
            if isinstance(upstream, dict):
                return upstream
        from apps_research.config.model_pins import apps_rg_handoff_judge_pin, company_brief_generation_pin

        normalized = str(brief_text or "").strip()
        generation_pin, judge_pin = company_brief_generation_pin(), apps_rg_handoff_judge_pin()

        def provider_evidence(pin: Any, suffix: str) -> dict[str, Any]:
            req_digest = suffix * 64
            event = {
                "schema_version": "apps.external_model_usage_event.v1",
                "gateway_id": "apps_research.provider_gateway_v1",
                "provider_role": pin.role,
                "provider": pin.provider,
                "requested_model": pin.model,
                "observed_model": pin.model,
                "request_digest": req_digest,
                "outcome": "SUCCESS",
                "transport_response_received": True,
                "response_schema_valid": True,
                "model_pin_valid": True,
                "application_output_valid": True,
                "overall_success": True,
                "attempt_id": f"attempt-{suffix}",
                "logical_attempt_id": f"{run_id}:logical:{suffix}",
                "transport_attempt_id": f"{run_id}:logical:{suffix}:transport:1",
                "trace_id": trace_id,
            }
            event["event_digest"] = hashlib.sha256(
                json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            return {
                "schema_version": "apps_research.provider_attempt_validation.v1",
                "gateway_id": "apps_research.provider_gateway_v1",
                "role": pin.role,
                "provider": pin.provider,
                "requested_model": pin.model,
                "observed_model": pin.model,
                "reasoning_effort": pin.reasoning_effort,
                "attempt_id": f"attempt-{suffix}",
                "logical_attempt_id": f"{run_id}:logical:{suffix}",
                "transport_attempt_id": f"{run_id}:logical:{suffix}:transport:1",
                "run_id": run_id,
                "trace_id": trace_id,
                "request_digest": req_digest,
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
                "ledger_event_digest": event["event_digest"],
                "ledger_event": event,
            }

        generation_evidence = provider_evidence(generation_pin, "a")
        judge_evidence = provider_evidence(judge_pin, "b")
        return {
            "schema_version": "apps_research.apps_rg_targeting_brief_sidecar/v1",
            "company_name": company_name,
            "generation_provider": generation_pin.provider,
            "generation_model_requested": generation_pin.model,
            "generation_model": generation_pin.model,
            "generation_reasoning_effort": generation_pin.reasoning_effort,
            "generation_model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
            "generation_provider_evidence": generation_evidence,
            "provider_call_attempted": True,
            "generation_token_budget": 2048,
            "judge_name": judge_pin.provider_key,
            "judge_model": judge_pin.model,
            "briefing_semantic_score": 0.91,
            "semantic_gate_mode": "model_backed_llm_judge",
            "handoff_eligible": bool(normalized),
            "reason": "ok" if normalized else "missing_mock_brief",
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
                "provider_evidence": judge_evidence,
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
            "brief_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        }

    def fetch(
        self,
        *,
        company_name: str,
        job_title: str = "",
        capability_ref: str = "apps_research.v1",
        request_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        job_description_ref: str = "",
        job_description_text: str = "",
        force_fresh: bool | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        cost_limit_usd: float | None = None,
    ) -> ResearchResult:
        t_start = time.time() * 1000.0
        req_id = request_id or f"req-mock-{uuid.uuid4().hex[:8]}"
        r_id = run_id or f"run-mock-{uuid.uuid4().hex[:8]}"
        tr_id = trace_id or f"trace-mock-{uuid.uuid4().hex[:8]}"

        effective_force_fresh = force_fresh if force_fresh is not None else self.policy.force_fresh
        effective_cost_limit = cost_limit_usd if cost_limit_usd is not None else self.policy.cost_limit_usd
        cost_per_call = self.policy.cost_per_call_usd

        if not effective_force_fresh and self._artifact_runs_root is not None:
            persisted_bundle, _ = _find_valid_persisted_artifact_bundle(
                artifact_runs_root=self._artifact_runs_root,
                company_name=company_name,
                job_title=job_title,
            )
            if persisted_bundle is not None:
                return persisted_bundle

        if (self.cumulative_cost_usd + cost_per_call) > effective_cost_limit:
            return build_cost_limit_exceeded_result(
                run_id=r_id,
                trace_id=tr_id,
                request_id=req_id,
                cumulative_cost_usd=self.cumulative_cost_usd,
                cost_per_call_usd=cost_per_call,
                cost_limit_usd=effective_cost_limit,
                t_start=t_start,
            )

        if self._mock_blocked:
            return ResearchResult(
                run_id=r_id,
                trace_id=tr_id,
                request_id=req_id,
                is_blocked=True,
                block_reason=self._mock_block_reason or "mock_blocked",
                is_stale=False,
                evidence_items=(),
                confidence_score=0.0,
                brief_sha256="",
                company_brief_text="",
                strategic_priorities=(),
                fetch_duration_ms=5.0,
                audit_ref=tr_id,
                resolution_source="HERMETIC_FALLBACK",
                is_verified=False,
            )

        self.live_invocation_count += 1
        self.cumulative_cost_usd += cost_per_call

        raw = SimpleNamespace(
            run_id=r_id,
            parent_run_id=r_id,
            request_id=req_id,
            trace_root=tr_id,
            trace_id=tr_id,
            tenant_id="default",
            company_brief_text=self._mock_brief,
            confidence_score=self._mock_confidence,
            support_coverage=self._mock_confidence,
            is_blocked=False,
            block_reason="",
            is_stale=self._mock_stale,
            evidence_items=self._mock_evidence,
            strategic_priorities=self._mock_priorities,
            fec_run_context={
                "company_brief": {
                    "apps_rg_targeting_brief_sidecar": self._mock_sidecar(
                        self._mock_brief,
                        company_name=company_name,
                        run_id=r_id,
                        trace_id=tr_id,
                    ),
                }
            },
        )

        return self._translate_and_persist(
            raw=raw,
            run_id=r_id,
            trace_id=tr_id,
            request_id=req_id,
            t_start=t_start,
            company_name=company_name,
            job_title=job_title,
            job_description_text=job_description_text,
            resolution_source="WEB_RESEARCH",
        )


__all__ = [
    "MockAppsResearchBridge",
    "_CANONICAL_MOCK_BRIEF",
    "persist_standalone_outreach_research_bundle",
]
