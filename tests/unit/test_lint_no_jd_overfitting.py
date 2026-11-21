"""Unit and bilateral recall-precision tests for tools/lint_no_jd_overfitting.py."""

from __future__ import annotations

from pathlib import Path

from tools.lint_no_jd_overfitting import (
    check_file_no_jd_overfitting,
    collect_production_files,
    scan_files,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_detects_hardcoded_company_branch_in_production_module(tmp_path: Path) -> None:
    prod_file = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "bad_allocator.py"
    prod_file.parent.mkdir(parents=True)
    prod_file.write_text(
        "def allocate(jd_text: str) -> str:\n"
        "    if 'truist' in jd_text.lower():\n"
        "        return 'banking_override'\n"
        "    return 'default'\n",
        encoding="utf-8",
    )
    hits = check_file_no_jd_overfitting(prod_file, tmp_path)
    assert len(hits) == 1
    assert hits[0]["code"] == "JD_COMPANY_OVERFITTING_BRANCH"
    assert hits[0]["token"] == "truist"


def test_bilateral_precision_clean_role_profile_has_zero_hits(tmp_path: Path) -> None:
    clean_file = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "clean_allocator.py"
    clean_file.parent.mkdir(parents=True)
    clean_file.write_text(
        "def allocate(role_profile: str) -> str:\n"
        "    if role_profile == 'svp_agentic_engineering':\n"
        "        return 'career_band_core'\n"
        "    return 'balanced'\n",
        encoding="utf-8",
    )
    hits = check_file_no_jd_overfitting(clean_file, tmp_path)
    assert hits == []


def test_targeting_config_and_tests_are_allowlisted(tmp_path: Path) -> None:
    cfg_file = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "config" / "targeting" / "loader.py"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text("def pick(name):\n    return name == 'truist'\n", encoding="utf-8")
    assert check_file_no_jd_overfitting(cfg_file, tmp_path) == []


def test_repository_passes_with_baseline_ratchet() -> None:
    files = collect_production_files(REPO_ROOT)
    report = scan_files(files, REPO_ROOT, use_baseline=True)
    assert report["status"] == "PASS", f"Unbaselined overfitting violations: {report['violations']}"
    assert report["unbaselined_count"] == 0
