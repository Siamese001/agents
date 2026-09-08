"""Whole-run CLI: U0→L1→L0 route governance + optional R3R4 apps_research → R4 draft leg."""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from apps_rg.prerequisites.briefing_validator import validate_apps_research_handoff
from apps_rg.runtime.bindings.briefing_mode_classifier import classify_briefing_mode
from apps_rg.runtime.bindings.l0_binding import l0_route_apps_rg
from apps_rg.runtime.bindings.l0_route_evidence import L1PlanNotReadyError
from apps_rg.runtime.bindings.l1_binding import l1_plan_apps_rg
from apps_rg.runtime.bindings.u0_binding import u0_validate_apps_rg
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    emit_plan_execution_reconciliation,
)
from apps_rg.runtime.contracts.failure_aware_replan import emit_failure_aware_replan
from apps_rg.runtime.dispatch import spine_stage_receipts as sr
from apps_rg.runtime.executive_summary_certification import (
    EXECUTIVE_SUMMARY_JUDGE_REVIEW_X3,
    executive_summary_certification_block,
)
from apps_rg.runtime.full_resume_review_bundle import (
    REVIEW_BUNDLE_FILENAME,
    emit_full_resume_review_bundle,
)
from apps_rg.runtime.orchestration.integrated_spine_runner import (
    run_integrated_single_action_spine,
)
from apps_rg.runtime.run_bundle_index import emit_integrated_run_bundle_index
from apps_rg.runtime.runtime_proof_layout import (
    allocate_full_resume_artifact_dir,
    find_repo_root,
    is_integrated_whole_run_artifact_dir,
)

ROUTE_FAMILY_R3R4 = "R3R4_MANAGED_WORKFLOW"
DRAFT_LEG_ROUTE_FAMILY = "R4_SINGLE_ACTION"
_PRODUCT_SUCCESS_X3 = "X3D_ALLOW_FINISH"


class ProductE2EAuthorityError(RuntimeError):
    """Raised when the frozen product authority chain cannot be constructed."""


def _product_x3_authorizes(value: Any) -> bool:
    """Return true only for the frozen canonical product-success code."""

    return str(value or "").strip() == _PRODUCT_SUCCESS_X3


def _authority_source_refs(receipt_path: Path) -> tuple[str, ...]:
    """Return exact source refs embedded by a receipt-derived adapter."""

    try:
        receipt = json.loads(Path(receipt_path).read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductE2EAuthorityError(
            f"stage authority receipt is unreadable: {type(exc).__name__}"
        ) from exc
    rows = receipt.get("source_bindings") if isinstance(receipt, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ProductE2EAuthorityError(
            "stage authority receipt has no exact source bindings"
        )
    refs = tuple(
        str(row.get("artifact_ref") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("artifact_ref") or "")
    )
    if len(refs) != len(rows):
        raise ProductE2EAuthorityError(
            "stage authority receipt contains an invalid source binding"
        )
    return refs


def _aggregate_x3_for_outcome(raw_x3: str | None, *, outcome: bool) -> str:
    """Preserve the source X3 decision; completion status carries later failures."""
    del outcome
    return str(raw_x3 or "")


def _whole_run_exit_identity(
    *, raw_request: dict[str, Any], validated_request: Any
) -> dict[str, Any]:
    """Return product identity when present, otherwise a labelled non-product projection.

    A compatibility/evaluation invocation intentionally has no Apps Research
    producer identity.  Its exit packet must still bind to the exact validated
    request, but it must not invent or masquerade as product identity.
    """

    candidate = raw_request.get("canonical_run_identity")
    if isinstance(candidate, dict) and candidate:
        return dict(candidate)
    return {
        "identity_class": "APPS_RG_NON_PRODUCT_VALIDATED_REQUEST",
        "app_id": str(getattr(validated_request, "app_id", "apps_rg") or "apps_rg"),
        "request_id": str(getattr(validated_request, "request_id", "") or ""),
        "run_id": str(getattr(validated_request, "run_id", "") or ""),
        "trace_id": str(getattr(validated_request, "trace_id", "") or ""),
        "tenant_id": str(getattr(validated_request, "tenant_id", "") or ""),
        "product_authorizing": False,
    }


def _default_artifact_dir(explicit: str) -> Path:
    if str(explicit).strip():
        return Path(explicit)
    return allocate_full_resume_artifact_dir(find_repo_root())


def _read_optional_brief(path_or_url: str) -> str:
    from apps_rg.runtime.orchestration.canonical_dispatch import _read_optional_brief as _rob

    return _rob(path_or_url)


def research_delegation_enabled(
    *,
    auto_research_internal: bool,
    research_via: str | None,
) -> bool:
    _ = research_via
    return bool(auto_research_internal)


def briefing_input_present(manual_brief: str) -> bool:
    return bool(_read_optional_brief(manual_brief).strip())


def apps_research_handoff_authorized(manual_brief: str, *, jd_ref: str = "") -> bool:
    validation = validate_apps_research_handoff(
        brief_ref=manual_brief,
        jd_ref=jd_ref,
        require_observed=True,
        require_x1_x3_authorization=True,
    )
    return bool(validation.valid)


def _validate_handoff_for_ingress_envelope(
    *,
    brief_ref: str,
    jd_ref: str,
    envelope: Any,
    require_observed: bool,
) -> Any:
    """Validate a reusable research handoff against this exact ingress run.

    A producer bundle is not portable across independently-created Apps RG
    runs.  The same bindings are enforced by U0, so the pre-U0 reuse decision
    must use them too; otherwise the runner can skip research and then send a
    handoff to U0 that U0 correctly rejects.
    """

    return validate_apps_research_handoff(
        brief_ref=brief_ref,
        jd_ref=jd_ref,
        require_observed=require_observed,
        require_x1_x3_authorization=require_observed,
        require_canonical_exit=require_observed,
        expected_target_company=str(envelope.app_payload.get("target_company") or ""),
        expected_target_role=str(envelope.app_payload.get("target_role") or ""),
        expected_parent_run_id=str(envelope.run_id),
        expected_request_id=str(envelope.request_id),
        expected_trace_root=str(envelope.trace_id),
        expected_tenant_id=str(envelope.tenant_id),
    )


def should_delegate_apps_research(
    *,
    route_family: str,
    manual_brief: str,
    auto_research_internal: bool,
    research_via: str | None,
    jd_ref: str = "",
) -> bool:
    if route_family != ROUTE_FAMILY_R3R4:
        return False
    if not research_delegation_enabled(
        auto_research_internal=auto_research_internal,
        research_via=research_via,
    ):
        return False
    if not briefing_input_present(manual_brief):
        return True
    return not apps_research_handoff_authorized(manual_brief, jd_ref=jd_ref)


def _research_bridge(*, artifact_runs_root: Path) -> Any:
    import importlib

    output_root = Path(artifact_runs_root).resolve()
    if os.environ.get("APPS_RG_MOCK_RESEARCH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        MockAppsResearchBridge = importlib.import_module("apps_rg.integrations.apps_research_bridge").MockAppsResearchBridge
        return MockAppsResearchBridge(
            confidence_score=0.88,
            artifact_runs_root=output_root,
        )

    AppsResearchBridge = importlib.import_module("apps_rg.integrations.apps_research_bridge").AppsResearchBridge
    return AppsResearchBridge(
        capability_ref="apps_research.v1",
        artifact_runs_root=output_root,
    )


def _build_cli_ingress_envelope(
    *,
    target_company: str,
    target_role: str,
    target_level: str,
    jd: str,
    job_description_ref: str,
    job_description_text: str,
    manual_brief: str,
    resume_path: str,
    source_resume_text: str,
    generation_mode: str,
    l1_cognitive_treatment_arm: str,
    auto_research_internal: bool,
    research_via: str | None,
    validated_input_bundle_ref: str = "",
    validated_input_bundle_digest: str = "",
) -> SimpleNamespace:
    request_id = f"req-{uuid.uuid4().hex}"
    run_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    # G23 (plan apps-rg-e2e-gap-remediation-7e2d9c): the CLI ``--jd`` value arrives as ``jd`` but was
    # never written into app_payload, so U0 fell back to DEFAULT_SSOT generic targeting and the resume
    # ignored the job description. Map it into the canonical fields when an explicit ref/text was not
    # supplied: an existing path becomes job_description_ref; inline text becomes job_description_text.
    jd_cli = str(jd or "").strip()
    if jd_cli and not str(job_description_ref or "").strip() and not str(job_description_text or "").strip():
        try:
            _jd_is_path = Path(jd_cli).expanduser().exists()
        except OSError:
            _jd_is_path = False
        if _jd_is_path:
            job_description_ref = jd_cli
        else:
            job_description_text = jd_cli
    app_payload: dict[str, Any] = {
        "target_company": target_company,
        "target_role": target_role,
        "target_title": target_role,
        "target_level": target_level,
        "job_description_text": job_description_text,
        "jd_text": job_description_text,
        "job_description_ref": job_description_ref,
        "manual_brief_path": manual_brief,
        "briefing_artifact_ref": manual_brief,
        "source_resume_ref": resume_path,
        "source_resume_text": source_resume_text,
        "generation_mode": generation_mode,
        "task_spec": {"generation_mode": generation_mode},
        "user_constraints": {
            "_l1_cognitive_treatment_arm": l1_cognitive_treatment_arm,
        },
        "transport": "ui",
        "source_channel": "apps_rg_cli",
        "auto_research_internal": auto_research_internal,
        "research_via": research_via,
        "validated_input_bundle_ref": validated_input_bundle_ref,
        "validated_input_bundle_digest": validated_input_bundle_digest,
    }
    return SimpleNamespace(
        app_payload=app_payload,
        request_id=request_id,
        run_id=run_id,
        trace_id=trace_id,
        app_id="apps_rg",
        tenant_id="default",
    )


def _route_contract_payload(route: Any) -> dict[str, Any]:
    return {
        "route_id": route.route_id,
        "route_family": route.route_family,
        "execution_form": route.execution_form,
        "l3_required": route.l3_required,
        "grounding_required": route.grounding_required,
        "route_profile_ref": route.route_profile_ref,
        "reason_codes": list(route.reason_codes),
        "request_id": route.request_id,
        "run_id": route.run_id,
        "trace_id": route.trace_id,
    }


def _pre_u0_research_route(envelope: Any) -> SimpleNamespace:
    """Stable delegation identity used only to dispatch apps_research before U0."""
    return SimpleNamespace(
        route_id=ROUTE_FAMILY_R3R4,
        route_family=ROUTE_FAMILY_R3R4,
        execution_form="MANAGED_WORKFLOW",
        l3_required=True,
        grounding_required=True,
        route_profile_ref="pre_u0_research_delegation.v1",
        reason_codes=("PRE_U0_APPS_RESEARCH_DELEGATION",),
        request_id=str(envelope.request_id),
        run_id=str(envelope.run_id),
        trace_id=str(envelope.trace_id),
    )


def _write_mock_elimination_proof(artifact_dir: Path, bridge: Any) -> None:
    sr.write_stage_receipt(
        artifact_dir / sr.FILENAME_MOCK_ELIMINATION_PROOF,
        {
            "APPS_RG_MOCK_RESEARCH": os.environ.get("APPS_RG_MOCK_RESEARCH", ""),
            "bridge_class": type(bridge).__name__,
            "mock_env_active": os.environ.get("APPS_RG_MOCK_RESEARCH", "").strip().lower()
            in ("1", "true", "yes"),
        },
    )


def _run_r3r4_research_hop(
    *,
    route: Any,
    validated_request: Any,
    artifact_dir: Path,
    target_company: str,
    target_role: str,
    job_description_ref: str = "",
    job_description_text: str = "",
) -> tuple[bool, str, str]:
    import importlib

    _delegation = importlib.import_module(
        "apps_rg.integrations.managed_research_delegation"
    )
    RequestForResumeBriefing = _delegation.RequestForResumeBriefing
    ResearchDispatchFailure = _delegation.ResearchDispatchFailure
    ResumeBriefingReady = _delegation.ResumeBriefingReady
    dispatch_resume_research_briefing = _delegation.dispatch_resume_research_briefing

    req = RequestForResumeBriefing(
        request_id=route.request_id,
        run_id=route.run_id,
        trace_id=route.trace_id,
        company_name=target_company,
        job_title=target_role,
        research_authorized=True,
        tenant_id=str(getattr(validated_request, "tenant_id", "") or "default"),
        job_description_ref=job_description_ref,
        job_description_text=job_description_text,
    )
    artifact_root = Path(artifact_dir).resolve()
    artifact_runs_root = (artifact_root / "apps_research" / "runs").resolve()
    artifact_runs_root.relative_to(artifact_root)
    artifact_runs_root.mkdir(parents=True, exist_ok=True)
    bridge = _research_bridge(artifact_runs_root=artifact_runs_root)
    _write_mock_elimination_proof(artifact_dir, bridge)
    sr.write_stage_receipt(
        artifact_dir / sr.FILENAME_ROUTE_PRE_RESEARCH,
        _route_contract_payload(route),
    )
    request_receipt = dataclasses.asdict(req)
    request_receipt["artifact_runs_root"] = str(artifact_runs_root)
    sr.write_stage_receipt(
        artifact_dir / sr.FILENAME_RESEARCH_BRIDGE_REQUEST,
        request_receipt,
    )

    outcome = dispatch_resume_research_briefing(req, bridge=bridge)

    if isinstance(outcome, ResumeBriefingReady):
        producer_run_dir = Path(str(outcome.research_artifact_dir or ""))
        producer_briefing = Path(str(outcome.research_briefing_path or ""))
        if (
            not producer_run_dir.is_dir()
            or not producer_briefing.is_file()
            or not producer_briefing.resolve().is_relative_to(producer_run_dir.resolve())
        ):
            sr.write_stage_receipt(
                artifact_dir / sr.FILENAME_RESEARCH_BRIDGE_RESPONSE,
                {
                    "outcome": "ResearchDispatchFailure",
                    "r5_reason_code": "APPS_RESEARCH_ARTIFACT_MISSING",
                    "detail": "ResumeBriefingReady lacked producer-owned persisted briefing evidence",
                    "research_artifact_dir": str(outcome.research_artifact_dir or ""),
                    "research_briefing_path": str(outcome.research_briefing_path or ""),
                },
            )
            return False, "APPS_RESEARCH_ARTIFACT_MISSING", ""
        sr.write_stage_receipt(
            artifact_dir / sr.FILENAME_RESEARCH_BRIDGE_RESPONSE,
            {
                "outcome": "ResumeBriefingReady",
                "research_run_id": outcome.research_run_id,
                "research_evidence_count": outcome.research_evidence_count,
                "confidence_score": outcome.confidence_score,
                "evidence_lineage": list(outcome.evidence_lineage),
                "research_artifact_dir": outcome.research_artifact_dir,
                "research_briefing_path": outcome.research_briefing_path,
                "artifact_runs_root": str(producer_run_dir.parent.resolve()),
                "apps_research_handoff_v2": outcome.apps_research_handoff_envelope,
            },
        )
        brief_path = artifact_dir / sr.FILENAME_DELEGATED_BRIEFING
        brief_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(producer_briefing, brief_path)
        handoff_v2 = dict(outcome.apps_research_handoff_envelope)
        fec_path = artifact_dir / sr.FILENAME_RESEARCH_EVIDENCE_CONTRACT
        sr.write_stage_receipt(
            fec_path,
            {
                "schema_version": "apps_rg.research_fec_stub.v1",
                "research_run_id": outcome.research_run_id,
                "result_hash": outcome.result_hash,
                "evidence_lineage": list(outcome.evidence_lineage),
                "confidence_score": outcome.confidence_score,
                "apps_research_handoff_v2": handoff_v2,
                "proof_note": "FEC-shaped contract for external review; full FEC lives under apps_research run when present.",
            },
        )
        sr.write_stage_receipt(
            artifact_dir / "research" / "research_artifact_ref.json",
            {
                "research_run_id": outcome.research_run_id,
                "research_artifact_dir": str(producer_run_dir.resolve()),
                "research_briefing_path": str(producer_briefing.resolve()),
                "research_company_brief_path": str(
                    (producer_run_dir / "company_brief.json").resolve()
                ),
                "research_handoff_v2_path": str(
                    (
                        producer_run_dir
                        / "apps_research_apps_rg_handoff_v2.json"
                    ).resolve()
                ),
                "consumer_delegated_briefing_path": str(brief_path.resolve()),
            },
        )
        # Product validation must consume the producer-owned brief adjacent to
        # its committed v2 manifest. The consumer copy is diagnostics only.
        return True, "ResumeBriefingReady", str(producer_briefing.resolve())

    if isinstance(outcome, ResearchDispatchFailure):
        sr.write_stage_receipt(
            artifact_dir / sr.FILENAME_RESEARCH_BRIDGE_RESPONSE,
            {
                "outcome": "ResearchDispatchFailure",
                "r5_reason_code": outcome.r5_reason_code,
                "detail": outcome.detail,
            },
        )
        return False, outcome.r5_reason_code, ""

    return False, "unknown_dispatch_outcome", ""


def _augment_r4_manifest_draft_leg_only(artifact_dir: Path, *, spine_manifest_ref: str) -> None:
    path = artifact_dir / sr.FILENAME_DRAFT_LEG_MANIFEST
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):  # guardian: allow-return-none-swallow -- P2 burndown: fail-soft optional boundary
        return
    data["apps_rg_proof_scope"] = "draft_leg_only"
    data["apps_rg_orchestration_manifest_ref"] = spine_manifest_ref
    data["apps_rg_whole_run_route_family"] = ROUTE_FAMILY_R3R4
    data["apps_rg_draft_leg_route_family"] = DRAFT_LEG_ROUTE_FAMILY
    data["apps_rg_whole_dag_proof_authority"] = spine_manifest_ref
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:  # guardian: allow-return-none-swallow -- P2 burndown: fail-soft optional boundary
        return


def _failure_payload(
    *,
    artifact_dir: Path,
    route: Any,
    reason: str,
    route_decision: dict[str, Any],
) -> dict[str, Any]:
    spine = {
        "schema_version": "apps_rg.spine_run_manifest.v1",
        "route_family": route.route_family,
        "route_id": route.route_id,
        "execution_form": route.execution_form,
        "proof_authority": "spine_run_manifest.json",
        "draft_leg_manifest": sr.FILENAME_DRAFT_LEG_MANIFEST,
        "draft_leg_proof_scope": "draft_leg_only",
        "research_delegation_required": True,
        "research_delegation_outcome": reason,
        "route_decision": route_decision,
        "terminal_r5": True,
        "x3_disposition": "X3_BLOCK",
        "exit_status": "error",
        "outcome_authorized": False,
    }
    sr.write_stage_receipt(artifact_dir / sr.FILENAME_SPINE_MANIFEST, spine)
    return {
        "exit_status": "error",
        "execution_status": "failed",
        "outcome_authorized": False,
        "x3_disposition": "X3_BLOCK",
        "fault": reason,
        "artifact_dir": str(artifact_dir),
        "route_family": route.route_family,
        "spine_run_manifest": str(artifact_dir / sr.FILENAME_SPINE_MANIFEST),
        "research_note": reason,
    }


def _emit_terminal_mandatory_closeout(
    *,
    artifact_dir: Path,
    repo_root: Path,
    payload: dict[str, Any],
    final_resume_outputs_pre_emitted: bool = False,
) -> dict[str, Any]:
    """Emit and enforce every mandatory terminal artifact for any E2E outcome."""
    from apps_rg.runtime.mandatory_run_outputs import (
        MANDATORY_OUTPUT_HARD_STOP_GATE_ID,
        emit_mandatory_run_outputs,
    )
    from apps_rg.runtime.section_failure_forensics import (
        E2E_SECTION_FORENSICS_GATE_ID,
    )

    try:
        mandatory_emit = emit_mandatory_run_outputs(
            artifact_dir,
            repo_root=repo_root,
            result=payload,
            print_stdout=False,
            emit_final_outputs=not final_resume_outputs_pre_emitted,
        )
    except Exception as exc:  # terminal evidence must not replace the upstream outcome
        from apps_rg.runtime.failure_evidence import (
            atomic_write_json,
            capture_failure_otel_evidence,
            exception_failure_envelope,
        )

        prior_fault = str(payload.get("fault") or "")
        identity_raw = payload.get("canonical_run_identity") or payload.get("identity") or {}
        identity = dict(identity_raw) if isinstance(identity_raw, dict) else {}
        for source, target in (
            ("request_id", "request_id"),
            ("trace_root", "trace_root"),
            ("trace_id", "trace_id"),
            ("tenant_id", "tenant_id"),
        ):
            if payload.get(source) and not identity.get(target):
                identity[target] = payload[source]
        closeout_failure = exception_failure_envelope(
            exc,
            stage="TERMINAL_MANDATORY_CLOSEOUT",
            operation="emit_mandatory_run_outputs",
            source_component="apps_rg.runtime.mandatory_run_outputs",
            artifact_dir=artifact_dir,
            integrated_artifact_dir=artifact_dir,
            identity=identity,
            run_id=str(payload.get("run_id") or artifact_dir.name),
            dispatch_invoked=True,
        )
        otel = capture_failure_otel_evidence(
            artifact_dir=artifact_dir,
            trace_root=str(closeout_failure.get("trace_root") or ""),
            stage="TERMINAL_MANDATORY_CLOSEOUT",
            operation="emit_mandatory_run_outputs",
            filename="terminal_closeout_otel_trace_snapshot.json",
        )
        receipt_path = artifact_dir / "terminal_closeout_failure.json"
        receipt = {
            "schema_version": "apps_rg.terminal_closeout_failure.v1",
            "status": "FAILED",
            "product_authorized": False,
            "pipeline_complete": False,
            "upstream_outcome": {
                "fault": prior_fault,
                "exit_status": str(payload.get("exit_status") or ""),
                "execution_status": str(payload.get("execution_status") or ""),
            },
            "closeout_failure": closeout_failure,
            "otel_snapshot_ref": "terminal_closeout_otel_trace_snapshot.json",
            "otel_capture_status": str(otel.get("status") or ""),
        }
        receipt_written = False
        receipt_write_error = ""
        try:
            atomic_write_json(receipt_path, receipt)
            receipt_written = True
        except OSError as receipt_exc:
            receipt_write_error = f"{type(receipt_exc).__name__}:{receipt_exc}"
        payload.update(
            {
                "exit_status": "error",
                "execution_status": "failed",
                "outcome_authorized": False,
                "completion_status": "BLOCKED",
                "fault": prior_fault or MANDATORY_OUTPUT_HARD_STOP_GATE_ID,
                "completion_fault": MANDATORY_OUTPUT_HARD_STOP_GATE_ID,
                "mandatory_output_upstream_fault": prior_fault,
                "mandatory_output_emit_error": str(exc),
                "mandatory_output_emit_error_class": type(exc).__name__,
                "terminal_closeout_failure_receipt": (
                    str(receipt_path) if receipt_written else ""
                ),
                "terminal_closeout_failure_receipt_write_error": receipt_write_error,
                "terminal_closeout_otel_capture_status": str(otel.get("status") or ""),
                "terminal_closeout_failed": True,
                "mandatory_output_hard_stop": {
                    "required": True,
                    "pass": False,
                    "reason": "TERMINAL_MANDATORY_CLOSEOUT_FAILED",
                    "error": str(exc),
                    "error_class": type(exc).__name__,
                },
            }
        )
        return payload

    payload.update(
        {
            "mandatory_run_output_json": str(mandatory_emit["json_path"]),
            "mandatory_run_output_md": str(mandatory_emit["markdown_path"]),
            "bcg_executive_output_md": str(mandatory_emit["bcg_markdown_path"]),
        }
    )
    emitted_payload = (
        mandatory_emit.get("payload") if isinstance(mandatory_emit, dict) else {}
    )
    forensics_gate = (
        emitted_payload.get("section_failure_forensics")
        if isinstance(emitted_payload, dict)
        and isinstance(emitted_payload.get("section_failure_forensics"), dict)
        else {}
    )
    if forensics_gate.get("required") and not bool(forensics_gate.get("pass")):
        prior_fault = str(payload.get("fault") or "")
        payload.update(
            {
                "exit_status": "error",
                "execution_status": "failed",
                "outcome_authorized": False,
                "completion_status": "BLOCKED",
                "fault": prior_fault or E2E_SECTION_FORENSICS_GATE_ID,
                "completion_fault": E2E_SECTION_FORENSICS_GATE_ID,
                "section_failure_forensics_gate": forensics_gate,
                "mandatory_output_upstream_fault": prior_fault,
                "terminal_closeout_failed": True,
            }
        )
    mandatory_gate = (
        mandatory_emit.get("mandatory_output_gate")
        if isinstance(mandatory_emit, dict)
        and isinstance(mandatory_emit.get("mandatory_output_gate"), dict)
        else {}
    )
    if mandatory_gate.get("required") and not bool(mandatory_gate.get("pass")):
        prior_fault = str(payload.get("fault") or "")
        payload.update(
            {
                "exit_status": "error",
                "execution_status": "failed",
                "outcome_authorized": False,
                "completion_status": "BLOCKED",
                "fault": prior_fault or (
                    E2E_SECTION_FORENSICS_GATE_ID
                    if not bool(forensics_gate.get("pass", True))
                    else MANDATORY_OUTPUT_HARD_STOP_GATE_ID
                ),
                "completion_fault": (
                    E2E_SECTION_FORENSICS_GATE_ID
                    if not bool(forensics_gate.get("pass", True))
                    else MANDATORY_OUTPUT_HARD_STOP_GATE_ID
                ),
                "mandatory_output_hard_stop": mandatory_gate,
                "mandatory_output_upstream_fault": prior_fault,
                "terminal_closeout_failed": True,
            }
        )
    return payload


def _activate_product_stage_ledger(
    *,
    artifact_dir: Path,
    legacy_ledger: Any,
    identity: dict[str, Any],
    preflight_validation: Any,
    continuation_path: Path,
    manual_brief: str,
    research_ran: bool,
) -> Any:
    """Replace pre-identity compatibility evidence with the product-v2 ledger.

    Fresh preflight necessarily runs before apps_research creates its child-run
    identity.  The early ledger therefore remains explicitly non-product.  Once
    the committed producer bundle supplies the frozen identity, this function
    binds the already-consumed continuation to that identity and starts the
    canonical receipt-derived ledger from exact artifact bytes.
    """

    from apps_rg.prerequisites.briefing_validator import (
        find_apps_research_handoff_v2_for_briefing,
    )
    from apps_rg.runtime.e2e_preflight import (
        E2E_PREFLIGHT_CONTINUATION_CONSUMPTION_FILENAME,
        bind_preflight_to_product_identity,
    )
    from apps_rg.runtime.e2e_stage_ledger import ReceiptDerivedE2EStageLedger
    from apps_rg.runtime.product_stage_authority import (
        mirror_external_authority_artifact,
    )

    root = Path(artifact_dir).resolve()
    if preflight_validation is None or not preflight_validation.valid:
        raise ProductE2EAuthorityError("fresh preflight validation is unavailable")
    manifest_path = find_apps_research_handoff_v2_for_briefing(manual_brief)
    if manifest_path is None:
        raise ProductE2EAuthorityError(
            "product execution requires a committed apps_research handoff v2"
        )
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductE2EAuthorityError(
            f"committed handoff manifest is unreadable: {type(exc).__name__}"
        ) from exc
    if not isinstance(manifest, dict) or manifest.get("identity") != identity:
        raise ProductE2EAuthorityError(
            "committed handoff identity differs from consumer-validated identity"
        )

    product_entry_path = bind_preflight_to_product_identity(
        validation=preflight_validation,
        receipt_path=continuation_path,
        secret=str(os.environ.get("APPS_RG_ROUTE_HMAC_SECRET") or ""),
        identity=identity,
        consumer_id="apps_rg.whole_run.primary",
    )

    preidentity_path = root / "e2e_stage_ledger_preidentity_non_product.json"
    if preidentity_path.exists():
        raise ProductE2EAuthorityError("pre-identity compatibility ledger already exists")
    legacy_path = Path(legacy_ledger.path)
    legacy_path.replace(preidentity_path)
    # Continue any compatibility-only failure reporting away from the canonical
    # product ledger path.  Product-v2 never invokes caller-asserted record().
    legacy_ledger.path = preidentity_path

    ledger = ReceiptDerivedE2EStageLedger.create(
        artifact_dir=root,
        identity=identity,
    )
    ledger.record_from_receipt(
        stage_id="FRESH_PREFLIGHT",
        receipt_ref=product_entry_path,
        artifact_refs=(
            continuation_path,
            root / E2E_PREFLIGHT_CONTINUATION_CONSUMPTION_FILENAME,
        ),
        next_stage_id="APPS_RESEARCH_U0" if research_ran else "APPS_RG_U0",
    )

    producer_root = manifest_path.parent.resolve()

    def _mirror(name: str) -> Path:
        return mirror_external_authority_artifact(
            artifact_dir=root,
            source=producer_root / name,
            relative_ref=f"apps_research/{name}",
        )

    if research_ran:
        producer_u0 = _mirror("apps_research_u0_receipt.json")
        producer_runtime = _mirror("runtime_exhaust_bundle.json")
        producer_exit = _mirror("exit_disposition_receipt.json")
        producer_manifest = _mirror("apps_research_apps_rg_handoff_v2.json")
        producer_marker = _mirror("bundle_commit_manifest.json")
        ledger.record_from_receipt(
            stage_id="APPS_RESEARCH_U0",
            receipt_ref=producer_u0,
        )
        ledger.record_from_receipt(
            stage_id="APPS_RESEARCH_RUNTIME",
            receipt_ref=producer_runtime,
        )
        ledger.record_from_receipt(
            stage_id="APPS_RESEARCH_EXIT",
            receipt_ref=producer_exit,
        )
        ledger.record_from_receipt(
            stage_id="HANDOFF_BUNDLE_COMMIT",
            receipt_ref=producer_manifest,
            artifact_refs=(producer_marker,),
        )

    consumer_validation = _mirror("apps_research_handoff_validation_receipt.json")
    ledger.record_from_receipt(
        stage_id="APPS_RG_U0",
        receipt_ref=consumer_validation,
    )
    ledger.record_from_receipt(
        stage_id="APPS_RG_L1",
        receipt_ref=root / sr.FILENAME_L1_PLAN,
    )
    ledger.record_from_receipt(
        stage_id="APPS_RG_L0",
        receipt_ref=root / sr.FILENAME_ROUTE_CONTRACT,
    )
    return ledger


def _emit_product_authority_activation_failure(
    *,
    artifact_dir: Path,
    identity: dict[str, Any],
    exc: BaseException,
) -> Path:
    """Persist the exact product-ledger activation failure and its checkpoint."""

    from apps_rg.runtime.failure_evidence import (
        atomic_write_json,
        capture_failure_otel_evidence,
        exception_failure_envelope,
    )

    root = Path(artifact_dir).resolve()
    ledger_path = root / "e2e_stage_ledger.json"
    entries: list[dict[str, Any]] = []
    ledger_read_error = ""
    if ledger_path.is_file():
        try:
            ledger_payload = json.loads(ledger_path.read_text(encoding="utf-8"))
            entries_raw = (
                ledger_payload.get("entries")
                if isinstance(ledger_payload, dict)
                else []
            )
            entries = [dict(item) for item in entries_raw or () if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError) as ledger_exc:
            ledger_read_error = f"{type(ledger_exc).__name__}:{ledger_exc}"
    last_entry = entries[-1] if entries else {}
    failure = exception_failure_envelope(
        exc,
        stage="PRODUCT_E2E_AUTHORITY_ACTIVATION",
        operation="activate_product_stage_ledger",
        source_component="apps_rg.runtime.orchestration.r3r4_whole_run_orchestration",
        artifact_dir=root,
        integrated_artifact_dir=root,
        identity=identity,
        run_id=str(identity.get("parent_run_id") or root.name),
        dispatch_invoked=True,
    )
    otel = capture_failure_otel_evidence(
        artifact_dir=root,
        trace_root=str(identity.get("trace_root") or ""),
        stage="PRODUCT_E2E_AUTHORITY_ACTIVATION",
        operation="activate_product_stage_ledger",
        filename="product_e2e_authority_activation_otel_trace_snapshot.json",
    )
    receipt_path = root / "product_e2e_authority_activation_failure.json"
    atomic_write_json(
        receipt_path,
        {
            "schema_version": "apps_rg.product_e2e_authority_activation_failure.v1",
            "status": "FAILED",
            "product_authorized": False,
            "pipeline_complete": False,
            "failure": failure,
            "ledger_checkpoint": {
                "ledger_ref": ledger_path.name,
                "ledger_present": ledger_path.is_file(),
                "ledger_read_error": ledger_read_error,
                "entry_count": len(entries),
                "last_stage_id": str(last_entry.get("stage_id") or ""),
                "last_stage_status": str(last_entry.get("status") or ""),
                "next_stage_id": str(last_entry.get("next_stage_id") or ""),
                "preidentity_ledger_present": (
                    root / "e2e_stage_ledger_preidentity_non_product.json"
                ).is_file(),
            },
            "otel_snapshot_ref": "product_e2e_authority_activation_otel_trace_snapshot.json",
            "otel_capture_status": str(otel.get("status") or ""),
        },
    )
    return receipt_path


def _seal_product_terminal_authority(
    *,
    artifact_dir: Path,
    product_ledger: Any,
    identity: dict[str, Any],
    product_authorization_ref: str,
) -> dict[str, str]:
    """Close mandatory output, ledger, manifest, and completion in that order."""

    from apps_rg.runtime.product_stage_authority import (
        emit_mandatory_outputs_authority_receipt,
    )
    from apps_rg.runtime.terminal_manifest import (
        seal_terminal_manifest,
        verify_terminal_manifest,
    )
    from apps_rg.runtime.terminal_state import TerminalStateMachine

    root = Path(artifact_dir).resolve()
    mandatory_authority = emit_mandatory_outputs_authority_receipt(
        artifact_dir=root,
        identity=identity,
    )
    mandatory_entry = product_ledger.record_from_receipt(
        stage_id="MANDATORY_OUTPUTS",
        receipt_ref=mandatory_authority,
        artifact_refs=_authority_source_refs(mandatory_authority),
    )
    if mandatory_entry["status"] != "PASS":
        raise ProductE2EAuthorityError("mandatory output authority receipt blocked")

    authorization_path = root / product_authorization_ref
    try:
        authorization = json.loads(authorization_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductE2EAuthorityError(
            f"product authorization receipt is unreadable: {type(exc).__name__}"
        ) from exc
    if not isinstance(authorization, dict):
        raise ProductE2EAuthorityError("product authorization receipt is not an object")
    decision = authorization.get("decision_receipt")
    output = authorization.get("output_artifact")
    if not isinstance(decision, dict) or not isinstance(output, dict):
        raise ProductE2EAuthorityError(
            "product authorization receipt lacks exact decision/output bindings"
        )
    terminal_state = TerminalStateMachine()
    terminal_state.close_product_authorization(
        authorized=True,
        decision_receipt_ref=str(decision.get("artifact_ref") or ""),
        decision_receipt_sha256=str(decision.get("sha256") or ""),
        output_artifact_sha256=str(output.get("sha256") or ""),
        closed_at_utc=str(authorization.get("closed_at_utc") or ""),
    )
    terminal_state.record_pipeline_completion(
        complete=True,
        decisive_stage_id="PIPELINE_COMPLETION_CLOSE",
    )
    product_ledger.seal(terminal_state=terminal_state.snapshot())

    promotion_ref = (
        root
        / "e2e_authority_receipts"
        / "promotion_terminal_authority_receipt.json"
    )
    try:
        promotion = json.loads(promotion_ref.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductE2EAuthorityError(
            f"promotion terminal receipt is unreadable: {type(exc).__name__}"
        ) from exc
    promotion_status = str(
        (promotion if isinstance(promotion, dict) else {}).get(
            "promotion_terminal_status"
        )
        or ""
    )
    mandatory_marker_path = root / "apps_rg_mandatory_output_commit_manifest.json"
    try:
        mandatory_marker = json.loads(mandatory_marker_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductE2EAuthorityError(
            f"mandatory output commit marker is unreadable: {type(exc).__name__}"
        ) from exc
    declared_outputs = (
        mandatory_marker.get("required_artifacts")
        if isinstance(mandatory_marker, dict)
        else None
    )
    if not isinstance(declared_outputs, list) or not declared_outputs:
        raise ProductE2EAuthorityError(
            "mandatory output commit marker has no required artifact set"
        )
    mandatory_refs: dict[str, str | Path] = {
        **{
            f"mandatory:{relative}": str(relative)
            for relative in declared_outputs
        },
        "mandatory_commit_marker": mandatory_marker_path,
        "product_authorization": product_authorization_ref,
        "authorized_output": str(output.get("artifact_ref") or ""),
    }
    manifest_path, completion_path = seal_terminal_manifest(
        artifact_dir=root,
        identity=identity,
        x3_code=_PRODUCT_SUCCESS_X3,
        x3_receipt_ref="apps_rg_whole_run_exit_review_packet.json",
        terminal_state=terminal_state,
        promotion_status=promotion_status,
        promotion_receipt_ref=promotion_ref,
        mandatory_output_refs=mandatory_refs,
    )
    verification = verify_terminal_manifest(manifest_path)
    if not verification.valid:
        raise ProductE2EAuthorityError(
            "terminal manifest verification failed: "
            + ";".join(verification.errors)
        )
    completion = verification.pipeline_completion_receipt
    if completion.get("pipeline_complete") is not True:
        raise ProductE2EAuthorityError(
            "pipeline completion receipt did not close the product pipeline"
        )
    from apps_model_telemetry.otel_runtime import capture_collector_snapshot

    terminal_otel = capture_collector_snapshot(
        artifact_dir=root,
        trace_id=str(identity.get("trace_root") or ""),
        filename="terminal_closeout_otel_trace_snapshot.json",
        boundary="terminal_closeout",
    )
    return {
        "terminal_manifest_ref": str(manifest_path),
        "pipeline_completion_receipt_ref": str(completion_path),
        "stage_ledger_seal_ref": str(
            root / "e2e_stage_ledger_seal_receipt.json"
        ),
        "terminal_closeout_otel_snapshot_ref": str(
            root / "terminal_closeout_otel_trace_snapshot.json"
        ),
        "terminal_closeout_otel_status": str(terminal_otel.get("status") or ""),
    }


def _seal_pending_non_product_stage_ledger(
    *,
    artifact_dir: Path,
    product_ledger: Any,
    identity: dict[str, Any],
) -> dict[str, str]:
    """Finish a receipt-derived ledger after its first governed failure."""

    from apps_rg.runtime.e2e_stage_ledger import verify_e2e_stage_ledger
    from apps_rg.runtime.product_stage_authority import (
        emit_product_eligibility_authority_receipt,
        emit_runtime_stage_authority_receipts,
        emit_terminal_non_product_authority_receipt,
    )

    root = Path(artifact_dir).resolve()
    ledger_payload = json.loads(product_ledger.path.read_text(encoding="utf-8"))
    entries = list(ledger_payload.get("entries") or ())
    if not entries:
        raise ProductE2EAuthorityError("cannot terminalize an empty product ledger")

    expected_stage = str(entries[-1].get("next_stage_id") or "")
    runtime_order = (
        "APPS_RG_C0",
        "APPS_RG_PA",
        "APPS_RG_L2",
        "X1_REVIEW",
        "X2_AGGREGATION",
        "X3_DISPOSITION",
    )
    if expected_stage in runtime_order:
        runtime_authority = emit_runtime_stage_authority_receipts(
            artifact_dir=root,
            identity=identity,
        )
        start = runtime_order.index(expected_stage)
        for stage_id in runtime_order[start:]:
            receipt_ref = runtime_authority[stage_id]
            entry = product_ledger.record_from_receipt(
                stage_id=stage_id,
                receipt_ref=receipt_ref,
                artifact_refs=_authority_source_refs(receipt_ref),
                next_stage_id=(
                    "PRODUCT_ELIGIBILITY"
                    if stage_id == "X3_DISPOSITION"
                    else None
                ),
            )
            if entry["status"] in {"FAIL", "BLOCKED"}:
                break
        ledger_payload = json.loads(product_ledger.path.read_text(encoding="utf-8"))
        entries = list(ledger_payload.get("entries") or ())
        expected_stage = str(entries[-1].get("next_stage_id") or "")
    elif expected_stage == "PRODUCT_ELIGIBILITY":
        receipt_ref = emit_product_eligibility_authority_receipt(
            artifact_dir=root,
            identity=identity,
        )
        product_ledger.record_from_receipt(
            stage_id="PRODUCT_ELIGIBILITY",
            receipt_ref=receipt_ref,
            artifact_refs=_authority_source_refs(receipt_ref),
        )
        ledger_payload = json.loads(product_ledger.path.read_text(encoding="utf-8"))
        entries = list(ledger_payload.get("entries") or ())
        expected_stage = str(entries[-1].get("next_stage_id") or "")

    if expected_stage != "TERMINAL_NON_PRODUCT":
        raise ProductE2EAuthorityError(
            f"product ledger has no decisive failed stage to terminalize: {expected_stage!r}"
        )
    decisive = entries[-1]
    decisive_stage_id = str(decisive.get("stage_id") or "")
    decisive_receipt_ref = str(decisive.get("authoritative_receipt_ref") or "")
    stage_graph = ledger_payload.get("stage_graph")
    stage_ids = (
        list(stage_graph.get("stage_ids") or [])
        if isinstance(stage_graph, dict)
        else []
    )
    try:
        decisive_index = stage_ids.index(decisive_stage_id)
    except ValueError as exc:
        raise ProductE2EAuthorityError(
            f"decisive stage absent from frozen stage graph: {decisive_stage_id}"
        ) from exc
    blocked_successors = [
        str(stage_id)
        for stage_id in stage_ids[decisive_index + 1 :]
        if str(stage_id) != "TERMINAL_NON_PRODUCT"
    ]
    if not blocked_successors:
        raise ProductE2EAuthorityError(
            f"decisive stage has no blocked successors: {decisive_stage_id}"
        )
    terminal_receipt = emit_terminal_non_product_authority_receipt(
        artifact_dir=root,
        identity=identity,
        decisive_stage_id=decisive_stage_id,
        decisive_receipt_ref=decisive_receipt_ref,
        blocked_successor_stage_ids=blocked_successors,
    )
    terminal_entry = product_ledger.record_from_receipt(
        stage_id="TERMINAL_NON_PRODUCT",
        receipt_ref=terminal_receipt,
        artifact_refs=_authority_source_refs(terminal_receipt),
    )
    if terminal_entry["status"] != "PASS":
        raise ProductE2EAuthorityError("non-product terminal authority receipt blocked")
    seal_path = product_ledger.seal(
        terminal_state={
            "product_authorized": False,
            "pipeline_complete": False,
            "observability_repair_required": False,
        }
    )
    report = verify_e2e_stage_ledger(product_ledger.path)
    if not report.valid or not report.complete or not report.sealed:
        raise ProductE2EAuthorityError(
            "non-product stage ledger verification failed: " + ";".join(report.errors)
        )
    from apps_model_telemetry.otel_runtime import capture_collector_snapshot

    terminal_otel = capture_collector_snapshot(
        artifact_dir=root,
        trace_id=str(identity.get("trace_root") or ""),
        filename="terminal_closeout_otel_trace_snapshot.json",
        boundary="terminal_closeout",
    )
    return {
        "terminal_non_product_receipt_ref": str(terminal_receipt),
        "stage_ledger_seal_ref": str(seal_path),
        "terminal_closeout_otel_snapshot_ref": str(
            root / "terminal_closeout_otel_trace_snapshot.json"
        ),
        "terminal_closeout_otel_status": str(terminal_otel.get("status") or ""),
    }


def _record_closeout_stage_unless_sealed(
    *,
    stage_ledger: Any,
    payload: dict[str, Any],
) -> bool:
    """Record legacy CLOSEOUT only while the selected ledger remains mutable.

    Receipt-derived product ledgers close on either TERMINAL_NON_PRODUCT or the
    product terminal seal.  Both paths deliberately make the ledger immutable
    before the compatibility CLOSEOUT code below runs.  Presence of the seal is
    therefore an instruction to verify the ledger, never to append another
    compatibility entry to it.
    """

    from apps_rg.runtime.e2e_stage_ledger import E2E_STAGE_LEDGER_SEAL_FILENAME

    if (Path(stage_ledger.path).parent / E2E_STAGE_LEDGER_SEAL_FILENAME).exists():
        return False
    record = getattr(stage_ledger, "record", None)
    if not callable(record):
        # Product-v2 ledgers are receipt-derived by construction and never
        # accept caller-asserted compatibility rows.  Their incomplete state
        # plus the mandatory failure output is the truthful checkpoint when a
        # terminal authority step fails before the product seal can be issued.
        return False
    record(
        stage_id="CLOSEOUT",
        status="PASS" if payload.get("pipeline_complete") is True else "FAIL",
        reason_code=(
            "MANDATORY_CLOSEOUT_COMPLETE"
            if payload.get("pipeline_complete") is True
            else str(payload.get("fault") or "RUN_NOT_AUTHORIZED")
        ),
        output_refs={
            "mandatory_run_output_json": str(
                payload.get("mandatory_run_output_json") or ""
            ),
            "bcg_executive_output_md": str(
                payload.get("bcg_executive_output_md") or ""
            ),
        },
    )
    return True


def run_whole_run_with_route_governance(
    *,
    target_company: str,
    target_role: str,
    target_level: str = "",
    jd: str = "",
    job_description_ref: str = "",
    job_description_text: str = "",
    manual_brief: str = "",
    resume_path: str = "",
    source_resume_text: str = "",
    generation_mode: str = "strategic_tailor",
    l1_cognitive_treatment_arm: str = "l1_v2_control",
    artifact_dir: str = "",
    auto_research_internal: bool = True,
    research_via: str | None = None,
    preflight_continuation_ref: str = "",
    require_fresh_preflight: bool = True,
    validated_input_bundle_ref: str = "",
    validated_input_bundle_digest: str = "",
) -> dict[str, Any]:
    """Canonical whole-run path: L0 route + optional R3R4 research + R4 draft leg."""
    art = _default_artifact_dir(artifact_dir)
    repo = find_repo_root()

    from apps_rg.runtime.embedding_settings import (
        apply_apps_rg_embedding_env_guards,
        bootstrap_apps_rg_embedding_env,
        write_embedding_settings_receipt,
    )
    from apps_rg.runtime.runtime_boundary import (
        assert_apps_rg_runtime_boundary,
        configure_apps_rg_runtime_boundary,
        write_apps_rg_runtime_boundary_receipt,
    )

    boundary = configure_apps_rg_runtime_boundary(repo_root=repo)
    write_apps_rg_runtime_boundary_receipt(art, boundary)
    bootstrap_apps_rg_embedding_env(repo_root=repo)
    assert_apps_rg_runtime_boundary(repo_root=repo)
    emb = apply_apps_rg_embedding_env_guards(chroma_persist_dir=os.environ.get("CHROMA_PERSIST_DIR"))
    write_embedding_settings_receipt(art, emb)

    envelope = _build_cli_ingress_envelope(
        target_company=target_company,
        target_role=target_role,
        target_level=target_level,
        jd=jd,
        job_description_ref=job_description_ref,
        job_description_text=job_description_text,
        manual_brief=manual_brief,
        resume_path=resume_path,
        source_resume_text=source_resume_text,
        generation_mode=generation_mode,
        l1_cognitive_treatment_arm=l1_cognitive_treatment_arm,
        auto_research_internal=auto_research_internal,
        research_via=research_via,
        validated_input_bundle_ref=validated_input_bundle_ref,
        validated_input_bundle_digest=validated_input_bundle_digest,
    )
    from apps_rg.runtime.e2e_preflight import (
        E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME,
        validate_preflight_continuation,
    )
    from apps_rg.runtime.e2e_stage_ledger import E2E_STAGE_LEDGER_FILENAME, E2EStageLedger

    continuation_path = (
        Path(preflight_continuation_ref).resolve()
        if str(preflight_continuation_ref or "").strip()
        else art / E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME
    )
    preflight_errors: tuple[str, ...] = ()
    preflight_validation = None
    if require_fresh_preflight:
        preflight_validation = validate_preflight_continuation(
            receipt_path=continuation_path,
            secret=str(os.environ.get("APPS_RG_ROUTE_HMAC_SECRET") or ""),
            expected_e2e_run_id=art.name,
            expected_key_id=str(os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID") or ""),
            consumer_id="apps_rg.whole_run.primary",
            consume=True,
            # The canonical producer identity is emitted only after delegated
            # research closes.  This seam validates signature/freshness/replay
            # now and refuses to invent the not-yet-known child identity.
            require_product_identity=False,
        )
        preflight_errors = preflight_validation.errors
    if require_fresh_preflight and (
        preflight_validation is None or not preflight_validation.valid
    ):
        stage_ledger = E2EStageLedger.create(
            artifact_dir=art,
            e2e_run_id=str(envelope.run_id),
        )
        rejection_path = art / "e2e_preflight_entry_rejection_receipt.json"
        sr.write_stage_receipt(
            rejection_path,
            {
                "schema_version": "apps_rg.e2e_preflight_entry_rejection.v1",
                "status": "BLOCKED",
                "failure_code": "FRESH_PREFLIGHT_CONTINUATION_INVALID",
                "failure_reasons": list(preflight_errors or ("continuation_missing",)),
            },
        )
        stage_ledger.record_from_receipt(
            stage_id="PREFLIGHT",
            receipt_ref=rejection_path,
            reason_code="FRESH_PREFLIGHT_CONTINUATION_INVALID",
        )
        rejection_route = _pre_u0_research_route(envelope)
        failed = _failure_payload(
            artifact_dir=art,
            route=rejection_route,
            reason="FRESH_PREFLIGHT_CONTINUATION_INVALID",
            route_decision={
                "preflight_continuation_ref": str(continuation_path),
                "preflight_continuation_errors": list(preflight_errors),
            },
        )
        failed.update(
            {
                "completion_status": "BLOCKED",
                "product_authorized": False,
                "pipeline_complete": False,
                "observability_repair_required": False,
            }
        )
        _emit_terminal_mandatory_closeout(
            artifact_dir=art,
            repo_root=repo,
            payload=failed,
        )
        stage_ledger.record(
            stage_id="CLOSEOUT",
            status="PASS",
            reason_code="FAILED_RUN_REPORTED",
            output_refs={
                "mandatory_run_output_json": str(
                    failed.get("mandatory_run_output_json") or ""
                )
            },
        )
        failed["e2e_stage_ledger"] = str(stage_ledger.path)
        return failed

    product_stage_ledger: Any | None = None
    if (art / E2E_STAGE_LEDGER_FILENAME).is_file():
        stage_ledger = E2EStageLedger.open(artifact_dir=art)
    else:
        stage_ledger = E2EStageLedger.create(
            artifact_dir=art,
            e2e_run_id=str(envelope.run_id),
        )
        if require_fresh_preflight:
            stage_ledger.record_from_receipt(
                stage_id="PREFLIGHT",
                receipt_ref=continuation_path,
                reason_code="SIGNED_FRESH_PREFLIGHT_CONTINUATION_ACCEPTED",
            )
        else:
            compatibility_path = art / "e2e_preflight_non_product_compatibility_receipt.json"
            sr.write_stage_receipt(
                compatibility_path,
                {
                    "schema_version": "apps_rg.e2e_preflight_non_product_compatibility.v1",
                    "status": "PASS",
                    "classification": "NON_PRODUCT_ONLY",
                    "reason": "EXPLICIT_TEST_OR_LEGACY_CALLER_COMPATIBILITY",
                },
            )
            stage_ledger.record_from_receipt(
                stage_id="PREFLIGHT",
                receipt_ref=compatibility_path,
                reason_code="NON_PRODUCT_COMPATIBILITY_ONLY",
            )
    handoff_jd_ref = (
        str(job_description_ref or "").strip()
        or str(jd or "").strip()
        or str(job_description_text or "").strip()
    )
    initial_handoff_validation = _validate_handoff_for_ingress_envelope(
        brief_ref=manual_brief,
        jd_ref=handoff_jd_ref,
        envelope=envelope,
        require_observed=research_delegation_enabled(
            auto_research_internal=auto_research_internal,
            research_via=research_via,
        )
        and briefing_input_present(manual_brief),
    )
    manual_brief_eff = manual_brief
    research_ran = False
    research_note = ""
    delegated_briefing_ref: str | None = None
    research_enabled = research_delegation_enabled(
        auto_research_internal=auto_research_internal,
        research_via=research_via,
    )
    should_delegate_pre_u0 = research_enabled and not (
        initial_handoff_validation.observed and initial_handoff_validation.valid
    )
    if should_delegate_pre_u0:
        delegation_route = _pre_u0_research_route(envelope)
        ok, research_note, brief_path = _run_r3r4_research_hop(
            route=delegation_route,
            validated_request=envelope,
            artifact_dir=art,
            target_company=target_company,
            target_role=target_role,
            job_description_ref=str(job_description_ref or jd or "").strip(),
            job_description_text=job_description_text,
        )
        research_ran = True
        if not ok:
            stage_ledger.record(
                stage_id="RESEARCH",
                status="FAIL",
                reason_code=research_note,
                output_refs={
                    "research_bridge_response": sr.FILENAME_RESEARCH_BRIDGE_RESPONSE,
                },
            )
            route_decision = {
                "route_profile_ref": delegation_route.route_profile_ref,
                "route_family": delegation_route.route_family,
                "route_id": delegation_route.route_id,
                "execution_form": delegation_route.execution_form,
                "research_delegation_enabled": True,
                "research_delegation_executed": True,
                "research_outcome": research_note,
                "research_failure": research_note,
                "research_failure_reason": "apps_research_hop_failed_without_authorized_handoff",
            }
            failed = _failure_payload(
                artifact_dir=art,
                route=delegation_route,
                reason=research_note,
                route_decision=route_decision,
            )
            failed["completion_status"] = "BLOCKED"
            _emit_terminal_mandatory_closeout(
                artifact_dir=art,
                repo_root=repo,
                payload=failed,
            )
            stage_ledger.record(
                stage_id="CLOSEOUT",
                status="PASS",
                reason_code="FAILED_RUN_REPORTED",
                output_refs={"spine_run_manifest": sr.FILENAME_SPINE_MANIFEST},
            )
            failed["e2e_stage_ledger"] = str(stage_ledger.path)
            return failed
        manual_brief_eff = brief_path
        delegated_briefing_ref = sr.FILENAME_DELEGATED_BRIEFING
        stage_ledger.record(
            stage_id="RESEARCH",
            status="PASS",
            reason_code=research_note,
            output_refs={
                "research_bridge_response": sr.FILENAME_RESEARCH_BRIDGE_RESPONSE,
                "delegated_briefing": sr.FILENAME_DELEGATED_BRIEFING,
            },
        )
    else:
        research_note = (
            "AUTHORIZED_HANDOFF_REUSED"
            if initial_handoff_validation.observed and initial_handoff_validation.valid
            else "RESEARCH_DISABLED"
        )
        stage_ledger.record(
            stage_id="RESEARCH",
            status="SKIPPED",
            reason_code=research_note,
            input_refs={"manual_brief": str(manual_brief or "")},
        )

    envelope.app_payload["manual_brief_path"] = manual_brief_eff
    envelope.app_payload["briefing_artifact_ref"] = manual_brief_eff
    from apps_rg.runtime.bindings.u0_rejection import AppsRgU0RejectedError

    try:
        validated_request = u0_validate_apps_rg(
            envelope,
            allow_missing_profiles=False,
        )
    except AppsRgU0RejectedError as exc:
        reason = f"U0_REJECTED:{exc.notice.rejection_reason.value}"
        stage_ledger.record(
            stage_id="U0",
            status="FAIL",
            reason_code=reason,
            output_refs={
                "rejection_detail": dict(exc.notice.machine_readable_detail or {})
            },
        )
        rejection_route = _pre_u0_research_route(envelope)
        route_decision = {
            "route_profile_ref": rejection_route.route_profile_ref,
            "route_family": rejection_route.route_family,
            "route_id": rejection_route.route_id,
            "execution_form": rejection_route.execution_form,
            "research_delegation_enabled": research_enabled,
            "research_delegation_executed": research_ran,
            "research_outcome": research_note,
            "u0_rejection_reason": exc.notice.rejection_reason.value,
        }
        failed = _failure_payload(
            artifact_dir=art,
            route=rejection_route,
            reason=reason,
            route_decision=route_decision,
        )
        failed["completion_status"] = "BLOCKED"
        _emit_terminal_mandatory_closeout(
            artifact_dir=art,
            repo_root=repo,
            payload=failed,
        )
        stage_ledger.record(
            stage_id="CLOSEOUT",
            status="FAIL",
            reason_code=str(failed.get("completion_fault") or reason),
            output_refs={
                "mandatory_run_output_json": str(
                    failed.get("mandatory_run_output_json") or ""
                )
            },
        )
        failed["e2e_stage_ledger"] = str(stage_ledger.path)
        return failed
    from apps_rg.runtime.spine.validated_request_contract import (
        CANONICAL_APPS_RG_VALIDATED_REQUEST_FILENAME,
        write_validated_request_contract,
    )

    write_validated_request_contract(
        art / CANONICAL_APPS_RG_VALIDATED_REQUEST_FILENAME,
        validated_request,
        consumer_stage="section_lane_modular",
    )
    stage_ledger.record(
        stage_id="U0",
        status="PASS",
        output_refs={
            "u0_receipt": sr.FILENAME_U0_RECEIPT,
            "validated_request": CANONICAL_APPS_RG_VALIDATED_REQUEST_FILENAME,
        },
    )
    l1_plan = l1_plan_apps_rg(validated_request)
    l1_task_spec = getattr(l1_plan, "task_spec", None) or {}
    l1_capsule = (
        l1_task_spec.get("apps_rg_planning_capsule")
        if isinstance(l1_task_spec, dict)
        else None
    )
    if not isinstance(l1_capsule, dict):
        raise ProductE2EAuthorityError("L1 planning capsule is required for W1 reconciliation")
    l1_capsule_path = art / sr.FILENAME_L1_PLANNING_CAPSULE
    sr.write_stage_receipt(l1_capsule_path, l1_capsule)
    l1_v2_capsule = (
        l1_task_spec.get("apps_rg_planning_v2_capsule")
        if isinstance(l1_task_spec, dict)
        else None
    )
    if not isinstance(l1_v2_capsule, dict):
        raise ProductE2EAuthorityError("L1 v2 planning capsule is required for W4 pairing")
    sr.write_stage_receipt(
        art / sr.FILENAME_L1_PLANNING_V2_CAPSULE,
        l1_v2_capsule,
    )
    l1_treatment = (
        l1_task_spec.get("l1_cognitive_treatment")
        if isinstance(l1_task_spec, dict)
        else None
    )
    if not isinstance(l1_treatment, dict):
        raise ProductE2EAuthorityError("L1 cognitive treatment is required for W4 pairing")
    sr.write_stage_receipt(
        art / sr.FILENAME_L1_COGNITIVE_TREATMENT,
        l1_treatment,
    )
    l1_cognitive_plan = (
        l1_task_spec.get("apps_rg_cognitive_v3_plan")
        if isinstance(l1_task_spec, dict)
        else None
    )
    if l1_cognitive_plan is not None:
        if not isinstance(l1_cognitive_plan, dict):
            raise ProductE2EAuthorityError("L1 cognitive plan is malformed")
        sr.write_stage_receipt(
            art / sr.FILENAME_L1_COGNITIVE_PLAN,
            l1_cognitive_plan,
        )

    def emit_plan_execution_artifacts(
        *,
        execution_witness: dict[str, Any] | None = None,
        l2_result: Any = None,
        terminal_reason: str = "",
    ) -> dict[str, str]:
        """Emit the W1 observation and its W2 advisory decision for this run path."""

        execution_receipt = emit_plan_execution_reconciliation(
            request_id=validated_request.request_id,
            run_id=validated_request.run_id,
            plan_capsule=l1_capsule,
            artifact_dir=art,
            execution_witness=execution_witness,
            l2_result=l2_result,
            terminal_reason=terminal_reason,
        )
        replan_decision = emit_failure_aware_replan(
            parent_plan_capsule_path=l1_capsule_path,
            plan_execution_receipt_path=execution_receipt,
            artifact_dir=art,
        )
        return {
            "plan_execution_receipt": str(execution_receipt),
            "plan_replan_decision": str(replan_decision),
        }

    stage_ledger.record(
        stage_id="L1",
        status="PASS",
        output_refs={
            "l1_plan": sr.FILENAME_L1_PLAN,
            "l1_planning_capsule": sr.FILENAME_L1_PLANNING_CAPSULE,
        },
    )
    try:
        route = l0_route_apps_rg(l1_plan)
    except L1PlanNotReadyError:
        # L0's fail-closed readiness boundary has no RouteContract to attach
        # to a normal terminal payload.  Preserve its existing exception
        # semantics, but never omit the planned-unit reconciliation it caused.
        emit_plan_execution_artifacts(terminal_reason="L1_PLAN_BLOCKED")
        raise
    stage_ledger.record(
        stage_id="L0",
        status="PASS",
        output_refs={"route_contract": sr.FILENAME_ROUTE_CONTRACT},
    )

    briefing_mode = classify_briefing_mode(
        validated_request.app_payload or {},
        chroma_path_resolved=None,
        research_via="apps_research" if research_ran else research_via,
    )
    handoff_validation = _validate_handoff_for_ingress_envelope(
        brief_ref=manual_brief_eff,
        jd_ref=handoff_jd_ref,
        envelope=envelope,
        require_observed=research_enabled and briefing_input_present(manual_brief_eff),
    )
    handoff_receipt = handoff_validation.to_receipt()
    handoff_identity = handoff_receipt.get("identity")
    route_decision = {
        "route_profile_ref": route.route_profile_ref,
        "route_family": route.route_family,
        "route_id": route.route_id,
        "execution_form": route.execution_form,
        "briefing_mode": briefing_mode.retrieval_mode,
        "briefing_classified_from": briefing_mode.classified_from,
        "research_delegation_enabled": research_enabled,
        "briefing_input_present": briefing_input_present(manual_brief_eff),
        "incoming_apps_research_handoff_authorized": (
            handoff_validation.observed and handoff_validation.valid
        ),
        "incoming_apps_research_handoff_reason": handoff_validation.reason,
        "incoming_apps_research_handoff_observed": handoff_validation.observed,
        "research_delegation_executed": research_ran,
        "research_outcome": research_note,
    }
    if research_ran:
        route_decision["delegated_briefing_path"] = manual_brief_eff
    if research_ran and route.route_family != ROUTE_FAMILY_R3R4:
        reason = "APPS_RESEARCH_ROUTE_MISMATCH"
        route_decision["research_failure"] = reason
        route_decision["research_failure_reason"] = (
            f"apps_research_completed_before_non_managed_route_{route.route_family}"
        )
        failed = _failure_payload(
            artifact_dir=art,
            route=route,
            reason=reason,
            route_decision=route_decision,
        )
        failed["completion_status"] = "BLOCKED"
        failed.update(emit_plan_execution_artifacts(terminal_reason=reason))
        _emit_terminal_mandatory_closeout(
            artifact_dir=art,
            repo_root=repo,
            payload=failed,
        )
        stage_ledger.record(
            stage_id="CLOSEOUT",
            status="PASS",
            reason_code="FAILED_RUN_REPORTED",
            output_refs={"spine_run_manifest": sr.FILENAME_SPINE_MANIFEST},
        )
        failed["e2e_stage_ledger"] = str(stage_ledger.path)
        return failed

    sr.write_stage_receipt(
        art / sr.FILENAME_INGRESS_RAW,
        {
            "target_company": target_company,
            "target_role": target_role,
            "generation_mode": generation_mode,
            "manual_brief": manual_brief_eff,
            "auto_research_internal": auto_research_internal,
            "research_via": research_via,
        },
    )
    sr.write_stage_receipt(
        art / sr.FILENAME_U0_RECEIPT,
        {
            "schema_version": "apps_rg.u0_receipt.v1",
            "status": "PASS",
            "request_id": validated_request.request_id,
            "run_id": validated_request.run_id,
            "trace_id": validated_request.trace_id,
            "trace_root": validated_request.trace_root,
            "tenant_id": validated_request.tenant_id,
            "payload_digest": validated_request.payload_digest,
            "authority_contract_id": (
                validated_request.authority_validation_receipt.authority_contract_id
            ),
            "authority_receipt_digest": (
                validated_request.authority_validation_receipt.authority_receipt_digest
            ),
            "identity": dict(handoff_identity) if isinstance(handoff_identity, dict) else {},
        },
    )
    sr.write_stage_receipt(
        art / sr.FILENAME_L1_PLAN,
        {
            "schema_version": "apps_rg.l1_plan_contract.v1",
            "status": "PASS",
            "request_id": l1_plan.request_id,
            "merge_required_hint": l1_plan.merge_required_hint,
            "grounding_required": l1_plan.grounding_required,
            "work_shape": l1_plan.work_shape,
            "identity": dict(handoff_identity) if isinstance(handoff_identity, dict) else {},
        },
    )
    route_contract_receipt = _route_contract_payload(route)
    route_contract_receipt.update(
        {
            "schema_version": "apps_rg.route_contract.v1",
            "status": "PASS",
            "identity": (
                dict(handoff_identity) if isinstance(handoff_identity, dict) else {}
            ),
        }
    )
    sr.write_stage_receipt(art / sr.FILENAME_ROUTE_CONTRACT, route_contract_receipt)

    spine_pre_draft = {
        "schema_version": "apps_rg.spine_run_manifest.v1",
        "route_family": route.route_family,
        "route_id": route.route_id,
        "execution_form": route.execution_form,
        "proof_authority": "spine_run_manifest.json",
        "draft_leg_manifest": sr.FILENAME_DRAFT_LEG_MANIFEST,
        "draft_leg_proof_scope": "draft_leg_only",
        "research_delegation_executed": research_ran,
        "research_note": research_note,
        "route_decision": route_decision,
        "downstream_refs": {
            "l1_planning_capsule": sr.FILENAME_L1_PLANNING_CAPSULE,
            "route_contract": sr.FILENAME_ROUTE_CONTRACT,
            "plan_execution_receipt": sr.FILENAME_PLAN_EXECUTION_RECEIPT,
            "plan_replan_decision": sr.FILENAME_PLAN_REPLAN_DECISION,
            "research_bridge_request": sr.FILENAME_RESEARCH_BRIDGE_REQUEST,
            "research_bridge_response": sr.FILENAME_RESEARCH_BRIDGE_RESPONSE,
            "delegated_briefing": delegated_briefing_ref,
        },
    }
    sr.write_stage_receipt(art / sr.FILENAME_SPINE_MANIFEST, spine_pre_draft)

    from apps_rg.runtime.orchestration.canonical_dispatch import build_raw_request_for_r4

    raw_request = build_raw_request_for_r4(
        target_company=target_company,
        target_role=target_role,
        target_level=target_level,
        jd=jd,
        job_description_ref=job_description_ref,
        job_description_text=job_description_text,
        manual_brief=manual_brief_eff,
        resume_path=resume_path,
        source_resume_text=source_resume_text,
        generation_mode=generation_mode,
    )
    raw_request["research_via"] = "apps_research" if research_ran else research_via
    raw_request["route_decision_ref"] = sr.FILENAME_SPINE_MANIFEST
    if handoff_validation.valid and isinstance(handoff_identity, dict):
        # Preserve the producer/consumer validated identity verbatim.  Missing
        # identity is left missing and becomes a terminal reconciliation gap;
        # this layer must never synthesize producer authority.
        raw_request["canonical_run_identity"] = dict(handoff_identity)

    if require_fresh_preflight:
        if not handoff_validation.valid or not isinstance(handoff_identity, dict):
            failed = _failure_payload(
                artifact_dir=art,
                route=route,
                reason="PRODUCT_RUN_IDENTITY_UNAVAILABLE",
                route_decision=route_decision,
            )
            failed.update(
                {
                    "completion_status": "BLOCKED",
                    "product_authorized": False,
                    "pipeline_complete": False,
                    "observability_repair_required": False,
                }
            )
            failed.update(
                emit_plan_execution_artifacts(
                    terminal_reason="PRODUCT_RUN_IDENTITY_UNAVAILABLE"
                )
            )
            _emit_terminal_mandatory_closeout(
                artifact_dir=art,
                repo_root=repo,
                payload=failed,
            )
            failed["e2e_stage_ledger"] = str(stage_ledger.path)
            return failed
        try:
            product_stage_ledger = _activate_product_stage_ledger(
                artifact_dir=art,
                legacy_ledger=stage_ledger,
                identity=dict(handoff_identity),
                preflight_validation=preflight_validation,
                continuation_path=continuation_path,
                manual_brief=manual_brief_eff,
                research_ran=research_ran,
            )
        except Exception as exc:  # guardian: product activation is a fail-closed boundary
            activation_failure_ref = ""
            activation_failure_emit_error = ""
            try:
                activation_failure_ref = str(
                    _emit_product_authority_activation_failure(
                        artifact_dir=art,
                        identity=dict(handoff_identity),
                        exc=exc,
                    )
                )
            except Exception as evidence_exc:  # preserve the primary activation failure
                activation_failure_emit_error = (
                    f"{type(evidence_exc).__name__}:{evidence_exc}"
                )
            failed = _failure_payload(
                artifact_dir=art,
                route=route,
                reason="PRODUCT_E2E_AUTHORITY_ACTIVATION_FAILED",
                route_decision=route_decision,
            )
            failed.update(
                {
                    "completion_status": "BLOCKED",
                    "product_authorized": False,
                    "pipeline_complete": False,
                    "observability_repair_required": False,
                    "e2e_authority_error": f"{type(exc).__name__}:{exc}",
                    "product_e2e_authority_activation_failure_ref": (
                        activation_failure_ref
                    ),
                    "product_e2e_authority_activation_failure_emit_error": (
                        activation_failure_emit_error
                    ),
                }
            )
            failed.update(
                emit_plan_execution_artifacts(
                    terminal_reason="PRODUCT_E2E_AUTHORITY_ACTIVATION_FAILED"
                )
            )
            _emit_terminal_mandatory_closeout(
                artifact_dir=art,
                repo_root=repo,
                payload=failed,
            )
            failed["e2e_stage_ledger"] = str(
                (product_stage_ledger or stage_ledger).path
            )
            return failed

    from apps_rg.cache.cache_preflight_evidence import (
        build_cache_preflight_evidence,
        write_cache_hit_receipt,
        write_cache_miss_receipt,
        write_whole_run_cache_preflight_artifact,
    )
    from apps_rg.cache.whole_run_entrypoint_preflight import (
        ENTRYPOINT_CANONICAL_DISPATCH,
        maybe_ingest_r1b_post_exit,
        run_whole_run_cache_preflight,
    )

    preflight = run_whole_run_cache_preflight(
        entrypoint=ENTRYPOINT_CANONICAL_DISPATCH,
        raw_request=raw_request,
        target_company=target_company,
        target_role=target_role,
        artifact_dir=art,
        runs_dir=art.parent,
        policy_hash=os.environ.get("APPS_RG_POLICY_HASH"),
        blueprint_hash=os.environ.get("APPS_RG_BLUEPRINT_HASH"),
        section="",
    )
    evidence = build_cache_preflight_evidence(preflight, artifact_dir=art)
    write_whole_run_cache_preflight_artifact(art, preflight, evidence)

    if not preflight.generation_required:
        write_cache_hit_receipt(art, preflight, evidence)
        r1b_result = preflight.r1b_result
        cache_candidate_dir = str(preflight.r1a_artifact_dir or "").strip()
        if not cache_candidate_dir and r1b_result is not None:
            cache_candidate_dir = str(
                getattr(r1b_result, "artifact_dir", "")
                or getattr(r1b_result, "run_dir", "")
                or ""
            ).strip()
        from apps_rg.runtime.e2e_stage_ledger import validate_cached_e2e_completion

        cache_completion = validate_cached_e2e_completion(
            Path(cache_candidate_dir)
            if cache_candidate_dir
            else art / "__missing_cache_candidate__"
        )
        failed = _failure_payload(
            artifact_dir=art,
            route=route,
            reason="E2E_FRESH_RUN_REQUIRES_CACHE_MISS",
            route_decision=route_decision,
        )
        failed.update(
            {
                "completion_status": "BLOCKED",
                "cache_preflight": evidence,
                "cache_candidate_dir": cache_candidate_dir,
                "cache_candidate_completion_valid": cache_completion.valid,
                "cache_candidate_completion_errors": list(cache_completion.errors),
            }
        )
        failed.update(
            emit_plan_execution_artifacts(
                terminal_reason="E2E_FRESH_RUN_REQUIRES_CACHE_MISS"
            )
        )
        _emit_terminal_mandatory_closeout(
            artifact_dir=art,
            repo_root=repo,
            payload=failed,
        )
        stage_ledger.record(
            stage_id="CLOSEOUT",
            status="FAIL",
            reason_code="E2E_FRESH_RUN_REQUIRES_CACHE_MISS",
            output_refs={
                "mandatory_run_output_json": str(
                    failed.get("mandatory_run_output_json") or ""
                )
            },
        )
        failed["e2e_stage_ledger"] = str(stage_ledger.path)
        return failed

    write_cache_miss_receipt(art, preflight, evidence)

    result = run_integrated_single_action_spine(
        raw_request=raw_request,
        app_name="apps_rg",
        artifact_dir=art,
        route_family=DRAFT_LEG_ROUTE_FAMILY,
        cache_preflight_evidence=evidence,
        front_continuation={
            "validated_request": validated_request,
            "plan_contract": l1_plan,
            "route_contract": route,
            "execution_route_id": DRAFT_LEG_ROUTE_FAMILY,
        },
    )
    # This app-local receipt observes the actual section artifacts after the
    # runner returns.  A missing C0-to-PA chain remains BLOCKED evidence; it is
    # never inferred from the L1 plan or used to alter the runner's outcome.
    from apps_rg.runtime.contracts.l1_cognitive_treatment_execution import (
        emit_l1_cognitive_treatment_execution_receipt,
    )

    emit_l1_cognitive_treatment_execution_receipt(
        run_root=art,
        l1_plan=l1_plan,
    )
    execution_witness = dict(getattr(result, "execution_witness", {}) or {})
    plan_execution_artifacts = emit_plan_execution_artifacts(
        execution_witness=execution_witness,
        l2_result=getattr(result, "l2_result", None),
        terminal_reason=str(getattr(result, "fault", "") or ""),
    )
    plan_execution_receipt = plan_execution_artifacts["plan_execution_receipt"]
    plan_replan_decision = plan_execution_artifacts["plan_replan_decision"]
    stage_ledger.record(
        stage_id="C0",
        status="PASS",
        reason_code=str(
            (execution_witness.get("c0") or {}).get("status")
            if isinstance(execution_witness.get("c0"), dict)
            else "CORE_C0_RECEIPT_EMITTED"
        ),
        output_refs={"runtime_execution_witness": "runtime_execution_witness.json"},
    )
    if result.fault:
        stage_ledger.record(
            stage_id="L2",
            status="FAIL",
            reason_code=str(result.fault),
            output_refs={"terminal_ret_packet": "terminal_ret_packet.json"},
        )
    else:
        stage_ledger.record(
            stage_id="L2",
            status="PASS",
            output_refs={"terminal_ret_packet": "terminal_ret_packet.json"},
        )
        stage_ledger.record(
            stage_id="X1",
            status="PASS",
            output_refs={"exit_review_packet": "exit_review_packet.json"},
        )
        stage_ledger.record(
            stage_id="X2",
            status="PASS",
            reason_code=str(
                (execution_witness.get("x2") or {}).get("disposition")
                if isinstance(execution_witness.get("x2"), dict)
                else "EXIT_X2_AGGREGATED"
            ),
            output_refs={"runtime_execution_witness": "runtime_execution_witness.json"},
        )
        stage_ledger.record(
            stage_id="X3",
            status="PASS",
            reason_code=str(result.x3_disposition),
            output_refs={"x3_disposition_receipt": "x3_disposition_receipt.json"},
        )
    from apps_rg.runtime.orchestration.canonical_dispatch import (
        _augment_integrated_manifest_with_apps_rg_docx,
        _augment_r4_run_manifest_for_apps_rg_l2_fault,
    )

    _augment_integrated_manifest_with_apps_rg_docx(art)
    _augment_r4_run_manifest_for_apps_rg_l2_fault(
        art,
        fault=result.fault,
        x3_disposition=result.x3_disposition,
    )
    _augment_r4_manifest_draft_leg_only(
        art,
        spine_manifest_ref=sr.FILENAME_SPINE_MANIFEST,
    )

    rid = str(getattr(result, "run_id", "") or "").strip()
    emit_integrated_run_bundle_index(repo, art, run_id=rid or None, correlation_id=rid or None)
    final_resume_outputs_pre_emitted = False
    if result.fault == "":
        from apps_rg.runtime.final_resume_outputs import emit_final_resume_product_outputs

        emit_final_resume_product_outputs(art, repo_root=repo, required=True)
        final_resume_outputs_pre_emitted = True
        stage_ledger.record(
            stage_id="CANDIDATE",
            status="PASS",
            output_refs={"apps_rg_output_manifest": "apps_rg_output_manifest.json"},
        )

    section_status_md: str | None = None
    if is_integrated_whole_run_artifact_dir(art):
        try:
            from apps_rg.runtime.full_run_section_status import emit_full_run_section_status

            status_emit = emit_full_run_section_status(art, repo_root=repo, print_stdout=False)
            section_status_md = str(status_emit["markdown_path"])
        except OSError:
            section_status_md = None

    from apps_rg.runtime.whole_run_exit import emit_whole_run_exit_review_packet

    whole_run_exit_identity = _whole_run_exit_identity(
        raw_request=raw_request,
        validated_request=validated_request,
    )
    whole_run_exit = emit_whole_run_exit_review_packet(
        artifact_dir=art,
        identity=whole_run_exit_identity,
    )
    exec_summary_block = executive_summary_certification_block(art)
    exec_summary_blocked = bool(exec_summary_block.get("blocked"))
    effective_x3 = (
        str(exec_summary_block.get("x3_disposition") or EXECUTIVE_SUMMARY_JUDGE_REVIEW_X3)
        if exec_summary_blocked
        else str(whole_run_exit.get("x3_disposition") or "X3A_DENY_REROUTE")
    )
    if not _product_x3_authorizes(effective_x3) or exec_summary_blocked:
        try:
            from apps_rg.runtime.orchestration.ResumeRunRecoveryAgent import (
                ResumeRunRecoveryAgent,
            )

            recovery_agent = ResumeRunRecoveryAgent(artifact_dir=art, repo_root=repo)
            if recovery_agent.can_attempt_recovery(
                whole_run_exit, exec_summary_block
            ):
                (
                    whole_run_exit,
                    effective_x3,
                    exec_summary_blocked,
                ) = recovery_agent.attempt_recovery(
                    whole_run_exit=whole_run_exit,
                    whole_run_exit_identity=whole_run_exit_identity,
                    raw_request=raw_request,
                    validated_request=validated_request,
                )
        except Exception:  # guardian: recovery failure must fail closed to original exit
            pass
    pre_uwg_eligible = (
        result.fault == ""
        and not exec_summary_blocked
        and _product_x3_authorizes(effective_x3)
    )
    product_authorized = False
    pipeline_complete = False
    post_boundary_candidate = False
    product_close_candidate = False
    observability_repair_required = False
    post_x3_completion: dict[str, Any] = {}
    result_fault = result.fault
    product_authority_error = ""
    non_product_terminal_refs: dict[str, str] = {}
    pending_non_product_terminalization = False
    if product_stage_ledger is not None and pre_uwg_eligible:
        from apps_rg.runtime.product_stage_authority import (
            emit_product_eligibility_authority_receipt,
            emit_runtime_stage_authority_receipts,
        )

        try:
            identity = dict(raw_request["canonical_run_identity"])
            runtime_authority = emit_runtime_stage_authority_receipts(
                artifact_dir=art,
                identity=identity,
            )
            for stage_id in (
                "APPS_RG_C0",
                "APPS_RG_PA",
                "APPS_RG_L2",
                "X1_REVIEW",
                "X2_AGGREGATION",
                "X3_DISPOSITION",
            ):
                entry = product_stage_ledger.record_from_receipt(
                    stage_id=stage_id,
                    receipt_ref=runtime_authority[stage_id],
                    artifact_refs=_authority_source_refs(
                        runtime_authority[stage_id]
                    ),
                    next_stage_id=(
                        "PRODUCT_ELIGIBILITY"
                        if stage_id == "X3_DISPOSITION"
                        else None
                    ),
                )
                if entry["status"] != "PASS":
                    raise ProductE2EAuthorityError(
                        f"receipt-derived product stage blocked: {stage_id}"
                    )
            eligibility_authority = emit_product_eligibility_authority_receipt(
                artifact_dir=art,
                identity=identity,
            )
            eligibility_entry = product_stage_ledger.record_from_receipt(
                stage_id="PRODUCT_ELIGIBILITY",
                receipt_ref=eligibility_authority,
                artifact_refs=_authority_source_refs(eligibility_authority),
            )
            if eligibility_entry["status"] != "PASS":
                raise ProductE2EAuthorityError(
                    "receipt-derived product eligibility blocked"
                )
        except Exception as exc:  # guardian: product authority fails closed before UWG
            pre_uwg_eligible = False
            product_authority_error = f"{type(exc).__name__}:{exc}"
            result_fault = "PRODUCT_E2E_RECEIPT_AUTHORITY_FAILED"
    pending_non_product_terminalization = (
        product_stage_ledger is not None and not pre_uwg_eligible
    )
    if pre_uwg_eligible and require_fresh_preflight:
        from apps_rg.runtime.post_x3_completion import complete_apps_rg_post_x3

        post_x3_completion = complete_apps_rg_post_x3(
            artifact_dir=art,
            result={
                "exit_status": "success",
                "execution_status": "completed",
                "outcome_authorized": True,
                "x3_disposition": effective_x3,
                "core_x3_disposition": result.x3_disposition,
                "completion_disposition": effective_x3,
                "fault": result.fault,
                "artifact_dir": str(art),
                "run_id": result.run_id,
                "request_id": result.request_id,
            },
            raw_request=raw_request,
        )
        product_authorized = (
            post_x3_completion.get("product_authorized") is True
            if "product_authorized" in post_x3_completion
            else bool(
                post_x3_completion.get("x3_to_uwg_completed") is True
                and post_x3_completion.get("durable_promotion_committed") is True
            )
        )
        post_boundary_candidate = (
            post_x3_completion.get("pipeline_complete") is True
            if "pipeline_complete" in post_x3_completion
            else post_x3_completion.get("x3_to_uwg_to_eval_to_l6_completed") is True
        )
        pipeline_complete = (
            False
            if product_stage_ledger is not None
            else post_boundary_candidate
        )
        if product_stage_ledger is not None and product_authorized:
            from apps_rg.runtime.product_stage_authority import (
                emit_post_boundary_authority_receipts,
            )

            try:
                uwg_ref = str(
                    ((post_x3_completion.get("uwg") or {}).get("artifacts") or {}).get(
                        "uwg_commit_receipt"
                    )
                    or ""
                )
                product_authorization_ref = str(
                    post_x3_completion.get("product_authorization_receipt_ref") or ""
                )
                if not uwg_ref or not product_authorization_ref:
                    raise ProductE2EAuthorityError(
                        "UWG/product authorization close receipts are missing"
                    )
                for stage_id, receipt_ref in (
                    ("UWG_COMMIT", uwg_ref),
                    ("PRODUCT_AUTHORIZATION_CLOSE", product_authorization_ref),
                ):
                    entry = product_stage_ledger.record_from_receipt(
                        stage_id=stage_id,
                        receipt_ref=receipt_ref,
                    )
                    if entry["status"] != "PASS":
                        raise ProductE2EAuthorityError(
                            f"receipt-derived product close blocked: {stage_id}"
                        )
                if not post_boundary_candidate:
                    raise ProductE2EAuthorityError(
                        "post-boundary completion is not a terminal-close candidate"
                    )
                post_boundary_authority = emit_post_boundary_authority_receipts(
                    artifact_dir=art,
                    identity=dict(raw_request["canonical_run_identity"]),
                    post_x3_completion=post_x3_completion,
                )
                for stage_id in (
                    "APPS_EVAL",
                    "L6_SHADOW",
                    "INDEPENDENT_PARITY",
                    "PROMOTION_TERMINAL",
                ):
                    entry = product_stage_ledger.record_from_receipt(
                        stage_id=stage_id,
                        receipt_ref=post_boundary_authority[stage_id],
                        artifact_refs=_authority_source_refs(
                            post_boundary_authority[stage_id]
                        ),
                    )
                    if entry["status"] != "PASS":
                        raise ProductE2EAuthorityError(
                            f"receipt-derived post-boundary stage blocked: {stage_id}"
                        )
                product_close_candidate = True
            except Exception as exc:  # guardian: UWG authority remains immutable
                product_authority_error = f"{type(exc).__name__}:{exc}"
                product_close_candidate = False
        observability_repair_required = bool(
            product_authorized
            and not (
                product_close_candidate
                if product_stage_ledger is not None
                else pipeline_complete
            )
        )
        if product_authorized and pipeline_complete:
            # Cache learning is future-run authority and cannot precede UWG.
            maybe_ingest_r1b_post_exit(
                raw_request=raw_request,
                artifact_dir=art,
                runs_dir=art.parent,
            )
        if not (
            product_close_candidate
            if product_stage_ledger is not None
            else pipeline_complete
        ):
            result_fault = (
                "PRODUCT_E2E_RECEIPT_AUTHORITY_FAILED"
                if product_authority_error
                else str(
                    post_x3_completion.get("failure_stage")
                    or "post_x3_completion"
                )
            )
    elif pre_uwg_eligible:
        result_fault = "FRESH_PREFLIGHT_REQUIRED_FOR_PRODUCT_AUTHORIZATION"
    elif not result_fault:
        result_fault = (
            "PRODUCT_X3D_ALLOW_FINISH_REQUIRED"
            if not _product_x3_authorizes(effective_x3)
            else "PRODUCT_NOT_ELIGIBLE_FOR_UWG"
        )
    if final_resume_outputs_pre_emitted and product_stage_ledger is None:
        apps_eval_completion = (
            post_x3_completion.get("apps_eval")
            if isinstance(post_x3_completion.get("apps_eval"), dict)
            else {}
        )
        coverage = (
            apps_eval_completion.get("coverage_summary")
            if isinstance(apps_eval_completion.get("coverage_summary"), dict)
            else {}
        )
        eval_pass = bool(
            coverage.get("release_blocked") is False
            and coverage.get("coverage_complete") is True
        )
        if not post_x3_completion:
            stage_ledger.record(
                stage_id="APPS_EVAL",
                status="BLOCKED",
                reason_code="X3_OR_EXECUTIVE_SUMMARY_NOT_AUTHORIZED",
            )
        elif not eval_pass:
            stage_ledger.record(
                stage_id="APPS_EVAL",
                status="FAIL",
                reason_code=str(
                    post_x3_completion.get("failure_stage") or "APPS_EVAL_FAILED"
                ),
                output_refs={
                    "eval_record": str(apps_eval_completion.get("eval_record_ref") or "")
                },
            )
        else:
            stage_ledger.record(
                stage_id="APPS_EVAL",
                status="PASS",
                output_refs={
                    "eval_record": str(apps_eval_completion.get("eval_record_ref") or "")
                },
            )
            l6_completion = (
                post_x3_completion.get("l6_shadow")
                if isinstance(post_x3_completion.get("l6_shadow"), dict)
                else {}
            )
            l6_pass = bool(
                l6_completion.get("l6_shadow_bridge_ref")
                and l6_completion.get("grain_parity_status") == "PASS"
                and l6_completion.get("apps_eval_rows_bound") is True
            )
            stage_ledger.record(
                stage_id="L6_SHADOW",
                status="PASS" if l6_pass else "FAIL",
                reason_code="L6_APPS_EVAL_BOUND" if l6_pass else "L6_CLOSURE_INCOMPLETE",
                output_refs={
                    "l6_shadow_bridge": str(
                        l6_completion.get("l6_shadow_bridge_ref") or ""
                    )
                },
            )
            if l6_pass:
                promotion_pass = bool(
                    post_x3_completion.get("completed")
                    and post_x3_completion.get("durable_promotion_committed") is True
                    and (post_x3_completion.get("fact_vector_writeback") or {}).get(
                        "status"
                    )
                    != "FAIL"
                )
                stage_ledger.record(
                    stage_id="STATE_PROMOTION",
                    status="PASS" if promotion_pass else "FAIL",
                    reason_code=(
                        "DURABLE_PROMOTION_COMMITTED"
                        if promotion_pass
                        else str(
                            post_x3_completion.get("failure_stage")
                            or "DURABLE_PROMOTION_INCOMPLETE"
                        )
                    ),
                    output_refs={
                        "post_x3_completion": "apps_rg_post_x3_completion_receipt.json"
                    },
                )
    payload: dict[str, Any] = {
        "exit_status": "success" if pipeline_complete else "error",
        "execution_status": "completed" if pipeline_complete else "failed",
        # Legacy field remains a compatibility alias for immutable current-run
        # product authority, never for post-boundary pipeline completion.
        "outcome_authorized": product_authorized,
        "product_authorized": product_authorized,
        "pipeline_complete": pipeline_complete,
        "observability_repair_required": observability_repair_required,
        "x3_disposition": effective_x3,
        "core_x3_disposition": result.x3_disposition,
        "apps_rg_whole_run_exit_review_packet": (
            "apps_rg_whole_run_exit_review_packet.json"
        ),
        "completion_disposition": effective_x3,
        "completion_status": "PASS" if pipeline_complete else "BLOCKED",
        "fault": result_fault,
        "artifact_dir": str(art),
        "run_id": result.run_id,
        "request_id": result.request_id,
        "route_family": route.route_family,
        "draft_leg_route_family": DRAFT_LEG_ROUTE_FAMILY,
        "spine_run_manifest": str(art / sr.FILENAME_SPINE_MANIFEST),
        "route_decision": route_decision,
        "plan_execution_receipt": plan_execution_receipt,
        "plan_replan_decision": plan_replan_decision,
        "research_delegation_executed": research_ran,
        "l7_how_trace_emitted": bool(result.fault == "" and (art / "apps_rg_how_trace.json").is_file()),
        "terminal_r5": result.terminal_r5,
        "executive_summary_certification_block": exec_summary_block,
        "post_x3_completion": post_x3_completion,
        "uwg_commit_receipt_ref": (
            (post_x3_completion.get("uwg") or {})
            .get("artifacts", {})
            .get("uwg_commit_receipt", "")
            if isinstance(post_x3_completion.get("uwg"), dict)
            else ""
        ),
        "apps_eval_record_ref": (
            (post_x3_completion.get("apps_eval") or {}).get("eval_record_ref", "")
            if isinstance(post_x3_completion.get("apps_eval"), dict)
            else ""
        ),
        "l6_shadow_bridge_ref": (
            (post_x3_completion.get("l6_shadow") or {}).get("l6_shadow_bridge_ref", "")
            if isinstance(post_x3_completion.get("l6_shadow"), dict)
            else ""
        ),
    }
    payload.update(non_product_terminal_refs)
    if research_ran:
        payload["delegated_briefing"] = str(art / sr.FILENAME_DELEGATED_BRIEFING)
        payload["research_bridge_response"] = str(art / sr.FILENAME_RESEARCH_BRIDGE_RESPONSE)
    immutable_product_authorized = product_authorized
    _emit_terminal_mandatory_closeout(
        artifact_dir=art,
        repo_root=repo,
        payload=payload,
        final_resume_outputs_pre_emitted=final_resume_outputs_pre_emitted,
    )
    if not immutable_product_authorized:
        # Failure closeout may materialize a gap-marked FINAL_RESUME_OUTPUT
        # after the first Exit packet was emitted.  Re-derive the blocked
        # packet now so its source bindings and diagnosis describe the final
        # persisted failure state.  A product-authorized packet is immutable
        # and is never rewritten here.
        whole_run_exit = emit_whole_run_exit_review_packet(
            artifact_dir=art,
            identity=whole_run_exit_identity,
        )
        if not exec_summary_blocked:
            effective_x3 = str(
                whole_run_exit.get("x3_disposition") or "X3A_DENY_REROUTE"
            )
        payload["x3_disposition"] = effective_x3
        payload["completion_disposition"] = effective_x3
    if pending_non_product_terminalization:
        try:
            # Failure closeout can write the final, gap-marked output and
            # re-derive Exit.  Bind that final packet before the receipt-derived
            # non-product ledger is sealed; otherwise the ledger intentionally
            # detects its own stale source digest on the next validation pass.
            non_product_terminal_refs = _seal_pending_non_product_stage_ledger(
                artifact_dir=art,
                product_ledger=product_stage_ledger,
                identity=dict(raw_request["canonical_run_identity"]),
            )
            payload.update(non_product_terminal_refs)
        except Exception as exc:  # guardian: preserve the primary product failure
            terminal_error = f"{type(exc).__name__}:{exc}"
            product_authority_error = (
                f"{product_authority_error};{terminal_error}"
                if product_authority_error
                else terminal_error
            )
    if immutable_product_authorized:
        # Mandatory closeout is post-boundary.  It may make the pipeline
        # incomplete, but it cannot revoke a UWG-closed current-run product.
        payload["outcome_authorized"] = True
        payload["product_authorized"] = True
        mandatory_gate = payload.get("mandatory_output_hard_stop")
        if (
            (isinstance(mandatory_gate, dict) and mandatory_gate.get("pass") is False)
            or payload.get("terminal_closeout_failed")
            or payload.get("exit_status") == "error"
        ):
            product_close_candidate = False
            payload["exit_status"] = "error"
            payload["execution_status"] = "failed"
            payload["pipeline_complete"] = False
            payload["observability_repair_required"] = True
            payload["completion_status"] = "BLOCKED"
            if not payload.get("fault"):
                payload["fault"] = MANDATORY_OUTPUT_HARD_STOP_GATE_ID
    # Raw prompts and provider transport output are diagnostics, not product
    # authority. Redact them before the optional review package and before the
    # terminal manifest captures any artifact bindings.
    if product_stage_ledger is not None and immutable_product_authorized and product_close_candidate:
        try:
            from apps_rg.runtime.product_artifact_privacy import redact_product_diagnostics

            payload["product_diagnostic_redaction_receipt"] = str(
                redact_product_diagnostics(art)
            )
        except Exception as exc:
            product_authority_error = f"{type(exc).__name__}:{exc}"
            product_close_candidate = False
            payload.update(
                {
                    "exit_status": "error",
                    "execution_status": "failed",
                    "pipeline_complete": False,
                    "observability_repair_required": True,
                    "completion_status": "BLOCKED",
                    "fault": "PRODUCT_DIAGNOSTIC_REDACTION_FAILED",
                }
            )
    review_zip = None
    if is_integrated_whole_run_artifact_dir(art):
        try:
            review_zip = emit_full_resume_review_bundle(art)
        except OSError:
            review_zip = None
    if review_zip is not None:
        payload["review_bundle_zip"] = str(review_zip)
        payload["review_bundle_relpath"] = REVIEW_BUNDLE_FILENAME
    if section_status_md is not None:
        payload["full_run_section_status_md"] = section_status_md
    if product_stage_ledger is not None:
        payload["pipeline_complete"] = False
        payload["completion_status"] = "BLOCKED"
        if immutable_product_authorized and product_close_candidate:
            try:
                terminal_refs = _seal_product_terminal_authority(
                    artifact_dir=art,
                    product_ledger=product_stage_ledger,
                    identity=dict(raw_request["canonical_run_identity"]),
                    product_authorization_ref=str(
                        post_x3_completion.get(
                            "product_authorization_receipt_ref"
                        )
                        or ""
                    ),
                )
                payload.update(terminal_refs)
                payload.update(
                    {
                        "exit_status": "success",
                        "execution_status": "completed",
                        "outcome_authorized": True,
                        "product_authorized": True,
                        "pipeline_complete": True,
                        "observability_repair_required": False,
                        "completion_status": "PASS",
                        "fault": "",
                    }
                )
                # Cache learning is future-run authority and may follow only the
                # externally bound terminal completion receipt.
                maybe_ingest_r1b_post_exit(
                    raw_request=raw_request,
                    artifact_dir=art,
                    runs_dir=art.parent,
                )
            except Exception as exc:  # guardian: preserve immutable UWG product state
                product_authority_error = f"{type(exc).__name__}:{exc}"
                product_close_candidate = False
                payload.update(
                    {
                        "exit_status": "error",
                        "execution_status": "failed",
                        "outcome_authorized": False,
                        "product_authorized": False,
                        "pipeline_complete": False,
                        "observability_repair_required": bool(
                            immutable_product_authorized
                        ),
                        "completion_status": "BLOCKED",
                        "fault": "PRODUCT_E2E_TERMINAL_SEAL_FAILED",
                    }
                )
        if product_authority_error:
            payload["product_e2e_authority_error"] = product_authority_error
    active_ledger = product_stage_ledger or stage_ledger
    _record_closeout_stage_unless_sealed(
        stage_ledger=active_ledger,
        payload=payload,
    )
    from apps_rg.runtime.e2e_stage_ledger import verify_e2e_stage_ledger

    ledger_report = verify_e2e_stage_ledger(active_ledger.path)
    payload["e2e_stage_ledger"] = str(active_ledger.path)
    payload["e2e_stage_ledger_valid"] = ledger_report.valid
    payload["e2e_stage_ledger_complete"] = ledger_report.complete
    if payload.get("product_authorized") is True and not ledger_report.complete:
        payload["exit_status"] = "error"
        payload["execution_status"] = "failed"
        payload["outcome_authorized"] = True
        payload["product_authorized"] = True
        payload["pipeline_complete"] = False
        payload["observability_repair_required"] = True
        payload["completion_status"] = "BLOCKED"
        if not str(payload.get("fault") or "").strip():
            payload["fault"] = "E2E_STAGE_LEDGER_INCOMPLETE"
        else:
            payload.setdefault("pipeline_reconciliation_faults", []).append(
                "E2E_STAGE_LEDGER_INCOMPLETE"
            )
        payload["e2e_stage_ledger_errors"] = list(ledger_report.errors)
    return payload


__all__ = [
    "ROUTE_FAMILY_R3R4",
    "apps_research_handoff_authorized",
    "briefing_input_present",
    "research_delegation_enabled",
    "run_whole_run_with_route_governance",
    "should_delegate_apps_research",
]
