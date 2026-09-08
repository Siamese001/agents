"""GE-W7 controlled comparison of a candidate graph-evidence projection.

This module deliberately accepts QRELs as an external, already-adjudicated
input.  It never creates relevance grades, rankings, or activation state.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    expected_judgment_keys,
    ranking_identity_sha256,
)
from apps_rg.evals.graph_evolution_qrel_change_impact import GE_W6_COMPLETION_MARKER


GE_W7_CONTRACT_RELATIVE_PATH = Path("src/apps_rg/evals/graph_evolution_candidate_comparison_contract.v1.json")
GE_W7_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_candidate_comparison_contract.v1"
GE_W7_QREL_SCHEMA_VERSION = "apps_rg.graph_evolution_candidate_cluster_qrels.v1"
GE_W7_COMPLETION_MARKER = "GE_W7_CANDIDATE_COMPARISON_EVALUATED"
QUERY_MANIFEST_RELATIVE_PATH = Path("src/apps_rg/evals/c03_graph_evidence_cluster_queries.v1.json")


class GraphEvolutionCandidateComparisonError(ValueError):
    """Raised when the frozen GE-W7 comparison contract is unavailable."""


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphEvolutionCandidateComparisonError(f"GE-W7 JSON unavailable: {path}") from exc
    if not isinstance(payload, dict):
        raise GraphEvolutionCandidateComparisonError("GE-W7 JSON must be an object")
    return payload


def load_ge_w7_candidate_comparison_contract(repo_root: Path | str) -> dict[str, Any]:
    return _read_json(Path(repo_root).resolve() / GE_W7_CONTRACT_RELATIVE_PATH)


def validate_ge_w7_candidate_comparison_contract(contract: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if contract.get("schema_version") != GE_W7_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_CANDIDATE_COMPARISON":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W7" or contract.get("status") != "FROZEN":
        issues.append("WAVE_OR_STATUS")
    inputs = contract.get("input")
    if not isinstance(inputs, Mapping) or any(inputs.get(key) is not True for key in ("ge_w6_change_impact_receipt_required", "candidate_registry_projection_digest_binding_required", "prelabel_full_ranking_freeze_required", "full_finite_candidate_universe_required")):
        issues.append("INPUT")
    authority = contract.get("human_qrel_authority")
    if not isinstance(authority, Mapping) or authority.get("qrel_schema_version") != GE_W7_QREL_SCHEMA_VERSION or authority.get("required_status") != "FROZEN_HUMAN_ADJUDICATED" or authority.get("relevance_grades") != [0, 1, 2, 3] or authority.get("relevant_grade_floor") != 2 or any(authority.get(key) is not True for key in ("two_distinct_human_reviewers_required", "separate_human_adjudicator_required", "external_human_review_authority_receipt_required", "synthetic_or_model_labels_forbidden")):
        issues.append("HUMAN_QREL_AUTHORITY")
    exit_gate = contract.get("ge_w7_exit")
    if not isinstance(exit_gate, Mapping) or exit_gate.get("candidate_state") != "CANDIDATE_COMPARISON_EVALUATED" or exit_gate.get("activation_created") is not False or exit_gate.get("active_runtime_pointer_changed") is not False:
        issues.append("GE_W7_EXIT")
    return issues


def _validate_w6_receipt(receipt: Mapping[str, Any], registry: Mapping[str, Any], projection: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if receipt.get("completion_marker") != GE_W6_COMPLETION_MARKER:
        issues.append("GE_W6_MARKER")
    if receipt.get("candidate_state") != "QREL_CHANGE_IMPACT_ASSESSED":
        issues.append("GE_W6_CANDIDATE_STATE")
    if receipt.get("candidate_registry_sha256") != registry.get("registry_sha256"):
        issues.append("GE_W6_REGISTRY_BINDING")
    if receipt.get("candidate_projection_sha256") != projection.get("projection_sha256"):
        issues.append("GE_W6_PROJECTION_BINDING")
    return issues


def _validate_rankings(rankings: Mapping[str, Sequence[str]], expected: set[tuple[str, str, str]]) -> list[str]:
    expected_by_pair: dict[str, set[str]] = {}
    for query_id, section_id, cluster_id in expected:
        expected_by_pair.setdefault(f"{query_id}|{section_id}", set()).add(cluster_id)
    issues: list[str] = []
    if set(str(pair) for pair in rankings) != set(expected_by_pair):
        issues.append("RANKING_PAIR_DENOMINATOR")
    for pair, cluster_ids in expected_by_pair.items():
        ranking = [str(value) for value in rankings.get(pair) or []]
        if len(ranking) != len(set(ranking)) or set(ranking) != cluster_ids:
            issues.append(f"RANKING_DENOMINATOR:{pair}")
    return sorted(set(issues))


def _validate_frozen_human_qrels(qrels: Mapping[str, Any], *, expected: set[tuple[str, str, str]], query_manifest: Mapping[str, Any], registry: Mapping[str, Any], projection: Mapping[str, Any], rankings: Mapping[str, Sequence[str]]) -> list[str]:
    issues: list[str] = []
    if qrels.get("schema_version") != GE_W7_QREL_SCHEMA_VERSION:
        issues.append("QREL_SCHEMA_VERSION")
    if qrels.get("status") != "FROZEN_HUMAN_ADJUDICATED":
        issues.append("QREL_STATUS")
    source = qrels.get("source_authority")
    if not isinstance(source, Mapping):
        issues.append("QREL_SOURCE")
        source = {}
    required_source = {
        "query_manifest_sha256": query_manifest.get("query_manifest_sha256"),
        "candidate_registry_sha256": registry.get("registry_sha256"),
        "candidate_projection_sha256": projection.get("projection_sha256"),
        "ranking_identity_sha256": ranking_identity_sha256(rankings),
    }
    for field, expected_value in required_source.items():
        if source.get(field) != expected_value:
            issues.append(f"QREL_SOURCE:{field}")
    authority_receipt = qrels.get("human_review_authority_receipt_sha256")
    if not _is_sha256(authority_receipt):
        issues.append("QREL_HUMAN_AUTHORITY_RECEIPT")
    authority = qrels.get("human_review_authority")
    if not isinstance(authority, Mapping):
        issues.append("QREL_HUMAN_IDENTITIES")
        authority = {}
    reviewer_ids = [str(value) for value in authority.get("primary_reviewer_ids") or []]
    adjudicator_id = str(authority.get("adjudicator_id") or "")
    if len(reviewer_ids) != 2 or len(set(reviewer_ids)) != 2 or any(not value.startswith("human-reviewer://") for value in reviewer_ids):
        issues.append("QREL_PRIMARY_REVIEWERS")
    if not adjudicator_id.startswith("human-reviewer://") or adjudicator_id in reviewer_ids:
        issues.append("QREL_ADJUDICATOR")
    observed: set[tuple[str, str, str]] = set()
    for index, judgment in enumerate(qrels.get("judgments") or []):
        if not isinstance(judgment, Mapping):
            issues.append(f"QREL_JUDGMENT_NOT_OBJECT:{index}")
            continue
        key = (str(judgment.get("query_id") or ""), str(judgment.get("section_id") or ""), str(judgment.get("cluster_id") or ""))
        if key in observed:
            issues.append(f"QREL_DUPLICATE:{'|'.join(key)}")
        observed.add(key)
        grade = judgment.get("relevance_grade")
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in {0, 1, 2, 3}:
            issues.append(f"QREL_GRADE:{'|'.join(key)}")
        if judgment.get("reviewer_ids") != reviewer_ids:
            issues.append(f"QREL_REVIEWERS:{'|'.join(key)}")
        if judgment.get("adjudicator_id") != adjudicator_id or judgment.get("adjudicated") is not True:
            issues.append(f"QREL_ADJUDICATION:{'|'.join(key)}")
    if observed != expected:
        issues.append(f"QREL_DENOMINATOR:missing={len(expected - observed)}:orphan={len(observed - expected)}")
    if qrels.get("judgment_count") != len(expected):
        issues.append("QREL_JUDGMENT_COUNT")
    unsigned = dict(qrels)
    supplied_digest = unsigned.pop("qrel_sha256", None)
    if _canonical_sha256(unsigned) != supplied_digest:
        issues.append("QREL_DIGEST")
    return sorted(set(issues))


def _evaluate_metrics(rankings: Mapping[str, Sequence[str]], qrels: Mapping[str, Any], query_manifest: Mapping[str, Any], structural_metrics: Mapping[str, int | float]) -> tuple[dict[str, float | int], list[str]]:
    relevance_by_pair: dict[str, dict[str, int]] = {}
    for row in qrels["judgments"]:
        pair = f"{row['query_id']}|{row['section_id']}"
        relevance_by_pair.setdefault(pair, {})[str(row["cluster_id"])] = int(row["relevance_grade"])
    query_splits = {str(query["query_id"]): str(query["split"]) for query in query_manifest["queries"]}
    buckets: dict[str, dict[str, Any]] = {split: {"recalls": [], "ndcgs": [], "rrs": [], "relevant": 0, "hits": 0} for split in ("CALIBRATION", "HOLDOUT")}
    failures: list[str] = []
    for pair, relevance in sorted(relevance_by_pair.items()):
        relevant = {cluster_id for cluster_id, grade in relevance.items() if grade >= 2}
        if not relevant:
            failures.append(f"NO_RELEVANT_CLUSTER:{pair}")
            continue
        ranking = [str(value) for value in rankings[pair]]
        bucket = buckets[query_splits[pair.split("|", 1)[0]]]
        bucket["recalls"].append(len(relevant & set(ranking[:10])) / len(relevant))
        actual = math.fsum((2.0 ** relevance.get(cluster_id, 0) - 1.0) / math.log2(rank + 1.0) for rank, cluster_id in enumerate(ranking[:10], start=1))
        ideal = math.fsum((2.0**grade - 1.0) / math.log2(rank + 1.0) for rank, grade in enumerate(sorted(relevance.values(), reverse=True)[:10], start=1))
        bucket["ndcgs"].append(actual / ideal if ideal else 0.0)
        first = next((rank for rank, cluster_id in enumerate(ranking, start=1) if cluster_id in relevant), None)
        bucket["rrs"].append(1.0 / first if first else 0.0)
        bucket["relevant"] += len(relevant)
        bucket["hits"] += len(relevant & set(ranking[:10]))
    metrics: dict[str, float | int] = dict(structural_metrics)
    for split, bucket in buckets.items():
        prefix = split.lower()
        metrics[f"{prefix}_macro_recall_at_10"] = math.fsum(bucket["recalls"]) / len(bucket["recalls"]) if bucket["recalls"] else 0.0
        metrics[f"{prefix}_pooled_recall_at_10"] = bucket["hits"] / bucket["relevant"] if bucket["relevant"] else 0.0
        metrics[f"{prefix}_macro_ndcg_at_10"] = math.fsum(bucket["ndcgs"]) / len(bucket["ndcgs"]) if bucket["ndcgs"] else 0.0
        metrics[f"{prefix}_macro_reciprocal_rank"] = math.fsum(bucket["rrs"]) / len(bucket["rrs"]) if bucket["rrs"] else 0.0
    return metrics, failures


def evaluate_candidate_comparison(candidate_registry: Mapping[str, Any], candidate_projection: Mapping[str, Any], ge_w6_receipt: Mapping[str, Any], *, repo_root: Path | str, rankings: Mapping[str, Sequence[str]] | None = None, qrels: Mapping[str, Any] | None = None, non_retrieval_metrics: Mapping[str, int | float] | None = None) -> dict[str, Any]:
    """Evaluate only an externally frozen, complete human-QREL comparison."""
    contract = load_ge_w7_candidate_comparison_contract(repo_root)
    contract_issues = validate_ge_w7_candidate_comparison_contract(contract)
    if contract_issues:
        raise GraphEvolutionCandidateComparisonError(f"GE-W7 contract invalid: {', '.join(contract_issues)}")
    w6_issues = _validate_w6_receipt(ge_w6_receipt, candidate_registry, candidate_projection)
    if w6_issues:
        return {"status": "BLOCKED", "reason": "GE_W7_PREREQUISITE", "failures": w6_issues, "metrics": {}}
    root = Path(repo_root).resolve()
    manifest = _read_json(root / QUERY_MANIFEST_RELATIVE_PATH)
    expected = expected_judgment_keys(manifest, candidate_registry)
    blocked_receipt = {
        "schema_version": "apps_rg.graph_evolution_candidate_comparison_receipt.v1",
        "completion_marker": GE_W7_COMPLETION_MARKER,
        "status": "BLOCKED_QREL_AUTHORITY",
        "candidate_state": "QREL_CHANGE_IMPACT_ASSESSED",
        "candidate_registry_sha256": candidate_registry.get("registry_sha256"),
        "candidate_projection_sha256": candidate_projection.get("projection_sha256"),
        "expected_final_human_judgment_count": len(expected),
        "qrel_grades_created": False,
        "retrieval_metrics_computed": False,
        "active_runtime_pointer_changed": False,
        "activation_created": False,
        "next_gate": "GE_W7_HUMAN_QREL_FREEZE",
    }
    if qrels is None:
        blocked_receipt["receipt_sha256"] = _canonical_sha256(blocked_receipt)
        return {"status": "BLOCKED_QREL_AUTHORITY", "reason": "GE_W7_HUMAN_QRELS_REQUIRED", "failures": [], "metrics": {}, "receipt": blocked_receipt}
    if rankings is None:
        return {"status": "BLOCKED_RANKING_FREEZE", "reason": "GE_W7_FROZEN_RANKINGS_REQUIRED", "failures": [], "metrics": {}, "receipt": blocked_receipt}
    ranking_issues = _validate_rankings(rankings, expected)
    if ranking_issues:
        return {"status": "BLOCKED_RANKING_FREEZE", "reason": "GE_W7_RANKING_DENOMINATOR", "failures": ranking_issues, "metrics": {}, "receipt": blocked_receipt}
    qrel_issues = _validate_frozen_human_qrels(qrels, expected=expected, query_manifest=manifest, registry=candidate_registry, projection=candidate_projection, rankings=rankings)
    if qrel_issues:
        return {"status": "BLOCKED_QREL_AUTHORITY", "reason": "GE_W7_QREL_VALIDATION", "failures": qrel_issues, "metrics": {}, "receipt": blocked_receipt}
    required_non_retrieval = contract["non_retrieval_evaluation"]["required_metrics"]
    non_retrieval = dict(non_retrieval_metrics or {})
    missing = [key for key in required_non_retrieval if key not in non_retrieval]
    if missing:
        return {"status": "BLOCKED", "reason": "GE_W7_NON_RETRIEVAL_EVALUATION_REQUIRED", "failures": [f"MISSING:{key}" for key in missing], "metrics": {}, "receipt": blocked_receipt}
    metrics, failures = _evaluate_metrics(rankings, qrels, manifest, non_retrieval)
    gates = contract["retrieval_metrics"]["holdout_quality_gates"]
    for metric, minimum in gates.items():
        actual_key = f"holdout_{metric.removesuffix('_min')}"
        if float(metrics[actual_key]) < float(minimum):
            failures.append(f"THRESHOLD:{actual_key}")
    for metric, maximum in contract["non_retrieval_evaluation"]["maximums"].items():
        if float(metrics[metric]) > float(maximum):
            failures.append(f"THRESHOLD:{metric}")
    status = "FAIL" if failures else "QUALIFIED"
    receipt = {
        "schema_version": "apps_rg.graph_evolution_candidate_comparison_receipt.v1",
        "completion_marker": GE_W7_COMPLETION_MARKER,
        "status": status,
        "candidate_state": "CANDIDATE_COMPARISON_EVALUATED",
        "candidate_registry_sha256": candidate_registry.get("registry_sha256"),
        "candidate_projection_sha256": candidate_projection.get("projection_sha256"),
        "qrel_sha256": qrels.get("qrel_sha256"),
        "ranking_identity_sha256": ranking_identity_sha256(rankings),
        "expected_final_human_judgment_count": len(expected),
        "qrel_grades_created": False,
        "retrieval_metrics_computed": True,
        "active_runtime_pointer_changed": False,
        "activation_created": False,
        "next_gate": "GE_W8_CONTROLLED_ACTIVATION" if status == "QUALIFIED" else "GE_W7_REMEDIATION",
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return {"status": status, "reason": GE_W7_COMPLETION_MARKER, "failures": sorted(set(failures)), "metrics": metrics, "receipt": receipt}


__all__ = ["GE_W7_COMPLETION_MARKER", "GE_W7_CONTRACT_RELATIVE_PATH", "GE_W7_CONTRACT_SCHEMA_VERSION", "GE_W7_QREL_SCHEMA_VERSION", "GraphEvolutionCandidateComparisonError", "evaluate_candidate_comparison", "load_ge_w7_candidate_comparison_contract", "validate_ge_w7_candidate_comparison_contract"]
