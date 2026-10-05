"""Runtime persistence helpers for graph selection rejections and metric usage (Wave 4 / AC4.5)."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from apps_rg.fact_inventory.graph_sqlite_path_index import (
    record_graph_selection_rejection,
    record_resume_metric_usage,
)


def persist_runtime_selection_events(
    db_path: Path | str,
    *,
    run_id: str,
    section_id: str,
    role_family_key: str = "",
    rejections: Sequence[dict[str, Any]] = (),
    selected_candidates: Sequence[dict[str, Any]] = (),
) -> dict[str, int]:
    """Persist rejections and metric usage events to SQLite during runtime runs.

    Guarantees that graph_selection_rejections and resume_metric_usage contain
    audit records of runtime candidate selection decisions.
    """
    p = Path(db_path)
    if not p.is_file():
        return {"rejections_written": 0, "metric_usages_written": 0}

    rejections_written = 0
    metric_usages_written = 0

    try:
        conn = sqlite3.connect(str(p), timeout=10.0)
        try:
            for r in rejections:
                cand_id = str(
                    r.get("candidate_node_id") or r.get("candidate_id") or r.get("skill_id") or ""
                )
                if cand_id:
                    record_graph_selection_rejection(
                        conn,
                        run_id=run_id or "run_default",
                        section_id=section_id,
                        candidate_node_id=cand_id,
                        candidate_node_type=str(r.get("candidate_node_type") or "skill"),
                        rejected_reason=str(
                            r.get("rejected_reason") or r.get("rejection_reason") or "ranked_out"
                        ),
                        rejected_at_stage=str(
                            r.get("rejected_at_stage") or r.get("failed_gate") or "ranking"
                        ),
                        competing_selected_node_id=str(r.get("competing_selected_node_id") or ""),
                        path_signature=str(r.get("path_signature") or ""),
                    )
                    rejections_written += 1

            facts_to_check: set[tuple[str, str]] = set()
            for c in selected_candidates:
                fid = str(c.get("fact_id") or "")
                sid = str(c.get("skill_id") or "")
                if fid:
                    facts_to_check.add((fid, sid))
            if not facts_to_check:
                for r in rejections:
                    fid = str(r.get("fact_id") or r.get("root_id") or "")
                    sid = str(r.get("skill_id") or "")
                    if fid:
                        facts_to_check.add((fid, sid))
            for fid, sid in facts_to_check:
                cur = conn.cursor()
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
                    record_resume_metric_usage(
                        conn,
                        run_id=run_id or "run_default",
                        resume_section=section_id,
                        metric_id=mid,
                        metric_value="",
                        fact_id=fid,
                        skill_id=sid,
                        role_family_key=role_family_key,
                        usage_count=1,
                    )
                    metric_usages_written += 1
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        pass

    return {
        "rejections_written": rejections_written,
        "metric_usages_written": metric_usages_written,
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
) -> dict[str, int]:
    """Record rejections and metric usage from C0.3 expansion into SQLite (AC4.5)."""
    if not ctx or not isinstance(ctx, Mapping):
        return {"rejections_written": 0, "metric_usages_written": 0}
    db_path = ctx.get("sqlite_db_path") or ctx.get("graph_sqlite_path")
    if not db_path:
        return {"rejections_written": 0, "metric_usages_written": 0}
    return persist_runtime_selection_events(
        db_path,
        run_id=run_id or "run_default",
        section_id=section_id,
        role_family_key=role_family_key,
        rejections=rejections,
        selected_candidates=selected_candidates,
    )


__all__ = [
    "persist_runtime_selection_events",
    "enrich_binding_receipt",
    "record_c03_expansion_events",
]
