"""Snapshot utility for augmented_skills_graph.sqlite.

Produces timestamped, sha256-manifested copies of the live SQLite database
and any pre-existing backup files into artifacts/apps_rg/fact_inventory/backups/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def snapshot_augmented_skills_graph(
    *,
    repo_root: Path | None = None,
    db_path: Path | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root or Path.cwd()).resolve()
    
    # Resolve target DB path
    target_db = Path(db_path) if db_path else root / "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
    if not target_db.exists():
        # Fallback to direct path if running inside resume_graph_engine
        candidate = root / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
        if candidate.exists():
            target_db = candidate

    # Resolve backup destination
    dest_dir = Path(backup_dir) if backup_dir else target_db.parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest_entries: list[dict[str, Any]] = []

    # 1. Snapshot live database if it exists
    if target_db.exists():
        snap_name = f"{target_db.name}.snapshot_{timestamp}"
        snap_path = dest_dir / snap_name
        shutil.copy2(target_db, snap_path)
        sha = _compute_sha256(snap_path)
        manifest_entries.append({
            "source": str(target_db),
            "target": str(snap_path),
            "name": snap_name,
            "sha256": sha,
            "size_bytes": snap_path.stat().st_size,
            "role": "live_projection_snapshot",
        })

    # 2. Archive pre-existing .bak files if present in the target directory
    for bak_file in sorted(target_db.parent.glob("*.bak*")):
        if bak_file.is_file():
            bak_dest = dest_dir / bak_file.name
            if not bak_dest.exists():
                shutil.copy2(bak_file, bak_dest)
            sha = _compute_sha256(bak_dest)
            manifest_entries.append({
                "source": str(bak_file),
                "target": str(bak_dest),
                "name": bak_file.name,
                "sha256": sha,
                "size_bytes": bak_dest.stat().st_size,
                "role": "pre_existing_backup_archive",
            })

    # Also archive any existing files in dest_dir matching .bak_20261005_125956
    known_bak = dest_dir / "augmented_skills_graph.sqlite.bak_20261005_125956"
    if known_bak.exists() and not any(e["name"] == known_bak.name for e in manifest_entries):
        sha = _compute_sha256(known_bak)
        manifest_entries.append({
            "source": str(known_bak),
            "target": str(known_bak),
            "name": known_bak.name,
            "sha256": sha,
            "size_bytes": known_bak.stat().st_size,
            "role": "pre_existing_backup_archive",
        })

    manifest = {
        "timestamp_utc": timestamp,
        "manifest_version": "1.0",
        "file_count": len(manifest_entries),
        "files": manifest_entries,
    }

    manifest_path = dest_dir / f"snapshot_manifest_{timestamp}.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    return {
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create timestamped, sha256-manifested snapshot of graph SQLite.")
    parser.add_argument("--repo-root", type=Path, default=None, help="Root of repository")
    parser.add_argument("--db-path", type=Path, default=None, help="Path to augmented_skills_graph.sqlite")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Directory to save snapshots")
    args = parser.parse_args()

    result = snapshot_augmented_skills_graph(
        repo_root=args.repo_root,
        db_path=args.db_path,
        backup_dir=args.backup_dir,
    )
    print(f"Snapshot created successfully: {result['manifest_path']}")
    for f in result["manifest"]["files"]:
        print(f"  [{f['role']}] {f['name']} (sha256: {f['sha256'][:16]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
