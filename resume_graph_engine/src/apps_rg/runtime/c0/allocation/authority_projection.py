"""Authority projection and source traversal helpers for C0.3 section slicing."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from apps_rg.runtime.c0.allocation.contracts_and_validation import (
    ResumeGraphAllocationError,
)
from apps_rg.runtime.c0.c03_resume_graph_contracts import (
    TraversalRecorder,
    build_candidate_receipt,
    stable_digest,
)


def _allocation_authority_projection(
    *,
    section_id: str,
    section_plan: Mapping[str, Any],
    assignments: Sequence[Mapping[str, Any]],
    strict_source_authority: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Preserve C0.3's complete candidate universe and annotate allocation paths.

    A section plan records the actual graph traversal: selected and rejected
    roots, skills, facts, and metrics.  A whole-resume allocation is a later
    reservation decision over that universe.  It must not rewrite the earlier
    traversal into an all-selected miniature ledger, because doing so erases
    the finite candidate universe and its rejected alternatives.

    The resulting slice therefore keeps each source terminal decision intact
    and adds ``allocation_claim_unit_ids`` only to source paths reserved by the
    frozen allocation.  Consumers that need the final visible allocation use
    that explicit annotation; consumers that audit C0.3 breadth retain the
    original C0.3 decisions.
    """

    source_rows = [
        dict(raw)
        for raw in section_plan.get("graph_candidate_decision_ledger") or []
        if isinstance(raw, Mapping)
    ]
    source_index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in source_rows:
        candidate_type = str(row.get("candidate_type") or "").strip()
        candidate_id = str(row.get("candidate_id") or "").strip()
        root_id = str(row.get("root_id") or "").strip()
        if candidate_type == "role_episode_root" and not root_id:
            root_id = candidate_id
        if candidate_type and root_id and candidate_id:
            source_index.setdefault((candidate_type, root_id, candidate_id), []).append(row)

    requested: dict[tuple[str, str, str], set[str]] = {}
    for assignment in assignments:
        root_id = str(assignment.get("root_id") or "").strip()
        claim_unit_id = str(assignment.get("claim_unit_id") or "").strip()
        if not root_id:
            continue
        requested.setdefault(("role_episode_root", root_id, root_id), set()).add(claim_unit_id)
        for candidate_type, key in (
            ("leaf_skill", "skill_id"),
            ("source_fact", "fact_id"),
            ("metric_outcome", "metric_outcome_id"),
        ):
            candidate_id = str(assignment.get(key) or "").strip()
            if candidate_id:
                requested.setdefault((candidate_type, root_id, candidate_id), set()).add(
                    claim_unit_id
                )

    # A canonical source plan must bind every allocated path back to its
    # pre-targeting authority decision.  The small legacy fixture form below
    # predates canonical plan sealing and is handled after this check.
    canonical_source_ledger = strict_source_authority and (
        bool(section_plan.get("graph_candidate_receipt"))
        or bool(section_plan.get("plan_digest"))
    )
    missing_or_unapproved: list[str] = []
    for key in sorted(requested):
        candidates = source_index.get(key, [])
        if len(candidates) != 1:
            missing_or_unapproved.append(
                "missing_or_ambiguous_source_authority_path:" + ":".join(key)
            )
            continue
        source = candidates[0]
        authority = source.get("authority")
        if not isinstance(authority, Mapping) or authority.get("authority_pass") is not True:
            missing_or_unapproved.append("source_authority_not_pass:" + ":".join(key))
            continue
        if authority.get("targeting_consulted") is not False:
            missing_or_unapproved.append("source_authority_targeting_boundary:" + ":".join(key))
            continue
    if missing_or_unapproved and canonical_source_ledger:
        raise ResumeGraphAllocationError(
            f"{section_id}: allocation cannot project authority paths",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "section_id": section_id,
                "unsatisfied_constraints": ["allocation_authority_path_projection"],
                "failure_reasons": sorted(missing_or_unapproved),
            },
        )

    # Standalone section previews and synthetic unit fixtures created before
    # canonical C0.3 plan sealing do not carry the full authority ledger. They
    # are intentionally supported through their already authority-passing
    # allocation. A whole-resume canonical source plan always takes the strict
    # path above and fails closed for a missing or ambiguous authority path.
    if not source_rows and canonical_source_ledger:
        raise ResumeGraphAllocationError(
            f"{section_id}: canonical source plan has no candidate ledger",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "section_id": section_id,
                "unsatisfied_constraints": ["canonical_source_candidate_ledger"],
            },
        )

    if not canonical_source_ledger:
        # Legacy fixtures have leaf-skill rows only.  Complete their source
        # ledger with allocation-bound root/fact paths strictly for test and
        # standalone compatibility; production canonical plans never enter
        # this branch.
        for key, unit_ids in requested.items():
            if key in source_index:
                continue
            candidate_type, root_id, candidate_id = key
            hop_depth = 0 if candidate_type == "role_episode_root" else 1
            source_rows.append(
                {
                    "schema_version": "graph_candidate_decision_v1",
                    "section_id": section_id,
                    "candidate_id": candidate_id,
                    "candidate_type": candidate_type,
                    "candidate_path_id": (
                        f"root:{root_id}"
                        if candidate_type == "role_episode_root"
                        else f"root:{root_id}/"
                        + ("skill" if candidate_type == "leaf_skill" else "fact" if candidate_type == "source_fact" else "metric")
                        + f":{candidate_id}"
                    ),
                    "parent_id": "" if candidate_type == "role_episode_root" else root_id,
                    "root_id": root_id,
                    "employer_lane": "",
                    "hop_depth": hop_depth,
                    "decision": "selected",
                    "reason_codes": ["legacy_allocation_projection"],
                    "authority": {
                        "authority_pass": True,
                        "targeting_consulted": False,
                        "reason_codes": ["legacy_allocation_projection"],
                    },
                    "authority_pass": True,
                    "proof_strength_raw": 0.0,
                    "target_alignment_score": 0.0,
                    "ranking_score": 0.0,
                    "path_signature": "",
                }
            )

    projected: list[dict[str, Any]] = []
    for source in source_rows:
        row = dict(source)
        # The source plan is separately sealed.  This newly sliced plan receives
        # its own canonical stamp below.
        row.pop("plan_id", None)
        row.pop("plan_digest", None)
        row["section_id"] = section_id
        if not canonical_source_ledger and not isinstance(row.get("authority"), Mapping):
            row["authority"] = {
                "authority_pass": row.get("authority_pass") is True,
                "targeting_consulted": False,
                "reason_codes": list(row.get("reason_codes") or []),
            }
        candidate_type = str(row.get("candidate_type") or "").strip()
        candidate_id = str(row.get("candidate_id") or "").strip()
        root_id = str(row.get("root_id") or "").strip()
        if candidate_type == "role_episode_root" and not root_id:
            root_id = candidate_id
            row["root_id"] = root_id
        key = (candidate_type, root_id, candidate_id)
        claim_unit_ids = sorted(unit for unit in requested.get(key, set()) if unit)
        if claim_unit_ids:
            row["allocation_selected"] = True
            row["allocation_claim_unit_ids"] = claim_unit_ids
            row["allocation_source_decision"] = str(source.get("decision") or "")
        else:
            row["allocation_selected"] = False
        projected.append(row)

    projected.sort(
        key=lambda row: (
            int(row.get("hop_depth") or 0),
            str(row.get("candidate_type") or ""),
            str(row.get("candidate_path_id") or ""),
        )
    )
    candidate_receipt = build_candidate_receipt(
        section_id=section_id,
        decisions=projected,
    )
    max_hop_depth = max(
        2,
        max((int(row.get("hop_depth") or 0) for row in projected), default=0),
    )
    recorder = TraversalRecorder(section_id=section_id, max_hop_depth=max_hop_depth)
    edge_type_by_candidate_type = {
        "role_episode_root": "allocation_selected_root",
        "leaf_skill": "role_episode_contains_skill",
        "source_fact": "role_episode_supported_by_fact",
        "metric_outcome": "role_episode_has_metric_outcome",
    }
    selected_roots: set[str] = set()
    rejected_roots: set[str] = set()
    for row in projected:
        candidate_type = str(row.get("candidate_type") or "")
        root_id = str(row.get("root_id") or row.get("candidate_id") or "")
        candidate_id = str(row.get("candidate_id") or "")
        path_id = str(row.get("candidate_path_id") or "")
        hop_depth = int(row.get("hop_depth") or (0 if candidate_type == "role_episode_root" else 1))
        decision = str(row.get("decision") or "").strip().lower()
        if candidate_type == "role_episode_root":
            if decision == "selected":
                selected_roots.add(root_id)
            elif decision == "rejected":
                rejected_roots.add(root_id)
        recorder.record(
            event_type="edge_traversed",
            hop_depth=hop_depth,
            source_node_id="" if candidate_type == "role_episode_root" else root_id,
            target_node_id=candidate_id,
            edge_type=edge_type_by_candidate_type.get(candidate_type, "allocation_selected_path"),
            candidate_path_id=path_id,
        )
        authority = dict(row.get("authority") or {})
        authority_pass = authority.get("authority_pass") is True
        recorder.record(
            event_type="authority_evaluated",
            hop_depth=hop_depth,
            source_node_id="" if candidate_type == "role_episode_root" else root_id,
            target_node_id=candidate_id,
            edge_type=edge_type_by_candidate_type.get(candidate_type, "allocation_selected_path"),
            candidate_path_id=path_id,
            authority_pass=authority_pass,
            reason_codes=authority.get("reason_codes") or [],
        )
        recorder.record(
            event_type="candidate_terminal",
            hop_depth=hop_depth,
            source_node_id="" if candidate_type == "role_episode_root" else root_id,
            target_node_id=candidate_id,
            edge_type=edge_type_by_candidate_type.get(candidate_type, "allocation_selected_path"),
            candidate_path_id=path_id,
            authority_pass=authority_pass,
            decision=decision,
            reason_codes=row.get("reason_codes") or [],
        )
    traversal_receipt = recorder.build_receipt(
        decisions=projected,
        selected_root_ids=sorted(selected_roots),
        rejected_root_ids=sorted(rejected_roots),
        target_role_profile=str(section_plan.get("target_role_profile") or ""),
    )
    authority_rows = [dict(row.get("authority") or {}) for row in projected]
    authority_receipt = {
        "schema_version": "c03_pretarget_authority_receipt_v1",
        "section_id": section_id,
        "candidate_count": len(authority_rows),
        "authority_pass_count": sum(
            1 for row in authority_rows if row.get("authority_pass") is True
        ),
        "authority_block_count": sum(
            1 for row in authority_rows if row.get("authority_pass") is not True
        ),
        "targeting_consulted_count": sum(
            1 for row in authority_rows if row.get("targeting_consulted") is True
        ),
        "authority_before_targeting_pass": all(
            row.get("targeting_consulted") is False for row in authority_rows
        ),
        "authority_decisions_digest": stable_digest(authority_rows),
    }
    return projected, candidate_receipt, {
        "traversal": traversal_receipt,
        "authority": authority_receipt,
    }


def _allocation_source_traversal_evidence(
    section_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Carry the source C0.3 breadth receipt beside a narrowed visible slice."""

    fields = (
        "target_role_profile",
        "selection_method",
        "facts",
        "selected_nodes",
        "selected_skills",
        "selected_skill_ids",
        "selected_metrics_detail",
        "selected_metrics",
        "excluded_due_to_root_cap",
        "excluded_due_to_metric_cap",
        "graph_evidence_depth_report",
        "graph_evidence_depth_pre_report",
        "graph_evidence_depth_comparison_report",
        "graph_traversal_receipt",
        "graph_candidate_receipt",
    )
    evidence = {
        key: section_plan.get(key)
        for key in fields
        if key in section_plan
    }
    evidence.update(
        {
            "schema_version": "allocation_source_traversal_evidence_v1",
            "source_section_plan_id": str(section_plan.get("plan_id") or ""),
            "source_section_plan_digest": str(section_plan.get("plan_digest") or ""),
            "source_candidate_ledger_digest": stable_digest(
                [
                    dict(row)
                    for row in section_plan.get("graph_candidate_decision_ledger") or []
                    if isinstance(row, Mapping)
                ]
            ),
            "scope": "C03_SOURCE_CANDIDATE_UNIVERSE",
        }
    )
    return evidence
