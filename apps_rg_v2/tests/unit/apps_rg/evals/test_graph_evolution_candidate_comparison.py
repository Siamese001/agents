from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apps_rg.evals.graph_evolution_candidate_comparison import (
    evaluate_candidate_comparison,
    load_ge_w7_candidate_comparison_contract,
    validate_ge_w7_candidate_comparison_contract,
)
from apps_rg.evals.c03_graph_evidence_cluster_qualification import expected_judgment_keys
from apps_rg.evals.graph_evolution_qrel_change_impact import assess_candidate_qrel_change_impact

ROOT = Path(__file__).resolve().parents[4]
ACTIVE = ROOT / "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/graph_evidence_cluster_registry.v1.json"


def _candidate_projection():
    active = json.loads(ACTIVE.read_text())
    cluster = {"cluster_id": "ge_cluster:test", "cluster_kind": "candidate_assertion_overlay", "member_node_ids": ["skill_partner_co_selling", "ge_assertion_test"], "allowed_sections": ["competencies", "executive_summary"], "canonical_embedding_text": "Evidence: source backed candidate assertion", "authority_envelope_sha256": "a" * 64}
    registry = {"schema_version": "apps_rg.graph_evolution_candidate_cluster_registry.v1", "clusters": [*active["clusters"], cluster], "held_candidates": active.get("held_candidates") or [], "active_runtime_pointer_changed": False}
    registry["registry_sha256"] = hashlib.sha256(json.dumps(registry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    projection = {"status": "GENERATED_NOT_QUALIFIED", "registry_sha256": registry["registry_sha256"], "projection_sha256": "b" * 64, "vectors": [{"cluster_id": row["cluster_id"]} for row in registry["clusters"]]}
    return registry, projection


def test_ge_w7_contract_requires_human_adjudicated_qrels_and_never_activates():
    contract = load_ge_w7_candidate_comparison_contract(ROOT)
    assert validate_ge_w7_candidate_comparison_contract(contract) == []
    assert contract["human_qrel_authority"]["synthetic_or_model_labels_forbidden"] is True
    assert contract["ge_w7_exit"]["activation_created"] is False


def test_ge_w7_blocks_without_external_human_qrels_and_does_not_calculate_metrics():
    registry, projection = _candidate_projection()
    impact = assess_candidate_qrel_change_impact(registry, projection, repo_root=ROOT)

    result = evaluate_candidate_comparison(registry, projection, impact["receipt"], repo_root=ROOT)

    assert result["status"] == "BLOCKED_QREL_AUTHORITY"
    assert result["reason"] == "GE_W7_HUMAN_QRELS_REQUIRED"
    assert result["metrics"] == {}
    assert result["receipt"]["expected_final_human_judgment_count"] == 468
    assert result["receipt"]["qrel_grades_created"] is False
    assert result["receipt"]["retrieval_metrics_computed"] is False
    assert result["receipt"]["activation_created"] is False


def test_ge_w7_rejects_unfrozen_or_incomplete_qrel_payload_without_scores():
    registry, projection = _candidate_projection()
    impact = assess_candidate_qrel_change_impact(registry, projection, repo_root=ROOT)
    incomplete_qrels = {"schema_version": "apps_rg.graph_evolution_candidate_cluster_qrels.v1", "status": "DRAFT", "judgments": []}
    manifest = json.loads((ROOT / "src/apps_rg/evals/c03_graph_evidence_cluster_queries.v1.json").read_text())
    rankings: dict[str, list[str]] = {}
    for query_id, section_id, cluster_id in expected_judgment_keys(manifest, registry):
        rankings.setdefault(f"{query_id}|{section_id}", []).append(cluster_id)

    result = evaluate_candidate_comparison(registry, projection, impact["receipt"], repo_root=ROOT, rankings=rankings, qrels=incomplete_qrels)

    assert result["status"] == "BLOCKED_QREL_AUTHORITY"
    assert result["metrics"] == {}
