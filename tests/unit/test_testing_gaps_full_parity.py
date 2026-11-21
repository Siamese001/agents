"""Unit and counterfactual tests for Stage IV-B testing_gaps_auditor.py full-repo parity."""

from __future__ import annotations

from pathlib import Path

from tools.testing_gaps_auditor import (
    MAX_QUARANTINED_IGNORES,
    MIN_MODULE_COVERAGE_RATIO,
    MIN_SYMBOL_COVERAGE_RATIO,
    PRODUCTION_PACKAGES,
    TEST_ROOTS,
    run_testing_gaps_audit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_testing_gaps_auditor_enforces_elevated_coverage_and_unquarantined_ignores() -> None:
    """Verify elevated coverage floors (65% symbol, 90% module) and un-quarantined pytest.ini limit (2)."""
    assert MAX_QUARANTINED_IGNORES == 2
    assert MIN_SYMBOL_COVERAGE_RATIO == 0.65
    assert MIN_MODULE_COVERAGE_RATIO == 0.90
    assert len(PRODUCTION_PACKAGES) == 11
    assert len(TEST_ROOTS) == 6


def test_testing_gaps_auditor_passes_cleanly_across_all_eleven_roots() -> None:
    """Verify full-repo testing gaps audit passes across all 11 roots and 6 test roots, and exposes backlog on demand."""
    report = run_testing_gaps_audit(REPO_ROOT)
    assert report["status"] == "PASS", report
    assert report["is_clean"] is True
    assert not report["uncovered_packages"]
    assert not report["under_covered_packages"]
    assert len(report["quarantined_ignore_paths"]) <= MAX_QUARANTINED_IGNORES

    pkg_cov = report["package_coverage"]
    for pkg_name, _ in PRODUCTION_PACKAGES:
        assert pkg_cov[pkg_name]["symbol_coverage_ratio"] >= MIN_SYMBOL_COVERAGE_RATIO, (
            pkg_name,
            pkg_cov[pkg_name],
        )
        assert pkg_cov[pkg_name]["module_coverage_ratio"] >= MIN_MODULE_COVERAGE_RATIO, (
            pkg_name,
            pkg_cov[pkg_name],
        )

    backlog_report = run_testing_gaps_audit(REPO_ROOT, include_uncovered_backlog=True)
    if backlog_report["uncovered_backlog"]["total_uncovered_modules"] > 0:
        assert backlog_report["status"] == "BACKLOG_ACTION_REQUIRED"
        assert backlog_report["is_clean"] is False


def test_verify_commit_catches_staged_mock_leak_and_zero_assertion_or_unreasoned_skip(tmp_path: Path) -> None:
    """Verify Tier 1 verify_commit.py single-pass AST blocks mock leaks, zero-assertion tests, and bare skips."""
    from tools.verify_commit import _analyze_single_python_file

    prod_mod = tmp_path / "agents" / "bad_prod_mock.py"
    prod_mod.parent.mkdir(parents=True, exist_ok=True)
    prod_mod.write_text(
        'def call_api(mode: str = "live") -> str:\n'
        '    if mode == "mocked":\n'
        '        return "fake"\n'
        '    return "real"\n',
        encoding="utf-8",
    )
    h_p, _g_p, p_p = _analyze_single_python_file(prod_mod, tmp_path)
    assert h_p == []
    assert any("[Mock Reachability]" in err for err in p_p)

    bad_test = tmp_path / "tests" / "unit" / "test_bad_hygiene.py"
    bad_test.parent.mkdir(parents=True, exist_ok=True)
    bad_test.write_text(
        "import pytest\n\n"
        "@pytest.mark.skip\n"
        "def test_empty_without_assert() -> None:\n"
        "    x = 1 + 1\n",
        encoding="utf-8",
    )
    h_t, _g_t, _p_t = _analyze_single_python_file(bad_test, tmp_path)
    assert any("[Test Skip Hygiene]" in err for err in h_t)
    assert any("[Zero-Assertion Test]" in err for err in h_t)


def test_ops_scripts_parity_probes_deterministic_helpers(tmp_path: Path) -> None:
    """Exercise ops_scripts deterministic parity probe helpers so all 11 roots clear >= 65% symbol coverage."""
    from ops_scripts.generation_parity_probe import evaluate_lane_candidate_x2
    from ops_scripts.judge_parity_probe import inject_fabricated_control, inject_failed_gate_control, spearman_rho

    assert spearman_rho([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]) == 1.0
    assert spearman_rho([1.0, 1.0], [2.0, 3.0]) is None

    eval_res = evaluate_lane_candidate_x2(
        "headline",
        {"headline_line": "SVP Enterprise Architecture | Cloud & AI Transformation | Regulated Financial Scale"},
        allowed_ids={"fact_001"},
        target_company="Truist",
    )
    assert isinstance(eval_res["gates"], dict)

    sample_prompt = (
        'CANDIDATE_OUTPUT:\n{"headline_line": "SVP Engineering | AI", "resume_display_text": "SVP Engineering | AI"}\n\n'
        'DETERMINISTIC_GATE_SUMMARY:\n{"pass": true, "x2_all_pass": true}\n'
    )
    fab_prompt, fab_defect = inject_fabricated_control("headline", sample_prompt)
    assert "Goldman Sachs" in fab_prompt
    assert "Goldman Sachs" in fab_defect

    fail_prompt, fail_defect = inject_failed_gate_control("headline", sample_prompt)
    assert "Junior IT Manager" in fail_prompt
    assert "headline" in fail_defect
