from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.fact_inventory.c03_cluster_embedding_wave0 import (
    ClusterEmbeddingWave0Error,
    validate_cluster_contract,
    validate_wave0_receipt,
)

ROOT = Path(__file__).resolve().parents[4]
BASELINE_COMMIT = "212244294f4a6fc5d33875460bc2ed4282c60b40"
BASELINE_TREE = "ecdf982bc5ae0f7c678dd45ee8a1f4a9f92919da"
RECEIPT = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave0_baseline_receipt.json"
)


def test_wave0_receipt_preserves_the_pre_w1_authority_profile() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    validate_wave0_receipt(receipt)
    assert receipt["status"] == "PASS"
    assert receipt["scope"] == {
        "repository": "apps_rg_v2",
        "baseline_freeze_only": True,
        "graph_mutated": False,
        "legacy_artifacts_deleted": False,
        "replacement_vectors_generated": False,
        "production_promotion_authorized": False,
    }
    assert receipt["graph_profile"]["node_count"] == 375
    assert receipt["graph_profile"]["edge_count"] == 2114
    assert receipt["graph_profile"]["skill_row_count"] == 254
    assert (
        receipt["graph_profile"]["semantic_hardening"]["malformed_description_count"]
        == 142
    )
    assert (
        receipt["graph_profile"]["path_and_lifecycle_hardening"][
            "non_traversable_graph_hop_row_count"
        ]
        == 237
    )
    assert receipt["legacy_embedding_artifacts"]["artifact_count"] == 13
    assert receipt["legacy_embedding_artifacts"]["model_baseline"] == {
        "model_id": "BAAI/bge-m3",
        "revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "artifact_sha256": (
            "38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263"
        ),
        "dimension": 1024,
        "normalization": "l2",
    }
    assert (
        receipt["legacy_embedding_artifacts"]["malformed_assertion_description_count"]
        == 139
    )
    assert receipt["role_episode_cluster_candidates"]["bundle_count"] == 35
    assert receipt["role_episode_cluster_candidates"]["factless_bundle_count"] == 2
    assert receipt["future_cluster_activation"]["status"] == ("FAIL_CLOSED_NOT_ACTIVE")


def test_checked_in_wave0_receipt_is_internally_valid() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    validate_wave0_receipt(receipt)
    assert receipt["source_baseline"]["commit"] == BASELINE_COMMIT
    assert receipt["source_baseline"]["tree"] == BASELINE_TREE
    assert receipt["next_wave"] == "C03_CLUSTER_EMBEDDING_W1_NODE_HARDENING"


def test_wave0_receipt_rejects_promotion_or_digest_tampering() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    receipt["scope"]["production_promotion_authorized"] = True

    with pytest.raises(ClusterEmbeddingWave0Error, match="scope claim"):
        validate_wave0_receipt(receipt)


def test_cluster_contract_rejects_per_node_vector_default() -> None:
    path = ROOT / (
        "src/apps_rg/fact_inventory/c03_graph_evidence_cluster_contract.v1.json"
    )
    contract = json.loads(path.read_text(encoding="utf-8"))
    contract["cluster_contract"]["vector_policy"][
        "per_node_vector_default_forbidden"
    ] = False

    with pytest.raises(ClusterEmbeddingWave0Error, match="per-node vector"):
        validate_cluster_contract(contract)
