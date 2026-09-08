from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    CONTRACT_PATH,
    GRAPH_PATH,
    REGISTRY_PATH,
    W6_RECEIPT_PATH,
    validate_generation_contract,
    validate_generation_manifest,
    validate_w6_receipt,
)
from apps_rg.runtime.graph_evidence_cluster_embedding_projection import (
    GraphEvidenceClusterEmbeddingError,
    GraphEvidenceClusterEmbeddingIndex,
    build_cluster_embedding_projection,
    rehydrate_cluster_candidates,
    validate_cluster_embedding_projection,
)

ROOT = Path(__file__).resolve().parents[4]
CLI_PATH = (
    ROOT / "tools/apps_rg_standalone/c03_graph_evidence_cluster_embedding_wave6.py"
)


def _load(relative: Path | str) -> dict:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_vectors(registry: dict) -> dict[str, list[float]]:
    rows = sorted(registry["clusters"], key=lambda row: row["cluster_id"])
    vectors: dict[str, list[float]] = {}
    for index, row in enumerate(rows):
        vector = [0.0] * 1024
        vector[index] = 1.0
        vectors[row["cluster_id"]] = vector
    return vectors


def _fake_model() -> dict:
    return {
        "model_id": "BAAI/bge-m3",
        "revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "dimension": 1024,
        "normalization": "l2",
        "artifact_sha256": "a" * 64,
    }


def test_w6_contract_freezes_cluster_granularity_and_production_boundary() -> None:
    contract = _load(CONTRACT_PATH)

    validate_generation_contract(contract)

    unit = contract["retrieval_unit"]
    assert unit["logical_retrieval_unit"] == "graph_evidence_cluster"
    assert unit["exact_active_cluster_count"] == 38
    assert unit["per_node_vectors_forbidden"] is True
    assert unit["per_skill_vectors_forbidden"] is True
    assert unit["held_candidate_vectors_forbidden"] is True
    assert contract["wave6_acceptance"]["production_promotion_authorized"] is False


def test_projection_has_exactly_one_row_per_active_cluster(tmp_path: Path) -> None:
    registry = _load(REGISTRY_PATH)
    projection_path = tmp_path / "clusters.sqlite"

    built = build_cluster_embedding_projection(
        projection_path,
        registry=registry,
        vectors_by_cluster=_fake_vectors(registry),
        model_manifest=_fake_model(),
    )

    assert built["vector_count"] == 38
    assert (
        validate_cluster_embedding_projection(
            projection_path, registry=registry, model_manifest=_fake_model()
        )
        == []
    )


def test_projection_rejects_skill_or_held_candidate_rows(tmp_path: Path) -> None:
    registry = _load(REGISTRY_PATH)
    vectors = _fake_vectors(registry)
    vectors[registry["clusters"][0]["member_node_ids"][0]] = [1.0] + [0.0] * 1023

    with pytest.raises(GraphEvidenceClusterEmbeddingError, match="parity mismatch"):
        build_cluster_embedding_projection(
            tmp_path / "orphan.sqlite",
            registry=registry,
            vectors_by_cluster=vectors,
            model_manifest=_fake_model(),
        )


def test_query_returns_only_cluster_id_similarity_and_bounded_top_k(
    tmp_path: Path,
) -> None:
    registry = _load(REGISTRY_PATH)
    vectors = _fake_vectors(registry)
    projection_path = tmp_path / "clusters.sqlite"
    build_cluster_embedding_projection(
        projection_path,
        registry=registry,
        vectors_by_cluster=vectors,
        model_manifest=_fake_model(),
    )
    first_id = sorted(vectors)[0]

    with GraphEvidenceClusterEmbeddingIndex(
        projection_path,
        expected_registry_sha256=registry["registry_sha256"],
        expected_model_artifact_sha256="a" * 64,
    ) as index:
        candidates = index.query(vectors[first_id], k=3)
        assert candidates[0] == {"cluster_id": first_id, "similarity": 1.0}
        assert all(set(row) == {"cluster_id", "similarity"} for row in candidates)
        with pytest.raises(GraphEvidenceClusterEmbeddingError, match="top-k"):
            index.query(vectors[first_id], k=38)


def test_rehydration_resolves_current_registry_and_graph_authority(
    tmp_path: Path,
) -> None:
    del tmp_path
    registry = _load(REGISTRY_PATH)
    graph = _load(GRAPH_PATH)
    cluster = sorted(registry["clusters"], key=lambda row: row["cluster_id"])[0]
    section_id = cluster["allowed_sections"][0]

    hydrated = rehydrate_cluster_candidates(
        [{"cluster_id": cluster["cluster_id"], "similarity": 0.75}],
        registry=registry,
        graph_payload=graph,
        section_id=section_id,
    )

    assert hydrated[0]["cluster_id"] == cluster["cluster_id"]
    assert (
        hydrated[0]["authority_envelope_sha256"] == cluster["authority_envelope_sha256"]
    )
    assert hydrated[0]["similarity"] == 0.75


def test_committed_w6_artifacts_are_digest_bound_and_not_activated() -> None:
    receipt = _load(W6_RECEIPT_PATH)
    validate_w6_receipt(receipt)
    generation_path = ROOT / receipt["generation"]["manifest_path"]
    assert _sha(generation_path) == receipt["generation"]["manifest_file_sha256"]
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    validate_generation_manifest(generation)
    assert generation["projection"]["vector_count"] == 38
    assert generation["projection"]["held_candidate_vector_count"] == 0
    assert generation["projection"]["skill_or_node_vector_count"] == 0
    assert generation["scope_guards"]["activation_manifest_created"] is False
    assert not (
        ROOT / "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
        "graph_evidence_cluster_embedding_activation_manifest.json"
    ).exists()


def test_w6_cli_check_is_read_only() -> None:
    receipt_path = ROOT / W6_RECEIPT_PATH
    receipt_before = _sha(receipt_path)

    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    assert output["status"] == "PASS"
    assert output["vector_count"] == 38
    assert output["held_candidate_vector_count"] == 0
    assert output["skill_or_node_vector_count"] == 0
    assert output["semantic_retrieval_qualification"] == "OPEN_W7"
    assert output["production_promotion"] == "NOT_AUTHORIZED"
    assert _sha(receipt_path) == receipt_before
