from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    CONTRACT_PATH,
    QUERY_MANIFEST_PATH,
    W7_RECEIPT_PATH,
    collect_qrel_issues,
    evaluate_labeled_rankings,
    expected_judgment_keys,
    ranking_identity_sha256,
    validate_qualification_contract,
    validate_query_manifest,
    validate_w7_receipt,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    REGISTRY_PATH,
    W6_RECEIPT_PATH,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

ROOT = Path(__file__).resolve().parents[4]
CLI_PATH = (
    ROOT / "tools/apps_rg_standalone/c03_graph_evidence_cluster_qualification_wave7.py"
)


def _load(relative: Path | str) -> dict:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _synthetic_complete_qrels(
    query_manifest: dict, registry: dict, generation_sha256: str
) -> tuple[dict, dict[str, list[str]]]:
    grouped: dict[str, list[str]] = {}
    for query_id, section_id, cluster_id in expected_judgment_keys(
        query_manifest, registry
    ):
        grouped.setdefault(f"{query_id}|{section_id}", []).append(cluster_id)
    judgments = []
    rankings = {}
    for pair, cluster_ids in sorted(grouped.items()):
        query_id, section_id = pair.split("|", 1)
        ordered = sorted(cluster_ids)
        rankings[pair] = ordered
        for index, cluster_id in enumerate(ordered):
            judgments.append(
                {
                    "query_id": query_id,
                    "section_id": section_id,
                    "cluster_id": cluster_id,
                    "relevance_grade": 3 if index == 0 else 0,
                    "reviewer_ids": ["human-reviewer-a", "human-reviewer-b"],
                    "adjudicator_id": "human-adjudicator",
                    "adjudicated": True,
                }
            )
    ranking_sha256 = ranking_identity_sha256(rankings)
    qrels = {
        "schema_version": "apps_rg.c03_graph_evidence_cluster_qrels.v1",
        "status": "FROZEN_HUMAN_ADJUDICATED",
        "source_authority": {
            "query_manifest_sha256": query_manifest["query_manifest_sha256"],
            "registry_sha256": registry["registry_sha256"],
            "projection_generation_sha256": generation_sha256,
            "ranking_identity_sha256": ranking_sha256,
        },
        "human_review_authority_receipt_sha256": "a" * 64,
        "judgment_count": len(judgments),
        "judgments": judgments,
    }
    qrels["qrel_sha256"] = canonical_sha256(qrels)
    return qrels, rankings


def test_w7_contract_and_queries_freeze_complete_unlabeled_denominator() -> None:
    contract = _load(CONTRACT_PATH)
    manifest = _load(QUERY_MANIFEST_PATH)
    registry = _load(REGISTRY_PATH)

    validate_qualification_contract(contract)
    validate_query_manifest(manifest, repository_root=ROOT)

    assert len(expected_judgment_keys(manifest, registry)) == 456
    assert manifest["label_authority"] == {
        "labels_present": False,
        "legacy_skill_qrels_migrated": False,
        "synthetic_labels_created": False,
        "human_review_required": True,
    }
    assert contract["activation_boundary"]["production_promotion_authorized"] is False


def test_qrel_validator_rejects_partial_or_unbound_labels() -> None:
    manifest = _load(QUERY_MANIFEST_PATH)
    registry = _load(REGISTRY_PATH)
    w6 = _load(W6_RECEIPT_PATH)

    issues = collect_qrel_issues(
        {},
        query_manifest=manifest,
        registry=registry,
        projection_generation_sha256=w6["generation"]["projection_generation_sha256"],
        expected_ranking_identity_sha256="b" * 64,
        expected_human_review_authority_receipt_sha256="a" * 64,
    )

    assert "QREL_SCHEMA_VERSION" in issues
    assert any(issue.startswith("QREL_DENOMINATOR:") for issue in issues)
    assert "QREL_HUMAN_AUTHORITY_RECEIPT" in issues


def test_complete_qrels_can_qualify_without_changing_claim_authority() -> None:
    contract = _load(CONTRACT_PATH)
    manifest = _load(QUERY_MANIFEST_PATH)
    registry = _load(REGISTRY_PATH)
    w6 = _load(W6_RECEIPT_PATH)
    generation_sha = w6["generation"]["projection_generation_sha256"]
    qrels, rankings = _synthetic_complete_qrels(manifest, registry, generation_sha)

    report = evaluate_labeled_rankings(
        rankings,
        qrels=qrels,
        query_manifest=manifest,
        registry=registry,
        projection_generation_sha256=generation_sha,
        expected_ranking_identity_sha256=ranking_identity_sha256(rankings),
        expected_human_review_authority_receipt_sha256="a" * 64,
        thresholds=contract["quality_gates"],
        structural_metrics={
            "section_policy_leak_count": 0,
            "orphan_candidate_count": 0,
            "stale_candidate_count": 0,
            "authority_bypass_count": 0,
            "projection_issue_count": 0,
            "cold_six_query_encode_elapsed_ms": 1.0,
            "projection_search_p95_ms": 1.0,
        },
    )

    assert report["status"] == "QUALIFIED"
    assert report["metrics"]["holdout_macro_recall_at_10"] == 1.0
    assert report["metrics"]["holdout_macro_ndcg_at_10"] == 1.0


def test_committed_w7_receipt_is_blocked_without_synthetic_labels() -> None:
    receipt = _load(W7_RECEIPT_PATH)

    validate_w7_receipt(receipt)

    assert receipt["status"] == "BLOCKED_QREL_AUTHORITY"
    assert receipt["label_authority"]["required_judgment_count"] == 456
    assert receipt["label_authority"]["observed_judgment_count"] == 0
    assert receipt["label_authority"]["synthetic_labels_created"] is False
    assert receipt["scope"]["semantic_retrieval_qualified"] is False
    assert receipt["scope"]["production_promotion_authorized"] is False


def test_w7_cli_check_is_read_only() -> None:
    receipt_path = ROOT / W7_RECEIPT_PATH
    before = hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    assert output["status"] == "BLOCKED_QREL_AUTHORITY"
    assert output["qualification_harness_ready"] is True
    assert output["semantic_retrieval_qualified"] is False
    assert output["required_human_judgment_count"] == 456
    assert output["observed_human_judgment_count"] == 0
    assert output["production_promotion"] == "NOT_AUTHORIZED"
    assert hashlib.sha256(receipt_path.read_bytes()).hexdigest() == before
