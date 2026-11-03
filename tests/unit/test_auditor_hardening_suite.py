"""Behavioral fault-injection unit tests for Wave 3 hardened governance auditors."""
from __future__ import annotations

import json
from pathlib import Path

from tools.audit_mock_reachability import audit_production_file
from tools.lint_file_budgets import PRODUCTION_DIRECTORIES as BUDGET_PROD_DIRS, check_file_budget
from tools.lint_model_pins import scan_catalog_json, scan_provider_profiles_yaml
from tools.lint_production_purity import check_file_production_purity
from tools.ssot_boundary_auditor import audit_constitutional_ast_floor
from tools.storage_worktree_hygiene import scan_scratch_violations
from tools.testing_gaps_auditor import run_testing_gaps_audit
from tools.validate_eval_rubrics import validate_eval_rubrics

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mock_reachability_catches_decoy_comments_and_unguarded_mock_branch(tmp_path: Path) -> None:
    prod_file = tmp_path / "agents" / "bad_client.py"
    prod_file.parent.mkdir(parents=True)
    prod_file.write_text(
        'PLACEHOLDER_SET = {"sk-local-dev-key"}\n'
        'def get_key(x: str = "") -> str:\n'
        '    api_key = x or "sk-local-dev-key"  # reject placeholder in (\n'
        '    return api_key\n'
        'def get_url() -> str:\n'
        '    return "http://localhost:8000/v1"  # forbidden reject\n'
        'def run_panel(mode: str) -> str:\n'
        '    if mode == "mocked":\n'
        '        note = "raise MOCK_JUDGE_FORBIDDEN"\n'
        '        return note\n'
        '    return "live"\n',
        encoding="utf-8",
    )
    violations = audit_production_file(prod_file, tmp_path)
    assert any("MR004" in v for v in violations), violations
    assert any("MR005" in v for v in violations), violations
    assert any("MR001" in v for v in violations), violations

    clean_file = tmp_path / "agents" / "clean_client.py"
    clean_file.write_text(
        'PLACEHOLDER_SET = {"sk-local-dev-key", "http://localhost:8000/v1"}\n'
        'def run_panel(mode: str) -> str:\n'
        '    if mode == "mocked":\n'
        '        raise RuntimeError("mock forbidden in production")\n'
        '    return "live"\n',
        encoding="utf-8",
    )
    assert audit_production_file(clean_file, tmp_path) == []


def test_production_purity_catches_do_not_and_json_brace_decoys(tmp_path: Path) -> None:
    tainted = tmp_path / "apps_research" / "synth.py"
    tainted.parent.mkdir(parents=True)
    tainted.write_text(
        "def generate_company_brief() -> str:\n"
        '    return \'{"summary": "Precomputed static answer over eighty characters claiming do not remediate proof_gap in output."}\'\n'
        'executive_summary = "Prewritten narrative over eighty characters stating we do not need live synthesis or remediation here."\n',
        encoding="utf-8",
    )
    hits = check_file_production_purity(tainted, tmp_path)
    assert len(hits) == 2, hits

    clean_prompt = tmp_path / "apps_research" / "prompt_builder.py"
    clean_prompt.write_text(
        'SYNTHESIS_PROMPT_TEMPLATE = (\n'
        '    "You are an executive analyst. Summarize {company_name} transformation priorities "\n'
        '    "strictly from verified evidence packets."\n'
        ')\n',
        encoding="utf-8",
    )
    assert check_file_production_purity(clean_prompt, tmp_path) == []


def test_testing_gaps_auditor_catches_zero_assertion_skip_and_xfail(tmp_path: Path) -> None:
    pkg = tmp_path / "agents"
    pkg.mkdir(parents=True)
    (pkg / "sample.py").write_text("def compute_value() -> int:\n    return 42\n", encoding="utf-8")

    tdir = tmp_path / "tests"
    tdir.mkdir(parents=True)
    (tdir / "test_bad.py").write_text(
        "import pytest\n"
        "from agents.sample import compute_value\n\n"
        "def test_zero_assert():\n"
        "    compute_value()\n\n"
        "@pytest.mark.skip\n"
        "def test_unreasoned_skip():\n"
        "    assert compute_value() == 42\n\n"
        "@pytest.mark.xfail\n"
        "def test_non_strict_xfail():\n"
        "    assert compute_value() == 42\n",
        encoding="utf-8",
    )

    rep = run_testing_gaps_audit(tmp_path)
    assert rep["is_clean"] is False
    assert any(item["test"] == "test_zero_assert" for item in rep["zero_assertion_tests"])
    assert len(rep["unreasoned_skips"]) == 1
    assert len(rep["non_strict_xfails"]) == 1


def test_validate_eval_rubrics_catches_comment_only_module_and_weight_drift(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    eval_dir = tmp_path / "apps_eval"
    eval_dir.mkdir()
    (eval_dir / "stub_eval.py").write_text("# non-zero file size with zero AST definitions\n", encoding="utf-8")

    rub_dir = tmp_path / "config" / "exit_eval_rubrics"
    rub_dir.mkdir(parents=True)
    (rub_dir / "x1a_broken.yaml").write_text(
        "composition: weighted\n"
        "aggregate_threshold: 0.85\n"
        "dimensions:\n"
        "  - name: grounding\n"
        "    scale: [0.0, 1.0]\n"
        "    threshold: 0.8\n"
        "    weight: 0.55\n"
        "  - name: clarity\n"
        "    scale: [0.0, 1.0]\n"
        "    threshold: 0.8\n"
        "    weight: 0.25\n",
        encoding="utf-8",
    )

    rep = validate_eval_rubrics(tmp_path)
    assert rep["is_clean"] is False
    assert any("zero AST definitions" in v for v in rep["violations"]), rep["violations"]
    assert any("sum to 0.8000 != 1.0" in v for v in rep["violations"]), rep["violations"]


def test_ssot_boundary_and_file_budgets_cover_all_nine_packages(tmp_path: Path) -> None:
    for expected_dir in (
        "agents",
        "outreach_engine",
        "resume_engine",
        "resume_graph_engine",
        "apps_research",
        "apps_eval",
        "apps_model_telemetry",
        "infrastructure",
        "ops_scripts",
    ):
        assert expected_dir in BUDGET_PROD_DIRS

    res_file = tmp_path / "apps_research" / "swallow.py"
    res_file.parent.mkdir(parents=True)
    res_file.write_text(
        "def quiet() -> None:\n"
        "    try:\n"
        "        int('bad')\n"
        "    except Exception:\n"
        "        pass\n",
        encoding="utf-8",
    )
    floor = audit_constitutional_ast_floor(tmp_path)
    assert any("apps_research/swallow.py" in item for item in floor["unguarded_exceptions"])

    oversized = tmp_path / "infrastructure" / "huge_mod.py"
    oversized.parent.mkdir(parents=True)
    oversized.write_text("x = 1\n" * 605, encoding="utf-8")
    passed, line_count, _ = check_file_budget(oversized, tmp_path, ratchet={})
    assert passed is False
    assert line_count == 605


def test_model_pins_and_scratch_secret_scanner_fail_closed(tmp_path: Path) -> None:
    cat_path = tmp_path / "model_catalog.json"
    cat_path.write_text(
        json.dumps({"routing": {"sonnet_tier": "opus-tier-pin", "active_default": "bare"}}).replace(
            '"bare"', '"gemini"'
        ),
        encoding="utf-8",
    )
    cat_findings = scan_catalog_json(cat_path)
    categories = {f["category"] for f in cat_findings}
    assert "MISLABELLED_ALIAS" in categories
    assert "BARE_FAMILY_ALIAS" in categories

    prof_path = tmp_path / "provider_profiles.yaml"
    prof_path.write_text(
        "judge_models:\n"
        "  tier_1:\n"
        "    openai: uncataloged-pin-v9\n",
        encoding="utf-8",
    )
    prof_findings = scan_provider_profiles_yaml(prof_path, approved_models={"approved-pin-v1"})
    assert any(f["category"] == "UNAPPROVED_PIN" for f in prof_findings)

    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir()
    token_prefix = "ghp_"
    token_body = "A1b2C3d4E5f6" * 3
    (scratch_dir / "temp_creds.txt").write_text(f"TOKEN={token_prefix}{token_body}\n", encoding="utf-8")
    leaks = scan_scratch_violations(tmp_path)
    assert "scratch/temp_creds.txt" in leaks
