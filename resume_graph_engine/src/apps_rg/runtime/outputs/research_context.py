"""Apps research gate context and briefing parsers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *

__all__ = ['_apps_research_gate_context', '_research_source_class', '_research_x2_cell', '_research_x3_cell', '_research_briefing_context', '_research_briefing_row', '_research_row']

def _apps_research_gate_context(
    run_root: Path,
    *,
    repo_root: Path,
    ingress: dict[str, Any],
    spine: dict[str, Any],
    brief_ref: str,
    auto_research_internal: Any,
) -> dict[str, Any]:
    jd_ref = _first_nonempty(
        _artifact_input_value(ingress, "job_description_ref", "jd_ref", "jd_path"),
        _artifact_input_value(ingress, "jd", "job_description_text", "jd_text"),
    )
    resolved_brief = _resolve_input_ref(brief_ref, run_root=run_root, repo_root=repo_root)
    resolved_jd = _resolve_input_ref(jd_ref, run_root=run_root, repo_root=repo_root)
    strict_required = auto_research_internal is True and bool(str(brief_ref or "").strip())
    validation_envelope: dict[str, Any] | None = None
    try:
        validation = validate_apps_research_handoff(
            brief_ref=resolved_brief,
            jd_ref=resolved_jd,
            require_observed=strict_required,
            require_x1_x3_authorization=strict_required,
        )
        validation_receipt = validation.to_receipt()
        validation_envelope = validation.envelope if isinstance(validation.envelope, dict) else None
    except (OSError, ValueError) as exc:
        validation_receipt = {
            "schema_version": "apps_rg.apps_research_handoff_validation_receipt.v1",
            "observed": False,
            "valid": not strict_required,
            "reason": f"brief_ref_unresolvable:{type(exc).__name__}",
            "envelope_path": "",
        }
    receipt = _research_handoff_receipt(run_root) or validation_receipt
    envelope = (
        validation_envelope
        if isinstance(validation_envelope, dict)
        else _research_handoff_v2(
            run_root,
            repo_root=repo_root,
            brief_ref=resolved_brief,
        )
    )
    identity = (
        envelope.get("identity")
        if isinstance(envelope.get("identity"), dict)
        else {}
    )
    gate_receipts = (
        envelope.get("mandatory_gate_receipts")
        if isinstance(envelope.get("mandatory_gate_receipts"), dict)
        else {}
    )
    exit_authorization = (
        envelope.get("exit_authorization")
        if isinstance(envelope.get("exit_authorization"), dict)
        else {}
    )
    model_observations = (
        envelope.get("model_observations")
        if isinstance(envelope.get("model_observations"), dict)
        else {}
    )
    generation_observation = (
        model_observations.get("generation")
        if isinstance(model_observations.get("generation"), dict)
        else {}
    )
    judge_observation = (
        model_observations.get("judge")
        if isinstance(model_observations.get("judge"), dict)
        else {}
    )
    route_decision = spine.get("route_decision") if isinstance(spine.get("route_decision"), dict) else {}
    if "status" in receipt:
        # The frozen v2 consumer receipt deliberately has no legacy
        # ``observed``/``valid``/``reason`` projection.  Its authoritative
        # status and failure-reason vector must drive the gate row directly.
        receipt_status = str(receipt.get("status") or "UNKNOWN").upper()
        receipt_failures = receipt.get("failure_reasons")
        failure_reasons = (
            [str(item) for item in receipt_failures if str(item).strip()]
            if isinstance(receipt_failures, list)
            else []
        )
        observed = True
        valid = receipt_status == "PASS"
        reason = "ok" if valid else ";".join(failure_reasons) or receipt_status
    else:
        observed = receipt.get("observed")
        valid = receipt.get("valid")
        reason = str(receipt.get("reason") or "NOT_OBSERVED")
    exact_gates_pass = set(gate_receipts) == {
        "G5",
        "G6",
        "G7",
        "G21",
        "G24",
        "G26",
    } and all(
        isinstance(gate, dict) and gate.get("status") == "PASS"
        for gate in gate_receipts.values()
    )
    if observed:
        x1_status = "PASS" if valid else "BLOCKED"
        x2_status = "PASS" if valid and exact_gates_pass else "BLOCKED"
        x3_disposition = str(
            exit_authorization.get("x3_code") or "NOT_OBSERVED"
        )
        x3_status = (
            "PASS"
            if valid and x3_disposition == "X3D_ALLOW_FINISH"
            else "BLOCKED"
        )
    else:
        x1_status = "NOT_OBSERVED"
        x2_status = "NOT_OBSERVED"
        x3_status = "NOT_OBSERVED"
        x3_disposition = "NOT_OBSERVED"
    x2_score = "NOT_OBSERVED"
    x2_judge_model = (
        str(judge_observation.get("observed_model") or "MODEL_NOT_OBSERVED")
        if judge_observation.get("status") == "OBSERVED_PROVIDER_RESPONSE"
        else "MODEL_NOT_OBSERVED"
    )
    generation_provider = (
        str(generation_observation.get("provider") or "NOT_OBSERVED")
        if generation_observation.get("status") == "OBSERVED_PROVIDER_RESPONSE"
        else "NOT_OBSERVED"
    )
    generation_model = (
        str(generation_observation.get("observed_model") or "MODEL_NOT_OBSERVED")
        if generation_observation.get("status") == "OBSERVED_PROVIDER_RESPONSE"
        else "MODEL_NOT_OBSERVED"
    )
    handoff_eligible = valid
    summary = (
        f"handoff_observed={observed}; handoff_valid={valid}; reason={reason}; "
        f"run_id={str(identity.get('child_run_id') or route_decision.get('research_run_id') or 'NOT_OBSERVED')}; "
        f"eligible={handoff_eligible}; "
        f"X1={x1_status}; X2={x2_status}"
        f"{' score=' + x2_score if x2_score != 'NOT_OBSERVED' else ''}"
        f"{' judge_model=' + x2_judge_model if x2_judge_model != 'NOT_OBSERVED' else ''}; "
        f"X3={x3_status}/{x3_disposition}; "
        f"brief_sha={_short_digest(identity.get('brief_sha256'))}; "
        f"jd_sha={_short_digest(identity.get('jd_sha256'))}"
    )
    return {
        "summary": summary,
        "observed": observed,
        "valid": valid,
        "reason": reason,
        "x1_status": x1_status,
        "x2_status": x2_status,
        "x3_status": x3_status,
        "x3_disposition": x3_disposition,
        "x2_judge_model": x2_judge_model,
        "x2_score": x2_score,
        "generation_provider": generation_provider,
        "generation_model": generation_model,
    }


def _research_source_class(
    *,
    auto_research_internal: Any,
    delegation_observed: Any,
    briefing_present: bool,
    research_via: str = "",
) -> str:
    via = str(research_via or "").strip().lower()
    if delegation_observed is True:
        return "FRESH_APPS_RESEARCH"
    if via in {"skip", "operator_skip", "none"}:
        return "OPERATOR_SKIP"
    if briefing_present:
        return "STATIC_MANUAL_BRIEF"
    if auto_research_internal is True:
        return "MISSING_APPS_RESEARCH"
    return "NOT_OBSERVED"


def _research_x2_cell(gates: dict[str, Any]) -> str:
    status = str(gates.get("x2_status") or "NOT_OBSERVED")
    if status == "NOT_OBSERVED":
        reason = str(gates.get("reason") or "").strip()
        return f"NOT_OBSERVED; blocker={reason}" if reason else "NOT_OBSERVED"
    parts = [status]
    score = str(gates.get("x2_score") or "").strip()
    judge = str(gates.get("x2_judge_model") or "").strip()
    if score and score != "NOT_OBSERVED":
        parts.append(score)
    if judge and judge != "NOT_OBSERVED":
        parts.append(f"judge={judge}")
    return "; ".join(parts)


def _research_x3_cell(gates: dict[str, Any]) -> str:
    disposition = str(gates.get("x3_disposition") or gates.get("x3_status") or "NOT_OBSERVED")
    x1_status = str(gates.get("x1_status") or "NOT_OBSERVED")
    if disposition == "NOT_OBSERVED":
        reason = str(gates.get("reason") or "").strip()
        return f"NOT_OBSERVED; blocker={reason}" if reason else "NOT_OBSERVED"
    return f"{disposition}; X1={x1_status}"


def _research_briefing_context(run_root: Path, *, repo_root: Path) -> dict[str, Any]:
    phase1 = _load_json(run_root / "modular_r4" / "phase1_lane_inventory.json")
    targeting = phase1.get("lane_argv_targeting") if isinstance(phase1.get("lane_argv_targeting"), dict) else {}
    briefing = _briefing_blob(targeting.get("briefing_text"))
    ingress = _load_json(run_root / "ingress_raw.json")
    spine = _load_json(run_root / "spine_run_manifest.json")
    route_decision = spine.get("route_decision") if isinstance(spine.get("route_decision"), dict) else {}
    delegation_observed = (
        spine.get("research_delegation_executed")
        if "research_delegation_executed" in spine
        else route_decision.get("research_delegation_executed")
        if "research_delegation_executed" in route_decision
        else "NOT_OBSERVED"
    )
    auto_research_internal = ingress.get("auto_research_internal", route_decision.get("research_delegation_enabled"))
    research_via = _first_nonempty(ingress.get("research_via"), route_decision.get("research_via"))
    source = _first_nonempty(
        targeting.get("briefing_source"),
        briefing.get("source"),
        ingress.get("research_via"),
        "NOT_OBSERVED",
    )
    digest = _first_nonempty(
        targeting.get("briefing_digest"),
        briefing.get("briefing_digest"),
        briefing.get("digest"),
        ingress.get("brief_hash"),
    )
    ref = _first_nonempty(
        targeting.get("briefing_ref_used"),
        targeting.get("briefing_artifact_ref"),
        route_decision.get("delegated_briefing_path"),
        ingress.get("manual_brief"),
        ingress.get("manual_brief_path"),
        ingress.get("briefing_artifact_ref"),
    )
    company = _first_nonempty(targeting.get("target_company"), briefing.get("target_company"), ingress.get("target_company"))
    title = _first_nonempty(
        targeting.get("target_title"),
        briefing.get("target_role"),
        briefing.get("target_title"),
        ingress.get("target_role"),
    )
    briefing_text = _first_nonempty(briefing.get("briefing_text"), targeting.get("briefing_text"), ingress.get("briefing_text"))
    gates = _apps_research_gate_context(
        run_root,
        repo_root=repo_root,
        ingress=ingress,
        spine=spine,
        brief_ref=ref,
        auto_research_internal=auto_research_internal,
    )
    return {
        "auto_research_internal": auto_research_internal,
        "research_delegation_executed": delegation_observed,
        "research_via": research_via,
        "source": source,
        "digest": digest,
        "ref": ref,
        "target_company": company,
        "target_title": title,
        "briefing_text": briefing_text,
        "briefing_text_chars": len(briefing_text) if briefing_text else 0,
        "fetched_at": _first_nonempty(briefing.get("fetched_at"), targeting.get("fetched_at")),
        "source_url": _first_nonempty(briefing.get("source_url"), targeting.get("source_url")),
        "briefing_present": bool(briefing_text or ref or digest),
        "apps_research_gates": gates,
    }


def _research_briefing_row(run_root: Path, *, repo_root: Path, cache: dict[str, str]) -> dict[str, Any]:
    context = _research_briefing_context(run_root, repo_root=repo_root)
    delegation_observed = context["research_delegation_executed"]
    auto_research_internal = context.get("auto_research_internal")
    source = str(context.get("source") or "NOT_OBSERVED")
    digest = str(context.get("digest") or "")
    ref = str(context.get("ref") or "")
    company = str(context.get("target_company") or "")
    title = str(context.get("target_title") or "")
    briefing_present = bool(context.get("briefing_present"))
    gates = context.get("apps_research_gates") if isinstance(context.get("apps_research_gates"), dict) else {}
    generation_provider = str(gates.get("generation_provider") or "").strip()
    generation_model = str(gates.get("generation_model") or "").strip()
    research_source_class = _research_source_class(
        auto_research_internal=auto_research_internal,
        delegation_observed=delegation_observed,
        briefing_present=briefing_present,
        research_via=str(context.get("research_via") or ""),
    )
    p0_static_manual = auto_research_internal is True and delegation_observed is not True
    evidence_parts = [
        f"auto_research_internal={auto_research_internal}",
        f"research_delegation_executed={delegation_observed}",
        f"source={source}",
    ]
    if context.get("fetched_at"):
        evidence_parts.append(f"fetched_at={context['fetched_at']}")
    if digest:
        evidence_parts.append(f"digest={digest}")
    if ref:
        evidence_parts.append(f"ref={ref}")
    if company or title:
        evidence_parts.append(f"target={company or 'UNKNOWN'} / {title or 'UNKNOWN'}")
    if context.get("briefing_text_chars"):
        evidence_parts.append(f"briefing_text_chars={context['briefing_text_chars']}")
    if not briefing_present:
        evidence_parts.append("briefing missing")
    return {
        "order": 0,
        "section": "research_briefing_input",
        "research_source_class": research_source_class,
        "r1a": cache["r1a"],
        "r1b": cache["r1b"],
        "lane_record": "YES" if briefing_present else "NO",
        "provider_call_attempted": delegation_observed,
        "primary_provider": (
            generation_provider
            if delegation_observed is True and generation_provider and generation_provider != "NOT_OBSERVED"
            else "NOT_OBSERVED"
            if delegation_observed is True
            else "STATIC_MANUAL_BRIEF" if briefing_present else "NOT_OBSERVED"
        ),
        "primary_model_observed": (
            generation_model
            if delegation_observed is True
            and generation_model
            and generation_model not in {"NOT_OBSERVED", "MODEL_NOT_OBSERVED"}
            else "MODEL_NOT_OBSERVED"
            if delegation_observed is True
            else "NOT_OBSERVED"
        ),
        "pooling_selector_llm": "N/A",
        "secondary_provider": "N/A",
        "secondary_model_observed": "N/A",
        "generation_status": (
            "P0_STATIC_MANUAL_BRIEF_USED"
            if p0_static_manual
            else f"BRIEFING_PRESENT:{source}" if briefing_present else "MISSING_BRIEFING"
        ),
        "judges_run": "N/A",
        "judge_models_scores": "N/A",
        "judge_retry_fallback": "N/A",
        "x2": _research_x2_cell(gates),
        "x3": (
            "FAIL"
            if p0_static_manual or not briefing_present
            else _research_x3_cell(gates)
        ),
        "past_fail_blocker": "; ".join(evidence_parts),
        "display_output": ref or "MISSING",
        "l6_evidence": "N/A",
    }


def _research_row(doc: dict[str, Any]) -> dict[str, Any]:
    rows = doc.get("section_lane_table") if isinstance(doc.get("section_lane_table"), list) else []
    for row in rows:
        if isinstance(row, dict) and row.get("section") == "research_briefing_input":
            return row
    return {}

