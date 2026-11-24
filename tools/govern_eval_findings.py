#!/usr/bin/env python3
"""Governed CLI for reviewing, approving, and fail-closed two-mode closeout verification in `agents`."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.observability.findings_consolidator import consolidate_all_findings
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from apps_eval._core_governance_bridge import verify_finding_closeout_proof


def _try_agents_trace_replay(runtime_root: Path, finding: Mapping[str, Any]) -> dict[str, Any]:
    traces_file = Path(runtime_root) / "run_traces.jsonl"
    sample_ids = set(str(s) for s in (finding.get("sample_trace_ids") or finding.get("sample_ids") or []) if s)
    if not sample_ids or not traces_file.is_file():
        return {"passed": False, "reason": "no_replayable_trace_samples"}
    from apps_eval.contracts.schemas import RunTrace
    from apps_eval.online_grader import grade_run_trace

    matched = 0
    for raw in traces_file.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        tid = str(obj.get("trace_id") or "")
        if tid not in sample_ids:
            continue
        verdict = grade_run_trace(RunTrace.from_dict(obj))
        if not verdict.get("passed"):
            return {"passed": False, "reason": f"trace_replay_failed:{tid}"}
        matched += 1
    if matched == 0:
        return {"passed": False, "reason": "sample_trace_ids_absent_from_run_traces"}
    return {"passed": True, "replayed_traces": matched}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Agents Evaluation Findings Governance & Closeout CLI")
    p.add_argument("--runtime-root", type=Path, default=_REPO_ROOT / "artifacts" / "learning")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    c_con = sub.add_parser("consolidate")
    c_con.add_argument("--cutoff-utc", default=None)

    c_lst = sub.add_parser("list")
    c_lst.add_argument("--status", default=None)
    c_lst.add_argument("--track", default=None)
    c_lst.add_argument("--limit", type=int, default=50)

    c_ins = sub.add_parser("inspect")
    c_ins.add_argument("finding_id")

    for act in ("approve", "reject"):
        ca = sub.add_parser(act)
        ca.add_argument("finding_id")
        ca.add_argument("--rationale", required=True)
        ca.add_argument("--operator-id", default="human_operator")

    c_snz = sub.add_parser("snooze")
    c_snz.add_argument("finding_id")
    c_snz.add_argument("--until-utc", required=True)
    c_snz.add_argument("--rationale", required=True)
    c_snz.add_argument("--operator-id", default="human_operator")

    c_ver = sub.add_parser("verify")
    c_ver.add_argument("finding_id")
    c_ver.add_argument("--rationale", required=True)
    c_ver.add_argument("--operator-id", default="human_operator")
    c_ver.add_argument("--proof-run-id", default=None)
    return p


def _dispatch(args: argparse.Namespace) -> Any:
    rt = Path(args.runtime_root).expanduser().resolve()
    rt.mkdir(parents=True, exist_ok=True)
    cmd = args.command
    if cmd == "consolidate":
        return consolidate_all_findings(rt, rt, cutoff_utc=args.cutoff_utc)

    q = SqliteFindingsQueueStore(rt / "remediation_queue.sqlite")
    try:
        if cmd == "list":
            return [f.to_dict() for f in q.list_findings(status=args.status, track=args.track, limit=args.limit)]
        if cmd == "inspect":
            rec = q.get_finding(args.finding_id)
            if rec is None:
                raise KeyError(f"Unknown finding_id: {args.finding_id}")
            return {"finding": rec.to_dict(), "events": q.list_events(args.finding_id)}
        if cmd in ("approve", "reject"):
            target = "APPROVED" if cmd == "approve" else "REJECTED"
            updated = q.transition_status(args.finding_id, target, actor=args.operator_id, rationale=args.rationale)
            q.export_snapshot(rt / "remediation_queue_snapshot.json")
            return {"finding": updated.to_dict()}
        if cmd == "snooze":
            updated = q.transition_status(
                args.finding_id, "SNOOZED", actor=args.operator_id, rationale=args.rationale, snoozed_until_utc=args.until_utc
            )
            q.export_snapshot(rt / "remediation_queue_snapshot.json")
            return {"finding": updated.to_dict()}

        rec = q.get_finding(args.finding_id)
        if rec is None:
            raise KeyError(f"Unknown finding_id: {args.finding_id}")
        if rec.status not in {"APPROVED", "IN_PROGRESS"}:
            raise ValueError(f"Cannot verify {args.finding_id} from status {rec.status}; expected APPROVED or IN_PROGRESS.")
        proof = verify_finding_closeout_proof(
            rt, rec.to_dict(), proof_run_id=args.proof_run_id, sample_replay_fn=_try_agents_trace_replay
        )
        updated = q.transition_status(
            args.finding_id,
            "VERIFIED",
            actor=args.operator_id,
            rationale=args.rationale,
            extra_metadata={"closeout_proof": proof},
        )
        q.export_snapshot(rt / "remediation_queue_snapshot.json")
        return {"finding": updated.to_dict(), "closeout_proof": proof}
    finally:
        q.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        res = _dispatch(args)
    except (KeyError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
