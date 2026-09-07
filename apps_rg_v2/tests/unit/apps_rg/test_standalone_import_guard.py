from __future__ import annotations

from pathlib import Path

from apps_standalone_import_guard import verify_local_apps_rg_source


def test_source_guard_accepts_a_checkout_with_the_local_application_package(
    tmp_path: Path,
) -> None:
    package = tmp_path / "src" / "apps_rg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("\n", encoding="utf-8")

    assert verify_local_apps_rg_source(repository_root=tmp_path) is True


def test_source_guard_rejects_a_checkout_without_the_application_package(
    tmp_path: Path,
) -> None:
    assert verify_local_apps_rg_source(repository_root=tmp_path) is False


def test_source_guard_requires_an_init_module_not_only_a_directory(tmp_path: Path) -> None:
    (tmp_path / "src" / "apps_rg").mkdir(parents=True)

    assert verify_local_apps_rg_source(repository_root=tmp_path) is False
