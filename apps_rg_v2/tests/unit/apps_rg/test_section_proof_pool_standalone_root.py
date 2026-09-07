"""Standalone-layout protection for canonical section proof resolution."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.proof_pool_resolver import _canonical_section_repo_root


def test_standalone_src_package_root_normalizes_to_checkout_root() -> None:
    checkout = Path(__file__).resolve().parents[3]
    assert (checkout / "src" / "apps_rg" / "__init__.py").is_file()

    assert _canonical_section_repo_root(checkout / "src") == checkout


def test_non_package_test_root_is_preserved() -> None:
    arbitrary_root = Path("C:/temporary/apps-rg-test-root")
    assert _canonical_section_repo_root(arbitrary_root) == arbitrary_root.resolve()
