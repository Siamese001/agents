"""SQLite implementation of the canonical deduplicated eval findings queue and immutable event audit trail."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.contracts.digests import canonical_sha256
from apps_eval.contracts.schemas import FindingRecord, utc_now_iso

FINDINGS_QUEUE_CONTRACT_ID = "urn:agents:learning:eval-findings-queue:1.0.0"

_PRIORITY_BASE = {"P0": 100.0, "P1": 60.0, "P2": 30.0}
_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}
_HUMAN_PRESERVED_STATUSES = frozenset({"APPROVED", "IN_PROGRESS", "REJECTED", "VERIFIED"})


def compute_finding_fingerprint(
    source_surface: str,
    failed_gate_signature: str,
    root_cause_bucket: str,
) -> str:
    raw = "|".join(
        [
            source_surface.strip().lower(),
            failed_gate_signature.strip().lower(),
            root_cause_bucket.strip().lower(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_impact_score(
    priority: str,
    occurrence_count: int,
    last_seen_utc: str,
    *,
    now_utc: datetime | None = None,
) -> float:
    """Compute priority * log-frequency * 14-day recency-decay score."""
    base = _PRIORITY_BASE.get(priority.upper(), 30.0)
    freq_boost = 1.0 + math.log2(max(1, int(occurrence_count))) * 0.25
    now = now_utc or datetime.now(timezone.utc)
    try:
        seen_dt = datetime.fromisoformat(last_seen_utc.replace("Z", "+00:00"))
        age_days = max(0.0, (now - seen_dt).total_seconds() / 86400.0)
    except ValueError:
        age_days = 0.0
    recency = max(0.35, 1.0 / (1.0 + age_days / 14.0))
    return round(base * freq_boost * recency, 2)


class SqliteFindingsQueueStore:
    """Canonical SQLite WAL store for eval_findings and immutable finding_events."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA busy_timeout = 30000;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS eval_findings (
                    finding_id TEXT PRIMARY KEY,
                    fingerprint_sha256 TEXT NOT NULL UNIQUE,
                    source_surface TEXT NOT NULL,
                    app_id TEXT NOT NULL,
                    failed_gate_signature TEXT NOT NULL,
                    root_cause_bucket TEXT NOT NULL,
                    owner_subsystem TEXT NOT NULL,
                    track TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    impact_score REAL NOT NULL DEFAULT 0.0,
                    target_files_json TEXT NOT NULL DEFAULT '[]',
                    sample_trace_ids_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    first_seen_utc TEXT NOT NULL,
                    last_seen_utc TEXT NOT NULL,
                    snoozed_until_utc TEXT,
                    hitl_decision_id TEXT,
                    finding_digest TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_findings_status_impact ON eval_findings(status, impact_score DESC)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS finding_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    finding_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    hitl_decision_id TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(finding_id) REFERENCES eval_findings(finding_id)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_finding_events_fid ON finding_events(finding_id, event_id DESC)"
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> FindingRecord:
        return FindingRecord(
            finding_id=str(row["finding_id"]),
            fingerprint_sha256=str(row["fingerprint_sha256"]),
            source_surface=str(row["source_surface"]),
            app_id=str(row["app_id"]),
            failed_gate_signature=str(row["failed_gate_signature"]),
            root_cause_bucket=str(row["root_cause_bucket"]),
            owner_subsystem=str(row["owner_subsystem"]),
            track=str(row["track"]),  # type: ignore[arg-type]
            priority=str(row["priority"]),  # type: ignore[arg-type]
            status=str(row["status"]),  # type: ignore[arg-type]
            title=str(row["title"]),
            summary=str(row["summary"]),
            recommended_action=str(row["recommended_action"]),
            occurrence_count=int(row["occurrence_count"]),
            impact_score=float(row["impact_score"]),
            target_files=list(json.loads(row["target_files_json"] or "[]")),
            sample_trace_ids=list(json.loads(row["sample_trace_ids_json"] or "[]")),
            metadata=dict(json.loads(row["metadata_json"] or "{}")),
            first_seen_utc=str(row["first_seen_utc"]),
            last_seen_utc=str(row["last_seen_utc"]),
            snoozed_until_utc=row["snoozed_until_utc"],
            hitl_decision_id=row["hitl_decision_id"],
            finding_digest=str(row["finding_digest"]),
        )

    def _append_event(
        self,
        *,
        finding_id: str,
        event_type: str,
        from_status: str | None,
        to_status: str,
        actor: str,
        rationale: str,
        hitl_decision_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO finding_events (
                finding_id, event_type, from_status, to_status,
                actor, rationale, hitl_decision_id, payload_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                event_type,
                from_status,
                to_status,
                actor,
                rationale,
                hitl_decision_id,
                json.dumps(dict(payload or {}), sort_keys=True),
                utc_now_iso(),
            ),
        )

    def upsert_finding(
        self,
        *,
        source_surface: str,
        app_id: str,
        failed_gate_signature: str,
        root_cause_bucket: str,
        owner_subsystem: str,
        track: str,
        priority: str,
        title: str,
        summary: str,
        recommended_action: str,
        occurrence_count: int = 1,
        target_files: Sequence[str] = (),
        sample_trace_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        seen_at_utc: str | None = None,
        cutoff_utc: str | None = None,
    ) -> FindingRecord:
        fp = compute_finding_fingerprint(source_surface, failed_gate_signature, root_cause_bucket)
        finding_id = f"find-{fp[:12]}"
        now_iso = utc_now_iso()
        seen_iso = seen_at_utc or now_iso
        is_pre_cutoff = bool(cutoff_utc and seen_iso < cutoff_utc)

        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT * FROM eval_findings WHERE fingerprint_sha256 = ?",
                (fp,),
            ).fetchone()

            if existing is None:
                status = "ARCHIVED" if is_pre_cutoff else "OPEN"
                merged_files = sorted(set(str(f) for f in target_files if f))[:20]
                merged_samples = list(dict.fromkeys(str(s) for s in sample_trace_ids if s))[:12]
                count = max(int(occurrence_count), len(merged_samples), 1)
                impact = compute_impact_score(priority, count, seen_iso)
                rec = FindingRecord(
                    finding_id=finding_id,
                    fingerprint_sha256=fp,
                    source_surface=source_surface,
                    app_id=app_id,
                    failed_gate_signature=failed_gate_signature,
                    root_cause_bucket=root_cause_bucket,
                    owner_subsystem=owner_subsystem,
                    track=track,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    status=status,  # type: ignore[arg-type]
                    title=title,
                    summary=summary,
                    recommended_action=recommended_action,
                    occurrence_count=count,
                    impact_score=impact,
                    target_files=merged_files,
                    sample_trace_ids=merged_samples,
                    metadata=dict(metadata or {}),
                    first_seen_utc=seen_iso,
                    last_seen_utc=seen_iso,
                )
                self._conn.execute(
                    """
                    INSERT INTO eval_findings (
                        finding_id, fingerprint_sha256, source_surface, app_id,
                        failed_gate_signature, root_cause_bucket, owner_subsystem,
                        track, priority, status, title, summary, recommended_action,
                        occurrence_count, impact_score, target_files_json,
                        sample_trace_ids_json, metadata_json, first_seen_utc,
                        last_seen_utc, snoozed_until_utc, hitl_decision_id,
                        finding_digest, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec.finding_id,
                        rec.fingerprint_sha256,
                        rec.source_surface,
                        rec.app_id,
                        rec.failed_gate_signature,
                        rec.root_cause_bucket,
                        rec.owner_subsystem,
                        rec.track,
                        rec.priority,
                        rec.status,
                        rec.title,
                        rec.summary,
                        rec.recommended_action,
                        rec.occurrence_count,
                        rec.impact_score,
                        json.dumps(rec.target_files),
                        json.dumps(rec.sample_trace_ids),
                        json.dumps(rec.metadata, sort_keys=True),
                        rec.first_seen_utc,
                        rec.last_seen_utc,
                        None,
                        None,
                        rec.finding_digest,
                        now_iso,
                    ),
                )
                self._append_event(
                    finding_id=rec.finding_id,
                    event_type="CREATED",
                    from_status=None,
                    to_status=rec.status,
                    actor="findings_consolidator",
                    rationale=f"Ingested from {source_surface} ({root_cause_bucket}).",
                )
                return rec

            prev_status = str(existing["status"])
            prev_files = list(json.loads(existing["target_files_json"] or "[]"))
            prev_samples = list(json.loads(existing["sample_trace_ids_json"] or "[]"))
            prev_meta = dict(json.loads(existing["metadata_json"] or "{}"))
            merged_files = sorted(set(prev_files) | {str(f) for f in target_files if f})[:20]
            merged_samples = list(dict.fromkeys([*prev_samples, *(str(s) for s in sample_trace_ids if s)]))[:12]
            merged_meta = {**prev_meta, **dict(metadata or {})}

            first_seen = min(str(existing["first_seen_utc"]), seen_iso)
            last_seen = max(str(existing["last_seen_utc"]), seen_iso)
            merged_count = max(int(existing["occurrence_count"]), int(occurrence_count), len(merged_samples))

            prev_prio = str(existing["priority"])
            merged_prio = (
                priority
                if _PRIORITY_RANK.get(priority, 2) < _PRIORITY_RANK.get(prev_prio, 2)
                else prev_prio
            )

            # Preserve human workflow statuses; auto-archive pre-cutoff OPEN, reopen expired snooze or recurred ARCHIVED.
            new_status = prev_status
            snoozed_until = existing["snoozed_until_utc"]
            if prev_status in _HUMAN_PRESERVED_STATUSES:
                new_status = prev_status
            elif prev_status == "SNOOZED" and snoozed_until and str(snoozed_until) <= now_iso:
                new_status = "OPEN"
                snoozed_until = None
            elif prev_status == "ARCHIVED" and cutoff_utc and last_seen >= cutoff_utc:
                new_status = "OPEN"
            elif prev_status == "OPEN" and cutoff_utc and last_seen < cutoff_utc:
                new_status = "ARCHIVED"

            impact = compute_impact_score(merged_prio, merged_count, last_seen)
            rec = FindingRecord(
                finding_id=finding_id,
                fingerprint_sha256=fp,
                source_surface=source_surface,
                app_id=app_id,
                failed_gate_signature=failed_gate_signature,
                root_cause_bucket=root_cause_bucket,
                owner_subsystem=owner_subsystem,
                track=track,  # type: ignore[arg-type]
                priority=merged_prio,  # type: ignore[arg-type]
                status=new_status,  # type: ignore[arg-type]
                title=title,
                summary=summary,
                recommended_action=recommended_action,
                occurrence_count=merged_count,
                impact_score=impact,
                target_files=merged_files,
                sample_trace_ids=merged_samples,
                metadata=merged_meta,
                first_seen_utc=first_seen,
                last_seen_utc=last_seen,
                snoozed_until_utc=snoozed_until,
                hitl_decision_id=existing["hitl_decision_id"],
            )
            self._conn.execute(
                """
                UPDATE eval_findings
                SET priority = ?, status = ?, title = ?, summary = ?,
                    recommended_action = ?, occurrence_count = ?, impact_score = ?,
                    target_files_json = ?, sample_trace_ids_json = ?, metadata_json = ?,
                    first_seen_utc = ?, last_seen_utc = ?, snoozed_until_utc = ?,
                    finding_digest = ?, updated_at_utc = ?
                WHERE finding_id = ?
                """,
                (
                    rec.priority,
                    rec.status,
                    rec.title,
                    rec.summary,
                    rec.recommended_action,
                    rec.occurrence_count,
                    rec.impact_score,
                    json.dumps(rec.target_files),
                    json.dumps(rec.sample_trace_ids),
                    json.dumps(rec.metadata, sort_keys=True),
                    rec.first_seen_utc,
                    rec.last_seen_utc,
                    rec.snoozed_until_utc,
                    rec.finding_digest,
                    now_iso,
                    rec.finding_id,
                ),
            )
            if new_status != prev_status:
                self._append_event(
                    finding_id=rec.finding_id,
                    event_type="AUTO_STATUS_REFRESH",
                    from_status=prev_status,
                    to_status=new_status,
                    actor="findings_consolidator",
                    rationale="Lifecycle auto-refresh on re-ingestion.",
                )
            return rec

    def transition_status(
        self,
        finding_id: str,
        to_status: str,
        *,
        actor: str,
        rationale: str,
        hitl_decision_id: str | None = None,
        snoozed_until_utc: str | None = None,
    ) -> FindingRecord:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM eval_findings WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown finding_id: {finding_id}")
            prev_status = str(row["status"])
            now_iso = utc_now_iso()
            self._conn.execute(
                """
                UPDATE eval_findings
                SET status = ?, hitl_decision_id = COALESCE(?, hitl_decision_id),
                    snoozed_until_utc = ?, updated_at_utc = ?
                WHERE finding_id = ?
                """,
                (to_status, hitl_decision_id, snoozed_until_utc, now_iso, finding_id),
            )
            self._append_event(
                finding_id=finding_id,
                event_type="STATUS_TRANSITION",
                from_status=prev_status,
                to_status=to_status,
                actor=actor,
                rationale=rationale,
                hitl_decision_id=hitl_decision_id,
            )
            updated = self._conn.execute(
                "SELECT * FROM eval_findings WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
            return self._row_to_record(updated)

    def list_findings(
        self,
        *,
        status: str | None = None,
        track: str | None = None,
        limit: int = 500,
    ) -> list[FindingRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if track is not None:
            clauses.append("track = ?")
            params.append(track)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT * FROM eval_findings
            {where}
            ORDER BY impact_score DESC, occurrence_count DESC, finding_id ASC
            LIMIT ?
        """
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_events(self, finding_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM finding_events WHERE finding_id = ? ORDER BY event_id ASC",
                (finding_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def export_snapshot(self, snapshot_path: Path | str) -> dict[str, Any]:
        target = Path(snapshot_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        findings = self.list_findings(limit=5000)
        by_status: dict[str, int] = {}
        by_track: dict[str, int] = {}
        for f in findings:
            by_status[f.status] = by_status.get(f.status, 0) + 1
            by_track[f.track] = by_track.get(f.track, 0) + 1
        payload = {
            "contract_id": FINDINGS_QUEUE_CONTRACT_ID,
            "schema_version": "1.0.0",
            "exported_at_utc": utc_now_iso(),
            "total_findings": len(findings),
            "counts_by_status": by_status,
            "counts_by_track": by_track,
            "findings": [f.to_dict() for f in findings],
        }
        payload["snapshot_digest"] = canonical_sha256(payload)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, target)
        return payload
