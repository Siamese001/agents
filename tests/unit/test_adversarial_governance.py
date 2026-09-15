"""Adversarial validation test suite for Two-Tier Governance Gate.

Explicitly tests Cases A through F:
- Case A: Hardcoded answer in production -> PRE-COMMIT FAIL
- Case B: Renamed hardcoded answer (semantic payload) -> PRE-COMMIT FAIL
- Case C: Production code loading golden fixture -> PRE-COMMIT FAIL
- Case D: Legitimate test using golden fixture -> PASS
- Case E: Normal declarative manifest/config -> PASS
- Case F: Production script exceeding budget without justified exclusion -> FAIL
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools.lint_file_budgets import check_file_budget
from tools.lint_production_purity import check_file_production_purity
from tools.lint_contract_schemas import validate_file_against_schema


def test_case_a_hardcoded_answer_fails():
    """Case A: Hardcoded domain answer in production fails pre-commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        prod_file = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "lane.py"
        prod_file.parent.mkdir(parents=True, exist_ok=True)
        prod_file.write_text(
            '''
def generate_executive_summary():
    final_summary = """Seasoned technology executive with 15+ years delivering enterprise AI transformations, leading global engineering organizations of 200+ engineers, and generating over $50M in new ARR."""
    return final_summary
''',
            encoding="utf-8",
        )

        violations = check_file_production_purity(prod_file, repo_root)
        assert len(violations) > 0, "Case A failed: hardcoded answer was not detected"
        assert any("final_summary" in v[1] or "predetermined" in v[2] for v in violations)


def test_case_b_renamed_hardcoded_answer_fails():
    """Case B: Renamed precomputed graph/result dictionary fails pre-commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        prod_file = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "engine.py"
        prod_file.parent.mkdir(parents=True, exist_ok=True)
        prod_file.write_text(
            '''
def synthesize_candidate_graph():
    result_payload = {
        "nodes": ["Skill:Python", "Role:VP_Eng", "Impact:Scale"],
        "edges": [("Skill:Python", "Role:VP_Eng")],
        "synthesis": "Demonstrated technical executive leadership scaling systems to millions of users.",
    }
    return result_payload
''',
            encoding="utf-8",
        )

        violations = check_file_production_purity(prod_file, repo_root)
        assert len(violations) > 0, "Case B failed: renamed precomputed dictionary was not detected"
        assert any("result_payload" in v[1] or "predetermined" in v[2] for v in violations)


def test_case_c_production_loads_golden_fixture_fails():
    """Case C: Production execution path loading golden fixture fails pre-commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        prod_file = repo_root / "scripts" / "export_pipeline.py"
        prod_file.parent.mkdir(parents=True, exist_ok=True)
        prod_file.write_text(
            '''
from pathlib import Path

def load_reference_data():
    golden_path = Path("data/eval/golden/verified_executive_summary.json")
    return golden_path.read_text()
''',
            encoding="utf-8",
        )

        violations = check_file_production_purity(prod_file, repo_root)
        assert len(violations) > 0, "Case C failed: production loading golden fixture was not detected"
        assert any("golden" in v[1] or "fixture" in v[2].lower() for v in violations)


def test_case_d_legitimate_test_uses_golden_fixture_passes():
    """Case D: Legitimate test importing or reading golden fixture passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        test_file = repo_root / "tests" / "unit" / "test_evaluation.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            '''
from pathlib import Path

def test_generated_output_against_golden():
    golden_path = Path("data/eval/golden/expected_summary.json")
    assert golden_path is not None
''',
            encoding="utf-8",
        )

        violations = check_file_production_purity(test_file, repo_root)
        assert len(violations) == 0, f"Case D failed: test file should be permitted to use fixtures, got {violations}"


def test_case_e_normal_declarative_manifest_passes():
    """Case E: Normal declarative manifest/config without canned answer passes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        config_file = repo_root / "config" / "pipeline_metadata.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            '''
{
  "pipeline_id": "apps_rg_pipeline_v1",
  "version": "1.0.0",
  "roster_hints": ["VP Engineering", "Staff Architect"],
  "glossary": {
    "AI": "Artificial Intelligence",
    "LLM": "Large Language Model"
  }
}
''',
            encoding="utf-8",
        )

        ok, msg = validate_file_against_schema(config_file, repo_root)
        assert ok, f"Case E failed: valid declarative metadata was rejected: {msg}"


def test_case_f_production_script_exceeding_budget_fails():
    """Case F: Production script exceeding budget without explicit exclusion fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        script_file = repo_root / "scripts" / "heavy_job.py"
        script_file.parent.mkdir(parents=True, exist_ok=True)
        # Generate 650 lines (exceeds default 600 line budget)
        lines = ["# Script line " + str(i) for i in range(650)]
        script_file.write_text("\n".join(lines), encoding="utf-8")

        passed, line_count, msg = check_file_budget(script_file, repo_root, max_lines=600, ratchet={})
        assert not passed, "Case F failed: script exceeding budget was not rejected"
        assert line_count == 650
        assert "VIOLATION" in msg
