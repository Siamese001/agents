"""Materialize app-owned data into an isolated repository-shaped test root."""

from __future__ import annotations

import shutil
from pathlib import Path

from apps_rg.repository_layout import apps_rg_package_root, repository_root


def materialize_standalone_repo_view(tmp_path: Path) -> Path:
    """Copy only runtime-read data needed by modular tests into ``tmp_path``."""

    source = apps_rg_package_root(repository_root())
    target = tmp_path / "repo"
    package = target / "apps_rg"
    for relative in (Path("fact_inventory"), Path("resume/base"), Path("config")):
        shutil.copytree(source / relative, package / relative, dirs_exist_ok=True)
    return target


__all__ = ["materialize_standalone_repo_view"]
