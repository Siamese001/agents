from __future__ import annotations

from pathlib import Path

from apps_eval.resources import resolve_apps_eval_resource


def test_logical_apps_eval_path_resolves_below_package() -> None:
    resolved = resolve_apps_eval_resource("apps_eval/fixtures/dev/apps_rg")

    assert resolved == Path(__file__).resolve().parents[1] / "fixtures" / "dev" / "apps_rg"


def test_absolute_caller_path_passes_through(tmp_path: Path) -> None:
    assert resolve_apps_eval_resource(tmp_path) == tmp_path
