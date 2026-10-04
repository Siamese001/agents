"""Unit tests verifying Wave 1 invariants: packaging normalization, subtree de-duplication, and configuration SSOT."""

from __future__ import annotations

import ast
from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_canonical_package_resolution() -> None:
    """Ensure apps_research, apps_eval, apps_model_telemetry resolve solely from repository root."""
    import apps_eval
    import apps_model_telemetry
    import apps_research

    assert Path(apps_research.__file__).resolve().is_relative_to(REPO_ROOT / "apps_research")
    assert Path(apps_eval.__file__).resolve().is_relative_to(REPO_ROOT / "apps_eval")
    assert Path(apps_model_telemetry.__file__).resolve().is_relative_to(REPO_ROOT / "apps_model_telemetry")

    # Verify they do NOT resolve from resume_graph_engine/src
    assert not Path(apps_research.__file__).resolve().is_relative_to(REPO_ROOT / "resume_graph_engine" / "src")
    assert not Path(apps_eval.__file__).resolve().is_relative_to(REPO_ROOT / "resume_graph_engine" / "src")
    assert not Path(apps_model_telemetry.__file__).resolve().is_relative_to(REPO_ROOT / "resume_graph_engine" / "src")


def test_no_duplicate_subtrees_in_resume_graph_engine() -> None:
    """Ensure duplicate application trees in resume_graph_engine/src are completely removed."""
    rge_src = REPO_ROOT / "resume_graph_engine" / "src"

    assert not (rge_src / "apps_research").exists(), "resume_graph_engine/src/apps_research must not exist"
    assert not (rge_src / "apps_eval").exists(), "resume_graph_engine/src/apps_eval must not exist"
    assert not (rge_src / "apps_model_telemetry").exists(), "resume_graph_engine/src/apps_model_telemetry must not exist"


LEGACY_SYS_PATH_ALLOWLIST: set[str] = set()

APPS_RG_MAIN_BLOCK_ALLOWLIST = {
    "__main__.py",
    "bare_pipeline.py",
    "fact_inventory/apply_agentic_experience_skills_augmentation.py",
    "fact_inventory/run_materialize_augmented_skills_graph_sqlite.py",
    "runtime/internal/final_resume_assembler.py",
    "runtime/internal/generated_lane_rollup.py",
    "runtime/internal/lane_batch.py",
    "runtime/internal/locked_copy_builder.py",
    "runtime/internal/resume_package_disposition.py",
    "runtime/sections/competencies_lane_runtime.py",
    "runtime/sections/executive_summary_lane.py",
    "runtime/sections/ibm_bullets_lane.py",
    "runtime/sections/ibm_narrative_lane_runtime.py",
    "runtime/sections/unify_bullets_lane.py",
    "runtime/sections/unify_narrative_lane.py",
}

APPS_RG_ARGPARSE_ALLOWLIST = {
    "__main__.py",
    "evals/authoritative/cli.py",
    "evals/benchmark_design.py",
    "evals/c03_ci_ratchet.py",
    "evals/c03_human_eval/cli.py",
    "evals/c03_human_eval/seal_records.py",
    "evals/e2e_operational_evaluation.py",
    "evals/evaluator_validity_registry.py",
    "evals/finished_resume_outcome.py",
    "evals/l1_cognitive_evaluation_cli.py",
    "evals/material_claim_authority.py",
    "evals/meta_eval/cli.py",
    "evals/pipeline_attempt_evaluation.py",
    "evals/pipeline_measurement_coverage.py",
    "evals/protected_holdout_qualification.py",
    "evals/receipt_catalog.py",
    "evals/repeatability/cli.py",
    "evals/resume_graph_calibration.py",
    "evals/section_quality_benchmark/cli.py",
    "evals/shadow_canary_promotion.py",
    "evals/whole_resume/cli.py",
    "evals/whole_resume/p1_blind_utility.py",
    "fact_inventory/apply_c03_graph_skill_granularity_hardening.py",
    "fact_inventory/apply_phase1_new_skill_nodes.py",
    "fact_inventory/apply_phase1_resume_linkage_remediation.py",
    "fact_inventory/c03_graph_kpi_health.py",
    "fact_inventory/detect_graph_skill_gaps.py",
    "fact_inventory/harden_augmented_skills_graph_ssot.py",
    "fact_inventory/materialize_career_tracks_p1.py",
    "fact_inventory/p2_graph_skills_accelerated_closeout.py",
    "fact_inventory/run_w14_senior_role_offline_traversal.py",
    "fact_inventory/validate_c03_graph_hardening.py",
    "fact_inventory/validate_c03_graph_skill_granularity.py",
    "runtime/doctor.py",
    "runtime/fact_vectors_bootstrap.py",
    "runtime/integrated_product_proof_gate.py",
    "runtime/orchestration/patch_run.py",
    "runtime/outputs/evidence_exporter.py",
    "runtime/providers/anthropic_cache_suite_summary.py",
    "runtime/sections/competencies_lane_runtime.py",
    "runtime/validators/validate_exec_summary_graph_only_generation.py",
}


def test_entrypoints_do_not_contain_sys_path_insert() -> None:
    """Ensure entrypoints, init files, and apps_rg modules do not use sys.path mutations."""
    scan_targets = [
        REPO_ROOT / "resume_engine",
        REPO_ROOT / "outreach_engine" / "__main__.py",
        REPO_ROOT / "resume_graph_engine" / "__init__.py",
        REPO_ROOT / "resume_graph_engine" / "__main__.py",
        REPO_ROOT / "resume_graph_engine" / "src" / "apps_rg",
    ]

    seen: set[Path] = set()
    for item in scan_targets:
        if not item.exists():
            continue
        py_files = [item] if item.is_file() else list(item.glob("**/*.py"))
        for py_file in py_files:
            if py_file in seen:
                continue
            seen.add(py_file)
            if "test_" in py_file.name or "tests" in str(py_file):
                continue
            rel = py_file.relative_to(REPO_ROOT).as_posix()
            if rel in LEGACY_SYS_PATH_ALLOWLIST:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr in ("insert", "append"):
                        val = func.value
                        if isinstance(val, ast.Attribute) and val.attr == "path":
                            if isinstance(val.value, ast.Name) and val.value.id == "sys":
                                pytest.fail(f"Found forbidden sys.path.{func.attr}() in {rel}:{node.lineno}")


def test_apps_rg_entrypoints_and_argparse_allowlist() -> None:
    """Ensure no unapproved __main__ blocks or argparse parsers exist in apps_rg."""
    apps_rg_root = REPO_ROOT / "resume_graph_engine" / "src" / "apps_rg"
    assert apps_rg_root.is_dir(), "apps_rg directory must exist"

    found_mains = set()
    found_argparses = set()

    for py_file in apps_rg_root.rglob("*.py"):
        if "test_" in py_file.name or "tests" in str(py_file):
            continue
        rel = py_file.relative_to(apps_rg_root).as_posix()
        tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                if isinstance(test, ast.Compare):
                    if isinstance(test.left, ast.Name) and test.left.id == "__name__":
                        for comp in test.comparators:
                            if isinstance(comp, ast.Constant) and comp.value == "__main__":
                                found_mains.add(rel)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "ArgumentParser":
                    found_argparses.add(rel)

    unapproved_mains = found_mains - APPS_RG_MAIN_BLOCK_ALLOWLIST
    assert not unapproved_mains, f"New unapproved __main__ blocks detected in apps_rg: {sorted(unapproved_mains)}"

    unapproved_argparses = found_argparses - APPS_RG_ARGPARSE_ALLOWLIST
    assert not unapproved_argparses, f"New unapproved ArgumentParser detected in apps_rg: {sorted(unapproved_argparses)}"


def test_provider_profiles_ssot_exists_and_valid() -> None:
    """Ensure config/provider_profiles.yaml exists as the root SSOT and is valid YAML."""
    root_profiles = REPO_ROOT / "config" / "provider_profiles.yaml"
    apps_rg_profiles = REPO_ROOT / "resume_graph_engine" / "src" / "apps_rg" / "config" / "provider_profiles.yaml"

    assert root_profiles.is_file(), "config/provider_profiles.yaml must exist as root SSOT"
    assert apps_rg_profiles.is_file(), "resume_graph_engine/src/apps_rg/config/provider_profiles.yaml must exist"

    root_data = yaml.safe_load(root_profiles.read_text(encoding="utf-8"))
    apps_rg_data = yaml.safe_load(apps_rg_profiles.read_text(encoding="utf-8"))

    assert isinstance(root_data, dict)
    assert "profiles" in root_data
    assert root_data["profiles"] == apps_rg_data["profiles"], "Root SSOT profiles must match apps_rg profiles"


def test_ratchet_has_no_dead_duplicate_entries() -> None:
    """Ensure file_budgets_ratchet.json does not retain dead duplicate subtree paths."""
    import json

    ratchet_path = REPO_ROOT / "config" / "governance" / "file_budgets_ratchet.json"
    ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))

    for key in ratchet.keys():
        assert not key.startswith("resume_graph_engine/src/apps_research/"), f"Dead key found in ratchet: {key}"
        assert not key.startswith("resume_graph_engine/src/apps_eval/"), f"Dead key found in ratchet: {key}"
        assert not key.startswith("resume_graph_engine/src/apps_model_telemetry/"), f"Dead key found in ratchet: {key}"
