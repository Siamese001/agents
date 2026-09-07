from __future__ import annotations

from pathlib import Path

import apps_eval
import apps_research
import apps_rg
import tools


def test_owned_packages_resolve_inside_this_checkout() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    expected_source_root = (repo_root / "src").resolve()

    for package in (apps_eval, apps_research, apps_rg):
        package_file = Path(package.__file__).resolve()
        assert package_file.is_relative_to(expected_source_root), package_file

    tools_file = Path(tools.__file__).resolve()
    assert tools_file.is_relative_to((repo_root / "tools").resolve()), tools_file
