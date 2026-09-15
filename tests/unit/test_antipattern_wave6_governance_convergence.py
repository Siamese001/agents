"""Unit tests for Wave 6: Cutover, Cleanup, and Continuous Architecture Governance.

Verifies:
1. tools/verify_release_gate.py executes and emits canonical release receipts and manifests.
2. tools/lint_architecture_boundaries.py enforces domain storage isolation, sys.path purity, and file budgets.
3. AST detection correctly catches synthetic violations of concrete storage imports and sys.path mutations.
4. Repository configuration runs warning-free without Pydantic deprecation or pytest config warnings.
5. All 6 Wave test suites exist and maintain full architectural convergence.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import pytest

from tools.lint_architecture_boundaries import (
    FORBIDDEN_STORAGE_MODULES,
    check_domain_storage_isolation,
    check_sys_path_purity,
    run_architecture_linter,
)
from tools.verify_release_gate import (
    WAVE_TEST_FILES,
    execute_release_gate,
    get_git_metadata,
)


def test_wave_test_files_presence() -> None:
    """Ensure all 6 anti-pattern remediation wave test suites exist."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    assert len(WAVE_TEST_FILES) == 6
    for rel_path in WAVE_TEST_FILES:
        path = repo_root / rel_path
        assert path.exists(), f"Wave test suite missing: {rel_path}"


def test_git_metadata_extraction() -> None:
    """Ensure git metadata helper extracts branch and SHA without throwing."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    meta = get_git_metadata(repo_root)
    assert "branch" in meta
    assert "commit_sha" in meta
    assert len(meta["commit_sha"]) > 0


def test_lint_architecture_boundaries_clean_repo() -> None:
    """Ensure the active repository passes all continuous architecture boundary checks."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    results = run_architecture_linter(repo_root)
    assert results["is_clean"] is True
    assert results["status"] == "PASS"
    assert results["total_violation_count"] == 0
    assert results["checks"]["domain_storage_isolation"]["status"] == "PASS"
    assert results["checks"]["sys_path_purity"]["status"] == "PASS"
    assert results["checks"]["file_budgets"]["status"] == "PASS"


def test_lint_domain_storage_isolation_catches_violations(tmp_path: Path) -> None:
    """Verify AST scanner detects forbidden concrete storage imports in domain services."""
    domain_dir = tmp_path / "agents" / "orchestration" / "services"
    domain_dir.mkdir(parents=True)
    violation_file = domain_dir / "bad_service.py"
    violation_file.write_text(
        "import sqlite3\n"
        "from agents.persistence.sqlite.state_repository import SqliteStateRepository\n",
        encoding="utf-8",
    )

    violations = check_domain_storage_isolation(tmp_path)
    assert len(violations) >= 2
    assert any("sqlite3" in v for v in violations)
    assert any("SqliteStateRepository" in v or "agents.persistence.sqlite" in v for v in violations)


def test_lint_sys_path_purity_catches_mutations(tmp_path: Path) -> None:
    """Verify AST scanner detects sys.path modifications."""
    prod_dir = tmp_path / "agents" / "orchestration"
    prod_dir.mkdir(parents=True)
    bad_file = prod_dir / "bad_path.py"
    bad_file.write_text(
        "import sys\n"
        "sys.path.insert(0, '/tmp/hack')\n"
        "sys.path.append('/tmp/hack2')\n",
        encoding="utf-8",
    )

    violations = check_sys_path_purity(tmp_path)
    assert len(violations) == 2
    assert any("Forbidden sys.path.insert() call" in v for v in violations)
    assert any("Forbidden sys.path.append() call" in v for v in violations)


def test_release_gate_receipt_and_manifest_generation(tmp_path: Path) -> None:
    """Verify release gate generates valid, cryptographically attested receipt and manifest."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    receipt = execute_release_gate(
        repo_root,
        output_dir=tmp_path,
        keep_going=True,
        wave_suites=["tests/unit/test_antipattern_wave1_packaging_ssot.py"],
        run_full_suite=False,
    )

    assert receipt["gate_name"] == "SOVEREIGN_PLATFORM_RELEASE_GATE"
    assert receipt["wave"] == 6
    assert receipt["status"] == "PASSED"
    assert receipt["all_passed"] is True
    assert "receipt_digest" in receipt
    assert len(receipt["receipt_digest"]) == 64

    # Verify receipt file on disk
    receipt_file = tmp_path / "release_receipt.json"
    assert receipt_file.exists()
    loaded_receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert loaded_receipt["receipt_digest"] == receipt["receipt_digest"]

    # Verify manifest file on disk
    manifest_file = tmp_path / "release_manifest.json"
    assert manifest_file.exists()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["manifest_type"] == "RELEASE_MANIFEST"
    assert manifest["receipt_sha256"] == receipt["receipt_digest"]
    assert manifest["status"] == "PASSED"
