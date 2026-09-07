"""W2 ranking tests use fixed vectors and never create human labels."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.evals.owner_solo import c03_full_resume_qrel_derived_clusters as derived_subject
from apps_rg.evals.owner_solo import c03_full_resume_qrel_w1c as w1c_subject
from apps_rg.evals.owner_solo import c03_full_resume_qrel_w2 as subject
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w1c import (
    build_combined_registry,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w2 import (
    build_frozen_ranking_artifact,
    build_w2_query_manifest,
    validate_frozen_ranking_artifact,
    validate_w2_query_manifest,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import canonical_sha256


ROOT = Path(__file__).resolve().parents[4]
W6_RECEIPT = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave6_cluster_vector_generation_receipt.json"
)


@pytest.fixture(autouse=True)
def _algorithm_test_uses_explicit_non_authorizing_scope_override(monkeypatch) -> None:
    for module in (derived_subject, w1c_subject, subject):
        monkeypatch.setattr(module, "validate_full_resume_scope", lambda *_args, **_kwargs: [])


def _model_manifest() -> dict[str, object]:
    receipt = json.loads(W6_RECEIPT.read_text(encoding="utf-8"))
    generation = json.loads(
        (ROOT / receipt["generation"]["manifest_path"]).read_text(encoding="utf-8")
    )
    return json.loads((ROOT / generation["model"]["path"]).read_text(encoding="utf-8"))


def _w1c_context(combined: dict[str, object]) -> dict[str, object]:
    return {
        "combined": combined,
        "receipt_path": ROOT / ".runtime/c03-owner-solo-qrel/w1c/example.json",
        "receipt": {"receipt_sha256": "a" * 64},
        "projection": {
            "generation_sha256": "b" * 64,
            "file_sha256": "c" * 64,
        },
    }


def _complete_rankings(
    query_manifest: dict[str, object], combined: dict[str, object]
) -> dict[str, list[tuple[str, float]]]:
    rankings: dict[str, list[tuple[str, float]]] = {}
    candidates_by_section = combined["section_candidate_cluster_ids"]
    for query in query_manifest["queries"]:
        for section_id in query_manifest["section_ids"]:
            candidates = candidates_by_section[section_id]
            rankings[f"{query['query_id']}|{section_id}"] = [
                (cluster_id, float(-index))
                for index, cluster_id in enumerate(candidates, start=1)
            ]
    return rankings


def _query_vector_digests(query_manifest: dict[str, object]) -> dict[str, str]:
    return {
        str(query["query_id"]): hashlib.sha256(
            str(query["query_id"]).encode("utf-8")
        ).hexdigest()
        for query in query_manifest["queries"]
    }


def test_w2_query_manifest_freezes_exact_target_query_construction() -> None:
    manifest = build_w2_query_manifest(ROOT)

    assert validate_w2_query_manifest(manifest, ROOT) == []
    assert manifest["query_construction"] == {
        "exact_text": "utf8(jd).strip() + double_newline + utf8(brief).strip()",
        "one_bge_m3_query_vector_per_target": True,
        "section_id_applies_candidate_universe_filter_only": True,
    }
    assert len(manifest["queries"]) == 6
    assert len(manifest["section_ids"]) == 11
    assert all(len(query["query_text_sha256"]) == 64 for query in manifest["queries"])


def test_w2_frozen_rankings_conserve_all_66_pairs_and_600_candidates() -> None:
    query_manifest = build_w2_query_manifest(ROOT)
    combined = build_combined_registry(ROOT)
    context = _w1c_context(combined)
    artifact = build_frozen_ranking_artifact(
        repo_root=ROOT,
        query_manifest=query_manifest,
        w1c_context=context,
        model_manifest=_model_manifest(),
        rankings_by_pair=_complete_rankings(query_manifest, combined),
        query_vector_sha256=_query_vector_digests(query_manifest),
        runtime_proof={"fallback_used": False, "vector_count": 6, "dimension": 1024},
    )

    assert artifact["query_section_count"] == 66
    assert artifact["candidate_judgment_count"] == 600
    assert artifact["sealed_mapping"]["reviewer_visible"] is False
    assert validate_frozen_ranking_artifact(
        artifact,
        query_manifest=query_manifest,
        w1c_context=context,
        model_manifest=_model_manifest(),
        repo_root=ROOT,
    ) == []


def test_w2_rejects_a_rank_conservation_violation() -> None:
    query_manifest = build_w2_query_manifest(ROOT)
    combined = build_combined_registry(ROOT)
    context = _w1c_context(combined)
    artifact = build_frozen_ranking_artifact(
        repo_root=ROOT,
        query_manifest=query_manifest,
        w1c_context=context,
        model_manifest=_model_manifest(),
        rankings_by_pair=_complete_rankings(query_manifest, combined),
        query_vector_sha256=_query_vector_digests(query_manifest),
        runtime_proof={"fallback_used": False, "vector_count": 6, "dimension": 1024},
    )
    tampered = copy.deepcopy(artifact)
    tampered["rankings"][0]["candidates"][1]["frozen_rank"] = 99
    tampered["ranking_artifact_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in tampered.items()
            if key != "ranking_artifact_sha256"
        }
    )

    assert "RANK_CONSERVATION:anthropic_manager_applied_ai_architecture_partnerships|headline" in validate_frozen_ranking_artifact(
        tampered,
        query_manifest=query_manifest,
        w1c_context=context,
        model_manifest=_model_manifest(),
        repo_root=ROOT,
    )
