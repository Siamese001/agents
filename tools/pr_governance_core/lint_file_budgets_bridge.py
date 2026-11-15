"""Helper bridge for clamping file budget ratchets during merge-train assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def clamp_ratchet_if_available(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Tighten grandfathered file budget ratchets downward if any file shrank."""
    try:
        from tools.lint_file_budgets import clamp_ratchet_to_current_lines

        return clamp_ratchet_to_current_lines(repo_root, write=True)
    except Exception:  # guardian: allow-silent-swallow -- optional bridge in minimal test fixtures
        return {}
