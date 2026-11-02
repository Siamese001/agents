#!/usr/bin/env python3
"""Agents Repository — 6-Pillar Storage, Worktree, and SQLite Hygiene Audit & Remediation Engine.

Implements the deterministic, fail-closed Stage I (`Order 1/7`) hygiene audit and wave
remediation workflow defined in `automations/prompts/agents_storage_worktree_hygiene_agent.md`
under `urn:agents:scheduled-task-common-control-matrix:1.0.0` (`INV-REPO-SEPARATION-AGENTS-ONLY`).

Pillars:
1. Worktree & Branch Drift (`git worktree list --porcelain`, `git branch --merged main`)
2. SQLite Integrity & Journal Mode (`PRAGMA integrity_check`, `PRAGMA journal_mode=WAL`)
3. WAL / SHM Bloat Detection (`-wal` or `-shm` > 32 MB requiring `PRAGMA wal_checkpoint(TRUNCATE)`)
4. Ephemeral Artifact Sprawl (`artifacts/sidecar_runs/`, `artifacts/mcp/playwright/`, `.pytest_cache/` > 500 MB)
5. Stale Lock & Temp File Sweep (orphaned `.lock`, `.tmp` > 24 hours outside `.git`, `.worktrees`, `.venv`, `uv.lock`)
6. Cross-Repository Isolation Verification (`tools/validate_sidecar_separation.py`)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.prune_merged_chat_worktrees import (
    get_merged_branches,
    list_worktrees,
    prune_merged_worktrees,
)
from tools.validate_sidecar_separation import DEFAULT_SIDECARS_ROOT, validate_sidecar_separation

WAL_BLOAT_THRESHOLD_MB: float = 32.0
ARTIFACT_SPRAWL_THRESHOLD_MB: float = 500.0
STALE_LOCK_AGE_SECONDS: float = 86400.0

EXEMPT_LOCK_NAMES: frozenset[str] = frozenset({"uv.lock", "poetry.lock", "Cargo.lock", "package-lock.json"})
EXEMPT_PATH_PARTS: frozenset[str] = frozenset({".git", ".worktrees", ".venv", "venv", "node_modules", "__pycache__"})


def _dir_size_mb(path: Path) -> float:
    """Measure directory disk footprint in megabytes."""
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())
    return round(total / (1024 * 1024), 3)


def _discover_sqlite_dbs(repo_root: Path) -> list[Path]:
    """Locate repository SQLite state databases under artifacts/ and .codex/."""
    found = list(repo_root.glob("artifacts/**/*.sqlite")) + list(repo_root.glob(".codex/**/*.sqlite"))
    return sorted({p.resolve() for p in found if p.is_file()})


def inspect_sqlite_databases(repo_root: Path) -> list[dict[str, Any]]:
    """Run read-only PRAGMA integrity_check, journal_mode, and WAL/SHM size checks."""
    reports: list[dict[str, Any]] = []
    for db_path in _discover_sqlite_dbs(repo_root):
        wal_path = Path(str(db_path) + "-wal")
        shm_path = Path(str(db_path) + "-shm")
        wal_mb = round(wal_path.stat().st_size / (1024 * 1024), 3) if wal_path.exists() else 0.0
        shm_mb = round(shm_path.stat().st_size / (1024 * 1024), 3) if shm_path.exists() else 0.0
        sha256_before = hashlib.sha256(db_path.read_bytes()).hexdigest()
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0)
            integrity_row = conn.execute("PRAGMA integrity_check;").fetchone()
            jmode_row = conn.execute("PRAGMA journal_mode;").fetchone()
            conn.close()
            integrity = str(integrity_row[0]) if integrity_row else "unknown"
            jmode = str(jmode_row[0]).lower() if jmode_row else "unknown"
        except Exception as exc:  # guardian: database corruption or lock diagnostic fallback
            integrity = f"ERROR: {exc}"
            jmode = "unknown"

        try:
            rel_path = str(db_path.relative_to(repo_root.resolve()))
        except ValueError:
            rel_path = str(db_path)

        reports.append(
            {
                "db": rel_path,
                "integrity": integrity,
                "journal_mode": jmode,
                "wal_mb": wal_mb,
                "shm_mb": shm_mb,
                "wal_bloat": wal_mb > WAL_BLOAT_THRESHOLD_MB or shm_mb > WAL_BLOAT_THRESHOLD_MB,
                "sha256": sha256_before,
            }
        )
    return reports


def remediate_sqlite_wal(repo_root: Path) -> list[dict[str, Any]]:
    """Enforce PRAGMA journal_mode=WAL and PRAGMA wal_checkpoint(TRUNCATE) on all repository SQLite DBs."""
    results: list[dict[str, Any]] = []
    for db_path in _discover_sqlite_dbs(repo_root):
        pre_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        pre_mode_row = conn.execute("PRAGMA journal_mode;").fetchone()
        pre_mode = str(pre_mode_row[0]).lower() if pre_mode_row else "unknown"
        post_mode_row = conn.execute("PRAGMA journal_mode=WAL;").fetchone()
        post_mode = str(post_mode_row[0]).lower() if post_mode_row else "unknown"
        chk_row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
        integ_row = conn.execute("PRAGMA integrity_check;").fetchone()
        conn.close()

        wal_path = Path(str(db_path) + "-wal")
        wal_mb = round(wal_path.stat().st_size / (1024 * 1024), 3) if wal_path.exists() else 0.0
        post_sha = hashlib.sha256(db_path.read_bytes()).hexdigest()
        try:
            rel_path = str(db_path.relative_to(repo_root.resolve()))
        except ValueError:
            rel_path = str(db_path)

        results.append(
            {
                "db": rel_path,
                "pre_journal_mode": pre_mode,
                "post_journal_mode": post_mode,
                "checkpoint_result": list(chk_row) if chk_row else [],
                "integrity": str(integ_row[0]) if integ_row else "unknown",
                "wal_mb": wal_mb,
                "pre_sha256": pre_sha,
                "post_sha256": post_sha,
            }
        )
    return results


def scan_stale_locks_and_temps(repo_root: Path, max_age_seconds: float = STALE_LOCK_AGE_SECONDS) -> list[str]:
    """Identify orphaned .lock or .tmp files older than max_age_seconds outside exempt directories."""
    cutoff = time.time() - max_age_seconds
    stale: list[str] = []
    root_resolved = repo_root.resolve()
    for pattern in ("*.lock", "*.tmp"):
        for path in root_resolved.rglob(pattern):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root_resolved)
            if any(part in EXEMPT_PATH_PARTS for part in rel.parts):
                continue
            if path.name in EXEMPT_LOCK_NAMES:
                continue
            if path.stat().st_mtime < cutoff:
                stale.append(str(rel))
    return sorted(stale)


def run_six_pillar_hygiene_audit(
    *,
    repo_root: Path = REPO_ROOT,
    sidecars_root: Path = DEFAULT_SIDECARS_ROOT,
    remediate: bool = False,
) -> dict[str, Any]:
    """Execute the 6-pillar storage, worktree, and SQLite hygiene audit (and optional remediation)."""
    root = repo_root.resolve()

    worktree_remediation = prune_merged_worktrees(
        repo_root=root,
        target_ref="main",
        delete_merged=remediate,
    )
    worktrees = list_worktrees(root)
    merged_branches = sorted(get_merged_branches(root, target_ref="main"))
    prunable_worktrees = [str(wt["path"]) for wt in worktrees if wt.get("prunable")]

    sqlite_remediation: list[dict[str, Any]] = []
    if remediate:
        sqlite_remediation = remediate_sqlite_wal(root)

    db_reports = inspect_sqlite_databases(root)

    sidecar_runs_mb = _dir_size_mb(root / "artifacts" / "sidecar_runs")
    playwright_mb = _dir_size_mb(root / "artifacts" / "mcp" / "playwright")
    pytest_cache_mb = _dir_size_mb(root / ".pytest_cache")
    total_sprawl_mb = round(sidecar_runs_mb + playwright_mb + pytest_cache_mb, 3)

    stale_files = scan_stale_locks_and_temps(root)
    if remediate and stale_files:
        for rel_file in list(stale_files):
            target = root / rel_file
            if target.is_file():
                target.unlink()
        stale_files = scan_stale_locks_and_temps(root)

    separation = validate_sidecar_separation(repo_root=root, sidecars_root=sidecars_root)

    pillar_status = {
        "pillar_1_worktree_branch_drift": "PASS" if (not prunable_worktrees and not merged_branches) else "FINDINGS",
        "pillar_2_sqlite_integrity_wal": "PASS"
        if all(d["integrity"] == "ok" and d["journal_mode"] == "wal" for d in db_reports)
        else "FINDINGS",
        "pillar_3_wal_shm_bloat": "PASS" if not any(d["wal_bloat"] for d in db_reports) else "FINDINGS",
        "pillar_4_artifact_sprawl": "PASS" if total_sprawl_mb <= ARTIFACT_SPRAWL_THRESHOLD_MB else "FINDINGS",
        "pillar_5_stale_locks_temps": "PASS" if not stale_files else "FINDINGS",
        "pillar_6_sidecar_isolation": "PASS" if separation["is_clean"] else "FAIL",
    }

    overall_clean = all(v == "PASS" for v in pillar_status.values())
    return {
        "status": "PASS" if overall_clean else "FINDINGS",
        "is_clean": overall_clean,
        "repo_root": str(root),
        "remediated": remediate,
        "pillar_status": pillar_status,
        "worktree_prunable_count": len(prunable_worktrees),
        "merged_branches": merged_branches,
        "db_count": len(db_reports),
        "dbs": db_reports,
        "sqlite_remediation": sqlite_remediation,
        "sprawl": {
            "sidecar_runs_mb": sidecar_runs_mb,
            "playwright_mb": playwright_mb,
            "pytest_cache_mb": pytest_cache_mb,
            "total_mb": total_sprawl_mb,
            "threshold_mb": ARTIFACT_SPRAWL_THRESHOLD_MB,
        },
        "stale_files": stale_files,
        "sidecar_separation": separation,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 6-pillar storage, worktree, and SQLite hygiene audit.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root path")
    parser.add_argument("--sidecars-root", type=Path, default=DEFAULT_SIDECARS_ROOT, help="Global sidecars root")
    parser.add_argument("--remediate", action="store_true", help="Execute bounded WAL and worktree remediation")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output file path")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    args = parser.parse_args(argv)

    report = run_six_pillar_hygiene_audit(
        repo_root=args.repo_root,
        sidecars_root=args.sidecars_root,
        remediate=args.remediate,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[{report['status']}] 6-Pillar Storage & Worktree Hygiene Audit (db_count={report['db_count']})")

    return 0 if report["sidecar_separation"]["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
