"""Top-level whole-resume and section-only C0.3 graph allocation orchestrators."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.runtime.c0.allocation.contracts_and_validation import (
    ALL_CLAIM_BEARING_SECTIONS,
    LEGACY_CLAIM_BEARING_SECTIONS,
    NARRATIVE_DERIVATION_POLICY,
    SECTION_ONLY_SCOPE,
    ResumeGraphAllocationError,
    _strings,
    build_resume_graph_usage_ledger,
    stable_digest,
    stable_edge_id,
)
from apps_rg.runtime.c0.allocation.slot_candidates import (
    _bind_assignment_embedding_scores,
    _bind_embedding_candidates,
    _candidate_sets_from_section_plans,
    _default_slot_specs,
)
from apps_rg.runtime.c0.allocation.solver import (
    _append_derived_narrative_assignments,
    allocate_candidate_sets,
    build_section_final_evidence_contracts,
)


def build_whole_resume_graph_allocation(
    *,
    repo_root: Path,
    target_role: str = "",
    jd_text: str = "",
    briefing_text: str = "",
    section_order: Sequence[str] | None = None,
    embedding_skill_scores_by_section: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    """Traverse all claim-bearing lanes, allocate once, and freeze section slices."""
    if briefing_text and ("\n" not in briefing_text) and len(briefing_text) < 500:
        try:
            _bp = Path(briefing_text)
            if _bp.is_file():
                briefing_text = _bp.read_text(encoding="utf-8")
        except (OSError, ValueError):
            pass
    if jd_text and ("\n" not in jd_text) and len(jd_text) < 500:
        try:
            _jp = Path(jd_text)
            if _jp.is_file():
                jd_text = _jp.read_text(encoding="utf-8")
        except (OSError, ValueError):
            pass

    from apps_rg.runtime.c0.c03_resume_graph_contracts import ResumeGraphSelectionPolicyV2, finalize_canonical_section_plan
    from apps_rg.runtime.c0.mandate_routing_engine import resolve_mandate_route
    from apps_rg.runtime.sections.graph_role_episode_selector import (
        build_selected_graph_evidence_plan_for_section,
    )

    mandate_route = resolve_mandate_route(
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    mandate_route_dict = mandate_route.as_dict()

    requested = list(section_order or ALL_CLAIM_BEARING_SECTIONS)
    requested_set = set(requested)
    if requested_set not in (set(ALL_CLAIM_BEARING_SECTIONS), set(LEGACY_CLAIM_BEARING_SECTIONS)):
        raise ValueError("whole-resume allocation requires all canonical claim-bearing sections")
    section_plans: dict[str, dict[str, Any]] = {}
    for section_id in requested:
        plan, _ordered, _allowed = build_selected_graph_evidence_plan_for_section(
            repo_root=repo_root,
            section_id=section_id,
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=briefing_text,
        )
        section_plans[section_id] = plan
    graph_digests = {
        str((plan.get("source_authority_contract") or {}).get("graph_digest") or "")
        for plan in section_plans.values()
    }
    graph_versions = {
        str((plan.get("source_authority_contract") or {}).get("graph_version") or "")
        for plan in section_plans.values()
    }
    if len(graph_digests) != 1 or "" in graph_digests:
        raise ResumeGraphAllocationError(
            "section graph source digests disagree",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["graph_source_digest_parity"],
                "observed_graph_digests": sorted(graph_digests),
            },
        )
    if len(graph_versions) != 1:
        raise ResumeGraphAllocationError(
            "section graph versions disagree",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["graph_version_parity"],
                "observed_graph_versions": sorted(graph_versions),
            },
        )
    graph_digest = next(iter(graph_digests))
    graph_version = next(iter(graph_versions))
    slot_specs = _default_slot_specs(section_plans, mandate_route=mandate_route_dict)
    section_budgets: dict[str, dict[str, int]] = {}
    for slot in slot_specs:
        section_id = str(slot["section_id"])
        section_budgets.setdefault(section_id, {"min_assignments": 0, "max_assignments": 0})
        section_budgets[section_id]["min_assignments"] += 1
        section_budgets[section_id]["max_assignments"] += 1
    policy = ResumeGraphSelectionPolicyV2(
        graph_snapshot_digest=graph_digest,
        graph_version=graph_version,
        section_budgets=section_budgets,
    )
    candidates = _candidate_sets_from_section_plans(
        section_plans, slot_specs, mandate_route=mandate_route_dict
    )
    if embedding_skill_scores_by_section is not None:
        candidates = _bind_embedding_candidates(
            candidates,
            slot_specs,
            embedding_skill_scores_by_section,
        )
    plan = allocate_candidate_sets(
        candidate_sets=candidates,
        slot_specs=slot_specs,
        graph_digest=graph_digest,
        policy_digest=policy.policy_digest,
        representation_policy={
            "canonical_role_representation": "bullets",
            "narratives_are_derived_alternatives": True,
            "narrative_derivation_map": dict(sorted(NARRATIVE_DERIVATION_POLICY.items())),
            "alternative_assignments_count_toward_global_uniqueness": False,
        },
        section_plan_digests={
            section_id: str(section_plan.get("plan_digest") or "")
            for section_id, section_plan in section_plans.items()
        },
        max_fact_reuse=policy.max_fact_reuse,
        max_source_family_share=policy.max_source_family_share,
    )
    plan["selection_policy"] = policy.to_dict()
    plan["mandate_route"] = mandate_route_dict
    plan["credential_elevation_ids"] = list(mandate_route.credential_elevation_ids)
    plan["two_page_slot_budget"] = dict(mandate_route.slot_budget_profile)
    try:
        from apps_rg.fact_inventory.augmented_skills_graph import load_augmented_skills_graph
        from apps_rg.fact_inventory.track_weighted_graph_expansion import build_track_weighted_expansion

        _graph = load_augmented_skills_graph(repo_root=repo_root)
        _exp = build_track_weighted_expansion(
            graph=_graph,
            role_family_key=mandate_route.canonical_projection_role,
            jd_text=jd_text or target_role,
            enforce_hybrid_contract=False,
            bind_c03=False,
            repo_root=repo_root,
        )
        plan["track_expansion_summary"] = {
            "role_family_key": _exp.get("role_family_key"),
            "track_weights": _exp.get("track_weights"),
            "tracks_with_facts": _exp.get("tracks_with_facts"),
            "selected_skill_count": len(_exp.get("selected_skills") or ()),
            "graph_hop_edge_types_used": _exp.get("graph_hop_edge_types_used"),
        }
    except (OSError, ValueError, KeyError, FileNotFoundError):
        plan["track_expansion_summary"] = {
            "role_family_key": mandate_route.canonical_projection_role,
            "track_weights": dict(mandate_route.track_weights),
        }
    unify_alloc = {str(r["claim_unit_id"]).split(":", 1)[-1]: str(r["root_id"]) for r in plan.get("assignments") or [] if str(r.get("section_id") or "") == "unify_bullets" and ":" in str(r.get("claim_unit_id") or "")}
    if unify_alloc and section_plans.get("unify_bullets", {}).get("unify_bullet_slot_bundle_map_resolved") != unify_alloc:
        u_plan = {k: v for k, v in section_plans["unify_bullets"].items() if k not in ("plan_id", "plan_digest")}
        section_plans["unify_bullets"] = finalize_canonical_section_plan({**u_plan, "unify_bullet_slot_bundle_map_resolved": dict(unify_alloc)})
        plan["section_plan_digests"]["unify_bullets"] = str(section_plans["unify_bullets"].get("plan_digest") or "")
    ibm_alloc = {str(r["claim_unit_id"]).split(":", 1)[-1]: str(r["root_id"]) for r in plan.get("assignments") or [] if str(r.get("section_id") or "") == "ibm_bullets" and ":" in str(r.get("claim_unit_id") or "")}
    if ibm_alloc and section_plans.get("ibm_bullets", {}).get("ibm_bullet_slot_bundle_map_resolved") != ibm_alloc:
        i_plan = {k: v for k, v in section_plans["ibm_bullets"].items() if k not in ("plan_id", "plan_digest")}
        section_plans["ibm_bullets"] = finalize_canonical_section_plan({**i_plan, "ibm_bullet_slot_bundle_map_resolved": dict(ibm_alloc)})
        plan["section_plan_digests"]["ibm_bullets"] = str(section_plans["ibm_bullets"].get("plan_digest") or "")
    plan["targeting_provenance"] = {
        "target_role": str(target_role or "").strip(),
        "jd_sha256": hashlib.sha256(str(jd_text or "").encode("utf-8")).hexdigest() if jd_text else "",
        "briefing_sha256": hashlib.sha256(str(briefing_text or "").encode("utf-8")).hexdigest() if briefing_text else "",
    }
    plan["section_traversal_receipts"] = {
        section_id: {
            "plan_digest": str(section_plan.get("plan_digest") or ""),
            "events_digest": str(
                (section_plan.get("graph_traversal_receipt") or {}).get("events_digest")
                or ""
            ),
            "candidate_conservation_pass": bool(
                (section_plan.get("graph_candidate_receipt") or {}).get(
                    "candidate_conservation_pass"
                )
            ),
            "traversal_pass": bool(
                (section_plan.get("graph_traversal_receipt") or {}).get("pass")
            ),
        }
        for section_id, section_plan in sorted(section_plans.items())
    }
    plan = _append_derived_narrative_assignments(plan, section_plans=section_plans)
    if embedding_skill_scores_by_section is not None:
        plan = _bind_assignment_embedding_scores(
            plan,
            embedding_skill_scores_by_section,
        )
    ledger = build_resume_graph_usage_ledger(plan)
    contracts = build_section_final_evidence_contracts(
        allocation_plan=plan,
        section_plans=section_plans,
    )
    return {
        "allocation_plan": plan,
        "usage_ledger": ledger,
        "section_final_evidence_contracts": contracts,
        "section_plans": section_plans,
    }


def build_section_only_graph_allocation(
    *,
    section_plan: Mapping[str, Any],
    section_id: str,
) -> dict[str, Any]:
    """Freeze a standalone section without asserting whole-resume uniqueness."""
    facts_by_root = {
        str(row.get("role_episode_bundle_id") or row.get("fact_id") or ""): dict(row)
        for row in section_plan.get("facts") or []
        if isinstance(row, Mapping)
    }
    selected_skills = [
        dict(row)
        for row in section_plan.get("selected_skills") or []
        if isinstance(row, Mapping) and row.get("skill_id")
    ]
    if not selected_skills:
        raise ResumeGraphAllocationError(
            f"{section_id}: standalone graph plan has no selected skills",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["section_only_selected_skill_coverage"],
                "section_id": section_id,
            },
        )
    # ``selected_skills`` is the compact selection projection.  Carry the
    # human-readable graph label and source references from the sealed
    # decision ledger as a backward-compatible fallback for plans generated
    # before those fields were added to the compact projection.
    skill_metadata_by_path: dict[tuple[str, str], dict[str, Any]] = {}
    for row in section_plan.get("graph_candidate_decision_ledger") or []:
        if not isinstance(row, Mapping) or str(row.get("candidate_type") or "") != "leaf_skill":
            continue
        root_id = str(row.get("root_id") or "").strip()
        skill_id = str(row.get("candidate_id") or "").strip()
        if root_id and skill_id:
            skill_metadata_by_path[(root_id, skill_id)] = dict(row)
    slot_specs: list[dict[str, Any]] = []
    candidates: dict[str, list[dict[str, Any]]] = {}
    for index, skill in enumerate(selected_skills, start=1):
        slot_id = f"{section_id}:section_only:{index:02d}"
        root_id = str(skill.get("role_episode_bundle_id") or "")
        fact = facts_by_root.get(root_id) or {}
        skill_id = str(skill.get("skill_id") or "")
        ledger_row = skill_metadata_by_path.get((root_id, skill_id), {})
        source_fact_ids = _strings(
            fact.get("linked_source_fact_ids") or fact.get("source_fact_ids") or [root_id]
        )
        source_fact_id = source_fact_ids[0] if source_fact_ids else root_id
        employer_lane = str(skill.get("employer_lane") or fact.get("employer_lane") or "")
        slot_specs.append(
            {
                "slot_id": slot_id,
                "section_id": section_id,
                "metric_required": False,
                "employer_lane": employer_lane,
            }
        )
        candidate = {
            "section_id": section_id,
            "claim_unit_id": slot_id,
            "skill_id": skill_id,
            "skill_label": str(
                skill.get("skill_label")
                or ledger_row.get("skill_label")
                or ledger_row.get("label")
                or ""
            ),
            "source_refs": _strings(
                list(skill.get("source_refs") or [])
                + list(ledger_row.get("source_refs") or [])
            ),
            "fact_id": source_fact_id,
            "root_id": root_id,
            "employer_lane": employer_lane,
            "source_family": employer_lane or source_fact_id,
            "authority_pass": True,
            "proof_strength_raw": float(skill.get("proof_strength_raw") or 0.0),
            "target_alignment_score": float(skill.get("target_alignment_score") or 0.0),
            "path_confidence_raw": 1.0,
            "source_independence_score": 0.5,
            "graph_path_ids": [
                f"root:{root_id}",
                f"root:{root_id}/skill:{skill.get('skill_id')}",
                f"root:{root_id}/fact:{source_fact_id}",
            ],
            "edge_ids": [
                stable_edge_id(root_id, "role_episode_contains_skill", skill_id),
                stable_edge_id(root_id, "role_episode_supported_by_fact", source_fact_id),
            ],
            "citation_refs": source_fact_ids,
            # The current selector names the graph-authored bundle surface
            # ``domain``.  Prefer an explicit bundle theme if supplied by a
            # future projection, while retaining the existing domain surface
            # for current plans.
            "root_bundle_theme": str(
                fact.get("bundle_theme") or fact.get("domain") or ""
            ),
            "root_claim_text": str(fact.get("claim_text") or root_id),
        }
        candidate["candidate_id"] = "section-only:" + stable_digest(candidate)[:24]
        candidates[slot_id] = [candidate]
    authority = section_plan.get("source_authority_contract") or {}
    plan = allocate_candidate_sets(
        candidate_sets=candidates,
        slot_specs=slot_specs,
        graph_digest=str(authority.get("graph_digest") or "unknown"),
        policy_digest=stable_digest(
            {
                "scope": SECTION_ONLY_SCOPE,
                "section_id": section_id,
                "source_plan_digest": section_plan.get("plan_digest"),
            }
        ),
        allocation_scope=SECTION_ONLY_SCOPE,
        section_plan_digests={section_id: str(section_plan.get("plan_digest") or "")},
        max_fact_reuse=max(len(slot_specs), 1),
        max_source_family_share=1.0,
    )
    traversal = section_plan.get("graph_traversal_receipt") or {}
    contract: dict[str, Any] = {
        "schema_version": "section_final_graph_evidence_contract_v1",
        "section_id": section_id,
        "allocation_scope": SECTION_ONLY_SCOPE,
        "allocation_plan_digest": plan["allocation_plan_digest"],
        "source_section_plan_id": str(section_plan.get("plan_id") or ""),
        "source_section_plan_digest": str(section_plan.get("plan_digest") or ""),
        "graph_digest": str(authority.get("graph_digest") or ""),
        "assignments": list(plan["assignments"]),
        "assignment_count": len(plan["assignments"]),
        "representation_mode": "SECTION_ONLY",
        "derived_from_section_id": "",
        "counts_toward_global_uniqueness": False,
        "traversal_receipt_digest": str(traversal.get("events_digest") or ""),
        "traversal_conservation_pass": traversal.get("pass") is True,
        "pass": traversal.get("pass") is True,
    }
    contract["contract_digest"] = stable_digest(contract)
    return {
        "allocation_plan": plan,
        "usage_ledger": build_resume_graph_usage_ledger(plan),
        "final_evidence_contract": contract,
    }


def write_whole_resume_graph_allocation_bundle(
    bundle: Mapping[str, Any],
    *,
    output_dir: Path,
) -> dict[str, str]:
    """Persist current-run artifacts only; no canonical graph or SQLite mutation."""
    output_dir.mkdir(parents=True, exist_ok=True)
    refs: dict[str, str] = {}
    artifacts = {
        "allocation_plan": "resume_graph_allocation_plan.json",
        "usage_ledger": "resume_graph_usage_ledger.json",
        "section_final_evidence_contracts": "section_final_graph_evidence_contracts.json",
        "section_plans": "c03_section_graph_plans.json",
    }
    for key, filename in artifacts.items():
        path = output_dir / filename
        path.write_text(
            json.dumps(bundle.get(key), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        refs[key] = str(path)
    return refs
