"""Slot spec derivation, candidate set generation, and embedding candidate binding."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from apps_rg.runtime.contracts.metric_lexical_primitives import HOLD_METRIC_TEXT_RE
from apps_rg.runtime.c0.allocation.candidate_normalization import _candidate_sort_key
from apps_rg.runtime.c0.allocation.contracts_and_validation import (
    ALL_CLAIM_BEARING_SECTIONS,
    CANONICAL_BULLET_CLAIM_UNITS,
    CANONICAL_VISIBLE_SECTIONS,
    EMPLOYER_LANE_BY_SECTION,
    ResumeGraphAllocationError,
    _slot_from_row,
    _strings,
    extract_exact_metric_value_unit,
    finalize_resume_graph_allocation_plan,
    normalize_metric_signature,
    stable_digest,
    stable_edge_id,
)


def _authority_rows_by_root(
    section_plan: Mapping[str, Any],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for raw in section_plan.get("graph_candidate_decision_ledger") or []:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        root_id = str(row.get("root_id") or row.get("candidate_id") or "").strip()
        if not root_id:
            continue
        candidate_type = str(row.get("candidate_type") or "")
        bucket = grouped.setdefault(
            root_id,
            {"root": [], "leaf_skill": [], "source_fact": [], "metric_outcome": []},
        )
        bucket_key = "root" if candidate_type == "role_episode_root" else candidate_type
        if bucket_key in bucket:
            bucket[bucket_key].append(row)
    for bucket in grouped.values():
        for rows in bucket.values():
            rows.sort(key=lambda row: str(row.get("candidate_path_id") or ""))
    return grouped


def _default_slot_specs(
    section_plans: Mapping[str, Mapping[str, Any]],
    *,
    mandate_route: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for index in range(1, 9):
        slots.append(
            {
                "slot_id": f"competencies:skill:{index:02d}",
                "section_id": "competencies",
                "metric_required": False,
            }
        )
    exec_plan = section_plans.get("executive_summary") or {}
    route = (
        dict(mandate_route)
        if isinstance(mandate_route, Mapping)
        else dict(exec_plan.get("mandate_route") or {})
    )
    slot_budget_profile = dict(
        route.get("slot_budget_profile")
        or exec_plan.get("slot_budget_profile")
        or {}
    )
    unify_slot_roots = section_plans.get("unify_bullets", {}).get("unify_bullet_slot_bundle_map_resolved")
    if not isinstance(unify_slot_roots, Mapping) or set(unify_slot_roots) != set(CANONICAL_BULLET_CLAIM_UNITS["unify_bullets"]):
        raise ResumeGraphAllocationError(
            "unify_bullets: frozen source plan lacks the complete slot-to-role-episode contract",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["unify_slot_role_episode_contract"],
                "observed_slot_ids": sorted(unify_slot_roots) if isinstance(unify_slot_roots, Mapping) else [],
            },
        )
    if any(not str(root_id).strip() for root_id in unify_slot_roots.values()):
        raise ResumeGraphAllocationError(
            "unify_bullets: slot-to-role-episode contract contains an empty root",
            receipt={"schema_version": "resume_graph_allocation_failure_v1", "unsatisfied_constraints": ["unify_slot_role_episode_contract"]},
        )
    for section_id, all_claim_units in CANONICAL_BULLET_CLAIM_UNITS.items():
        if section_id not in section_plans or not all_claim_units:
            continue
        section_roots_map = _authority_rows_by_root(section_plans.get(section_id, {}))
        authorized_root_count = sum(
            1
            for bucket in section_roots_map.values()
            if any(r.get("authority_pass") is True for r in bucket["root"])
            and any(r.get("authority_pass") is True for r in bucket["leaf_skill"])
            and any(r.get("authority_pass") is True for r in bucket["source_fact"])
        )
        if authorized_root_count == 0:
            continue
        requested_count = slot_budget_profile.get(section_id)
        if requested_count is None:
            requested_count = (
                2 if section_id in {"insurtech_bullets", "ey_bullets"}
                else (1 if section_id == "early_career_bullets" else len(all_claim_units))
            )
        active_count = max(0, min(int(requested_count), len(all_claim_units), authorized_root_count))
        if active_count == 0:
            continue
        if section_id == "unify_bullets" and active_count < len(all_claim_units):
            # Keep numeric-outcome tail slots (bul_unify_005, bul_unify_006) prioritized alongside leading slots.
            tail_numeric = [cid for cid in ("bul_unify_005", "bul_unify_006") if cid in all_claim_units]
            head_slots = [cid for cid in all_claim_units if cid not in tail_numeric][: max(0, active_count - len(tail_numeric))]
            claim_units = tuple(sorted(head_slots + tail_numeric[:active_count]))
        else:
            claim_units = all_claim_units[:active_count]
        metric_available = any(
            extract_exact_metric_value_unit(str(row.get("metric") or ""))[0]
            for bucket in section_roots_map.values()
            for row in bucket["metric_outcome"]
            if row.get("authority_pass") is True
        )
        numeric_unify_roots_count = (
            sum(
                1
                for bucket in section_roots_map.values()
                if any(
                    extract_exact_metric_value_unit(str(row.get("metric") or ""))[0]
                    for row in bucket["metric_outcome"]
                    if row.get("authority_pass") is True
                )
            )
            if section_id == "unify_bullets"
            else 0
        )
        for index, claim_unit in enumerate(claim_units):
            unify_req_root = str(unify_slot_roots.get(claim_unit) or "").strip() if section_id == "unify_bullets" else ""
            unify_slot_numeric_eligible = (
                section_id == "unify_bullets"
                and (
                    (
                        bool(unify_req_root)
                        and any(
                            extract_exact_metric_value_unit(str(row.get("metric") or ""))[0]
                            for row in section_roots_map.get(unify_req_root, {}).get("metric_outcome", [])
                            if row.get("authority_pass") is True
                        )
                    )
                    or (claim_unit in ("bul_unify_005", "bul_unify_006") and numeric_unify_roots_count >= 2)
                )
            )
            slots.append(
                {
                    "slot_id": f"{section_id}:{claim_unit}",
                    "section_id": section_id,
                    "metric_required": (
                        metric_available
                        and (
                            (
                                index == 0
                                and section_id not in (
                                    "unify_bullets",
                                    "ibm_bullets",
                                    "slalom_bullets",
                                    "insurtech_bullets",
                                    "ey_bullets",
                                    "early_career_bullets",
                                )
                            )
                            or (section_id == "unify_bullets" and unify_slot_numeric_eligible)
                            or (section_id == "ibm_bullets" and index == len(claim_units) - 1)
                            or (section_id == "slalom_bullets" and index == min(2, len(claim_units) - 1))
                        )
                    ),
                    "metric_outcome_required": section_id == "unify_bullets",
                    "employer_lane": EMPLOYER_LANE_BY_SECTION[section_id],
                }
            )
    exec_profile = str(route.get("selector_profile") or exec_plan.get("target_role_profile") or "").strip()
    exec_grouped = _authority_rows_by_root(exec_plan)
    available_exec_lanes = {
        str(r.get("employer_lane") or "")
        for bucket in exec_grouped.values()
        for r in bucket["root"]
        if r.get("authority_pass") is True
        and any(s.get("authority_pass") is True for s in bucket["leaf_skill"])
        and any(f.get("authority_pass") is True for f in bucket["source_fact"])
    }
    track1_candidates_by_profile: dict[str, tuple[str, ...]] = {
        "insurance_it_strategy": ("insurtech", "ey", "early_career"),
        "insurance_agentic_ai": ("early_career", "ey", "insurtech"),
        "banking_model_risk_ai": ("ey", "early_career"),
        "healthcare_payer_data_ai": ("early_career", "ey"),
        "quant_risk_hpc": ("early_career", "ey"),
        "executive_agentic_transformation": ("ey", "early_career", "insurtech"),
        "ai_partnerships_gtm": ("early_career",),
        "svp_agentic_engineering": ("early_career",),
    }
    preferred_t1 = track1_candidates_by_profile.get(
        exec_profile, ("early_career", "ey", "insurtech")
    )
    available_t1 = tuple(lane for lane in preferred_t1 if lane in available_exec_lanes)
    for index, employer_lane in enumerate(("slalom", "unify", "ibm"), start=1):
        slots.append(
            {
                "slot_id": f"executive_summary:claim:{index:02d}",
                "section_id": "executive_summary",
                "metric_required": index == 1,
                "employer_lane": employer_lane,
            }
        )
    if available_t1:
        slots.append(
            {
                "slot_id": "executive_summary:claim:04",
                "section_id": "executive_summary",
                "metric_required": False,
                "employer_lane": "",
                "allowed_employer_lanes": available_t1,
            }
        )
    track_weights = dict(route.get("track_weights") or {})
    actuarial_weight = float(track_weights.get("track_actuarial_risk_derivatives") or 0.0)
    headline_grouped = _authority_rows_by_root(section_plans.get("headline") or {})
    available_headline_t1 = tuple(
        lane
        for lane in preferred_t1
        if any(
            str(r.get("employer_lane") or "") == lane and r.get("authority_pass") is True
            for bucket in headline_grouped.values()
            for r in bucket["root"]
            if any(s.get("authority_pass") is True for s in bucket["leaf_skill"])
            and any(f.get("authority_pass") is True for f in bucket["source_fact"])
        )
    )
    require_t1_headline_slot = bool(available_headline_t1) and (
        actuarial_weight >= 0.25
        or exec_profile in {
            "insurance_agentic_ai",
            "insurance_it_strategy",
            "banking_model_risk_ai",
            "healthcare_payer_data_ai",
            "quant_risk_hpc",
        }
    )
    for index in range(1, 4):
        headline_slot: dict[str, Any] = {
            "slot_id": f"headline:skill:{index:02d}",
            "section_id": "headline",
            "metric_required": False,
        }
        if index == 3 and require_t1_headline_slot:
            headline_slot["allowed_employer_lanes"] = available_headline_t1
        slots.append(headline_slot)
    return slots


def _candidate_sets_from_section_plans(
    section_plans: Mapping[str, Mapping[str, Any]],
    slot_specs: Sequence[Mapping[str, Any]],
    *,
    mandate_route: Mapping[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    from apps_rg.runtime.c0.c0_perf_sync_helpers import (
        compute_candidate_alignment_and_independence,
        compute_career_band_filter,
        diversify_slot_candidates,
    )

    out: dict[str, list[dict[str, Any]]] = {}
    grouped_by_section = {
        section_id: _authority_rows_by_root(plan)
        for section_id, plan in section_plans.items()
        if section_id in CANONICAL_VISIBLE_SECTIONS
    }
    for raw_slot in slot_specs:
        slot = _slot_from_row(raw_slot)
        sec_plan = section_plans.get(slot.section_id) or {}
        sec_profile = str(sec_plan.get("target_role_profile") or "")
        sec_reqs = set(sec_plan.get("canonical_jd_requirement_ids") or ())
        has_explicit_cosell = bool(sec_reqs & {"partner_cosell", "hyperscaler_alliance", "si_enablement", "partner_gtm"})
        route = (
            dict(mandate_route)
            if isinstance(mandate_route, Mapping)
            else dict(sec_plan.get("mandate_route") or {})
        )
        is_fde_only = bool(route.get("fde_context")) or ("forward_deployed_execution" in sec_reqs)
        requires_commercial = bool(route.get("requires_commercial_pairing"))
        employer_root_weights, employer_weights, enforce_career_band, primary_secondary_roots = compute_career_band_filter(
            section_id=slot.section_id, sec_plan=sec_plan, grouped_section_buckets=grouped_by_section[slot.section_id],
        )
        cosell_roots = {
            "reb_unify_partner_channel_cosell",
            "reb_unify_hyperscaler_joint_solution_architecture",
            "reb_slalom_ecosystem_accelerators",
            "reb_ibm_aws_alliance_partner_cosell_gtm",
        }
        non_cosell_root_count = sum(
            1
            for rid, bkt in grouped_by_section[slot.section_id].items()
            if rid not in cosell_roots
            and (not enforce_career_band or rid in primary_secondary_roots)
            and any(r.get("authority_pass") is True for r in bkt["root"])
            and any(r.get("authority_pass") is True for r in bkt["leaf_skill"])
            and any(r.get("authority_pass") is True for r in bkt["source_fact"])
        )
        sec_slot_count = sum(1 for rs in slot_specs if str(rs.get("section_id") or "") == slot.section_id)
        rows: list[dict[str, Any]] = []
        for root_id, bucket in grouped_by_section[slot.section_id].items():
            if (
                enforce_career_band
                and not slot.employer_lane
                and not slot.allowed_employer_lanes
                and root_id not in primary_secondary_roots
            ):
                continue
            if (
                is_fde_only
                and not has_explicit_cosell
                and not slot.required_root_id
                and root_id in cosell_roots
                and non_cosell_root_count >= sec_slot_count
            ):
                continue
            if (
                sec_profile in {"svp_agentic_engineering", "insurance_it_strategy"}
                and not has_explicit_cosell
                and not requires_commercial
                and not slot.required_root_id
                and root_id in cosell_roots
                and non_cosell_root_count >= sec_slot_count
            ):
                continue
            roots = [row for row in bucket["root"] if row.get("authority_pass") is True]
            skills = [row for row in bucket["leaf_skill"] if row.get("authority_pass") is True]
            facts = [row for row in bucket["source_fact"] if row.get("authority_pass") is True]
            metrics = [
                row
                for row in bucket["metric_outcome"]
                if row.get("authority_pass") is True
                and row.get("approved", True) is True
                and (
                    not row.get("section_eligibility")
                    or slot.section_id in {str(v).strip() for v in (row.get("section_eligibility") or []) if str(v).strip()}
                )
            ]
            if not roots or not skills or not facts:
                continue
            root = roots[0]
            employer_lane = str(root.get("employer_lane") or "")
            root_weight = float(employer_root_weights.get(root_id, employer_weights.get(employer_lane, 1.0)))
            if slot.employer_lane and employer_lane != slot.employer_lane:
                continue
            if slot.allowed_employer_lanes and employer_lane not in slot.allowed_employer_lanes:
                continue
            if slot.required_root_id and root_id != slot.required_root_id:
                continue
            metric_options: list[dict[str, Any] | None] = [None]
            if slot.metric_required or slot.metric_outcome_required:
                metric_options = []
                for metric in metrics:
                    metric_raw_text = str(metric.get("metric") or "")
                    if slot.section_id == "ibm_bullets" and HOLD_METRIC_TEXT_RE.search(metric_raw_text):
                        continue
                    value, unit = extract_exact_metric_value_unit(metric_raw_text)
                    if slot.metric_required and not (value and unit):
                        continue
                    metric_options.append({**metric, "metric_value": value, "metric_unit": unit})
                if not metric_options:
                    continue
            elif (
                (slot.section_id.endswith("_bullets") and slot.section_id != "insurtech_bullets")
                or slot.section_id == "executive_summary"
            ) and metrics:
                populated: list[dict[str, Any] | None] = []
                for metric in metrics:
                    metric_raw_text = str(metric.get("metric") or "")
                    if slot.section_id in {"ibm_bullets", "executive_summary"} and HOLD_METRIC_TEXT_RE.search(metric_raw_text):
                        continue
                    value, unit = extract_exact_metric_value_unit(metric_raw_text)
                    populated.append({**metric, "metric_value": value, "metric_unit": unit})
                if populated:
                    # Prefer bound graph metrics while preserving a low-scoring None fallback
                    # for minimal synthetic fixtures whose single metric is already claimed.
                    metric_options = [*populated, None]
            for skill in skills:
                for fact in facts:
                    for metric in metric_options:
                        skill_id = str(skill.get("candidate_id") or "")
                        fact_id = str(fact.get("candidate_id") or "")
                        metric_id = str((metric or {}).get("candidate_id") or "")
                        graph_path_ids = [
                            str(root.get("candidate_path_id") or f"root:{root_id}"),
                            str(skill.get("candidate_path_id") or ""),
                            str(fact.get("candidate_path_id") or ""),
                        ]
                        edge_ids = [
                            stable_edge_id(root_id, "role_episode_contains_skill", skill_id),
                            stable_edge_id(root_id, "role_episode_supported_by_fact", fact_id),
                        ]
                        if metric is not None:
                            graph_path_ids.append(str(metric.get("candidate_path_id") or ""))
                            edge_ids.append(stable_edge_id(root_id, "role_episode_has_metric_outcome", metric_id))
                        citation_refs = _strings(list(fact.get("source_refs") or []) + list((fact.get("authority") or {}).get("source_refs") or []) + [fact_id])
                        skill_sources = _strings(list(skill.get("source_refs") or []) + list((skill.get("authority") or {}).get("source_refs") or []))
                        metric_text = str((metric or {}).get("metric") or "")
                        proof_score, align_score, indep_score = compute_candidate_alignment_and_independence(
                            root=root, skill=skill, metric=metric, root_weight=root_weight,
                            citation_refs=citation_refs, skill_sources=skill_sources,
                            sec_plan=section_plans.get(slot.section_id) or {},
                        )
                        if (
                            slot.section_id == "ibm_bullets"
                            and metric_id == "metric_ibm_20pct_joint_revenue_growth"
                            and sec_profile in {"insurance_it_strategy", "ai_partnerships_gtm"}
                        ):
                            align_score = round(align_score + 0.5, 6)
                        candidate: dict[str, Any] = {
                            "section_id": slot.section_id, "claim_unit_id": slot.slot_id,
                            "skill_id": skill_id, "skill_label": str(skill.get("skill_label") or ""),
                            "fact_id": fact_id, "metric_outcome_id": metric_id,
                            "metric_text": metric_text, "metric_value": str((metric or {}).get("metric_value") or ""),
                            "metric_unit": str((metric or {}).get("metric_unit") or ""),
                            "normalized_metric_signature": normalize_metric_signature(metric_text),
                            "root_id": root_id, "employer_lane": employer_lane, "source_family": employer_lane,
                            "authority_pass": True, "proof_strength_raw": proof_score,
                            "target_alignment_score": align_score, "claim_entailment_score": 1.0,
                            "metric_binding_score": 1.0 if metric is not None else 0.0,
                            "path_confidence_raw": 1.0, "source_independence_score": indep_score,
                            "graph_path_ids": _strings(graph_path_ids), "edge_ids": edge_ids, "citation_refs": citation_refs,
                            "root_bundle_theme": str(root.get("bundle_theme") or ""),
                            "root_claim_text": str(root.get("claim_text") or ""),
                            "root_claim_action": str(root.get("claim_action") or ""),
                            "root_claim_scope": str(root.get("claim_scope") or ""),
                            "root_claim_outcome": str(root.get("claim_outcome") or ""),
                        }
                        candidate["candidate_id"] = "alloc-cand:" + stable_digest(candidate)[:24]
                        rows.append(candidate)
        rows.sort(key=_candidate_sort_key)
        out[slot.slot_id] = diversify_slot_candidates(rows, required_root_id=slot.required_root_id, section_id=slot.section_id)
    return out


def _bind_embedding_candidates(
    candidate_sets: Mapping[str, Sequence[Mapping[str, Any]]],
    slot_specs: Sequence[Mapping[str, Any]],
    skill_scores_by_section: Mapping[str, Mapping[str, float]],
) -> dict[str, list[dict[str, Any]]]:
    """Narrow graph candidates to exact assertion eligibility before allocation."""
    missing_sections = sorted(
        set(ALL_CLAIM_BEARING_SECTIONS) - set(skill_scores_by_section)
    )
    if missing_sections:
        raise ResumeGraphAllocationError(
            "embedding candidate authority is incomplete",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["embedding_section_candidate_coverage"],
                "missing_sections": missing_sections,
            },
        )
    slot_section = {
        str(row.get("slot_id") or ""): str(row.get("section_id") or "")
        for row in slot_specs
    }
    narrowed: dict[str, list[dict[str, Any]]] = {}
    for slot_id, raw_rows in candidate_sets.items():
        section_id = slot_section.get(slot_id, "")
        scores = skill_scores_by_section.get(section_id) or {}
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            skill_id = str(raw.get("skill_id") or "")
            if skill_id not in scores:
                continue
            row = dict(raw)
            row["embedding_similarity"] = round(float(scores[skill_id]), 9)
            rows.append(row)
        rows.sort(key=_candidate_sort_key)
        if not rows:
            raise ResumeGraphAllocationError(
                f"{slot_id}: no graph candidates remain after assertion eligibility",
                receipt={
                    "schema_version": "resume_graph_allocation_failure_v1",
                    "unsatisfied_constraints": ["embedding_candidate_intersection"],
                    "slot_id": slot_id,
                    "section_id": section_id,
                },
            )
        narrowed[slot_id] = rows
    return narrowed


def _bind_assignment_embedding_scores(
    plan: Mapping[str, Any],
    skill_scores_by_section: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    out = dict(plan)
    assignments: list[dict[str, Any]] = []
    for raw in plan.get("assignments") or []:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        section_id = str(row.get("section_id") or "")
        skill_id = str(row.get("skill_id") or "")
        scores = skill_scores_by_section.get(section_id) or {}
        if skill_id not in scores:
            raise ResumeGraphAllocationError(
                f"{section_id}: allocated skill lacks an exact embedding candidate",
                receipt={
                    "schema_version": "resume_graph_allocation_failure_v1",
                    "unsatisfied_constraints": ["embedding_assignment_coverage"],
                    "section_id": section_id,
                    "skill_id": skill_id,
                },
            )
        row["embedding_similarity"] = round(float(scores[skill_id]), 9)
        assignments.append(row)
    out["assignments"] = assignments
    out["embedding_candidate_authority"] = {
        "schema_version": "resume_graph_embedding_candidate_authority_v1",
        "section_candidate_counts": {
            section_id: len(scores)
            for section_id, scores in sorted(skill_scores_by_section.items())
        },
        "similarity_is_claim_authority": False,
        "allocation_narrowing_only": True,
        "pass": True,
    }
    return finalize_resume_graph_allocation_plan(out)
