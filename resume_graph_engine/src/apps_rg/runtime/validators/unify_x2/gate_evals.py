"""Deterministic gate-evaluation helpers for ``run_unify_bullets_x2_gates``."""
from __future__ import annotations

import json
from typing import Any

from apps_rg.runtime.validators.executive_summary_x2 import (
    check_claim_ledger_claim_text_non_empty,
    check_judge_schema_valid,
)
from apps_rg.runtime.validators.unify_x2.constants import (
    FORBIDDEN_FACT_PREFIXES,
    UNIFY_BULLET_IDS,
    _metric_raw_values,
)
from apps_rg.runtime.validators.unify_x2.coverage_checks import _all_source_fact_ids


def _eval_unify_plan_and_archive_overlap(
    bullets: list[dict[str, Any]],
    po_raw: dict[str, Any],
    proof_pool_metadata: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[Any], str, list[str], list[str]]:
    """Extract Unify selected_fact_plan, ledger IDs, selection method, and archive overlap hits."""
    from apps_rg.runtime.sections.unify_bullets_graph_evidence import (
        max_consecutive_word_overlap,
    )

    plan_raw = (
        po_raw.get("selected_fact_plan")
        if isinstance(po_raw.get("selected_fact_plan"), dict)
        else {}
    )
    selection_method = str(plan_raw.get("selection_method") or "")
    if isinstance(proof_pool_metadata, dict):
        selection_method = selection_method or str(
            proof_pool_metadata.get("selection_method") or ""
        )

    plan_facts = list(plan_raw.get("facts") or [])
    pick_order = plan_raw.get("ledger_pick_order")
    if isinstance(pick_order, list) and pick_order:
        ledger_ids = [str(x).strip() for x in pick_order if str(x).strip()]
    else:
        ledger_ids = [
            str(f.get("ledger_candidate_fact_id") or f.get("candidate_fact_id") or "").strip()
            for f in plan_facts
            if isinstance(f, dict)
        ]
        ledger_ids = [x for x in ledger_ids if x]

    archive_hits: list[str] = []
    claim_by_slot = {
        str(f.get("fact_id") or ""): str(f.get("claim_text") or "")
        for f in plan_facts
        if isinstance(f, dict) and str(f.get("fact_id") or "").startswith("bul_unify_")
    }
    for bullet in bullets:
        if not isinstance(bullet, dict):
            continue
        bid = str(bullet.get("bullet_id") or "")
        archive = claim_by_slot.get(bid, "")
        text = str(bullet.get("bullet_text") or "")
        if archive and max_consecutive_word_overlap(archive, text) >= 8:
            archive_hits.append(bid)

    return plan_raw, plan_facts, selection_method, ledger_ids, archive_hits


def _eval_unify_ledger_claim_text(
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


def _eval_unify_scope_and_leakage(
    bullets: list[dict[str, Any]],
    parsed_output: dict[str, Any] | None,
    po_raw: dict[str, Any],
    claim_ledger: list[dict[str, Any]],
    allowed_fact_ids: set[str],
    proof_pool_metadata: dict[str, Any] | None,
    plan_raw: dict[str, Any],
    plan_facts: list[Any],
) -> tuple[bool, set[str], str, str, str, bool, set[str], set[str], Any, str, bool]:
    """Evaluate Unify fact scope, serialized leakage JSON, 100% ledger coverage, and granularity."""
    from apps_rg.runtime.validators.proof_pool_source_fact_validation import (
        proof_source_from_metadata,
        scope_ids_membership_only,
    )

    source_ids = set(_all_source_fact_ids(parsed_output, claim_ledger))
    proof_source = proof_source_from_metadata(proof_pool_metadata)
    bound_source_fact_ids = {
        str(fact.get("candidate_fact_id") or "").strip()
        for fact in plan_facts
        if isinstance(fact, dict)
        and str(fact.get("fact_id") or "").startswith("bul_unify_")
        and str(fact.get("candidate_fact_id") or "").strip()
    }
    bound_visible_fact_ids = {
        str(fact.get("fact_id") or "").split("_metric_")[0]
        for fact in plan_facts
        if isinstance(fact, dict)
        and str(fact.get("fact_id") or "").startswith("bul_unify_")
    }
    if proof_source in ("srfs", "broad_skills_ledger"):
        scope_ok, illegal_prefix_ids, forbidden_hits, not_in_allowlist = scope_ids_membership_only(
            source_ids,
            allowed_fact_ids=set(allowed_fact_ids),
            forbidden_prefixes=FORBIDDEN_FACT_PREFIXES,
        )
        scope_threshold = "active_proof_pool_membership"
    else:
        illegal_prefix_ids = sorted(
            {
                str(s)
                for s in source_ids
                if not (
                    str(s).split("_metric_")[0] in bound_visible_fact_ids
                    or str(s) in bound_source_fact_ids
                )
            }
        )
        forbidden_hits = sorted(
            {str(s) for s in source_ids if any(str(s).startswith(prefix) for prefix in FORBIDDEN_FACT_PREFIXES)}
        )
        not_in_allowlist = sorted(
            {
                str(s)
                for s in source_ids
                if str(s) not in allowed_fact_ids
                and str(s).split("_metric_")[0] not in allowed_fact_ids
            }
        )
        scope_ok = bool(source_ids) and not illegal_prefix_ids and not forbidden_hits and not not_in_allowlist
        scope_threshold = "slot-bound bul_unify_* or its exact graph source fact"
    scope_parts: list[str] = []
    if illegal_prefix_ids:
        scope_parts.append(f"tokens_not_slot_bound_unify_evidence={illegal_prefix_ids}")
    if forbidden_hits:
        scope_parts.append(f"forbidden_cross_lane_tokens={forbidden_hits}")
    if not_in_allowlist:
        scope_parts.append(f"tokens_not_in_allowed_fact_pool={not_in_allowlist}")
    scope_failure = (
        "Fact scope must match active proof pool."
        + (f" ({'; '.join(scope_parts)})" if scope_parts else "")
    )

    section_plan_for_leakage = {
        "section_id": plan_raw.get("section_id"),
        "selection_method": plan_raw.get("selection_method"),
        "facts": plan_facts,
        "required_fact_ids": plan_raw.get("required_fact_ids"),
        "allowed_graph_evidence_ids": plan_raw.get("allowed_graph_evidence_ids"),
        "selected_skill_ids": plan_raw.get("selected_skill_ids"),
        "selected_metrics": plan_raw.get("selected_metrics"),
    }
    scan_doc = {
        "bullets": po_raw.get("bullets"),
        "claim_ledger": claim_ledger,
        "change_log": po_raw.get("change_log"),
        "jd_alignment": po_raw.get("jd_alignment"),
        "selected_fact_plan": section_plan_for_leakage,
    }
    serialized = json.dumps(scan_doc, sort_keys=True).lower()

    output_ids = {str(b.get("bullet_id")) for b in bullets if b.get("bullet_id")}
    ledger_roots: set[str] = set()
    for claim in claim_ledger:
        for fid in claim.get("source_fact_ids") or []:
            ledger_roots.add(str(fid).split("_metric_")[0])
    if proof_source in ("srfs", "broad_skills_ledger"):
        pool_bullet_ids = {str(x) for x in allowed_fact_ids if str(x).startswith("bul_unify_")}
        coverage_ok = output_ids <= set(allowed_fact_ids) | pool_bullet_ids and bool(output_ids)
        coverage_ok = (
            coverage_ok
            and all(
                any(rid in allowed_fact_ids or rid.split("_metric_")[0] in allowed_fact_ids for rid in ledger_roots)
                for rid in ledger_roots
            )
            if ledger_roots
            else coverage_ok
        )
        coverage_threshold: Any = "active_pool_bullet_ids"
        coverage_msg = "Every output bullet_id and ledger root must be in active proof pool."
    else:
        required_bullet_ids = set(UNIFY_BULLET_IDS)
        coverage_ok = required_bullet_ids <= output_ids and required_bullet_ids <= ledger_roots
        coverage_threshold = sorted(required_bullet_ids)
        coverage_msg = "Every bul_unify_* bullet must appear in output and claim_ledger."

    metric_granular_ok = True
    for claim in claim_ledger:
        text = str(claim.get("claim_text", "")).lower()
        ids = claim.get("source_fact_ids") or []
        if "$22m" in text or "margin" in text:
            metric_granular_ok = metric_granular_ok and any(
                ("bul_unify_006" in str(i) or "fact_engineering_platform_006" in str(i))
                for i in ids
            )
        if "six months" in text or "three weeks" in text:
            metric_granular_ok = metric_granular_ok and any(
                ("bul_unify_004" in str(i) or "fact_engineering_platform_004" in str(i))
                for i in ids
            )

    return (
        scope_ok,
        source_ids,
        scope_threshold,
        scope_failure,
        serialized,
        coverage_ok,
        output_ids,
        ledger_roots,
        coverage_threshold,
        coverage_msg,
        metric_granular_ok,
    )


def _eval_unify_skill_ids_and_metric_source(
    bullets: list[dict[str, Any]],
    po_raw: dict[str, Any],
    plan_raw: dict[str, Any],
    proof_pool_metadata: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """Validate change_log skill IDs and metric_raw provenance against plan facts or pool outcomes."""
    po_change_log = list(po_raw.get("change_log") or [])
    bullets_missing_skill_ids: list[str] = []
    cl_bullet_ids: set[str] = set()
    for cl_entry in po_change_log:
        if not isinstance(cl_entry, dict):
            continue
        bid_cl = str(cl_entry.get("bullet_id") or "")
        if not bid_cl.startswith("bul_unify_"):
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
        if bid_b.startswith("bul_unify_") and bid_b not in cl_bullet_ids:
            bullets_missing_skill_ids.append(bid_b)

    plan_facts_unify = list(plan_raw.get("facts") or [])
    plan_facts_by_bid_u: dict[str, dict[str, Any]] = {
        str(f.get("fact_id") or ""): f
        for f in plan_facts_unify
        if isinstance(f, dict)
    }
    bullets_metric_unsupported_u: list[str] = []
    for b in bullets:
        bid_mu = str(b.get("bullet_id") or "")
        if not bid_mu.startswith("bul_unify_"):
            continue
        if not b.get("has_metric"):
            continue
        mr_raw = b.get("metric_raw")
        mr_tokens = _metric_raw_values(mr_raw)
        mr_u = ", ".join(mr_tokens)
        if not mr_tokens:
            bullets_metric_unsupported_u.append(f"{bid_mu}:metric_raw_empty")
            continue
        mr_u_lower = mr_u.lower()
        plan_fact_metric_u = str(
            (plan_facts_by_bid_u.get(bid_mu) or {}).get("metric_raw") or ""
        ).lower()
        metric_supported = bool(plan_fact_metric_u) and (
            plan_fact_metric_u in mr_u_lower or mr_u_lower in plan_fact_metric_u
        )
        approved_metric_ids = {
            str(x).strip().lower()
            for x in (
                (proof_pool_metadata or {}).get("approved_metric_outcome_ids") or []
            )
            if str(x).strip()
        }
        metric_supported = metric_supported or (
            bool(mr_tokens)
            and bool(approved_metric_ids)
            and all(t in approved_metric_ids for t in mr_tokens)
        )
        if not metric_supported:
            bullets_metric_unsupported_u.append(
                f"{bid_mu}:metric_raw={mr_raw!r}_not_in_proof_bundle"
            )
    return bullets_missing_skill_ids, bullets_metric_unsupported_u


def _eval_unify_blocked_judges(x1d_judges: list[dict[str, Any]]) -> list[Any]:
    """Return provider keys whose BLOCKED judge row fails X1D schema validation."""
    blocked_invalid: list[Any] = []
    for judge in x1d_judges:
        if str(judge.get("evaluator_mode", "")).startswith("BLOCKED_"):
            schema_ok, _ = check_judge_schema_valid(judge)
            if not schema_ok:
                blocked_invalid.append(judge.get("provider_key"))
    return blocked_invalid


__all__ = [
    "_eval_unify_blocked_judges",
    "_eval_unify_ledger_claim_text",
    "_eval_unify_plan_and_archive_overlap",
    "_eval_unify_scope_and_leakage",
    "_eval_unify_skill_ids_and_metric_source",
]
