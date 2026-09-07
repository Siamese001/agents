"""Wave 6 contract and receipts for C0.3 semantic-cluster vector generation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

CONTRACT_PATH = Path(
    "src/apps_rg/fact_inventory/c03_graph_evidence_cluster_generation_contract.v1.json"
)
GRAPH_PATH = Path("src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")
ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_evidence_cluster_embeddings")
REGISTRY_PATH = ARTIFACT_DIR / "graph_evidence_cluster_registry.v1.json"
RETIREMENT_MARKER_PATH = (
    ARTIFACT_DIR / "legacy_graph_skill_embedding_retirement.v1.json"
)
W5_RECEIPT_PATH = ARTIFACT_DIR / "wave5_legacy_artifact_retirement_receipt.json"
W6_RECEIPT_PATH = ARTIFACT_DIR / "wave6_cluster_vector_generation_receipt.json"

CONTRACT_SCHEMA_VERSION = "apps_rg.c03_graph_evidence_cluster_generation_contract.v1"
GENERATION_SCHEMA_VERSION = (
    "apps_rg.graph_evidence_cluster_embedding_generation_manifest.v1"
)
RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w6_receipt.v1"
W6_COMPLETION_MARKER = "C03_CLUSTER_EMBEDDING_W6_CLUSTER_VECTORS_GENERATED"


class ClusterEmbeddingGenerationWave6Error(ValueError):
    """Raised when a W6 generation or authority binding is invalid."""


def validate_generation_contract(contract: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        issues.append("schema_version")
    if contract.get("wave") != "W6" or contract.get("status") != "FROZEN":
        issues.append("wave_or_status")
    unit = contract.get("retrieval_unit") or {}
    if unit.get("logical_retrieval_unit") != "graph_evidence_cluster":
        issues.append("retrieval_unit.logical_retrieval_unit")
    if unit.get("exact_active_cluster_count") != 38:
        issues.append("retrieval_unit.exact_active_cluster_count")
    runtime = contract.get("embedding_runtime") or {}
    expected_runtime = {
        "model_id": "BAAI/bge-m3",
        "model_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "dimension": 1024,
        "normalization": "l2",
        "float_storage": "little_endian_float32",
        "network_allowed": False,
        "fallback_allowed": False,
    }
    for field, value in expected_runtime.items():
        if runtime.get(field) != value:
            issues.append(f"embedding_runtime.{field}")
    projection = contract.get("projection_contract") or {}
    if projection.get("maximum_top_k") != 37:
        issues.append("projection_contract.maximum_top_k")
    acceptance = contract.get("wave6_acceptance") or {}
    if acceptance.get("exact_vector_count") != 38:
        issues.append("wave6_acceptance.exact_vector_count")

    required_true = (
        ("source_requirements", "wave5_receipt_required"),
        ("source_requirements", "wave5_retirement_marker_required"),
        ("source_requirements", "wave4_registry_required"),
        ("source_requirements", "canonical_graph_required"),
        ("source_requirements", "canonical_graph_preservation_required"),
        ("source_requirements", "wave4_registry_preservation_required"),
        ("source_requirements", "legacy_artifact_directory_absent_required"),
        ("retrieval_unit", "one_vector_per_active_cluster"),
        ("retrieval_unit", "cluster_id_is_projection_primary_key"),
        ("retrieval_unit", "per_node_vectors_forbidden"),
        ("retrieval_unit", "per_skill_vectors_forbidden"),
        ("retrieval_unit", "held_candidate_vectors_forbidden"),
        ("retrieval_unit", "facet_vectors_forbidden_in_wave6"),
        ("retrieval_unit", "canonical_embedding_text_is_only_model_input"),
        ("embedding_runtime", "local_model_manifest_required"),
        ("embedding_runtime", "runtime_proof_required"),
        ("projection_contract", "immutable_generation_required"),
        ("projection_contract", "registry_digest_binding_required"),
        ("projection_contract", "graph_digest_binding_required"),
        ("projection_contract", "model_artifact_digest_binding_required"),
        ("projection_contract", "canonical_text_digest_binding_required"),
        ("projection_contract", "authority_envelope_digest_binding_required"),
        ("projection_contract", "allowed_section_binding_required"),
        ("projection_contract", "vector_digest_binding_required"),
        ("projection_contract", "exact_current_registry_rehydration_required"),
        ("projection_contract", "bounded_top_k_required"),
        ("projection_contract", "top_k_equal_to_corpus_size_forbidden"),
        ("artifact_contract", "immutable_model_manifest_required"),
        ("artifact_contract", "immutable_sqlite_projection_required"),
        ("artifact_contract", "immutable_generation_manifest_required"),
        ("artifact_contract", "wave6_receipt_required"),
        ("wave6_acceptance", "all_vectors_finite_and_normalized"),
        ("wave6_acceptance", "all_active_clusters_have_exactly_one_vector"),
        ("wave6_acceptance", "all_held_candidates_have_zero_vectors"),
        ("wave6_acceptance", "all_skill_and_node_ids_have_zero_projection_rows"),
        ("wave6_acceptance", "candidate_only_query_smoke_required"),
        ("wave6_acceptance", "section_filter_query_smoke_required"),
        ("wave6_acceptance", "current_authority_rehydration_smoke_required"),
    )
    for section, field in required_true:
        if (contract.get(section) or {}).get(field) is not True:
            issues.append(f"{section}.{field}")
    required_false = (
        ("artifact_contract", "activation_manifest_created"),
        ("artifact_contract", "legacy_environment_flag_repurposed"),
        ("wave6_acceptance", "semantic_retrieval_qualification_completed"),
        ("wave6_acceptance", "activation_authorized"),
        ("wave6_acceptance", "production_promotion_authorized"),
    )
    for section, field in required_false:
        if (contract.get(section) or {}).get(field) is not False:
            issues.append(f"{section}.{field}")
    if issues:
        raise ClusterEmbeddingGenerationWave6Error(
            f"Invalid W6 generation contract fields: {sorted(set(issues))}"
        )


def build_generation_manifest(
    *,
    source_baseline: Mapping[str, Any],
    model: Mapping[str, Any],
    projection: Mapping[str, Any],
    runtime_proof: Mapping[str, Any],
    smoke_proof: Mapping[str, Any],
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": GENERATION_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W6",
        "status": "GENERATED_NOT_QUALIFIED",
        "completion_marker": W6_COMPLETION_MARKER,
        "logical_retrieval_unit": "graph_evidence_cluster",
        "source_baseline": dict(source_baseline),
        "model": dict(model),
        "projection": dict(projection),
        "runtime_proof": dict(runtime_proof),
        "smoke_proof": dict(smoke_proof),
        "query_contract": {
            "candidate_payload_fields": ["cluster_id", "similarity"],
            "minimum_top_k": 1,
            "maximum_top_k": 37,
            "exact_current_registry_rehydration_required": True,
            "similarity_is_claim_authority": False,
        },
        "scope_guards": {
            "cluster_vectors_generated": True,
            "claim_authority_expanded": False,
            "semantic_retrieval_qualification_completed": False,
            "activation_manifest_created": False,
            "production_promotion_authorized": False,
        },
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def validate_generation_manifest(manifest: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if manifest.get("schema_version") != GENERATION_SCHEMA_VERSION:
        issues.append("schema_version")
    if manifest.get("status") != "GENERATED_NOT_QUALIFIED":
        issues.append("status")
    if manifest.get("completion_marker") != W6_COMPLETION_MARKER:
        issues.append("completion_marker")
    if manifest.get("logical_retrieval_unit") != "graph_evidence_cluster":
        issues.append("logical_retrieval_unit")
    projection = manifest.get("projection") or {}
    for field in (
        "path",
        "file_sha256",
        "generation_sha256",
        "registry_sha256",
        "graph_sha256",
        "model_artifact_sha256",
    ):
        if not str(projection.get(field) or ""):
            issues.append(f"projection.{field}")
    if projection.get("vector_count") != 38:
        issues.append("projection.vector_count")
    if projection.get("dimension") != 1024 or projection.get("normalization") != "l2":
        issues.append("projection.shape")
    runtime = manifest.get("runtime_proof") or {}
    if runtime.get("vector_count") != 38 or runtime.get("dimension") != 1024:
        issues.append("runtime_proof.shape")
    if runtime.get("fallback_used") is not False:
        issues.append("runtime_proof.fallback_used")
    smoke = manifest.get("smoke_proof") or {}
    for field in (
        "candidate_only_query_passed",
        "bounded_top_k_rejection_passed",
        "section_filter_query_passed",
        "current_authority_rehydration_passed",
    ):
        if smoke.get(field) is not True:
            issues.append(f"smoke_proof.{field}")
    guards = manifest.get("scope_guards") or {}
    if guards.get("cluster_vectors_generated") is not True:
        issues.append("scope_guards.cluster_vectors_generated")
    for field in (
        "claim_authority_expanded",
        "semantic_retrieval_qualification_completed",
        "activation_manifest_created",
        "production_promotion_authorized",
    ):
        if guards.get(field) is not False:
            issues.append(f"scope_guards.{field}")
    query = manifest.get("query_contract") or {}
    if query.get("candidate_payload_fields") != ["cluster_id", "similarity"]:
        issues.append("query_contract.candidate_payload_fields")
    if query.get("maximum_top_k") != 37:
        issues.append("query_contract.maximum_top_k")
    unsigned = dict(manifest)
    supplied = unsigned.pop("manifest_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("manifest_sha256")
    if issues:
        raise ClusterEmbeddingGenerationWave6Error(
            f"Invalid W6 generation manifest fields: {sorted(set(issues))}"
        )


def build_w6_receipt(
    *,
    contract: Mapping[str, Any],
    generation_manifest: Mapping[str, Any],
    generation_manifest_path: str,
    generation_manifest_file_sha256: str,
    registry: Mapping[str, Any],
    w5_receipt: Mapping[str, Any],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    projection = generation_manifest.get("projection") or {}
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W6",
        "status": "PASS",
        "completion_marker": W6_COMPLETION_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave5_receipt_sha256": w5_receipt.get("receipt_sha256"),
            "wave4_registry_sha256": registry.get("registry_sha256"),
            "canonical_graph_sha256": (registry.get("source_authority") or {}).get(
                "canonical_graph_sha256"
            ),
        },
        "contract": {
            "path": CONTRACT_PATH.as_posix(),
            "schema_version": contract.get("schema_version"),
            "canonical_sha256": canonical_sha256(contract),
        },
        "generation": {
            "manifest_path": generation_manifest_path,
            "manifest_sha256": generation_manifest.get("manifest_sha256"),
            "manifest_file_sha256": generation_manifest_file_sha256,
            "projection_path": projection.get("path"),
            "projection_file_sha256": projection.get("file_sha256"),
            "projection_generation_sha256": projection.get("generation_sha256"),
            "model_artifact_sha256": projection.get("model_artifact_sha256"),
            "vector_count": projection.get("vector_count"),
            "active_cluster_count": len(registry.get("clusters") or []),
            "held_candidate_count": len(registry.get("held_candidates") or []),
            "held_candidate_vector_count": 0,
            "skill_or_node_vector_count": 0,
        },
        "scope": {
            "cluster_vectors_generated": True,
            "legacy_artifacts_remain_retired": True,
            "claim_authority_expanded": False,
            "semantic_retrieval_qualification_completed": False,
            "cluster_embedding_activation_created": False,
            "production_promotion_authorized": False,
        },
        "wave_exit_gates": {
            "node_semantic_hardening": "PASS_W1",
            "edge_assertion_hardening": "PASS_W2",
            "authority_reconciliation": "PASS_W3",
            "cluster_registry_materialization": "PASS_W4",
            "legacy_artifact_retirement": "PASS_W5",
            "cluster_embedding_generation": "PASS_W6",
            "semantic_retrieval_qualification": "OPEN_W7",
            "release_activation": "BLOCKED_UNTIL_QUALIFIED",
            "production_promotion": "NOT_AUTHORIZED",
        },
        "next_wave": "C03_CLUSTER_EMBEDDING_W7_SEMANTIC_RETRIEVAL_QUALIFICATION",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def validate_w6_receipt(receipt: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        issues.append("schema_version")
    if receipt.get("status") != "PASS":
        issues.append("status")
    if receipt.get("completion_marker") != W6_COMPLETION_MARKER:
        issues.append("completion_marker")
    generation = receipt.get("generation") or {}
    if generation.get("vector_count") != 38:
        issues.append("generation.vector_count")
    if generation.get("active_cluster_count") != 38:
        issues.append("generation.active_cluster_count")
    if generation.get("held_candidate_vector_count") != 0:
        issues.append("generation.held_candidate_vector_count")
    if generation.get("skill_or_node_vector_count") != 0:
        issues.append("generation.skill_or_node_vector_count")
    scope = receipt.get("scope") or {}
    for field in ("cluster_vectors_generated", "legacy_artifacts_remain_retired"):
        if scope.get(field) is not True:
            issues.append(f"scope.{field}")
    for field in (
        "claim_authority_expanded",
        "semantic_retrieval_qualification_completed",
        "cluster_embedding_activation_created",
        "production_promotion_authorized",
    ):
        if scope.get(field) is not False:
            issues.append(f"scope.{field}")
    gates = receipt.get("wave_exit_gates") or {}
    if gates.get("cluster_embedding_generation") != "PASS_W6":
        issues.append("wave_exit_gates.cluster_embedding_generation")
    if gates.get("semantic_retrieval_qualification") != "OPEN_W7":
        issues.append("wave_exit_gates.semantic_retrieval_qualification")
    if gates.get("production_promotion") != "NOT_AUTHORIZED":
        issues.append("wave_exit_gates.production_promotion")
    unsigned = dict(receipt)
    supplied = unsigned.pop("receipt_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("receipt_sha256")
    if issues:
        raise ClusterEmbeddingGenerationWave6Error(
            f"Invalid W6 generation receipt fields: {sorted(set(issues))}"
        )


__all__ = [
    "ARTIFACT_DIR",
    "CONTRACT_PATH",
    "ClusterEmbeddingGenerationWave6Error",
    "GENERATION_SCHEMA_VERSION",
    "GRAPH_PATH",
    "RECEIPT_SCHEMA_VERSION",
    "REGISTRY_PATH",
    "RETIREMENT_MARKER_PATH",
    "W5_RECEIPT_PATH",
    "W6_COMPLETION_MARKER",
    "W6_RECEIPT_PATH",
    "build_generation_manifest",
    "build_w6_receipt",
    "validate_generation_contract",
    "validate_generation_manifest",
    "validate_w6_receipt",
]
