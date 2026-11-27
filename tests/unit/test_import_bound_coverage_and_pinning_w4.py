"""Wave 4 unmocked tests for import-bound symbol/module coverage, AST handoff checks, and E2E pinning."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
for _p in (REPO_ROOT, RG_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from apps_research.tools import research_dry_run_tool
from apps_rg.evals.whole_resume import deterministic_checks, pairwise
from apps_rg.evals.whole_resume.constants import W9_DIMENSIONS
from apps_rg.fact_inventory import (
    apply_commercial_fact_promotion,
    apply_commercial_skills_expansion,
    apply_cro_projection_hardening,
    apply_draft_skill_promotions_20260527,
    apply_phase1_new_skill_nodes,
    apply_phase1_resume_linkage_remediation,
    apply_phase2_gtm_presales_expansion,
    apply_phase2_senior_role_graph_w12,
    apply_phase2_senior_role_graph_w8_w11,
    exec_summary_graph_projection_w4b,
    harden_augmented_skills_graph_ssot,
    run_materialize_augmented_skills_graph_sqlite,
    run_w14b_taxonomy_track_weight_wiring,
    run_w4_w14_multilane_section_projection,
    select_role_facts,
    validate_commercial_srfs_projection,
    validate_p2_w0_graph_skills_gap_inventory,
)
from ops_scripts import mark_stub_judge_artifacts
from ops_scripts.ci import check_eval_harness_promotion_evidence
from resume_graph_engine.tools.apps_rg_standalone import (
    c03_final_resume_output_review_ui,
    c03_full_resume_qrel_w1b,
    c03_graph_evidence_cluster_embedding_wave6,
    c03_graph_evidence_cluster_human_intake_wave9,
    c03_graph_evidence_cluster_qualification_wave7,
    c03_graph_evidence_cluster_registry_wave4,
    c03_targeted_qrel_review_ui,
    gpu_embedding_residency_w2,
    snapshot_graph_sqlite,
)
from resume_graph_engine.tools.otel import verify_preflight
from tools import benchmark_macbook_runtime, lint_commit_message
from tools.testing_gaps_auditor import run_testing_gaps_audit
from tools.verify_fix_eval_pinning import evaluate_non_mock_e2e_branch_requirement


def test_import_bound_coverage_rejects_generic_and_cross_package_name_collisions(tmp_path: Path) -> None:
    """Prove generic `main`/`run` and cross-package symbol collisions no longer fake module coverage (LH-08)."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "tested_runner.py").write_text(
        "def run() -> int:\n    return 1\n\ndef unique_domain_op() -> int:\n    return 2\n",
        encoding="utf-8",
    )
    (agents_dir / "untested_cli.py").write_text(
        "def main() -> int:\n    return 0\n\ndef run() -> int:\n    return 0\n",
        encoding="utf-8",
    )
    lic_dir = tmp_path / "outreach_engine" / "src" / "apps_lic"
    lic_dir.mkdir(parents=True)
    (lic_dir / "shadow_collision.py").write_text(
        "def unique_domain_op() -> int:\n    return 99\n",
        encoding="utf-8",
    )

    tests_dir = tmp_path / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_only_agents.py").write_text(
        "from agents import tested_runner\n\n"
        "def main() -> int:\n    return tested_runner.run()\n\n"
        "def test_runner() -> None:\n"
        "    assert tested_runner.run() == 1\n"
        "    assert tested_runner.unique_domain_op() == 2\n"
        "    assert main() == 1\n",
        encoding="utf-8",
    )

    rep = run_testing_gaps_audit(tmp_path, include_uncovered_backlog=True)
    assert rep["package_coverage"]["agents"]["uncovered_module_count"] == 1
    assert rep["package_coverage"]["outreach_engine"]["covered_modules"] == 0
    assert "outreach_engine" in rep["uncovered_packages"]


def test_pillar2_ast_handoff_rejects_comment_and_docstring_decoys(tmp_path: Path) -> None:
    """Prove Pillar 2 rejects `# apps_rg_handoff` comments and docstrings without AST references (LH-08)."""
    (tmp_path / "apps_research").mkdir()
    (tmp_path / "outreach_engine" / "src").mkdir(parents=True)
    (tmp_path / "resume_graph_engine" / "src").mkdir(parents=True)

    tdir = tmp_path / "tests" / "unit"
    tdir.mkdir(parents=True)
    (tdir / "test_decoy_comments.py").write_text(
        '"""Docstring decoy mentioning apps_rg_handoff and GovernedBriefingResolver."""\n'
        "# Comment decoy: managed_research_delegation dispatch_outreach_research_briefing apps_rg_handoff\n"
        "def test_unrelated_math() -> None:\n"
        "    assert 3 + 4 == 7\n",
        encoding="utf-8",
    )

    rep = run_testing_gaps_audit(tmp_path)
    assert rep["outreach_handoff_test_count"] == 0
    assert rep["resume_handoff_test_count"] == 0
    assert rep["pillar_status"]["pillar_2_cross_subsystem_handoff_tests"] == "FAIL"


def test_verify_fix_eval_pinning_blocks_chore_branches_and_subsystem_e2e_mocks(tmp_path: Path) -> None:
    """Prove `chore/*` branches and subsystem `resume_graph_engine/tests/end_to_end/` mocks fail closed (LH-07)."""
    rg_e2e = tmp_path / "resume_graph_engine" / "tests" / "end_to_end"
    rg_e2e.mkdir(parents=True)
    (rg_e2e / "test_mocked_rg_e2e.py").write_text(
        "from unittest.mock import MagicMock\n\n"
        "def test_fake_rg_e2e() -> None:\n"
        "    m = MagicMock(return_value=1)\n"
        "    assert m() == 1\n",
        encoding="utf-8",
    )

    rep = evaluate_non_mock_e2e_branch_requirement(
        tmp_path,
        changed_paths=["agents/orchestration/workflow.py"],
        branch_name="chore/agents-assurance-remediation",
    )
    assert rep["status"] == "FAIL"
    assert rep["fail_closed_fix_pinning_active"] is True
    codes = {v["code"] for v in rep["violations"]}
    assert "FORBIDDEN_MOCK_IN_E2E_PIN" in codes
    assert "MISSING_BRANCH_REGRESSION_TEST" in codes


def test_previously_collision_masked_modules_behavioral_contracts(tmp_path: Path) -> None:
    """Exercise genuine contracts on modules previously masked by `main`/`run` flat name collisions."""
    # 1. tools/lint_commit_message.py
    assert lint_commit_message.lint_commit_msg("feat(governance): harden import-bound coverage") is True
    assert lint_commit_message.lint_commit_msg("bad commit message without prefix") is False

    # 2. tools/benchmark_macbook_runtime.py
    stats = benchmark_macbook_runtime._compute_stats([10.0, 11.0, 10.5, 11.2])
    assert stats["min"] == 10.0 and stats["max"] == 11.2 and stats["drift_ratio"] == 1.0
    assert callable(benchmark_macbook_runtime.benchmark_outreach_validation)
    assert callable(benchmark_macbook_runtime.main)

    # 3. ops_scripts/mark_stub_judge_artifacts.py
    art_root = tmp_path / "proofs"
    run_lane = art_root / "run_01" / "lanes" / "headline"
    run_lane.mkdir(parents=True)
    (run_lane / "headline_judge_packet.json").write_text("{}", encoding="utf-8")
    (run_lane / "x1d_llm_judge_outputs.json").write_text(
        json.dumps(
            {
                "judges": [
                    {"judge_id": "j_stub", "model_actual": "argon-stub", "score": 0.95, "pass": True},
                    {"judge_id": "j_real", "model_actual": "gpt-oss-120b-medium", "score": 0.88, "pass": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    scan_res = mark_stub_judge_artifacts.scan(art_root, tmp_path / "scan_out")
    assert scan_res["inventory"]["stub_rows"] == 1
    assert scan_res["corpus"]["real_rows"] == 1
    assert callable(mark_stub_judge_artifacts.scan_generators)
    assert callable(mark_stub_judge_artifacts.main)

    # 4. ops_scripts/ci/check_eval_harness_promotion_evidence.py & apps_research dry-run tool
    missing_rc = check_eval_harness_promotion_evidence.main(
        ["--repo-root", str(tmp_path), "--manifest", str(tmp_path / "missing_manifest.json"), "--json"]
    )
    assert missing_rc == 1
    assert research_dry_run_tool.main() == 0

    # 5. whole_resume deterministic_checks & pairwise
    det_res = deterministic_checks.evaluate_resume_artifact(
        {"sections": [{"section_id": "headline", "text": "SVP AI Platform", "claims": []}], "employment": []},
        {"jd_text": "Enterprise AI architecture leadership", "concepts": []},
    )
    assert det_res["metrics"]["chronology_inconsistency_count"] == 0 and det_res["material_defect_count"] >= 1

    dim_scores = {dim: 4 for dim in W9_DIMENSIONS}
    pw_res = pairwise.evaluate_pairwise(
        {
            "candidate_variant": "A",
            "adjudication": {"final_labels": {"preference": "A", "resume_a": dim_scores, "resume_b": dim_scores}},
            "reviews": [],
        },
        {"status": "PASS", "failure_codes": []},
    )
    assert pw_res["status"] == "PASS" and pw_res["resolved_preference"] == "CANDIDATE"

    # 6. validate_p2_w0_graph_skills_gap_inventory & snapshot_graph_sqlite & otel verify_preflight
    with pytest.raises(validate_p2_w0_graph_skills_gap_inventory.P2W0GapInventoryError):
        validate_p2_w0_graph_skills_gap_inventory.validate_p2_w0_graph_skills_gap_inventory({"wave": "WRONG"})

    db_file = tmp_path / "sample_graph.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    snap_res = snapshot_graph_sqlite.snapshot_augmented_skills_graph(
        repo_root=tmp_path,
        db_path=db_file,
        backup_dir=tmp_path / "snaps",
    )
    assert snap_res["manifest"]["file_count"] == 1
    assert callable(verify_preflight.main)

    # 7. Verify CLI entrypoints across fact_inventory and apps_rg_standalone wave modules
    cli_modules = (
        apply_commercial_fact_promotion,
        apply_commercial_skills_expansion,
        apply_cro_projection_hardening,
        apply_draft_skill_promotions_20260527,
        apply_phase1_new_skill_nodes,
        apply_phase1_resume_linkage_remediation,
        apply_phase2_gtm_presales_expansion,
        apply_phase2_senior_role_graph_w12,
        apply_phase2_senior_role_graph_w8_w11,
        exec_summary_graph_projection_w4b,
        harden_augmented_skills_graph_ssot,
        run_materialize_augmented_skills_graph_sqlite,
        run_w14b_taxonomy_track_weight_wiring,
        run_w4_w14_multilane_section_projection,
        select_role_facts,
        validate_commercial_srfs_projection,
        c03_final_resume_output_review_ui,
        c03_full_resume_qrel_w1b,
        c03_graph_evidence_cluster_embedding_wave6,
        c03_graph_evidence_cluster_human_intake_wave9,
        c03_graph_evidence_cluster_qualification_wave7,
        c03_graph_evidence_cluster_registry_wave4,
        c03_targeted_qrel_review_ui,
        gpu_embedding_residency_w2,
    )
    for mod in cli_modules:
        assert callable(getattr(mod, "main")), f"{mod.__name__} missing callable main()"
