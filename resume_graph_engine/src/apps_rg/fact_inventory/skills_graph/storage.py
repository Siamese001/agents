"""SQLite connection, maintenance locking, atomic replacement, and path resolution."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_rg.repository_layout import repository_root
from .constants import REPO_REL_DB

def _repo_root() -> Path:
    return repository_root(Path(__file__))

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _sha256_hex(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()

def _sqlite_sidecar_paths(path: Path) -> tuple[Path, ...]:
    return tuple(Path(f"{path}{suffix}") for suffix in ("-journal", "-wal", "-shm"))

def _new_sibling_temp_db_path(path: Path) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    return Path(raw_path)

def _open_isolated_temp_graph_sqlite(
    *,
    temp_path: Path,
    canonical_target: Path,
) -> sqlite3.Connection:
    """Open the private writer used only for an atomic sibling-temp build."""
    resolved_temp = temp_path.resolve(strict=False)
    resolved_target = canonical_target.resolve(strict=False)
    is_unique_sibling = (
        resolved_temp != resolved_target
        and resolved_temp.parent == resolved_target.parent
        and resolved_temp.name.startswith(f".{resolved_target.name}.")
        and resolved_temp.name.endswith(".tmp")
    )
    if not is_unique_sibling:
        raise RuntimeError(
            "isolated graph SQLite writer requires a unique sibling temp path and "
            f"refuses the canonical target: temp={temp_path}, target={canonical_target}"
        )
    conn = sqlite3.connect(str(temp_path), timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        if int(conn.execute("PRAGMA foreign_keys").fetchone()[0]) != 1:
            raise RuntimeError("SQLite foreign key enforcement could not be enabled for isolated temp build")
    except (sqlite3.Error, RuntimeError):
        conn.close()
        raise
    return conn

def _cleanup_temp_sqlite(path: Path) -> None:
    for candidate in (path, *_sqlite_sidecar_paths(path)):
        candidate.unlink(missing_ok=True)

def _require_sidecar_free_atomic_target(path: Path) -> None:
    present = [sidecar.name for sidecar in _sqlite_sidecar_paths(path) if sidecar.exists()]
    if present:
        raise RuntimeError(
            "cannot atomically replace SQLite projection while sidecars exist: " + ",".join(present)
        )

def _sqlite_projection_digest(path: Path) -> str | None:
    """Return a byte-exact projection digest for compare-and-swap replacement."""
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _sqlite_maintenance_lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.maintenance.lock")

def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False

def _check_and_reclaim_stale_lock(lock_path: Path, max_age_seconds: float = 300.0) -> bool:
    """Return True if a stale lock was reclaimed, False otherwise."""
    try:
        if not lock_path.exists():
            return False
        content = lock_path.read_text(encoding="ascii", errors="ignore")
        match = re.search(r"pid=(\d+)", content)
        pid = int(match.group(1)) if match else None

        is_stale = False
        if pid is not None and not _is_pid_alive(pid):
            is_stale = True
        else:
            mtime = lock_path.stat().st_mtime
            if (time.time() - mtime) > max_age_seconds:
                is_stale = True

        if is_stale:
            lock_path.unlink(missing_ok=True)
            return True
    except (OSError, ValueError):
        pass
    return False

def _acquire_sqlite_maintenance_lock(path: Path) -> Path:
    """Acquire the projection maintenance lock using an atomic create with stale recovery."""
    lock_path = _sqlite_maintenance_lock_path(path)
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as exc:
            if attempt == 0 and _check_and_reclaim_stale_lock(lock_path):
                continue
            raise RuntimeError(f"SQLite projection maintenance is already active: {lock_path}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    finally:
        os.close(descriptor)
    return lock_path

def _release_sqlite_maintenance_lock(lock_path: Path) -> None:
    lock_path.unlink(missing_ok=True)

def _replace_sqlite_projection_if_unchanged(
    *,
    target: Path,
    replacement: Path,
    expected_digest: str | None,
) -> None:
    """CAS-replace a sidecar-free projection while its maintenance lock is held."""
    _require_sidecar_free_atomic_target(target)
    current_digest = _sqlite_projection_digest(target)
    if current_digest != expected_digest:
        raise RuntimeError(
            "SQLite projection changed during maintenance; refusing atomic replace: "
            f"expected={expected_digest!r}, current={current_digest!r}"
        )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            os.replace(replacement, target)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    if last_error:
        raise last_error

def default_graph_sqlite_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    env = str(os.environ.get("APPS_RG_AUGMENTED_SKILLS_GRAPH_SQLITE_PATH") or "").strip()
    if env:
        p = Path(env)
        return p if p.is_absolute() else (root / p).resolve()
    return (root / REPO_REL_DB).resolve()

def open_graph_sqlite(
    *,
    repo_root: Path | None = None,
    db_path: Path | None = None,
    read_only: bool = True,
) -> sqlite3.Connection:
    path = db_path or default_graph_sqlite_path(repo_root)
    if not read_only:
        raise RuntimeError(
            "writable graph SQLite access is internal-only; use "
            "materialize_augmented_skills_graph_sqlite(...) for an atomic rebuild or "
            "apply_graphdb_capability_sqlite_hardening(...) for atomic capability hardening"
        )
    if not path.is_file():
        raise FileNotFoundError(f"augmented skills graph sqlite missing: {path}")
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(
        uri,
        uri=True,
        timeout=15,
    )
    conn.execute("PRAGMA query_only=ON")
    if int(conn.execute("PRAGMA query_only").fetchone()[0]) != 1:
        conn.close()
        raise RuntimeError("SQLite query_only mode could not be enabled")
    return conn

def load_graph_metadata_row(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT graph_version, materialized_from, materialized_at, ledger_hash,
               graph_count_summary, authority_status
        FROM graph_metadata
        ORDER BY materialized_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        raise ValueError("graph_metadata empty")
    summary = json.loads(row[4] or "{}")
    return {
        "graph_version": row[0],
        "materialized_from": row[1],
        "materialized_at": row[2],
        "ledger_hash": row[3],
        "graph_count_summary": summary,
        "authority_status": row[5],
    }


__all__ = ['_repo_root', '_utc_now', '_sha256_hex', '_sqlite_sidecar_paths', '_new_sibling_temp_db_path', '_open_isolated_temp_graph_sqlite', '_cleanup_temp_sqlite', '_require_sidecar_free_atomic_target', '_sqlite_projection_digest', '_sqlite_maintenance_lock_path', '_is_pid_alive', '_check_and_reclaim_stale_lock', '_acquire_sqlite_maintenance_lock', '_release_sqlite_maintenance_lock', '_replace_sqlite_projection_if_unchanged', 'default_graph_sqlite_path', 'open_graph_sqlite', 'load_graph_metadata_row']
