"""Unmocked Wave 3 regression tests for scanner, shield, construct-validity, and purity loophole closures."""

from __future__ import annotations

from pathlib import Path

from apps_eval.construct_validity import scan_extended_construct_validity
from tools.audit_eval_construct_validity import audit_repository
from tools.lint_no_jd_overfitting import _is_allowlisted, check_file_no_jd_overfitting
from tools.lint_production_purity import check_file_production_purity, is_production_file
from tools.run_diff_scoped_eval_shield import select_domains_for_paths

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_diff_scoped_eval_shield_expands_2_hop_reverse_importers(tmp_path: Path) -> None:
    """LH-04: 2-hop transitive importer expansion activates downstream domain shield on git-tracked files."""
    import subprocess

    (tmp_path / "infrastructure").mkdir(parents=True)
    (tmp_path / "infrastructure" / "leaf_util.py").write_text("X = 1\n", encoding="utf-8")

    (tmp_path / "agents").mkdir(parents=True)
    (tmp_path / "agents" / "mid_bridge.py").write_text("from infrastructure import leaf_util\n", encoding="utf-8")

    (tmp_path / "outreach_engine" / "src").mkdir(parents=True)
    (tmp_path / "outreach_engine" / "src" / "consumer.py").write_text(
        "from agents import mid_bridge\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True, timeout=15)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True, text=True, timeout=15)

    domains = select_domains_for_paths(
        ["infrastructure/leaf_util.py"],
        effective_lane=1,
        run_all=False,
        repo_root=tmp_path,
    )
    assert "agents_eval_flywheel" in domains
    assert "outreach_engine" in domains


def test_construct_validity_wires_scanner_and_test_flags_across_repo() -> None:
    """LH-05: audit_eval_construct_validity scans tools/ scanners and all 6 test roots with zero violations."""
    report = audit_repository(REPO_ROOT)
    assert report["status"] == "PASS", f"Unexpected construct validity violations: {report['violations']}"
    assert len(report["scanned_scanner_files"]) >= 15
    assert len(report["scanned_test_files"]) >= 100


def test_extended_construct_validity_catches_silent_syntax_swallow_and_pass_fail_tautology(tmp_path: Path) -> None:
    """LH-05 & LH-11: Extended scanner detects silent SyntaxError return [] and verdict in ('PASS', 'FAIL')."""
    bad_scanner = tmp_path / "lint_fake.py"
    bad_scanner.write_text(
        "def scan():\n"
        "    try:\n"
        "        return [1]\n"
        "    except SyntaxError:\n"
        "        return []\n",
        encoding="utf-8",
    )
    s_viols = scan_extended_construct_validity(bad_scanner, is_scanner_file=True)
    assert any(v["code"] == "SCANNER_SILENT_SYNTAX_ERROR_SWALLOW" for v in s_viols)

    bad_test = tmp_path / "test_fake.py"
    bad_test.write_text(
        "def test_vacuous(verdict):\n"
        '    assert verdict in ("PASS", "FAIL")\n',
        encoding="utf-8",
    )
    t_viols = scan_extended_construct_validity(bad_test, is_test_file=True)
    assert any(v["code"] == "VACUOUS_PASS_OR_FAIL_ASSERTION" for v in t_viols)


def test_lint_production_purity_includes_apps_eval_fails_on_syntax_error_and_blocks_comment_smuggling(
    tmp_path: Path,
) -> None:
    """LH-11: Purity linter covers apps_eval, fails closed on SyntaxError, and blocks # config/fixtures/ comments."""
    assert is_production_file(REPO_ROOT / "apps_eval" / "online_grader.py", REPO_ROOT) is True
    assert is_production_file(REPO_ROOT / "apps_eval" / "scenarios.py", REPO_ROOT) is False

    broken = tmp_path / "agents" / "broken_syntax.py"
    broken.parent.mkdir(parents=True)
    broken.write_text("def broken(:\n    pass\n", encoding="utf-8")
    syn_viols = check_file_production_purity(broken, tmp_path)
    assert any(sym == "SYNTAX_ERROR" for _ln, sym, _msg in syn_viols)

    smuggled = tmp_path / "agents" / "smuggled.py"
    forbidden_fixture = "tests/" + "fixtures/golden_answer.json"
    comment_bypass = "config/" + "fixtures/allowed.json"
    smuggled.write_text(
        f'LEAK = "{forbidden_fixture}"  # {comment_bypass}\n',
        encoding="utf-8",
    )
    smug_viols = check_file_production_purity(smuggled, tmp_path)
    assert len(smug_viols) >= 1, "Inline comment must not suppress forbidden fixture path violation"


def test_lint_no_jd_overfitting_fails_on_syntax_error_and_enforces_segment_allowlist(tmp_path: Path) -> None:
    """LH-11: Overfitting linter fails closed on SyntaxError and uses exact /segment/ allowlisting."""
    assert _is_allowlisted("resume_graph_engine/src/apps_rg/config/targeting/citi.py") is True
    assert _is_allowlisted("agents/my_evals_helper.py") is False

    broken = tmp_path / "agents" / "bad_syntax.py"
    broken.parent.mkdir(parents=True)
    broken.write_text("if company == 'truist'\n", encoding="utf-8")
    syn_hits = check_file_no_jd_overfitting(broken, tmp_path)
    assert any(h["code"] == "JD_OVERFITTING_SYNTAX_ERROR" for h in syn_hits)

    multi_word = tmp_path / "agents" / "branch_overfit.py"
    multi_word.write_text(
        'def route(company: str) -> str:\n'
        '    if company == "Truist Financial Corporation":\n'
        '        return "bank"\n'
        '    return "general"\n',
        encoding="utf-8",
    )
    mw_hits = check_file_no_jd_overfitting(multi_word, tmp_path)
    assert any(h["token"] == "truist" for h in mw_hits)
