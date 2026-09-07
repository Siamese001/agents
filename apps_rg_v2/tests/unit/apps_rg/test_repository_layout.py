from __future__ import annotations

from pathlib import Path

from apps_rg.repository_layout import (
    apps_rg_package_root,
    repository_root,
    resolve_apps_rg_path,
    resolve_repository_path,
)


def _package(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "__init__.py").write_text("", encoding="utf-8")
    return path


def test_package_root_resolves_monorepo_layout(tmp_path: Path) -> None:
    package_root = _package(tmp_path / "apps_rg")

    assert apps_rg_package_root(tmp_path) == package_root


def test_package_root_resolves_standalone_src_layout(tmp_path: Path) -> None:
    package_root = _package(tmp_path / "src" / "apps_rg")

    assert apps_rg_package_root(tmp_path) == package_root
    assert apps_rg_package_root(tmp_path / "src") == package_root
    assert apps_rg_package_root(package_root) == package_root


def test_resolve_apps_rg_path_appends_package_relative_parts(tmp_path: Path) -> None:
    package_root = _package(tmp_path / "src" / "apps_rg")

    assert resolve_apps_rg_path(tmp_path, "fact_inventory", "graph.json") == (
        package_root / "fact_inventory" / "graph.json"
    )


def test_resolve_repository_path_translates_logical_apps_rg_ref(tmp_path: Path) -> None:
    package_root = _package(tmp_path / "src" / "apps_rg")

    assert resolve_repository_path(tmp_path, "apps_rg/config/profile.yaml") == (
        package_root / "config" / "profile.yaml"
    )


def test_resolve_repository_path_preserves_other_relative_refs(tmp_path: Path) -> None:
    assert resolve_repository_path(tmp_path, "tests/fixture.json") == (
        tmp_path / "tests" / "fixture.json"
    )


def test_partial_monorepo_tree_does_not_shadow_standalone_package(
    tmp_path: Path,
) -> None:
    (tmp_path / "apps_rg" / "runtime").mkdir(parents=True)
    package_root = _package(tmp_path / "src" / "apps_rg")

    assert apps_rg_package_root(tmp_path) == package_root


def test_standalone_source_package_wins_when_both_shapes_exist(tmp_path: Path) -> None:
    _package(tmp_path / "apps_rg")
    standalone_package = _package(tmp_path / "src" / "apps_rg")

    assert apps_rg_package_root(tmp_path) == standalone_package


def test_repository_root_resolves_standalone_layout(tmp_path: Path) -> None:
    package_root = _package(tmp_path / "src" / "apps_rg")

    assert repository_root(package_root / "runtime") == tmp_path


def test_repository_root_resolves_monorepo_layout(tmp_path: Path) -> None:
    package_root = _package(tmp_path / "apps_rg")

    assert repository_root(package_root) == tmp_path


def test_missing_layout_preserves_historical_fail_closed_path(tmp_path: Path) -> None:
    assert apps_rg_package_root(tmp_path) == tmp_path / "apps_rg"
