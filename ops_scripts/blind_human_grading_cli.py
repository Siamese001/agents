#!/usr/bin/env python3
"""Interactive blind one-by-one human grading, DIE Calibration Studio UI launcher, and offline CSV intake CLI."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import secrets
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.graders.judge.studio_session_binder import handle_judge_calibrate_ui
from apps_eval.graders.judge.external_rubric_store import (
    EXTERNAL_RUBRIC_DIMENSIONS,
    VALID_JUDGE_SURFACES,
    VALID_PARTITIONS,
    ExternalRubricHumanStore,
    compute_payload_sha256,
    load_and_verify_external_rubric,
    validate_human_annotator_id,
)
from apps_eval.graders.judge.gold_corpus import (
    build_blind_grading_packet,
    build_studio_blind_pool_dict,
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
        "pool": "artifacts/eval_harness/blind_packets/resume_blind_pool.v1.json",
        "sealed": "artifacts/eval_harness/blind_packets/resume_sealed_mapping.v1.json",
        "adjudicated": "data/judge_calibration/resume_human_adjudicated.v1.json",
    },
    "outreach_engine": {
        "candidates": "data/judge_calibration/outreach_gold_candidates.v1.jsonl",
        "ledger": "data/judge_calibration/outreach_human_gold.v1.jsonl",
        "packet": "artifacts/eval_harness/blind_packets/outreach_blind_prompts.v1.json",
        "pool": "artifacts/eval_harness/blind_packets/outreach_blind_pool.v1.json",
        "sealed": "artifacts/eval_harness/blind_packets/outreach_sealed_mapping.v1.json",
        "adjudicated": "data/judge_calibration/outreach_human_adjudicated.v1.json",
    },
}

_COMPACT_KEY_MAP: dict[str, str] = {
    "f": "factual_faithfulness",
    "factual_faithfulness": "factual_faithfulness",
    "c": "completeness_and_relevance",
    "completeness_and_relevance": "completeness_and_relevance",
    "r": "cold_reader_clarity",
    "cold_reader_clarity": "cold_reader_clarity",
    "a": "actionability_and_proportion",
    "actionability_and_proportion": "actionability_and_proportion",
}


def parse_compact_human_grades(raw_grades: str) -> dict[str, int]:
    """Parse JSON or compact `F=4, C=5, R=4, A=4` human external rubric grades."""
    clean = str(raw_grades or "").strip()
    if not clean:
        raise ValueError("Grades input cannot be empty.")
    if clean.startswith("{"):
        parsed = json.loads(clean)
        if not isinstance(parsed, Mapping):
            raise ValueError("JSON grades payload must be an object.")
        return {
            _COMPACT_KEY_MAP.get(str(k).strip().lower(), str(k).strip()): int(v)
            for k, v in parsed.items()
            if not isinstance(v, bool)
        }
    grades: dict[str, int] = {}
    for token in re.split(r"[,;]+", clean):
        part = token.strip()
        if not part or "=" not in part:
            continue
        k_raw, v_raw = (x.strip() for x in part.split("=", 1))
        if k_raw.lower() == "verdict":
            continue
        mapped = _COMPACT_KEY_MAP.get(k_raw.lower())
        if mapped is None:
            raise ValueError(f"Unknown pillar key {k_raw!r}; use F, C, R, A.")
        grades[mapped] = int(v_raw)
    if set(grades.keys()) != set(EXTERNAL_RUBRIC_DIMENSIONS):
        raise ValueError("All four pillars (F, C, R, A) must be supplied.")
    return grades


def format_one_by_one_blind_chat_card(item: Mapping[str, Any], rubric: Mapping[str, Any]) -> str:
    """Render a single blind review card with separated prompt and compact 1-to-5 external rubric legend."""
    dims = rubric["dimensions"]
    rows = [
        "| Pillar Code | External Dimension | Score 1 (Severe Defect) | Score 3 (Acceptable) | Score 5 (Exemplary) |",
        "| :---: | :--- | :--- | :--- | :--- |",
    ]
    for code, dim_key in zip(("F", "C", "R", "A"), EXTERNAL_RUBRIC_DIMENSIONS):
        spec = dims[dim_key]
        rows.append(
            f"| **{code}** | {spec['title']} | {spec['anchors']['1']} | {spec['anchors']['3']} | {spec['anchors']['5']} |"
        )
    legend = "\n".join(rows)
    prompt_block = f"**Prompt Being Answered:** {item['prompt_text']}\n\n" if item.get("prompt_text") else ""
    body_text = str(item.get("core_answer_text") or item.get("blinded_text") or "")
    excerpts = item.get("source_evidence_excerpts") or []
    ev_lines = [
        f"- **{ev.get('source', 'Evidence')}**: {ev.get('excerpt', '')}"
        for ev in excerpts
        if isinstance(ev, Mapping)
    ]
    ev_block = ("#### Source Evidence Excerpts\n\n" + "\n".join(ev_lines) + "\n\n") if ev_lines else ""
    return (
        f"### Blind Human Calibration Item `{item['case_id']}`\n\n"
        f"- **Surface**: `{item['judge_surface']}` | **Partition**: `{item['partition']}` | "
        f"**Topic Family**: `{item['topic_family']}`\n"
        f"- **Artifact SHA-256**: `{item['artifact_sha256']}`\n\n"
        f"{legend}\n\n"
        f"#### Blinded Candidate Artifact\n\n"
        f"{prompt_block}{body_text}\n\n"
        f"{ev_block}"
        f"Reply with four 1-to-5 pillar grades and verdict, for example: "
        f"`F=4, C=5, R=4, A=4, Verdict=PASS`\n"
    )


def _cmd_init_packet(engine: str, seed: str | None, repo_root: Path) -> dict[str, Any]:
    cfg = ENGINE_FILES[engine]
    candidates = load_gold_candidates_jsonl(repo_root / cfg["candidates"])
    eff_seed = seed or secrets.token_hex(16)
    pkt = build_blind_grading_packet(
        candidates, engine=engine, blinding_seed=eff_seed, repeat_count=3, repo_root=repo_root
    )
    pkt_path = repo_root / cfg["packet"]
    sealed_path = repo_root / cfg["sealed"]
    pool_path = repo_root / cfg["pool"]
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
    studio_pool = build_studio_blind_pool_dict(candidates, engine=engine, repo_root=repo_root)
    pool_path.write_text(json.dumps(studio_pool, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "engine": engine,
        "prompt_count": len(pkt.prompts),
        "packet_path": str(pkt_path),
        "pool_path": str(pool_path),
        "sealed_path": str(sealed_path),
    }


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
                "dimensions": [
                    {"id": d["id"], "name": d["name"], "anchors": d.get("anchors", {})}
                    for d in rubric_doc["dimensions"]
                ],
                "hard_fail_flags": [
                    {"id": f["id"], "definition": f["definition"]} for f in rubric_doc["hard_fail_flags"]
                ],
            }
    return {"done": True, "graded_count": len(graded_ids), "total_prompts": len(pkt_doc["prompts"])}


def _cmd_status(engine: str, repo_root: Path) -> dict[str, Any]:
    cfg = ENGINE_FILES[engine]
    ledger_path = repo_root / cfg["ledger"]
    if not ledger_path.is_file():
        return {"engine": engine, "status": "PENDING_HUMAN_GRADING", "entry_count": 0, "valid": True, "violations": []}
    ok, viols, summary = verify_human_label_ledger(ledger_path)
    return {"engine": engine, "status": "VERIFIED" if ok else "INVALID", "valid": ok, "violations": viols, **summary}


def _cmd_judge_calibrate_sample(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    engine = "resume_engine" if "resume" in str(args.engine or "resume_engine") else "outreach_engine"
    cfg = ENGINE_FILES[engine]
    candidates = load_gold_candidates_jsonl(repo_root / cfg["candidates"])
    pool = build_studio_blind_pool_dict(
        candidates,
        engine=engine,
        partition=str(args.partition),
        presentation_seed=int(args.seed if args.seed is not None else 20260417),
        repo_root=repo_root,
    )
    items = list(pool["items"])[: max(1, int(args.limit))]
    pool["items"] = items
    pool["sample_count"] = len(items)
    rubric = load_and_verify_external_rubric(args.rubric_path)
    pool["first_item_chat_card"] = format_one_by_one_blind_chat_card(items[0], rubric) if items else ""
    out_p = Path(args.output) if args.output is not None else (repo_root / cfg["pool"])
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(pool, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return pool


def _cmd_judge_calibrate_grade(args: argparse.Namespace) -> dict[str, Any]:
    annotator = validate_human_annotator_id(args.annotator)
    cand_text = (
        Path(args.candidate_file).read_text(encoding="utf-8").strip()
        if getattr(args, "candidate_file", None) is not None
        else None
    )
    art_sha = str(args.artifact_sha256 or "").strip().lower() or (
        compute_payload_sha256(cand_text) if cand_text is not None else ""
    )
    store = ExternalRubricHumanStore(store_path=args.store_path, rubric_path=args.rubric_path)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    q_reason = getattr(args, "quarantine", None)
    if q_reason:
        q_rec = store.append_quarantine(
            {
                "case_id": args.case_id,
                "judge_surface": args.surface,
                "topic_family": args.topic_family,
                "partition": args.partition,
                "artifact_sha256": art_sha,
                "reason": q_reason,
                "annotator_id": annotator,
                "recorded_at_utc": now_utc,
                "notes": args.notes,
            }
        )
        return {"status": "PASS", "command": "judge-calibrate-grade", "quarantined": q_rec.to_dict()}
    if not args.grades or not args.verdict:
        raise ValueError("--grades and --verdict are required unless --quarantine is specified.")
    atomic_raw = json.loads(args.atomic_checks) if getattr(args, "atomic_checks", None) else {}
    saved = store.append_label(
        {
            "case_id": args.case_id,
            "judge_surface": args.surface,
            "topic_family": args.topic_family,
            "partition": args.partition,
            "artifact_sha256": art_sha,
            "external_rubric_id": "external_judge_rubric_v1",
            "external_rubric_sha256": store.rubric_sha256,
            "dimension_grades": parse_compact_human_grades(args.grades),
            "human_verdict": str(args.verdict).upper(),
            "atomic_checks": atomic_raw,
            "failure_tags": getattr(args, "failure_tags", ""),
            "critique_rationale": args.notes,
            "annotator_id": annotator,
            "graded_at_utc": now_utc,
            "notes": args.notes,
        },
        candidate_text=cand_text,
        require_fail_critique=True,
    )
    return {"status": "PASS", "command": "judge-calibrate-grade", "record": saved.to_dict()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blind human grading, Calibration Studio UI, and provenance ledger CLI.")
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

    p_samp = sub.add_parser("judge-calibrate-sample")
    p_samp.add_argument("--engine", choices=sorted(ENGINE_FILES), default="resume_engine")
    p_samp.add_argument("--partition", choices=sorted(VALID_PARTITIONS), default="dev")
    p_samp.add_argument("--limit", type=int, default=24)
    p_samp.add_argument("--output", type=Path, default=None)
    p_samp.add_argument("--rubric-path", type=Path, default=None)
    p_samp.add_argument("--seed", type=int, default=20260417)

    p_grade = sub.add_parser("judge-calibrate-grade")
    p_grade.add_argument("--case-id", required=True)
    p_grade.add_argument("--surface", default="resume_engine", choices=sorted(VALID_JUDGE_SURFACES))
    p_grade.add_argument("--partition", default="dev", choices=sorted(VALID_PARTITIONS))
    p_grade.add_argument("--topic-family", required=True)
    p_grade.add_argument("--candidate-file", type=Path, default=None)
    p_grade.add_argument("--artifact-sha256", default=None)
    p_grade.add_argument("--grades", default=None)
    p_grade.add_argument("--verdict", default=None, choices=["PASS", "FAIL", "pass", "fail"])
    p_grade.add_argument("--atomic-checks", default=None)
    p_grade.add_argument("--failure-tags", default="")
    p_grade.add_argument("--quarantine", default=None, choices=["ABSTAIN_INSUFFICIENT_EVIDENCE", "DEFECTIVE_PROMPT"])
    p_grade.add_argument("--annotator", required=True)
    p_grade.add_argument("--notes", default="")
    p_grade.add_argument("--store-path", type=Path, default=None)
    p_grade.add_argument("--rubric-path", type=Path, default=None)

    p_ui = sub.add_parser("judge-calibrate-ui")
    p_ui.add_argument("--pool", type=Path, required=True)
    p_ui.add_argument("--store-path", type=Path, default=None)
    p_ui.add_argument("--rubric-path", type=Path, default=None)
    p_ui.add_argument("--host", default="127.0.0.1")
    p_ui.add_argument("--port", type=int, default=8765)
    p_ui.add_argument("--annotator", default="amit.ayer")
    p_ui.add_argument("--seed", type=int, default=None)
    p_ui.add_argument("--check-only", action="store_true", default=False)

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
            candidates,
            engine=args.engine,
            blinding_seed=args.seed or secrets.token_hex(16),
            repeat_count=3,
            repo_root=REPO_ROOT,
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
        print(
            json.dumps(
                {
                    "adjudicated_path": str(out_path),
                    "adjudicated_count": adj["adjudicated_count"],
                    "intra_rater_repeat_kappa": adj["intra_rater_repeat_kappa"],
                },
                indent=2,
            )
        )
        return 0
    if args.cmd == "judge-calibrate-sample":
        res = _cmd_judge_calibrate_sample(args, REPO_ROOT)
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0
    if args.cmd == "judge-calibrate-grade":
        try:
            res = _cmd_judge_calibrate_grade(args)
            print(json.dumps(res, indent=2, sort_keys=True))
            return 0
        except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
            print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
            return 1
    if args.cmd == "judge-calibrate-ui":
        res = handle_judge_calibrate_ui(args)
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
