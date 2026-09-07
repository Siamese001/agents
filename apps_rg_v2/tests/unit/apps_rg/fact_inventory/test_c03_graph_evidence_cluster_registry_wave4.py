from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from apps_rg.fact_inventory.c03_graph_evidence_cluster_registry import (
    ClusterRegistryWave4Error,
    collect_registry_issues,
    registry_profile,
    validate_registry,
    validate_registry_contract,
    validate_w4_receipt,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
    file_sha256,
)

ROOT = Path(__file__).resolve().parents[4]
GRAPH_PATH = ROOT / "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
CONTRACT_PATH = ROOT / (
    "src/apps_rg/fact_inventory/" "c03_graph_evidence_cluster_registry_contract.v1.json"
)
REGISTRY_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "graph_evidence_cluster_registry.v1.json"
)
W3_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave3_authority_reconciliation_receipt.json"
)
W4_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave4_cluster_registry_receipt.json"
)
CLI_PATH = ROOT / (
    "tools/apps_rg_standalone/c03_graph_evidence_cluster_registry_wave4.py"
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_w4_registry_has_the_frozen_cluster_grain_and_exact_profile() -> None:
    registry = _load(REGISTRY_PATH)
    graph = _load(GRAPH_PATH)

    validate_registry(registry, graph=graph)
    assert registry_profile(registry) == {
        "materialized_cluster_count": 38,
        "role_episode_cluster_count": 23,
        "capability_evidence_cluster_count": 15,
        "future_vector_count": 38,
        "held_candidate_count": 94,
        "held_role_episode_candidate_count": 12,
        "held_capability_candidate_count": 82,
        "active_member_membership_count": 122,
        "active_unique_member_count": 116,
        "overlapping_active_member_count": 5,
        "maximum_active_memberships_per_skill": 3,
        "cluster_size_counts": {
            "2": 17,
            "3": 12,
            "4": 5,
            "5": 1,
            "6": 1,
            "7": 1,
            "14": 1,
        },
        "held_reason_counts": {
            "INSUFFICIENT_COMPATIBLE_MEMBERS": 11,
            "NO_HARDENED_SHARED_FACT_EDGE": 3,
            "NO_LINKED_SOURCE_FACT": 2,
            "SINGLETON_NOT_EMBEDDABLE": 79,
        },
    }
    assert registry["eligible_skill_audit"]["retrieval_eligible_skill_count"] == 198
    assert len(registry["eligible_skill_audit"]["held_unembedded_skill_ids"]) == 82


def test_w4_materializes_only_multi_node_clusters_and_keeps_holds_non_embeddable() -> (
    None
):
    registry = _load(REGISTRY_PATH)

    assert all(len(cluster["member_node_ids"]) >= 2 for cluster in registry["clusters"])
    assert all(cluster["future_vector_count"] == 1 for cluster in registry["clusters"])
    assert all(
        "canonical_embedding_text" not in candidate
        for candidate in registry["held_candidates"]
    )
    singletons = [
        candidate
        for candidate in registry["held_candidates"]
        if "SINGLETON_NOT_EMBEDDABLE" in candidate["hold_reasons"]
    ]
    assert len(singletons) == 79
    assert all(
        len(candidate["candidate_member_node_ids"]) == 1 for candidate in singletons
    )
    assert registry["scope_guards"] == {
        "replacement_vectors_generated": False,
        "legacy_embedding_artifacts_changed": False,
        "legacy_artifact_deletion_authorized": False,
        "production_promotion_authorized": False,
    }


def test_w4_role_clusters_use_compatible_cohorts_without_arbitrary_facets() -> None:
    registry = _load(REGISTRY_PATH)
    clusters = {
        cluster["role_episode_bundle_id"]: cluster
        for cluster in registry["clusters"]
        if cluster["cluster_kind"] == "role_episode"
    }

    platform = clusters["reb_unify_agentic_platform_architecture"]
    assert len(platform["member_node_ids"]) == 14
    assert platform["member_limit_exception"] == (
        "PRIMARY_ROLE_EPISODE_ROOT_NOT_SECONDARY_CLUSTER_NO_FACETING"
    )
    assert platform["future_vector_count"] == 1
    assert set(platform["allowed_sections"]) == {"competencies", "unify_bullets"}
    assert "reb_ey_regulatory_analytics_modernization" not in clusters
    held_roles = {
        item["role_episode_bundle_id"]: item
        for item in registry["held_candidates"]
        if item["candidate_kind"] == "role_episode"
    }
    assert held_roles["reb_ey_regulatory_analytics_modernization"]["hold_reasons"] == [
        "INSUFFICIENT_COMPATIBLE_MEMBERS"
    ]
    assert (
        "NO_LINKED_SOURCE_FACT"
        in held_roles["reb_ibm_cognitive_business_decision_support"]["hold_reasons"]
    )


def test_w4_capability_clusters_share_fact_context_domain_and_sections() -> None:
    registry = _load(REGISTRY_PATH)
    graph = _load(GRAPH_PATH)
    rows = {row["skill_id"]: row for row in graph["skill_rows"]}

    for cluster in registry["clusters"]:
        if cluster["cluster_kind"] != "capability_evidence":
            continue
        assert 2 <= len(cluster["member_node_ids"]) <= 8
        assert len(cluster["linked_fact_ids"]) == 1
        fact_id = cluster["primary_evidence_anchor_id"]
        assert cluster["linked_fact_ids"] == [fact_id]
        assert {
            rows[skill_id]["career_epoch"] for skill_id in cluster["member_node_ids"]
        } == {cluster["career_context_id"]}
        assert {
            rows[skill_id].get("domain_id") or rows[skill_id]["pillar"]
            for skill_id in cluster["member_node_ids"]
        } == {cluster["domain_context_id"]}
        assert {
            tuple(sorted(rows[skill_id]["allowed_sections"]))
            for skill_id in cluster["member_node_ids"]
        } == {tuple(cluster["allowed_sections"])}


def test_w4_authority_envelopes_bind_current_hardened_edges_and_natural_text() -> None:
    registry = _load(REGISTRY_PATH)
    graph = _load(GRAPH_PATH)

    assert collect_registry_issues(registry, graph=graph) == []
    for cluster in registry["clusters"]:
        assert cluster["authority_envelope_sha256"] == canonical_sha256(
            cluster["authority_envelope"]
        )
        text = cluster["canonical_embedding_text"].lower()
        forbidden = (
            [cluster["cluster_id"]]
            + cluster["member_node_ids"]
            + cluster["linked_fact_ids"]
            + cluster["linked_metric_ids"]
            + cluster["allowed_sections"]
        )
        assert not [value for value in forbidden if value.lower() in text]
        assert "Action:" in cluster["canonical_embedding_text"]
        assert "Evidence:" in cluster["canonical_embedding_text"]


def test_w4_registry_validator_detects_per_node_text_edge_and_digest_tampering() -> (
    None
):
    registry = _load(REGISTRY_PATH)
    graph = _load(GRAPH_PATH)
    tampered = copy.deepcopy(registry)
    tampered["clusters"][0]["member_node_ids"] = tampered["clusters"][0][
        "member_node_ids"
    ][:1]
    tampered["clusters"][1]["canonical_embedding_text"] += " skill_raw_id"
    tampered["clusters"][2]["member_edge_ids"] = ["missing_edge"]
    tampered["clusters"][3]["authority_envelope_sha256"] = "0" * 64
    tampered["held_candidates"][0]["canonical_embedding_text"] = "must not exist"

    issues = collect_registry_issues(tampered, graph=graph)

    assert any("REGISTRY_PER_NODE_OR_EMPTY_CLUSTER" in issue for issue in issues)
    assert any("REGISTRY_CANONICAL_TEXT_DRIFT" in issue for issue in issues)
    assert any("REGISTRY_MEMBER_EDGE_NOT_ACTIVE_HARDENED" in issue for issue in issues)
    assert any("REGISTRY_AUTHORITY_ENVELOPE_DIGEST" in issue for issue in issues)
    assert any("REGISTRY_HELD_HAS_EMBEDDING_TEXT" in issue for issue in issues)


def test_w4_contract_and_receipt_are_fail_closed_and_legacy_is_unchanged() -> None:
    contract = _load(CONTRACT_PATH)
    receipt = _load(W4_RECEIPT_PATH)
    w3_receipt = _load(W3_RECEIPT_PATH)

    validate_registry_contract(contract)
    validate_w4_receipt(receipt)
    assert receipt["scope"]["replacement_vectors_generated"] is False
    assert receipt["scope"]["production_promotion_authorized"] is False
    assert receipt["wave_exit_gates"]["cluster_registry_materialization"] == "PASS_W4"
    assert receipt["wave_exit_gates"]["legacy_artifact_retirement"] == "OPEN_W5"
    assert (
        receipt["wave_exit_gates"]["cluster_embedding_generation"] == "BLOCKED_UNTIL_W5"
    )
    assert (
        receipt["legacy_embedding_artifacts"]
        == w3_receipt["legacy_embedding_artifacts"]
    )

    unsafe = copy.deepcopy(contract)
    unsafe["wave4_acceptance"]["production_promotion_authorized"] = True
    with pytest.raises(
        ClusterRegistryWave4Error, match="production_promotion_authorized"
    ):
        validate_registry_contract(unsafe)


def test_w4_cli_check_is_deterministic_and_non_mutating() -> None:
    registry_before = file_sha256(REGISTRY_PATH)
    receipt_before = file_sha256(W4_RECEIPT_PATH)
    graph_before = file_sha256(GRAPH_PATH)

    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    assert output["status"] == "PASS"
    assert output["materialized_cluster_count"] == 38
    assert output["replacement_vectors_generated"] is False
    assert file_sha256(REGISTRY_PATH) == registry_before
    assert file_sha256(W4_RECEIPT_PATH) == receipt_before
    assert file_sha256(GRAPH_PATH) == graph_before
