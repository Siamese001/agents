from __future__ import annotations

from pathlib import Path

import pytest

from apps_rg.fact_inventory.augmented_skills_graph import (
    default_augmented_skills_graph_path,
)
from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    default_graph_sqlite_path,
)
from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    default_arsenal_ledger_path,
)
from apps_rg.repository_layout import repository_root


def test_graph_defaults_resolve_source_and_artifact_roots_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPS_RG_AUGMENTED_SKILLS_GRAPH_SQLITE_PATH", raising=False)
    repo = repository_root(Path(__file__))

    expected_ledger = (
        repo / "src" / "apps_rg" / "fact_inventory" / "master_skills_arsenal_ledger.json"
    )
    assert default_augmented_skills_graph_path() == expected_ledger
    assert default_arsenal_ledger_path() == expected_ledger
    assert default_graph_sqlite_path() == (
        repo / "artifacts" / "apps_rg" / "fact_inventory" / "augmented_skills_graph.sqlite"
    )
