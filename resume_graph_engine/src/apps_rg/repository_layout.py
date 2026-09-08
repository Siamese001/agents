"""Resolve app-owned files in monorepo and standalone source layouts."""

from __future__ import annotations

from pathlib import Path


def repository_root(start: Path | None = None) -> Path:
    """Return the checkout root for either monorepo or standalone layouts."""

    current = Path(start) if start is not None else Path(__file__)
    current = current.resolve()
    if current.is_file():
        current = current.parent

    monorepo_fallback: Path | None = None
    for candidate in (current, *current.parents):
        standalone_package = candidate / "src" / "apps_rg" / "__init__.py"
        monorepo_package = candidate / "apps_rg" / "__init__.py"
        if standalone_package.is_file():
            return candidate
        if monorepo_package.is_file():
            if (candidate / ".git").exists():
                return candidate
            if monorepo_fallback is None:
                monorepo_fallback = candidate

    if monorepo_fallback is not None:
        return monorepo_fallback

    raise FileNotFoundError(f"could not locate repository root from {current}")


def apps_rg_package_root(repo_root: Path | None = None) -> Path:
    """Return the filesystem root of the ``apps_rg`` package.

    The production monorepo stores the package at ``apps_rg`` while the
    standalone repository uses the conventional ``src/apps_rg`` layout.  A
    caller may also pass the standalone ``src`` directory directly.
    """

    if repo_root is None:
        return Path(__file__).resolve().parent

    root = Path(repo_root)
    if root.name == "apps_rg" and (root / "__init__.py").is_file():
        return root

    candidates = (
        (root / "apps_rg",)
        if root.name == "src"
        else (root / "src" / "apps_rg", root / "apps_rg")
    )
    for candidate in candidates:
        if (candidate / "__init__.py").is_file():
            return candidate

    # Preserve the historical monorepo-shaped error path when the repository
    # itself is missing or malformed; callers will then fail closed on access.
    return root / "apps_rg"


def resolve_apps_rg_path(repo_root: Path | None, *parts: str) -> Path:
    """Resolve ``parts`` beneath the package root for the active layout."""

    return apps_rg_package_root(repo_root).joinpath(*parts)


def resolve_repository_path(repo_root: Path, ref: str | Path) -> Path:
    """Resolve a repository-relative reference across supported layouts.

    Contract and receipt payloads retain their historical ``apps_rg/...``
    logical references.  The standalone checkout stores that package beneath
    ``src``, so filesystem consumers must translate only that leading package
    segment while leaving every other repository-relative reference intact.
    """

    path = Path(ref)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "apps_rg":
        return resolve_apps_rg_path(repo_root, *path.parts[1:])
    return Path(repo_root) / path
