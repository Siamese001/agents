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
