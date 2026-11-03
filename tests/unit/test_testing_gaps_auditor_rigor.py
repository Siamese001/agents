"""Unit tests for Wave 5 11-root Testing Gaps, Mock Reachability, and Assertion Rigor."""

from __future__ import annotations

from pathlib import Path

from tools.audit_mock_reachability import _PRODUCTION_ROOTS
from tools.testing_gaps_auditor import PRODUCTION_PACKAGES, TEST_ROOTS, run_testing_gaps_audit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_live_testing_gaps_auditor_covers_all_11_roots_and_6_test_surfaces() -> None:
    rep = run_testing_gaps_audit(REPO_ROOT)
    assert rep["is_clean"] is True, rep
    assert len(PRODUCTION_PACKAGES) == 11
    assert len(_PRODUCTION_ROOTS) == 11
    assert set(TEST_ROOTS) == {
        "tests",
        "resume_graph_engine/tests",
        "outreach_engine/tests",
        "apps_eval/tests",
        "scripts/local_llm",
        "resume_graph_engine/src/apps_rg/evals",
    }
    assert rep["total_test_files_scanned"] >= 945
    assert rep["outreach_handoff_test_count"] >= 1
    assert rep["resume_handoff_test_count"] >= 1


def test_testing_gaps_rejects_validate_only_bare_reraise_under_coverage_and_quarantine(tmp_path: Path) -> None:
    # 1. Create a 12-symbol package where only 1 symbol is referenced (< 15% ratio gate)
    pkg = tmp_path / "agents"
    pkg.mkdir(parents=True)
    fn_defs = "\n".join(f"def pub_fn_{idx}() -> int:\n    return {idx}\n" for idx in range(12))
    (pkg / "many_symbols.py").write_text(fn_defs, encoding="utf-8")

    # 2. Create apps_research + outreach_engine + resume_graph_engine, but ONLY provide outreach handoff test
    (tmp_path / "apps_research").mkdir()
    (tmp_path / "outreach_engine" / "src").mkdir(parents=True)
    (tmp_path / "resume_graph_engine" / "src").mkdir(parents=True)

    # Misplaced test inside production src/ outside tests/
    (tmp_path / "outreach_engine" / "src" / "test_stray_in_src.py").write_text(
        "def test_ok() -> None:\n    assert 1 == 1\n",
        encoding="utf-8",
    )

    # Protected test root ignored in outreach_engine/pytest.ini and missing --timeout=
    (tmp_path / "outreach_engine" / "pytest.ini").write_text(
        "[pytest]\naddopts = --ignore=outreach_engine/tests\n",
        encoding="utf-8",
    )

    # 3. Create tests calling validate_something() with no assert, and bare `raise` with no exception
    tdir = tmp_path / "tests"
    tdir.mkdir()
    (tdir / "test_weak_cases.py").write_text(
        "from agents.many_symbols import pub_fn_0\n\n"
        "def validate_helper(x: int) -> int:\n"
        "    return x\n\n"
        "def test_validate_without_assert() -> None:\n"
        "    validate_helper(pub_fn_0())\n\n"
        "def test_bare_reraise_only() -> None:\n"
        "    try:\n"
        "        pub_fn_0()\n"
        "    except ValueError:\n"
        "        raise\n\n"
        "def test_outreach_handoff_only() -> None:\n"
        "    marker = 'GovernedBriefingResolver'\n"
        "    assert marker == 'GovernedBriefingResolver'\n",
        encoding="utf-8",
    )

    rep = run_testing_gaps_audit(tmp_path)
    assert rep["is_clean"] is False
    assert rep["pillar_status"]["pillar_1_public_entrypoint_coverage"] == "FAIL"
    assert any("agents(" in item for item in rep["under_covered_packages"])
    assert rep["pillar_status"]["pillar_2_cross_subsystem_handoff_tests"] == "FAIL"
    assert rep["outreach_handoff_test_count"] == 1
    assert rep["resume_handoff_test_count"] == 0

    zero_names = {item["test"] for item in rep["zero_assertion_tests"]}
    assert "test_validate_without_assert" in zero_names
    assert "test_bare_reraise_only" in zero_names

    issues_txt = "\n".join(rep["hook_and_pytest_issues"])
    assert "outreach_engine/pytest.ini: missing mandatory --timeout=" in issues_txt
    assert "forbidden --ignore=outreach_engine/tests" in issues_txt
    assert "test_stray_in_src.py: misplaced test module" in issues_txt
