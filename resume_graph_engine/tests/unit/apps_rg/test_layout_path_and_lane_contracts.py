"""Wave 2 contract tests: worktree path safety, unified section roots, forensics baseline, single-path competencies, and headline pre-judge gating."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.reasoning.bullet_lane_generation import generate_bullet_lane_with_sc_and_claude
from apps_rg.runtime.reasoning.competencies_graph_pool import (
    COMPETENCIES_FINAL_CATEGORY_COUNT,
    is_competencies_pool_generation,
)
from apps_rg.runtime.run_bundle_index import repo_relative_posix
from apps_rg.runtime.runtime_proof_layout import (
    MODULAR_R4_SECTIONS_ROOT_ENV,
    allocate_product_full_resume_artifact_dir,
    modular_sections_root_from_env,
    rel_posix,
    resolve_modular_latest_l2,
)
from apps_rg.runtime.section_failure_forensics import (
    _find_pinned_successful_same_scenario,
    emit_section_failure_forensics,
)
from apps_rg.runtime.sections.headline_lane import (
    HEADLINE_WORD_MAX,
    HEADLINE_WORD_MIN,
    _coerce_segment_claim_ledger_rows,
    build_headline_canonical_claim_ledger_v2,
    evaluate_headline_literal_grounding,
    has_valid_headline_prefix,
    headline_resume_native_clarity_report,
    headline_word_count,
    normalize_headline_claim_ledger,
    recite_canonical_segments_to_bundle_facts,
    repair_headline_segment_citations_for_grounding,
)
from apps_rg.runtime.claim_ledger.headline_claim_ledger import build_headline_text_claim_coverage
from apps_rg.runtime.sections.lane_perf_sync_helpers import (
    execute_headline_judges_with_final_display_gate,
    remap_trimmed_headline_claim_ledger,
)
from apps_rg.runtime.sections_root_manifest import SECTIONS_ROOT_MANIFEST_FILENAME
from apps_rg.runtime.worktree_path_resolution import (
    _git_common_checkout_root_str,
    resolve_unified_section_lane_dir,
)


def _create_mock_git_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main_repo = tmp_path / "main_repo"
    wt_git_dir = main_repo / ".git" / "worktrees" / "feature_wt"
    wt_git_dir.mkdir(parents=True)
    (wt_git_dir / "commondir").write_text("../..\n", encoding="utf-8")

    worktree = tmp_path / "worktrees" / "feature_wt"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {wt_git_dir}\n", encoding="utf-8")
    _git_common_checkout_root_str.cache_clear()
    return main_repo, worktree


def test_isolated_worktree_accepts_shared_checkout_proof_paths_and_blocks_outside(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    main_repo, worktree = _create_mock_git_worktree(tmp_path)
    shared_run = main_repo / "artifacts" / "apps_rg" / "runtime_proofs" / "full_resume_abc123"
    shared_lanes = shared_run / "lanes"
    shared_lanes.mkdir(parents=True)
    (shared_lanes / SECTIONS_ROOT_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")

    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(shared_lanes))
    assert modular_sections_root_from_env(worktree) == shared_lanes.resolve()
    assert allocate_product_full_resume_artifact_dir(worktree, str(shared_run)) == shared_run.resolve()
    assert rel_posix(shared_lanes, worktree) == "artifacts/apps_rg/runtime_proofs/full_resume_abc123/lanes"
    assert repo_relative_posix(worktree, shared_run) == "artifacts/apps_rg/runtime_proofs/full_resume_abc123"

    outside = tmp_path / "outside_untrusted" / "lanes"
    outside.mkdir(parents=True)
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(outside))
    with pytest.raises(ValueError, match="outside-repo modular roots are not supported"):
        modular_sections_root_from_env(worktree)

    symlink_target = tmp_path / "outside_untrusted"
    symlink_escape = worktree / "artifacts" / "apps_rg" / "runtime_proofs" / "escape_link"
    symlink_escape.parent.mkdir(parents=True, exist_ok=True)
    symlink_escape.symlink_to(symlink_target)
    with pytest.raises(ValueError):
        allocate_product_full_resume_artifact_dir(worktree, str(symlink_escape / "bundle"))


def test_unified_split_section_roots_resolve_across_lanes_and_modular_sections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    run_root = repo / "artifacts" / "apps_rg" / "runtime_proofs" / "full_resume_split01"
    lanes_root = run_root / "lanes"
    mod_sections = run_root / "modular_r4" / "sections"
    lanes_root.mkdir(parents=True)
    mod_sections.mkdir(parents=True)
    (lanes_root / SECTIONS_ROOT_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    (mod_sections / SECTIONS_ROOT_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")

    actual_run_dir = mod_sections / "headline" / "mock" / "r1"
    actual_run_dir.mkdir(parents=True)
    l2_file = actual_run_dir / "l2_output.json"
    l2_file.write_text(
        json.dumps({"runtime_generation_status": "MOCKED", "headline_line": "SVP Engineering | A | B | C"}),
        encoding="utf-8",
    )
    ptr_file = mod_sections / "headline" / "latest_mock_run.json"
    ptr_file.write_text(
        json.dumps({"run_dir": actual_run_dir.relative_to(repo).as_posix()}),
        encoding="utf-8",
    )

    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(lanes_root))
    monkeypatch.setenv("APPS_RG_ALLOW_DEV_MOCK", "1")
    resolved_l2 = resolve_modular_latest_l2(repo, "headline")
    assert resolved_l2 == l2_file.resolve()

    flat_mod_hl = mod_sections / "competencies"
    flat_mod_hl.mkdir(parents=True)
    (flat_mod_hl / "l2_output.json").write_text('{"competencies": []}', encoding="utf-8")
    (lanes_root / "competencies").mkdir(parents=True)
    unified = resolve_unified_section_lane_dir({"section": "competencies"}, repo, run_root)
    assert unified == flat_mod_hl


def test_forensics_baseline_resolves_in_worktree_and_reads_split_section_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APPS_RG_E2E_BASELINE_REF", raising=False)
    worktree_root = Path(__file__).resolve().parents[4]
    run_root = tmp_path / "failed_anthropic_run"
    (run_root / "modular_r4" / "sections" / "headline").mkdir(parents=True)
    (run_root / "lanes" / "headline").mkdir(parents=True)
    (run_root / "ingress_raw.json").write_text(
        json.dumps(
            {
                "target_company": "Anthropic",
                "target_role": "Manager of Applied AI Architecture, Partnerships",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "apps_rg_spine_proof.json").write_text(
        json.dumps({"git_commit": "abcdef1234567"}),
        encoding="utf-8",
    )
    (run_root / "modular_r4" / "sections" / "headline" / "headline_output.txt").write_text(
        "SVP Engineering | Partner AI Platforms | Runtime Governance | Enterprise Delivery\n",
        encoding="utf-8",
    )

    baseline = _find_pinned_successful_same_scenario(run_root, worktree_root)
    assert baseline["found"] is True
    assert baseline["baseline_digest_match"] is True

    gate = emit_section_failure_forensics(
        run_root,
        repo_root=worktree_root,
        sections=[
            {
                "section": "headline",
                "status_bucket": "failed",
                "x3_code": "X3_BLOCK",
                "failed_gates": ["x2_headline_segments_quality"],
            }
        ],
        result={"exit_status": "blocked"},
    )
    rca_doc = json.loads((run_root / "section_failure_forensics" / "headline.json").read_text(encoding="utf-8"))
    assert rca_doc["current_output"]["present"] is True
    assert rca_doc["current_output"]["source"] != "missing_lane_dir"
    assert rca_doc["last_successful_output"]["baseline_found"] is True
    assert gate["baseline_run_dir"] != ""


def test_single_path_competencies_succeeds_without_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps_rg.runtime.reasoning import bullet_lane_self_consistency

    bundles = [
        "ccb_agentic_platforms",
        "ccb_runtime_governance",
        "ccb_retrieval_context_engineering",
        "ccb_llmops_reliability",
        "ccb_distributed_systems_engineering",
        "ccb_platform_productization",
        "ccb_partner_applied_ai_architecture",
        "ccb_engineering_leadership",
    ]
    payload_obj = {
        "categories": [
            {
                "category_label": f"Capability_{idx}",
                "competency_bundle_id": bundles[idx],
                "taxonomy_category_id": f"tax_{idx}",
                "terms": [
                    {"text": f"governed platform term {idx}", "source_fact_ids": ["bul_001"]},
                    {"text": f"runtime architecture term {idx}", "source_fact_ids": ["bul_001"]},
                ],
                "source_fact_ids": ["bul_001"],
            }
            for idx in range(COMPETENCIES_FINAL_CATEGORY_COUNT)
        ]
    }
    monkeypatch.setattr(
        bullet_lane_self_consistency,
        "call_section_model_provider",
        lambda *_a, **_kw: ProviderResult(
            provider_requested="external_claude",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="stub",
            raw_model_output=json.dumps(payload_obj),
            provider_response={"status": "ok"},
        ),
    )
    monkeypatch.setenv("APPS_RG_BULLET_SC_DISABLE", "1")
    _res, _raw, parsed, err, meta = generate_bullet_lane_with_sc_and_claude(
        section_lane="competencies",
        slot_kind="competencies",
        provider_payload={"model": "stub", "messages": []},
        parse_model_json=lambda r: (json.loads(r), ""),
        normalize_parsed=lambda p: p,
        targeting_context={"allowed_fact_ids": ["bul_001"], "resume_support_blob_lower": ""},
        judge_mode="mocked",
        use_sc_path=None,
    )
    assert err == ""
    assert parsed is not None
    assert is_competencies_pool_generation(meta)
    assert meta["total_paths_executed"] == 1
    assert meta["regen_rounds_executed"] == 0
    assert meta["single_path_mode"] is True


def test_headline_gates_final_display_text_blocks_overlap_and_rejects_bad_voice_repair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    parsed_trim = {
        "claim_ledger": [
            {"claim_text": "Governed Agentic Platform Controls", "source_fact_ids": ["bul_unify_001"]},
            {"claim_text": "Runtime Infrastructure", "source_fact_ids": ["bul_unify_001"]},
            {"claim_text": "Regulated Delivery", "source_fact_ids": ["bul_unify_001"]},
        ]
    }
    remap_trimmed_headline_claim_ledger(
        parsed_trim,
        ("Governed Agentic Platform Controls", "Runtime Infrastructure", "Regulated Delivery"),
        ["Governed Agentic Platforms", "Runtime Infrastructure", "Regulated Delivery"],
    )
    assert parsed_trim["claim_ledger"][0]["claim_text"] == "Governed Agentic Platforms"

    allowed = {"bul_unify_001"}
    runtime_payload = {
        "selected_fact_plan": {
            "section_id": "headline",
            "facts": [
                {
                    "fact_id": "bul_unify_001",
                    "claim_text": "Built governed agentic platforms, distributed cloud infrastructure, and regulated delivery systems.",
                }
            ],
            "required_fact_ids": ["bul_unify_001"],
        }
    }

    # Case 1: Overlapping headline fails pre-judge without invoking LLM judges
    overlap_hl = "SVP Engineering | Governed Agentic Platforms | Agentic Platform Systems | Regulated Delivery"
    overlap_ledger = _coerce_segment_claim_ledger_rows(overlap_hl, ["bul_unify_001"])
    judge_calls: list[dict[str, Any]] = []

    def _spy_judges(**kwargs: Any) -> list[JudgeOutput]:
        judge_calls.append(kwargs)
        return [
            JudgeOutput(
                judge_id="x1d_gemini_pro_headline",
                provider_name="gemini_pro",
                provider_key="gemini_pro",
                evaluator_mode="MOCKED",
                provider_status="MODEL_BACKED_FAIL",
                model_name="stub",
                provider_available=True,
                provider_blocked=False,
                exact_provider_error=None,
                score_scale="0_to_5",
                score=3.2,
                threshold=4.0,
                pass_=False,
                decisive_failure=False,
                findings=["tighten executive cadence"],
            )
        ]

    overlap_dir = tmp_path / "overlap_case"
    overlap_dir.mkdir()
    _hl_out, _, _, _, blocked_x1d = execute_headline_judges_with_final_display_gate(
        headline_line=overlap_hl,
        parsed={"headline_line": overlap_hl, "claim_ledger": overlap_ledger},
        parsed_for_x2={"headline_line": overlap_hl},
        claim_ledger=overlap_ledger,
        canon_doc={},
        coverage={},
        allowed_fact_ids=allowed,
        proof_pool_metadata=None,
        runtime_payload=runtime_payload,
        judge_keys=["gemini_pro"],
        companion_context="",
        judge_mode="mocked",
        judge_allowed_mock=True,
        artifact_dir=overlap_dir,
        allowed_fact_packet=[],
        target_title="SVP",
        target_company="Anthropic",
        word_min=HEADLINE_WORD_MIN,
        word_max=HEADLINE_WORD_MAX,
        word_count_fn=headline_word_count,
        has_valid_prefix_fn=has_valid_headline_prefix,
        clarity_report_fn=headline_resume_native_clarity_report,
        evaluate_grounding_fn=evaluate_headline_literal_grounding,
        coerce_segment_ledger_fn=_coerce_segment_claim_ledger_rows,
        recite_bundle_fn=recite_canonical_segments_to_bundle_facts,
        repair_grounding_fn=repair_headline_segment_citations_for_grounding,
        normalize_ledger_fn=normalize_headline_claim_ledger,
        build_canon_fn=build_headline_canonical_claim_ledger_v2,
        build_coverage_fn=build_headline_text_claim_coverage,
        run_judges_fn=_spy_judges,
        write_json_fn=lambda p, d: p.write_text(json.dumps(d), encoding="utf-8"),
    )
    assert judge_calls == []
    assert blocked_x1d[0]["pass"] is False
    gate_receipt = json.loads((overlap_dir / "headline_final_display_pre_judge_gate.json").read_text(encoding="utf-8"))
    assert gate_receipt["pass"] is False
    assert any("segment_overlap" in issue for issue in gate_receipt["issues"])

    # Case 2: Valid grounded headline passes pre-judge, and overlapping voice-repair candidate is rejected
    clean_hl = "SVP Engineering | Governed Agentic Platforms | Distributed Cloud Infrastructure | Regulated Delivery"
    clean_ledger = _coerce_segment_claim_ledger_rows(clean_hl, ["bul_unify_001"])
    from apps_rg.runtime.sections import ExecutiveVoiceRepairAgent

    monkeypatch.setattr(
        ExecutiveVoiceRepairAgent,
        "repair_section_with_executive_voice_agent",
        lambda **_kw: (
            {"headline_line": overlap_hl, "claim_ledger": clean_ledger},
            SimpleNamespace(repair_succeeded=True),
        ),
    )
    clean_dir = tmp_path / "clean_case"
    clean_dir.mkdir()
    final_hl, final_ledger, _, _, clean_x1d = execute_headline_judges_with_final_display_gate(
        headline_line=clean_hl,
        parsed={"headline_line": clean_hl, "claim_ledger": clean_ledger},
        parsed_for_x2={"headline_line": clean_hl},
        claim_ledger=clean_ledger,
        canon_doc={},
        coverage={},
        allowed_fact_ids=allowed,
        proof_pool_metadata=None,
        runtime_payload=runtime_payload,
        judge_keys=["gemini_pro"],
        companion_context="",
        judge_mode="mocked",
        judge_allowed_mock=True,
        artifact_dir=clean_dir,
        allowed_fact_packet=[],
        target_title="SVP",
        target_company="Anthropic",
        word_min=HEADLINE_WORD_MIN,
        word_max=HEADLINE_WORD_MAX,
        word_count_fn=headline_word_count,
        has_valid_prefix_fn=has_valid_headline_prefix,
        clarity_report_fn=headline_resume_native_clarity_report,
        evaluate_grounding_fn=evaluate_headline_literal_grounding,
        coerce_segment_ledger_fn=_coerce_segment_claim_ledger_rows,
        recite_bundle_fn=recite_canonical_segments_to_bundle_facts,
        repair_grounding_fn=repair_headline_segment_citations_for_grounding,
        normalize_ledger_fn=normalize_headline_claim_ledger,
        build_canon_fn=build_headline_canonical_claim_ledger_v2,
        build_coverage_fn=build_headline_text_claim_coverage,
        run_judges_fn=_spy_judges,
        write_json_fn=lambda p, d: p.write_text(json.dumps(d), encoding="utf-8"),
    )
    assert len(judge_calls) == 1
    assert judge_calls[0]["deterministic_gate_summary"]["pass"] is True
    assert final_hl == clean_hl
    assert final_ledger == clean_ledger
    clean_receipt = json.loads((clean_dir / "headline_final_display_pre_judge_gate.json").read_text(encoding="utf-8"))
    assert "voice_repair_rejected" in clean_receipt
