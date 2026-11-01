"""Regression suite for SVP / Frontier Lab Executive Public Repository Positioning."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

EXECUTIVE_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "EXECUTIVE_OVERVIEW.md",
    REPO_ROOT / "docs" / "RECRUITER_GUIDE.md",
    REPO_ROOT / "docs" / "RUNTIME_CONTROL_PLANE.md",
    REPO_ROOT / "docs" / "SVP_ENGINEERING_GOVERNANCE_README.md",
    REPO_ROOT / "docs" / "THOUGHT_LEADERSHIP_INDEX.md",
    REPO_ROOT / "docs" / "architecture" / "REVIEWER_GUIDE.md",
    REPO_ROOT / "docs" / "architecture" / "architecture-proof-pack.md",
)

RETIRED_SCRIPT_PATTERNS = (
    "scripts/governance/verify_codex_primary.py",
    "scripts/governance/verify_codex_enforcement_home.py",
    "ops_scripts/ci/run_architecture_proof.py",
    "ops_scripts/ci/check_governed_app_conformance.py",
    "apps_shared/integrations/app_registry.py",
)

PURGED_CLUTTER_PATHS = (
    REPO_ROOT / "implementation_plan.md",
    REPO_ROOT / "docs" / "chatgpt-project-instructions.md",
    REPO_ROOT / "docs" / "codex-primary-execution.md",
    REPO_ROOT / "docs" / "cursor",
    REPO_ROOT / "docs" / "wave_e",
    REPO_ROOT / "docs" / "wave_g",
    REPO_ROOT / "docs" / "wave_h",
    REPO_ROOT / "docs" / "wave_i",
)


def test_readme_leads_with_economics_and_subordinates_reference_workloads() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Verified Platform Economics & Production Benchmarks" in text
    assert "### Core Platform Substrates" in text
    assert "### Reference Enterprise Workloads" in text
    assert "Verified Document & Dossier Synthesis" in text
    assert "Policy-Gated External Messaging" in text
    assert "python tools/cost_token_budget_auditor.py" in text
    assert "cd resume_graph_engine" not in text


def test_recruiter_guide_is_operating_model_whitepaper_without_role_solicitation() -> None:
    text = (REPO_ROOT / "docs" / "RECRUITER_GUIDE.md").read_text(encoding="utf-8")
    assert "# Operating Model & Reliability Economics" in text
    assert "## Roles this supports" not in text
    assert "Chief AI Officer" not in text
    assert "python tools/cost_token_budget_auditor.py" in text


def test_workload_readmes_positioned_as_enterprise_reference_workloads() -> None:
    outreach_readme = (REPO_ROOT / "outreach_engine" / "README.md").read_text(encoding="utf-8")
    resume_readme = (REPO_ROOT / "resume_graph_engine" / "README.md").read_text(encoding="utf-8")

    assert "Reference Enterprise Workload" in outreach_readme
    assert "Policy-Gated External Communications Engine" in outreach_readme
    assert "Reference Enterprise Workload" in resume_readme
    assert "Verified Document & Dossier Synthesis Engine" in resume_readme


def test_executive_docs_contain_no_retired_codex_or_missing_script_references() -> None:
    for doc_path in EXECUTIVE_DOCS:
        assert doc_path.is_file(), f"Missing executive doc: {doc_path}"
        text = doc_path.read_text(encoding="utf-8")
        for retired in RETIRED_SCRIPT_PATTERNS:
            assert retired not in text, f"{doc_path.name} still references retired path: {retired}"
        assert "Codex-primary" not in text, f"{doc_path.name} still claims Codex-primary governance"
        assert ".codex is the active" not in text, f"{doc_path.name} still claims .codex is active"


def test_all_python_script_paths_in_executive_docs_exist_on_disk() -> None:
    script_regex = re.compile(r"python(?:3)?\s+((?:tools|ops_scripts|scripts)/[A-Za-z0-9_./\-]+\.py)")
    for doc_path in EXECUTIVE_DOCS:
        text = doc_path.read_text(encoding="utf-8")
        for match in script_regex.finditer(text):
            rel_script = match.group(1)
            target = REPO_ROOT / rel_script
            assert target.is_file(), f"{doc_path.name} references non-existent script: {rel_script}"


def test_public_clutter_files_and_wave_folders_are_absent() -> None:
    for clutter_path in PURGED_CLUTTER_PATHS:
        assert not clutter_path.exists(), f"Public clutter path still exists: {clutter_path}"
