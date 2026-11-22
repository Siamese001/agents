"""Product-release assembly must execute aggregate full-resume judge, not x2_no_judge_calls pass."""
# apps-test-model: APP CONTRACT

from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.assembly.final_resume_x2 import GENERATED_LANE_IDS, run_final_resume_x2_gates
from apps_rg.runtime.spine.section_x3_finalize import FINAL_MATERIALIZED_ACCEPTANCE_CONTRACT


def _minimal_final_resume(*, judge_calls_made: bool) -> dict:
    return {
        "final_resume_hash": "abc",
        "calls": {
            "provider_calls_made": False,
            "retired_provider_calls_made": False,
            "judge_calls_made": judge_calls_made,
            "docx_rendered": False,
        },
        "sections": [],
    }


def _gate(results, gate_id: str):
    for g in results:
        if g.gate_id == gate_id:
            return g
    raise AssertionError(gate_id)


def _paths(tmp_path: Path):
    from apps_rg.runtime.assembly.final_resume_manifest import FinalResumePaths

    out = tmp_path / "assembly"
    out.mkdir()
    repo = tmp_path
    for name in ("rollup.json", "locked.json", "locked_x2.json", "base.json"):
        (repo / name).write_text("{}", encoding="utf-8")
    return repo, FinalResumePaths(
        repo_root=repo,
        rollup_json=repo / "rollup.json",
        locked_manifest=repo / "locked.json",
        locked_x2=repo / "locked_x2.json",
        base_resume=repo / "base.json",
        output_dir=out,
    )


def _generated_rollup_row(lane: str, **overrides) -> dict:
    row = {
        "accepted_real_evidence_resolution": "modular_r4_explicit_run_dir",
        "rollup_source_run_dir": f"artifacts/apps_rg/runtime_proofs/{lane}",
        "runtime_generation_status": "REAL_LLM",
        "x2_failed": 0,
        "x2_failed_gate_ids": [],
        "x3_code": "X3_ALLOW",
    }
    row.update(overrides)
    return row


def _write_final_materialized_contract(
    repo: Path,
    lane: str,
    *,
    pass_: bool = True,
    binding_pass: bool | None = True,
) -> str:
    rel = f"artifacts/apps_rg/runtime_proofs/{lane}"
    run_dir = repo / rel
    run_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": "apps_rg.final_materialized_acceptance_contract.v1",
        "section_id": lane,
        "gate_id": "x3_final_materialized_acceptance_contract",
        "pass": pass_,
    }
    if binding_pass is not None:
        doc["x2_final_materialized_binding_pass"] = binding_pass
    (run_dir / FINAL_MATERIALIZED_ACCEPTANCE_CONTRACT).write_text(
        json.dumps(doc),
        encoding="utf-8",
    )
    return rel


def test_final_resume_x2_accepts_patch_run_explicit_real_x3_allow_dirs(tmp_path: Path):
    repo, paths = _paths(tmp_path)
    rollup = {
        "lanes": {
            lane: _generated_rollup_row(
                lane,
                rollup_source_run_dir=_write_final_materialized_contract(repo, lane),
            )
            for lane in GENERATED_LANE_IDS
        }
    }

    results = run_final_resume_x2_gates(
        repo=repo,
        paths=paths,
        final_resume_blob=_minimal_final_resume(judge_calls_made=False),
        rollup_blob=rollup,
        locked_manifest_blob={},
        coherence_review=None,
        product_release_mode=False,
    )

    assert _gate(results, "x2_generated_sections_from_latest_successful_real").pass_ is True
    assert _gate(results, "x2_generated_sections_final_materialized_contracts_pass").pass_ is True


def test_final_resume_x2_rejects_missing_final_materialized_contract(tmp_path: Path):
    repo, paths = _paths(tmp_path)
    rollup = {
        "lanes": {
            lane: _generated_rollup_row(
                lane,
                rollup_source_run_dir=f"artifacts/apps_rg/runtime_proofs/{lane}",
            )
            for lane in GENERATED_LANE_IDS
        }
    }

    results = run_final_resume_x2_gates(
        repo=repo,
        paths=paths,
        final_resume_blob=_minimal_final_resume(judge_calls_made=False),
        rollup_blob=rollup,
        locked_manifest_blob={},
        coherence_review=None,
        product_release_mode=False,
    )

    gate = _gate(results, "x2_generated_sections_final_materialized_contracts_pass")
    assert gate.pass_ is False
    assert "headline:missing_final_materialized_acceptance_contract" in str(gate.observed_value)


def test_final_resume_x2_rejects_failed_final_materialized_contract(tmp_path: Path):
    repo, paths = _paths(tmp_path)
    rollup = {
        "lanes": {
            lane: _generated_rollup_row(
                lane,
                rollup_source_run_dir=_write_final_materialized_contract(
                    repo,
                    lane,
                    pass_=lane != "insurtech_bullets",
                ),
            )
            for lane in GENERATED_LANE_IDS
        }
    }

    results = run_final_resume_x2_gates(
        repo=repo,
        paths=paths,
        final_resume_blob=_minimal_final_resume(judge_calls_made=False),
        rollup_blob=rollup,
        locked_manifest_blob={},
        coherence_review=None,
        product_release_mode=False,
    )

    gate = _gate(results, "x2_generated_sections_final_materialized_contracts_pass")
    assert gate.pass_ is False
    assert "insurtech_bullets:final_materialized_acceptance_contract_failed" in str(gate.observed_value)


def test_final_resume_x2_rejects_pass_true_contract_without_x2_binding_proof(tmp_path: Path):
    repo, paths = _paths(tmp_path)
    rollup = {
        "lanes": {
            lane: _generated_rollup_row(
                lane,
                rollup_source_run_dir=_write_final_materialized_contract(
                    repo,
                    lane,
                    binding_pass=None if lane == "headline" else True,
                ),
            )
            for lane in GENERATED_LANE_IDS
        }
    }

    results = run_final_resume_x2_gates(
        repo=repo,
        paths=paths,
        final_resume_blob=_minimal_final_resume(judge_calls_made=False),
        rollup_blob=rollup,
        locked_manifest_blob={},
        coherence_review=None,
        product_release_mode=False,
    )

    gate = _gate(results, "x2_generated_sections_final_materialized_contracts_pass")
    assert gate.pass_ is False
    assert "headline:final_materialized_x2_binding_not_proven" in str(gate.observed_value)


def test_final_resume_x2_rejects_patch_run_explicit_dir_without_x3_allow(tmp_path: Path):
    repo, paths = _paths(tmp_path)
    rollup = {
        "lanes": {
            lane: _generated_rollup_row(lane)
            for lane in GENERATED_LANE_IDS
        }
    }
    rollup["lanes"]["headline"]["x3_code"] = "X3_BLOCK"

    results = run_final_resume_x2_gates(
        repo=repo,
        paths=paths,
        final_resume_blob=_minimal_final_resume(judge_calls_made=False),
        rollup_blob=rollup,
        locked_manifest_blob={},
        coherence_review=None,
        product_release_mode=False,
    )

    gate = _gate(results, "x2_generated_sections_from_latest_successful_real")
    assert gate.pass_ is False
    assert "headline resolution not accepted" in str(gate.observed_value)


def test_product_mode_fails_without_aggregate_judge_artifacts(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("APPS_RG_ASSEMBLY_STRUCTURAL_ONLY", raising=False)
    repo, paths = _paths(tmp_path)

    results = run_final_resume_x2_gates(
        repo=repo,
        paths=paths,
        final_resume_blob=_minimal_final_resume(judge_calls_made=False),
        rollup_blob={},
        locked_manifest_blob={},
        coherence_review=None,
        product_release_mode=True,
    )
    assert _gate(results, "x2_final_resume_aggregate_judge_executed").pass_ is False
    assert _gate(results, "x2_final_resume_aggregate_judge_artifact_present").pass_ is False
    assert _gate(results, "x2_full_resume_llm_coherence_aggregation").pass_ is False
    ids = {g.gate_id for g in results}
    assert "x2_no_judge_calls" not in ids


def test_product_mode_passes_when_coherence_artifacts_and_review_present(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("APPS_RG_ASSEMBLY_STRUCTURAL_ONLY", raising=False)
    repo, paths = _paths(tmp_path)
    out = paths.output_dir
    review = {
        "full_resume_coherence_pass": True,
        "decisive_reason": "quorum_pass_no_blockers",
        "blockers": [],
    }
    (out / "full_resume_llm_coherence_review.json").write_text(json.dumps(review), encoding="utf-8")
    (out / "x1d_full_resume_judge_outputs.json").write_text('{"judges":[]}', encoding="utf-8")

    results = run_final_resume_x2_gates(
        repo=repo,
        paths=paths,
        final_resume_blob=_minimal_final_resume(judge_calls_made=True),
        rollup_blob={},
        locked_manifest_blob={},
        coherence_review=review,
        product_release_mode=True,
    )
    assert _gate(results, "x2_final_resume_aggregate_judge_executed").pass_ is True
    assert _gate(results, "x2_final_resume_aggregate_judge_artifact_present").pass_ is True
    assert _gate(results, "x2_full_resume_llm_coherence_aggregation").pass_ is True


def test_assemble_final_resume_skips_12th_coherence_panel_when_non_allow_lane_present(
    tmp_path: Path, monkeypatch
) -> None:
    from unittest.mock import patch
    from apps_rg.runtime.assembly.final_resume_manifest import FinalResumePaths
    from apps_rg.runtime.internal.final_resume_assembler import assemble_final_resume

    monkeypatch.setenv("APPS_RG_ASSEMBLY_STRUCTURAL_ONLY", "0")
    monkeypatch.setenv("APPS_RG_FULL_RESUME_LLM_COHERENCE_REVIEW", "1")

    repo = tmp_path / "repo"
    out = repo / "modular_r4" / "final_resume_assembly"
    out.mkdir(parents=True, exist_ok=True)
    # Seed stale Pass-1 coherence artifacts that must be overwritten when skipped in Pass 2
    (out / "x1d_full_resume_judge_outputs.json").write_text(
        json.dumps({"stale": True, "judges": [{"pass": True}], "aggregation": {"full_resume_coherence_pass": True}}),
        encoding="utf-8",
    )

    lanes_blob = {}
    for lane in GENERATED_LANE_IDS:
        rel_dir = f"artifacts/apps_rg/runtime_proofs/{lane}"
        ldir = repo / rel_dir
        ldir.mkdir(parents=True, exist_ok=True)
        x3_code = "X3_REVIEW_JUDGE_SOFT_FAIL" if lane == "headline" else "X3_ALLOW"
        (ldir / "l2_output.json").write_text(
            json.dumps({"section_id": lane, "runtime_generation_status": "REAL_LLM", "product_quality_status": "PASS", "headline_line": "SVP AI"}),
            encoding="utf-8",
        )
        (ldir / "x3_disposition.json").write_text(
            json.dumps({"x3_code": x3_code, "runtime_generation_status": "REAL_LLM"}),
            encoding="utf-8",
        )
        lanes_blob[lane] = _generated_rollup_row(lane, rollup_source_run_dir=rel_dir, x3_code=x3_code)

    from apps_rg.runtime.assembly.final_resume_x2 import (
        LOCKED_EMBEDDED_ORDER_IDS,
        LOCKED_INVARIANT_IDS,
    )

    rollup_p = repo / "rollup.json"
    rollup_p.write_text(json.dumps({"rollup_id": "r1", "lanes": lanes_blob}), encoding="utf-8")
    locked_sections = [
        {"section_id": sid, "copied_text": f"locked:{sid}"}
        for sid in (*LOCKED_EMBEDDED_ORDER_IDS, *LOCKED_INVARIANT_IDS)
    ]
    locked_p = repo / "locked.json"
    locked_p.write_text(json.dumps({"manifest_id": "m1", "sections": locked_sections}), encoding="utf-8")
    locked_x2_p = repo / "locked_x2.json"
    locked_x2_p.write_text("{}", encoding="utf-8")
    base_p = repo / "base.json"
    base_p.write_text("{}", encoding="utf-8")
    prof_p = repo / "static_profile.json"
    prof_p.write_text(
        json.dumps({"candidate_name": "Test Candidate", "header_contact": {"email": "a@example.com"}}),
        encoding="utf-8",
    )
    paths = FinalResumePaths(
        repo_root=repo,
        rollup_json=rollup_p,
        locked_manifest=locked_p,
        locked_x2=locked_x2_p,
        base_resume=base_p,
        output_dir=out,
        candidate_static_profile=prof_p,
    )

    with patch(
        "apps_rg.runtime.assembly.full_resume_llm_coherence.emit_full_resume_llm_coherence_review",
        side_effect=AssertionError("12th coherence judge must not run when headline is X3_REVIEW_JUDGE_SOFT_FAIL"),
    ):
        result = assemble_final_resume(paths, skip_preflight=True)

    assert result["gates_all_pass"] is False
    receipt_doc = json.loads((out / "final_resume_receipt.json").read_text(encoding="utf-8"))
    assert receipt_doc["product_allow_claimed"] is False
    final_doc = json.loads((out / "final_resume.json").read_text(encoding="utf-8"))
    assert final_doc["calls"]["judge_calls_made"] is False
    assert final_doc["calls"]["provider_calls_made"] is False
    sem = final_doc["assembly_proof_semantics"]
    assert sem["aggregate_judge_executed"] is False
    assert sem["aggregate_judge_skipped"] is True
    assert "headline" in sem["aggregate_judge_skipped_lanes"]

    coh_review = json.loads((out / "full_resume_llm_coherence_review.json").read_text(encoding="utf-8"))
    assert coh_review["skipped"] is True
    assert coh_review["skip_reason"] == "upstream_lanes_not_x3_allow"
    assert coh_review["non_allow_lanes"] == ["headline"]
    assert coh_review["full_resume_coherence_pass"] is False
    assert coh_review["judge_verdicts"] == []

    x1d_doc = json.loads((out / "x1d_full_resume_judge_outputs.json").read_text(encoding="utf-8"))
    assert "stale" not in x1d_doc
    assert x1d_doc["skipped"] is True
    assert x1d_doc["policy_valid"] is True
    assert x1d_doc["judges"] == []
    assert x1d_doc["aggregation"]["full_resume_coherence_pass"] is False

    x2_doc = json.loads((out / "final_resume_x2_gate_outputs.json").read_text(encoding="utf-8"))
    exec_gate = next(g for g in x2_doc["gates"] if g["gate_id"] == "x2_final_resume_aggregate_judge_executed")
    assert exec_gate["pass"] is False
    assert "aggregate_judge_skipped:upstream_lanes_not_x3_allow" in str(exec_gate["failure_reason"])
