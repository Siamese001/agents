"""Persistent Feedback Learning Store for Adaptive Agent Self-Correction.

Part of Sovereign Agentic Platform System Learning Rigor (Wave 1).
Maintains cross-session knowledge of recurring failure signatures,
evaluates resolution efficacy, and retrieves proven historical repair hints
to accelerate bounded semantic revision loops.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Mapping, Sequence

from agents.orchestration.failure_taxonomy import FailureKind

DEFAULT_LEARNING_STORE_PATH = Path("artifacts/learning/feedback_learning.sqlite")


def normalize_constraint_key(constraint: str) -> str:
    """Normalize constraint text into a canonical key for signature hashing."""
    cleaned = constraint.strip().lower()
    # Normalize numbers, quotes, and punctuation
    cleaned = re.sub(r"['\"`]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def compute_failure_signature(failure_kind: FailureKind | str, constraint: str) -> str:
    """Compute deterministic SHA-256 failure signature hash."""
    kind_str = failure_kind.value if isinstance(failure_kind, FailureKind) else str(failure_kind)
    canonical = f"{kind_str.upper()}:{normalize_constraint_key(constraint)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class FeedbackLearningStore:
    """Thread-safe SQLite store for failure signatures and empirical repair hints."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        raw_path = db_path or os.environ.get("AGENTS_LEARNING_STORE_PATH") or DEFAULT_LEARNING_STORE_PATH
        self.is_memory = str(raw_path) == ":memory:"
        if self.is_memory:
            self.db_path = Path(":memory:")
        else:
            self.db_path = Path(raw_path).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            db_target = ":memory:" if self.is_memory else str(self.db_path)
            self._conn = sqlite3.connect(
                db_target,
                timeout=30.0,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS failure_signatures (
                        signature_hash TEXT PRIMARY KEY,
                        failure_kind TEXT NOT NULL,
                        normalized_constraint TEXT NOT NULL,
                        occurrence_count INTEGER DEFAULT 1,
                        resolution_count INTEGER DEFAULT 0,
                        success_rate REAL DEFAULT 0.0,
                        effective_repair_hints_json TEXT DEFAULT '[]',
                        first_seen_at REAL,
                        last_seen_at REAL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS resolution_events (
                        event_id TEXT PRIMARY KEY,
                        signature_hash TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        action_taken TEXT NOT NULL,
                        repair_hint TEXT,
                        outcome TEXT NOT NULL,
                        occurred_at REAL NOT NULL,
                        FOREIGN KEY(signature_hash) REFERENCES failure_signatures(signature_hash)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_failure_kind ON failure_signatures(failure_kind)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_resolution_sig ON resolution_events(signature_hash)"
                )

    def record_failure(
        self,
        failure_kind: FailureKind | str,
        constraint: str,
        *,
        run_id: str = "",
        timestamp: float | None = None,
    ) -> str:
        """Record an observed failure occurrence and return its signature hash."""
        sig_hash = compute_failure_signature(failure_kind, constraint)
        kind_str = failure_kind.value if isinstance(failure_kind, FailureKind) else str(failure_kind)
        norm_constraint = normalize_constraint_key(constraint)
        now = timestamp or time.time()

        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO failure_signatures (
                        signature_hash, failure_kind, normalized_constraint,
                        occurrence_count, resolution_count, success_rate,
                        effective_repair_hints_json, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, 1, 0, 0.0, '[]', ?, ?)
                    ON CONFLICT(signature_hash) DO UPDATE SET
                        occurrence_count = occurrence_count + 1,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (sig_hash, kind_str, norm_constraint, now, now),
                )
        return sig_hash

    def record_resolution(
        self,
        signature_hash: str,
        *,
        run_id: str = "",
        action_taken: str = "SEMANTIC_REVISION",
        repair_hint: str = "",
        outcome: str = "SUCCESS",
        timestamp: float | None = None,
    ) -> None:
        """Record a resolution attempt, updating signature success rates and proven hints."""
        now = timestamp or time.time()
        event_id = f"res_{hashlib.sha256(f'{signature_hash}:{run_id}:{now}'.encode()).hexdigest()[:12]}"
        is_success = outcome.upper() == "SUCCESS"

        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO resolution_events (
                        event_id, signature_hash, run_id, action_taken,
                        repair_hint, outcome, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, signature_hash, run_id, action_taken, repair_hint, outcome.upper(), now),
                )

                # Fetch updated stats
                row = conn.execute(
                    """
                    SELECT occurrence_count, resolution_count, effective_repair_hints_json
                    FROM failure_signatures
                    WHERE signature_hash = ?
                    """,
                    (signature_hash,),
                ).fetchone()

                if row:
                    curr_occ = row["occurrence_count"]
                    hints = json.loads(row["effective_repair_hints_json"] or "[]")
                    if is_success and repair_hint and repair_hint not in hints:
                        hints.append(repair_hint)
                        if len(hints) > 5:
                            hints = hints[-5:]

                    succ_count = conn.execute(
                        "SELECT COUNT(*) FROM resolution_events WHERE signature_hash = ? AND outcome = 'SUCCESS'",
                        (signature_hash,),
                    ).fetchone()[0]

                    total_res = conn.execute(
                        "SELECT COUNT(*) FROM resolution_events WHERE signature_hash = ?",
                        (signature_hash,),
                    ).fetchone()[0]

                    succ_rate = round(succ_count / max(1, total_res), 4)

                    conn.execute(
                        """
                        UPDATE failure_signatures
                        SET resolution_count = ?,
                            success_rate = ?,
                            effective_repair_hints_json = ?,
                            last_seen_at = ?
                        WHERE signature_hash = ?
                        """,
                        (total_res, succ_rate, json.dumps(hints), now, signature_hash),
                    )

    def get_repair_hints(self, failure_kind: FailureKind | str, constraint: str) -> list[str]:
        """Retrieve empirically effective repair hints for a given failure."""
        sig_hash = compute_failure_signature(failure_kind, constraint)
        with self._lock:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT effective_repair_hints_json FROM failure_signatures WHERE signature_hash = ?",
                (sig_hash,),
            ).fetchone()
            if row and row["effective_repair_hints_json"]:
                try:
                    return json.loads(row["effective_repair_hints_json"])
                except Exception:
                    return []
        return []

    def get_failure_statistics(self, signature_hash: str | None = None) -> list[dict[str, Any]]:
        """Query failure signature statistics."""
        with self._lock:
            conn = self._get_connection()
            if signature_hash:
                cursor = conn.execute(
                    "SELECT * FROM failure_signatures WHERE signature_hash = ?",
                    (signature_hash,),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM failure_signatures ORDER BY occurrence_count DESC"
                )
            return [dict(r) for r in cursor.fetchall()]

    def get_summary(self) -> dict[str, Any]:
        """Aggregate summary of system learning from feedback controller."""
        with self._lock:
            conn = self._get_connection()
            total_sigs = conn.execute("SELECT COUNT(*) FROM failure_signatures").fetchone()[0]
            total_events = conn.execute("SELECT COUNT(*) FROM resolution_events").fetchone()[0]
            succ_events = conn.execute(
                "SELECT COUNT(*) FROM resolution_events WHERE outcome = 'SUCCESS'"
            ).fetchone()[0]
            avg_rate = (
                conn.execute("SELECT AVG(success_rate) FROM failure_signatures").fetchone()[0] or 0.0
            )

            top_failures = conn.execute(
                """
                SELECT signature_hash, failure_kind, normalized_constraint, occurrence_count, success_rate
                FROM failure_signatures
                ORDER BY occurrence_count DESC
                LIMIT 5
                """
            ).fetchall()

            return {
                "total_failure_signatures": total_sigs,
                "total_resolutions_recorded": total_events,
                "successful_resolutions": succ_events,
                "overall_success_rate": round(succ_events / max(1, total_events), 4),
                "mean_signature_success_rate": round(float(avg_rate), 4),
                "top_failure_patterns": [dict(r) for r in top_failures],
                "store_location": str(self.db_path),
            }

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None


__all__ = [
    "DEFAULT_LEARNING_STORE_PATH",
    "FeedbackLearningStore",
    "compute_failure_signature",
    "normalize_constraint_key",
]
