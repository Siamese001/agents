from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.c0.graph_skill_embedding_allocation import (
    ALL_EMBEDDING_LANES,
    GraphSkillEmbeddingAllocationError,
    build_lane_embedding_allowlists,
    build_whole_resume_graph_embedding_candidates,
    graph_skill_embeddings_required,
    load_graph_skill_embedding_authority,
    load_lane_embedding_allowlists,
    write_graph_skill_embedding_runtime_bundle,
)
from apps_rg.runtime.c0 import graph_skill_embedding_allocation as embedding_allocation


def _candidate(
    assertion_id: str,
    skill_id: str,
    *,
    similarity: float,
    authority_section_id: str,
) -> dict[str, object]:
    return {
        "assertion_id": assertion_id,
        "skill_id": skill_id,
        "fact_links": [f"lineage_{skill_id}"],
        "similarity": similarity,
        "authority_section_id": authority_section_id,
        "assertion_document_sha256": "1" * 64,
        "authority_envelope_sha256": "2" * 64,
        "skill_row_sha256": "3" * 64,
    }


def _allocation(*assignments: dict[str, object]) -> dict[str, object]:
    return {
        "allocation_plan_digest": "a" * 64,
        "assignments": list(assignments),
    }


def _synthetic_authority_allowlists(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], dict[str, object]]:
    graph_row = {
        "skill_id": "skill_1",
        "retrieval_eligible": True,
        "fact_id_links": ["fact_1"],
    }
    graph = {"skill_rows": [graph_row]}
    graph_sha256 = embedding_allocation.canonical_sha256(graph)
    assertion = {
        "assertion_id": "skill_1",
        "skill_id": "skill_1",
        "fact_links": ["fact_1"],
        "allowed_sections": ["competencies"],
        "assertion_document_sha256": "1" * 64,
        "authority_envelope_sha256": "2" * 64,
        "skill_row_sha256": embedding_allocation.canonical_sha256(graph_row),
    }
    corpus = {
        "source_digests": {"graph_sha256": graph_sha256},
        "assertions": [assertion],
    }
    authority: dict[str, object] = {
        "manifest_sha256": "3" * 64,
        "graph_sha256": graph_sha256,
        "candidate_fact_ledger_sha256": "4" * 64,
        "base_resume_sha256": "5" * 64,
        "corpus_sha256": "6" * 64,
        "embedding_generation_sha256": "7" * 64,
        "projection_sha256": "8" * 64,
        "model_id": "BAAI/bge-m3",
        "model_revision": "9" * 40,
        "model_artifact_sha256": "a" * 64,
        "qualification": {"qualification_sha256": "b" * 64},
        "qualification_scope": "REGRESSION_ONLY",
        "release_authorizing": False,
        "runtime_contract": {
            "contract_sha256": "c" * 64,
            "packages": {"torch": "pinned"},
        },
        "_graph_payload": graph,
        "_corpus_payload": corpus,
    }
    allocation: dict[str, object] = {
        "allocation_plan_digest": "d" * 64,
        "graph_digest": graph_sha256,
        "assignments": [
            {
                "section_id": "competencies",
                "skill_id": "skill_1",
                "fact_id": "fact_1",
                "metric_outcome_id": "",
            }
        ],
    }
    candidates = {
        "competencies": [
            {
                **assertion,
                "similarity": 0.75,
                "authority_section_id": "competencies",
            }
        ]
    }
    allowlists = build_lane_embedding_allowlists(
        allocation_plan=allocation,
        candidates_by_section=candidates,
        authority_pins=embedding_allocation._authority_pins(authority),
        section_order=("competencies",),
    )
    monkeypatch.setattr(
        embedding_allocation,
        "load_graph_skill_embedding_authority",
        lambda _repo_root: authority,
    )
    return allowlists, allocation


def _reseal(payload: dict[str, object], field: str) -> None:
    payload.pop(field, None)
    payload[field] = embedding_allocation.canonical_sha256(payload)


def test_requirement_flag_is_explicit_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED", raising=False)
    assert graph_skill_embeddings_required() is False
    monkeypatch.setenv("APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED", "1")
    assert graph_skill_embeddings_required() is True
    monkeypatch.setenv("APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED", "sometimes")
    with pytest.raises(GraphSkillEmbeddingAllocationError, match="boolean"):
        graph_skill_embeddings_required()


def test_mandatory_runtime_rejects_non_promoted_device_before_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()
    model_manifest = {"artifact_sha256": "m" * 64}
    monkeypatch.setattr(
        embedding_allocation,
        "load_graph_skill_embedding_authority",
        lambda _root: {
            "_model_manifest": model_manifest,
            "runtime_contract": {
                "promoted_device": "cuda:0",
                "packages": {
                    "torch": "2.12.0.dev20260228+cu128",
                    "sentence-transformers": "5.2.3",
                },
            },
        },
    )
    monkeypatch.setattr(
        "apps_rg.fact_inventory.c03_skill_embedding_builder.build_local_model_manifest",
        lambda _path: model_manifest,
    )
    provider_called = False

    def fail_if_called(*_args: object, **_kwargs: object) -> tuple[dict, list]:
        nonlocal provider_called
        provider_called = True
        raise AssertionError("provider must not run")

    monkeypatch.setattr(
        "apps_rg.fact_inventory.c03_skill_embedding_builder.encode_bge_m3",
        fail_if_called,
    )

    with pytest.raises(GraphSkillEmbeddingAllocationError, match="device mismatch"):
        build_whole_resume_graph_embedding_candidates(
            repo_root=tmp_path,
            target_company="Example",
            target_role="VP AI",
            jd_text="AI transformation",
            briefing_text="regulated cloud",
            model_path=model_path,
            device="cpu",
        )

    assert provider_called is False


def test_stored_runtime_proof_rejects_non_promoted_device() -> None:
    with pytest.raises(
        GraphSkillEmbeddingAllocationError, match="device proof mismatch"
    ):
        embedding_allocation._validate_runtime_proof(
            {
                "python_major_minor": "3.12",
                "torch_version": "2.12.0.dev20260228+cu128",
                "sentence_transformers_version": "5.2.3",
                "device": "cpu",
                "cuda_available": True,
                "dimension": 1024,
                "fallback_used": False,
            },
            runtime_contract={
                "python_major_minor": "3.12",
                "packages": {
                    "torch": "2.12.0.dev20260228+cu128",
                    "sentence-transformers": "5.2.3",
                },
                "promoted_device": "cuda:0",
                "_model": {"dimension": 1024},
            },
            label="test",
        )


def test_legacy_embedding_authority_fails_closed_after_w5_retirement() -> None:
    repo = Path(__file__).resolve().parents[5]
    with pytest.raises(
        GraphSkillEmbeddingAllocationError,
        match="lane is retired",
    ):
        load_graph_skill_embedding_authority(repo)


def test_allocation_is_narrowed_to_exact_rehydrated_assertions() -> None:
    allocation = _allocation(
        {
            "section_id": "competencies",
            "skill_id": "skill_b",
            "fact_id": "fact_allocated",
            "metric_outcome_id": "metric_1",
        }
    )
    candidates = {
        "competencies": [
            _candidate(
                "assertion_a",
                "skill_a",
                similarity=0.95,
                authority_section_id="competencies",
            ),
            _candidate(
                "assertion_b",
                "skill_b",
                similarity=0.80,
                authority_section_id="competencies",
            ),
        ]
    }

    bundle = build_lane_embedding_allowlists(
        allocation_plan=allocation,
        candidates_by_section=candidates,
        section_order=("competencies",),
        authority_pins={"manifest_sha256": "b" * 64},
    )
    lane = bundle["lanes"]["competencies"]

    assert lane["candidate_assertions"] == [
        {"assertion_id": "assertion_a", "similarity": 0.95},
        {"assertion_id": "assertion_b", "similarity": 0.8},
    ]
    assert lane["allowlists"] == {
        "assertion_ids": ["assertion_b"],
        "skill_ids": ["skill_b"],
        "fact_ids": ["fact_allocated"],
        "metric_ids": ["metric_1"],
    }
    assert lane["accepted_assertion_bindings"][0]["fact_links"] == ["lineage_skill_b"]
    assert "embedding_text" not in json.dumps(lane["candidate_assertions"])
    assert bundle["similarity_is_claim_authority"] is False
    assert bundle["durable_graph_state_mutated"] is False
    assert bundle["pass"] is True


def test_derived_narrative_binds_to_frozen_source_section_authority() -> None:
    allocation = _allocation(
        {
            "section_id": "ibm_narrative",
            "skill_id": "skill_ibm",
            "fact_id": "fact_ibm",
            "metric_outcome_id": "",
            "derived_from_section_id": "ibm_bullets",
        }
    )
    candidates = {
        "ibm_narrative": [
            _candidate(
                "assertion_ibm",
                "skill_ibm",
                similarity=0.72,
                authority_section_id="ibm_bullets",
            )
        ]
    }

    bundle = build_lane_embedding_allowlists(
        allocation_plan=allocation,
        candidates_by_section=candidates,
        section_order=("ibm_narrative",),
        authority_pins={"manifest_sha256": "b" * 64},
    )

    lane = bundle["lanes"]["ibm_narrative"]
    assert lane["derived_from_section_id"] == "ibm_bullets"
    assert lane["assertion_authority_section_id"] == "ibm_bullets"
    assert lane["allowlists"]["assertion_ids"] == ["assertion_ibm"]


def test_missing_allocated_skill_assertion_fails_closed() -> None:
    allocation = _allocation(
        {
            "section_id": "headline",
            "skill_id": "skill_missing",
            "fact_id": "fact_1",
            "metric_outcome_id": "",
        }
    )
    with pytest.raises(
        GraphSkillEmbeddingAllocationError,
        match="allocated skills lack exact assertion candidates",
    ):
        build_lane_embedding_allowlists(
            allocation_plan=allocation,
            candidates_by_section={"headline": []},
            section_order=("headline",),
            authority_pins={"manifest_sha256": "b" * 64},
        )


def test_runtime_bundle_round_trip_is_digest_bound(tmp_path: Path) -> None:
    candidates = {
        lane: [
            _candidate(
                f"assertion_{lane}",
                f"skill_{lane}",
                similarity=0.5,
                authority_section_id=(
                    lane.replace("_narrative", "_bullets")
                    if lane.endswith("_narrative")
                    else lane
                ),
            )
        ]
        for lane in ALL_EMBEDDING_LANES
    }
    assignments = [
        {
            "section_id": lane,
            "skill_id": f"skill_{lane}",
            "fact_id": f"fact_{lane}",
            "metric_outcome_id": "",
            **(
                {"derived_from_section_id": lane.replace("_narrative", "_bullets")}
                if lane.endswith("_narrative")
                else {}
            ),
        }
        for lane in ALL_EMBEDDING_LANES
    ]
    allowlists = build_lane_embedding_allowlists(
        allocation_plan=_allocation(*assignments),
        candidates_by_section=candidates,
        authority_pins={"manifest_sha256": "b" * 64},
    )
    runtime_receipt = {
        "schema_version": "apps_rg.graph_skill_embedding_runtime_receipt.v1",
        "status": "PASS",
        "authority": {"manifest_sha256": "b" * 64},
        "allowlists_digest": allowlists["allowlists_digest"],
        "projection_sha256_before": "c" * 64,
        "projection_sha256_after": "c" * 64,
        "pass": True,
    }

    refs = write_graph_skill_embedding_runtime_bundle(
        {"lane_allowlists": allowlists, "runtime_receipt": runtime_receipt},
        output_dir=tmp_path,
    )
    loaded = load_lane_embedding_allowlists(Path(refs["lane_allowlists"]))

    assert loaded == allowlists
    assert Path(refs["runtime_receipt"]).is_file()


def test_allowlist_loader_rejects_digest_drift(tmp_path: Path) -> None:
    path = tmp_path / "lane_graph_skill_embedding_allowlists.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "apps_rg.lane_graph_skill_embedding_allowlists.v1",
                "lanes": {},
                "allowlists_digest": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GraphSkillEmbeddingAllocationError, match="digest mismatch"):
        load_lane_embedding_allowlists(path)


def test_allowlist_loader_rejects_lane_drift_even_when_top_is_resealed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowlists, _allocation_plan = _synthetic_authority_allowlists(monkeypatch)
    lane = allowlists["lanes"]["competencies"]
    lane["allowlists"]["fact_ids"].append("fact_injected")
    _reseal(allowlists, "allowlists_digest")
    path = tmp_path / "lane_graph_skill_embedding_allowlists.json"
    path.write_text(json.dumps(allowlists), encoding="utf-8")

    with pytest.raises(
        GraphSkillEmbeddingAllocationError, match="lane_allowlist_digest"
    ):
        load_lane_embedding_allowlists(path)


def test_allowlist_authority_rejects_resealed_stale_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowlists, allocation = _synthetic_authority_allowlists(monkeypatch)
    allowlists["authority"]["manifest_sha256"] = "f" * 64
    _reseal(allowlists, "allowlists_digest")

    with pytest.raises(GraphSkillEmbeddingAllocationError, match="authority pins"):
        embedding_allocation.validate_lane_embedding_allowlist_authority(
            allowlists,
            repo_root=Path(__file__).resolve().parents[5],
            allocation_plan=allocation,
            section_id="competencies",
        )


def test_allowlist_authority_rejects_resealed_unauthorized_accepted_assertion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowlists, allocation = _synthetic_authority_allowlists(monkeypatch)
    lane = allowlists["lanes"]["competencies"]
    lane["accepted_assertion_bindings"][0]["assertion_id"] = "skill_injected"
    lane["allowlists"]["assertion_ids"] = ["skill_injected"]
    _reseal(lane, "lane_allowlist_digest")
    _reseal(allowlists, "allowlists_digest")
    path = tmp_path / "lane_graph_skill_embedding_allowlists.json"
    path.write_text(json.dumps(allowlists), encoding="utf-8")
    loaded = load_lane_embedding_allowlists(path)

    with pytest.raises(
        GraphSkillEmbeddingAllocationError,
        match="not an authorized candidate",
    ):
        embedding_allocation.validate_lane_embedding_allowlist_authority(
            loaded,
            repo_root=Path(__file__).resolve().parents[5],
            allocation_plan=allocation,
            section_id="competencies",
        )
