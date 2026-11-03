"""Unit tests for Wave 2: Full-Repository SSOT, Pytest Timeouts, and Subsystem Boundaries."""

from __future__ import annotations

from pathlib import Path

from tools.lint_architecture_boundaries import run_architecture_linter
from tools.lint_file_budgets import PRODUCTION_DIRECTORIES as BUDGET_PROD_DIRS
from tools.lint_layer_imports import PRODUCTION_DIRECTORIES as LAYER_PROD_DIRS
from tools.lint_production_purity import PRODUCTION_DIRECTORIES as PURITY_PROD_DIRS
from tools.ssot_boundary_auditor import (
    SUBPROCESS_SCAN_DIRS,
    SUBSYSTEM_TARGETS,
    audit_constitutional_ast_floor,
    run_ssot_boundary_audit,
)
from tools.ssot_hardcoding_scanner import scan_ast_hygiene_and_env_sprawl
from tools.ssot_sprawl_scanner import (
    scan_intra_file_contradictions,
    scan_shadow_config_drift,
    scan_twin_profile_sprawl,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ALL_11_EXECUTABLE_ROOTS = {
    "agents",
    "apps_eval",
    "apps_model_telemetry",
    "apps_research",
    "infrastructure",
    "ops_scripts",
    "outreach_engine",
    "resume_engine",
    "resume_graph_engine",
    "scripts",
    "tools",
}


def test_all_11_executable_roots_covered_across_boundary_and_budget_linters() -> None:
    assert set(SUBPROCESS_SCAN_DIRS) == ALL_11_EXECUTABLE_ROOTS
    assert set(SUBSYSTEM_TARGETS) == ALL_11_EXECUTABLE_ROOTS - {"tools"}
    assert set(BUDGET_PROD_DIRS) == ALL_11_EXECUTABLE_ROOTS
    assert set(LAYER_PROD_DIRS) == ALL_11_EXECUTABLE_ROOTS
    assert set(PURITY_PROD_DIRS) == ALL_11_EXECUTABLE_ROOTS - {"apps_eval"}


def test_outreach_pytest_ini_enforces_180s_timeout_and_negative_fixture_fails(tmp_path: Path) -> None:
    outreach_ini = (REPO_ROOT / "outreach_engine" / "pytest.ini").read_text(encoding="utf-8")
    assert "--timeout=180" in outreach_ini
    assert scan_shadow_config_drift(REPO_ROOT) == []

    # Negative fixture: nested outreach_engine/pytest.ini missing --timeout=180 must fail closed
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -v --timeout=180\n", encoding="utf-8")
    sub = tmp_path / "outreach_engine"
    sub.mkdir(parents=True)
    (sub / "pytest.ini").write_text("[pytest]\naddopts = -v --tb=short\n", encoding="utf-8")

    findings = scan_shadow_config_drift(tmp_path)
    assert any(
        f["category"] == "SHADOW_PYTEST_DRIFT" and f["shadow"] == "outreach_engine/pytest.ini"
        for f in findings
    )


def test_sprawl_scanner_covers_outreach_and_resume_engine_configs_and_data(tmp_path: Path) -> None:
    outreach_cfg = tmp_path / "outreach_engine" / "config"
    outreach_data = tmp_path / "outreach_engine" / "data"
    resume_cfg = tmp_path / "resume_graph_engine" / "config"
    for d in (outreach_cfg, outreach_data, resume_cfg):
        d.mkdir(parents=True)

    (outreach_cfg / "bad_bounds.yaml").write_text("bounds:\n  min_words: 200\n  max_words: 50\n", encoding="utf-8")
    (outreach_data / "bad_holdout.json").write_text('{"minimum": 10, "maximum": 3}', encoding="utf-8")
    (resume_cfg / "profile.yaml").write_text("version: 1\n", encoding="utf-8")
    (resume_cfg / "profile.v1.yaml").write_text("version: 1\n", encoding="utf-8")

    contradictions = scan_intra_file_contradictions(tmp_path)
    contr_files = {c["file"] for c in contradictions}
    assert "outreach_engine/config/bad_bounds.yaml" in contr_files
    assert "outreach_engine/data/bad_holdout.json" in contr_files

    twins = scan_twin_profile_sprawl(tmp_path)
    assert any(t["variant_file"] == "resume_graph_engine/config/profile.v1.yaml" for t in twins)


def test_constitutional_ast_floor_catches_silent_except_in_tools_and_scripts(tmp_path: Path) -> None:
    for rel in ("tools/bad_tool.py", "scripts/bad_script.py"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("try:\n    x = 1\nexcept Exception:\n    pass\n", encoding="utf-8")

    res = audit_constitutional_ast_floor(tmp_path)
    flagged = "\n".join(res["unguarded_exceptions"])
    assert "tools/bad_tool.py" in flagged
    assert "scripts/bad_script.py" in flagged


def test_env_sprawl_catches_new_outreach_or_ratchet_exceeding_env_lookups(tmp_path: Path) -> None:
    gov = tmp_path / "config" / "governance"
    gov.mkdir(parents=True)
    (gov / "env_lookup_ratchet.json").write_text(
        '{"schema_version": "1.0.0", "file_counts": {"apps_research/legacy.py": 1}}',
        encoding="utf-8",
    )
    leg = tmp_path / "apps_research" / "legacy.py"
    leg.parent.mkdir(parents=True)
    leg.write_text("import os\na = os.getenv('A')\n", encoding="utf-8")
    assert scan_ast_hygiene_and_env_sprawl(tmp_path) == []

    # Exceeding ratchet ceiling or introducing rogue outreach lookup fails closed
    leg.write_text("import os\na = os.getenv('A')\nb = os.getenv('B')\n", encoding="utf-8")
    rogue = tmp_path / "outreach_engine" / "src" / "apps_lic" / "rogue.py"
    rogue.parent.mkdir(parents=True)
    rogue.write_text("import os\nx = os.environ.get('X')\n", encoding="utf-8")

    findings = scan_ast_hygiene_and_env_sprawl(tmp_path)
    flagged_files = {f["file"] for f in findings if f["category"] == "UNCENTRALIZED_ENV_LOOKUP"}
    assert "apps_research/legacy.py" in flagged_files
    assert "outreach_engine/src/apps_lic/rogue.py" in flagged_files


def test_live_repository_passes_all_10_ssot_and_boundary_dimensions(tmp_path: Path) -> None:
    empty_sidecars = tmp_path / "sidecars"
    empty_sidecars.mkdir()
    arch = run_architecture_linter(REPO_ROOT)
    assert arch["is_clean"] is True, arch

    report = run_ssot_boundary_audit(repo_root=REPO_ROOT, sidecars_root=empty_sidecars)
    assert report["is_clean"] is True, report["dimension_status"]
    for dim_key, dim_val in report["dimension_status"].items():
        assert dim_val == "PASS", f"{dim_key} failed: {report}"
