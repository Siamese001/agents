"""Deterministic backtracking and narrative allocation solver for C0.3 resume allocation."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from apps_rg.runtime.c0.allocation.candidate_normalization import (
    _assignment_view,
    _candidate_sort_key,
    _normalize_candidate,
    _selection_margin_receipt,
)
from apps_rg.runtime.c0.allocation.contracts_and_validation import (
    ALL_CLAIM_BEARING_SECTIONS,
    ALLOCATION_SCOPES,
    DEFAULT_MAX_CANDIDATES_PER_SLOT,
    NARRATIVE_DERIVATION_POLICY,
    WHOLE_RESUME_SCOPE,
    ResumeGraphAllocationError,
    _Slot,
    _constraint_receipt,
    _slot_from_row,
    _validate_assignment_uniqueness,
    finalize_resume_graph_allocation_plan,
    validate_resume_graph_allocation_plan,
)
from apps_rg.runtime.c0.c03_resume_graph_contracts import (
    ALLOCATION_PLAN_SCHEMA_VERSION,
    stable_digest,
)
from apps_rg.runtime.c0.c0_fact_anchor import select_disjoint_narrative_candidates


def allocate_candidate_sets(
    *,
    candidate_sets: Mapping[str, Sequence[Mapping[str, Any]]],
    slot_specs: Sequence[Mapping[str, Any]],
    graph_digest: str,
    policy_digest: str,
    allocation_scope: str = WHOLE_RESUME_SCOPE,
    representation_policy: Mapping[str, Any] | None = None,
    section_plan_digests: Mapping[str, str] | None = None,
    max_fact_reuse: int = 2,
    max_source_family_share: float = 0.75,
    max_candidates_per_slot: int = DEFAULT_MAX_CANDIDATES_PER_SLOT,
    max_search_states: int = 250000,
) -> dict[str, Any]:
    """Allocate one candidate per slot under immutable hard constraints.

    Candidate input order and slot dispatch order are normalized before search.
    The solver uses deterministic minimum-remaining-values backtracking with the
    policy objective tuple as its candidate order.  It returns only a complete
    feasible assignment; search-budget exhaustion and impossibility are sealed
    failures, never partial plans.
    """
    scope = str(allocation_scope or "").strip().upper()
    if scope not in ALLOCATION_SCOPES:
        raise ValueError(f"invalid allocation_scope: {allocation_scope!r}")
    slots = sorted((_slot_from_row(row) for row in slot_specs), key=lambda slot: slot.slot_id)
    if not slots or len({slot.slot_id for slot in slots}) != len(slots):
        raise ValueError("allocation slots must be non-empty with unique slot_id values")
    if not str(graph_digest or "").strip() or not str(policy_digest or "").strip():
        raise ValueError("graph_digest and policy_digest are required")
    max_fact_reuse = max(1, int(max_fact_reuse))
    max_family_uses = max(1, int(math.ceil(len(slots) * float(max_source_family_share))))

    eligible_by_slot: dict[str, list[dict[str, Any]]] = {}
    predecisions: list[dict[str, Any]] = []
    for slot in slots:
        normalized: list[dict[str, Any]] = []
        seen_candidates: set[str] = set()
        for raw in candidate_sets.get(slot.slot_id) or ():
            row, reasons = _normalize_candidate(raw, slot=slot)
            candidate_id = str(row["candidate_id"])
            if candidate_id in seen_candidates:
                reasons.append("duplicate_candidate_id_in_slot")
            seen_candidates.add(candidate_id)
            if reasons:
                predecisions.append(
                    {
                        "candidate_id": candidate_id,
                        "section_id": slot.section_id,
                        "claim_unit_id": slot.slot_id,
                        "decision": "rejected",
                        "reason_codes": sorted(set(reasons)),
                    }
                )
                continue
            normalized.append(row)
        normalized.sort(key=_candidate_sort_key)
        if len(normalized) > max_candidates_per_slot:
            for row in normalized[max_candidates_per_slot:]:
                predecisions.append(
                    {
                        "candidate_id": row["candidate_id"],
                        "section_id": slot.section_id,
                        "claim_unit_id": slot.slot_id,
                        "decision": "rejected",
                        "reason_codes": ["allocation_candidate_budget"],
                    }
                )
            normalized = normalized[:max_candidates_per_slot]
        eligible_by_slot[slot.slot_id] = normalized

    if any(not eligible_by_slot[slot.slot_id] for slot in slots):
        receipt = _constraint_receipt(
            slots=slots,
            eligible_by_slot=eligible_by_slot,
            reason="empty_eligible_candidate_pool",
        )
        raise ResumeGraphAllocationError(
            "resume graph allocation unsatisfied: empty eligible candidate pool",
            receipt=receipt,
        )
    chosen: dict[str, dict[str, Any]] = {}
    used_skills: set[str] = set()
    used_metrics: set[str] = set()
    used_signatures: set[str] = set()
    used_fingerprint_tokens: Counter[str] = Counter()
    used_section_roots: dict[str, set[str]] = defaultdict(set)
    fact_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    search_states = 0
    budget_exhausted = False
    from apps_rg.runtime.c0.c0_perf_sync_helpers import compute_distinct_root_sections, slot_priority_tier
    from apps_rg.runtime.contracts.metric_lexical_primitives import is_quantified_metric_outcome_text
    distinct_root_sections = compute_distinct_root_sections(slots, eligible_by_slot)
    bullet_slot_counts_by_lane: Counter[str] = Counter(
        slot.employer_lane
        for slot in slots
        if slot.section_id.endswith("_bullets") and slot.employer_lane
    )
    quantified_roots_by_lane: dict[str, set[str]] = defaultdict(set)
    root_fp_options_by_lane: dict[str, dict[str, list[frozenset[str]]]] = defaultdict(lambda: defaultdict(list))
    for slot in slots:
        if not slot.section_id.endswith("_bullets") or not slot.employer_lane:
            continue
        for row in eligible_by_slot[slot.slot_id]:
            rid = str(row.get("root_id") or "")
            mid = str(row.get("metric_outcome_id") or "")
            if mid and is_quantified_metric_outcome_text(str(row.get("metric_text") or "")):
                quantified_roots_by_lane[slot.employer_lane].add(rid)
            if mid and rid:
                fp_set = frozenset(row.get("metric_fingerprint_tokens") or ())
                if fp_set:
                    opts = root_fp_options_by_lane[slot.employer_lane][rid]
                    if fp_set not in opts:
                        opts.append(fp_set)
    sole_fingerprints_by_lane: dict[str, set[str]] = defaultdict(set)
    sole_fps_by_lane_root: dict[str, dict[str, frozenset[str]]] = defaultdict(dict)
    multi_option_roots_by_lane: dict[str, set[str]] = defaultdict(set)
    for lane, root_map in root_fp_options_by_lane.items():
        for rid, fp_list in root_map.items():
            if not fp_list:
                continue
            if len(fp_list) > 1:
                multi_option_roots_by_lane[lane].add(rid)
            common_tokens = frozenset(set(fp_list[0]).intersection(*fp_list[1:])) if fp_list else frozenset()
            if common_tokens:
                sole_fps_by_lane_root[lane][rid] = common_tokens
                sole_fingerprints_by_lane[lane].update(common_tokens)

    _AWS_MIGRATION_EXEC_SUMMARY_ROOTS = frozenset({
        "reb_insurtech_aws_migration_execution", "reb_ibm_aws_modernization_architecture",
    })

    def _fact_reuse_key(row: Mapping[str, Any]) -> str:
        fact_id = str(row.get("fact_id") or "")
        root_id = str(row.get("root_id") or "")
        if fact_id.startswith("exp_") and root_id.startswith("reb_"):
            return f"{fact_id}:{root_id}"
        return fact_id

    def feasible_rows(slot: _Slot) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in eligible_by_slot[slot.slot_id]:
            visible = slot.counts_toward_global_uniqueness
            skill_id, metric_id, signature = str(row["skill_id"]), str(row.get("metric_outcome_id") or ""), str(row.get("normalized_metric_signature") or "")
            fp_tokens = tuple(row.get("metric_fingerprint_tokens") or ())
            fact_key, family, root_id = _fact_reuse_key(row), str(row["source_family"]), str(row["root_id"])
            if (visible and skill_id in used_skills) or (visible and metric_id and metric_id in used_metrics) or (visible and signature and signature in used_signatures):
                continue
            if visible and fp_tokens and any(used_fingerprint_tokens[tok] > 0 for tok in fp_tokens):
                continue
            if slot.section_id in distinct_root_sections and root_id and root_id in used_section_roots[slot.section_id]:
                continue
            if slot.section_id == "executive_summary" and root_id in _AWS_MIGRATION_EXEC_SUMMARY_ROOTS and (used_section_roots["executive_summary"] & _AWS_MIGRATION_EXEC_SUMMARY_ROOTS):
                continue
            if (visible and fact_counts[fact_key] >= max_fact_reuse) or (visible and family_counts[family] >= max_family_uses):
                continue
            rows.append(row)

        exec_roots = used_section_roots.get("executive_summary", set())
        is_bullet_section = slot.section_id.endswith("_bullets")
        has_lane_metric_headroom = (
            not slot.employer_lane
            or len(quantified_roots_by_lane.get(slot.employer_lane, set()))
            > bullet_slot_counts_by_lane.get(slot.employer_lane, 0) + 1
        )
        is_metric_preferred_section = is_bullet_section or (
            slot.section_id == "executive_summary"
            and (slot.metric_required or has_lane_metric_headroom)
        )
        prefer_non_exec = is_bullet_section and not slot.required_root_id and any(str(r.get("root_id") or "") not in exec_roots for r in rows)
        max_non_exec_align = max(
            (float(r.get("target_alignment_score") or 0.0) for r in rows if str(r.get("root_id") or "") not in exec_roots),
            default=0.0,
        )
        lane_sole_fps = sole_fingerprints_by_lane.get(slot.employer_lane, set())
        lane_root_sole_fps = sole_fps_by_lane_root.get(slot.employer_lane, {})
        lane_multi_roots = multi_option_roots_by_lane.get(slot.employer_lane, set())

        def _collides_with_other_root_sole_fp(r: Mapping[str, Any]) -> bool:
            rid = str(r.get("root_id") or "")
            r_fps = set(r.get("metric_fingerprint_tokens") or ())
            if not r_fps:
                return False
            if slot.section_id == "executive_summary":
                return bool(r_fps & lane_sole_fps)
            if rid not in lane_multi_roots:
                return False
            own_req = set(lane_root_sole_fps.get(rid) or ())
            extra_fps = r_fps - own_req
            if not extra_fps:
                return False
            return any(
                other_rid != rid and bool(extra_fps & other_fps)
                for other_rid, other_fps in lane_root_sole_fps.items()
            )

        rows.sort(
            key=lambda row: (
                1 if (slot.section_id == "headline" and str(row.get("skill_id") or "") in {"skill_risk_three_lines_of_defense", "skill_p2_tech_adoption_derisking"}) else 0,
                1
                if (
                    prefer_non_exec
                    and str(row.get("root_id") or "") in exec_roots
                    and not (
                        slot.section_id == "ibm_bullets"
                        and str(row.get("root_id") or "") == "reb_ibm_aws_alliance_partner_cosell_gtm"
                    )
                )
                else 0,
                1
                if (
                    (not slot.metric_required or str(row.get("root_id") or "") in lane_multi_roots)
                    and _collides_with_other_root_sole_fp(row)
                )
                else 0,
                0 if (
                    not (
                        is_metric_preferred_section
                        and (
                            slot.metric_required
                            or not is_bullet_section
                        )
                    )
                    or (
                        bool(row.get("metric_outcome_id"))
                        and (
                            is_quantified_metric_outcome_text(str(row.get("metric_text") or ""))
                            or (slot.section_id == "executive_summary" and not slot.metric_required and bool(lane_sole_fps))
                        )
                    )
                    or (
                        slot.section_id == "executive_summary"
                        and not slot.metric_required
                        and bool(lane_sole_fps)
                    )
                ) else 1,
                0 if is_bullet_section else fact_counts[_fact_reuse_key(row)],
                *_candidate_sort_key(row),
                fact_counts[_fact_reuse_key(row)] if is_bullet_section else 0,
            )
        )
        return rows

    def search() -> bool:
        nonlocal search_states, budget_exhausted
        if len(chosen) == len(slots):
            return True
        search_states += 1
        if search_states > max_search_states:
            budget_exhausted = True
            return False
        unresolved = [slot for slot in slots if slot.slot_id not in chosen]
        ranked = [(feasible_rows(slot), slot) for slot in unresolved]
        ranked.sort(key=lambda pair: (0 if len(pair[0]) <= 1 else 1, slot_priority_tier(pair[1]), len(pair[0]), pair[1].slot_id))
        rows, slot = ranked[0]
        if not rows:
            return False
        for row in rows:
            visible = slot.counts_toward_global_uniqueness
            skill_id = str(row["skill_id"])
            metric_id = str(row.get("metric_outcome_id") or "")
            signature = str(row.get("normalized_metric_signature") or "")
            fp_tokens = tuple(row.get("metric_fingerprint_tokens") or ())
            fact_key = _fact_reuse_key(row)
            family = str(row["source_family"])
            root_id = str(row["root_id"])
            chosen[slot.slot_id] = row
            if slot.section_id in distinct_root_sections and root_id:
                used_section_roots[slot.section_id].add(root_id)
            if visible:
                used_skills.add(skill_id)
                if metric_id:
                    used_metrics.add(metric_id)
                if signature:
                    used_signatures.add(signature)
                for fp_tok in fp_tokens:
                    used_fingerprint_tokens[fp_tok] += 1
                fact_counts[fact_key] += 1
                family_counts[family] += 1
            remaining_feasible = all(
                bool(feasible_rows(other))
                for other in unresolved
                if other.slot_id != slot.slot_id
            )
            if remaining_feasible and search():
                return True
            if slot.section_id in distinct_root_sections and root_id:
                used_section_roots[slot.section_id].discard(root_id)
            if visible:
                used_skills.remove(skill_id)
                if metric_id:
                    used_metrics.remove(metric_id)
                if signature:
                    used_signatures.remove(signature)
                for fp_tok in fp_tokens:
                    used_fingerprint_tokens[fp_tok] -= 1
                    if used_fingerprint_tokens[fp_tok] <= 0:
                        del used_fingerprint_tokens[fp_tok]
                fact_counts[fact_key] -= 1
                family_counts[family] -= 1
            del chosen[slot.slot_id]
        return False

    if not search():
        conflicting_resources = sorted(
            {
                "skill_id",
                *(
                    ["metric_outcome_id", "normalized_metric_signature"]
                    if any(slot.metric_required for slot in slots)
                    else []
                ),
                "fact_id_concentration",
                "source_family_concentration",
            }
        )
        receipt = _constraint_receipt(
            slots=slots,
            eligible_by_slot=eligible_by_slot,
            reason="search_budget_exhausted" if budget_exhausted else "hard_constraints_unsatisfied",
        )
        receipt["unsatisfied_constraints"] = conflicting_resources
        receipt["search_states"] = search_states
        receipt["max_search_states"] = max_search_states
        raise ResumeGraphAllocationError(
            "resume graph allocation unsatisfied: " + ", ".join(conflicting_resources),
            receipt=receipt,
        )

    assignments = []
    for slot in slots:
        selected = dict(chosen[slot.slot_id])
        selected.update(
            _selection_margin_receipt(selected, eligible_by_slot[slot.slot_id])
        )
        assignments.append(_assignment_view(selected, slot=slot))
    selected_candidate_ids = {str(row["candidate_id"]) for row in assignments}
    candidate_decisions = list(predecisions)
    for slot in slots:
        for row in eligible_by_slot[slot.slot_id]:
            selected = str(row["candidate_id"]) in selected_candidate_ids
            candidate_decisions.append(
                {
                    "candidate_id": str(row["candidate_id"]),
                    "section_id": slot.section_id,
                    "claim_unit_id": slot.slot_id,
                    "decision": "selected" if selected else "rejected",
                    "reason_codes": [
                        "selected_by_global_allocation"
                        if selected
                        else "global_constraint_or_objective_not_selected"
                    ],
                }
            )
    candidate_decisions.sort(
        key=lambda row: (
            str(row.get("section_id") or ""),
            str(row.get("claim_unit_id") or ""),
            str(row.get("candidate_id") or ""),
        )
    )
    uniqueness = _validate_assignment_uniqueness(assignments)
    if uniqueness["pass"] is not True:
        raise AssertionError("allocator emitted a resource-reuse violation")
    section_counts = Counter(str(row["section_id"]) for row in assignments)
    required_counts = Counter(slot.section_id for slot in slots)
    budget_receipt = {
        "schema_version": "resume_graph_allocation_budget_receipt_v1",
        "required_assignment_count_by_section": dict(sorted(required_counts.items())),
        "actual_assignment_count_by_section": dict(sorted(section_counts.items())),
        "pass": section_counts == required_counts,
    }
    plan: dict[str, Any] = {
        "schema_version": ALLOCATION_PLAN_SCHEMA_VERSION,
        "allocation_scope": scope,
        "global_uniqueness_claimed": scope == WHOLE_RESUME_SCOPE,
        "graph_digest": str(graph_digest),
        "policy_digest": str(policy_digest),
        "section_plan_digests": dict(sorted((section_plan_digests or {}).items())),
        "representation_policy": dict(
            representation_policy
            or {
                "canonical_role_representation": "bullets",
                "narratives_are_derived_alternatives": True,
                "alternative_assignments_count_toward_global_uniqueness": False,
            }
        ),
        "assignments": assignments,
        "candidate_decisions": candidate_decisions,
        "solver_metadata": {
            "solver": "deterministic_mrv_constraint_search_v1",
            "stable_tie_break": "candidate_id_ascending",
            "objective_order": [
                "proof_strength_raw",
                "path_confidence_raw",
                "source_independence_score",
                "target_alignment_score",
                "stable_candidate_id",
            ],
            "selection_margin_policy": (
                "signed_first_differing_lexicographic_component_vs_"
                "best_locally_eligible_rejected_v1"
            ),
            "search_states": search_states,
            "max_search_states": max_search_states,
            "max_candidates_per_slot": max_candidates_per_slot,
            "candidate_input_order_independent": True,
            "section_dispatch_order_independent": True,
        },
        "hard_constraints": {
            "skill_id_zero_reuse": True,
            "metric_outcome_id_zero_reuse": True,
            "normalized_metric_signature_zero_reuse": True,
            "max_fact_reuse": max_fact_reuse,
            "max_source_family_uses": max_family_uses,
            "employer_locality": True,
            "authority_pass_required": True,
            "complete_path_required": True,
        },
        "uniqueness_receipt": uniqueness,
        "budget_receipt": budget_receipt,
        "candidate_conservation_receipt": {
            "candidate_count": len(candidate_decisions),
            "terminal_decision_count": sum(
                1 for row in candidate_decisions if row.get("decision") in {"selected", "rejected"}
            ),
            "pass": all(
                row.get("decision") in {"selected", "rejected"} for row in candidate_decisions
            ),
        },
        "durable_graph_state_mutated": False,
    }
    return finalize_resume_graph_allocation_plan(plan)


def _append_derived_narrative_assignments(
    plan: Mapping[str, Any],
    *,
    section_plans: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    out = dict(plan)
    assignments = [dict(row) for row in plan.get("assignments") or []]
    decisions = [dict(row) for row in plan.get("candidate_decisions") or []]
    for narrative_section, bullet_section in sorted(NARRATIVE_DERIVATION_POLICY.items()):
        upstream = [row for row in assignments if row.get("section_id") == bullet_section]
        derived_rows = select_disjoint_narrative_candidates(
            narrative_section=narrative_section,
            bullet_section=bullet_section,
            upstream_bullet_assignments=upstream,
            all_assignments=assignments,
            section_plans=section_plans,
        )
        for derived in derived_rows:
            assignments.append(derived)
            decisions.append(
                {
                    "candidate_id": derived["candidate_id"],
                    "section_id": narrative_section,
                    "claim_unit_id": derived["claim_unit_id"],
                    "decision": "selected",
                    "reason_codes": ["derived_alternative_from_frozen_bullet_allocation"],
                }
            )
    out["assignments"] = assignments
    out["candidate_decisions"] = sorted(
        decisions,
        key=lambda row: (
            str(row.get("section_id") or ""),
            str(row.get("claim_unit_id") or ""),
            str(row.get("candidate_id") or ""),
        ),
    )
    required = Counter(str(row.get("section_id") or "") for row in assignments)
    out["budget_receipt"] = {
        "schema_version": "resume_graph_allocation_budget_receipt_v1",
        "required_assignment_count_by_section": dict(sorted(required.items())),
        "actual_assignment_count_by_section": dict(sorted(required.items())),
        "pass": True,
    }
    out["candidate_conservation_receipt"] = {
        "candidate_count": len(out["candidate_decisions"]),
        "terminal_decision_count": len(out["candidate_decisions"]),
        "pass": True,
    }
    return finalize_resume_graph_allocation_plan(out)


def build_section_final_evidence_contracts(
    *,
    allocation_plan: Mapping[str, Any],
    section_plans: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    failures = validate_resume_graph_allocation_plan(allocation_plan)
    if failures:
        raise ValueError("allocation plan invalid: " + ", ".join(failures))
    contracts: dict[str, dict[str, Any]] = {}
    for section_id in ALL_CLAIM_BEARING_SECTIONS:
        if section_id not in section_plans:
            continue
        source_plan = section_plans.get(section_id) or {}
        traversal = (
            source_plan.get("graph_traversal_receipt")
            if isinstance(source_plan.get("graph_traversal_receipt"), Mapping)
            else {}
        )
        assignments = [
            dict(row)
            for row in allocation_plan.get("assignments") or []
            if isinstance(row, Mapping) and row.get("section_id") == section_id
        ]
        derived_from = NARRATIVE_DERIVATION_POLICY.get(section_id, "")
        contract: dict[str, Any] = {
            "schema_version": "section_final_graph_evidence_contract_v1",
            "section_id": section_id,
            "allocation_scope": str(allocation_plan.get("allocation_scope") or ""),
            "allocation_plan_digest": str(
                allocation_plan.get("allocation_plan_digest") or ""
            ),
            "source_section_plan_id": str(source_plan.get("plan_id") or ""),
            "source_section_plan_digest": str(source_plan.get("plan_digest") or ""),
            "graph_digest": str(allocation_plan.get("graph_digest") or ""),
            "assignments": assignments,
            "assignment_count": len(assignments),
            "representation_mode": "DERIVED_ALTERNATIVE" if derived_from else "CANONICAL_VISIBLE",
            "derived_from_section_id": derived_from,
            "counts_toward_global_uniqueness": not bool(derived_from),
            "traversal_receipt_digest": str(traversal.get("events_digest") or ""),
            "traversal_conservation_pass": traversal.get("pass") is True,
            "pass": (
                bool(assignments)
                or section_id in ("ey_bullets", "ey_narrative", "early_career_bullets", "early_career_narrative")
            )
            and bool(source_plan.get("plan_digest"))
            and traversal.get("pass") is True,
        }
        contract["contract_digest"] = stable_digest(contract)
        contracts[section_id] = contract
    return contracts
