"""Source-bound W1 evaluation contracts for graph-evidence cluster retrieval."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any

from apps_rg.evals.resume_graph.reporting import canonical_digest

from .artifacts import HEX64, seal_record, validate_pinned_record
from .retrieval import evaluate_authoritative_retrieval

CLUSTER_UNIVERSE_SCHEMA = "apps_rg.authoritative_cluster_candidate_universe.v1"
CLUSTER_RANKING_SCHEMA = "apps_rg.authoritative_cluster_system_ranking.v1"
CLUSTER_QRELS_SCHEMA = "apps_rg.authoritative_cluster_retrieval_qrels.v1"
CLUSTER_THRESHOLD_POLICY_SCHEMA = (
    "apps_rg.authoritative_cluster_retrieval_threshold_policy.v1"
)
CLUSTER_RECEIPT_SCHEMA = "apps_rg.authoritative_cluster_retrieval_receipt.v1"
LOGICAL_RETRIEVAL_UNIT = "graph_evidence_cluster"
QUALIFICATION_SCOPE = "EVAL_W1_CONTRACT_ONLY"

_STATIC_BINDING_FIELDS = frozenset(
    {
        "graph_sha256",
        "cluster_registry_sha256",
        "corpus_sha256",
        "model_artifact_sha256",
        "projection_sha256",
        "runtime_config_sha256",
    }
)
_CASE_BINDING_FIELDS = _STATIC_BINDING_FIELDS | {"query_sha256"}
_BINDING_FIELDS_WITH_ENVELOPE = _CASE_BINDING_FIELDS | {
    "authority_envelope_sha256"
}
_THRESHOLD_BINDING_FIELDS = _STATIC_BINDING_FIELDS | {"authority_envelope_sha256"}
_LEGACY_ID_FIELDS = frozenset({"candidate_id", "assertion_id", "skill_id"})
_CLUSTER_KINDS = frozenset({"role_episode", "capability_evidence"})
_LIFECYCLE_STATES = frozenset(
    {"DRAFT", "HELD", "ACTIVE", "ACTIVE_CONFIRMED", "RETIRED"}
)
_HARD_NEGATIVE_CLASSES = frozenset(
    {
        "NONE",
        "WRONG_EMPLOYER",
        "WRONG_ROLE",
        "WRONG_DATE",
        "METRIC_SEMANTIC_MISMATCH",
        "SCOPE_MISMATCH",
        "PROJECTED_NOT_ACHIEVED",
        "JD_ONLY_NO_EVIDENCE",
        "DUPLICATE_GRAPH_PATH",
    }
)
_UNIVERSE_FIELDS = frozenset(
    {
        "schema_version",
        "query_id",
        "query_text",
        "target_profile",
        "section",
        "graph_lane",
        "employer",
        "evidence_density",
        "logical_retrieval_unit",
        "authority_bindings",
        "clusters",
        "record_digest",
    }
)
_CLUSTER_FIELDS = frozenset(
    {
        "cluster_id",
        "cluster_kind",
        "cluster_authority_envelope_sha256",
        "member_node_ids",
        "linked_fact_ids",
        "allowed_sections",
        "activation_status",
        "external_claim_policy",
        "graph_path",
        "employer",
        "role",
        "evidence_type",
        "metric_bearing",
    }
)
_RANKING_FIELDS = frozenset(
    {
        "schema_version",
        "query_id",
        "universe_digest",
        "logical_retrieval_unit",
        "authority_bindings",
        "split",
        "gate_k",
        "ranking",
        "record_digest",
    }
)
_RANKING_ROW_FIELDS = frozenset({"cluster_id", "rank", "score"})
_QRELS_FIELDS = frozenset(
    {
        "schema_version",
        "query_id",
        "universe_digest",
        "logical_retrieval_unit",
        "authority_bindings",
        "authority_receipt_file_sha256",
        "reviewer_identity_refs",
        "adjudicator_identity_ref",
        "labels",
        "record_digest",
    }
)
_LABEL_FIELDS = frozenset(
    {
        "cluster_id",
        "reviewer_identity_refs",
        "adjudication_status",
        "adjudicator_identity_ref",
        "relevance_grade",
        "expected_graph_path",
        "critical_hard_negative",
        "hard_negative_class",
        "near_duplicate_cluster_id",
        "jd_concepts",
        "claim_ids",
    }
)
_THRESHOLD_FIELDS = frozenset(
    {
        "schema_version",
        "logical_retrieval_unit",
        "runtime_top_k",
        "positive_relevance_floor",
        "metric_thresholds",
        "authority_bindings",
        "record_digest",
    }
)
_REQUIRED_METRIC_THRESHOLDS = frozenset(
    {
        "recall_at_runtime_k_minimum",
        "ndcg_at_runtime_k_minimum",
        "mrr_minimum",
        "hard_negative_rejection_rate_minimum",
        "top_k_redundancy_rate_maximum",
    }
)


def seal_cluster_authority_bindings(value: Mapping[str, str]) -> dict[str, str]:
    """Seal static or query-specific evaluation bindings."""

    sealed = dict(value)
    sealed.pop("authority_envelope_sha256", None)
    sealed["authority_envelope_sha256"] = canonical_digest(sealed)
    return sealed


def _has_legacy_identity(value: Mapping[str, Any]) -> bool:
    return bool(set(value) & _LEGACY_ID_FIELDS)


def _valid_text_list(value: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item) for item in value)
        and len(value) == len(set(value))
    )


def _validate_bindings(
    value: object,
    *,
    query_text: str | None = None,
    threshold_policy: bool = False,
) -> list[str]:
    expected = (
        _THRESHOLD_BINDING_FIELDS
        if threshold_policy
        else _BINDING_FIELDS_WITH_ENVELOPE
    )
    if not isinstance(value, Mapping) or set(value) != expected:
        return ["CLUSTER_AUTHORITY_BINDING_SCHEMA_INVALID"]
    reasons: list[str] = []
    digest_fields = expected - {"authority_envelope_sha256"}
    if any(not HEX64.fullmatch(str(value.get(field) or "")) for field in digest_fields):
        reasons.append("CLUSTER_AUTHORITY_BINDING_DIGEST_INVALID")
    unsigned = {field: value[field] for field in sorted(digest_fields)}
    if value.get("authority_envelope_sha256") != canonical_digest(unsigned):
        reasons.append("CLUSTER_AUTHORITY_ENVELOPE_INVALID")
    if query_text is not None and value.get("query_sha256") != hashlib.sha256(
        query_text.encode("utf-8")
    ).hexdigest():
        reasons.append("CLUSTER_QUERY_DIGEST_INVALID")
    return reasons


def _validate_cluster_rows(value: object) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    reasons: list[str] = []
    if not isinstance(value, list) or len(value) < 2:
        return {}, ["CLUSTER_UNIVERSE_TOO_SMALL"]
    rows: dict[str, Mapping[str, Any]] = {}
    for row in value:
        if not isinstance(row, Mapping):
            reasons.append("CLUSTER_UNIVERSE_ROW_SCHEMA_INVALID")
            continue
        if _has_legacy_identity(row):
            reasons.append("LEGACY_SKILL_OR_ASSERTION_ID_FORBIDDEN")
        if set(row) != _CLUSTER_FIELDS:
            reasons.append("CLUSTER_UNIVERSE_ROW_SCHEMA_INVALID")
            continue
        cluster_id = str(row.get("cluster_id") or "")
        if not cluster_id or cluster_id in rows:
            reasons.append("CLUSTER_IDENTITY_INVALID")
            continue
        rows[cluster_id] = row
        if row.get("cluster_kind") not in _CLUSTER_KINDS:
            reasons.append("CLUSTER_KIND_INVALID")
        if not HEX64.fullmatch(str(row.get("cluster_authority_envelope_sha256") or "")):
            reasons.append("CLUSTER_ROW_AUTHORITY_ENVELOPE_INVALID")
        for field, allow_empty in (
            ("member_node_ids", False),
            ("linked_fact_ids", True),
            ("allowed_sections", True),
            ("graph_path", False),
        ):
            if not _valid_text_list(row.get(field), allow_empty=allow_empty):
                reasons.append(f"CLUSTER_{field.upper()}_INVALID")
        if row.get("activation_status") not in _LIFECYCLE_STATES:
            reasons.append("CLUSTER_LIFECYCLE_INVALID")
        if not all(
            isinstance(row.get(field), str) and row[field]
            for field in (
                "external_claim_policy",
                "employer",
                "role",
                "evidence_type",
            )
        ):
            reasons.append("CLUSTER_METADATA_INVALID")
        if not isinstance(row.get("metric_bearing"), bool):
            reasons.append("CLUSTER_METRIC_FLAG_INVALID")
    return rows, sorted(set(reasons))


def _index_rows(
    value: object,
    *,
    expected_fields: frozenset[str],
    label: str,
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    reasons: list[str] = []
    if not isinstance(value, list) or not value:
        return {}, [f"{label}_EMPTY"]
    rows: dict[str, Mapping[str, Any]] = {}
    for row in value:
        if not isinstance(row, Mapping):
            reasons.append(f"{label}_ROW_SCHEMA_INVALID")
            continue
        if _has_legacy_identity(row):
            reasons.append("LEGACY_SKILL_OR_ASSERTION_ID_FORBIDDEN")
        if set(row) != expected_fields:
            reasons.append(f"{label}_ROW_SCHEMA_INVALID")
            continue
        cluster_id = str(row.get("cluster_id") or "")
        if not cluster_id or cluster_id in rows:
            reasons.append(f"{label}_IDENTITY_INVALID")
            continue
        rows[cluster_id] = row
    return rows, sorted(set(reasons))


def _validate_threshold_policy(
    value: object,
    *,
    expected_digest: str,
) -> tuple[dict[str, Any], list[str]]:
    reasons = validate_pinned_record(
        value,
        expected_digest=expected_digest,
        schema_version=CLUSTER_THRESHOLD_POLICY_SCHEMA,
    )
    if not isinstance(value, Mapping):
        return {}, sorted(set(reasons))
    policy = dict(value)
    if set(policy) != _THRESHOLD_FIELDS:
        reasons.append("CLUSTER_THRESHOLD_POLICY_SCHEMA_INVALID")
    if policy.get("logical_retrieval_unit") != LOGICAL_RETRIEVAL_UNIT:
        reasons.append("CLUSTER_LOGICAL_RETRIEVAL_UNIT_INVALID")
    reasons.extend(
        _validate_bindings(policy.get("authority_bindings"), threshold_policy=True)
    )
    runtime_top_k = policy.get("runtime_top_k")
    if (
        not isinstance(runtime_top_k, int)
        or isinstance(runtime_top_k, bool)
        or runtime_top_k <= 0
    ):
        reasons.append("CLUSTER_RUNTIME_TOP_K_INVALID")
    positive_floor = policy.get("positive_relevance_floor")
    if (
        not isinstance(positive_floor, (int, float))
        or isinstance(positive_floor, bool)
        or not math.isfinite(float(positive_floor))
        or not 0.0 < float(positive_floor) <= 3.0
    ):
        reasons.append("CLUSTER_POSITIVE_RELEVANCE_FLOOR_INVALID")
    thresholds = policy.get("metric_thresholds")
    if not isinstance(thresholds, Mapping) or set(thresholds) != (
        _REQUIRED_METRIC_THRESHOLDS
    ):
        reasons.append("CLUSTER_METRIC_THRESHOLD_SET_INVALID")
    elif any(
        not isinstance(threshold, (int, float))
        or isinstance(threshold, bool)
        or not math.isfinite(float(threshold))
        or not 0.0 <= float(threshold) <= 1.0
        for threshold in thresholds.values()
    ):
        reasons.append("CLUSTER_METRIC_THRESHOLD_VALUE_INVALID")
    return policy, sorted(set(reasons))


def _validate_case(
    case: Mapping[str, Any],
    *,
    threshold_policy: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str], dict[str, str]]:
    reasons: list[str] = []
    universe = case.get("universe")
    ranking = case.get("ranking")
    qrels = case.get("qrels")
    for label, value, schema in (
        ("universe", universe, CLUSTER_UNIVERSE_SCHEMA),
        ("ranking", ranking, CLUSTER_RANKING_SCHEMA),
        ("qrels", qrels, CLUSTER_QRELS_SCHEMA),
    ):
        reasons.extend(
            f"{label.upper()}::{reason}"
            for reason in validate_pinned_record(
                value,
                expected_digest=str(case.get(f"expected_{label}_digest") or ""),
                schema_version=schema,
            )
        )
    if not all(isinstance(value, Mapping) for value in (universe, ranking, qrels)):
        return None, sorted(set(reasons)), {}
    assert isinstance(universe, Mapping)
    assert isinstance(ranking, Mapping)
    assert isinstance(qrels, Mapping)
    if set(universe) != _UNIVERSE_FIELDS:
        reasons.append("CLUSTER_UNIVERSE_SCHEMA_INVALID")
    if set(ranking) != _RANKING_FIELDS:
        reasons.append("CLUSTER_RANKING_SCHEMA_INVALID")
    if set(qrels) != _QRELS_FIELDS:
        reasons.append("CLUSTER_QRELS_SCHEMA_INVALID")
    if any(_has_legacy_identity(value) for value in (universe, ranking, qrels)):
        reasons.append("LEGACY_SKILL_OR_ASSERTION_ID_FORBIDDEN")
    if any(
        value.get("logical_retrieval_unit") != LOGICAL_RETRIEVAL_UNIT
        for value in (universe, ranking, qrels)
    ):
        reasons.append("CLUSTER_LOGICAL_RETRIEVAL_UNIT_INVALID")
    query_text = str(universe.get("query_text") or "")
    universe_bindings = universe.get("authority_bindings")
    ranking_bindings = ranking.get("authority_bindings")
    qrels_bindings = qrels.get("authority_bindings")
    for bindings in (universe_bindings, ranking_bindings, qrels_bindings):
        reasons.extend(_validate_bindings(bindings, query_text=query_text))
    if not (
        universe_bindings == ranking_bindings == qrels_bindings
        and isinstance(universe_bindings, Mapping)
    ):
        reasons.append("CLUSTER_CASE_AUTHORITY_BINDING_MISMATCH")
    threshold_bindings = threshold_policy.get("authority_bindings")
    if isinstance(universe_bindings, Mapping) and isinstance(
        threshold_bindings, Mapping
    ):
        if any(
            universe_bindings.get(field) != threshold_bindings.get(field)
            for field in _STATIC_BINDING_FIELDS
        ):
            reasons.append("CLUSTER_THRESHOLD_AUTHORITY_BINDING_MISMATCH")
    if not query_text:
        reasons.append("CLUSTER_QUERY_TEXT_INVALID")
    if not (
        universe.get("query_id") == ranking.get("query_id") == qrels.get("query_id")
        and ranking.get("universe_digest") == universe.get("record_digest")
        and qrels.get("universe_digest") == universe.get("record_digest")
    ):
        reasons.append("CLUSTER_RETRIEVAL_ARTIFACT_BINDING_MISMATCH")

    clusters, cluster_reasons = _validate_cluster_rows(universe.get("clusters"))
    ranking_rows, ranking_reasons = _index_rows(
        ranking.get("ranking"),
        expected_fields=_RANKING_ROW_FIELDS,
        label="CLUSTER_RANKING",
    )
    label_rows, label_reasons = _index_rows(
        qrels.get("labels"),
        expected_fields=_LABEL_FIELDS,
        label="CLUSTER_QRELS",
    )
    reasons.extend(cluster_reasons)
    reasons.extend(ranking_reasons)
    reasons.extend(label_reasons)
    if set(clusters) != set(ranking_rows) or set(clusters) != set(label_rows):
        reasons.append("CLUSTER_FULL_UNIVERSE_MISMATCH")
    try:
        ordered_ranking = sorted(
            ranking_rows.values(), key=lambda row: int(row.get("rank") or 0)
        )
    except (TypeError, ValueError):
        ordered_ranking = []
        reasons.append("CLUSTER_SYSTEM_RANKS_INVALID")
    if [row.get("rank") for row in ordered_ranking] != list(
        range(1, len(ordered_ranking) + 1)
    ):
        reasons.append("CLUSTER_SYSTEM_RANKS_NOT_CONTIGUOUS")
    if any(
        not isinstance(row.get("score"), (int, float))
        or isinstance(row.get("score"), bool)
        or not math.isfinite(float(row["score"]))
        for row in ordered_ranking
    ):
        reasons.append("CLUSTER_SYSTEM_SCORE_INVALID")
    runtime_top_k = threshold_policy.get("runtime_top_k")
    if ranking.get("gate_k") != runtime_top_k:
        reasons.append("CLUSTER_GATE_K_RUNTIME_MISMATCH")
    if (
        not isinstance(runtime_top_k, int)
        or isinstance(runtime_top_k, bool)
        or runtime_top_k <= 0
        or runtime_top_k >= len(clusters)
    ):
        reasons.append("CLUSTER_TOP_K_NOT_BOUNDED")
    for label in label_rows.values():
        if label.get("relevance_grade") not in {0, 1, 2, 3}:
            reasons.append("CLUSTER_RELEVANCE_GRADE_INVALID")
        if label.get("hard_negative_class") not in _HARD_NEGATIVE_CLASSES:
            reasons.append("CLUSTER_HARD_NEGATIVE_CLASS_INVALID")
        if not isinstance(label.get("critical_hard_negative"), bool):
            reasons.append("CLUSTER_HARD_NEGATIVE_FLAG_INVALID")
        for field in ("expected_graph_path", "jd_concepts", "claim_ids"):
            if not _valid_text_list(
                label.get(field), allow_empty=field in {"jd_concepts", "claim_ids"}
            ):
                reasons.append(f"CLUSTER_{field.upper()}_INVALID")
        duplicate = label.get("near_duplicate_cluster_id")
        if duplicate is not None and (
            not isinstance(duplicate, str)
            or duplicate not in clusters
            or duplicate == label.get("cluster_id")
        ):
            reasons.append("CLUSTER_NEAR_DUPLICATE_REFERENCE_INVALID")
    if reasons:
        return None, sorted(set(reasons)), {}

    generic_universe = seal_record(
        {
            "schema_version": "apps_rg.authoritative_candidate_universe.v1",
            "query_id": universe["query_id"],
            "query_text": universe["query_text"],
            "target_profile": universe["target_profile"],
            "section": universe["section"],
            "graph_lane": universe["graph_lane"],
            "employer": universe["employer"],
            "evidence_density": universe["evidence_density"],
            "corpus_digest": universe_bindings["corpus_sha256"],
            "graph_digest": universe_bindings["graph_sha256"],
            "candidates": [
                {
                    "candidate_id": cluster_id,
                    "graph_path": list(cluster["graph_path"]),
                    "employer": cluster["employer"],
                    "role": cluster["role"],
                    "evidence_type": cluster["evidence_type"],
                    "metric_bearing": cluster["metric_bearing"],
                }
                for cluster_id, cluster in sorted(clusters.items())
            ],
        }
    )
    generic_ranking = seal_record(
        {
            "schema_version": "apps_rg.authoritative_system_ranking.v1",
            "query_id": ranking["query_id"],
            "universe_digest": generic_universe["record_digest"],
            "split": ranking["split"],
            "gate_k": ranking["gate_k"],
            "ranking": [
                {
                    "candidate_id": row["cluster_id"],
                    "rank": row["rank"],
                    "score": row["score"],
                }
                for row in ordered_ranking
            ],
        }
    )
    generic_qrels = seal_record(
        {
            "schema_version": "apps_rg.authoritative_retrieval_qrels.v1",
            "query_id": qrels["query_id"],
            "universe_digest": generic_universe["record_digest"],
            "authority_receipt_file_sha256": qrels[
                "authority_receipt_file_sha256"
            ],
            "reviewer_identity_refs": list(qrels["reviewer_identity_refs"]),
            "adjudicator_identity_ref": qrels["adjudicator_identity_ref"],
            "labels": [
                {
                    "candidate_id": cluster_id,
                    "reviewer_identity_refs": list(label["reviewer_identity_refs"]),
                    "adjudication_status": label["adjudication_status"],
                    "adjudicator_identity_ref": label[
                        "adjudicator_identity_ref"
                    ],
                    "relevance_grade": label["relevance_grade"],
                    "expected_graph_path": list(label["expected_graph_path"]),
                    "critical_hard_negative": label["critical_hard_negative"],
                    "hard_negative_class": label["hard_negative_class"],
                    "near_duplicate_of": label["near_duplicate_cluster_id"],
                    "jd_concepts": list(label["jd_concepts"]),
                    "claim_ids": list(label["claim_ids"]),
                }
                for cluster_id, label in sorted(label_rows.items())
            ],
        }
    )
    generic_case = {
        "universe": generic_universe,
        "expected_universe_digest": generic_universe["record_digest"],
        "ranking": generic_ranking,
        "expected_ranking_digest": generic_ranking["record_digest"],
        "qrels": generic_qrels,
        "expected_qrels_digest": generic_qrels["record_digest"],
    }
    input_digests = {
        "universe": str(universe["record_digest"]),
        "ranking": str(ranking["record_digest"]),
        "qrels": str(qrels["record_digest"]),
        "authority_envelope": str(
            universe_bindings["authority_envelope_sha256"]
        ),
    }
    return generic_case, [], input_digests


def _unknown(reasons: Sequence[str]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_RECEIPT_SCHEMA,
            "gate_id": "G1",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": QUALIFICATION_SCOPE,
            "status": "UNKNOWN",
            "runtime_top_k": None,
            "metrics": {},
            "query_results": [],
            "slices": {},
            "input_digests": {},
            "threshold_policy_digest": None,
            "generic_receipt_digest": None,
            "failure_codes": [],
            "unknown_reasons": sorted(set(reasons)),
            "authority": {
                "measurement_scope": "SOURCE_BOUND_CLUSTER_SYSTEM_VS_QRELS",
                "human_authority_verified": False,
                "release_authorizing": False,
            },
        }
    )


def evaluate_authoritative_cluster_retrieval(
    cases: Sequence[Mapping[str, Any]],
    *,
    threshold_policy: Mapping[str, Any],
    expected_threshold_policy_digest: str,
    authority_receipt_path: Any,
    expected_authority_file_sha256: str,
) -> dict[str, Any]:
    """Evaluate cluster rankings without accepting skill-level identity carriers."""

    policy, reasons = _validate_threshold_policy(
        threshold_policy,
        expected_digest=expected_threshold_policy_digest,
    )
    if not cases:
        reasons.append("AUTHORITATIVE_CLUSTER_RETRIEVAL_CASES_EMPTY")
    generic_cases: list[dict[str, Any]] = []
    input_digests: dict[str, dict[str, str]] = {}
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            reasons.append(f"case[{index}]::CLUSTER_CASE_NOT_OBJECT")
            continue
        generic_case, case_reasons, case_digests = _validate_case(
            case,
            threshold_policy=policy,
        )
        reasons.extend(f"case[{index}]::{reason}" for reason in case_reasons)
        if generic_case is not None:
            generic_cases.append(generic_case)
            input_digests[str(generic_case["universe"]["query_id"])] = case_digests
    if reasons:
        return _unknown(reasons)

    runtime_top_k = int(policy["runtime_top_k"])
    k_values = sorted({1, 3, 5, 10, runtime_top_k})
    generic_receipt = evaluate_authoritative_retrieval(
        generic_cases,
        authority_receipt_path=authority_receipt_path,
        expected_authority_file_sha256=expected_authority_file_sha256,
        positive_floor=float(policy["positive_relevance_floor"]),
        k_values=k_values,
    )
    authority = dict(generic_receipt.get("authority") or {})
    authority.update(
        {
            "measurement_scope": "SOURCE_BOUND_CLUSTER_SYSTEM_VS_QRELS",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "release_authorizing": False,
        }
    )
    return seal_record(
        {
            "schema_version": CLUSTER_RECEIPT_SCHEMA,
            "gate_id": "G1",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": QUALIFICATION_SCOPE,
            "status": generic_receipt["status"],
            "runtime_top_k": runtime_top_k,
            "metrics": generic_receipt["metrics"],
            "query_results": generic_receipt["query_results"],
            "slices": generic_receipt["slices"],
            "input_digests": input_digests,
            "threshold_policy_digest": policy["record_digest"],
            "generic_receipt_digest": generic_receipt["record_digest"],
            "failure_codes": generic_receipt["failure_codes"],
            "unknown_reasons": generic_receipt["unknown_reasons"],
            "authority": authority,
        }
    )


__all__ = [
    "CLUSTER_QRELS_SCHEMA",
    "CLUSTER_RANKING_SCHEMA",
    "CLUSTER_RECEIPT_SCHEMA",
    "CLUSTER_THRESHOLD_POLICY_SCHEMA",
    "CLUSTER_UNIVERSE_SCHEMA",
    "LOGICAL_RETRIEVAL_UNIT",
    "QUALIFICATION_SCOPE",
    "evaluate_authoritative_cluster_retrieval",
    "seal_cluster_authority_bindings",
]
