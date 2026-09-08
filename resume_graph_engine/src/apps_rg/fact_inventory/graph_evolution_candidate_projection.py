"""GE-W5 candidate-only graph-evidence-cluster and BGE-M3 projection rebuild."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg

from apps_rg.fact_inventory.graph_evolution_authority import build_ge_w0_authority_baseline

GE_W5_CONTRACT_RELATIVE_PATH = Path(
    "src/apps_rg/fact_inventory/graph_evolution_candidate_projection_contract.v1.json"
)
GE_W5_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_candidate_projection_contract.v1"
GE_W5_COMPLETION_MARKER = "GE_W5_CANDIDATE_PROJECTION_BUILT"
ACTIVE_REGISTRY_RELATIVE_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/graph_evidence_cluster_registry.v1.json"
)


class GraphEvolutionCandidateProjectionError(ValueError):
    """Raised when a GE-W5 candidate-only rebuild cannot preserve bindings."""


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _text(value: object) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphEvolutionCandidateProjectionError(f"GE-W5 JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise GraphEvolutionCandidateProjectionError("GE-W5 JSON must be an object")
    return value


def load_ge_w5_candidate_projection_contract(repo_root: Path | str) -> dict[str, Any]:
    return _read_json(Path(repo_root).resolve() / GE_W5_CONTRACT_RELATIVE_PATH)


def validate_ge_w5_candidate_projection_contract(contract: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if contract.get("schema_version") != GE_W5_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_CANDIDATE_PROJECTION":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W5" or contract.get("status") != "FROZEN":
        issues.append("WAVE_OR_STATUS")
    source = contract.get("input")
    if not isinstance(source, Mapping) or source.get("required_graph_validation_state") != "GRAPH_VALIDATED" or any(
        source.get(key) is not True
        for key in ("candidate_version_digest_binding_required", "base_cluster_registry_required", "full_candidate_universe_rebuild_required")
    ):
        issues.append("INPUT")
    unit = contract.get("retrieval_unit")
    if not isinstance(unit, Mapping) or unit.get("logical_retrieval_unit") != "graph_evidence_cluster" or any(
        unit.get(key) is not expected
        for key, expected in (("candidate_assertion_embedded_as_cluster", True), ("per_node_vectors_forbidden", True), ("per_skill_vectors_forbidden", True))
    ):
        issues.append("RETRIEVAL_UNIT")
    embedding = contract.get("embedding")
    if not isinstance(embedding, Mapping) or embedding.get("model_id") != "BAAI/bge-m3" or embedding.get("dimension") != 1024 or embedding.get("normalization") != "l2" or embedding.get("fallback_allowed") is not False or embedding.get("runtime_proof_required") is not True:
        issues.append("EMBEDDING")
    exit_gate = contract.get("ge_w5_exit")
    if not isinstance(exit_gate, Mapping) or exit_gate.get("completion_marker") != GE_W5_COMPLETION_MARKER or exit_gate.get("candidate_state") != "PROJECTION_BUILT" or exit_gate.get("next_gate") != "QREL_CHANGE_IMPACT" or any(
        exit_gate.get(key) is not False
        for key in ("active_runtime_pointer_changed", "active_registry_mutated", "active_projection_mutated", "qrel_evaluation_run", "activation_created")
    ):
        issues.append("GE_W5_EXIT")
    return issues


def _validate_w4_receipt(version: Mapping[str, Any], receipt: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if receipt.get("status") != "PASS" or receipt.get("candidate_state") != "GRAPH_VALIDATED" or receipt.get("completion_marker") != "GE_W4_CANDIDATE_GRAPH_VALIDATED":
        issues.append("GE_W4_STATE")
    if _text(receipt.get("candidate_version_sha256")) != _text(version.get("version_sha256")):
        issues.append("GE_W4_VERSION_BINDING")
    if _text(receipt.get("candidate_id")) != _text((version.get("candidate") or {}).get("candidate_id")):
        issues.append("GE_W4_CANDIDATE_BINDING")
    return issues


def _candidate_cluster(version: Mapping[str, Any], graph: Mapping[str, Any]) -> dict[str, Any]:
    candidate = version["candidate"]
    delta = version["proposed_graph_delta"]
    assertion = delta["assertion_nodes"][0]
    edges = delta["assertion_edges"]
    rows = {str(row.get("skill_id") or ""): row for row in graph.get("skill_rows") or [] if isinstance(row, Mapping)}
    skills = sorted(str(edge["source_node_id"]) for edge in edges)
    allowed_sections = sorted({str(section) for skill in skills for section in (rows.get(skill, {}).get("allowed_sections") or [])})
    text = "\n".join(
        [
            "Graph-evidence cluster: source-backed candidate assertion",
            "Skills: " + ", ".join(skills),
            "Evidence: " + str(candidate["assertion_text"]),
            "Source: " + str(assertion["source_refs"][0]),
        ]
    )
    cluster: dict[str, Any] = {
        "cluster_id": "ge_cluster:" + str(version["version_sha256"])[:24],
        "cluster_kind": "candidate_assertion_overlay",
        "member_node_ids": skills + [str(assertion["node_id"])],
        "allowed_sections": allowed_sections,
        "canonical_embedding_text": text,
        "authority_envelope": {
            "candidate_version_sha256": version["version_sha256"],
            "parent_graph_sha256": version["parent_graph"]["payload_sha256"],
            "candidate_id": candidate["candidate_id"],
            "source_refs": assertion["source_refs"],
        },
    }
    cluster["authority_envelope_sha256"] = _canonical_sha256(cluster["authority_envelope"])
    return cluster


def _check_vectors(vectors: Sequence[Sequence[float]], *, expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise GraphEvolutionCandidateProjectionError("BGE-M3 vector count does not match candidate cluster universe")
    for index, vector in enumerate(vectors):
        if len(vector) != 1024 or not all(math.isfinite(float(value)) for value in vector):
            raise GraphEvolutionCandidateProjectionError(f"BGE-M3 vector contract invalid at index {index}")
        norm = math.sqrt(math.fsum(float(value) ** 2 for value in vector))
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-5):
            raise GraphEvolutionCandidateProjectionError(f"BGE-M3 vector not L2 normalized at index {index}")


def bge_m3_embedder(*, model_path: Path | str, device: str) -> Callable[[list[str]], tuple[Mapping[str, Any], Sequence[Sequence[float]]]]:
    """Return the explicit offline BGE-M3 encoder used for a real GE-W5 rebuild."""

    from apps_rg.fact_inventory.c03_skill_embedding_builder import encode_bge_m3

    resolved_model_path = Path(model_path).resolve()
    resolved_device = _text(device)
    if not resolved_model_path.is_dir() or not resolved_device:
        raise GraphEvolutionCandidateProjectionError("GE-W5 requires a local BGE-M3 model path and device")

    def encode(texts: list[str]) -> tuple[Mapping[str, Any], Sequence[Sequence[float]]]:
        return encode_bge_m3(texts, model_path=resolved_model_path, device=resolved_device, batch_size=len(texts))

    return encode


def build_candidate_cluster_projection(
    version: Mapping[str, Any],
    graph_validation_receipt: Mapping[str, Any],
    *,
    repo_root: Path | str,
    output_dir: Path | str,
    model_manifest: Mapping[str, Any],
    embedder: Callable[[list[str]], tuple[Mapping[str, Any], Sequence[Sequence[float]]]],
    base_registry_path: Path | str | None = None,
) -> dict[str, Any]:
    """Rebuild a full, isolated candidate cluster/vector universe using explicit BGE input."""

    contract = load_ge_w5_candidate_projection_contract(repo_root)
    contract_issues = validate_ge_w5_candidate_projection_contract(contract)
    if contract_issues:
        raise GraphEvolutionCandidateProjectionError(f"GE-W5 contract invalid: {', '.join(contract_issues)}")
    issues = _validate_w4_receipt(version, graph_validation_receipt)
    if issues:
        return {"route": "BLOCKED", "reason": "GE_W5_PRECONDITION_FAILED", "issues": issues}
    if model_manifest.get("model_id") != "BAAI/bge-m3" or model_manifest.get("dimension") != 1024 or model_manifest.get("normalization") != "l2" or not _text(model_manifest.get("artifact_sha256")):
        return {"route": "BLOCKED", "reason": "GE_W5_MODEL_MANIFEST_INVALID"}
    root = Path(repo_root).resolve()
    output = Path(output_dir).resolve()
    registry_path = Path(base_registry_path or (root / ACTIVE_REGISTRY_RELATIVE_PATH))
    base_registry = _read_json(registry_path)
    base_clusters = list(base_registry.get("clusters") or [])
    if not base_clusters:
        return {"route": "BLOCKED", "reason": "GE_W5_BASE_REGISTRY_EMPTY"}
    baseline = build_ge_w0_authority_baseline(root)
    graph = _read_json(root / baseline["canonical_graph"]["path"])
    overlay = _candidate_cluster(version, graph)
    clusters = [dict(cluster) for cluster in base_clusters] + [overlay]
    registry: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_candidate_cluster_registry.v1",
        "status": "MATERIALIZED_NOT_ACTIVATED",
        "logical_retrieval_unit": "graph_evidence_cluster",
        "source": {"candidate_version_sha256": version["version_sha256"], "parent_graph_sha256": version["parent_graph"]["payload_sha256"], "base_registry_sha256": base_registry.get("registry_sha256")},
        "clusters": clusters,
        "held_candidates": list(base_registry.get("held_candidates") or []),
        "active_runtime_pointer_changed": False,
    }
    registry["registry_sha256"] = _canonical_sha256(registry)
    texts = [str(cluster["canonical_embedding_text"]) for cluster in clusters]
    runtime, vectors = embedder(texts)
    if runtime.get("fallback_used") is not False or runtime.get("vector_count") != len(clusters) or runtime.get("dimension") != 1024:
        return {"route": "BLOCKED", "reason": "GE_W5_RUNTIME_PROOF_INVALID"}
    try:
        _check_vectors(vectors, expected_count=len(clusters))
    except GraphEvolutionCandidateProjectionError as exc:
        return {"route": "BLOCKED", "reason": "GE_W5_VECTOR_CONTRACT_INVALID", "issues": [str(exc)]}
    projection: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_candidate_cluster_projection.v1",
        "status": "GENERATED_NOT_QUALIFIED",
        "logical_retrieval_unit": "graph_evidence_cluster",
        "registry_sha256": registry["registry_sha256"],
        "candidate_version_sha256": version["version_sha256"],
        "model": dict(model_manifest),
        "runtime_proof": dict(runtime),
        "vectors": [
            {"cluster_id": cluster["cluster_id"], "vector": [float(value) for value in vector], "vector_sha256": _canonical_sha256([float(value) for value in vector])}
            for cluster, vector in zip(clusters, vectors, strict=True)
        ],
        "active_runtime_pointer_changed": False,
        "activation_created": False,
    }
    projection["projection_sha256"] = _canonical_sha256(projection)
    registry_file = output / "candidate_cluster_registry.v1.json"
    projection_file = output / "candidate_cluster_projection.v1.json"
    if registry_file.exists() or projection_file.exists():
        return {"route": "BLOCKED", "reason": "GE_W5_IMMUTABLE_OUTPUT_EXISTS"}
    _wg.ensure_dir(output)
    _wg.write_text(registry_file, json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _wg.write_text(projection_file, json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"route": "PROJECTION_BUILT", "reason": GE_W5_COMPLETION_MARKER, "registry_path": str(registry_file), "projection_path": str(projection_file), "cluster_count": len(clusters), "active_runtime_pointer_changed": False, "activation_created": False}


__all__ = ["GE_W5_COMPLETION_MARKER", "GE_W5_CONTRACT_RELATIVE_PATH", "GE_W5_CONTRACT_SCHEMA_VERSION", "GraphEvolutionCandidateProjectionError", "bge_m3_embedder", "build_candidate_cluster_projection", "load_ge_w5_candidate_projection_contract", "validate_ge_w5_candidate_projection_contract"]
