"""SQLite WAL ledger for applied post-runtime changes, cooldowns, rollback locks, and LP0..LP5 stage seals."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.contracts.schemas import utc_now_iso


class SqliteLearningLedgerStore:
    """Durable SQLite store for post-runtime auto-apply receipts, cooldowns, rollback locks, and Merkle seals."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA busy_timeout = 30000;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS applied_changes (
                    commit_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL UNIQUE,
                    proposal_digest TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    target_key TEXT NOT NULL,
                    autonomy_tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    canary_status TEXT NOT NULL,
                    rollback_handle_path TEXT NOT NULL,
                    merkle_seal_root TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    applied_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rollback_locks (
                    lock_key TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    locked_until_utc TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_stage_seals (
                    seal_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL,
                    merkle_root TEXT NOT NULL,
                    stages_json TEXT NOT NULL,
                    terminal_outcome TEXT NOT NULL,
                    sealed_at_utc TEXT NOT NULL
                )
                """
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def has_active_apply(self, proposal_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM applied_changes WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return row is not None and str(row["status"]) == "APPLIED"

    def record_applied_change(
        self,
        *,
        commit_id: str,
        proposal_id: str,
        proposal_digest: str,
        target_path: str,
        target_key: str,
        autonomy_tier: str,
        status: str,
        canary_status: str,
        rollback_handle_path: str,
        merkle_seal_root: str,
        receipt_dict: Mapping[str, Any],
        applied_at_utc: str | None = None,
    ) -> None:
        now = applied_at_utc or utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO applied_changes (
                    commit_id, proposal_id, proposal_digest, target_path, target_key,
                    autonomy_tier, status, canary_status, rollback_handle_path,
                    merkle_seal_root, receipt_json, applied_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_id,
                    proposal_id,
                    proposal_digest,
                    target_path,
                    target_key,
                    autonomy_tier,
                    status,
                    canary_status,
                    rollback_handle_path,
                    merkle_seal_root,
                    json.dumps(dict(receipt_dict), sort_keys=True),
                    now,
                    now,
                ),
            )

    def update_change_status(
        self,
        proposal_id: str,
        *,
        status: str,
        canary_status: str,
        merkle_seal_root: str | None = None,
    ) -> None:
        now = utc_now_iso()
        with self._lock, self._conn:
            if merkle_seal_root is not None:
                self._conn.execute(
                    """
                    UPDATE applied_changes
                    SET status = ?, canary_status = ?, merkle_seal_root = ?, updated_at_utc = ?
                    WHERE proposal_id = ?
                    """,
                    (status, canary_status, merkle_seal_root, now, proposal_id),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE applied_changes
                    SET status = ?, canary_status = ?, updated_at_utc = ?
                    WHERE proposal_id = ?
                    """,
                    (status, canary_status, now, proposal_id),
                )

    def count_recent_auto_applies(
        self,
        *,
        window_hours: int = 24,
        target_path: str | None = None,
        target_key: str | None = None,
        now_utc: datetime | None = None,
    ) -> int:
        now = now_utc or datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=window_hours)).isoformat().replace("+00:00", "Z")
        clauses = ["autonomy_tier = 'TIER_A_AUTO_APPLY'", "applied_at_utc >= ?"]
        params: list[Any] = [cutoff]
        if target_path is not None:
            clauses.append("target_path = ?")
            params.append(target_path)
        if target_key is not None:
            clauses.append("target_key = ?")
            params.append(target_key)
        sql = f"SELECT COUNT(*) FROM applied_changes WHERE {' AND '.join(clauses)}"
        with self._lock:
            return int(self._conn.execute(sql, params).fetchone()[0])

    def set_rollback_lock(
        self,
        *,
        target_path: str,
        target_key: str,
        proposal_id: str,
        lock_days: int = 7,
        reason: str = "post_apply_canary_rollback",
        now_utc: datetime | None = None,
    ) -> str:
        now = now_utc or datetime.now(timezone.utc)
        until = (now + timedelta(days=lock_days)).isoformat().replace("+00:00", "Z")
        lock_key = f"{target_path}::{target_key}"
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO rollback_locks (
                    lock_key, proposal_id, locked_until_utc, reason, created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (lock_key, proposal_id, until, reason, now.isoformat().replace("+00:00", "Z")),
            )
        return until

    def get_active_rollback_lock(
        self,
        *,
        target_path: str,
        target_key: str,
        now_utc: datetime | None = None,
    ) -> dict[str, Any] | None:
        now_iso = (now_utc or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
        lock_key = f"{target_path}::{target_key}"
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM rollback_locks WHERE lock_key = ? AND locked_until_utc > ?",
                (lock_key, now_iso),
            ).fetchone()
        return dict(row) if row is not None else None

    def record_stage_seal(
        self,
        *,
        seal_id: str,
        proposal_id: str,
        merkle_root: str,
        stages: Sequence[str],
        terminal_outcome: str,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO learning_stage_seals (
                    seal_id, proposal_id, merkle_root, stages_json, terminal_outcome, sealed_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    seal_id,
                    proposal_id,
                    merkle_root,
                    json.dumps(list(stages)),
                    terminal_outcome,
                    utc_now_iso(),
                ),
            )
