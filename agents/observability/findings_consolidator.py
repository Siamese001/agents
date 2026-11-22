"""Multi-surface findings consolidator and root-cause FailureCluster builder.

Explicitly keeps (source_root, output_root) distinct for hermetic sandbox execution
and enforces a single canonical correction schema (source_identifier with safe alias fallback).
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from apps_eval.contracts.digests import stable_id
from apps_eval.contracts.schemas import FailureCluster, FindingRecord, PriorityLevel, TrackName
from apps_eval.online_grader import load_online_eval_records

_APP_TO_SUBSYSTEM: dict[str, str] = {
    "apps_rg": "resume_graph_engine",
    "apps_lic": "outreach_engine",
    "apps_research": "apps_research",
    "agents_core": "agents",
    "agents_cli": "agents",
    "antigravity_turn": "tools",
}

_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}


def _collect_online_eval_findings(
    source_root: Path,
    queue: SqliteFindingsQueueStore,
    *,
    cutoff_utc: str | None,
    online_ledger_path: Path | None = None,
) -> int:
    ledger = online_ledger_path if online_ledger_path is not None else (source_root / "online_eval_ledger.jsonl")
    records = load_online_eval_records(ledger)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        if rec.get("passed") is True:
            continue
        app_id = str(rec.get("app_id") or "agents_core")
        failed_gates = sorted(str(g) for g in (rec.get("failed_gates") or []) if g)
        gate_sig = ",".join(failed_gates) or "unknown_online_failure"
        grouped[(app_id, gate_sig)].append(rec)

    upserted = 0
    for (app_id, gate_sig), rows in sorted(grouped.items()):
        seen_times = [str(r.get("trace_finished_at_utc") or r.get("evaluated_at_utc") or "") for r in rows]
        latest_seen = max((t for t in seen_times if t), default=None)
        trace_ids = [str(r.get("trace_id") or "") for r in rows if r.get("trace_id")]
        run_ids = sorted({str(r.get("run_id") or "") for r in rows if r.get("run_id")})
        session_ids = sorted({str(r.get("session_id") or "") for r in rows if r.get("session_id")})
        priority: PriorityLevel = "P0" if "terminal_success" in gate_sig or len(rows) >= 5 else "P1"
        track: TrackName = (
            "TRACK_1_CALIBRATION"
            if gate_sig == "latency_sla"
            else "TRACK_2_CODE_FIX"
        )
        bucket = f"{app_id}_{gate_sig.split(',')[0]}_defect"
        queue.upsert_finding(
            source_surface="online_eval",
            app_id=app_id,
            failed_gate_signature=gate_sig,
            root_cause_bucket=bucket,
            owner_subsystem=_APP_TO_SUBSYSTEM.get(app_id, "agents"),
            track=track,
            priority=priority,
            title=f"{app_id} online eval failure ({gate_sig})",
            summary=f"{len(rows)} failed post-runtime trace(s) on gates [{gate_sig}].",
            recommended_action=f"Inspect failing traces for {app_id} and resolve {gate_sig}.",
            occurrence_count=len(rows),
            sample_trace_ids=trace_ids,
            metadata={"run_ids": run_ids, "session_ids": session_ids},
            seen_at_utc=latest_seen,
            cutoff_utc=cutoff_utc,
        )
        upserted += 1
    return upserted


def _collect_operator_correction_findings(
    source_root: Path,
    queue: SqliteFindingsQueueStore,
    *,
    cutoff_utc: str | None,
    min_recurrence: int = 2,
) -> int:
    corr_path = source_root / "operator_corrections.jsonl"
    if not corr_path.is_file():
        return 0
    retracted: set[str] = set()
    rows: list[dict[str, Any]] = []
    for line in corr_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if obj.get("retracted") is True and obj.get("correction_id"):
            retracted.add(str(obj["correction_id"]))
        else:
            rows.append(obj)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cid = str(row.get("correction_id") or "")
        if cid and cid in retracted:
            continue
        # Canonical key is source_identifier (fixing DIE's original_identifier mismatch bug).
        src = str(
            row.get("source_identifier")
            or row.get("original_identifier")
            or row.get("original")
            or ""
        ).strip()
        tgt = str(row.get("corrected_identifier") or row.get("corrected") or "").strip()
        cat = str(row.get("category") or "general").strip()
        if not src or not tgt:
            continue
        grouped[(cat, src)].append({**row, "_src": src, "_tgt": tgt})

    upserted = 0
    for (cat, src), items in sorted(grouped.items()):
        targets = sorted({str(i["_tgt"]) for i in items})
        conflict = len(targets) > 1
        unique_votes = {
            (str(i.get("operator_id") or "op"), str(i.get("session_id") or ""), str(i["_tgt"]))
            for i in items
        }
        if len(unique_votes) < min_recurrence:
            continue
        latest_seen = max((str(i.get("recorded_at") or "") for i in items), default=None) or None
        priority: PriorityLevel = "P1" if len(unique_votes) >= 3 else "P2"
        queue.upsert_finding(
            source_surface="operator_correction",
            app_id=str(items[0].get("app_id") or "agents_core"),
            failed_gate_signature=f"correction:{cat}",
            root_cause_bucket=f"correction_{cat}_{src[:40]}",
            owner_subsystem=_APP_TO_SUBSYSTEM.get(str(items[0].get("app_id") or ""), "agents"),
            track="TRACK_1_CALIBRATION",
            priority=priority,
            title=f"Recurring operator correction ({cat}: {src})",
            summary=f"{len(unique_votes)} confirmed operator corrections for '{src}' -> {targets}.",
            recommended_action=(
                "Resolve conflicting operator correction targets before proposing calibration."
                if conflict
                else f"Synthesize bounded calibration or prior update for '{src}' -> '{targets[0]}'."
            ),
            occurrence_count=len(unique_votes),
            sample_trace_ids=[str(i.get("correction_id") or "") for i in items if i.get("correction_id")],
            metadata={
                "source_identifier": src,
                "targets": targets,
                "conflict_detected": conflict,
                "session_ids": sorted({str(i.get("session_id") or "") for i in items if i.get("session_id")}),
            },
            seen_at_utc=latest_seen,
            cutoff_utc=cutoff_utc,
        )
        upserted += 1
    return upserted


def _collect_hitl_override_findings(
    hitl_db_path: Path | None,
    queue: SqliteFindingsQueueStore,
    *,
    cutoff_utc: str | None,
) -> int:
    if hitl_db_path is None or not hitl_db_path.is_file():
        return 0
    conn = sqlite3.connect(f"file:{hitl_db_path}?mode=ro", uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "hitl_decisions" not in tables:
            return 0
        cols = {r[1] for r in conn.execute("PRAGMA table_info(hitl_decisions)").fetchall()}
        if "category" not in cols or "outcome" not in cols:
            return 0
        rows = conn.execute(
            "SELECT * FROM hitl_decisions WHERE UPPER(outcome) = 'OVERRIDDEN'"
        ).fetchall()
    finally:
        conn.close()

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_cat[str(r["category"] or "general")].append(dict(r))

    upserted = 0
    for cat, items in sorted(by_cat.items()):
        if len(items) < 2:
            continue
        queue.upsert_finding(
            source_surface="hitl_override",
            app_id="antigravity_turn",
            failed_gate_signature=f"hitl_override:{cat}",
            root_cause_bucket=f"hitl_calibration_{cat}",
            owner_subsystem="tools",
            track="TRACK_1_CALIBRATION",
            priority="P1" if len(items) >= 3 else "P2",
            title=f"Recurring HITL overrides in category '{cat}'",
            summary=f"{len(items)} operator overrides recorded in hitl_decisions.sqlite.",
            recommended_action=f"Recalibrate HITL confidence prior or ambiguity margin for '{cat}'.",
            occurrence_count=len(items),
            sample_trace_ids=[str(i.get("decision_id") or "") for i in items if i.get("decision_id")],
            metadata={"category": cat, "override_count": len(items)},
            cutoff_utc=cutoff_utc,
        )
        upserted += 1
    return upserted


def _collect_feedback_store_findings(
    feedback_db_path: Path | None,
    queue: SqliteFindingsQueueStore,
    *,
    cutoff_utc: str | None,
) -> int:
    if feedback_db_path is None or not feedback_db_path.is_file():
        return 0
    conn = sqlite3.connect(f"file:{feedback_db_path}?mode=ro", uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "failure_signatures" not in tables:
            return 0
        rows = conn.execute(
            "SELECT * FROM failure_signatures WHERE occurrence_count >= 2 AND success_rate < 0.80"
        ).fetchall()
    finally:
        conn.close()

    upserted = 0
    for row in rows:
        constraint = str(row["normalized_constraint"] or "")
        app_id = "apps_rg" if "apps_rg" in constraint else ("apps_lic" if "apps_lic" in constraint else "agents_core")
        queue.upsert_finding(
            source_surface="feedback_store",
            app_id=app_id,
            failed_gate_signature=str(row["failure_kind"] or "unknown"),
            root_cause_bucket=f"sig_{str(row['signature_hash'])[:10]}",
            owner_subsystem=_APP_TO_SUBSYSTEM.get(app_id, "agents"),
            track="TRACK_2_CODE_FIX",
            priority="P1" if int(row["occurrence_count"]) >= 3 else "P2",
            title=f"Unresolved recurring failure signature ({constraint[:64]})",
            summary=f"Occurred {row['occurrence_count']}x with verified success_rate={row['success_rate']}.",
            recommended_action=f"Investigate and pin regression test for constraint '{constraint[:80]}'.",
            occurrence_count=int(row["occurrence_count"]),
            sample_trace_ids=[str(row["signature_hash"])],
            metadata={"normalized_constraint": constraint, "success_rate": float(row["success_rate"])},
            cutoff_utc=cutoff_utc,
        )
        upserted += 1
    return upserted


def _collect_triage_packet_findings(
    triage_root: Path | None,
    queue: SqliteFindingsQueueStore,
    *,
    cutoff_utc: str | None,
) -> int:
    if triage_root is None or not triage_root.is_dir():
        return 0
    upserted = 0
    for pkt_file in sorted(triage_root.rglob("*.json")):
        try:
            pkt = json.loads(pkt_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(pkt, dict) or str(pkt.get("status") or "").upper() in {
            "PROMOTED",
            "RESOLVED",
            "ARCHIVED",
        }:
            continue
        app_id = str(pkt.get("app_id") or "agents_core")
        fmode = str(
            pkt.get("failure_mode")
            or pkt.get("trigger_reason")
            or pkt.get("trigger_signal")
            or "triage_defect"
        )
        seen_ts = pkt.get("staged_at") or pkt.get("created_at")
        queue.upsert_finding(
            source_surface="eval_harness",
            app_id=app_id,
            failed_gate_signature=fmode,
            root_cause_bucket=f"triage_{app_id}_{fmode}",
            owner_subsystem=_APP_TO_SUBSYSTEM.get(app_id, "agents"),
            track="TRACK_2_CODE_FIX",
            priority="P1",
            title=f"Staged eval triage failure ({app_id}: {fmode})",
            summary=str(pkt.get("description") or f"Eval harness triage packet {pkt_file.name}"),
            recommended_action=f"Promote or fix staged eval failure {fmode} in {app_id}.",
            occurrence_count=1,
            sample_trace_ids=[str(pkt.get("candidate_id") or pkt_file.stem)],
            metadata={"packet_path": pkt_file.as_posix()},
            seen_at_utc=seen_ts,
            cutoff_utc=cutoff_utc,
        )
        upserted += 1
    return upserted


def build_failure_clusters(
    findings: Sequence[FindingRecord],
    *,
    min_occurrences_for_proposal: int = 3,
    min_sessions_for_proposal: int = 2,
) -> list[FailureCluster]:
    """Group OPEN findings by (owner_subsystem, root_cause_bucket) into actionable FailureClusters."""
    grouped: dict[tuple[str, str], list[FindingRecord]] = defaultdict(list)
    for f in findings:
        if f.status not in {"OPEN", "APPROVED"}:
            continue
        grouped[(f.owner_subsystem, f.root_cause_bucket)].append(f)

    clusters: list[FailureCluster] = []
    for (subsystem, bucket), members in sorted(grouped.items()):
        finding_ids = sorted(m.finding_id for m in members)
        run_ids: set[str] = set()
        session_ids: set[str] = set()
        conflict = False
        total_occ = 0
        for m in members:
            total_occ += m.occurrence_count
            if m.metadata.get("conflict_detected") is True:
                conflict = True
            for rid in m.metadata.get("run_ids") or []:
                run_ids.add(str(rid))
            for sid in m.metadata.get("session_ids") or []:
                session_ids.add(str(sid))
            for tid in m.sample_trace_ids:
                run_ids.add(str(tid))

        max_prio = min((m.priority for m in members), key=lambda p: _PRIORITY_RANK.get(p, 2))
        agg_impact = round(sum(m.impact_score for m in members), 2)
        unique_sessions = max(len(session_ids), min(len(run_ids), total_occ))
        track: TrackName = (
            "TRACK_2_CODE_FIX"
            if any(m.track == "TRACK_2_CODE_FIX" for m in members)
            else "TRACK_1_CALIBRATION"
        )
        eligible_golden = (total_occ >= 2 or max_prio == "P0") and not conflict
        eligible_proposal = (
            (total_occ >= min_occurrences_for_proposal and unique_sessions >= min_sessions_for_proposal)
            or max_prio == "P0"
        ) and not conflict

        clusters.append(
            FailureCluster(
                cluster_id=stable_id("clst", subsystem, bucket, length=12),
                root_cause_bucket=bucket,
                owner_subsystem=subsystem,
                member_finding_ids=finding_ids,
                unique_run_ids=sorted(run_ids)[:50],
                unique_session_count=unique_sessions,
                max_priority=max_prio,
                aggregate_impact_score=agg_impact,
                conflict_detected=conflict,
                eligible_for_golden_promotion=eligible_golden,
                eligible_for_proposal_synthesis=eligible_proposal,
                recommended_track=track,
            )
        )

    clusters.sort(key=lambda c: (-c.aggregate_impact_score, c.cluster_id))
    return clusters


def consolidate_all_findings(
    source_root: Path,
    output_root: Path,
    *,
    online_ledger_path: Path | None = None,
    hitl_db_path: Path | None = None,
    feedback_db_path: Path | None = None,
    triage_root: Path | None = None,
    cutoff_utc: str | None = None,
) -> dict[str, Any]:
    """Consolidate all signal surfaces from source_root into output_root's SQLite queue & snapshot."""
    src = Path(source_root).resolve()
    out = Path(output_root).resolve()
    out.mkdir(parents=True, exist_ok=True)

    queue_db = out / "remediation_queue.sqlite"
    snapshot_path = out / "remediation_queue_snapshot.json"
    queue = SqliteFindingsQueueStore(queue_db)
    try:
        counts = {
            "online_eval": _collect_online_eval_findings(
                src,
                queue,
                cutoff_utc=cutoff_utc,
                online_ledger_path=online_ledger_path,
            ),
            "operator_correction": _collect_operator_correction_findings(src, queue, cutoff_utc=cutoff_utc),
            "hitl_override": _collect_hitl_override_findings(hitl_db_path, queue, cutoff_utc=cutoff_utc),
            "feedback_store": _collect_feedback_store_findings(feedback_db_path, queue, cutoff_utc=cutoff_utc),
            "eval_harness": _collect_triage_packet_findings(triage_root, queue, cutoff_utc=cutoff_utc),
        }
        snapshot = queue.export_snapshot(snapshot_path)
        all_findings = queue.list_findings(limit=5000)
        clusters = build_failure_clusters(all_findings)
    finally:
        queue.close()

    return {
        "source_root": src.as_posix(),
        "output_root": out.as_posix(),
        "queue_db_path": queue_db.as_posix(),
        "snapshot_path": snapshot_path.as_posix(),
        "ingested_by_surface": counts,
        "total_findings": snapshot["total_findings"],
        "counts_by_status": snapshot["counts_by_status"],
        "counts_by_track": snapshot["counts_by_track"],
        "cluster_count": len(clusters),
        "clusters": [c.to_dict() for c in clusters],
        "marginal_api_cost_usd": 0.0,
    }
