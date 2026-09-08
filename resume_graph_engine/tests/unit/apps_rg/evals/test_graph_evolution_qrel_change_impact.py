from __future__ import annotations

import json
from pathlib import Path

from apps_rg.evals.graph_evolution_qrel_change_impact import assess_candidate_qrel_change_impact, load_ge_w6_qrel_change_impact_contract, validate_ge_w6_qrel_change_impact_contract

ROOT = Path(__file__).resolve().parents[4]
ACTIVE = ROOT / "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/graph_evidence_cluster_registry.v1.json"


def _candidate_projection():
    active = json.loads(ACTIVE.read_text())
    cluster = {"cluster_id":"ge_cluster:test", "cluster_kind":"candidate_assertion_overlay", "member_node_ids":["skill_partner_co_selling", "ge_assertion_test"], "allowed_sections":["competencies", "executive_summary"], "canonical_embedding_text":"Evidence: source backed candidate assertion", "authority_envelope_sha256":"a" * 64}
    registry = {"schema_version":"apps_rg.graph_evolution_candidate_cluster_registry.v1", "clusters":[*active["clusters"], cluster], "held_candidates":active.get("held_candidates") or [], "active_runtime_pointer_changed":False}
    import hashlib
    registry["registry_sha256"] = hashlib.sha256(json.dumps(registry,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    projection = {"status":"GENERATED_NOT_QUALIFIED","registry_sha256":registry["registry_sha256"],"projection_sha256":"b" * 64,"vectors":[{"cluster_id":row["cluster_id"]} for row in registry["clusters"]]}
    return registry, projection


def test_ge_w6_contract_prohibits_labels_and_metrics():
    contract = load_ge_w6_qrel_change_impact_contract(ROOT)
    assert validate_ge_w6_qrel_change_impact_contract(contract) == []
    assert contract["ge_w6_exit"]["qrel_grades_created"] is False


def test_candidate_change_expands_full_qrel_denominator_without_authoring_grades():
    registry, projection = _candidate_projection()
    result = assess_candidate_qrel_change_impact(registry, projection, repo_root=ROOT)
    receipt = result["receipt"]
    assert result["route"] == "BLOCKED_QREL_AUTHORITY"
    assert receipt["active_cluster_count"] == 38
    assert receipt["candidate_cluster_count"] == 39
    assert receipt["candidate_full_judgment_count"] == 468
    assert receipt["changed_judgment_count"] == 12
    assert receipt["required_human_review"]["required_primary_judgment_count"] == 936
    assert receipt["required_human_review"]["required_adjudication_count"] == 468
    assert receipt["qrel_grades_created"] is False
    assert receipt["retrieval_metrics_computed"] is False
    assert receipt["synthetic_labels_created"] is False
    assert "judgments" not in receipt


def test_projection_registry_mismatch_blocks_impact_assessment():
    registry, projection = _candidate_projection()
    projection["registry_sha256"] = "0" * 64
    result = assess_candidate_qrel_change_impact(registry, projection, repo_root=ROOT)
    assert result["route"] == "BLOCKED"
