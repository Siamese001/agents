"""Governed W7 semantic qualification for C0.3 graph-evidence clusters."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

CONTRACT_PATH = Path(
    "src/apps_rg/evals/c03_graph_evidence_cluster_qualification_contract.v1.json"
)
QUERY_MANIFEST_PATH = Path(
    "src/apps_rg/evals/c03_graph_evidence_cluster_queries.v1.json"
)
ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_evidence_cluster_embeddings")
W6_RECEIPT_PATH = ARTIFACT_DIR / "wave6_cluster_vector_generation_receipt.json"
W7_RECEIPT_PATH = ARTIFACT_DIR / "wave7_semantic_qualification_receipt.json"
ACTIVATION_MANIFEST_PATH = (
    ARTIFACT_DIR / "graph_evidence_cluster_embedding_activation_manifest.json"
)

CONTRACT_SCHEMA_VERSION = "apps_rg.c03_graph_evidence_cluster_qualification_contract.v1"
QUERY_SCHEMA_VERSION = "apps_rg.c03_graph_evidence_cluster_queries.v1"
QREL_SCHEMA_VERSION = "apps_rg.c03_graph_evidence_cluster_qrels.v1"
RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w7_receipt.v1"
W7_READINESS_MARKER = (
    "C03_CLUSTER_EMBEDDING_W7_READINESS_COMPLETE_QUALIFICATION_BLOCKED"
)


class ClusterSemanticQualificationError(ValueError):
    """Raised when W7 semantic qualification authority is incomplete."""


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


def validate_qualification_contract(contract: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        issues.append("schema_version")
    if contract.get("wave") != "W7" or contract.get("status") != "FROZEN":
        issues.append("wave_or_status")
    denominator = contract.get("evaluation_denominator") or {}
    expected = {
        "query_count": 6,
        "calibration_query_count": 3,
        "holdout_query_count": 3,
        "section_count": 8,
        "query_section_count": 48,
        "expected_cluster_judgment_count": 456,
        "relevant_grade_floor": 2,
    }
    for field, value in expected.items():
        if denominator.get(field) != value:
            issues.append(f"evaluation_denominator.{field}")
    required_true = (
        ("source_requirements", "wave6_pass_receipt_required"),
        ("source_requirements", "immutable_projection_required"),
        ("source_requirements", "wave4_registry_required"),
        ("source_requirements", "canonical_graph_required"),
        ("source_requirements", "source_bound_query_manifest_required"),
        (
            "source_requirements",
            "historical_per_skill_qrels_forbidden_as_release_authority",
        ),
        ("evaluation_denominator", "full_finite_candidate_universe_required"),
        ("evaluation_denominator", "partial_top_k_judging_forbidden"),
        ("human_authority", "two_distinct_human_reviewers_required"),
        ("human_authority", "adjudication_required"),
        ("human_authority", "external_human_review_authority_receipt_required"),
        ("human_authority", "synthetic_or_model_labels_forbidden"),
        ("human_authority", "unknown_labels_forbidden"),
        ("human_authority", "reviewer_rank_and_score_blinding_required"),
        ("human_authority", "prelabel_ranking_identity_freeze_required"),
        ("activation_boundary", "qualification_is_not_activation"),
        ("activation_boundary", "release_activation_requires_later_explicit_wave"),
    )
    for section, field in required_true:
        if (contract.get(section) or {}).get(field) is not True:
            issues.append(f"{section}.{field}")
    for field in (
        "wave7_creates_activation_manifest",
        "production_promotion_authorized",
    ):
        if (contract.get("activation_boundary") or {}).get(field) is not False:
            issues.append(f"activation_boundary.{field}")
    if issues:
        raise ClusterSemanticQualificationError(
            f"Invalid W7 qualification contract: {sorted(set(issues))}"
        )


def validate_query_manifest(
    manifest: Mapping[str, Any], *, repository_root: Path | str
) -> None:
    issues: list[str] = []
    root = Path(repository_root).resolve()
    if manifest.get("schema_version") != QUERY_SCHEMA_VERSION:
        issues.append("schema_version")
    if manifest.get("status") != "FROZEN_UNLABELED":
        issues.append("status")
    queries = manifest.get("queries") or []
    sections = manifest.get("section_ids") or []
    if manifest.get("query_count") != 6 or len(queries) != 6:
        issues.append("query_count")
    if len(sections) != 8 or len(set(sections)) != 8:
        issues.append("section_ids")
    query_ids: list[str] = []
    splits_by_profile: dict[str, set[str]] = {}
    for index, query in enumerate(queries):
        if not isinstance(query, Mapping):
            issues.append(f"query_not_object:{index}")
            continue
        query_id = str(query.get("query_id") or "")
        query_ids.append(query_id)
        split = str(query.get("split") or "")
        if split not in {"CALIBRATION", "HOLDOUT"}:
            issues.append(f"query_split:{query_id}")
        profile = str(query.get("target_profile_id") or "")
        splits_by_profile.setdefault(profile, set()).add(split)
        for prefix in ("jd", "brief"):
            relative = Path(str(query.get(f"{prefix}_path") or ""))
            path = (root / relative).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                issues.append(f"source_path_escape:{query_id}:{prefix}")
                continue
            if not path.is_file():
                issues.append(f"source_missing:{query_id}:{prefix}")
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != query.get(
                f"{prefix}_sha256"
            ):
                issues.append(f"source_digest:{query_id}:{prefix}")
    if not all(query_ids) or len(query_ids) != len(set(query_ids)):
        issues.append("query_ids")
    split_counts = {
        split: sum(
            query.get("split") == split
            for query in queries
            if isinstance(query, Mapping)
        )
        for split in ("CALIBRATION", "HOLDOUT")
    }
    if split_counts != {"CALIBRATION": 3, "HOLDOUT": 3}:
        issues.append("split_counts")
    if any(
        splits != {"CALIBRATION", "HOLDOUT"} for splits in splits_by_profile.values()
    ):
        issues.append("profile_split_pairs")
    authority = manifest.get("label_authority") or {}
    expected_authority = {
        "labels_present": False,
        "legacy_skill_qrels_migrated": False,
        "synthetic_labels_created": False,
        "human_review_required": True,
    }
    if authority != expected_authority:
        issues.append("label_authority")
    unsigned = dict(manifest)
    supplied = unsigned.pop("query_manifest_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("query_manifest_sha256")
    if issues:
        raise ClusterSemanticQualificationError(
            f"Invalid W7 query manifest: {sorted(set(issues))}"
        )


def build_query_texts(
    manifest: Mapping[str, Any], *, repository_root: Path | str
) -> dict[str, str]:
    validate_query_manifest(manifest, repository_root=repository_root)
    root = Path(repository_root).resolve()
    return {
        str(query["query_id"]): (
            (root / str(query["jd_path"])).read_text(encoding="utf-8").strip()
            + "\n\n"
            + (root / str(query["brief_path"])).read_text(encoding="utf-8").strip()
        )
        for query in manifest["queries"]
    }


def expected_judgment_keys(
    query_manifest: Mapping[str, Any], registry: Mapping[str, Any]
) -> set[tuple[str, str, str]]:
    allowed_by_section: dict[str, set[str]] = {
        str(section): set() for section in query_manifest.get("section_ids") or []
    }
    for cluster in registry.get("clusters") or []:
        if not isinstance(cluster, Mapping):
            continue
        cluster_id = str(cluster.get("cluster_id") or "")
        for section in cluster.get("allowed_sections") or []:
            if str(section) in allowed_by_section:
                allowed_by_section[str(section)].add(cluster_id)
    return {
        (str(query["query_id"]), section, cluster_id)
        for query in query_manifest.get("queries") or []
        for section, cluster_ids in allowed_by_section.items()
        for cluster_id in cluster_ids
    }


def collect_qrel_issues(
    qrels: Mapping[str, Any],
    *,
    query_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    projection_generation_sha256: str,
    expected_ranking_identity_sha256: str,
    expected_human_review_authority_receipt_sha256: str,
) -> list[str]:
    issues: list[str] = []
    if qrels.get("schema_version") != QREL_SCHEMA_VERSION:
        issues.append("QREL_SCHEMA_VERSION")
    if qrels.get("status") != "FROZEN_HUMAN_ADJUDICATED":
        issues.append("QREL_STATUS")
    source = qrels.get("source_authority") or {}
    expected_source = {
        "query_manifest_sha256": query_manifest.get("query_manifest_sha256"),
        "registry_sha256": registry.get("registry_sha256"),
        "projection_generation_sha256": projection_generation_sha256,
        "ranking_identity_sha256": expected_ranking_identity_sha256,
    }
    for field, value in expected_source.items():
        if source.get(field) != value:
            issues.append(f"QREL_SOURCE:{field}")
    if (
        not _is_sha256(expected_human_review_authority_receipt_sha256)
        or qrels.get("human_review_authority_receipt_sha256")
        != expected_human_review_authority_receipt_sha256
    ):
        issues.append("QREL_HUMAN_AUTHORITY_RECEIPT")
    expected = expected_judgment_keys(query_manifest, registry)
    observed: set[tuple[str, str, str]] = set()
    for index, judgment in enumerate(qrels.get("judgments") or []):
        if not isinstance(judgment, Mapping):
            issues.append(f"QREL_JUDGMENT_NOT_OBJECT:{index}")
            continue
        key = (
            str(judgment.get("query_id") or ""),
            str(judgment.get("section_id") or ""),
            str(judgment.get("cluster_id") or ""),
        )
        if key in observed:
            issues.append(f"QREL_DUPLICATE:{key}")
        observed.add(key)
        grade = judgment.get("relevance_grade")
        if (
            not isinstance(grade, int)
            or isinstance(grade, bool)
            or grade not in {0, 1, 2, 3}
        ):
            issues.append(f"QREL_GRADE:{key}")
        reviewers = judgment.get("reviewer_ids")
        if (
            not isinstance(reviewers, list)
            or len(reviewers) != 2
            or len(set(str(value) for value in reviewers)) != 2
            or any(not str(value).strip() for value in reviewers)
        ):
            issues.append(f"QREL_REVIEWERS:{key}")
        if not str(judgment.get("adjudicator_id") or "").strip():
            issues.append(f"QREL_ADJUDICATOR:{key}")
        elif isinstance(reviewers, list) and str(judgment["adjudicator_id"]) in {
            str(value) for value in reviewers
        }:
            issues.append(f"QREL_ADJUDICATOR_NOT_DISTINCT:{key}")
        if judgment.get("adjudicated") is not True:
            issues.append(f"QREL_ADJUDICATED:{key}")
    if observed != expected:
        issues.append(
            f"QREL_DENOMINATOR:missing={len(expected - observed)}:orphan={len(observed - expected)}"
        )
    if qrels.get("judgment_count") != len(expected):
        issues.append("QREL_JUDGMENT_COUNT")
    unsigned = dict(qrels)
    supplied = unsigned.pop("qrel_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("QREL_DIGEST")
    return sorted(set(issues))


def _recall(ranking: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    relevant = {key for key, value in relevance.items() if value >= 2}
    if not relevant:
        raise ClusterSemanticQualificationError("qrel pair has no relevant cluster")
    return len(relevant & set(ranking[:k])) / len(relevant)


def _ndcg(ranking: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    actual = math.fsum(
        (2.0 ** relevance.get(cluster_id, 0) - 1.0) / math.log2(rank + 1.0)
        for rank, cluster_id in enumerate(ranking[:k], start=1)
    )
    ideal = math.fsum(
        (2.0**grade - 1.0) / math.log2(rank + 1.0)
        for rank, grade in enumerate(
            sorted(relevance.values(), reverse=True)[:k], start=1
        )
    )
    return actual / ideal if ideal else 0.0


def ranking_identity_sha256(rankings: Mapping[str, Sequence[str]]) -> str:
    """Bind pre-label ranking identities without publishing ranks or scores."""

    return hashlib.sha256(
        json.dumps(
            {
                str(key): [str(value) for value in values]
                for key, values in rankings.items()
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def evaluate_labeled_rankings(
    rankings: Mapping[str, Sequence[str]],
    *,
    qrels: Mapping[str, Any],
    query_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    projection_generation_sha256: str,
    expected_ranking_identity_sha256: str,
    expected_human_review_authority_receipt_sha256: str,
    thresholds: Mapping[str, Any],
    structural_metrics: Mapping[str, int | float],
) -> dict[str, Any]:
    if ranking_identity_sha256(rankings) != expected_ranking_identity_sha256:
        return {
            "status": "BLOCKED_RANKING_FREEZE",
            "failures": ["RANKING_IDENTITY_DIGEST_MISMATCH"],
            "metrics": {},
        }
    issues = collect_qrel_issues(
        qrels,
        query_manifest=query_manifest,
        registry=registry,
        projection_generation_sha256=projection_generation_sha256,
        expected_ranking_identity_sha256=expected_ranking_identity_sha256,
        expected_human_review_authority_receipt_sha256=(
            expected_human_review_authority_receipt_sha256
        ),
    )
    if issues:
        return {"status": "BLOCKED_QREL_AUTHORITY", "failures": issues, "metrics": {}}
    relevance_by_pair: dict[str, dict[str, int]] = {}
    for row in qrels["judgments"]:
        pair = f"{row['query_id']}|{row['section_id']}"
        relevance_by_pair.setdefault(pair, {})[str(row["cluster_id"])] = int(
            row["relevance_grade"]
        )
    query_splits = {
        str(query["query_id"]): str(query["split"])
        for query in query_manifest["queries"]
    }
    by_split: dict[str, dict[str, Any]] = {
        split: {"recalls": [], "ndcgs": [], "rrs": [], "relevant": 0, "hits": 0}
        for split in ("CALIBRATION", "HOLDOUT")
    }
    failures: list[str] = []
    for pair, relevance in sorted(relevance_by_pair.items()):
        ranking = list(rankings.get(pair) or [])
        if set(ranking) != set(relevance) or len(ranking) != len(set(ranking)):
            failures.append(f"RANKING_DENOMINATOR:{pair}")
            continue
        relevant = {key for key, grade in relevance.items() if grade >= 2}
        if not relevant:
            failures.append(f"NO_RELEVANT_CLUSTER:{pair}")
            continue
        query_id = pair.split("|", 1)[0]
        split = query_splits[query_id]
        bucket = by_split[split]
        bucket["recalls"].append(_recall(ranking, relevance, 10))
        bucket["ndcgs"].append(_ndcg(ranking, relevance, 10))
        first = next(
            (
                rank
                for rank, cluster_id in enumerate(ranking, start=1)
                if cluster_id in relevant
            ),
            None,
        )
        bucket["rrs"].append(1.0 / first if first else 0.0)
        bucket["relevant"] += len(relevant)
        bucket["hits"] += len(relevant & set(ranking[:10]))
    metrics: dict[str, float | int] = dict(structural_metrics)
    for split, bucket in by_split.items():
        prefix = split.lower()
        metrics[f"{prefix}_macro_recall_at_10"] = (
            math.fsum(bucket["recalls"]) / len(bucket["recalls"])
            if bucket["recalls"]
            else 0.0
        )
        metrics[f"{prefix}_pooled_recall_at_10"] = (
            bucket["hits"] / bucket["relevant"] if bucket["relevant"] else 0.0
        )
        metrics[f"{prefix}_macro_ndcg_at_10"] = (
            math.fsum(bucket["ndcgs"]) / len(bucket["ndcgs"])
            if bucket["ndcgs"]
            else 0.0
        )
        metrics[f"{prefix}_macro_reciprocal_rank"] = (
            math.fsum(bucket["rrs"]) / len(bucket["rrs"]) if bucket["rrs"] else 0.0
        )
    minimums = (
        "holdout_macro_recall_at_10",
        "holdout_pooled_recall_at_10",
        "holdout_macro_ndcg_at_10",
        "holdout_macro_reciprocal_rank",
    )
    for metric in minimums:
        if float(metrics[metric]) < float(thresholds[f"{metric}_min"]):
            failures.append(f"THRESHOLD:{metric}")
    maximums = (
        "section_policy_leak_count",
        "orphan_candidate_count",
        "stale_candidate_count",
        "authority_bypass_count",
        "projection_issue_count",
        "cold_six_query_encode_elapsed_ms",
        "projection_search_p95_ms",
    )
    for metric in maximums:
        if float(metrics[metric]) > float(thresholds[f"{metric}_max"]):
            failures.append(f"THRESHOLD:{metric}")
    return {
        "status": "FAIL" if failures else "QUALIFIED",
        "failures": sorted(set(failures)),
        "metrics": metrics,
    }


def build_w7_blocked_receipt(
    *,
    contract: Mapping[str, Any],
    query_manifest: Mapping[str, Any],
    w6_receipt: Mapping[str, Any],
    registry: Mapping[str, Any],
    diagnostic_proof: Mapping[str, Any],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    expected = expected_judgment_keys(query_manifest, registry)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W7",
        "status": "BLOCKED_QREL_AUTHORITY",
        "completion_marker": W7_READINESS_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave6_receipt_sha256": w6_receipt.get("receipt_sha256"),
            "wave4_registry_sha256": registry.get("registry_sha256"),
            "projection_generation_sha256": (w6_receipt.get("generation") or {}).get(
                "projection_generation_sha256"
            ),
        },
        "contract": {
            "path": CONTRACT_PATH.as_posix(),
            "canonical_sha256": canonical_sha256(contract),
        },
        "query_manifest": {
            "path": QUERY_MANIFEST_PATH.as_posix(),
            "query_manifest_sha256": query_manifest.get("query_manifest_sha256"),
            "query_count": len(query_manifest.get("queries") or []),
            "calibration_query_count": sum(
                query.get("split") == "CALIBRATION"
                for query in query_manifest.get("queries") or []
            ),
            "holdout_query_count": sum(
                query.get("split") == "HOLDOUT"
                for query in query_manifest.get("queries") or []
            ),
            "section_count": len(query_manifest.get("section_ids") or []),
            "query_section_count": len(query_manifest.get("queries") or [])
            * len(query_manifest.get("section_ids") or []),
        },
        "label_authority": {
            "current_cluster_qrels_present": False,
            "human_review_authority_receipt_present": False,
            "required_judgment_count": len(expected),
            "observed_judgment_count": 0,
            "two_distinct_human_reviewers_required": True,
            "adjudication_required": True,
            "legacy_per_skill_qrels_release_authorizing": False,
            "synthetic_labels_created": False,
        },
        "diagnostic_proof": dict(diagnostic_proof),
        "scope": {
            "qualification_harness_ready": True,
            "semantic_retrieval_qualified": False,
            "cluster_embedding_activation_created": False,
            "production_promotion_authorized": False,
        },
        "wave_exit_gates": {
            "cluster_embedding_generation": "PASS_W6",
            "semantic_retrieval_qualification": "BLOCKED_QREL_AUTHORITY",
            "human_cluster_qrels": "OPEN_456_JUDGMENTS",
            "release_activation": "BLOCKED_UNTIL_QUALIFIED",
            "production_promotion": "NOT_AUTHORIZED",
        },
        "blocking_conditions": [
            "CURRENT_CLUSTER_QRELS_MISSING",
            "HUMAN_REVIEW_AUTHORITY_RECEIPT_MISSING",
            "TWO_REVIEWER_ADJUDICATION_MISSING",
        ],
        "next_action": (
            "Complete two independent blinded human reviews and adjudication for all "
            f"{len(expected)} query-section-cluster judgments, then rerun W7."
        ),
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def validate_w7_receipt(receipt: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        issues.append("schema_version")
    if receipt.get("status") != "BLOCKED_QREL_AUTHORITY":
        issues.append("status")
    if receipt.get("completion_marker") != W7_READINESS_MARKER:
        issues.append("completion_marker")
    labels = receipt.get("label_authority") or {}
    if labels.get("required_judgment_count") != 456:
        issues.append("label_authority.required_judgment_count")
    if labels.get("observed_judgment_count") != 0:
        issues.append("label_authority.observed_judgment_count")
    if labels.get("synthetic_labels_created") is not False:
        issues.append("label_authority.synthetic_labels_created")
    for field in (
        "current_cluster_qrels_present",
        "human_review_authority_receipt_present",
        "legacy_per_skill_qrels_release_authorizing",
    ):
        if labels.get(field) is not False:
            issues.append(f"label_authority.{field}")
    for field in (
        "two_distinct_human_reviewers_required",
        "adjudication_required",
    ):
        if labels.get(field) is not True:
            issues.append(f"label_authority.{field}")
    query_manifest = receipt.get("query_manifest") or {}
    expected_query_counts = {
        "query_count": 6,
        "calibration_query_count": 3,
        "holdout_query_count": 3,
        "section_count": 8,
        "query_section_count": 48,
    }
    for field, value in expected_query_counts.items():
        if query_manifest.get(field) != value:
            issues.append(f"query_manifest.{field}")
    diagnostic = receipt.get("diagnostic_proof") or {}
    for field in (
        "projection_integrity_passed",
        "candidate_only_payload_passed",
        "section_policy_passed",
        "current_authority_rehydration_passed",
        "latency_gate_passed",
    ):
        if diagnostic.get(field) is not True:
            issues.append(f"diagnostic_proof.{field}")
    if diagnostic.get("candidate_row_count") != 456:
        issues.append("diagnostic_proof.candidate_row_count")
    if diagnostic.get("expected_judgment_count") != 456:
        issues.append("diagnostic_proof.expected_judgment_count")
    if not _is_sha256(diagnostic.get("ranking_identity_sha256")):
        issues.append("diagnostic_proof.ranking_identity_sha256")
    if diagnostic.get("quality_metrics_computed") is not False:
        issues.append("diagnostic_proof.quality_metrics_computed")
    if diagnostic.get("rankings_or_scores_published") is not False:
        issues.append("diagnostic_proof.rankings_or_scores_published")
    runtime = diagnostic.get("runtime_proof") or {}
    if runtime.get("fallback_used") is not False or runtime.get("vector_count") != 6:
        issues.append("diagnostic_proof.runtime_proof")
    scope = receipt.get("scope") or {}
    if scope.get("qualification_harness_ready") is not True:
        issues.append("scope.qualification_harness_ready")
    for field in (
        "semantic_retrieval_qualified",
        "cluster_embedding_activation_created",
        "production_promotion_authorized",
    ):
        if scope.get(field) is not False:
            issues.append(f"scope.{field}")
    gates = receipt.get("wave_exit_gates") or {}
    if gates.get("semantic_retrieval_qualification") != "BLOCKED_QREL_AUTHORITY":
        issues.append("wave_exit_gates.semantic_retrieval_qualification")
    if gates.get("production_promotion") != "NOT_AUTHORIZED":
        issues.append("wave_exit_gates.production_promotion")
    unsigned = dict(receipt)
    supplied = unsigned.pop("receipt_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("receipt_sha256")
    if issues:
        raise ClusterSemanticQualificationError(
            f"Invalid W7 receipt: {sorted(set(issues))}"
        )


__all__ = [
    "ACTIVATION_MANIFEST_PATH",
    "ARTIFACT_DIR",
    "CONTRACT_PATH",
    "ClusterSemanticQualificationError",
    "QUERY_MANIFEST_PATH",
    "QREL_SCHEMA_VERSION",
    "W6_RECEIPT_PATH",
    "W7_RECEIPT_PATH",
    "build_query_texts",
    "build_w7_blocked_receipt",
    "collect_qrel_issues",
    "evaluate_labeled_rankings",
    "expected_judgment_keys",
    "ranking_identity_sha256",
    "validate_qualification_contract",
    "validate_query_manifest",
    "validate_w7_receipt",
]
