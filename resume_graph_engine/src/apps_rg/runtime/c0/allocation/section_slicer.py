"""Section plan slicing against finalized C0.3 whole-resume allocation plans."""

from __future__ import annotations

from typing import Any, Mapping

from apps_rg.runtime.c0.allocation.authority_projection import (
    _allocation_authority_projection,
    _allocation_source_traversal_evidence,
)
from apps_rg.runtime.c0.allocation.contracts_and_validation import (
    CANONICAL_BULLET_CLAIM_UNITS,
    SECTION_ONLY_SCOPE,
    ResumeGraphAllocationError,
    _strings,
    validate_resume_graph_allocation_plan,
)
from apps_rg.runtime.c0.c0_fact_anchor import build_fact_anchor


def slice_section_plan_for_allocation(
    *,
    section_plan: Mapping[str, Any],
    allocation_plan: Mapping[str, Any],
    final_evidence_contract: Mapping[str, Any],
    section_id: str,
) -> dict[str, Any]:
    """Project the frozen global assignment into one canonical section fact plan."""
    from apps_rg.runtime.c0.c03_resume_graph_contracts import (
        finalize_canonical_section_plan,
    )

    failures = validate_resume_graph_allocation_plan(allocation_plan)
    if failures:
        raise ResumeGraphAllocationError(
            "cannot slice invalid allocation plan",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["allocation_plan_validation"],
                "validation_failures": failures,
            },
        )
    if str(final_evidence_contract.get("section_id") or "") != section_id:
        raise ValueError(f"{section_id}: final evidence contract section mismatch")
    allocation_digest = str(allocation_plan.get("allocation_plan_digest") or "")
    if str(final_evidence_contract.get("allocation_plan_digest") or "") != allocation_digest:
        raise ValueError(f"{section_id}: final evidence contract allocation digest mismatch")
    assignments = [
        dict(row)
        for row in allocation_plan.get("assignments") or []
        if isinstance(row, Mapping) and row.get("section_id") == section_id
    ]
    if not assignments and section_id not in ("ey_bullets", "ey_narrative"):
        raise ResumeGraphAllocationError(
            f"{section_id}: frozen allocation has no assignments",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["section_assignment_coverage"],
                "section_id": section_id,
            },
        )
    by_root: dict[str, list[dict[str, Any]]] = {}
    for assignment in assignments:
        root_id = str(assignment.get("root_id") or "").strip()
        if not root_id:
            raise ValueError(f"{section_id}: assignment missing root_id")
        by_root.setdefault(root_id, []).append(assignment)
    preserve_root_authority = section_id == "competencies"
    source_facts_by_root = {
        str(row.get("role_episode_bundle_id") or row.get("fact_id") or ""): dict(row)
        for row in section_plan.get("facts") or []
        if isinstance(row, Mapping)
        and str(row.get("role_episode_bundle_id") or row.get("fact_id") or "")
    }
    for raw in section_plan.get("graph_candidate_decision_ledger") or []:
        if not isinstance(raw, Mapping) or str(raw.get("candidate_type") or "") != "role_episode_root":
            continue
        auth = raw.get("authority")
        if not (raw.get("authority_pass") is True or (isinstance(auth, Mapping) and auth.get("authority_pass") is True)):
            continue
        root_id = str(raw.get("root_id") or raw.get("candidate_id") or "").strip()
        if root_id and root_id not in source_facts_by_root:
            source_facts_by_root[root_id] = {
                "fact_id": root_id,
                "candidate_fact_id": root_id,
                "role_episode_bundle_id": root_id,
                "claim_text": str(raw.get("claim_text") or ""),
                "employer_lane": str(raw.get("employer_lane") or ""),
                "source_employment": str(raw.get("employer") or raw.get("employer_lane") or ""),
                "domain": str(raw.get("bundle_theme") or raw.get("claim_scope") or ""),
                "linked_source_fact_ids": list(raw.get("linked_source_fact_ids") or []),
                "linked_identity_fact_ids": list(raw.get("linked_source_fact_ids") or []),
                "graph_skill_node_ids": list(raw.get("graph_skill_node_ids") or []),
                "metric_outcome_ids": list(raw.get("metric_outcome_ids") or []),
                "confidence": "HIGH",
            }
    source_skills_by_root: dict[str, list[dict[str, Any]]] = {}
    for raw in section_plan.get("selected_skills") or []:
        if not isinstance(raw, Mapping):
            continue
        root_id = str(raw.get("role_episode_bundle_id") or "").strip()
        if root_id in by_root:
            source_skills_by_root.setdefault(root_id, []).append(dict(raw))
    source_metrics_by_root: dict[str, list[dict[str, Any]]] = {}
    for raw in section_plan.get("selected_metrics_detail") or []:
        if not isinstance(raw, Mapping):
            continue
        root_id = str(raw.get("role_episode_bundle_id") or "").strip()
        if root_id in by_root:
            source_metrics_by_root.setdefault(root_id, []).append(dict(raw))

    facts: list[dict[str, Any]] = []
    selected_skills: list[dict[str, Any]] = []
    selected_metrics_detail: list[dict[str, Any]] = []
    selected_edges: list[dict[str, Any]] = []
    allowed_ids: list[str] = []
    for root_id, rows in sorted(by_root.items()):
        rows.sort(key=lambda row: str(row.get("claim_unit_id") or ""))
        allocated_skill_ids = {
            str(row.get("skill_id") or "") for row in rows if str(row.get("skill_id") or "")
        }
        allocated_metric_ids = {
            str(row.get("metric_outcome_id") or "")
            for row in rows
            if str(row.get("metric_outcome_id") or "")
        }
        root_skills = {
            str(row.get("skill_id") or ""): dict(row)
            for row in source_skills_by_root.get(root_id, [])
            if str(row.get("skill_id") or "") in allocated_skill_ids
        }
        root_metrics = {
            str(row.get("metric_outcome_id") or ""): dict(row)
            for row in source_metrics_by_root.get(root_id, [])
            if str(row.get("metric_outcome_id") or "") in allocated_metric_ids
        }
        for assignment in rows:
            skill_id = str(assignment.get("skill_id") or "")
            if skill_id:
                root_skills.setdefault(
                    skill_id,
                    {
                        "skill_id": skill_id,
                        "role_episode_bundle_id": root_id,
                        "employer_lane": str(assignment.get("employer_lane") or ""),
                        "proof_strength_raw": float(
                            assignment.get("proof_strength_raw") or 0.0
                        ),
                        "target_alignment_score": float(
                            assignment.get("target_alignment_score") or 0.0
                        ),
                    },
                )
                root_skills[skill_id]["claim_unit_id"] = str(
                    assignment.get("claim_unit_id") or ""
                )
            metric_id = str(assignment.get("metric_outcome_id") or "")
            if metric_id:
                root_metrics.setdefault(
                    metric_id,
                    {
                        "metric_outcome_id": metric_id,
                        "role_episode_bundle_id": root_id,
                        "employer_lane": str(assignment.get("employer_lane") or ""),
                        "metric": str(assignment.get("metric_text") or ""),
                        "metric_value": str(assignment.get("metric_value") or ""),
                        "metric_unit": str(assignment.get("metric_unit") or ""),
                        "normalized_metric_signature": str(
                            assignment.get("normalized_metric_signature") or ""
                        ),
                    },
                )
                root_metrics[metric_id]["claim_unit_id"] = str(
                    assignment.get("claim_unit_id") or ""
                )
        skill_ids = sorted(root_skills)
        metric_ids = sorted(root_metrics)
        source_fact_ids = _strings(row.get("fact_id") for row in rows)
        metric_values = _strings(
            row.get("metric") or row.get("metric_text")
            for row in root_metrics.values()
        )
        first = rows[0]
        fact = dict(source_facts_by_root.get(root_id) or {})
        linked_identity_ids = _strings(
            list(fact.get("linked_identity_fact_ids") or []) + source_fact_ids
        )
        linked_source_ids = _strings(
            list(fact.get("linked_source_fact_ids") or []) + source_fact_ids
        )
        fact.update(
            {
                "fact_id": root_id,
                "candidate_fact_id": root_id,
                "claim_text": str(
                    fact.get("claim_text") or first.get("root_claim_text") or root_id
                ),
                "role_episode_bundle_id": root_id,
                "graph_evidence_type": "role_episode_bundle",
                "employer_lane": str(
                    fact.get("employer_lane") or first.get("employer_lane") or ""
                ),
                "source_employment": str(
                    fact.get("source_employment")
                    or fact.get("employer_lane")
                    or first.get("employer_lane")
                    or ""
                ),
                "graph_skill_node_ids": skill_ids,
                "metric_outcome_ids": metric_ids,
                "selected_metric_ids": metric_ids,
                "allowed_graph_evidence_ids": _strings(
                    list(fact.get("allowed_graph_evidence_ids") or [])
                    + [root_id, *source_fact_ids, *skill_ids, *metric_ids]
                ),
                "linked_identity_fact_ids": linked_identity_ids,
                "linked_source_fact_ids": linked_source_ids,
                "source_fact_ids": [root_id],
                "confidence": str(fact.get("confidence") or "HIGH"),
                "support_level": "allocation_authority_pass",
                "verification_status": "allocation_authority_pass",
                "metric_values": metric_values,
                "technologies": skill_ids,
                "domain": str(fact.get("domain") or first.get("root_claim_scope") or ""),
                "allocation_claim_unit_ids": [
                    str(row.get("claim_unit_id") or "") for row in rows
                ],
                "allocation_plan_digest": allocation_digest,
                "fact_anchor": first.get("fact_anchor") or build_fact_anchor({**fact, **first}),
                "raw_chunk": str(first.get("raw_chunk") or (first.get("fact_anchor") or {}).get("resolved_raw_chunk") or build_fact_anchor({**fact, **first})["resolved_raw_chunk"]),
            }
        )
        facts.append(fact)
        allowed_ids.extend(fact["allowed_graph_evidence_ids"])
        selected_skills.extend(root_skills[skill_id] for skill_id in skill_ids)
        selected_metrics_detail.extend(
            root_metrics[metric_id] for metric_id in metric_ids
        )
        for row in rows:
            selected_edges.extend(
                {
                    "edge_id": edge_id,
                    "source": root_id,
                    "target": "",
                    "edge_type": "allocation_bound_graph_edge",
                }
                for edge_id in row.get("edge_ids") or []
            )
        source_edge_keys = {
            (
                str(edge.get("source") or ""),
                str(edge.get("edge_type") or ""),
                str(edge.get("target") or ""),
            )
            for edge in section_plan.get("selected_edges") or []
            if isinstance(edge, Mapping)
            and preserve_root_authority
            and str(edge.get("source") or "") == root_id
            and str(edge.get("target") or "") in fact["allowed_graph_evidence_ids"]
        }
        selected_edges.extend(
            {
                "source": source,
                "edge_type": edge_type,
                "target": target,
            }
            for source, edge_type, target in sorted(source_edge_keys)
        )

    # Bullet lanes have stable presentation claim-unit identifiers (for example
    # ``bul_unify_001``) which must survive the root-bound graph projection.
    # The prior root-grouped projection emitted one fact per role episode and
    # silently discarded those slot identities.  That made the final renderer
    # ask for bullet IDs that the frozen proof pool could not authorize.  Build
    # one visible fact per immutable allocation assignment instead.  Each row is
    # still directly bound to its role-episode root, skill, source fact, and
    # optional metric; no root or evidence path is inferred here.
    # Section-only / legacy allocations intentionally retain graph-root facts;
    # they do not carry final visible bullet slots.  A final whole-resume slice
    # must carry either the complete canonical slot set or none of it: a mixed
    # allocation would lose the identity of some rendered bullets and fails
    # closed rather than producing a hybrid proof pool.
    canonical_bullet_slot_count = 0
    if section_id in CANONICAL_BULLET_CLAIM_UNITS:
        expected_bullet_ids = set(CANONICAL_BULLET_CLAIM_UNITS[section_id])
        canonical_bullet_slot_count = sum(
            1
            for assignment in assignments
            if str(assignment.get("claim_unit_id") or "").startswith(f"{section_id}:")
            and str(assignment.get("claim_unit_id") or "").split(":", 1)[1]
            in expected_bullet_ids
        )
        if 0 < canonical_bullet_slot_count < len(assignments):
            raise ResumeGraphAllocationError(
                f"{section_id}: allocation mixes canonical and noncanonical bullet slots",
                receipt={
                    "schema_version": "resume_graph_allocation_failure_v1",
                    "unsatisfied_constraints": ["canonical_bullet_claim_unit_identity"],
                    "section_id": section_id,
                    "canonical_bullet_slot_count": canonical_bullet_slot_count,
                    "assignment_count": len(assignments),
                },
            )
    if (
        section_id in CANONICAL_BULLET_CLAIM_UNITS
        and canonical_bullet_slot_count == len(assignments)
    ):
        expected_claim_units = set(CANONICAL_BULLET_CLAIM_UNITS[section_id])
        display_facts: list[dict[str, Any]] = []
        display_skills: list[dict[str, Any]] = []
        display_metrics: list[dict[str, Any]] = []
        display_allowed_ids: list[str] = []
        for assignment in sorted(assignments, key=lambda row: str(row.get("claim_unit_id") or "")):
            claim_unit_id = str(assignment.get("claim_unit_id") or "").strip()
            prefix = f"{section_id}:"
            visible_fact_id = (
                claim_unit_id[len(prefix) :] if claim_unit_id.startswith(prefix) else ""
            )
            if visible_fact_id not in expected_claim_units:
                raise ResumeGraphAllocationError(
                    f"{section_id}: allocation claim unit has no canonical visible bullet id",
                    receipt={
                        "schema_version": "resume_graph_allocation_failure_v1",
                        "unsatisfied_constraints": ["canonical_bullet_claim_unit_identity"],
                        "section_id": section_id,
                        "claim_unit_id": claim_unit_id,
                    },
                )
            root_id = str(assignment.get("root_id") or "").strip()
            root_fact = dict(source_facts_by_root.get(root_id) or {})
            if not root_fact:
                raise ResumeGraphAllocationError(
                    f"{section_id}: allocated bullet root is absent from the source graph plan",
                    receipt={
                        "schema_version": "resume_graph_allocation_failure_v1",
                        "unsatisfied_constraints": ["allocated_bullet_root_source_coverage"],
                        "section_id": section_id,
                        "root_id": root_id,
                        "claim_unit_id": claim_unit_id,
                    },
                )
            skill_id = str(assignment.get("skill_id") or "").strip()
            source_fact_id = str(assignment.get("fact_id") or "").strip()
            metric_id = str(assignment.get("metric_outcome_id") or "").strip()
            linked_identity_ids = _strings(
                list(root_fact.get("linked_identity_fact_ids") or [])
                + [source_fact_id]
            )
            linked_source_ids = _strings(
                list(root_fact.get("linked_source_fact_ids") or [])
                + [source_fact_id]
            )
            evidence_ids = _strings(
                list(root_fact.get("allowed_graph_evidence_ids") or [])
                + [visible_fact_id, root_id, source_fact_id, skill_id, metric_id]
            )
            display_facts.append(
                {
                    **root_fact,
                    "fact_id": visible_fact_id,
                    "candidate_fact_id": source_fact_id or root_id,
                    "claim_text": str(
                        root_fact.get("claim_text")
                        or assignment.get("root_claim_text")
                        or root_id
                    ),
                    "role_episode_bundle_id": root_id,
                    "graph_evidence_type": "role_episode_bundle",
                    "employer_lane": str(
                        root_fact.get("employer_lane")
                        or assignment.get("employer_lane")
                        or ""
                    ),
                    "source_employment": str(
                        root_fact.get("source_employment")
                        or root_fact.get("employer_lane")
                        or assignment.get("employer_lane")
                        or ""
                    ),
                    "graph_skill_node_ids": _strings([skill_id]),
                    "metric_outcome_ids": _strings([metric_id]),
                    "selected_metric_ids": _strings([metric_id]),
                    "allowed_graph_evidence_ids": evidence_ids,
                    "linked_identity_fact_ids": linked_identity_ids,
                    "linked_source_fact_ids": linked_source_ids,
                    # The visible bullet slot is the only source identifier a
                    # renderer may cite.  The immutable graph source stays in
                    # linked_source_fact_ids and the allocation assignment.
                    "source_fact_ids": [visible_fact_id],
                    "confidence": str(root_fact.get("confidence") or "HIGH"),
                    "support_level": "allocation_authority_pass",
                    "verification_status": "allocation_authority_pass",
                    "metric_values": _strings([assignment.get("metric_text")]),
                    "has_metric": bool(metric_id),
                    "metric_raw": str(assignment.get("metric_text") or ""),
                    "technologies": _strings([skill_id]),
                    "domain": str(
                        root_fact.get("domain")
                        or assignment.get("root_claim_scope")
                        or ""
                    ),
                    "allocation_claim_unit_ids": [claim_unit_id],
                    "allocation_plan_digest": allocation_digest,
                    "fact_anchor": assignment.get("fact_anchor") or build_fact_anchor({**root_fact, **assignment}),
                    "raw_chunk": str(assignment.get("raw_chunk") or (assignment.get("fact_anchor") or {}).get("resolved_raw_chunk") or build_fact_anchor({**root_fact, **assignment})["resolved_raw_chunk"]),
                }
            )
            if skill_id:
                source_skill = next(
                    (
                        row
                        for row in source_skills_by_root.get(root_id, [])
                        if str(row.get("skill_id") or "") == skill_id
                    ),
                    {},
                )
                display_skills.append(
                    {
                        **source_skill,
                        "skill_id": skill_id,
                        "role_episode_bundle_id": root_id,
                        "employer_lane": str(assignment.get("employer_lane") or ""),
                        "claim_unit_id": claim_unit_id,
                    }
                )
            if metric_id:
                source_metric = next(
                    (
                        row
                        for row in source_metrics_by_root.get(root_id, [])
                        if str(row.get("metric_outcome_id") or "") == metric_id
                    ),
                    {},
                )
                display_metrics.append(
                    {
                        **source_metric,
                        "metric_outcome_id": metric_id,
                        "role_episode_bundle_id": root_id,
                        "employer_lane": str(assignment.get("employer_lane") or ""),
                        "metric": str(
                            source_metric.get("metric")
                            or assignment.get("metric_text")
                            or ""
                        ),
                        "claim_unit_id": claim_unit_id,
                    }
                )
            display_allowed_ids.extend(evidence_ids)
        facts = display_facts
        selected_skills = display_skills
        selected_metrics_detail = display_metrics
        allowed_ids = display_allowed_ids
    projected_decisions, projected_candidate_receipt, projected_receipts = (
        _allocation_authority_projection(
            section_id=section_id,
            section_plan=section_plan,
            assignments=assignments,
            strict_source_authority=(
                str(allocation_plan.get("allocation_scope") or "")
                != SECTION_ONLY_SCOPE
            ),
        )
    )
    source_traversal_evidence = _allocation_source_traversal_evidence(section_plan)
    out = dict(section_plan)
    out.pop("plan_id", None)
    out.pop("plan_digest", None)
    out.update(
        {
            "facts": facts,
            "required_fact_ids": [str(row["fact_id"]) for row in facts],
            "allowed_graph_evidence_ids": _strings(allowed_ids),
            "selected_nodes": sorted(by_root),
            "selected_edges": selected_edges,
            "selected_skills": selected_skills,
            "selected_skill_ids": _strings(
                row.get("skill_id") for row in selected_skills
            ),
            "selected_metrics": _strings(
                row.get("metric_outcome_id") for row in selected_metrics_detail
            ),
            "selected_metrics_detail": selected_metrics_detail,
            "graph_candidate_decision_ledger": projected_decisions,
            "graph_candidate_receipt": projected_candidate_receipt,
            "graph_traversal_receipt": projected_receipts["traversal"],
            "pretarget_authority_receipt": projected_receipts["authority"],
            # This is intentionally distinct from the narrowed visible
            # allocation above. X2 traversal checks consume it to prove the
            # candidate universe C0.3 actually inspected.
            "allocation_source_traversal_evidence": source_traversal_evidence,
            "selected_employer_lane_ids": _strings(
                row.get("employer_lane") for row in assignments
            ),
            "allocation_scope": str(allocation_plan.get("allocation_scope") or ""),
            "allocation_plan_id": str(allocation_plan.get("allocation_plan_id") or ""),
            "allocation_plan_digest": allocation_digest,
            "allocation_assignments": assignments,
            "final_graph_evidence_contract": dict(final_evidence_contract),
            "global_uniqueness_claimed": bool(
                allocation_plan.get("global_uniqueness_claimed")
            ),
            "durable_graph_state_mutated": False,
        }
    )
    return finalize_canonical_section_plan(out)
