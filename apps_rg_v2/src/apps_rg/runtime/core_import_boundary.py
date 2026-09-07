"""AST ratchet that keeps Apps RG free of generic shared-runtime imports.

The application owns the runtime contracts used by its pipeline.  This check is
deliberately static: it detects both ordinary and literal dynamic imports
without importing any application code.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final


APP_IMPORT_BOUNDARY_SCHEMA_VERSION: Final[str] = "apps_rg.import_boundary.v2"
APP_IMPORT_BOUNDARY_CONTRACT_RELPATH: Final[Path] = Path(
    "config/contracts/apps_rg_import_boundary.v2.json"
)


class AppImportBoundaryError(RuntimeError):
    """Raised when Apps RG source imports a prohibited shared-runtime package."""


@dataclass(frozen=True)
class AppImportRecord:
    path: str
    module: str
    line: int


def _module_root(module: str) -> str:
    return module.split(".", 1)[0]


def _literal_import_module(node: ast.Call) -> str | None:
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    value = node.args[0].value
    if not isinstance(value, str):
        return None
    function = node.func
    if isinstance(function, ast.Attribute) and function.attr == "import_module":
        return value
    if isinstance(function, ast.Name) and function.id == "import_module":
        return value
    return None


def scan_shared_runtime_imports(
    source_root: Path, *, forbidden_package_roots: Sequence[str]
) -> list[AppImportRecord]:
    """Return static and literal-dynamic imports of prohibited runtime roots."""

    root = Path(source_root).resolve()
    repo = root.parent.parent if root.name == "apps_rg" else root.parent
    forbidden = set(forbidden_package_roots)
    records: list[AppImportRecord] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.resolve().relative_to(repo).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _module_root(module) in forbidden:
                    records.append(AppImportRecord(relative, module, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _module_root(alias.name) in forbidden:
                        records.append(AppImportRecord(relative, alias.name, node.lineno))
            elif isinstance(node, ast.Call):
                module = _literal_import_module(node)
                if module is not None and _module_root(module) in forbidden:
                    records.append(AppImportRecord(relative, module, node.lineno))
    return sorted(records, key=lambda row: (row.path, row.line, row.module))


def _read_policy(contract_path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AppImportBoundaryError("Apps RG import-boundary contract is unreadable") from exc
    forbidden = policy.get("forbidden_runtime_package_roots")
    facade = policy.get("apps_rg_contract_facade")
    if (
        policy.get("schema_version") != APP_IMPORT_BOUNDARY_SCHEMA_VERSION
        or not isinstance(forbidden, Sequence)
        or isinstance(forbidden, (str, bytes))
        or not forbidden
        or any(not isinstance(name, str) or not name.isidentifier() for name in forbidden)
        or len(set(forbidden)) != len(forbidden)
        or not isinstance(facade, str)
        or not facade.startswith("src/apps_rg/")
    ):
        raise AppImportBoundaryError("Apps RG import-boundary contract is invalid")
    return policy


def boundary_violations(
    records: Sequence[AppImportRecord], policy: Mapping[str, Any]
) -> dict[str, list[str]]:
    """Return the exact files and modules that breach the application boundary."""

    return {
        "forbidden_shared_runtime_import_files": sorted(
            {record.path for record in records}
        ),
        "forbidden_shared_runtime_imports": sorted(
            {f"{record.path}:{record.line}:{record.module}" for record in records}
        ),
    }


def validate_app_import_boundary(
    repo_root: Path, *, contract_path: Path | None = None
) -> dict[str, Any]:
    """Validate Apps RG source isolation and return digest-free W6 evidence."""

    repo = Path(repo_root).resolve()
    path = contract_path or repo / APP_IMPORT_BOUNDARY_CONTRACT_RELPATH
    policy = _read_policy(path)
    records = scan_shared_runtime_imports(
        repo / "src" / "apps_rg",
        forbidden_package_roots=policy["forbidden_runtime_package_roots"],
    )
    violations = boundary_violations(records, policy)
    if any(violations.values()):
        raise AppImportBoundaryError(
            "Apps RG import-boundary violation: "
            + json.dumps(violations, sort_keys=True)
        )
    return {
        "schema_version": APP_IMPORT_BOUNDARY_SCHEMA_VERSION,
        "application_package": "apps_rg",
        "forbidden_runtime_package_roots": list(
            policy["forbidden_runtime_package_roots"]
        ),
        "current_forbidden_shared_runtime_import_files": 0,
        "apps_rg_contract_facade": policy["apps_rg_contract_facade"],
    }


__all__ = [
    "APP_IMPORT_BOUNDARY_CONTRACT_RELPATH",
    "APP_IMPORT_BOUNDARY_SCHEMA_VERSION",
    "AppImportBoundaryError",
    "AppImportRecord",
    "boundary_violations",
    "scan_shared_runtime_imports",
    "validate_app_import_boundary",
]
