"""P0 model-pin ownership and forbidden-runtime regression gates."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import yaml

from apps_rg.runtime.judges import executive_summary_x1d
from apps_rg.runtime.model_pin_ownership import (
    MODEL_CATALOG_PATH,
    PROVIDER_PROFILES_PATH,
    assert_model_pin_ownership,
    build_active_model_manifest,
)
from apps_rg.runtime.section_judge_policy import REQUIRED_JUDGE_PROVIDER_KEYS

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODEL_LITERAL_CONTRACT_TESTS = {
    "tests/unit/apps_research/test_model_pin_governance.py",
    "tests/unit/apps_rg/test_judge_models_ssot.py",
    "tests/unit/apps_rg/test_model_capabilities.py",
    "tests/unit/apps_rg/test_model_pin_ownership.py",
    "tests/unit/apps_rg/test_provider_gateway_wave10.py",
    "tests/unit/apps_rg/test_section_judge_policy.py",
    "tests/unit/apps_rg/test_section_model_limits_ssot.py",
    "tests/unit/apps_rg/test_section_model_ssot_resolver.py",
}


def test_model_pin_ownership_contract_passes() -> None:
    assert_model_pin_ownership()


def test_proof_registry_is_gemini_and_openai_only() -> None:
    assert set(executive_summary_x1d.PROVIDERS) == set(REQUIRED_JUDGE_PROVIDER_KEYS)
    assert set(REQUIRED_JUDGE_PROVIDER_KEYS) == {"gemini_pro", "openai_chatgpt"}


def test_claude_transport_cannot_execute_as_proof_judge() -> None:
    source_path = Path(executive_summary_x1d.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_call_anthropic"
    ]
    assert calls == []
    assert "anthropic_claude" not in executive_summary_x1d.PROVIDERS


def test_claude_selectors_remain_separate_from_proof_judges() -> None:
    data = yaml.safe_load(PROVIDER_PROFILES_PATH.read_text(encoding="utf-8"))
    selectors = data["selector_models"]
    for selector_role in (
        "competencies_graph_pool_selector",
        "employment_bullet_pool_selector",
    ):
        selector = selectors[selector_role]
        assert selector["provider_key"] == "anthropic_claude"
        assert selector["model"] == "claude-sonnet-5"
        assert selector["role"] == "advisory_selector"
        assert selector["review_after"] == "2026-11-07"
        assert selector["proof_eligible"] is False
    assert selectors["competencies_graph_pool_selector"]["reasoning_effort"] == "low"
    assert selectors["competencies_graph_pool_selector"]["owner"] == (
        "apps_rg.competencies_graph_pool"
    )
    assert selectors["employment_bullet_pool_selector"]["owner"] == (
        "apps_rg.employment_bullet_pool"
    )
    assert all("anthropic_claude" not in models for models in data["judge_models"].values())


def test_active_manifest_includes_governed_selectors_and_apps_research() -> None:
    manifest = build_active_model_manifest()
    by_role = {(row["app_id"], row["role_type"], row["role_id"]): row for row in manifest}
    competency_selector = by_role[
        ("apps_rg", "advisory_selector", "competencies_graph_pool_selector")
    ]
    assert competency_selector["provider_key"] == "anthropic_claude"
    assert competency_selector["model"] == "claude-sonnet-5"
    assert competency_selector["effort"] == "low"
    assert competency_selector["owner"] == "apps_rg.competencies_graph_pool"
    assert competency_selector["proof_eligible"] is False
    competency_selector_backup = by_role[
        (
            "apps_rg",
            "advisory_selector_backup",
            "anthropic_limit.competencies_graph_pool_selector",
        )
    ]
    assert competency_selector_backup["provider_key"] == "openai_chatgpt"
    assert competency_selector_backup["proof_eligible"] is False
    competencies_generator_backup = by_role[
        ("apps_rg", "generator_backup", "anthropic_limit.competencies")
    ]
    assert competencies_generator_backup["provider_key"] == "external_openai"
    assert competencies_generator_backup["proof_eligible"] is False
    assert (
        "apps_research",
        "generator",
        "company_brief_generation",
    ) in by_role
    research_generator = by_role[
        ("apps_research", "generator", "company_brief_generation")
    ]
    assert research_generator["model"] == "gpt-5.6-terra"
    assert research_generator["effort"] == "medium"
    assert (
        "apps_research",
        "proof_judge",
        "apps_rg_handoff_judge",
    ) in by_role
    gemini_rows = [
        row for row in manifest if row["provider_key"] == "gemini_pro"
    ]
    assert {row["role_id"] for row in gemini_rows} == {
        "enhanced.gemini_pro",
        "standard.gemini_pro",
        "apps_rg_handoff_judge",
    }
    assert all(row["model"] == "gemini-3.6-flash" for row in gemini_rows)
    assert all(row["effort"] == "high" for row in gemini_rows)


def test_every_active_openai_pin_is_in_the_gpt_56_family() -> None:
    openai_rows = [
        row
        for row in build_active_model_manifest()
        if row["provider_key"] in {"external_openai", "openai_chatgpt"}
    ]
    assert openai_rows
    assert all(str(row["model"]).startswith("gpt-5.6-") for row in openai_rows)


def test_shared_catalog_has_capabilities_not_role_aliases() -> None:
    catalog = json.loads(MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
    assert catalog["catalog_role"] == "capability_metadata_only"
    assert catalog["routing_allowed"] is False
    assert not {"openai", "anthropic", "gemini"}.intersection(catalog)
    assert catalog["compatibility_policy"]["generic_role_aliases_allowed"] is False
    assert catalog["models"]["gpt-5.6-sol"]["provider"] == "openai"


def test_removed_local_generator_has_zero_executable_code_matches() -> None:
    """Do not let opaque, immutable runtime evidence masquerade as code.

    Historical provider payloads are intentionally retained beneath
    ``artifacts/`` and can contain arbitrary model-generated text.  The
    regression gate is about executable Python paths, so scanning the whole
    repository turns an unrelated saved response into a false code failure.
    """
    forbidden_terms = ("q" + "wen", "local_" + "generator_stub")
    for term in forbidden_terms:
        result = subprocess.run(
            [
                "rg",
                "-n",
                "-i",
                term,
                str(_REPO_ROOT / "src"),
                str(_REPO_ROOT / "tools"),
                str(_REPO_ROOT / "tests"),
                "--glob",
                "*.py",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 1, result.stdout


def test_dead_hops_direct_sdk_client_is_absent() -> None:
    assert not (_REPO_ROOT / "src/apps_rg/integrations/hops/_llm_client.py").exists()


def test_active_model_literals_are_confined_to_ssot_contract_tests() -> None:
    catalog = json.loads(MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
    active_literals = {
        str(row["model"])
        for row in build_active_model_manifest()
        if str(row.get("model") or "") in catalog["models"]
    }
    violations: list[str] = []
    for path in (_REPO_ROOT / "tests").rglob("*.py"):
        rel = path.relative_to(_REPO_ROOT).as_posix()
        if rel in _MODEL_LITERAL_CONTRACT_TESTS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            matches = sorted(model for model in active_literals if model in node.value)
            if matches:
                violations.append(f"{rel}:{node.lineno}:{','.join(matches)}")
    assert violations == []
