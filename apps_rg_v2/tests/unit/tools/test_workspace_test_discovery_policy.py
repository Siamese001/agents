"""Regression coverage for the repository's manual-test workspace policy."""

from __future__ import annotations

import json
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SETTINGS_PATH = _REPOSITORY_ROOT / ".vscode" / "settings.json"


def test_workspace_disables_automatic_python_test_activity() -> None:
    """New branches must not cause editor-driven Python test work by default."""
    settings = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))

    assert settings["python.testing.autoTestDiscoverOnSaveEnabled"] is False
    assert settings["python.testing.pytestEnabled"] is False
    assert settings["python.testing.unittestEnabled"] is False
    assert settings["python.testing.promptToConfigure"] is False
