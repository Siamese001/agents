"""W1C combined-projection tests use frozen W4/W6 inputs without BGE inference."""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from apps_rg.evals.owner_solo import c03_full_resume_qrel_derived_clusters as derived_subject
from apps_rg.evals.owner_solo import c03_full_resume_qrel_w1c as subject
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w1c import (
    build_combined_projection,
    build_combined_registry,
    validate_combined_projection,
    validate_combined_registry,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import canonical_sha256


ROOT = Path(__file__).resolve().parents[4]
W6_RECEIPT = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave6_cluster_vector_generation_receipt.json"
)


@pytest.fixture(autouse=True)
def _algorithm_test_uses_explicit_non_authorizing_scope_override(monkeypatch) -> None:
    for module in (derived_subject, subject):
        monkeypatch.setattr(module, "validate_full_resume_scope", lambda *_args, **_kwargs: [])


def _w6_inputs() -> tuple[Path, dict[str, object]]:
    receipt = json.loads(W6_RECEIPT.read_text(encoding="utf-8"))
    generation_path = ROOT / receipt["generation"]["manifest_path"]
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    projection_path = ROOT / generation["projection"]["path"]
    model_path = ROOT / generation["model"]["path"]
    return projection_path, json.loads(model_path.read_text(encoding="utf-8"))


def _derived_vectors(registry: dict[str, object]) -> dict[str, list[float]]:
    vectors: dict[str, list[float]] = {}
    for index, cluster_id in enumerate(registry["derived_cluster_ids"]):
        vector = [0.0] * 1024
        vector[index] = 1.0
        vectors[str(cluster_id)] = vector
    return vectors


def test_w1c_combines_base_and_w1b_units_for_every_scoped_section() -> None:
    registry = build_combined_registry(ROOT)

    assert validate_combined_registry(registry, ROOT) == []
    assert len(registry["base_cluster_ids"]) == 38
    assert len(registry["derived_cluster_ids"]) == 16
    assert registry["coverage"] == {
        "query_count": 6,
        "section_count": 11,
        "query_section_case_count": 66,
        "candidate_count_by_section": {
            "headline": 8,
            "executive_summary": 12,
            "competencies": 22,
            "unify_bullets": 19,
            "unify_narrative": 3,
            "ibm_bullets": 8,
            "ibm_narrative": 8,
            "ey_bullets": 2,
            "ey_narrative": 2,
            "insurtech_bullets": 8,
            "insurtech_narrative": 8,
        },
        "candidate_judgment_count": 600,
        "full_finite_candidate_universe_required": True,
        "partial_top_k_judging_forbidden": True,
    }
    assert registry["authoritative_lane_boundary"]["authoritative_w4_registry_changed"] is False
    assert registry["authoritative_lane_boundary"]["production_promotion_authorized"] is False


def test_w1c_detects_a_mutated_base_cluster() -> None:
    registry = copy.deepcopy(build_combined_registry(ROOT))
    registry["clusters"][0]["canonical_embedding_text"] = "tampered"
    registry["combined_registry_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in registry.items()
            if key != "combined_registry_sha256"
        }
    )

    assert "BASE_CLUSTER_MUTATION" in validate_combined_registry(registry, ROOT)


def test_w1c_projection_copies_w6_vectors_and_validates_new_bundle_vectors(
    tmp_path: Path,
) -> None:
    registry = build_combined_registry(ROOT)
    base_projection_path, model_manifest = _w6_inputs()
    output_path = tmp_path / "combined.sqlite"

    projection = build_combined_projection(
        output_path,
        combined_registry=registry,
        base_projection_path=base_projection_path,
        model_manifest=model_manifest,
        vectors_by_derived_cluster=_derived_vectors(registry),
    )

    assert projection["vector_count"] == 54
    assert projection["base_vector_count"] == 38
    assert projection["derived_vector_count"] == 16
    assert validate_combined_projection(
        output_path,
        combined_registry=registry,
        base_projection_path=base_projection_path,
        model_manifest=model_manifest,
    ) == []

    with sqlite3.connect(base_projection_path) as base_conn, sqlite3.connect(
        output_path
    ) as combined_conn:
        base_vector = base_conn.execute(
            "SELECT vector FROM cluster_vectors WHERE cluster_id = ?",
            (registry["base_cluster_ids"][0],),
        ).fetchone()[0]
        combined_vector = combined_conn.execute(
            "SELECT vector FROM cluster_vectors WHERE cluster_id = ?",
            (registry["base_cluster_ids"][0],),
        ).fetchone()[0]
    assert combined_vector == base_vector
