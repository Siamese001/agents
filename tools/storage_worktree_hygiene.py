#!/usr/bin/env python3
"""Agents Repository — 6-Pillar Storage, Worktree, and SQLite Hygiene Audit & Remediation Engine.

Implements the deterministic, fail-closed Stage I (`Order 1/7`) hygiene audit and wave
remediation workflow defined in `automations/prompts/agents_storage_worktree_hygiene_agent.md`
under `urn:agents:scheduled-task-common-control-matrix:1.0.0` (`INV-REPO-SEPARATION-AGENTS-ONLY`).

Pillars:
1. Worktree & Branch Drift (`git worktree list --porcelain`, `git branch --merged main`)
2. SQLite Integrity & Journal Mode (`PRAGMA integrity_check`, `PRAGMA journal_mode=WAL`) across all 6 DBs
3. WAL / SHM Bloat Detection (`-wal` or `-shm` > 32 MB requiring `PRAGMA wal_checkpoint(TRUNCATE)`)
4. Ephemeral Artifact Sprawl & Storage Inventory (`sidecar_runs`, `playwright`, `.pytest_cache` + 28 GB inventory)
5. Stale Lock, Provisioning Lock & Scratch Sweep (orphaned `.lock`/`.tmp` > 24h, `.provisioning.lock`, `scratch/` leaks)
6. Cross-Repository Isolation Verification (`tools/validate_sidecar_separation.py`)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.prune_merged_chat_worktrees import (
    get_main_repo_root,
    get_merged_branches,
    has_active_sidecar_lease,
    is_worktree_clean,
    list_worktrees,
    prune_merged_worktrees,
)
from tools.validate_sidecar_separation import (
    DEFAULT_SIDECARS_ROOT,
    NEE_CANONICAL_ROOT,
    validate_sidecar_separation,
)

WAL_BLOAT_THRESHOLD_MB: float = 32.0
ARTIFACT_SPRAWL_THRESHOLD_MB: float = 500.0
STALE_LOCK_AGE_SECONDS: float = 86400.0
SQLITE_MAGIC_HEADER: bytes = b"SQLite format 3\x00"
SQLITE_SUFFIXES: frozenset[str] = frozenset({".sqlite", ".sqlite3", ".db"})

EXEMPT_LOCK_NAMES: frozenset[str] = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "Cargo.lock",
        "package-lock.json",
        ".sidecar_active_run.lock",
    }
)
EXEMPT_PATH_PARTS: frozenset[str] = frozenset(
    {".git", ".worktrees", ".venv", "venv", "node_modules", "__pycache__"}
)
DB_SCAN_SUBDIRS: tuple[str, ...] = (
    "artifacts",
    ".codex",
    "resume_graph_engine/artifacts/apps_rg/fact_inventory",
    "resume_graph_engine/data/cache",
)
DB_SKIP_DIRS: frozenset[str] = frozenset(
    {"models", "career_calls", "runs", ".git", ".venv", "node_modules", "__pycache__"}
)


def _storage_roots(repo_root: Path) -> list[Path]:
    """Return [repo_root] plus primary checkout root when running inside a linked worktree."""
    root = repo_root.resolve()
    primary = get_main_repo_root(root).resolve()
    if primary != root and primary.is_dir():
        return [root, primary]
    return [root]


def _dir_size_mb(path: Path) -> float:
    """Measure directory disk footprint in megabytes using fast os.walk traversal."""
    if not path.exists():
        return 0.0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
        for fname in filenames:
            fp = os.path.join(dirpath, fname)
            try:
                if not os.path.islink(fp):
                    total += os.lstat(fp).st_size
            except OSError:
                continue
    return round(total / (1024 * 1024), 3)


def _is_sqlite_file(path: Path) -> bool:
    """Verify standard 16-byte SQLite3 file header."""
    try:
        if not path.is_file() or path.is_symlink():
            return False
        with path.open("rb") as fh:
            return fh.read(16) == SQLITE_MAGIC_HEADER
    except OSError:
        return False


def _discover_sqlite_dbs(repo_root: Path) -> list[Path]:
    """Locate repository SQLite/Chroma/vector state databases across active and primary roots."""
    found: set[Path] = set()
    for base in _storage_roots(repo_root):
        for rel_sub in DB_SCAN_SUBDIRS:
            scan_dir = base / rel_sub
            if not scan_dir.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(scan_dir, followlinks=False):
                dirnames[:] = [d for d in dirnames if d not in DB_SKIP_DIRS]
                for fname in filenames:
                    if Path(fname).suffix.lower() in SQLITE_SUFFIXES:
                        candidate = Path(dirpath) / fname
                        if _is_sqlite_file(candidate):
                            found.add(candidate.resolve())
    return sorted(found)


def _format_rel_path(target: Path, roots: Sequence[Path]) -> str:
    resolved = target.resolve()
    for base in roots:
        try:
            return str(resolved.relative_to(base.resolve()))
        except ValueError:
            continue
    return str(resolved)


def inspect_sqlite_databases(repo_root: Path) -> list[dict[str, Any]]:
    """Run read-only PRAGMA integrity_check, journal_mode, and WAL/SHM size checks."""
    roots = _storage_roots(repo_root)
    reports: list[dict[str, Any]] = []
    for db_path in _discover_sqlite_dbs(repo_root):
        wal_path = Path(str(db_path) + "-wal")
        shm_path = Path(str(db_path) + "-shm")
        wal_mb = round(wal_path.stat().st_size / (1024 * 1024), 3) if wal_path.exists() else 0.0
        shm_mb = round(shm_path.stat().st_size / (1024 * 1024), 3) if shm_path.exists() else 0.0
        size_mb = round(db_path.stat().st_size / (1024 * 1024), 3)
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

        reports.append(
            {
                "db": _format_rel_path(db_path, roots),
                "size_mb": size_mb,
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
    roots = _storage_roots(repo_root)
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

        results.append(
            {
                "db": _format_rel_path(db_path, roots),
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
    stale: set[str] = set()
    roots = _storage_roots(repo_root)
    skip_walk = set(EXEMPT_PATH_PARTS) | {"models", "career_calls"}

    for base in roots:
        prov_lock = base / ".worktrees" / ".provisioning.lock"
        if prov_lock.is_file() and not prov_lock.is_symlink():
            try:
                if prov_lock.stat().st_mtime < cutoff:
                    stale.add(str(prov_lock.relative_to(base)))
            except OSError:
                pass

        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            rel_dir = Path(dirpath).relative_to(base)
            if rel_dir.parts and rel_dir.parts[0] == "resume_graph_engine" and len(rel_dir.parts) >= 2 and rel_dir.parts[1] == "artifacts":
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in skip_walk]
            for fname in filenames:
                if not (fname.endswith(".lock") or fname.endswith(".tmp")):
                    continue
                if fname in EXEMPT_LOCK_NAMES:
                    continue
                fp = Path(dirpath) / fname
                if not fp.is_file() or fp.is_symlink():
                    continue
                try:
                    if fp.stat().st_mtime < cutoff:
                        stale.add(str(fp.relative_to(base)))
                except OSError:
                    continue
    return sorted(stale)


def scan_scratch_violations(repo_root: Path) -> list[str]:
    """Scan scratch/ for cross-repository secret/path leaks violating INV-REPO-SEPARATION-AGENTS-ONLY."""
    violations: list[str] = []
    for base in _storage_roots(repo_root):
        scratch_dir = base / "scratch"
        if not scratch_dir.is_dir():
            continue
        for fp in sorted(scratch_dir.rglob("*")):
            if not fp.is_file() or fp.is_symlink():
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if NEE_CANONICAL_ROOT in content or "env_di" in content:
                violations.append(str(fp.relative_to(base)))
    return sorted(set(violations))


def collect_storage_inventory(repo_root: Path) -> dict[str, float]:
    """Measure full storage inventory across model caches, call recordings, graph runs, plans, and scratch."""
    roots = _storage_roots(repo_root)
    primary = roots[-1]
    tracked_dirs = {
        "models_mb": primary / "artifacts" / "models",
        "career_calls_mb": primary / "artifacts" / "career_calls",
        "resume_graph_artifacts_mb": primary / "resume_graph_engine" / "artifacts",
        "resume_graph_runtime_mb": primary / "resume_graph_engine" / ".runtime",
        "reports_mb": primary / "reports",
        "plans_mb": primary / "plans",
        "scratch_mb": primary / "scratch",
    }
    inventory = {key: _dir_size_mb(path) for key, path in tracked_dirs.items()}
    inventory["total_inventory_mb"] = round(sum(inventory.values()), 3)
    return inventory


def run_six_pillar_hygiene_audit(
    *,
    repo_root: Path = REPO_ROOT,
    sidecars_root: Path = DEFAULT_SIDECARS_ROOT,
    remediate: bool = False,
) -> dict[str, Any]:
    """Execute the 6-pillar storage, worktree, and SQLite hygiene audit (and optional remediation)."""
    root = repo_root.resolve()
    roots = _storage_roots(root)
    primary = roots[-1]

    prune_merged_worktrees(
        repo_root=root,
        target_ref="main",
        delete_merged=remediate,
    )
    worktrees = list_worktrees(root)
    protected_active_branches: set[str] = set()
    for wt in worktrees:
        wt_branch = wt.get("branch")
        wt_path = wt.get("path")
        if not wt_branch or not isinstance(wt_path, Path):
            continue
        if (
            wt_path.resolve() == root
            or has_active_sidecar_lease(wt_path)
            or not is_worktree_clean(wt_path)
        ):
            protected_active_branches.add(str(wt_branch))

    raw_merged = get_merged_branches(root, target_ref="main")
    merged_branches = sorted(b for b in raw_merged if b not in protected_active_branches)
    active_worktree_branches = sorted(protected_active_branches)
    prunable_worktrees = [str(wt["path"]) for wt in worktrees if wt.get("prunable")]

    sqlite_remediation: list[dict[str, Any]] = []
    if remediate:
        sqlite_remediation = remediate_sqlite_wal(root)

    db_reports = inspect_sqlite_databases(root)

    sidecar_runs_mb = _dir_size_mb(primary / "artifacts" / "sidecar_runs")
    playwright_mb = _dir_size_mb(primary / "artifacts" / "mcp" / "playwright")
    pytest_cache_mb = _dir_size_mb(primary / ".pytest_cache")
    total_sprawl_mb = round(sidecar_runs_mb + playwright_mb + pytest_cache_mb, 3)
    storage_inventory = collect_storage_inventory(root)

    stale_files = scan_stale_locks_and_temps(root)
    scratch_violations = scan_scratch_violations(root)
    if remediate and (stale_files or scratch_violations):
        for rel_file in list(stale_files) + list(scratch_violations):
            for base in roots:
                target = base / rel_file
                if target.is_file() and not target.is_symlink():
                    target.unlink()
        stale_files = scan_stale_locks_and_temps(root)
        scratch_violations = scan_scratch_violations(root)

    separation = validate_sidecar_separation(repo_root=root, sidecars_root=sidecars_root)

    pillar_status = {
        "pillar_1_worktree_branch_drift": "PASS" if (not prunable_worktrees and not merged_branches) else "FINDINGS",
        "pillar_2_sqlite_integrity_wal": "PASS"
        if all(d["integrity"] == "ok" and d["journal_mode"] == "wal" for d in db_reports)
        else "FINDINGS",
        "pillar_3_wal_shm_bloat": "PASS" if not any(d["wal_bloat"] for d in db_reports) else "FINDINGS",
        "pillar_4_artifact_sprawl": "PASS" if total_sprawl_mb <= ARTIFACT_SPRAWL_THRESHOLD_MB else "FINDINGS",
        "pillar_5_stale_locks_temps": "PASS" if (not stale_files and not scratch_violations) else "FINDINGS",
        "pillar_6_sidecar_isolation": "PASS" if (separation["is_clean"] and not scratch_violations) else "FAIL",
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
        "active_worktree_branches": active_worktree_branches,
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
        "storage_inventory": storage_inventory,
        "stale_files": stale_files,
        "scratch_violations": scratch_violations,
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

    return 0 if report["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
