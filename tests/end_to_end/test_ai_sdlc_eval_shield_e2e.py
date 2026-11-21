"""Unmocked E2E and adversarial edge-case suite for AI-SDLC eval construct validity & shield.

Zero unittest.mock, MagicMock, patch, or monkeypatch imports are permitted in this file.
Covers adversarial categories:
1. Invariant bypass attempts (mock injection into smoke harness / E2E pin, vacuous pass stub, score clamping).
2. Malformed input (broken syntax file, invalid flat plan).
3. Exact production regressions (blind executive_summary judge leak check, off-domain employer leak check).
"""

from __future__ import annotations

from pathlib import Path

from tools.audit_eval_construct_validity import (
    audit_repository,
    scan_file_for_forbidden_mocks,
    scan_file_for_vacuous_eval_and_score_clamping,
)
from tools.run_diff_scoped_eval_shield import run_eval_shield
from tools.verify_fix_eval_pinning import (
    evaluate_non_mock_e2e_branch_requirement,
    scan_e2e_file_for_forbidden_mocks,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_real_repository_passes_eval_construct_validity_strict() -> None:
    report = audit_repository(REPO_ROOT)
    assert report["status"] == "PASS", f"Construct validity failed: {report['violations']}"
    assert report["violation_count"] == 0
    assert "tools/run_diff_scoped_eval_shield.py" in report["scanned_smoke_files"]


def test_fault_injection_detects_forbidden_mock_in_smoke_harness(tmp_path: Path) -> None:
    bad_smoke = tmp_path / "fake_smoke.py"
    bad_smoke.write_text(
        "from unittest.mock import MagicMock, patch\n"
        "def run():\n"
        "    with patch('os.path.exists', return_value=True):\n"
        "        return MagicMock()\n",
        encoding="utf-8",
    )
    violations = scan_file_for_forbidden_mocks(bad_smoke, code="FORBIDDEN_MOCK_IN_SMOKE_HARNESS")
    codes = {v["code"] for v in violations}
    assert "FORBIDDEN_MOCK_IN_SMOKE_HARNESS" in codes
    assert len(violations) >= 3


def test_fault_injection_detects_vacuous_eval_stub_and_score_clamping(tmp_path: Path) -> None:
    bad_eval = tmp_path / "fake_eval.py"
    bad_eval.write_text(
        "def evaluate_candidate(payload):\n"
        "    return {'status': 'PASS', 'score': 5.0}\n\n"
        "def coerce_judge(raw_score, threshold=4.7):\n"
        "    return max(raw_score, threshold)\n",
        encoding="utf-8",
    )
    violations = scan_file_for_vacuous_eval_and_score_clamping(bad_eval)
    codes = {v["code"] for v in violations}
    assert "VACUOUS_EVALUATE_STUB" in codes
    assert "CLAMPED_REGRESSION_DELTA" in codes


def test_malformed_python_file_fails_closed_with_ast_parse_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken_eval.py"
    broken.write_text("def broken(:\n    pass\n", encoding="utf-8")
    violations = scan_e2e_file_for_forbidden_mocks(broken)
    assert len(violations) == 1
    assert violations[0]["code"] == "AST_PARSE_ERROR"


def test_this_e2e_file_passes_unmocked_pin_gate_and_rejects_monkeypatch(tmp_path: Path) -> None:
    self_report = evaluate_non_mock_e2e_branch_requirement(
        REPO_ROOT,
        changed_paths=["tools/run_diff_scoped_eval_shield.py", "tests/end_to_end/test_ai_sdlc_eval_shield_e2e.py"],
        e2e_files=[Path(__file__)],
        require_branch_test=True,
    )
    assert self_report["status"] == "PASS", self_report

    mocked_e2e = tmp_path / "test_mocked_e2e.py"
    mocked_e2e.write_text(
        "def test_bad_e2e(monkeypatch):\n"
        "    monkeypatch.setenv('FOO', 'bar')\n",
        encoding="utf-8",
    )
    bad_report = evaluate_non_mock_e2e_branch_requirement(
        REPO_ROOT,
        changed_paths=["resume_graph_engine/src/x.py"],
        e2e_files=[mocked_e2e],
        require_branch_test=True,
    )
    codes = {v["code"] for v in bad_report["violations"]}
    assert bad_report["status"] == "FAIL"
    assert "FORBIDDEN_MOCK_IN_E2E_PIN" in codes
    assert "MISSING_BRANCH_REGRESSION_TEST" in codes


def test_unmocked_diff_scoped_eval_shield_all_domains_pass() -> None:
    report = run_eval_shield(REPO_ROOT, run_all=True)
    assert report["status"] == "PASS", f"Eval shield failed: {report}"
    assert set(report["domains_run"]) == {
        "resume_graph_engine",
        "outreach_engine",
        "apps_research",
        "agents_eval_flywheel",
        "governance_guards",
    }
