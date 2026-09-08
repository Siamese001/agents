"""apps-test-model: HARNESS.

Contract tests for the apps_rg app-level agent guidance.
"""

from __future__ import annotations

from pathlib import Path

from apps_rg.repository_layout import apps_rg_package_root, repository_root

REPO_ROOT = repository_root(Path(__file__))
APPS_RG_ROOT = apps_rg_package_root(REPO_ROOT)


def test_apps_rg_agent_contract_is_codex_owned() -> None:
    agents = APPS_RG_ROOT / "AGENTS.md"
    legacy_agent_file = APPS_RG_ROOT / ("CLAUDE" + ".md")

    assert agents.is_file(), "apps_rg/AGENTS.md must exist"
    assert not legacy_agent_file.exists(), "legacy app-agent guidance should be removed"

    agents_text = agents.read_text(encoding="utf-8")

    assert legacy_agent_file.name not in agents_text
    assert "AGENTIC_SPINE.md" in agents_text
    assert "LEAN_CORE.md" in agents_text
    assert "AGENTS.md" in agents_text
