from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apps_rg.evals.graph_evolution_controlled_activation import (
    evaluate_canary_shadow,
    load_ge_w8_controlled_activation_contract,
    prepare_controlled_canary_plan,
    validate_ge_w8_controlled_activation_contract,
)

ROOT = Path(__file__).resolve().parents[4]
ACTIVE = ROOT / "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/graph_evidence_cluster_registry.v1.json"


def _candidate_projection():
    active = json.loads(ACTIVE.read_text())
    cluster = {"cluster_id": "ge_cluster:test", "cluster_kind": "candidate_assertion_overlay", "member_node_ids": ["skill_partner_co_selling", "ge_assertion_test"], "allowed_sections": ["competencies", "executive_summary"], "canonical_embedding_text": "Evidence: source backed candidate assertion", "authority_envelope_sha256": "a" * 64}
    registry = {"schema_version": "apps_rg.graph_evolution_candidate_cluster_registry.v1", "clusters": [*active["clusters"], cluster], "held_candidates": active.get("held_candidates") or [], "active_runtime_pointer_changed": False}
    registry["registry_sha256"] = hashlib.sha256(json.dumps(registry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    projection = {"status": "GENERATED_NOT_QUALIFIED", "registry_sha256": registry["registry_sha256"], "projection_sha256": "b" * 64, "vectors": [{"cluster_id": row["cluster_id"]} for row in registry["clusters"]]}
    return registry, projection


def _qualified_comparison(registry, projection):
    return {
        "completion_marker": "GE_W7_CANDIDATE_COMPARISON_EVALUATED",
        "status": "QUALIFIED",
        "candidate_state": "CANDIDATE_COMPARISON_EVALUATED",
        "candidate_registry_sha256": registry["registry_sha256"],
        "candidate_projection_sha256": projection["projection_sha256"],
        "receipt_sha256": "c" * 64,
    }


def _release_authorization(registry, projection):
    return {
        "schema_version": "apps_rg.graph_evolution_release_authorization.v1",
        "status": "EXPLICIT_RELEASE_AUTHORIZED",
        "candidate_registry_sha256": registry["registry_sha256"],
        "candidate_projection_sha256": projection["projection_sha256"],
        "qualified_comparison_receipt_sha256": "c" * 64,
        "authorized_by": "human-release-authority://release-steward",
        "release_authority_receipt_sha256": "d" * 64,
        "candidate_traffic_fraction": 0.05,
    }


def test_ge_w8_contract_is_reversible_and_requires_uwg_for_pointer_changes():
    contract = load_ge_w8_controlled_activation_contract(ROOT)
    assert validate_ge_w8_controlled_activation_contract(contract) == []
    assert contract["entry_requirements"]["uwg_required_for_any_active_pointer_change"] is True
    assert contract["rollback"]["restore_prior_active_registry_required"] is True


def test_ge_w8_refuses_to_plan_canary_before_a_qualified_ge_w7_receipt():
    registry, projection = _candidate_projection()
    blocked = {"status": "BLOCKED_QREL_AUTHORITY"}

    result = prepare_controlled_canary_plan(registry, projection, blocked, None, repo_root=ROOT, prior_active_registry_sha256="a" * 64)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "GE_W8_QUALIFIED_COMPARISON_REQUIRED"
    assert result["activation_created"] is False


def test_ge_w8_plan_needs_explicit_release_authority_and_remains_non_writing():
    registry, projection = _candidate_projection()
    comparison = _qualified_comparison(registry, projection)

    blocked = prepare_controlled_canary_plan(registry, projection, comparison, None, repo_root=ROOT, prior_active_registry_sha256="a" * 64)
    ready = prepare_controlled_canary_plan(registry, projection, comparison, _release_authorization(registry, projection), repo_root=ROOT, prior_active_registry_sha256="a" * 64)

    assert blocked["status"] == "BLOCKED_RELEASE_AUTHORITY"
    assert ready["status"] == "CANARY_PLAN_READY"
    assert ready["activation_created"] is False
    assert ready["plan"]["active_runtime_pointer_changed"] is False
    assert ready["plan"]["rollback"]["restore_registry_sha256"] == "a" * 64


def test_ge_w8_shadow_guardrail_breach_requires_uwg_pointer_restore():
    registry, projection = _candidate_projection()
    ready = prepare_controlled_canary_plan(registry, projection, _qualified_comparison(registry, projection), _release_authorization(registry, projection), repo_root=ROOT, prior_active_registry_sha256="a" * 64)
    observation = {
        "plan_sha256": ready["plan"]["plan_sha256"],
        "request_count": 100,
        "elapsed_window_seconds": 3600,
        "candidate_error_rate": 0.03,
        "baseline_error_rate": 0.0,
        "candidate_p95_latency_ms": 100,
        "baseline_p95_latency_ms": 100,
        "evidence_authority_bypass_count": 0,
        "section_policy_leak_count": 0,
        "projection_issue_count": 0,
    }

    result = evaluate_canary_shadow(ready["plan"], observation, repo_root=ROOT)

    assert result["status"] == "ROLLBACK_REQUIRED"
    assert result["receipt"]["rollback_operation"] == "UWG_POINTER_RESTORE"
    assert result["receipt"]["active_runtime_pointer_changed"] is False
