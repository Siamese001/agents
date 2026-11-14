"""Unit tests verifying Wave 2 package/facade awareness across governance auditors."""

from __future__ import annotations

import textwrap
from pathlib import Path

from tools.cost_token_budget_probes import (
    load_repo_module,
    verify_ast_compact_json_surface,
)
from tools.lint_model_neutral_naming import check_path_model_neutrality, is_path_exempt
from tools.retrieval_surface_auditor import (
    _require_module,
    scan_untyped_public_retrieval_callables,
)
from tools.testing_gaps_auditor import run_testing_gaps_audit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


def test_testing_gaps_credits_pure_importfrom_facades(tmp_path: Path) -> None:
    _write(
        tmp_path / "agents" / "pkg" / "impl.py",
        '''
        def compute_answer(x: int) -> int:
            return x + 1
        ''',
    )
    _write(
        tmp_path / "agents" / "pkg" / "__init__.py",
        '''
        """Package re-export facade."""

        from agents.pkg.impl import compute_answer

        __all__ = ["compute_answer"]
        ''',
    )
    _write(
        tmp_path / "agents" / "thin_facade.py",
        '''
        """Legacy flat module re-export facade."""

        from agents.pkg.impl import compute_answer

        __all__ = ["compute_answer"]
        ''',
    )
    _write(
        tmp_path / "tests" / "unit" / "test_impl.py",
        '''
        from agents.pkg.impl import compute_answer

        def test_compute_answer() -> None:
            assert compute_answer(4) == 5
        ''',
    )

    clean_report = run_testing_gaps_audit(tmp_path, include_uncovered_backlog=True)
    agents_cov = clean_report["package_coverage"]["agents"]
    assert agents_cov["uncovered_module_count"] == 0, agents_cov
    assert clean_report["uncovered_backlog"]["total_uncovered_modules"] == 0

    _write(
        tmp_path / "agents" / "untested_sub.py",
        '''
        def orphan_helper(v: int) -> int:
            return v * 2
        ''',
    )
    _write(
        tmp_path / "agents" / "broken_facade.py",
        '''
        from agents.untested_sub import orphan_helper

        __all__ = ["orphan_helper"]
        ''',
    )
    dirty_report = run_testing_gaps_audit(tmp_path, include_uncovered_backlog=True)
    assert dirty_report["package_coverage"]["agents"]["uncovered_module_count"] == 1
    assert dirty_report["uncovered_backlog"]["total_uncovered_modules"] == 1


def test_cost_token_budget_probes_loads_and_traverses_converted_package(tmp_path: Path) -> None:
    pkg = tmp_path / "probe_pkg_ok"
    _write(pkg / "__init__.py", "from .serializer import serialize_compact\n__all__ = ['serialize_compact']\n")
    _write(
        pkg / "serializer.py",
        '''
        import json

        def serialize_compact(data: dict[str, int]) -> str:
            return json.dumps(data, sort_keys=True, separators=(",", ":"))
        ''',
    )
    entry = _write(
        tmp_path / "probe_facade.py",
        '''
        from probe_pkg_ok.serializer import serialize_compact

        __all__ = ["serialize_compact"]
        ''',
    )

    mod, err = load_repo_module(tmp_path, "probe_pkg_ok.py")
    assert err is None and mod is not None
    assert mod.serialize_compact({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert verify_ast_compact_json_surface(tmp_path / "probe_pkg_ok.py") == []
    assert verify_ast_compact_json_surface(entry) == []

    bad_pkg = tmp_path / "probe_pkg_bad"
    _write(bad_pkg / "__init__.py", "from .serializer import serialize_loose\n")
    _write(
        bad_pkg / "serializer.py",
        '''
        import json

        def serialize_loose(data: dict[str, int]) -> str:
            return json.dumps(data, indent=2)
        ''',
    )
    gaps = verify_ast_compact_json_surface(tmp_path / "probe_pkg_bad.py")
    assert gaps and any("separators" in g for g in gaps)


def test_retrieval_surface_auditor_facade_helpers_and_submodule_probes(tmp_path: Path) -> None:
    facade_dir = tmp_path / "apps_research" / "factored_ret"
    _write(
        facade_dir / "helpers.py",
        '''
        def internal_normalize(text):
            return text.strip().lower()

        def reexported_typed(text):
            return text.upper()
        ''',
    )
    _write(
        facade_dir / "__init__.py",
        '''
        from typing import Callable
        from .helpers import internal_normalize, reexported_typed

        reexported_typed: Callable[[str], str]

        def run_query(q: str) -> str:
            return internal_normalize(q)

        __all__ = ["run_query", "reexported_typed"]
        ''',
    )
    assert scan_untyped_public_retrieval_callables(tmp_path) == []

    _write(
        tmp_path / "apps_research" / "integrations" / "rogue_untyped.py",
        '''
        def rogue_helper(x):
            return x
        ''',
    )
    rogue_findings = scan_untyped_public_retrieval_callables(tmp_path)
    assert [f["callable"] for f in rogue_findings] == ["rogue_helper"]

    # Ensure untyped export inside __all__ still fails closed.
    _write(
        facade_dir / "__init__.py",
        '''
        from .helpers import internal_normalize

        __all__ = ["internal_normalize"]
        ''',
    )
    exported_untyped = scan_untyped_public_retrieval_callables(tmp_path)
    assert any(f["callable"] == "internal_normalize" for f in exported_untyped)

    probe_pkg = tmp_path / "ret_probe_pkg" / "surface"
    _write(probe_pkg / "__init__.py", "from .public import api_fn\n")
    _write(probe_pkg / "public.py", "def api_fn() -> str:\n    return 'api'\n")
    _write(probe_pkg / "internal_probe.py", "def sub_probe_fn() -> str:\n    return 'sub'\n")

    loaded = _require_module(tmp_path, "ret_probe_pkg/surface.py")
    assert loaded.api_fn() == "api"
    assert loaded.sub_probe_fn() == "sub"


def test_model_neutral_naming_package_submodules_inherit_exemptions(tmp_path: Path) -> None:
    sub = _write(tmp_path / "tools" / "run_luna_pkg" / "sub.py", "def ok() -> int:\n    return 1\n")
    cat = _write(tmp_path / "config" / "core_model_catalog" / "tiers.py", "TIERS = {}\n")
    bad = _write(tmp_path / "tools" / "run_luna_pkg" / "gpt4_extra.py", "def no() -> int:\n    return 0\n")

    assert is_path_exempt("tools/run_luna_pkg/sub.py")
    assert check_path_model_neutrality(sub, tmp_path) == []
    assert check_path_model_neutrality(cat, tmp_path) == []
    assert check_path_model_neutrality(bad, tmp_path)
