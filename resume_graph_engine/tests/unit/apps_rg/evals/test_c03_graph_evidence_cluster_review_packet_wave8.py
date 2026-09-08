from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    QUERY_MANIFEST_PATH,
    W7_RECEIPT_PATH,
    ranking_identity_sha256,
)
from apps_rg.evals.c03_graph_evidence_cluster_review_packet import (
    CONTRACT_PATH,
    W8_RECEIPT_PATH,
    ClusterReviewPacketError,
    build_prelabel_packet_content,
    build_w8_receipt,
    validate_prelabel_packet_content,
    validate_review_packet_contract,
    validate_w8_receipt,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    REGISTRY_PATH,
)

ROOT = Path(__file__).resolve().parents[4]


def _load(relative: Path | str) -> dict:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _complete_rankings(manifest: dict, registry: dict) -> dict[str, list[str]]:
    by_section = {
        str(section): sorted(
            str(cluster["cluster_id"])
            for cluster in registry["clusters"]
            if section in cluster["allowed_sections"]
        )
        for section in manifest["section_ids"]
    }
    return {
        f"{query['query_id']}|{section}": list(by_section[section])
        for query in manifest["queries"]
        for section in manifest["section_ids"]
    }


@pytest.fixture
def packet_inputs() -> tuple[dict, dict, dict[str, list[str]], dict]:
    manifest = _load(QUERY_MANIFEST_PATH)
    registry = _load(REGISTRY_PATH)
    rankings = _complete_rankings(manifest, registry)
    packet = build_prelabel_packet_content(
        query_manifest=manifest,
        registry=registry,
        rankings=rankings,
        ranking_identity_sha256=ranking_identity_sha256(rankings),
        authority_bindings={
            "wave7_receipt_sha256": "1" * 64,
            "query_manifest_sha256": manifest["query_manifest_sha256"],
            "registry_sha256": registry["registry_sha256"],
            "projection_generation_sha256": "2" * 64,
        },
        blinding_nonce="a" * 64,
        repository_root=ROOT,
    )
    return manifest, registry, rankings, packet


def test_w8_contract_freezes_blinded_full_denominator_without_activation() -> None:
    contract = _load(CONTRACT_PATH)

    validate_review_packet_contract(contract)

    assert contract["review_packet"]["candidate_judgment_count_per_cohort"] == 456
    assert contract["review_packet"]["total_reviewer_judgment_slots"] == 912
    assert contract["label_authority"]["labels_created_by_wave8"] is False
    assert contract["activation_boundary"]["production_promotion_authorized"] is False


def test_packet_has_two_complete_independently_blinded_cohorts(
    packet_inputs: tuple[dict, dict, dict[str, list[str]], dict],
) -> None:
    manifest, registry, _, packet = packet_inputs

    validate_prelabel_packet_content(packet, query_manifest=manifest, registry=registry)

    assert set(packet["cohorts"]) == {"reviewer_a", "reviewer_b"}
    for cohort in ("reviewer_a", "reviewer_b"):
        assert len(packet["cohorts"][cohort]) == 48
        assert sum(row["candidate_count"] for row in packet["cohorts"][cohort]) == 456
        visible = json.dumps(packet["cohorts"][cohort], sort_keys=True)
        assert not any(cluster["cluster_id"] in visible for cluster in registry["clusters"])
        assert "frozen_rank" not in visible
        assert "similarity" not in visible
    mapping_a = packet["sealed_mapping"]["cohorts"]["reviewer_a"]
    mapping_b = packet["sealed_mapping"]["cohorts"]["reviewer_b"]
    orders_a = {
        (row["query_id"], row["section_id"]): [
            candidate["cluster_id"] for candidate in row["candidates"]
        ]
        for row in mapping_a
    }
    orders_b = {
        (row["query_id"], row["section_id"]): [
            candidate["cluster_id"] for candidate in row["candidates"]
        ]
        for row in mapping_b
    }
    assert any(orders_a[pair] != orders_b[pair] for pair in orders_a)


def test_packet_validator_rejects_rank_leak_and_partial_denominator(
    packet_inputs: tuple[dict, dict, dict[str, list[str]], dict],
) -> None:
    manifest, registry, _, packet = packet_inputs
    rank_leak = copy.deepcopy(packet)
    rank_leak["cohorts"]["reviewer_a"][0]["candidates"][0]["rank"] = 1

    with pytest.raises(ClusterReviewPacketError, match="unsafe_keys"):
        validate_prelabel_packet_content(
            rank_leak, query_manifest=manifest, registry=registry
        )

    partial = copy.deepcopy(packet)
    partial["cohorts"]["reviewer_b"][0]["candidates"].pop()
    with pytest.raises(ClusterReviewPacketError, match="candidate_conservation"):
        validate_prelabel_packet_content(
            partial, query_manifest=manifest, registry=registry
        )


def test_w8_receipt_is_prelabel_only_and_does_not_clear_w7_gate() -> None:
    contract = _load(CONTRACT_PATH)
    w7 = _load(W7_RECEIPT_PATH)
    packet_manifest = {
        "manifest_sha256": "3" * 64,
        "cohorts": {
            "reviewer_a": {"manifest_sha256": "4" * 64},
            "reviewer_b": {"manifest_sha256": "5" * 64},
        },
    }

    receipt = build_w8_receipt(
        contract=contract,
        w7_receipt=w7,
        packet_manifest=packet_manifest,
        packet_manifest_file_sha256="6" * 64,
        source_commit="7" * 40,
        source_tree="8" * 40,
    )
    validate_w8_receipt(receipt)

    assert receipt["status"] == "PASS_PRELABEL_PACKET_READY"
    assert receipt["label_authority"]["human_labels_present"] is False
    assert receipt["scope"]["semantic_retrieval_qualified"] is False
    assert receipt["scope"]["production_promotion_authorized"] is False
    assert receipt["wave_exit_gates"]["semantic_retrieval_qualification"] == (
        "BLOCKED_QREL_AUTHORITY"
    )


def test_committed_w8_receipt_remains_non_authorizing() -> None:
    if not (ROOT / W8_RECEIPT_PATH).is_file():
        pytest.skip("W8 runtime receipt is generated after the implementation test pass")
    receipt = _load(W8_RECEIPT_PATH)

    validate_w8_receipt(receipt)

    assert receipt["controlled_packet"]["candidate_judgment_count_per_cohort"] == 456
    assert receipt["controlled_packet"]["sealed_mapping_distributed"] is False
    assert receipt["wave_exit_gates"]["production_promotion"] == "NOT_AUTHORIZED"
