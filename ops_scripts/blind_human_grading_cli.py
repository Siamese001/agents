#!/usr/bin/env python3
"""Interactive blind one-by-one human grading and offline CSV sheet intake CLI for IDE judge calibration."""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.graders.judge.gold_corpus import (
    build_blind_grading_packet,
    export_blind_review_sheet_csv,
    import_blind_review_sheet_csv,
    load_external_stakeholder_rubric,
    load_gold_candidates_jsonl,
)
from apps_eval.graders.judge.human_provenance import (
    append_human_grade_entry,
    load_human_grade_ledger,
    unseal_and_adjudicate_human_gold,
    verify_human_label_ledger,
)

ENGINE_FILES = {
    "resume_engine": {
        "candidates": "data/judge_calibration/resume_gold_candidates.v1.jsonl",
        "ledger": "data/judge_calibration/resume_human_gold.v1.jsonl",
        "packet": "artifacts/eval_harness/blind_packets/resume_blind_prompts.v1.json",
        "sealed": "artifacts/eval_harness/blind_packets/resume_sealed_mapping.v1.json",
        "adjudicated": "data/judge_calibration/resume_human_adjudicated.v1.json",
    },
    "outreach_engine": {
        "candidates": "data/judge_calibration/outreach_gold_candidates.v1.jsonl",
        "ledger": "data/judge_calibration/outreach_human_gold.v1.jsonl",
        "packet": "artifacts/eval_harness/blind_packets/outreach_blind_prompts.v1.json",
        "sealed": "artifacts/eval_harness/blind_packets/outreach_sealed_mapping.v1.json",
        "adjudicated": "data/judge_calibration/outreach_human_adjudicated.v1.json",
    },
}


def _cmd_init_packet(engine: str, seed: str | None, repo_root: Path) -> dict[str, Any]:
    cfg = ENGINE_FILES[engine]
    candidates = load_gold_candidates_jsonl(repo_root / cfg["candidates"])
    eff_seed = seed or secrets.token_hex(16)
    pkt = build_blind_grading_packet(candidates, engine=engine, blinding_seed=eff_seed, repeat_count=3, repo_root=repo_root)
    pkt_path = repo_root / cfg["packet"]
    sealed_path = repo_root / cfg["sealed"]
    pkt_path.parent.mkdir(parents=True, exist_ok=True)
    pkt_path.write_text(
        json.dumps(
            {
                "engine": pkt.engine,
                "rubric_id": pkt.rubric_id,
                "rubric_sha256": pkt.rubric_sha256,
                "prompts": [p.to_dict() for p in pkt.prompts],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    sealed_path.write_text(json.dumps(pkt.sealed_mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"engine": engine, "prompt_count": len(pkt.prompts), "packet_path": str(pkt_path), "sealed_path": str(sealed_path)}


def _cmd_next_item(engine: str, repo_root: Path) -> dict[str, Any]:
    cfg = ENGINE_FILES[engine]
    pkt_doc = json.loads((repo_root / cfg["packet"]).read_text(encoding="utf-8"))
    graded_ids = {e.blind_id for e in load_human_grade_ledger(repo_root / cfg["ledger"])}
    for idx, p in enumerate(pkt_doc["prompts"], start=1):
        if p["blind_id"] not in graded_ids:
            rubric_doc, _ = load_external_stakeholder_rubric(engine, repo_root=repo_root)
            return {
                "done": False,
                "position": f"{idx}/{len(pkt_doc['prompts'])}",
                "prompt": p,
                "dimensions": [{"id": d["id"], "name": d["name"], "anchors": d.get("anchors", {})} for d in rubric_doc["dimensions"]],
                "hard_fail_flags": [{"id": f["id"], "definition": f["definition"]} for f in rubric_doc["hard_fail_flags"]],
            }
    return {"done": True, "graded_count": len(graded_ids), "total_prompts": len(pkt_doc["prompts"])}


def _cmd_status(engine: str, repo_root: Path) -> dict[str, Any]:
    cfg = ENGINE_FILES[engine]
    ledger_path = repo_root / cfg["ledger"]
    if not ledger_path.is_file():
        return {"engine": engine, "status": "PENDING_HUMAN_GRADING", "entry_count": 0, "valid": True, "violations": []}
    ok, viols, summary = verify_human_label_ledger(ledger_path)
    return {"engine": engine, "status": "VERIFIED" if ok else "INVALID", "valid": ok, "violations": viols, **summary}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blind human grading and provenance ledger CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-packet")
    p_init.add_argument("--engine", choices=sorted(ENGINE_FILES), required=True)
    p_init.add_argument("--seed", default=None)

    p_next = sub.add_parser("next-item")
    p_next.add_argument("--engine", choices=sorted(ENGINE_FILES), required=True)

    p_rec = sub.add_parser("record-grade")
    p_rec.add_argument("--engine", choices=sorted(ENGINE_FILES), required=True)
    p_rec.add_argument("--blind-id", required=True)
    p_rec.add_argument("--scores-json", required=True)
    p_rec.add_argument("--flags-json", default="{}")
    p_rec.add_argument("--overall-pass", choices=["true", "false"], required=True)
    p_rec.add_argument("--conversation-id", required=True)
    p_rec.add_argument("--notes", default="")

    p_exp = sub.add_parser("export-sheet")
    p_exp.add_argument("--engine", choices=sorted(ENGINE_FILES), required=True)
    p_exp.add_argument("--out", required=True)
    p_exp.add_argument("--seed", default=None)

    p_imp = sub.add_parser("import-sheet")
    p_imp.add_argument("--engine", choices=sorted(ENGINE_FILES), required=True)
    p_imp.add_argument("--sheet", required=True)

    p_stat = sub.add_parser("status")
    p_stat.add_argument("--engine", choices=sorted(ENGINE_FILES) + ["all"], default="all")

    p_uns = sub.add_parser("unseal")
    p_uns.add_argument("--engine", choices=sorted(ENGINE_FILES), required=True)

    args = parser.parse_args(argv)
    if args.cmd == "init-packet":
        print(json.dumps(_cmd_init_packet(args.engine, args.seed, REPO_ROOT), indent=2))
        return 0
    if args.cmd == "next-item":
        print(json.dumps(_cmd_next_item(args.engine, REPO_ROOT), indent=2))
        return 0
    if args.cmd == "record-grade":
        cfg = ENGINE_FILES[args.engine]
        pkt_doc = json.loads((REPO_ROOT / cfg["packet"]).read_text(encoding="utf-8"))
        match = next((p for p in pkt_doc["prompts"] if p["blind_id"] == args.blind_id), None)
        if match is None:
            raise SystemExit(f"Unknown blind_id {args.blind_id!r}")
        entry = append_human_grade_entry(
            REPO_ROOT / cfg["ledger"],
            blind_id=args.blind_id,
            engine=args.engine,
            prompt_sha256=match["prompt_sha256"],
            dimension_scores=json.loads(args.scores_json),
            hard_fail_flags=json.loads(args.flags_json),
            overall_pass=(args.overall_pass == "true"),
            provenance_mode="in_chat_blind",
            provenance_ref=args.conversation_id,
            reviewer_notes=args.notes,
            repo_root=REPO_ROOT,
        )
        print(json.dumps(entry.to_dict(), indent=2))
        return 0
    if args.cmd == "export-sheet":
        cfg = ENGINE_FILES[args.engine]
        candidates = load_gold_candidates_jsonl(REPO_ROOT / cfg["candidates"])
        pkt = build_blind_grading_packet(
            candidates, engine=args.engine, blinding_seed=args.seed or secrets.token_hex(16), repeat_count=3, repo_root=REPO_ROOT
        )
        out = export_blind_review_sheet_csv(pkt, Path(args.out), repo_root=REPO_ROOT)
        print(json.dumps({"exported_csv": str(out), "prompt_count": len(pkt.prompts)}, indent=2))
        return 0
    if args.cmd == "import-sheet":
        cfg = ENGINE_FILES[args.engine]
        rows = import_blind_review_sheet_csv(Path(args.sheet), engine=args.engine, repo_root=REPO_ROOT)
        ledger = REPO_ROOT / cfg["ledger"]
        for row in rows:
            append_human_grade_entry(
                ledger,
                blind_id=row["blind_id"],
                engine=args.engine,
                prompt_sha256=row["prompt_sha256"],
                dimension_scores=row["dimension_scores"],
                hard_fail_flags=row["hard_fail_flags"],
                overall_pass=row["overall_pass"],
                provenance_mode="offline_sheet_import",
                provenance_ref=row["source_sheet_sha256"],
                reviewer_notes=row["reviewer_notes"],
                recorded_at=row["recorded_at"],
                repo_root=REPO_ROOT,
            )
        print(json.dumps({"imported_entries": len(rows), "ledger": str(ledger)}, indent=2))
        return 0
    if args.cmd == "status":
        engines = sorted(ENGINE_FILES) if args.engine == "all" else [args.engine]
        print(json.dumps([_cmd_status(e, REPO_ROOT) for e in engines], indent=2))
        return 0
    if args.cmd == "unseal":
        cfg = ENGINE_FILES[args.engine]
        sealed = json.loads((REPO_ROOT / cfg["sealed"]).read_text(encoding="utf-8"))
        adj = unseal_and_adjudicate_human_gold(REPO_ROOT / cfg["ledger"], sealed)
        out_path = REPO_ROOT / cfg["adjudicated"]
        out_path.write_text(json.dumps(adj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"adjudicated_path": str(out_path), "adjudicated_count": adj["adjudicated_count"], "intra_rater_repeat_kappa": adj["intra_rater_repeat_kappa"]}, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
