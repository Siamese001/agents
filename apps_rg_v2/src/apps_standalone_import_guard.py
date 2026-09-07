"""Validate the local Apps RG source layout used by standalone entry points."""

from __future__ import annotations

from pathlib import Path


def verify_local_apps_rg_source(*, repository_root: Path | None = None) -> bool:
    """Return whether this checkout contains the application package source."""

    root = (repository_root or Path(__file__).resolve().parent.parent).resolve()
    return (root / "src" / "apps_rg" / "__init__.py").is_file()


__all__ = ["verify_local_apps_rg_source"]
