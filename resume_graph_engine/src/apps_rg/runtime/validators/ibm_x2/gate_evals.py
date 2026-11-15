"""Deterministic gate-evaluation helpers for ``run_ibm_bullets_x2_gates``."""
from __future__ import annotations

import json
from typing import Any, Mapping

from apps_rg.runtime.validators.executive_summary_x2 import (
    check_claim_ledger_claim_text_non_empty,
    check_judge_schema_valid,
)
from apps_rg.runtime.validators.ibm_x2.constants import IBM_BULLET_IDS
from apps_rg.runtime.validators.ibm_x2.coverage_checks import _all_source_fact_ids


def _resolve_ibm_proof_context(
    allowed_fact_ids: set[str],
    proof_pool_digest: str,
    proof_pool_metadata: dict[str, Any] | None,
    parsed_output: dict[str, Any] | None,
    runtime_payload: dict[str, Any] | None,
) -> tuple[set[str], str, dict[str, Any] | None, Any, str, tuple[str, ...]]:
    """Normalize runtime proof-pool metadata and expected IBM bullet slot IDs."""
    if runtime_payload:
        allowed_fact_ids = {
            str(x) for x in (runtime_payload.get("allowed_fact_ids") or allowed_fact_ids)
        }
        proof_pool_digest = str(
            runtime_payload.get("canonical_evidence_set_digest") or proof_pool_digest
        )
        meta = dict(proof_pool_metadata or {})
        meta.setdefault(
            "canonical_evidence_set_digest",
            runtime_payload.get("canonical_evidence_set_digest"),
        )
        meta.setdefault(
            "id_alias_map",
            (runtime_payload.get("canonical_section_evidence_set") or {}).get("id_alias_map"),
        )
        proof_pool_metadata = meta

    selected_plan = (
        (runtime_payload or {}).get("selected_fact_plan")
        if runtime_payload
        else (parsed_output or {}).get("selected_fact_plan")
    )
    selection_method = str(
        (proof_pool_metadata or {}).get("selection_method")
        or (selected_plan or {}).get("selection_method")
        or ""
    )

    expected_bullet_ids = IBM_BULLET_IDS
    plan = (
        (parsed_output or {}).get("selected_fact_plan")
        or (runtime_payload or {}).get("selected_fact_plan")
        or {}
    )
    if isinstance(plan, dict):
        if "facts" in plan:
            p_facts = [
                str(f.get("fact_id", "") if isinstance(f, dict) else f).strip()
                for f in (plan.get("facts") or [])
                if str(f.get("fact_id", "") if isinstance(f, dict) else f).strip().startswith("bul_ibm_")
            ]
        else:
            p_facts = [
                str(k).strip()
                for k in plan.keys()
                if str(k).strip().startswith("bul_ibm_")
            ]
        if p_facts:
            expected_bullet_ids = tuple(p_facts)
    elif runtime_payload and runtime_payload.get("allowed_fact_ids"):
        p_facts = [
            str(fid).strip()
            for fid in runtime_payload.get("allowed_fact_ids", [])
            if str(fid).strip().startswith("bul_ibm_")
        ]
        if p_facts:
            expected_bullet_ids = tuple(p_facts)

    return (
        allowed_fact_ids,
        proof_pool_digest,
        proof_pool_metadata,
        selected_plan,
        selection_method,
        expected_bullet_ids,
    )


def _eval_ledger_claim_text(
    claim_ledger: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Evaluate non-empty trimmed claim_text across claim_ledger rows with diagnostic hints."""
    ledger_text_ok, ledger_text_reason = check_claim_ledger_claim_text_non_empty(claim_ledger)
    if not ledger_text_ok and ledger_text_reason:
        hint_parts = []
        for i, row in enumerate(claim_ledger):
            if not isinstance(row, dict):
                continue
            ct = row.get("claim_text")
            if ct is None or (isinstance(ct, str) and not str(ct).strip()):
                b_hint = row.get("bullet_id")
                if b_hint is None and row.get("source_fact_ids"):
                    sfx = f"ledger_idx={i} source_fact_ids={row.get('source_fact_ids')!r}"
                else:
                    sfx = f"ledger_idx={i} bullet_id_hint={b_hint!r} source_fact_ids={row.get('source_fact_ids')!r}"
                hint_parts.append(sfx)
        if hint_parts:
            ledger_text_reason = f"{ledger_text_reason}; " + "; ".join(hint_parts)
    return ledger_text_ok, ledger_text_reason


def _resolve_plan_facts_for_anchors(selected_plan: Any) -> list[dict[str, Any]]:
    """Adapt list or slot-keyed selected_fact_plan into fact rows for anchor checks."""
    plan_facts_for_anchors = list((selected_plan or {}).get("facts") or [])
    if not plan_facts_for_anchors and isinstance(selected_plan, dict):
        plan_facts_for_anchors = [
            {"fact_id": k, **v}
            for k, v in selected_plan.items()
            if isinstance(v, dict) and str(k).startswith("bul_ibm_")
        ]
    return plan_facts_for_anchors


def _eval_hold_metrics(
    bullets: list[dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    """Scan bullets for HOLD/DO_NOT_PROMOTE metrics with slot exceptions."""
    from apps_rg.runtime.sections.ibm_role_episode_evidence import (
        PROMOTABLE_METRIC_OUTCOME_IDS,
        scan_forbidden_metrics_in_text,
    )

    forbidden_hits: list[str] = []
    for b in bullets:
        bid = str(b.get("bullet_id") or "")
        btext = str(b.get("bullet_text") or "")
        hits = scan_forbidden_metrics_in_text(btext)
        if bid == "bul_ibm_002":
            hits = [h for h in hits if h != "30%"]
        elif bid == "bul_ibm_005":
            hits = [h for h in hits if h not in {"$15m", "$15 m", "15m", "$15M", "15M", "15m incremental"}]
        forbidden_hits.extend(hits)
    metrics_obs = {
        "forbidden_absent": not forbidden_hits,
        "promotable_ids": list(PROMOTABLE_METRIC_OUTCOME_IDS),
    }
    return forbidden_hits, metrics_obs


def _eval_skill_ids_and_bundles(
    bullets: list[dict[str, Any]],
    parsed_output: dict[str, Any] | None,
    proof_pool_metadata: dict[str, Any] | None,
    runtime_payload: dict[str, Any] | None,
) -> tuple[list[str], bool, bool, dict[str, Any], list[str], list[str]]:
    """Evaluate change_log graph skill IDs, role episode bundle pool presence, and slot bundle binding."""
    po_change_log = list((parsed_output or {}).get("change_log") or [])
    bullets_missing_skill_ids: list[str] = []
    cl_bullet_ids: set[str] = set()
    for cl_entry in po_change_log:
        if not isinstance(cl_entry, dict):
            continue
        bid_cl = str(cl_entry.get("bullet_id") or "")
        if not bid_cl.startswith("bul_ibm_"):
            continue
        cl_bullet_ids.add(bid_cl)
        skill_ids = (
            cl_entry.get("graph_skill_node_ids")
            or cl_entry.get("skill_ids_used")
            or []
        )
        if not skill_ids:
            bullets_missing_skill_ids.append(bid_cl)
    for b in bullets:
        bid_b = str(b.get("bullet_id") or "")
        if bid_b.startswith("bul_ibm_") and bid_b not in cl_bullet_ids:
            bullets_missing_skill_ids.append(bid_b)

    from apps_rg.runtime.sections.ibm_role_episode_evidence import (
        IBM_BULLET_SLOT_BUNDLE_MAP,
        PROMOTABLE_METRIC_OUTCOME_IDS,
        is_flat_skill_only_graph_packet,
    )

    pp_meta = dict(proof_pool_metadata or {})
    bundles_present = bool(pp_meta.get("role_episode_bundles")) or bool(
        (runtime_payload or {}).get("role_episode_bundle_ids")
    )
    flat_only = is_flat_skill_only_graph_packet(pp_meta) and not bundles_present

    expected_bundle_by_slot = dict(IBM_BULLET_SLOT_BUNDLE_MAP)
    selected_plan = (runtime_payload or {}).get("selected_fact_plan")
    if isinstance(selected_plan, Mapping):
        for row in selected_plan.get("allocation_assignments") or []:
            if not isinstance(row, Mapping) or str(row.get("section_id") or "") != "ibm_bullets":
                continue
            claim_unit_id = str(row.get("claim_unit_id") or "")
            bullet_id = claim_unit_id.rsplit(":", 1)[-1]
            root_id = str(row.get("root_id") or "").strip()
            if bullet_id in IBM_BULLET_IDS and root_id:
                expected_bundle_by_slot[bullet_id] = root_id

    bullets_missing_bundle_id: list[str] = []
    bullets_metric_unsupported: list[str] = []
    allowed_outcomes = set(PROMOTABLE_METRIC_OUTCOME_IDS)
    by_bullet_id = {str(b.get("bullet_id")): b for b in bullets if b.get("bullet_id")}
    for cl_entry in po_change_log:
        if not isinstance(cl_entry, dict):
            continue
        bid_cl = str(cl_entry.get("bullet_id") or "")
        if not bid_cl.startswith("bul_ibm_"):
            continue
        reb = str(cl_entry.get("role_episode_bundle_id") or "").strip()
        expected = expected_bundle_by_slot.get(bid_cl, "")
        if not reb:
            bullets_missing_bundle_id.append(bid_cl)
        elif expected and reb != expected:
            bullets_missing_bundle_id.append(f"{bid_cl}:wrong_bundle={reb}")
        metric_ids = [str(x) for x in (cl_entry.get("metric_outcome_ids") or [])]
        bullet_row = by_bullet_id.get(bid_cl) or {}
        if bullet_row.get("has_metric") and metric_ids:
            if not all(mid in allowed_outcomes for mid in metric_ids):
                bullets_metric_unsupported.append(f"{bid_cl}:invalid_metric_outcome_ids")

    for b in bullets:
        bid_b = str(b.get("bullet_id") or "")
        if bid_b.startswith("bul_ibm_") and bid_b not in cl_bullet_ids:
            bullets_missing_bundle_id.append(bid_b)

    return (
        bullets_missing_skill_ids,
        bundles_present,
        flat_only,
        pp_meta,
        bullets_missing_bundle_id,
        bullets_metric_unsupported,
    )


def _eval_ibm_scope_and_coverage(
    bullets: list[dict[str, Any]],
    parsed_output: dict[str, Any] | None,
    claim_ledger: list[dict[str, Any]],
    allowed_fact_ids: set[str],
    proof_pool_metadata: dict[str, Any] | None,
    expected_bullet_ids: tuple[str, ...],
) -> tuple[bool, set[str], str, str, str, bool, set[str], set[str], Any, str, str]:
    """Evaluate IBM fact scope, serialized unify leakage string, and 100% claim_ledger coverage."""
    from apps_rg.runtime.validators.proof_pool_source_fact_validation import (
        proof_source_from_metadata,
        scope_ids_membership_only,
    )

    source_ids = set(_all_source_fact_ids(parsed_output, claim_ledger))
    proof_source = proof_source_from_metadata(proof_pool_metadata)
    if proof_source in ("srfs", "broad_skills_ledger"):
        scope_ok, _, forbidden_hits, not_in_pool = scope_ids_membership_only(
            source_ids,
            allowed_fact_ids=set(allowed_fact_ids),
            forbidden_prefixes=("bul_unify_", "bul_insurtech_", "bul_ey_"),
        )
        scope_threshold = "active_proof_pool_membership"
        scope_fail = "Fact scope must match active IBM proof pool."
        if forbidden_hits or not_in_pool:
            scope_fail += f" forbidden={forbidden_hits} out_of_pool={not_in_pool}"
    else:
        scope_ok = bool(source_ids) and all(str(sid).startswith("bul_ibm_") for sid in source_ids)
        scope_ok = scope_ok and all(
            sid.split("_metric_")[0] in allowed_fact_ids or sid in allowed_fact_ids for sid in source_ids
        )
        scope_threshold = "bul_ibm_*"
        scope_fail = "Fact scope must be IBM bullets only."

    serialized = json.dumps(
        {k: v for k, v in (parsed_output or {}).items() if k != "self_check"},
        sort_keys=True,
    ).lower()

    output_ids = {str(b.get("bullet_id")) for b in bullets if b.get("bullet_id")}
    ledger_roots: set[str] = set()
    for claim in claim_ledger:
        for fid in claim.get("source_fact_ids") or []:
            ledger_roots.add(str(fid).split("_metric_")[0])
    if proof_source in ("srfs", "broad_skills_ledger"):
        allowed_bases = {str(x).split("_metric_")[0] for x in allowed_fact_ids} | set(allowed_fact_ids)
        coverage_ok = (
            bool(output_ids)
            and all(bid in allowed_bases for bid in output_ids)
            and all(rid in allowed_bases for rid in ledger_roots)
            and len(claim_ledger) >= len(output_ids)
        )
        coverage_threshold: Any = "active_pool_bullet_ids"
        coverage_msg = "Every output bullet_id and ledger root must be in active proof pool."
    else:
        required_bullet_ids = set(expected_bullet_ids)
        coverage_ok = required_bullet_ids <= output_ids and required_bullet_ids <= ledger_roots
        coverage_threshold = sorted(required_bullet_ids)
        coverage_msg = "Every bul_ibm_* bullet must appear in output and claim_ledger."

    return (
        scope_ok,
        source_ids,
        scope_threshold,
        scope_fail,
        serialized,
        coverage_ok,
        output_ids,
        ledger_roots,
        coverage_threshold,
        coverage_msg,
    )


def _eval_blocked_judge_schemas(x1d_judges: list[dict[str, Any]]) -> list[Any]:
    """Return provider keys whose BLOCKED judge row fails X1D schema validation."""
    blocked_invalid: list[Any] = []
    for judge in x1d_judges:
        if str(judge.get("evaluator_mode", "")).startswith("BLOCKED_"):
            schema_ok, _ = check_judge_schema_valid(judge)
            if not schema_ok:
                blocked_invalid.append(judge.get("provider_key"))
    return blocked_invalid


__all__ = [
    "_eval_blocked_judge_schemas",
    "_eval_hold_metrics",
    "_eval_ibm_scope_and_coverage",
    "_eval_ledger_claim_text",
    "_eval_skill_ids_and_bundles",
    "_resolve_ibm_proof_context",
    "_resolve_plan_facts_for_anchors",
]
