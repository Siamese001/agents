"""Unit tests verifying Wave 1 invariants: packaging normalization, subtree de-duplication, and configuration SSOT."""

from __future__ import annotations

import ast
from pathlib import Path
import yaml
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_canonical_package_resolution() -> None:
    """Ensure apps_research, apps_eval, apps_model_telemetry resolve solely from repository root."""
    import apps_eval
    import apps_model_telemetry
    import apps_research

    assert Path(apps_research.__file__).resolve().is_relative_to(REPO_ROOT / "apps_research")
    assert Path(apps_eval.__file__).resolve().is_relative_to(REPO_ROOT / "apps_eval")
    assert Path(apps_model_telemetry.__file__).resolve().is_relative_to(REPO_ROOT / "apps_model_telemetry")

    # Verify they do NOT resolve from resume_graph_engine/src
    assert not Path(apps_research.__file__).resolve().is_relative_to(REPO_ROOT / "resume_graph_engine" / "src")
    assert not Path(apps_eval.__file__).resolve().is_relative_to(REPO_ROOT / "resume_graph_engine" / "src")
    assert not Path(apps_model_telemetry.__file__).resolve().is_relative_to(REPO_ROOT / "resume_graph_engine" / "src")


def test_no_duplicate_subtrees_in_resume_graph_engine() -> None:
    """Ensure duplicate application trees in resume_graph_engine/src are completely removed."""
    rge_src = REPO_ROOT / "resume_graph_engine" / "src"

    assert not (rge_src / "apps_research").exists(), "resume_graph_engine/src/apps_research must not exist"
    assert not (rge_src / "apps_eval").exists(), "resume_graph_engine/src/apps_eval must not exist"
    assert not (rge_src / "apps_model_telemetry").exists(), "resume_graph_engine/src/apps_model_telemetry must not exist"


def test_entrypoints_do_not_contain_sys_path_insert() -> None:
    """Ensure entrypoints do not use sys.path.insert or sys.path.append hacks."""
    entrypoints = [
        REPO_ROOT / "resume_engine" / "__main__.py",
        REPO_ROOT / "outreach_engine" / "__main__.py",
        REPO_ROOT / "resume_graph_engine" / "__main__.py",
    ]

    for ep in entrypoints:
        tree = ast.parse(ep.read_text(encoding="utf-8"), filename=str(ep))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in ("insert", "append"):
                    val = func.value
                    if isinstance(val, ast.Attribute) and val.attr == "path":
                        if isinstance(val.value, ast.Name) and val.value.id == "sys":
                            pytest.fail(f"Found forbidden sys.path.{func.attr}() in {ep.name}:{node.lineno}")


def test_provider_profiles_ssot_exists_and_valid() -> None:
    """Ensure config/provider_profiles.yaml exists as the root SSOT and is valid YAML."""
    root_profiles = REPO_ROOT / "config" / "provider_profiles.yaml"
    apps_rg_profiles = REPO_ROOT / "resume_graph_engine" / "src" / "apps_rg" / "config" / "provider_profiles.yaml"

    assert root_profiles.is_file(), "config/provider_profiles.yaml must exist as root SSOT"
    assert apps_rg_profiles.is_file(), "resume_graph_engine/src/apps_rg/config/provider_profiles.yaml must exist"

    root_data = yaml.safe_load(root_profiles.read_text(encoding="utf-8"))
    apps_rg_data = yaml.safe_load(apps_rg_profiles.read_text(encoding="utf-8"))

    assert isinstance(root_data, dict)
    assert "profiles" in root_data
    assert root_data["profiles"] == apps_rg_data["profiles"], "Root SSOT profiles must match apps_rg profiles"


def test_ratchet_has_no_dead_duplicate_entries() -> None:
    """Ensure file_budgets_ratchet.json does not retain dead duplicate subtree paths."""
    import json

    ratchet_path = REPO_ROOT / "config" / "governance" / "file_budgets_ratchet.json"
    ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))

    for key in ratchet.keys():
        assert not key.startswith("resume_graph_engine/src/apps_research/"), f"Dead key found in ratchet: {key}"
        assert not key.startswith("resume_graph_engine/src/apps_eval/"), f"Dead key found in ratchet: {key}"
        assert not key.startswith("resume_graph_engine/src/apps_model_telemetry/"), f"Dead key found in ratchet: {key}"
