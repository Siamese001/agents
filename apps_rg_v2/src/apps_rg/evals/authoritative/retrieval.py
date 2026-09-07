"""G1 measurement over independently pinned universes, rankings, and QRELs."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from apps_rg.evals.resume_graph.metrics.retrieval import (
    evaluate_retrieval_gate,
    seal_retrieval_query,
)

from .artifacts import (
    load_human_authority_receipt,
    seal_record,
    validate_authorized_reviewer,
    validate_label_review_coverage,
    validate_pinned_record,
)

UNIVERSE_SCHEMA = "apps_rg.authoritative_candidate_universe.v1"
RANKING_SCHEMA = "apps_rg.authoritative_system_ranking.v1"
QRELS_SCHEMA = "apps_rg.authoritative_retrieval_qrels.v1"
RECEIPT_SCHEMA = "apps_rg.authoritative_retrieval_receipt.v1"


def _unknown(reasons: Sequence[str]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": RECEIPT_SCHEMA,
            "gate_id": "G1",
            "score_groups": ["retrieval_quality"],
            "status": "UNKNOWN",
            "metrics": {},
            "query_results": [],
            "slices": {},
            "input_digests": {},
            "failure_codes": [],
            "unknown_reasons": sorted(set(reasons)),
            "authority": {
                "measurement_scope": "SOURCE_BOUND_SYSTEM_VS_QRELS",
                "human_authority_verified": False,
                "release_authorizing": False,
            },
        }
    )


def _candidate_index(value: Any, *, label: str, reasons: list[str]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        reasons.append(f"{label}_EMPTY")
        return {}
    index: dict[str, Mapping[str, Any]] = {}
    for row in value:
        if not isinstance(row, Mapping):
            reasons.append(f"{label}_ROW_INVALID")
            continue
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id or candidate_id in index:
            reasons.append(f"{label}_IDENTITY_INVALID")
            continue
        index[candidate_id] = row
    return index


def _build_query(
    universe: Mapping[str, Any],
    ranking: Mapping[str, Any],
    qrels: Mapping[str, Any],
    *,
    k_values: Sequence[int],
) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    if not (
        universe.get("query_id") == ranking.get("query_id") == qrels.get("query_id")
        and ranking.get("universe_digest") == universe.get("record_digest")
        and qrels.get("universe_digest") == universe.get("record_digest")
    ):
        reasons.append("RETRIEVAL_ARTIFACT_BINDING_MISMATCH")
    universe_rows = _candidate_index(universe.get("candidates"), label="UNIVERSE", reasons=reasons)
    ranking_rows = _candidate_index(ranking.get("ranking"), label="RANKING", reasons=reasons)
    qrel_rows = _candidate_index(qrels.get("labels"), label="QRELS", reasons=reasons)
    expected_ids = set(universe_rows)
    if set(ranking_rows) != expected_ids:
        reasons.append("SYSTEM_RANKING_NOT_FULL_UNIVERSE")
    if set(qrel_rows) != expected_ids:
        reasons.append("QRELS_NOT_FULL_UNIVERSE")
    try:
        ordered_ranking = sorted(
            ranking_rows.values(), key=lambda row: int(row.get("rank") or 0)
        )
    except (TypeError, ValueError):
        reasons.append("SYSTEM_RANKS_INVALID")
        ordered_ranking = []
    if [row.get("rank") for row in ordered_ranking] != list(range(1, len(ordered_ranking) + 1)):
        reasons.append("SYSTEM_RANKS_NOT_CONTIGUOUS")
    if reasons:
        return None, sorted(set(reasons))

    candidates: list[dict[str, Any]] = []
    for rank_row in ordered_ranking:
        candidate_id = str(rank_row["candidate_id"])
        source = universe_rows[candidate_id]
        truth = qrel_rows[candidate_id]
        expected_path = truth.get("expected_graph_path")
        observed_path = source.get("graph_path")
        path_binding = "EXACT" if observed_path == expected_path else "MISMATCH"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "rank": rank_row["rank"],
                "score": rank_row["score"],
                "relevance_grade": truth["relevance_grade"],
                "path_binding": path_binding,
                "graph_path": observed_path,
                "employer": source["employer"],
                "role": source["role"],
                "evidence_type": source["evidence_type"],
                "jd_concepts": truth.get("jd_concepts", []),
                "claim_ids": truth.get("claim_ids", []),
                "metric_bearing": bool(source.get("metric_bearing")),
                "critical_hard_negative": bool(truth.get("critical_hard_negative")),
                "hard_negative_class": truth.get("hard_negative_class", "NONE"),
                "near_duplicate_of": truth.get("near_duplicate_of"),
            }
        )
    query = {
        "schema_version": "apps_rg.retrieval_universe.v1",
        "query_id": universe["query_id"],
        "query_text": universe["query_text"],
        "target_profile": universe["target_profile"],
        "section": universe["section"],
        "graph_lane": universe["graph_lane"],
        "employer": universe["employer"],
        "evidence_density": universe["evidence_density"],
        "split": ranking["split"],
        "judging_scope": "FULL_FINITE_UNIVERSE",
        "candidate_count": len(candidates),
        "candidate_universe": {
            "authority": "FROZEN_HUMAN_LABELLED",
            "candidate_ids": sorted(expected_ids),
            "candidate_count": len(expected_ids),
            "manifest_digest": "",
        },
        "k_values": sorted(set(k_values)),
        "gate_k": ranking["gate_k"],
        "candidates": candidates,
        "query_digest": "",
    }
    return seal_retrieval_query(query), []


def evaluate_authoritative_retrieval(
    cases: Sequence[Mapping[str, Any]],
    *,
    authority_receipt_path: Any,
    expected_authority_file_sha256: str,
    positive_floor: float = 2.0,
    k_values: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, Any]:
    """Compare system rankings with externally pinned candidate universes and QRELs."""

    authority, roster, reasons = load_human_authority_receipt(
        authority_receipt_path,
        expected_file_sha256=expected_authority_file_sha256,
    )
    if not cases:
        reasons.append("AUTHORITATIVE_RETRIEVAL_CASES_EMPTY")
    queries: list[dict[str, Any]] = []
    input_digests: dict[str, dict[str, str]] = {}
    for index, case in enumerate(cases):
        universe = case.get("universe")
        ranking = case.get("ranking")
        qrels = case.get("qrels")
        for label, value, schema in (
            ("universe", universe, UNIVERSE_SCHEMA),
            ("ranking", ranking, RANKING_SCHEMA),
            ("qrels", qrels, QRELS_SCHEMA),
        ):
            reasons.extend(
                f"case[{index}]::{reason}"
                for reason in validate_pinned_record(
                    value,
                    expected_digest=str(case.get(f"expected_{label}_digest") or ""),
                    schema_version=schema,
                )
            )
        if not all(isinstance(value, Mapping) for value in (universe, ranking, qrels)):
            continue
        if qrels.get("authority_receipt_file_sha256") != expected_authority_file_sha256:
            reasons.append(f"case[{index}]::QRELS_AUTHORITY_BINDING_MISMATCH")
        reviewers = qrels.get("reviewer_identity_refs")
        if (
            not isinstance(reviewers, list)
            or any(not isinstance(reviewer, str) or not reviewer for reviewer in reviewers)
            or len(set(reviewers)) < 2
        ):
            reasons.append(f"case[{index}]::QRELS_TWO_REVIEWERS_REQUIRED")
            reviewers = []
        for reviewer in reviewers:
            reasons.extend(
                f"case[{index}]::{reason}"
                for reason in validate_authorized_reviewer(
                    identity_ref=str(reviewer),
                    qualification_ref=None,
                    cohort="retrieval",
                    role="primary",
                    roster=roster,
                )
            )
        adjudicator = str(qrels.get("adjudicator_identity_ref") or "")
        reasons.extend(
            f"case[{index}]::{reason}"
            for reason in validate_authorized_reviewer(
                identity_ref=adjudicator,
                qualification_ref=None,
                cohort="retrieval",
                role="adjudicator",
                roster=roster,
            )
        )
        for label in qrels.get("labels") or []:
            if not isinstance(label, Mapping):
                continue
            reasons.extend(
                f"case[{index}]::{reason}"
                for reason in validate_label_review_coverage(
                    label,
                    reviewer_identity_refs=[str(reviewer) for reviewer in reviewers],
                    adjudicator_identity_ref=adjudicator,
                )
            )
        try:
            query, query_reasons = _build_query(
                universe,
                ranking,
                qrels,
                k_values=k_values,
            )
        except (KeyError, TypeError, ValueError):
            query, query_reasons = None, ["RETRIEVAL_ARTIFACT_CONTENT_INVALID"]
        reasons.extend(f"case[{index}]::{reason}" for reason in query_reasons)
        if query is not None:
            queries.append(query)
            input_digests[str(universe.get("query_id") or index)] = {
                "universe": str(universe.get("record_digest")),
                "ranking": str(ranking.get("record_digest")),
                "qrels": str(qrels.get("record_digest")),
            }
    if reasons:
        return _unknown(reasons)
    result = evaluate_retrieval_gate(queries, positive_floor=positive_floor)
    return seal_record(
        {
            "schema_version": RECEIPT_SCHEMA,
            "gate_id": "G1",
            "score_groups": ["retrieval_quality"],
            "status": result["status"],
            "metrics": result["metrics"],
            "query_results": result["query_results"],
            "slices": result["slices"],
            "input_digests": input_digests,
            "failure_codes": result["failure_codes"],
            "unknown_reasons": result["unknown_reasons"],
            "authority": {
                "measurement_scope": "SOURCE_BOUND_SYSTEM_VS_QRELS",
                "authority_receipt_digest": authority.get("receipt_digest"),
                "authority_receipt_file_sha256": expected_authority_file_sha256,
                "human_authority_verified": True,
                "release_authorizing": False,
            },
        }
    )


__all__ = [
    "QRELS_SCHEMA",
    "RANKING_SCHEMA",
    "RECEIPT_SCHEMA",
    "UNIVERSE_SCHEMA",
    "evaluate_authoritative_retrieval",
]
