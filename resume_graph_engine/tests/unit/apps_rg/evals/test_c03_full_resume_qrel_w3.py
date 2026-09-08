"""W3 packet tests: full finite universe, opaque references, and no human grades."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.evals.owner_solo import c03_full_resume_qrel_derived_clusters as derived_subject
from apps_rg.evals.owner_solo import c03_full_resume_qrel_w1c as w1c_subject
from apps_rg.evals.owner_solo import c03_full_resume_qrel_w2 as w2_subject
from apps_rg.evals.owner_solo import c03_full_resume_qrel_w3 as subject
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w1c import (
    build_combined_registry,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w2 import (
    build_frozen_ranking_artifact,
    build_w2_query_manifest,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w3 import (
    FullResumeQrelW3Error,
    build_w3_packet_content,
    load_w3_review_contract,
    validate_w3_packet_content,
    validate_w3_review_contract,
)


ROOT = Path(__file__).resolve().parents[4]
W6_RECEIPT = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave6_cluster_vector_generation_receipt.json"
)


@pytest.fixture(autouse=True)
def _algorithm_test_uses_explicit_non_authorizing_scope_override(monkeypatch) -> None:
    for module in (derived_subject, w1c_subject, w2_subject):
        monkeypatch.setattr(module, "validate_full_resume_scope", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        subject,
        "_target_context",
        lambda root, query: (
            "Target job description:\n"
            + (root / str(query["jd_path"])).read_text(encoding="utf-8").strip()
            + "\n\nApplication brief:\n"
            + (root / str(query["brief_path"])).read_text(encoding="utf-8").strip()
        ),
    )


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


def _artifact() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    query_manifest = build_w2_query_manifest(ROOT)
    combined = build_combined_registry(ROOT)
    rankings: dict[str, list[tuple[str, float]]] = {}
    for query in query_manifest["queries"]:
        for section_id in query_manifest["section_ids"]:
            rankings[f"{query['query_id']}|{section_id}"] = [
                (cluster_id, float(-position))
                for position, cluster_id in enumerate(
                    combined["section_candidate_cluster_ids"][section_id], 1
                )
            ]
    digests = {
        str(query["query_id"]): hashlib.sha256(
            str(query["query_id"]).encode("utf-8")
        ).hexdigest()
        for query in query_manifest["queries"]
    }
    artifact = build_frozen_ranking_artifact(
        repo_root=ROOT,
        query_manifest=query_manifest,
        w1c_context=_w1c_context(combined),
        model_manifest=_model_manifest(),
        rankings_by_pair=rankings,
        query_vector_sha256=digests,
        runtime_proof={"fallback_used": False, "vector_count": 6, "dimension": 1024},
    )
    return query_manifest, combined, artifact


def _packet() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    query_manifest, combined, artifact = _artifact()
    packet = build_w3_packet_content(
        repo_root=ROOT,
        query_manifest=query_manifest,
        combined_registry=combined,
        ranking_artifact=artifact,
        blinding_nonce="1" * 64,
    )
    return query_manifest, combined, artifact, packet


def test_w3_frozen_contract_has_the_full_owner_packet_boundary() -> None:
    contract = load_w3_review_contract(ROOT)

    assert contract["review_packet"]["query_section_item_count"] == 66
    assert contract["review_packet"]["candidate_judgment_count"] == 600
    assert contract["blinding"]["sealed_mapping_runtime_only"] is True
    assert contract["authority_boundary"]["human_labels_created_by_w3"] is False


def test_w3_rejects_a_weakened_contract() -> None:
    contract = load_w3_review_contract(ROOT)
    malformed = copy.deepcopy(contract)
    malformed["review_packet"]["partial_top_k_judging_forbidden"] = False

    with pytest.raises(FullResumeQrelW3Error, match="partial_top_k_judging_forbidden"):
        validate_w3_review_contract(malformed)


def test_w3_builds_a_blinded_full_universe_owner_packet() -> None:
    _manifest, _combined, _artifact_value, packet = _packet()

    assert packet["reviewer"]["item_count"] == 66
    assert packet["reviewer"]["candidate_judgment_count"] == 600
    assert sum(row["candidate_count"] for row in packet["reviewer_items"]) == 600
    assert packet["sealed_mapping"]["distribution_forbidden"] is True
    assert packet["scope_guards"]["human_qrels_created"] is False
    visible = json.dumps(packet["reviewer_items"], ensure_ascii=False)
    assert "cluster_id" not in visible
    assert "query_id" not in visible
    assert "frozen_rank" not in visible
    assert "similarity" not in visible
    assert "CALIBRATION" not in visible
    assert "HOLDOUT" not in visible


def test_w3_rejects_a_rank_leak_in_reviewer_payload() -> None:
    query_manifest, combined, artifact, packet = _packet()
    tampered = copy.deepcopy(packet)
    tampered["reviewer_items"][0]["candidates"][0]["frozen_rank"] = 1

    with pytest.raises(FullResumeQrelW3Error, match="VISIBLE_CANDIDATE_KEYS"):
        validate_w3_packet_content(
            tampered,
            repo_root=ROOT,
            query_manifest=query_manifest,
            combined_registry=combined,
            ranking_artifact=artifact,
        )


def test_w3_rejects_mismatched_visible_evidence_text() -> None:
    query_manifest, combined, artifact, packet = _packet()
    tampered = copy.deepcopy(packet)
    tampered["reviewer_items"][0]["candidates"][0]["evidence_cluster_text"] = (
        "Unbound replacement text"
    )

    with pytest.raises(FullResumeQrelW3Error, match="EVIDENCE_TEXT_BINDING"):
        validate_w3_packet_content(
            tampered,
            repo_root=ROOT,
            query_manifest=query_manifest,
            combined_registry=combined,
            ranking_artifact=artifact,
        )
