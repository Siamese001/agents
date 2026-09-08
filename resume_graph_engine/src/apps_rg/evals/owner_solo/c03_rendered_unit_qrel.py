"""Validate the retrieval binding required to turn rendered resume units into QRELs.

This deliberately sits between the existing final-output review lane (which is
not a retrieval evaluation) and the old W3 graph-cluster packet (which is not
the owner's review unit).  It creates no embeddings, ranks, or human grades.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_PATH = Path("src/apps_rg/evals/owner_solo/c03_rendered_unit_qrel_contract.v1.json")
SCHEMA = "apps_rg.owner_solo_rendered_unit_qrel_registry.v1"
READY_SCHEMA = "apps_rg.owner_solo_rendered_unit_qrel_readiness.v1"
PACKET_SCHEMA = "apps_rg.owner_solo_rendered_unit_qrel_packet.v1"
PACKET_RECEIPT_SCHEMA = "apps_rg.owner_solo_rendered_unit_qrel_packet_receipt.v1"
EVENT_SCHEMA = "apps_rg.owner_solo_rendered_unit_qrel_event.v1"
FINAL_SCHEMA = "apps_rg.owner_solo_rendered_unit_qrels.v1"
RECONCILIATION_SCHEMA = "apps_rg.owner_solo_rendered_unit_qrel_prior_label_reconciliation.v1"
OWNER_IDENTITY = "human-reviewer://amit-owner"
GRADES = frozenset({0, 1, 2, 3})
_COMPETENCY_RENDERING_METHOD = "governed_competency_bundle_resume_surface.v3"
_COMPETENCY_DEDUP_RENDERING_METHOD = "governed_competency_bundle_resume_surface_dedup.v4"
_COMPETENCY_TOKEN_STOPWORDS = frozenset(
    {
        "a",
        "ai",
        "and",
        "architecture",
        "capabilities",
        "capability",
        "design",
        "engineering",
        "enterprise",
        "for",
        "in",
        "of",
        "platform",
        "the",
        "to",
        "with",
    }
)


class RenderedUnitQrelError(ValueError):
    """A rendered-unit retrieval registry is not safe to review."""


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderedUnitQrelError(f"JSON unavailable or malformed: {path}") from exc
    if not isinstance(value, dict):
        raise RenderedUnitQrelError(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderedUnitQrelError(f"JSONL unavailable or malformed: {path}") from exc
    if not all(isinstance(row, dict) for row in rows):
        raise RenderedUnitQrelError("JSONL must contain objects only")
    return rows


def _segment(text: str, start: str, endings: Sequence[str]) -> str:
    value = str(text or "")
    marker = start + ":"
    if marker not in value:
        return ""
    result = value.split(marker, 1)[1]
    for ending in endings:
        result = result.split(ending + ":", 1)[0]
    return " ".join(result.strip().split())


def _is_authoring_guidance(text: str) -> bool:
    """Distinguish graph-side composition instructions from résumé prose."""

    normalized = " ".join(str(text or "").strip().casefold().split())
    return normalized.startswith((
        "frame as ", "use only ", "write as ", "do not ", "metrics only ",
        "qualitative unless ", "avoid ", "only when ",
    ))


def _tokens(value: Any) -> set[str]:
    normalized = "".join(character.casefold() if character.isalnum() else " " for character in str(value or ""))
    return {token for token in normalized.split() if len(token) > 2 and token not in _COMPETENCY_TOKEN_STOPWORDS}


def _select_competency_bundle(
    cluster: Mapping[str, Any],
    competency_bundles: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Bind one graph retrieval unit to its governed resume competency family.

    The binding is target-independent and uses graph authority before prose:
    exact role-episode, skill-node, and fact identities dominate lexical
    alignment.  Lexical alignment is only a deterministic tie breaker for
    graph units whose older inventory lacks direct bundle edges.
    """

    cluster_role = str(cluster.get("role_episode_bundle_id") or "").strip()
    cluster_skills = {str(value) for value in cluster.get("member_node_ids") or [] if str(value)}
    cluster_facts = {str(value) for value in cluster.get("linked_fact_ids") or [] if str(value)}
    primary_anchor = str(cluster.get("primary_evidence_anchor_id") or "").strip()
    if primary_anchor:
        cluster_facts.add(primary_anchor)
    components = cluster.get("semantic_components") if isinstance(cluster.get("semantic_components"), Mapping) else {}
    cluster_words = _tokens(
        " ".join(
            [
                str(cluster.get("canonical_embedding_text") or ""),
                str(components.get("claim_scope") or ""),
                str(components.get("operating_context") or ""),
                " ".join(str(value) for value in components.get("concrete_capabilities") or []),
            ]
        )
    )
    ranked: list[tuple[tuple[int, int, int, int], str, Mapping[str, Any]]] = []
    for bundle in competency_bundles:
        if str(bundle.get("activation_status") or "") != "ACTIVE" or "competencies" not in (bundle.get("allowed_sections") or []):
            continue
        bundle_id = str(bundle.get("competency_bundle_id") or "").strip()
        label = str(bundle.get("display_label_candidate") or "").strip()
        anchors = [str(value).strip() for value in bundle.get("vocabulary_anchors") or [] if str(value).strip()]
        if not bundle_id or not label or not anchors:
            raise RenderedUnitQrelError("Active competency bundle lacks its final resume surface")
        role_matches = int(bool(cluster_role and cluster_role in {str(value) for value in bundle.get("role_episode_bindings") or []}))
        skill_matches = len(cluster_skills & {str(value) for value in bundle.get("graph_skill_node_ids") or []})
        fact_matches = len(cluster_facts & {str(value) for value in bundle.get("linked_source_fact_ids") or []})
        bundle_words = _tokens(
            " ".join(
                [
                    label,
                    str(bundle.get("capability_family") or ""),
                    str(bundle.get("base_rigor_family_match") or ""),
                    str(bundle.get("target_relevance_rationale") or ""),
                    " ".join(anchors),
                ]
            )
        )
        ranked.append(((role_matches, skill_matches, fact_matches, len(cluster_words & bundle_words)), bundle_id, bundle))
    if not ranked:
        raise RenderedUnitQrelError("No active governed competency bundles are available")
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    best_score, _best_id, best = ranked[0]
    if best_score == (0, 0, 0, 0):
        raise RenderedUnitQrelError(f"Graph cluster {cluster.get('cluster_id')} cannot bind to a governed competency bundle")
    return best


def _rendered_competency_unit(
    cluster: Mapping[str, Any],
    competency_bundles: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    bundle = _select_competency_bundle(cluster, competency_bundles)
    label = str(bundle["display_label_candidate"]).strip()
    terms = [str(value).strip() for value in bundle["vocabulary_anchors"] if str(value).strip()]
    return f"{label}: {', '.join(terms)}", str(bundle["competency_bundle_id"])


def _rendered_resume_unit(
    cluster: Mapping[str, Any],
    section_id: str,
    competency_bundles: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Deterministically project graph Action/Scope/Evidence into review prose.

    This is not an LLM rewrite: every token comes from the frozen cluster
    projection, letting the reviewer judge complete resume-shaped text while
    the stored vector remains bound to the original graph evidence unit.
    """
    components = cluster.get("semantic_components") if isinstance(cluster.get("semantic_components"), Mapping) else {}
    canonical = str(cluster.get("canonical_embedding_text") or "")
    action = str(components.get("claim_action") or _segment(canonical, "Action", ("Scope", "Outcome", "Operating context", "Capabilities", "Evidence"))).strip()
    outcome = str(components.get("claim_outcome") or _segment(canonical, "Outcome", ("Operating context", "Capabilities", "Evidence"))).strip()
    capabilities = components.get("concrete_capabilities") if isinstance(components.get("concrete_capabilities"), list) else []
    capability_text = "; ".join(str(value).strip() for value in capabilities if str(value).strip())
    if not action:
        raise RenderedUnitQrelError("Graph cluster has no Action text for rendered-unit projection")
    if section_id == "competencies":
        if competency_bundles is None:
            raise RenderedUnitQrelError("Competency review requires the governed competency-bundle registry")
        return _rendered_competency_unit(cluster, competency_bundles)[0]
    if section_id.endswith("_bullets"):
        # `claim_outcome` sometimes carries graph-side authoring guidance such
        # as “Frame as …” or a metric eligibility condition.  It helps the
        # generator compose a bullet, but it is not candidate résumé prose and
        # must never be shown to the human reviewer as part of that bullet.
        rendered_outcome = "" if _is_authoring_guidance(outcome) else outcome
        return "• " + action.rstrip(".") + (f"; {rendered_outcome.rstrip('.')}" if rendered_outcome and rendered_outcome != action else "") + "."
    if section_id in {"headline", "executive_summary"}:
        return action.rstrip(".") + (f". {outcome.rstrip('.')}" if outcome and outcome != action else ".")
    return action.rstrip(".") + "."


def _collapse_final_review_candidates(
    *,
    target_id: str,
    section_id: str,
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Create one question per distinct finished resume line for one target.

    Several graph clusters can produce the same visible output.  The human
    review unit is that finished output, so those clusters are aggregated
    behind one visible line. Its retrieval position is the earliest
    constituent cluster rank; every constituent identity remains sealed.
    """

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for candidate in candidates:
        text = str(candidate.get("complete_rendered_resume_unit") or "").strip()
        if not text:
            raise RenderedUnitQrelError("Rendered candidate lacks its final resume surface")
        grouped.setdefault(text, []).append(candidate)
    ordered = sorted(
        grouped.items(),
        key=lambda row: (
            min(int(candidate["frozen_rank"]) for candidate in row[1]),
            row[0],
        ),
    )
    collapsed: list[dict[str, Any]] = []
    for deduped_rank, (text, members) in enumerate(ordered, start=1):
        ranked_members = sorted(members, key=lambda row: (int(row["frozen_rank"]), str(row["rendered_unit_id"])))
        best = dict(ranked_members[0])
        cluster_ids = sorted({str(value) for row in ranked_members for value in row.get("graph_bundle_ids") or [] if str(value)})
        source_ids = sorted({str(value) for row in ranked_members for value in row.get("source_assertion_ids") or [] if str(value)})
        embedding_ids = [str(row.get("embedding_identity") or "") for row in ranked_members]
        original_ranks = [int(row["frozen_rank"]) for row in ranked_members]
        collapsed.append(
            {
                **best,
                "rendered_unit_id": "rendered-" + hashlib.sha256(
                    (target_id + "|" + section_id + "|" + text).encode("utf-8")
                ).hexdigest()[:24],
                "frozen_rank": deduped_rank,
                "best_constituent_frozen_rank": original_ranks[0],
                "constituent_frozen_ranks": original_ranks,
                "source_assertion_ids": source_ids,
                "graph_bundle_ids": cluster_ids,
                "supporting_embedding_identities": embedding_ids,
                "supporting_cluster_count": len(cluster_ids),
                "rendering_method": (
                    _COMPETENCY_DEDUP_RENDERING_METHOD
                    if section_id == "competencies"
                    else "deterministic_final_resume_surface_dedup.v4"
                ),
                "dedupe_rule": "one_identical_final_output_per_target_section_best_constituent_rank",
            }
        )
    return collapsed


def _collapse_competency_candidates(
    *,
    target_id: str,
    section_id: str,
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compatibility wrapper for the competency-specific review contract."""

    return _collapse_final_review_candidates(
        target_id=target_id,
        section_id=section_id,
        candidates=candidates,
    )


def materialize_registry_from_w3(
    *,
    reviewer_items: Sequence[Mapping[str, Any]],
    sealed_mapping: Mapping[str, Any],
    combined_registry: Mapping[str, Any],
    competency_registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the R1 rendered-unit registry from frozen W1C/W2/W3 artifacts.

    It conserves every existing W3 candidate and rank, but changes only the
    reviewer-visible representation from raw cluster prose to a deterministic,
    complete résumé-shaped Action/Scope/Evidence projection.
    """
    clusters = {str(row.get("cluster_id")): row for row in combined_registry.get("clusters") or [] if isinstance(row, Mapping)}
    competency_bundles = [row for row in competency_registry.get("bundles") or [] if isinstance(row, Mapping)]
    if not competency_bundles:
        raise RenderedUnitQrelError("Governed competency-bundle registry is unavailable")
    mapping_by_item = {str(row.get("item_ref")): row for row in sealed_mapping.get("items") or [] if isinstance(row, Mapping)}
    target_splits = {
        "brown_brown_svp_it_strategy_innovation": "CALIBRATION",
        "anthropic_manager_applied_ai_architecture_partnerships": "CALIBRATION",
        "neo4j_vp_product_management_agentic_ai": "CALIBRATION",
        "openai_partner_ade": "HOLDOUT",
        "truist_head_agentic_ai_engineering": "HOLDOUT",
        "aveva_distinguished_ai_tech_lead_initiatives": "HOLDOUT",
    }
    cases: list[dict[str, Any]] = []
    total = 0
    for item in reviewer_items:
        item_ref = str(item.get("item_ref") or "")
        sealed_item = mapping_by_item.get(item_ref)
        if not sealed_item:
            raise RenderedUnitQrelError("W3 reviewer item lacks a sealed identity mapping")
        target_id = str(sealed_item.get("query_id") or "")
        section_id = str(sealed_item.get("section_id") or "")
        by_ref = {str(row.get("candidate_ref")): row for row in sealed_item.get("candidates") or [] if isinstance(row, Mapping)}
        candidates: list[dict[str, Any]] = []
        for visible in item.get("candidates") or []:
            candidate_ref = str(visible.get("candidate_ref") or "")
            sealed_candidate = by_ref.get(candidate_ref)
            if not sealed_candidate:
                raise RenderedUnitQrelError("W3 reviewer candidate lacks a sealed identity mapping")
            cluster_id = str(sealed_candidate.get("cluster_id") or "")
            cluster = clusters.get(cluster_id)
            if not cluster:
                raise RenderedUnitQrelError("W3 candidate cluster is unavailable from W1C authority")
            text = _rendered_resume_unit(cluster, section_id, competency_bundles)
            competency_bundle_id = (
                _rendered_competency_unit(cluster, competency_bundles)[1]
                if section_id == "competencies"
                else None
            )
            embedding_text = str(cluster.get("canonical_embedding_text") or "")
            facts = [str(value) for value in cluster.get("linked_fact_ids") or [] if str(value)]
            anchor = str(cluster.get("primary_evidence_anchor_id") or "")
            if anchor and anchor not in facts: facts.append(anchor)
            candidates.append({
                "rendered_unit_id": f"rendered-{hashlib.sha256((target_id+'|'+section_id+'|'+cluster_id+'|'+text).encode('utf-8')).hexdigest()[:24]}",
                "complete_rendered_resume_unit": text,
                "final_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "embedding_text_sha256": hashlib.sha256(embedding_text.encode("utf-8")).hexdigest(),
                "embedding_identity": f"BAAI/bge-m3:graph_evidence_cluster:{cluster_id}",
                "frozen_ranking_identity_sha256": str(sealed_mapping.get("ranking_identity_sha256") or ""),
                "frozen_rank": sealed_candidate.get("frozen_rank"),
                "source_assertion_ids": facts,
                "graph_bundle_ids": [cluster_id],
                "rendering_method": _COMPETENCY_RENDERING_METHOD if competency_bundle_id else "deterministic_action_scope_evidence_projection.v2_final_resume_text_only",
                **({"competency_bundle_id": competency_bundle_id} if competency_bundle_id else {}),
            })
        candidates = _collapse_final_review_candidates(
            target_id=target_id,
            section_id=section_id,
            candidates=candidates,
        )
        cases.append({"target_id": target_id, "section_id": section_id, "target_context": str(item.get("target_context") or ""), "candidates": candidates})
        total += len(candidates)
    registry = {"schema_version": SCHEMA, "status": "FROZEN_FOR_BLINDED_REVIEW", "source": {"w3_ranking_identity_sha256": sealed_mapping.get("ranking_identity_sha256"), "review_unit_projection": "final_resume_surface.v4_unique_visible_questions", "competency_projection": _COMPETENCY_DEDUP_RENDERING_METHOD, "competency_registry_sha256": canonical_sha256(competency_registry)}, "targets": [{"target_id": target_id, "split": split} for target_id, split in target_splits.items()], "query_section_cases": cases, "candidate_judgment_count": total}
    return registry


def _normalise_review_text(value: str) -> str:
    """Normalize only presentation whitespace for an exact review-text check."""

    return " ".join(value.replace("•", "").strip().split()).casefold()


def _w8_candidate_cluster_ids(sealed_mapping: Mapping[str, Any]) -> dict[str, set[str]]:
    """Read candidate-to-cluster bindings from the old W8 sealed mapping.

    The prior workbook contains opaque W8 candidate references.  This helper
    restores only their immutable graph identity; it does not compare prose or
    infer relevance.
    """

    result: dict[str, set[str]] = {}
    raw_cohorts = sealed_mapping.get("cohorts")
    # W8 has one object keyed by reviewer; later packet formats may retain a
    # list of cohort objects.  Both carry the same immutable candidate binding.
    cohorts = [raw_cohorts] if isinstance(raw_cohorts, Mapping) else raw_cohorts
    if not isinstance(cohorts, list):
        raise RenderedUnitQrelError("W8 sealed mapping has no cohorts")
    for cohort in cohorts:
        if not isinstance(cohort, Mapping):
            raise RenderedUnitQrelError("W8 sealed mapping has malformed cohort")
        for reviewer_items in cohort.values():
            if not isinstance(reviewer_items, list):
                continue
            for item in reviewer_items:
                if not isinstance(item, Mapping):
                    raise RenderedUnitQrelError("W8 sealed mapping has malformed item")
                for candidate in item.get("candidates") or []:
                    if not isinstance(candidate, Mapping):
                        raise RenderedUnitQrelError("W8 sealed mapping has malformed candidate")
                    candidate_ref = str(candidate.get("candidate_ref") or "")
                    cluster_id = str(candidate.get("cluster_id") or "")
                    if not candidate_ref or not cluster_id:
                        raise RenderedUnitQrelError("W8 sealed mapping candidate binding is incomplete")
                    result.setdefault(candidate_ref, set()).add(cluster_id)
    return result


def reconcile_prior_labels(
    *,
    prior_reconciliation: Mapping[str, Any],
    registry: Mapping[str, Any],
    w8_sealed_mapping: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Preserve historical labels while preventing an invalid silent reuse.

    A historic grade becomes a retrieval QREL only if it was made against the
    exact frozen rendered resume unit.  A raw-cluster identity chain is useful
    provenance, but it is deliberately *not* a grade transfer because the
    reviewer saw a different unit of judgment.
    """

    prior_labels = prior_reconciliation.get("prior_labels")
    proposals = prior_reconciliation.get("proposals")
    if not isinstance(prior_labels, list) or not isinstance(proposals, list):
        raise RenderedUnitQrelError("Prior-label reconciliation must contain labels and proposals")
    if len(prior_labels) != len(proposals):
        raise RenderedUnitQrelError("Prior-label reconciliation count mismatch")
    repo_root = Path(__file__).resolve().parents[4]
    if validate_registry(registry, load_contract(repo_root)):
        raise RenderedUnitQrelError("Rendered-unit registry is not valid for reconciliation")

    prior_by_id: dict[int, Mapping[str, Any]] = {}
    for row in prior_labels:
        if not isinstance(row, Mapping):
            raise RenderedUnitQrelError("Prior-label reconciliation contains malformed label")
        calibration_id = row.get("calibration_id")
        grade = row.get("grade")
        if not isinstance(calibration_id, int) or isinstance(calibration_id, bool) or calibration_id in prior_by_id:
            raise RenderedUnitQrelError("Prior-label reconciliation calibration IDs are invalid")
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in GRADES:
            raise RenderedUnitQrelError("Prior-label reconciliation contains an invalid human grade")
        if not str(row.get("evidence_candidate") or "").strip() or not str(row.get("rationale") or "").strip():
            raise RenderedUnitQrelError("Prior-label reconciliation has an empty candidate or rationale")
        prior_by_id[calibration_id] = row

    rendered_units: list[dict[str, Any]] = []
    for case in _cases(registry):
        for candidate in case.get("candidates") or []:
            if isinstance(candidate, Mapping):
                rendered_units.append({
                    "target_id": str(case.get("target_id") or ""),
                    "section_id": str(case.get("section_id") or ""),
                    **dict(candidate),
                })
    exact_text_index: dict[str, list[dict[str, Any]]] = {}
    for unit in rendered_units:
        exact_text_index.setdefault(_normalise_review_text(str(unit["complete_rendered_resume_unit"])), []).append(unit)
    candidate_clusters = _w8_candidate_cluster_ids(w8_sealed_mapping)

    queue: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    grade_counts: Counter[int] = Counter()
    exact_final_unit_count = 0
    source_identity_confirmation_count = 0
    unbound_rubric_count = 0
    for proposal in proposals:
        if not isinstance(proposal, Mapping):
            raise RenderedUnitQrelError("Prior-label reconciliation contains malformed proposal")
        calibration_id = proposal.get("calibration_id")
        prior = prior_by_id.get(calibration_id) if isinstance(calibration_id, int) else None
        if prior is None:
            raise RenderedUnitQrelError("Prior-label proposal lacks a matching human label")
        grade_counts[int(prior["grade"])] += 1
        exact_matches = exact_text_index.get(_normalise_review_text(str(prior["evidence_candidate"])), [])
        if len(exact_matches) == 1:
            unit = exact_matches[0]
            exact_final_unit_count += 1
            queue.append({
                "confirmation_ref": f"prior-label-{calibration_id}",
                "reason": "EXACT_FINAL_RENDERED_UNIT_TEXT",
                "calibration_id": calibration_id,
                "prior_complete_review_text": prior["evidence_candidate"],
                "prior_grade": prior["grade"],
                "prior_rationale": prior["rationale"],
                "rendered_unit_id": unit["rendered_unit_id"],
                "current_complete_rendered_resume_unit": unit["complete_rendered_resume_unit"],
                "instruction": "Owner may explicitly import this unchanged final-unit grade; no automatic QREL event has been created.",
            })
            dispositions.append({"calibration_id": calibration_id, "status": "EXACT_FINAL_UNIT_OWNER_IMPORT_REQUIRED"})
            continue
        old_candidate_ref = str(proposal.get("candidate_ref") or "")
        cluster_ids = candidate_clusters.get(old_candidate_ref, set())
        matched_units = [
            unit for unit in rendered_units
            if unit["target_id"] == "brown_brown_svp_it_strategy_innovation"
            and unit["section_id"] == "competencies"
            and any(str(unit.get("embedding_identity") or "").endswith(":" + cluster_id) for cluster_id in cluster_ids)
        ]
        if len(matched_units) == 1 and str(proposal.get("status") or "") == "OWNER_CONFIRMATION_REQUIRED":
            unit = matched_units[0]
            source_identity_confirmation_count += 1
            queue.append({
                "confirmation_ref": f"prior-label-{calibration_id}",
                "reason": "SAME_GRAPH_EVIDENCE_DIFFERENT_REVIEW_UNIT",
                "calibration_id": calibration_id,
                "prior_complete_review_text": prior["evidence_candidate"],
                "prior_grade": prior["grade"],
                "prior_rationale": prior["rationale"],
                "current_complete_rendered_resume_unit": unit["complete_rendered_resume_unit"],
                "rendered_unit_id": unit["rendered_unit_id"],
                "instruction": "The source graph evidence is the same, but this is a different rendered resume unit. Re-rate the current complete unit; do not transfer the prior grade.",
            })
            dispositions.append({"calibration_id": calibration_id, "status": "SAME_EVIDENCE_RE_RATE_CURRENT_FINAL_UNIT"})
            continue
        unbound_rubric_count += 1
        dispositions.append({"calibration_id": calibration_id, "status": "HISTORICAL_RUBRIC_EXAMPLE_NO_FROZEN_RENDERED_UNIT_BINDING"})

    if len(dispositions) != len(prior_labels):
        raise RenderedUnitQrelError("Prior-label reconciliation did not conserve every human label")
    queue_unsigned = {
        "schema_version": "apps_rg.owner_solo_rendered_unit_qrel_prior_label_confirmation_queue.v1",
        "status": "OWNER_REVIEW_REQUIRED" if queue else "NO_CONFIRMATION_ACTIONS",
        "items": queue,
    }
    queue_result = {**queue_unsigned, "queue_sha256": canonical_sha256(queue_unsigned)}
    receipt_unsigned = {
        "schema_version": RECONCILIATION_SCHEMA,
        "status": "R2_PRIOR_LABELS_PRESERVED_REVIEW_UNIT_RECONCILED",
        "prior_label_source_sha256": canonical_sha256(prior_reconciliation),
        "rendered_unit_registry_sha256": canonical_sha256(registry),
        "w8_sealed_mapping_sha256": canonical_sha256(w8_sealed_mapping),
        "prior_human_label_count": len(prior_labels),
        "prior_grade_distribution": {str(grade): grade_counts[grade] for grade in sorted(GRADES)},
        "exact_final_unit_owner_import_candidates": exact_final_unit_count,
        "same_graph_evidence_re_rate_candidates": source_identity_confirmation_count,
        "historical_rubric_only_count": unbound_rubric_count,
        "formal_qrels_created": 0,
        "human_grades_transferred": False,
        "metrics_computable": False,
        "release_authorizing": False,
        "production_promotion_authorized": False,
        "dispositions": dispositions,
        "confirmation_queue_sha256": queue_result["queue_sha256"],
    }
    return {**receipt_unsigned, "receipt_sha256": canonical_sha256(receipt_unsigned)}, queue_result


def load_contract(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root)
    contract = _read_json(root / CONTRACT_PATH)
    if contract.get("schema_version") != "apps_rg.owner_solo_rendered_unit_qrel_contract.v1":
        raise RenderedUnitQrelError("Unexpected rendered-unit QREL contract")
    if contract.get("status") != "FROZEN":
        raise RenderedUnitQrelError("Rendered-unit QREL contract is not frozen")
    return contract


def validate_registry(registry: Mapping[str, Any], contract: Mapping[str, Any]) -> list[str]:
    """Return all structural defects without manufacturing any reviewer judgment."""

    issues: list[str] = []
    if registry.get("schema_version") != SCHEMA:
        issues.append("SCHEMA")
    if registry.get("status") != "FROZEN_FOR_BLINDED_REVIEW":
        issues.append("STATUS")
    targets = registry.get("targets")
    cases = registry.get("query_section_cases")
    if not isinstance(targets, list) or not isinstance(cases, list):
        return issues + ["TARGETS_OR_CASES"]
    expected = contract["required_scope"]
    target_ids = [str(row.get("target_id") or "") for row in targets if isinstance(row, dict)]
    if len(target_ids) != expected["target_count"] or set(target_ids) != set(expected["target_ids"]):
        issues.append("TARGET_SCOPE")
    splits = Counter(str(row.get("split") or "") for row in targets if isinstance(row, dict))
    if splits != Counter({"CALIBRATION": 3, "HOLDOUT": 3}):
        issues.append("TARGET_SPLITS")
    allowed_targets = set(expected["target_ids"])
    seen_cases: set[tuple[str, str]] = set()
    seen_units: set[str] = set()
    total_units = 0
    for case in cases:
        if not isinstance(case, dict):
            issues.append("MALFORMED_CASE")
            continue
        target_id = str(case.get("target_id") or "")
        section_id = str(case.get("section_id") or "")
        key = (target_id, section_id)
        if target_id not in allowed_targets or not section_id or key in seen_cases:
            issues.append("CASE_IDENTITY")
        seen_cases.add(key)
        candidates = case.get("candidates")
        if not str(case.get("target_context") or "").strip():
            issues.append("TARGET_CONTEXT")
        if not isinstance(candidates, list) or not candidates:
            issues.append("EMPTY_CANDIDATE_UNIVERSE")
            continue
        seen_case_text: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                issues.append("MALFORMED_CANDIDATE")
                continue
            unit_id = str(candidate.get("rendered_unit_id") or "")
            required_text = str(candidate.get("complete_rendered_resume_unit") or "").strip()
            required = (
                unit_id,
                required_text,
                str(candidate.get("final_text_sha256") or ""),
                str(candidate.get("embedding_text_sha256") or ""),
                str(candidate.get("embedding_identity") or ""),
                str(candidate.get("frozen_ranking_identity_sha256") or ""),
            )
            rank = candidate.get("frozen_rank")
            sources = candidate.get("source_assertion_ids")
            bundles = candidate.get("graph_bundle_ids")
            if not all(required) or not isinstance(sources, list) or not sources or not isinstance(bundles, list) or not bundles:
                issues.append("CANDIDATE_BINDING")
            if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
                issues.append("FROZEN_RANK")
            if required_text and hashlib.sha256(required_text.encode("utf-8")).hexdigest() != candidate.get("final_text_sha256"):
                issues.append("FINAL_TEXT_DIGEST")
            if unit_id in seen_units:
                issues.append("DUPLICATE_RENDERED_UNIT")
            if required_text in seen_case_text:
                issues.append("DUPLICATE_FINAL_REVIEW_UNIT")
            seen_case_text.add(required_text)
            seen_units.add(unit_id)
            total_units += 1
        ranks = [candidate.get("frozen_rank") for candidate in candidates if isinstance(candidate, dict)]
        if sorted(ranks) != list(range(1, len(candidates) + 1)):
            issues.append("RANK_CONSERVATION")
    if len(seen_cases) != expected["query_section_case_count"]:
        issues.append("CASE_DENOMINATOR")
    if total_units != int(registry.get("candidate_judgment_count") or -1):
        issues.append("CANDIDATE_DENOMINATOR")
    return sorted(set(issues))


def readiness_receipt(registry: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    issues = validate_registry(registry, contract)
    candidate_count = int(registry.get("candidate_judgment_count") or 0)
    receipt = {
        "schema_version": READY_SCHEMA,
        "status": "READY_FOR_BLINDED_OWNER_QREL_REVIEW" if not issues else "BLOCKED_RENDERED_UNIT_QREL_BINDING",
        "result_label": "OWNER_SOLO_PROVISIONAL",
        "review_unit": contract["review_unit"],
        "query_section_case_count": len(registry.get("query_section_cases") or []),
        "candidate_judgment_count": candidate_count,
        "completed_human_judgment_count": 0,
        "remaining_human_judgment_count": candidate_count,
        "registry_sha256": canonical_sha256(registry),
        "contract_sha256": canonical_sha256(contract),
        "issues": issues,
        "human_grades_created": False,
        "metrics_computable": False,
        "release_authorizing": False,
        "production_promotion_authorized": False,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def validate_registry_file(registry_path: Path | str, *, repo_root: Path | str) -> dict[str, Any]:
    contract = load_contract(repo_root)
    registry = _read_json(Path(registry_path))
    receipt = readiness_receipt(registry, contract)
    if receipt["status"] != "READY_FOR_BLINDED_OWNER_QREL_REVIEW":
        raise RenderedUnitQrelError("Rendered-unit QREL registry is blocked: " + ", ".join(receipt["issues"]))
    return receipt


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _cases(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    cases = registry.get("query_section_cases")
    if not isinstance(cases, list):
        raise RenderedUnitQrelError("Registry cases are unavailable")
    return [dict(case) for case in cases if isinstance(case, dict)]


def build_blinded_packet(registry: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create reviewer material and a separate sealed identity/ranking map.

    The caller is responsible for storing only the packet with the reviewer and
    retaining the sealed mapping in ignored local runtime storage.
    """
    issues = validate_registry(registry, contract)
    if issues:
        raise RenderedUnitQrelError("Rendered-unit registry is blocked: " + ", ".join(issues))
    registry_digest = canonical_sha256(registry)
    packet_items: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []
    for case in _cases(registry):
        case_key = f"{case['target_id']}|{case['section_id']}"
        item_ref = "item-" + hashlib.sha256((registry_digest + case_key).encode("utf-8")).hexdigest()[:24]
        visible_candidates: list[dict[str, str]] = []
        # Deterministic opaque ordering keeps the reviewer experience stable
        # without using the retrieval rank as presentation order.
        for candidate in sorted(case["candidates"], key=lambda row: hashlib.sha256((registry_digest + case_key + str(row["rendered_unit_id"])).encode("utf-8")).hexdigest()):
            unit_id = str(candidate["rendered_unit_id"])
            candidate_ref = "candidate-" + hashlib.sha256((registry_digest + case_key + unit_id).encode("utf-8")).hexdigest()[:24]
            visible_candidates.append({
                "candidate_ref": candidate_ref,
                "complete_rendered_resume_unit": str(candidate["complete_rendered_resume_unit"]),
            })
            mapping.append({
                "item_ref": item_ref, "candidate_ref": candidate_ref,
                "target_id": case["target_id"], "section_id": case["section_id"],
                "rendered_unit_id": unit_id, "frozen_rank": candidate["frozen_rank"],
                "frozen_ranking_identity_sha256": candidate["frozen_ranking_identity_sha256"],
            })
        packet_items.append({
            "item_ref": item_ref,
            "target_context": case["target_context"],
            "resume_section": case["section_id"],
            "candidates": visible_candidates,
        })
    packet_unsigned = {"schema_version": PACKET_SCHEMA, "status": "READY_FOR_BLINDED_OWNER_QREL_REVIEW", "registry_sha256": registry_digest, "items": packet_items}
    packet = {**packet_unsigned, "packet_sha256": canonical_sha256(packet_unsigned)}
    sealed_unsigned = {"schema_version": "apps_rg.owner_solo_rendered_unit_qrel_sealed_mapping.v1", "packet_sha256": packet["packet_sha256"], "registry_sha256": registry_digest, "mappings": mapping}
    sealed = {**sealed_unsigned, "sealed_mapping_sha256": canonical_sha256(sealed_unsigned)}
    return packet, sealed


def _visible_packet_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return {str(key).casefold() for key in value} | set().union(*(_visible_packet_keys(child) for child in value.values()))
    if isinstance(value, list):
        return set().union(*(_visible_packet_keys(child) for child in value)) if value else set()
    return set()


def validate_frozen_packet(*, registry: Mapping[str, Any], contract: Mapping[str, Any], packet: Mapping[str, Any], sealed_mapping: Mapping[str, Any]) -> list[str]:
    """Return any packet/sealed-map defect; reviewer content fails closed on leakage."""

    issues = validate_registry(registry, contract)
    expected_packet, expected_sealed = build_blinded_packet(registry, contract) if not issues else ({}, {})
    if expected_packet:
        expected_packet_unsigned = {**expected_packet, "status": "FROZEN_FOR_BLINDED_OWNER_QREL_REVIEW"}
        expected_packet_unsigned.pop("packet_sha256", None)
        expected_packet = {**expected_packet_unsigned, "packet_sha256": canonical_sha256(expected_packet_unsigned)}
        expected_sealed_unsigned = {**expected_sealed, "packet_sha256": expected_packet["packet_sha256"]}
        expected_sealed_unsigned.pop("sealed_mapping_sha256", None)
        expected_sealed = {**expected_sealed_unsigned, "sealed_mapping_sha256": canonical_sha256(expected_sealed_unsigned)}
    if packet.get("schema_version") != PACKET_SCHEMA or packet.get("status") != "FROZEN_FOR_BLINDED_OWNER_QREL_REVIEW":
        issues.append("PACKET_SCHEMA_OR_STATUS")
    unsigned_packet = {key: value for key, value in packet.items() if key != "packet_sha256"}
    if packet.get("packet_sha256") != canonical_sha256(unsigned_packet):
        issues.append("PACKET_DIGEST")
    if expected_packet and packet.get("packet_sha256") != expected_packet.get("packet_sha256"):
        issues.append("PACKET_REGISTRY_BINDING")
    forbidden = ("rank", "score", "split", "cluster", "embedding", "query_id", "target_id", "sealed")
    if any(token in key for key in _visible_packet_keys(packet) for token in forbidden):
        issues.append("REVIEWER_VISIBLE_LEAKAGE")
    mappings = sealed_mapping.get("mappings")
    unsigned_sealed = {key: value for key, value in sealed_mapping.items() if key != "sealed_mapping_sha256"}
    if sealed_mapping.get("sealed_mapping_sha256") != canonical_sha256(unsigned_sealed):
        issues.append("SEALED_MAPPING_DIGEST")
    if sealed_mapping.get("packet_sha256") != packet.get("packet_sha256") or sealed_mapping.get("registry_sha256") != canonical_sha256(registry):
        issues.append("SEALED_MAPPING_PACKET_BINDING")
    if not isinstance(mappings, list) or len(mappings) != int(registry.get("candidate_judgment_count") or -1):
        issues.append("SEALED_MAPPING_DENOMINATOR")
    if expected_sealed and sealed_mapping.get("sealed_mapping_sha256") != expected_sealed.get("sealed_mapping_sha256"):
        issues.append("SEALED_MAPPING_REGISTRY_BINDING")
    return sorted(set(issues))


def freeze_blinded_packet(*, registry: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Create the R3 reviewer packet plus its separately retained rank map."""

    packet, sealed_mapping = build_blinded_packet(registry, contract)
    # Mark this copy as frozen, then recompute the digest that every owner
    # return will bind to.  No human judgment is created by this operation.
    packet_unsigned = {**packet, "status": "FROZEN_FOR_BLINDED_OWNER_QREL_REVIEW"}
    packet_unsigned.pop("packet_sha256", None)
    packet = {**packet_unsigned, "packet_sha256": canonical_sha256(packet_unsigned)}
    sealed_unsigned = {**sealed_mapping, "packet_sha256": packet["packet_sha256"]}
    sealed_unsigned.pop("sealed_mapping_sha256", None)
    sealed_mapping = {**sealed_unsigned, "sealed_mapping_sha256": canonical_sha256(sealed_unsigned)}
    issues = validate_frozen_packet(registry=registry, contract=contract, packet=packet, sealed_mapping=sealed_mapping)
    if issues:
        raise RenderedUnitQrelError("Frozen reviewer packet is blocked: " + ", ".join(issues))
    receipt_unsigned = {
        "schema_version": PACKET_RECEIPT_SCHEMA,
        "status": "R3_FROZEN_BLINDED_REVIEW_PACKET_READY",
        "result_label": "OWNER_SOLO_PROVISIONAL",
        "registry_sha256": canonical_sha256(registry),
        "packet_sha256": packet["packet_sha256"],
        "sealed_mapping_sha256": sealed_mapping["sealed_mapping_sha256"],
        "query_section_case_count": len(packet["items"]),
        "candidate_judgment_count": sum(len(item["candidates"]) for item in packet["items"]),
        "reviewer_visible_fields": ["item_ref", "target_context", "resume_section", "candidate_ref", "complete_rendered_resume_unit"],
        "rank_score_split_graph_embedding_hidden": True,
        "human_grades_created": False,
        "release_authorizing": False,
        "production_promotion_authorized": False,
    }
    return packet, sealed_mapping, {**receipt_unsigned, "receipt_sha256": canonical_sha256(receipt_unsigned)}


def _active_events(events: Sequence[Mapping[str, Any]], *, packet: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    allowed = {(item["item_ref"], candidate["candidate_ref"]) for item in packet["items"] for candidate in item["candidates"]}
    active: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(events, 1):
        event = dict(raw)
        unsigned = {key: value for key, value in event.items() if key != "event_digest"}
        key = (str(event.get("item_ref") or ""), str(event.get("candidate_ref") or ""))
        grade = event.get("relevance_grade")
        if event.get("event_digest") != canonical_sha256(unsigned) or event.get("schema_version") != EVENT_SCHEMA or event.get("packet_sha256") != packet.get("packet_sha256") or event.get("owner_identity_ref") != OWNER_IDENTITY or key not in allowed or not isinstance(grade, int) or isinstance(grade, bool) or grade not in GRADES or not str(event.get("raw_human_rationale") or "").strip():
            raise RenderedUnitQrelError(f"Invalid human QREL ledger event {index}")
        prior = active.get(key)
        if event.get("event_type") == "OWNER_EXPLICIT_QREL_GRADE":
            if prior is not None or event.get("prior_event_id") is not None:
                raise RenderedUnitQrelError(f"Duplicate active judgment at event {index}")
        elif event.get("event_type") == "OWNER_QREL_CORRECTION":
            if prior is None or event.get("prior_event_id") != prior.get("event_id"):
                raise RenderedUnitQrelError(f"Invalid correction chain at event {index}")
        else:
            raise RenderedUnitQrelError(f"Unknown human QREL event type at event {index}")
        active[key] = event
    return active


def _packet_text_by_ref(packet: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    values: dict[tuple[str, str], str] = {}
    for item in packet.get("items") or []:
        if not isinstance(item, Mapping):
            raise RenderedUnitQrelError("Reviewer packet contains a malformed item")
        item_ref = str(item.get("item_ref") or "")
        for candidate in item.get("candidates") or []:
            if not isinstance(candidate, Mapping):
                raise RenderedUnitQrelError("Reviewer packet contains a malformed candidate")
            key = (item_ref, str(candidate.get("candidate_ref") or ""))
            text = str(candidate.get("complete_rendered_resume_unit") or "")
            if not all(key) or not text or key in values:
                raise RenderedUnitQrelError("Reviewer packet candidate identity is invalid")
            values[key] = text
    return values


def _sealed_rank_index(sealed_mapping: Mapping[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    rows = sealed_mapping.get("mappings")
    if not isinstance(rows, list):
        raise RenderedUnitQrelError("Sealed mapping is missing candidates")
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise RenderedUnitQrelError("Sealed mapping contains a malformed candidate")
        target_id, section_id, rank = str(row.get("target_id") or ""), str(row.get("section_id") or ""), row.get("frozen_rank")
        key = (target_id, section_id, rank) if isinstance(rank, int) and not isinstance(rank, bool) else None
        if not key or key in index:
            raise RenderedUnitQrelError("Sealed mapping rank identity is invalid")
        index[key] = dict(row)
    return index


def build_packet_successor_transition(
    *,
    predecessor_packet: Mapping[str, Any],
    predecessor_sealed_mapping: Mapping[str, Any],
    predecessor_events: Sequence[Mapping[str, Any]],
    successor_packet: Mapping[str, Any],
    successor_sealed_mapping: Mapping[str, Any],
    predecessor_active_events: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Preserve only byte-identical prior judgments across a corrected packet.

    This does not copy, rewrite, or manufacture a grade.  It records links to
    the original append-only events.  Any changed rendered text is excluded
    and must receive a new explicit human judgment.
    """

    predecessor_active = (
        {key: dict(value) for key, value in predecessor_active_events.items()}
        if predecessor_active_events is not None
        else _active_events(predecessor_events, packet=predecessor_packet)
    )
    old_rows = {(str(row["item_ref"]), str(row["candidate_ref"])): row for row in predecessor_sealed_mapping.get("mappings") or [] if isinstance(row, Mapping)}
    new_rows_by_rank = _sealed_rank_index(successor_sealed_mapping)
    old_text = _packet_text_by_ref(predecessor_packet)
    new_text = _packet_text_by_ref(successor_packet)
    new_rows_by_final_surface: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in successor_sealed_mapping.get("mappings") or []:
        if not isinstance(row, Mapping):
            continue
        row_key = (str(row.get("item_ref") or ""), str(row.get("candidate_ref") or ""))
        rendered = new_text.get(row_key)
        if rendered:
            new_rows_by_final_surface.setdefault(
                (str(row.get("target_id") or ""), str(row.get("section_id") or ""), rendered),
                [],
            ).append(dict(row))
    carried: list[dict[str, Any]] = []
    regrade: list[dict[str, Any]] = []
    redundant_duplicates: list[dict[str, Any]] = []
    conflicting_duplicates: list[dict[str, Any]] = []
    changed_rendered_unit_count = 0
    candidate_records: dict[tuple[str, str], list[tuple[dict[str, Any], Mapping[str, Any]]]] = {}
    for old_key, event in predecessor_active.items():
        old_row = old_rows.get(old_key)
        if old_row is None:
            raise RenderedUnitQrelError("Prior owner event lacks a sealed mapping")
        target_id = str(old_row.get("target_id") or "")
        section_id = str(old_row.get("section_id") or "")
        matches = new_rows_by_final_surface.get((target_id, section_id, old_text[old_key]), [])
        if len(matches) == 1:
            new_row = matches[0]
        elif len(matches) > 1:
            raise RenderedUnitQrelError("Successor packet repeats an identical final review unit")
        else:
            rank_key = (target_id, section_id, old_row.get("frozen_rank"))
            new_row = new_rows_by_rank.get(rank_key)
        if new_row is None:
            raise RenderedUnitQrelError("Successor packet does not conserve prior candidate rank identity")
        new_key = (str(new_row.get("item_ref") or ""), str(new_row.get("candidate_ref") or ""))
        if new_key not in new_text:
            raise RenderedUnitQrelError("Successor packet mapping has no reviewer-visible candidate")
        record = {
            "successor_item_ref": new_key[0],
            "successor_candidate_ref": new_key[1],
            "predecessor_event_id": event["event_id"],
            "predecessor_event_digest": event["event_digest"],
            "predecessor_item_ref": old_key[0],
            "predecessor_candidate_ref": old_key[1],
            "predecessor_final_text_sha256": hashlib.sha256(old_text[old_key].encode("utf-8")).hexdigest(),
            "successor_final_text_sha256": hashlib.sha256(new_text[new_key].encode("utf-8")).hexdigest(),
        }
        candidate_records.setdefault(new_key, []).append((record, event))
    for records_and_events in candidate_records.values():
        if len(records_and_events) == 1:
            record, _event = records_and_events[0]
            if record["predecessor_final_text_sha256"] == record["successor_final_text_sha256"]:
                carried.append(record)
            else:
                changed_rendered_unit_count += 1
                regrade.append(record)
            continue
        signatures = {
            (event.get("relevance_grade"), str(event.get("raw_human_rationale") or ""))
            for _record, event in records_and_events
        }
        ordered_records = sorted(
            records_and_events,
            key=lambda value: (str(value[1].get("recorded_at_utc") or ""), str(value[1].get("event_id") or "")),
        )
        if len(signatures) == 1:
            carried.append(ordered_records[0][0])
            redundant_duplicates.extend(record for record, _event in ordered_records[1:])
        else:
            regrade.append(ordered_records[0][0])
            conflicting_duplicates.append(
                {
                    "successor_item_ref": ordered_records[0][0]["successor_item_ref"],
                    "successor_candidate_ref": ordered_records[0][0]["successor_candidate_ref"],
                    "predecessor_events": [
                        {"event_id": event["event_id"], "event_digest": event["event_digest"]}
                        for _record, event in ordered_records
                    ],
                    "reason": "CONFLICTING_HUMAN_GRADES_FOR_DUPLICATE_VISIBLE_QUESTION",
                }
            )
    if len({(row["successor_item_ref"], row["successor_candidate_ref"]) for row in carried + regrade}) != len(carried) + len(regrade):
        raise RenderedUnitQrelError("Successor transition does not conserve unique review identities")
    unsigned = {
        "schema_version": "apps_rg.owner_solo_rendered_unit_qrel_packet_successor_transition.v1",
        "status": "R4_FINAL_RESUME_SURFACE_SUCCESSOR_READY",
        "predecessor_packet_sha256": predecessor_packet.get("packet_sha256"),
        "predecessor_sealed_mapping_sha256": predecessor_sealed_mapping.get("sealed_mapping_sha256"),
        "successor_packet_sha256": successor_packet.get("packet_sha256"),
        "successor_sealed_mapping_sha256": successor_sealed_mapping.get("sealed_mapping_sha256"),
        "preserved_prior_event_count": len(predecessor_active),
        "byte_identical_carried_forward_count": len(carried),
        "prior_events_requiring_explicit_regrade_count": len(regrade),
        "redundant_duplicate_prior_event_count": len(redundant_duplicates),
        "conflicting_duplicate_successor_question_count": len(conflicting_duplicates),
        "changed_rendered_unit_count_among_prior_events": changed_rendered_unit_count,
        "human_grades_created": False,
        "human_grades_transferred": False,
        "carried_forward_links": carried,
        "regrade_required_links": regrade,
        "redundant_duplicate_links": redundant_duplicates,
        "conflicting_duplicate_links": conflicting_duplicates,
        "release_authorizing": False,
        "production_promotion_authorized": False,
    }
    return {**unsigned, "transition_sha256": canonical_sha256(unsigned)}


def transition_carried_forward_events(
    *,
    transition: Mapping[str, Any],
    predecessor_packet: Mapping[str, Any],
    predecessor_events: Sequence[Mapping[str, Any]],
    successor_packet: Mapping[str, Any],
    predecessor_active_events: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Resolve old immutable events that remain valid for byte-identical text."""

    unsigned = {key: value for key, value in transition.items() if key != "transition_sha256"}
    allowed_statuses = {"R4_FINAL_BULLET_SUCCESSOR_READY", "R4_FINAL_RESUME_SURFACE_SUCCESSOR_READY"}
    if transition.get("transition_sha256") != canonical_sha256(unsigned) or transition.get("status") not in allowed_statuses:
        raise RenderedUnitQrelError("Successor transition is malformed")
    if transition.get("predecessor_packet_sha256") != predecessor_packet.get("packet_sha256") or transition.get("successor_packet_sha256") != successor_packet.get("packet_sha256"):
        raise RenderedUnitQrelError("Successor transition packet binding is invalid")
    predecessor_active = (
        {key: dict(value) for key, value in predecessor_active_events.items()}
        if predecessor_active_events is not None
        else _active_events(predecessor_events, packet=predecessor_packet)
    )
    by_event = {str(event["event_id"]): event for event in predecessor_active.values()}
    carried: dict[tuple[str, str], dict[str, Any]] = {}
    for row in transition.get("carried_forward_links") or []:
        if not isinstance(row, Mapping):
            raise RenderedUnitQrelError("Successor transition contains a malformed carry-forward link")
        event = by_event.get(str(row.get("predecessor_event_id") or ""))
        key = (str(row.get("successor_item_ref") or ""), str(row.get("successor_candidate_ref") or ""))
        if event is None or event.get("event_digest") != row.get("predecessor_event_digest") or not all(key) or key in carried:
            raise RenderedUnitQrelError("Successor transition carry-forward proof is invalid")
        carried[key] = event
    return carried


def resolved_active_events(
    *,
    successor_packet: Mapping[str, Any],
    successor_events: Sequence[Mapping[str, Any]],
    transition: Mapping[str, Any] | None = None,
    predecessor_packet: Mapping[str, Any] | None = None,
    predecessor_events: Sequence[Mapping[str, Any] | None] = (),
    predecessor_active_events: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Combine new events with byte-identical predecessor events, fail closed on overlap."""

    active = _active_events(successor_events, packet=successor_packet)
    if transition is None:
        return active
    if predecessor_packet is None:
        raise RenderedUnitQrelError("Successor transition requires predecessor packet and events")
    carried = transition_carried_forward_events(
        transition=transition,
        predecessor_packet=predecessor_packet,
        predecessor_events=[row for row in predecessor_events if isinstance(row, Mapping)],
        successor_packet=successor_packet,
        predecessor_active_events=predecessor_active_events,
    )
    if set(active) & set(carried):
        raise RenderedUnitQrelError("A carried-forward judgment cannot be silently overwritten")
    return {**carried, **active}


def append_human_judgments(ledger_path: Path | str, *, packet: Mapping[str, Any], submissions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    path = Path(ledger_path)
    existing = _read_jsonl(path) if path.exists() else []
    active = _active_events(existing, packet=packet)
    allowed = {(item["item_ref"], candidate["candidate_ref"]) for item in packet["items"] for candidate in item["candidates"]}
    appended: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for submission in submissions:
        key = (str(submission.get("item_ref") or ""), str(submission.get("candidate_ref") or ""))
        grade = submission.get("grade")
        rationale = str(submission.get("rationale") or "").strip()
        if key not in allowed or key in active or key in seen or not isinstance(grade, int) or isinstance(grade, bool) or grade not in GRADES or not rationale:
            raise RenderedUnitQrelError("Every saved QREL return must be a new explicit 0-3 grade with rationale")
        unsigned = {"schema_version": EVENT_SCHEMA, "event_id": f"owner-solo-rendered-unit-qrel-{uuid.uuid4()}", "event_type": "OWNER_EXPLICIT_QREL_GRADE", "recorded_at_utc": _now(), "owner_identity_ref": OWNER_IDENTITY, "packet_sha256": packet["packet_sha256"], "item_ref": key[0], "candidate_ref": key[1], "relevance_grade": grade, "raw_human_rationale": rationale, "prior_event_id": None, "release_authorizing": False}
        appended.append({**unsigned, "event_digest": canonical_sha256(unsigned)})
        seen.add(key)
    if not appended:
        raise RenderedUnitQrelError("No human QREL returns supplied")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for event in appended:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush(); os.fsync(handle.fileno())
    return appended


def finalize_owner_solo_qrels(*, registry: Mapping[str, Any], contract: Mapping[str, Any], packet: Mapping[str, Any], sealed_mapping: Mapping[str, Any], events: Sequence[Mapping[str, Any]], active_events: Mapping[tuple[str, str], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Finalize only a complete owner-solo QREL set and compute deterministic metrics."""
    if validate_registry(registry, contract):
        raise RenderedUnitQrelError("Cannot finalize an invalid rendered-unit registry")
    active = dict(active_events) if active_events is not None else _active_events(events, packet=packet)
    mappings = sealed_mapping.get("mappings")
    if not isinstance(mappings, list) or len(active) != len(mappings):
        raise RenderedUnitQrelError("Cannot finalize before every frozen candidate has one active human grade")
    map_by_ref = {(row["item_ref"], row["candidate_ref"]): row for row in mappings}
    qrels: list[dict[str, Any]] = []
    for key, event in active.items():
        row = map_by_ref.get(key)
        if row is None:
            raise RenderedUnitQrelError("Sealed mapping does not conserve owner returns")
        qrels.append({"target_id": row["target_id"], "section_id": row["section_id"], "rendered_unit_id": row["rendered_unit_id"], "relevance_grade": event["relevance_grade"], "frozen_rank": row["frozen_rank"]})
    by_case: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in qrels: by_case.setdefault((row["target_id"], row["section_id"]), []).append(row)
    per_case = []
    for key, rows in sorted(by_case.items()):
        rows.sort(key=lambda row: int(row["frozen_rank"]))
        relevant = [row for row in rows if row["relevance_grade"] >= 2]
        recall = (sum(row["relevance_grade"] >= 2 for row in rows[:10]) / len(relevant)) if relevant else 1.0
        gains = [2 ** int(row["relevance_grade"]) - 1 for row in rows[:10]]
        dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
        ideal = sorted((2 ** int(row["relevance_grade"]) - 1 for row in rows), reverse=True)[:10]
        idcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal))
        first = next((index for index, row in enumerate(rows, 1) if row["relevance_grade"] >= 2), None)
        per_case.append({"target_id": key[0], "section_id": key[1], "recall_at_10": recall, "ndcg_at_10": dcg / idcg if idcg else 1.0, "mrr": 1 / first if first else 0.0})
    result = {"schema_version": FINAL_SCHEMA, "status": "FROZEN_OWNER_SOLO_PROVISIONAL", "result_label": "OWNER_SOLO_PROVISIONAL — NOT INDEPENDENT RELEASE EVIDENCE", "qrel_count": len(qrels), "qrels": sorted(qrels, key=lambda row: (row["target_id"], row["section_id"], row["frozen_rank"])), "metrics": {"per_case": per_case, "macro_recall_at_10": sum(row["recall_at_10"] for row in per_case) / len(per_case), "macro_ndcg_at_10": sum(row["ndcg_at_10"] for row in per_case) / len(per_case), "macro_mrr": sum(row["mrr"] for row in per_case) / len(per_case)}, "one_human_reviewer": True, "independent_reviewer_present": False, "independent_adjudicator_present": False, "release_authorizing": False, "production_promotion_authorized": False, "packet_sha256": packet["packet_sha256"], "sealed_mapping_sha256": sealed_mapping.get("sealed_mapping_sha256"), "registry_sha256": canonical_sha256(registry)}
    result["artifact_sha256"] = canonical_sha256(result)
    return result


__all__ = [
    "CONTRACT_PATH", "READY_SCHEMA", "RenderedUnitQrelError", "canonical_sha256",
    "OWNER_IDENTITY", "RECONCILIATION_SCHEMA", "RenderedUnitQrelError", "append_human_judgments", "build_blinded_packet", "build_packet_successor_transition", "canonical_sha256", "finalize_owner_solo_qrels", "freeze_blinded_packet", "load_contract", "materialize_registry_from_w3", "readiness_receipt", "reconcile_prior_labels", "resolved_active_events", "transition_carried_forward_events", "validate_frozen_packet", "validate_registry", "validate_registry_file",
]
