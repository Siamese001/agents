"""Runtime persistence helpers for graph selection rejections and metric usage (Wave 4 / AC4.5)."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from apps_rg.fact_inventory.graph_sqlite_path_index import (
    record_graph_selection_rejection,
    record_resume_metric_usage,
)


_TELEMETRY_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS graph_selection_rejections (
        run_id TEXT NOT NULL CHECK (TRIM(run_id) <> ''),
        section_id TEXT NOT NULL CHECK (TRIM(section_id) <> ''),
        candidate_node_id TEXT NOT NULL CHECK (TRIM(candidate_node_id) <> ''),
        candidate_node_type TEXT NOT NULL CHECK (TRIM(candidate_node_type) <> ''),
        rejected_reason TEXT NOT NULL CHECK (TRIM(rejected_reason) <> ''),
        rejected_at_stage TEXT NOT NULL CHECK (TRIM(rejected_at_stage) <> ''),
        competing_selected_node_id TEXT NOT NULL DEFAULT '',
        path_signature TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        PRIMARY KEY (run_id, section_id, candidate_node_id, rejected_at_stage)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_metric_usage (
        run_id TEXT NOT NULL CHECK (TRIM(run_id) <> ''),
        resume_section TEXT NOT NULL CHECK (TRIM(resume_section) <> ''),
        metric_id TEXT NOT NULL CHECK (TRIM(metric_id) <> ''),
        metric_value TEXT NOT NULL DEFAULT '',
        fact_id TEXT NOT NULL DEFAULT '',
        skill_id TEXT NOT NULL DEFAULT '',
        role_family_key TEXT NOT NULL DEFAULT '',
        usage_count INTEGER NOT NULL DEFAULT 1 CHECK (usage_count >= 1),
        created_at TEXT NOT NULL,
        PRIMARY KEY (run_id, resume_section, metric_id)
    )
    """,
)


def resolve_runtime_telemetry_db_path(
    db_path: Path | str,
    *,
    telemetry_db_path: Path | str | None = None,
    run_dir: Path | str | None = None,
) -> Path:
    """Resolve sidecar telemetry SQLite path so canonical graph DB stays strictly read-only."""
    if telemetry_db_path is not None:
        return Path(telemetry_db_path)
    if run_dir is not None:
        return Path(run_dir) / "runtime_graph_telemetry.sqlite"
    return Path(db_path).parent / "runtime_graph_telemetry.sqlite"


def persist_runtime_selection_events(
    db_path: Path | str,
    *,
    run_id: str,
    section_id: str,
    role_family_key: str = "",
    rejections: Sequence[dict[str, Any]] = (),
    selected_candidates: Sequence[dict[str, Any]] = (),
    telemetry_db_path: Path | str | None = None,
    run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Persist rejections and metric usage events to a sidecar telemetry SQLite.

    Opens canonical graph DB strictly read-only (mode=ro, PRAGMA query_only=ON) so
    runtime queries never mutate augmented_skills_graph.sqlite.
    """
    p = Path(db_path)
    target_telemetry = resolve_runtime_telemetry_db_path(
        p, telemetry_db_path=telemetry_db_path, run_dir=run_dir
    )
    if not p.is_file():
        return {
            "rejections_written": 0,
            "metric_usages_written": 0,
            "telemetry_db_path": str(target_telemetry),
        }

    rejections_written = 0
    metric_usages_written = 0

    try:
        ro_conn = sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True, timeout=10.0)
        ro_conn.execute("PRAGMA query_only=ON")
        target_telemetry.parent.mkdir(parents=True, exist_ok=True)
        tel_conn = sqlite3.connect(str(target_telemetry), timeout=10.0)
        try:
            for ddl in _TELEMETRY_DDL:
                tel_conn.execute(ddl)
            tel_conn.commit()
            import datetime as _dt

            now_ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
            for r in rejections:
                cand_id = str(
                    r.get("candidate_node_id") or r.get("candidate_id") or r.get("skill_id") or ""
                )
                if cand_id:
                    tel_conn.execute(
                        """
                        INSERT OR REPLACE INTO graph_selection_rejections (
                            run_id, section_id, candidate_node_id, candidate_node_type, rejected_reason,
                            rejected_at_stage, competing_selected_node_id, path_signature, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id or "run_default",
                            section_id,
                            cand_id,
                            str(r.get("candidate_node_type") or "skill"),
                            str(r.get("rejected_reason") or r.get("rejection_reason") or "ranked_out"),
                            str(r.get("rejected_at_stage") or r.get("failed_gate") or "ranking"),
                            str(r.get("competing_selected_node_id") or ""),
                            str(r.get("path_signature") or ""),
                            now_ts,
                        ),
                    )
                    rejections_written += 1

            facts_to_check: set[tuple[str, str]] = set()
            for c in selected_candidates:
                fid = str(c.get("ledger_fact_id") or c.get("fact_id") or "")
                sid = str(c.get("skill_id") or "")
                if fid and sid:
                    facts_to_check.add((fid, sid))
            if not facts_to_check:
                for r in rejections:
                    fid = str(r.get("ledger_fact_id") or r.get("fact_id") or r.get("root_id") or "")
                    sid = str(r.get("skill_id") or "")
                    if fid and sid:
                        facts_to_check.add((fid, sid))
            for fid, sid in facts_to_check:
                cur = ro_conn.cursor()
                valid_pair = cur.execute(
                    """
                    SELECT 1
                    FROM graph_nodes fn
                    JOIN graph_nodes sn ON sn.node_id = ? AND sn.node_type = 'skill'
                    WHERE fn.node_id = ?
                      AND fn.node_type IN ('fact', 'locked_bullet', 'employment', 'certification', 'engagement')
                    LIMIT 1
                    """,
                    (sid, fid),
                ).fetchone()
                if not valid_pair:
                    continue
                cur.execute(
                    """
                    SELECT target_node_id FROM graph_edges
                    WHERE edge_type = 'fact_has_metric_outcome' AND source_node_id = ?
                    UNION
                    SELECT target_node_id FROM graph_edges
                    WHERE edge_type = 'skill_surfaces_metric_outcome' AND source_node_id = ?
                    LIMIT 5
                    """,
                    (fid, sid),
                )
                metric_ids = [row[0] for row in cur.fetchall()]
                for mid in metric_ids:
                    tel_conn.execute(
                        """
                        INSERT OR REPLACE INTO resume_metric_usage (
                            run_id, resume_section, metric_id, metric_value, fact_id, skill_id,
                            role_family_key, usage_count, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id or "run_default",
                            section_id,
                            mid,
                            "",
                            fid,
                            sid,
                            role_family_key,
                            1,
                            now_ts,
                        ),
                    )
                    metric_usages_written += 1
            tel_conn.commit()
        finally:
            tel_conn.close()
            ro_conn.close()
    except (sqlite3.Error, OSError):
        pass

    return {
        "rejections_written": rejections_written,
        "metric_usages_written": metric_usages_written,
        "telemetry_db_path": str(target_telemetry),
    }


def enrich_binding_receipt(
    binding: dict[str, Any],
    *,
    selected: Sequence[dict[str, Any]],
    fact_id: str,
    inner: Mapping[str, Any],
) -> dict[str, Any]:
    """Enrich C0.3 binding receipt with path_confidence, evidence_ids, and build_run_id (AC4.4)."""
    path_conf = 0.0
    evidence_ids: list[str] = []
    if selected:
        scores = [
            float(c.get("path_confidence") or c.get("path_score") or c.get("proof_strength_score") or 0.85)
            for c in selected
        ]
        path_conf = round(max(scores), 4) if scores else 0.0
        for c in selected:
            for ev in (c.get("evidence_ids") or []):
                if ev and ev not in evidence_ids:
                    evidence_ids.append(str(ev))
    if not evidence_ids and fact_id:
        evidence_ids.append(fact_id)
    build_run_id = str(
        inner.get("build_run_id")
        or (inner.get("metadata") or {}).get("build_run_id")
        or "build_run_c03_traversal"
    )
    binding["path_confidence"] = path_conf
    binding["evidence_ids"] = evidence_ids
    binding["build_run_id"] = build_run_id
    return binding


def record_c03_expansion_events(
    ctx: Mapping[str, Any] | None,
    *,
    run_id: str,
    section_id: str,
    role_family_key: str,
    rejections: Sequence[dict[str, Any]],
    selected_candidates: Sequence[dict[str, Any]],
    run_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Record rejections and metric usage from C0.3 expansion into sidecar telemetry SQLite (AC4.5)."""
    if not ctx or not isinstance(ctx, Mapping):
        return {"rejections_written": 0, "metric_usages_written": 0, "telemetry_db_path": ""}
    db_path = ctx.get("sqlite_db_path") or ctx.get("graph_sqlite_path")
    if not db_path:
        return {"rejections_written": 0, "metric_usages_written": 0, "telemetry_db_path": ""}
    return persist_runtime_selection_events(
        db_path,
        run_id=run_id or "run_default",
        section_id=section_id,
        role_family_key=role_family_key,
        rejections=rejections,
        selected_candidates=selected_candidates,
        run_dir=run_dir or ctx.get("run_dir"),
    )


__all__ = [
    "resolve_runtime_telemetry_db_path",
    "persist_runtime_selection_events",
    "enrich_binding_receipt",
    "record_c03_expansion_events",
]
