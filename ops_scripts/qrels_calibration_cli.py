#!/usr/bin/env python3
"""Governed QRELS Calibration CLI: 1-by-1 Blind 4-Passage Chat Panel, Pure-White Studio UI, & Pooling (DIE Parity)."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.qrels.qrels_human_store import (  # noqa: E402
    DEFAULT_QRELS_HUMAN_STORE_REL_PATH,
    ExternalQrelsHumanStore,
)
from apps_eval.qrels.qrels_rubric_contract import (  # noqa: E402
    ALLOWED_QRELS_GRADES,
    QRELS_GRADE_ANCHORS,
    load_and_verify_qrels_rubric,
)
from apps_eval.qrels.qrels_studio_server import create_qrels_studio_server  # noqa: E402
from apps_eval.qrels.trec_pooling import build_blind_four_passage_panel  # noqa: E402
from apps_eval.qrels.weight_calibration import run_holdout_isolated_weight_calibration  # noqa: E402
from tools.audit_qrels_coverage import audit_qrels_coverage  # noqa: E402


def format_one_by_one_blind_qrels_chat_panel(
    panel: Mapping[str, Any],
    *,
    anchor_index: int = 1,
    anchor_total: int = 5,
) -> str:
    """Render strictly one blind QRELS query with 4 shuffled A/B/C/D passages and compact 3-2-1-0 legend."""
    legend_rows = [
        "| Score | Meaning |",
        "| :---: | :--- |",
    ]
    for g in ("3", "2", "1", "0"):
        spec = QRELS_GRADE_ANCHORS[g]
        legend_rows.append(f"| **{g}** | **{spec['short_label']}**: {spec['meaning']} |")
    legend = "\n".join(legend_rows)

    passage_blocks: list[str] = []
    for p in panel.get("passages") or []:
        slot = str(p["slot"])
        core = str(p.get("core_statement") or "").strip()
        footer = str(p.get("boilerplate_footer") or "").strip()
        block = f"#### Passage {slot}\n**Core Statement:** {core}"
        if footer:
            block += f"\n> *Reference Only (do not grade): {footer}*"
        passage_blocks.append(block)

    return (
        f"### Blind QRELS Gold Anchor ({anchor_index} of {anchor_total})\n\n"
        f"{legend}\n\n"
        f"**Query ({panel.get('surface', 'candidate_graph')} / {panel.get('target_section', 'general')}):** "
        f"{panel.get('query_text', '')}\n\n"
        + "\n\n".join(passage_blocks)
        + "\n\nReply with four scores (`0` to `3`), for example: `A=3, B=1, C=0, D=0`\n"
    )


def parse_four_passage_chat_reply(raw_reply: str) -> dict[str, int]:
    """Parse compact `A=3, B=1, C=0, D=0` human reply deterministically."""
    clean = str(raw_reply or "").strip()
    if not clean:
        raise ValueError("Four-passage reply cannot be empty.")
    grades: dict[str, int] = {}
    for token in re.split(r"[,;\n]+", clean):
        part = token.strip()
        if not part or "=" not in part:
            continue
        k_raw, v_raw = (x.strip() for x in part.split("=", 1))
        slot = k_raw.upper()
        if slot not in {"A", "B", "C", "D"}:
            raise ValueError(f"Unknown passage slot {slot!r}; expected A, B, C, or D.")
        grade = int(v_raw)
        if grade not in ALLOWED_QRELS_GRADES:
            raise ValueError(f"Grade for slot {slot} must be 0..3, got {grade}.")
        grades[slot] = grade
    if set(grades.keys()) != {"A", "B", "C", "D"}:
        raise ValueError("All four slots (A, B, C, D) must be scored.")
    return grades


def cmd_anchor_chat(pool_path: Path, query_id: str | None, seed: int) -> dict[str, Any]:
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    queries = pool.get("queries") or []
    if not queries:
        raise ValueError(f"No pooled queries found in {pool_path}.")
    target_q = next((q for q in queries if q.get("query_id") == query_id), None) if query_id else queries[0]
    if target_q is None:
        raise ValueError(f"Query id {query_id!r} not found in {pool_path}.")
    panel, slot_map = build_blind_four_passage_panel(target_q, seed=seed)
    markdown = format_one_by_one_blind_qrels_chat_panel(panel, anchor_index=1, anchor_total=min(5, len(queries)))
    return {
        "status": "PASS",
        "command": "qrels-anchor-chat",
        "query_id": panel["query_id"],
        "sealed_slot_map": slot_map,
        "markdown": markdown,
    }


def cmd_grade(args: argparse.Namespace) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    store = ExternalQrelsHumanStore(store_path=args.store, rubric_path=args.rubric)
    if args.quarantine:
        q = store.append_quarantine(
            {
                "pair_id": f"{args.query_id}::{args.record_id}",
                "query_id": args.query_id,
                "record_id": args.record_id,
                "surface": args.surface,
                "topic_family": args.topic_family,
                "partition": args.partition,
                "artifact_sha256": args.artifact_sha256,
                "reason": args.quarantine,
                "annotator_id": args.annotator,
                "recorded_at_utc": now_utc,
                "notes": args.notes or "",
            }
        )
        return {"status": "PASS", "command": "qrels-grade", "quarantined": q.to_dict()}

    atomic_checks = json.loads(args.atomic_checks) if args.atomic_checks else {}
    rejection_tags = [t.strip() for t in (args.rejection_tags or "").split(",") if t.strip()]
    rec = store.append_grade(
        {
            "pair_id": f"{args.query_id}::{args.record_id}",
            "query_id": args.query_id,
            "record_id": args.record_id,
            "surface": args.surface,
            "topic_family": args.topic_family,
            "partition": args.partition,
            "artifact_sha256": args.artifact_sha256,
            "relevance_grade": int(args.grade),
            "atomic_checks": atomic_checks,
            "rejection_tags": rejection_tags,
            "critique_rationale": args.notes or "",
            "annotator_id": args.annotator,
            "graded_at_utc": now_utc,
            "notes": args.notes or "",
        },
        require_grade0_rationale=True,
    )
    return {"status": "PASS", "command": "qrels-grade", "record": rec.to_dict()}


def cmd_studio_ui(args: argparse.Namespace) -> dict[str, Any]:
    server = create_qrels_studio_server(
        pool_path=args.pool,
        store_path=args.store,
        rubric_path=args.rubric,
        host=args.host,
        port=args.port,
        annotator_id=args.annotator,
        seed=args.seed,
        max_items=args.max_items,
    )
    url = f"http://{args.host}:{args.port}/"
    print(f"Pure-White Blind QRELS Calibration Studio: {url}")
    if not args.no_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return {"status": "PASS", "command": "qrels-studio-ui", "url": url}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Governed DIE-Parity QRELS Calibration CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_chat = sub.add_parser("qrels-anchor-chat", help="Render a single 1-by-1 blind 4-passage A/B/C/D chat panel")
    p_chat.add_argument("--pool", type=Path, default=REPO_ROOT / "data/qrels/qrels_authentic_candidate_pool.v1.json")
    p_chat.add_argument("--query-id", default=None)
    p_chat.add_argument("--seed", type=int, default=42)
    p_chat.add_argument("--json", action="store_true")

    p_grade = sub.add_parser("qrels-grade", help="Record a single human QRELS grade or quarantine disposition")
    p_grade.add_argument("--query-id", required=True)
    p_grade.add_argument("--record-id", required=True)
    p_grade.add_argument("--artifact-sha256", required=True)
    p_grade.add_argument("--surface", default="candidate_graph")
    p_grade.add_argument("--topic-family", default="topic_general")
    p_grade.add_argument("--partition", default="calibration")
    p_grade.add_argument("--grade", type=int, default=None)
    p_grade.add_argument("--atomic-checks", default=None)
    p_grade.add_argument("--rejection-tags", default="")
    p_grade.add_argument("--quarantine", default=None)
    p_grade.add_argument("--notes", default="")
    p_grade.add_argument("--annotator", default="amit.ayer")
    p_grade.add_argument("--store", type=Path, default=REPO_ROOT / DEFAULT_QRELS_HUMAN_STORE_REL_PATH)
    p_grade.add_argument("--rubric", type=Path, default=None)

    p_ui = sub.add_parser("qrels-studio-ui", help="Launch pure-white (#ffffff) Click-to-Grade QRELS Studio")
    p_ui.add_argument("--pool", type=Path, default=REPO_ROOT / "data/qrels/qrels_authentic_candidate_pool.v1.json")
    p_ui.add_argument("--store", type=Path, default=REPO_ROOT / DEFAULT_QRELS_HUMAN_STORE_REL_PATH)
    p_ui.add_argument("--rubric", type=Path, default=None)
    p_ui.add_argument("--host", default="127.0.0.1")
    p_ui.add_argument("--port", type=int, default=8767)
    p_ui.add_argument("--annotator", default="amit.ayer")
    p_ui.add_argument("--seed", type=int, default=42)
    p_ui.add_argument("--max-items", type=int, default=None)
    p_ui.add_argument("--no-browser", action="store_true")

    p_rubric = sub.add_parser("qrels-verify-rubric", help="Verify external_qrels_rubric_v1.json integrity")
    p_rubric.add_argument("--rubric", type=Path, default=None)

    p_audit = sub.add_parser("qrels-audit", help="Run fail-closed QRELS coverage, leakage, and Kappa gate")
    p_audit.add_argument("--partitions", type=Path, default=REPO_ROOT / "data/qrels/qrels_partitions.v1.json")
    p_audit.add_argument("--ground-truth", type=Path, default=REPO_ROOT / "data/qrels/qrels_independent_ground_truth.v1.json")
    p_audit.add_argument("--pool", type=Path, default=REPO_ROOT / "data/qrels/qrels_authentic_candidate_pool.v1.json")
    p_audit.add_argument("--output", type=Path, default=None)

    p_opt = sub.add_parser("qrels-optimize", help="Run holdout-isolated 1,771-point 4-simplex weight sweep")
    p_opt.add_argument("--partitions", type=Path, default=REPO_ROOT / "data/qrels/qrels_partitions.v1.json")
    p_opt.add_argument("--ground-truth", type=Path, default=REPO_ROOT / "data/qrels/qrels_independent_ground_truth.v1.json")
    p_opt.add_argument("--output", type=Path, default=REPO_ROOT / "data/qrels/qrels_weight_calibration_results.v1.json")
    p_opt.add_argument("--step", type=float, default=0.05)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "qrels-anchor-chat":
        res = cmd_anchor_chat(args.pool, args.query_id, args.seed)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res["markdown"])
        return 0
    if args.cmd == "qrels-grade":
        res = cmd_grade(args)
        print(json.dumps(res, indent=2))
        return 0
    if args.cmd == "qrels-studio-ui":
        cmd_studio_ui(args)
        return 0
    if args.cmd == "qrels-verify-rubric":
        rubric = load_and_verify_qrels_rubric(args.rubric)
        print(json.dumps({"status": "PASS", "rubric_id": rubric["rubric_id"], "rubric_sha256": rubric["rubric_sha256"]}, indent=2))
        return 0
    if args.cmd == "qrels-audit":
        rep = audit_qrels_coverage(args.partitions, args.ground_truth, args.pool, receipt_output_path=args.output)
        print(json.dumps(rep, indent=2))
        return 0 if rep["gate_status"] == "PASS" else 1
    if args.cmd == "qrels-optimize":
        gt_data = json.loads(args.ground_truth.read_text(encoding="utf-8"))
        part_data = json.loads(args.partitions.read_text(encoding="utf-8"))
        rep = run_holdout_isolated_weight_calibration(
            gt_data, part_data, grid_step=args.step, output_path=args.output
        )
        print(json.dumps(rep, indent=2))
        return 0 if rep["is_validated"] else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
