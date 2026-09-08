from __future__ import annotations

import ast
import json
from pathlib import Path

from apps_rg.runtime.core_import_boundary import (
    APP_IMPORT_BOUNDARY_CONTRACT_RELPATH,
    AppImportRecord,
    boundary_violations,
    scan_shared_runtime_imports,
    validate_app_import_boundary,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_repository_import_boundary_proves_apps_rg_has_no_shared_runtime_imports() -> None:
    evidence = validate_app_import_boundary(REPO_ROOT)

    assert evidence["application_package"] == "apps_rg"
    assert evidence["current_forbidden_shared_runtime_import_files"] == 0
    assert evidence["forbidden_runtime_package_roots"] == ["shared_runtime"]
    assert evidence["apps_rg_contract_facade"] == "src/apps_rg/runtime/spine_contracts.py"


def test_boundary_rejects_new_static_and_literal_dynamic_shared_runtime_imports(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src" / "apps_rg"
    module = source_root / "new_direct_import.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import shared_runtime.knowledge.retrieval\n"
        "import importlib\n"
        "importlib.import_module('shared_runtime.provider_gateway')\n",
        encoding="utf-8",
    )
    records = scan_shared_runtime_imports(
        source_root,
        forbidden_package_roots=("shared_runtime",),
    )
    policy = {
        "apps_rg_contract_facade": "src/apps_rg/runtime/spine_contracts.py",
        "forbidden_runtime_package_roots": ["shared_runtime"],
    }

    violations = boundary_violations(records, policy)

    assert violations["forbidden_shared_runtime_import_files"] == [
        "src/apps_rg/new_direct_import.py"
    ]
    assert violations["forbidden_shared_runtime_imports"] == [
        "src/apps_rg/new_direct_import.py:1:shared_runtime.knowledge.retrieval",
        "src/apps_rg/new_direct_import.py:3:shared_runtime.provider_gateway",
    ]


def test_boundary_contract_has_unique_shared_runtime_package_names() -> None:
    policy = json.loads(
        (REPO_ROOT / APP_IMPORT_BOUNDARY_CONTRACT_RELPATH).read_text(encoding="utf-8")
    )
    forbidden = policy["forbidden_runtime_package_roots"]

    assert len(forbidden) == len(set(forbidden))
    assert all(name.isidentifier() for name in forbidden)


def test_violation_rows_preserve_the_source_location() -> None:
    records = [
        AppImportRecord(
            "src/apps_rg/runtime/bypass.py",
            "shared_runtime.contracts.route_contract",
            11,
        )
    ]
    policy = {
        "apps_rg_contract_facade": "src/apps_rg/runtime/spine_contracts.py",
        "forbidden_runtime_package_roots": ["shared_runtime"],
    }

    violations = boundary_violations(records, policy)

    assert violations["forbidden_shared_runtime_imports"] == [
        "src/apps_rg/runtime/bypass.py:11:shared_runtime.contracts.route_contract"
    ]


def test_canonical_fresh_cli_requires_the_app_runtime_preflight() -> None:
    tree = ast.parse((REPO_ROOT / "src/apps_rg/__main__.py").read_text(encoding="utf-8"))
    fresh_preflight_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_fresh_e2e_preflight"
    ]

    assert any(
        {keyword.arg for keyword in call.keywords}
        >= {
        "dependency_check",
        "runtime_check",
        "bootstrap",
        }
        for call in fresh_preflight_calls
    )
