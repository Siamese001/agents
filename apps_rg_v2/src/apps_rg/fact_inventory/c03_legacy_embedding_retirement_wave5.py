"""Wave 5 retirement contract for malformed per-skill C0.3 embeddings.

The retirement marker permanently closes the legacy one-vector-per-skill lane.
Historical artifact identities stay digest-bound and recoverable from the W4
Git baseline, but they are absent from the working tree and cannot be loaded or
reactivated.  Replacement cluster vectors remain a later wave.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

CONTRACT_PATH = Path(
    "src/apps_rg/fact_inventory/" "c03_legacy_embedding_retirement_contract.v1.json"
)
GRAPH_PATH = Path("src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")
REGISTRY_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "graph_evidence_cluster_registry.v1.json"
)
W4_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave4_cluster_registry_receipt.json"
)
LEGACY_ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_skill_embeddings")
RETIREMENT_MARKER_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "legacy_graph_skill_embedding_retirement.v1.json"
)
W5_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave5_legacy_artifact_retirement_receipt.json"
)

CONTRACT_SCHEMA_VERSION = "apps_rg.c03_legacy_embedding_retirement_contract.v1"
MARKER_SCHEMA_VERSION = "apps_rg.c03_legacy_embedding_retirement.v1"
RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w5_receipt.v1"
RETIREMENT_MARKER = "C03_LEGACY_GRAPH_SKILL_EMBEDDINGS_RETIRED"
W5_COMPLETION_MARKER = "C03_CLUSTER_EMBEDDING_W5_LEGACY_ARTIFACTS_RETIRED"


class LegacyEmbeddingRetirementWave5Error(ValueError):
    """Raised when the W5 retirement boundary is invalid."""


def validate_retirement_contract(contract: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        issues.append("schema_version")
    if contract.get("wave") != "W5" or contract.get("status") != "FROZEN":
        issues.append("wave_or_status")
    boundary = contract.get("retirement_boundary") or {}
    if boundary.get("retired_artifact_directory") != LEGACY_ARTIFACT_DIR.as_posix():
        issues.append("retirement_boundary.retired_artifact_directory")
    if boundary.get("exact_frozen_artifact_count") != 13:
        issues.append("retirement_boundary.exact_frozen_artifact_count")
    required_true = (
        ("source_requirements", "wave4_receipt_required"),
        ("source_requirements", "wave4_registry_required"),
        ("source_requirements", "exact_frozen_legacy_inventory_required"),
        ("source_requirements", "canonical_graph_preservation_required"),
        ("retirement_boundary", "delete_every_frozen_artifact"),
        ("retirement_boundary", "unexpected_file_blocks_retirement"),
        ("retirement_boundary", "retirement_marker_required"),
        ("retirement_boundary", "runtime_loader_must_fail_closed"),
        ("retirement_boundary", "legacy_preflight_must_fail_closed"),
        (
            "retirement_boundary",
            "legacy_build_qualify_activate_rebuild_smoke_must_fail_closed",
        ),
        ("retirement_boundary", "historical_receipts_remain_auditable"),
        ("retirement_boundary", "git_recovery_binding_required"),
        ("replacement_boundary", "wave4_cluster_registry_preserved"),
        ("wave5_acceptance", "all_frozen_legacy_artifacts_absent"),
        ("wave5_acceptance", "legacy_artifact_directory_empty_or_absent"),
        ("wave5_acceptance", "retirement_marker_digest_valid"),
        ("wave5_acceptance", "retired_loader_precedes_manifest_access"),
        ("wave5_acceptance", "canonical_graph_byte_identical_to_wave4"),
        ("wave5_acceptance", "cluster_registry_byte_identical_to_wave4"),
        ("wave5_acceptance", "wave6_generation_gate_opened"),
    )
    for section, field in required_true:
        if (contract.get(section) or {}).get(field) is not True:
            issues.append(f"{section}.{field}")
    required_false = (
        ("replacement_boundary", "replacement_vectors_generated"),
        ("replacement_boundary", "cluster_embedding_activation_created"),
        ("replacement_boundary", "legacy_environment_flag_repurposed"),
        ("replacement_boundary", "production_promotion_authorized"),
        ("wave5_acceptance", "wave6_generation_executed"),
        ("wave5_acceptance", "production_promotion_authorized"),
    )
    for section, field in required_false:
        if (contract.get(section) or {}).get(field) is not False:
            issues.append(f"{section}.{field}")
    if issues:
        raise LegacyEmbeddingRetirementWave5Error(
            f"Invalid W5 retirement contract fields: {sorted(issues)}"
        )


def frozen_legacy_inventory(w4_receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    legacy = w4_receipt.get("legacy_embedding_artifacts") or {}
    artifacts = legacy.get("artifacts")
    if legacy.get("artifact_count") != 13 or not isinstance(artifacts, list):
        raise LegacyEmbeddingRetirementWave5Error(
            "W4 receipt does not contain the exact 13-artifact legacy inventory"
        )
    records = [dict(item) for item in artifacts if isinstance(item, Mapping)]
    if len(records) != 13:
        raise LegacyEmbeddingRetirementWave5Error(
            "W4 legacy artifact inventory is malformed"
        )
    paths = [str(item.get("path") or "") for item in records]
    if len(paths) != len(set(paths)) or any(
        not path.startswith(f"{LEGACY_ARTIFACT_DIR.as_posix()}/") for path in paths
    ):
        raise LegacyEmbeddingRetirementWave5Error(
            "W4 legacy artifact inventory escapes or duplicates the retired directory"
        )
    return sorted(records, key=lambda item: str(item["path"]))


def build_retirement_marker(
    *,
    w4_receipt: Mapping[str, Any],
    registry: Mapping[str, Any],
    source_commit: str,
    source_tree: str,
    git_blob_sha1_by_path: Mapping[str, str],
) -> dict[str, Any]:
    frozen = frozen_legacy_inventory(w4_receipt)
    retired = []
    for record in frozen:
        path = str(record["path"])
        blob = str(git_blob_sha1_by_path.get(path) or "")
        if len(blob) != 40:
            raise LegacyEmbeddingRetirementWave5Error(
                f"Missing W4 Git recovery blob for {path}"
            )
        retired.append(dict(record) | {"w4_git_blob_sha1": blob})
    marker: dict[str, Any] = {
        "schema_version": MARKER_SCHEMA_VERSION,
        "status": "RETIRED",
        "completion_marker": RETIREMENT_MARKER,
        "retired_lane": "one_vector_per_skill_assertion",
        "retired_artifact_directory": LEGACY_ARTIFACT_DIR.as_posix(),
        "retired_artifact_count": len(retired),
        "retired_total_size_bytes": sum(int(item["size_bytes"]) for item in retired),
        "retired_artifacts": retired,
        "recovery_authority": {
            "source_commit": source_commit,
            "source_tree": source_tree,
            "recovery_command_template": "git show <source_commit>:<artifact_path>",
            "recovery_is_for_audit_only": True,
            "runtime_reactivation_forbidden": True,
        },
        "source_authority": {
            "wave4_receipt_sha256": w4_receipt.get("receipt_sha256"),
            "wave4_registry_sha256": registry.get("registry_sha256"),
            "canonical_graph_sha256": (w4_receipt.get("source_baseline") or {}).get(
                "canonical_graph_sha256"
            ),
        },
        "runtime_disposition": {
            "legacy_loader": "FAIL_CLOSED_RETIRED",
            "legacy_preflight": "FAIL_CLOSED_RETIRED",
            "legacy_build": "FAIL_CLOSED_RETIRED",
            "legacy_qualify": "FAIL_CLOSED_RETIRED",
            "legacy_activate": "FAIL_CLOSED_RETIRED",
            "legacy_rebuild": "FAIL_CLOSED_RETIRED",
            "legacy_smoke": "FAIL_CLOSED_RETIRED",
        },
        "scope_guards": {
            "replacement_vectors_generated": False,
            "cluster_embedding_activation_created": False,
            "legacy_environment_flag_repurposed": False,
            "production_promotion_authorized": False,
        },
    }
    marker["retirement_sha256"] = canonical_sha256(marker)
    return marker


def validate_retirement_marker(marker: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if marker.get("schema_version") != MARKER_SCHEMA_VERSION:
        issues.append("schema_version")
    if marker.get("status") != "RETIRED":
        issues.append("status")
    if marker.get("completion_marker") != RETIREMENT_MARKER:
        issues.append("completion_marker")
    if marker.get("retired_lane") != "one_vector_per_skill_assertion":
        issues.append("retired_lane")
    if marker.get("retired_artifact_directory") != LEGACY_ARTIFACT_DIR.as_posix():
        issues.append("retired_artifact_directory")
    artifacts = marker.get("retired_artifacts") or []
    if marker.get("retired_artifact_count") != 13 or len(artifacts) != 13:
        issues.append("retired_artifact_count")
    paths = [str(item.get("path") or "") for item in artifacts]
    if len(paths) != len(set(paths)) or any(
        not path.startswith(f"{LEGACY_ARTIFACT_DIR.as_posix()}/") for path in paths
    ):
        issues.append("retired_artifact_paths")
    if marker.get("retired_total_size_bytes") != sum(
        int(item.get("size_bytes") or 0) for item in artifacts
    ):
        issues.append("retired_total_size_bytes")
    if any(len(str(item.get("w4_git_blob_sha1") or "")) != 40 for item in artifacts):
        issues.append("w4_git_blob_sha1")
    recovery = marker.get("recovery_authority") or {}
    if (
        recovery.get("recovery_is_for_audit_only") is not True
        or recovery.get("runtime_reactivation_forbidden") is not True
    ):
        issues.append("recovery_authority")
    runtime = marker.get("runtime_disposition") or {}
    if set(runtime.values()) != {"FAIL_CLOSED_RETIRED"} or len(runtime) != 7:
        issues.append("runtime_disposition")
    guards = marker.get("scope_guards") or {}
    if any(
        guards.get(field) is not False
        for field in (
            "replacement_vectors_generated",
            "cluster_embedding_activation_created",
            "legacy_environment_flag_repurposed",
            "production_promotion_authorized",
        )
    ):
        issues.append("scope_guards")
    unsigned = dict(marker)
    supplied = unsigned.pop("retirement_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("retirement_sha256")
    if issues:
        raise LegacyEmbeddingRetirementWave5Error(
            f"Invalid W5 retirement marker fields: {sorted(issues)}"
        )


def historical_legacy_inventory_from_marker(
    marker: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return the exact pre-W5 records used by historical W1-W4 checks."""

    validate_retirement_marker(marker)
    return [
        {key: value for key, value in record.items() if key != "w4_git_blob_sha1"}
        for record in marker["retired_artifacts"]
    ]


def build_w5_receipt(
    *,
    contract: Mapping[str, Any],
    marker: Mapping[str, Any],
    w4_receipt: Mapping[str, Any],
    registry: Mapping[str, Any],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W5",
        "status": "PASS",
        "completion_marker": W5_COMPLETION_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave4_receipt_sha256": w4_receipt.get("receipt_sha256"),
            "wave4_registry_sha256": registry.get("registry_sha256"),
            "canonical_graph_sha256": (w4_receipt.get("source_baseline") or {}).get(
                "canonical_graph_sha256"
            ),
        },
        "contract": {
            "path": CONTRACT_PATH.as_posix(),
            "schema_version": contract.get("schema_version"),
            "canonical_sha256": canonical_sha256(contract),
        },
        "retirement": {
            "marker_path": RETIREMENT_MARKER_PATH.as_posix(),
            "marker_sha256": marker.get("retirement_sha256"),
            "retired_artifact_directory": LEGACY_ARTIFACT_DIR.as_posix(),
            "deleted_artifact_count": marker.get("retired_artifact_count"),
            "deleted_total_size_bytes": marker.get("retired_total_size_bytes"),
            "unexpected_file_count": 0,
            "remaining_file_count": 0,
            "git_recovery_bound": True,
            "runtime_fail_closed": True,
        },
        "preservation": {
            "canonical_graph_byte_identical": True,
            "wave4_registry_byte_identical": True,
            "historical_receipts_preserved": True,
            "legacy_environment_flag_repurposed": False,
        },
        "scope": {
            "legacy_artifacts_retired": True,
            "claim_authority_expanded": False,
            "replacement_vectors_generated": False,
            "cluster_embedding_activation_created": False,
            "production_promotion_authorized": False,
        },
        "wave_exit_gates": {
            "node_semantic_hardening": "PASS_W1",
            "edge_assertion_hardening": "PASS_W2",
            "authority_reconciliation": "PASS_W3",
            "cluster_registry_materialization": "PASS_W4",
            "legacy_artifact_retirement": "PASS_W5",
            "cluster_embedding_generation": "OPEN_W6",
            "production_promotion": "NOT_AUTHORIZED",
        },
        "next_wave": "C03_CLUSTER_EMBEDDING_W6_CLUSTER_VECTOR_GENERATION",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def validate_w5_receipt(receipt: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        issues.append("schema_version")
    if receipt.get("status") != "PASS":
        issues.append("status")
    if receipt.get("completion_marker") != W5_COMPLETION_MARKER:
        issues.append("completion_marker")
    retirement = receipt.get("retirement") or {}
    if retirement.get("deleted_artifact_count") != 13:
        issues.append("retirement.deleted_artifact_count")
    if retirement.get("unexpected_file_count") != 0:
        issues.append("retirement.unexpected_file_count")
    if retirement.get("remaining_file_count") != 0:
        issues.append("retirement.remaining_file_count")
    if retirement.get("git_recovery_bound") is not True:
        issues.append("retirement.git_recovery_bound")
    if retirement.get("runtime_fail_closed") is not True:
        issues.append("retirement.runtime_fail_closed")
    scope = receipt.get("scope") or {}
    if scope.get("legacy_artifacts_retired") is not True:
        issues.append("scope.legacy_artifacts_retired")
    for field in (
        "claim_authority_expanded",
        "replacement_vectors_generated",
        "cluster_embedding_activation_created",
        "production_promotion_authorized",
    ):
        if scope.get(field) is not False:
            issues.append(f"scope.{field}")
    gates = receipt.get("wave_exit_gates") or {}
    if gates.get("legacy_artifact_retirement") != "PASS_W5":
        issues.append("wave_exit_gates.legacy_artifact_retirement")
    if gates.get("cluster_embedding_generation") != "OPEN_W6":
        issues.append("wave_exit_gates.cluster_embedding_generation")
    if gates.get("production_promotion") != "NOT_AUTHORIZED":
        issues.append("wave_exit_gates.production_promotion")
    unsigned = dict(receipt)
    supplied = unsigned.pop("receipt_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("receipt_sha256")
    if issues:
        raise LegacyEmbeddingRetirementWave5Error(
            f"Invalid W5 retirement receipt fields: {sorted(issues)}"
        )
