#!/usr/bin/env python3
"""Lint Architectural Layer Boundaries.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Scans ASTs of domain services and contracts to verify strict layer isolation:
- Domain services MUST NOT import concrete persistence adapters (sqlite3, SQLite/JSONL implementations).
- Domain services MUST NOT import CLI frameworks or raw terminal runners.
- Domain services MUST interact with persistence solely through abstract ports.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

FORBIDDEN_PERSISTENCE_MODULES = {
    "sqlite3",
    "agents.persistence.sqlite",
    "agents.persistence.jsonl",
    "agents.persistence.sqlite.state_repository",
    "agents.persistence.sqlite.event_store",
    "agents.persistence.jsonl.event_store",
    "agents.persistence.jsonl.artifact_store",
}

FORBIDDEN_CLI_MODULES = {
    "argparse",
    "click",
    "typer",
}


def check_layer_boundaries(target_dir: Path) -> list[str]:
    """Scan python files in target directory for layer boundary violations."""
    violations: list[str] = []

    for file_path in target_dir.glob("**/*.py"):
        if file_path.name.startswith("__") and file_path.name != "__init__.py":
            continue

        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except Exception as e:
            violations.append(f"{file_path}: Parse error: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    if mod in FORBIDDEN_PERSISTENCE_MODULES:
                        violations.append(
                            f"{file_path.name}:{node.lineno}: Forbidden concrete persistence import: '{mod}'"
                        )
                    if mod in FORBIDDEN_CLI_MODULES:
                        violations.append(
                            f"{file_path.name}:{node.lineno}: Forbidden CLI framework import in domain service: '{mod}'"
                        )

            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in FORBIDDEN_PERSISTENCE_MODULES:
                    violations.append(
                        f"{file_path.name}:{node.lineno}: Forbidden concrete persistence import: '{mod}'"
                    )
                for alias in node.names:
                    full = f"{mod}.{alias.name}" if mod else alias.name
                    if full in FORBIDDEN_PERSISTENCE_MODULES:
                        violations.append(
                            f"{file_path.name}:{node.lineno}: Forbidden concrete persistence import: '{full}'"
                        )
                    if alias.name in ("SqliteStateRepository", "SqliteEventStore", "JsonlEventStore", "FilesystemArtifactStore"):
                        violations.append(
                            f"{file_path.name}:{node.lineno}: Forbidden concrete persistence class import: '{alias.name}'"
                        )

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    services_dir = repo_root / "agents" / "orchestration" / "services"

    if not services_dir.exists():
        print(f"[ERROR] Directory not found: {services_dir}")
        return 1

    violations = check_layer_boundaries(services_dir)

    # Also check orchestration state contracts
    state_contract_violations = check_layer_boundaries(repo_root / "agents" / "orchestration")
    # Filter out test files or non-contract files
    filtered_orch = [v for v in state_contract_violations if "state_contracts.py" in v or "feedback_controller.py" in v]
    violations.extend(filtered_orch)

    if violations:
        print(f"[FAIL] Found {len(violations)} layer boundary violation(s):")
        for v in violations:
            print(f"  - {v}")
        return 1

    print("[PASS] Architectural layer boundaries clean (Zero concrete persistence or CLI leaks in domain services).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
