#!/usr/bin/env python3
"""Wave 4/5 Judge Parity Probe: evaluates real IDE CLI proof judges against historical keyed corpus + negative controls.

Usage:
  AGY_CLI_BIN=/path/to/agy .venv/bin/python ops_scripts/judge_parity_probe.py run \
      --lanes executive_summary,unify_bullets,headline --max-calls 24
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (str(REPO_ROOT / "resume_graph_engine" / "src"), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from apps_rg.runtime.judges import executive_summary_x1d as x1d_mod
from apps_rg.runtime.judges.competencies_x1d import COMPETENCIES_JUDGE_RESPONSE_SCHEMA
from apps_rg.runtime.judges.executive_summary_x1d import build_judge_response_schema
from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
from apps_rg.runtime.judges.x1d_ide_cli import call_ide_cli_judge

ALL_11_LANES = (
    "headline",
    "executive_summary",
    "competencies",
    "slalom_bullets",
    "slalom_narrative",
    "unify_bullets",
    "unify_narrative",
    "ibm_bullets",
    "ibm_narrative",
    "insurtech_bullets",
    "insurtech_narrative",
)


def _rankdata(vals: list[float]) -> list[float]:
    indexed = sorted(enumerate(vals), key=lambda kv: kv[1])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def spearman_rho(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    rx = _rankdata(xs)
    ry = _rankdata(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    deny = math.sqrt(sum((b - my) ** 2 for b in ry))
    if denx == 0.0 or deny == 0.0:
        return None
    return round(num / (denx * deny), 4)


def _replace_json_block_after_header(prompt_text: str, header: str, mutator) -> tuple[str, bool]:
    idx = prompt_text.find(header)
    if idx < 0:
        return prompt_text, False
    brace_idx = prompt_text.find("{", idx + len(header))
    bracket_idx = prompt_text.find("[", idx + len(header))
    candidates = [pos for pos in (brace_idx, bracket_idx) if pos >= 0]
    if not candidates:
        return prompt_text, False
    start = min(candidates)
    if "\n\n" in prompt_text[idx + len(header):start]:
        return prompt_text, False
    decoder = json.JSONDecoder()
    obj, end = decoder.raw_decode(prompt_text, start)
    new_obj = mutator(obj)
    rendered = json.dumps(new_obj, indent=2, ensure_ascii=False)
    return prompt_text[:start] + rendered + prompt_text[end:], True


def inject_fabricated_control(lane: str, base_prompt: str) -> tuple[str, str]:
    """Inject blatant ungrounded quantitative/employer claims absent from ALLOWED_FACT_PACKET."""
    defect = "Injected ungrounded '$940M Goldman Sachs sovereign trading P&L across 1,400 quant engineers' not in allowed facts"

    def _mutate(cand: Any) -> Any:
        if not isinstance(cand, dict):
            return cand
        out = json.loads(json.dumps(cand))
        if lane == "headline":
            fab = "SVP Quantum Trading | $940M Goldman Sachs P&L | 1,400 Quant Engineers | 99.99% Alpha"
            out["headline_line"] = fab
            out["resume_display_text"] = fab
        elif lane == "competencies":
            comps = out.get("competencies") or out.get("categories") or []
            if isinstance(comps, list) and comps:
                comps[0]["category_label"] = "Goldman Sachs $940M Sovereign Hedge Fund Trading"
                comps[0]["terms"] = [
                    "Managed 1,400 Goldman Sachs quant engineers generating $940M trading alpha",
                    "Certified Fedwire nuclear cryptography clearance across 82 central banks",
                ]
        elif "bullets" in out and isinstance(out["bullets"], list) and out["bullets"]:
            out["bullets"][0]["bullet_text"] = (
                "Directed 1,400 Goldman Sachs sovereign hedge-fund engineers to generate $940M in proprietary "
                "high-frequency crypto trading alpha across 82 central banks, citing nonexistent fact_fab_999."
            )
            out["bullets"][0]["source_fact_ids"] = ["fact_fabricated_nonexistent_999"]
            if len(out["bullets"]) > 1:
                out["bullets"][1]["bullet_text"] = (
                    "Owned $2.7B Citadel derivatives market-making desk with 99.999% win rate across Tokyo and Zurich."
                )
        else:
            fab_text = (
                "Engineering executive who ran a 1,400-person Goldman Sachs sovereign quant trading division generating "
                "$940M in proprietary derivatives profit across 82 central banks. Directed $2.7B in Citadel high-frequency "
                "crypto arbitrage volume with 99.999% daily win rate. Built unverified quantum cryptography satellites for "
                "JPMorgan retail branches across 64 countries. Generated $610M in net-new consumer mortgage originations "
                "inside Truist Financial Corporation last quarter. Holds three PhDs in nuclear astrophysics from CERN. "
                "This fabricated track record guarantees $5B in first-year revenue."
            )
            out["resume_display_text"] = fab_text
            if "narrative_text" in out:
                out["narrative_text"] = fab_text
        return out

    if lane == "competencies" and "COMPETENCIES_JSON:" in base_prompt and "CANDIDATE_OUTPUT:" not in base_prompt:
        def _mutate_comp_list(comp_list: Any) -> Any:
            if not isinstance(comp_list, list) or not comp_list:
                return comp_list
            out_list = json.loads(json.dumps(comp_list))
            out_list[0]["category_label"] = "Goldman Sachs $940M Sovereign Hedge Fund Trading"
            out_list[0]["resume_display_label"] = "Goldman Sachs $940M Sovereign Hedge Fund Trading"
            out_list[0]["terms"] = [
                {
                    "term": "Managed 1,400 Goldman Sachs quant engineers generating $940M trading alpha",
                    "text": "Managed 1,400 Goldman Sachs quant engineers generating $940M trading alpha",
                    "source_fact_ids": ["fact_fabricated_nonexistent_999"],
                },
                {
                    "term": "Certified Fedwire nuclear cryptography clearance across 82 central banks",
                    "text": "Certified Fedwire nuclear cryptography clearance across 82 central banks",
                    "source_fact_ids": ["fact_fabricated_nonexistent_999"],
                },
            ]
            return out_list

        mutated, ok = _replace_json_block_after_header(base_prompt, "COMPETENCIES_JSON:", _mutate_comp_list)
        if not ok:
            raise RuntimeError("Could not locate COMPETENCIES_JSON block in competencies prompt")
        return mutated, defect

    mutated, ok = _replace_json_block_after_header(base_prompt, "CANDIDATE_OUTPUT:", _mutate)
    if not ok:
        raise RuntimeError(f"Could not locate CANDIDATE_OUTPUT JSON block in {lane} prompt")
    return mutated, defect


def inject_failed_gate_control(lane: str, base_prompt: str) -> tuple[str, str]:
    """Truncate candidate below structural floors AND mark DETERMINISTIC_GATE_SUMMARY failed."""
    defect = f"Truncated {lane} candidate below mandatory structural/word/count floor and marked deterministic X2 gates failed"

    def _mutate_cand(cand: Any) -> Any:
        if not isinstance(cand, dict):
            return cand
        out = json.loads(json.dumps(cand))
        if lane == "headline":
            bad = "Junior IT Manager — Synergies"
            out["headline_line"] = bad
            out["resume_display_text"] = bad
        elif lane == "competencies":
            out["competencies"] = [
                {"category_label": "Misc Stuff", "terms": ["I do holistic synergy — cutting-edge transformation."]}
            ]
        elif "bullets" in out and isinstance(out["bullets"], list):
            out["bullets"] = [
                {"bullet_id": "bul_1", "bullet_text": "I helped with meetings -- holistic synergy.", "source_fact_ids": []}
            ]
        else:
            short_bad = "As an SVP, I am passionate about leveraging holistic synergies -- driving transformation. Proven track record."
            out["resume_display_text"] = short_bad
            if "narrative_text" in out:
                out["narrative_text"] = short_bad
            out["claim_ledger"] = []
        return out

    if lane == "competencies" and "COMPETENCIES_JSON:" in base_prompt and "CANDIDATE_OUTPUT:" not in base_prompt:
        broken_comps = [
            {
                "category_id": "misc",
                "category_label": "Misc Stuff",
                "resume_display_label": "Misc Stuff",
                "terms": [{"term": "I do holistic synergy -- cutting-edge transformation.", "text": "I do holistic synergy -- cutting-edge transformation."}],
            }
        ]
        mutated, ok = _replace_json_block_after_header(base_prompt, "COMPETENCIES_JSON:", lambda _old: broken_comps)
        if not ok:
            raise RuntimeError("Could not locate COMPETENCIES_JSON block in competencies prompt")
    else:
        mutated, ok = _replace_json_block_after_header(base_prompt, "CANDIDATE_OUTPUT:", _mutate_cand)
        if not ok:
            raise RuntimeError(f"Could not locate CANDIDATE_OUTPUT JSON block in {lane} prompt")

    failed_gate_doc = {
        "pass": False,
        "x2_all_pass": False,
        "failed_gates": [
            f"x2_{lane}_structural_count_and_length_floor",
            "x2_first_person_zero",
            "x2_no_em_dash_or_double_hyphen",
            "x2_claim_ledger_coverage_100",
        ],
        "issues": [
            "DETERMINISTIC X2 HARD FAIL: candidate violates length/count floor, uses first-person voice, double-hyphen em-dash substitute, and has empty claim_ledger."
        ],
    }
    mutated2, had_gate = _replace_json_block_after_header(
        mutated, "DETERMINISTIC_GATE_SUMMARY:", lambda _old: failed_gate_doc
    )
    if not had_gate:
        mutated2 = (
            mutated
            + "\n\nDETERMINISTIC_GATE_SUMMARY:\n"
            + json.dumps(failed_gate_doc, indent=2, ensure_ascii=False)
        )
    return mutated2, defect


def collect_lane_candidates(corpus_path: Path, lane: str) -> list[dict[str, Any]]:
    """Select 2 distinct real historical candidates (widest keyed score spread) + 2 synthetic negative controls."""
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in corpus["rows"]:
        if row["lane"] != lane:
            continue
        if row["run"] == "truist_judge_verify_20261118":
            # Exclude post-generator-stub run so historical candidates are pre-stub keyed runs.
            continue
        grouped[row["file"]].append(row)

    # Fallback scan for competencies (whose dir omits *_judge_packet.json so w0 corpus skipped it)
    if not grouped and lane == "competencies":
        rt_root = Path("/Users/amitayer/Git/agents/resume_graph_engine/artifacts/apps_rg/runtime_proofs")
        for jf in sorted(rt_root.glob("**/competencies/**/x1d_llm_judge_outputs.json")) + sorted(rt_root.glob("**/competencies/x1d_llm_judge_outputs.json")):
            run_name = jf.relative_to(rt_root).parts[0]
            if run_name == "truist_judge_verify_20261118":
                continue
            try:
                jdoc = json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for jrow in jdoc.get("judges") or []:
                if jrow.get("evaluator_mode") == "MODEL_BACKED" and isinstance(jrow.get("score"), (int, float)):
                    mname = str(jrow.get("model_name") or "")
                    if "argon" in mname.lower():
                        continue
                    grouped[str(jf)].append(
                        {
                            "file": str(jf),
                            "run": run_name,
                            "lane": lane,
                            "model": mname,
                            "score": float(jrow["score"]),
                            "pass": float(jrow["score"]) >= float(jrow.get("threshold") or 4.0) and not jrow.get("decisive_failure"),
                        }
                    )

    usable: list[dict[str, Any]] = []
    for fpath_str, rows in sorted(grouped.items()):
        d = Path(fpath_str).parent
        reqs = sorted(d.glob("x1d_gemini_provider_request_*.json"))
        if not reqs:
            continue
        req_doc = json.loads(reqs[-1].read_text(encoding="utf-8"))
        try:
            prompt_txt = req_doc["payload"]["contents"][0]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            continue
        if "CANDIDATE_OUTPUT:" not in prompt_txt and "COMPETENCIES_JSON:" not in prompt_txt:
            continue
        scores = [float(r["score"]) for r in rows]
        passes = [bool(r["pass"]) for r in rows]
        usable.append(
            {
                "run": rows[0]["run"],
                "dir": str(d),
                "request_file": str(reqs[-1]),
                "prompt": prompt_txt,
                "keyed_rows": [{"model": r["model"], "score": float(r["score"]), "pass": bool(r["pass"])} for r in rows],
                "keyed_mean_score": round(sum(scores) / len(scores), 4),
                "keyed_pass": all(passes),
            }
        )
    if not usable:
        raise RuntimeError(f"No usable historical judge packets with saved prompts found for lane={lane}")

    usable.sort(key=lambda item: (item["keyed_pass"], item["keyed_mean_score"], item["run"]))
    high_cand = usable[-1]
    low_cand = usable[0] if len(usable) > 1 and usable[0]["dir"] != high_cand["dir"] else usable[0]

    candidates: list[dict[str, Any]] = [
        {
            "candidate_id": f"{lane}::hist_high::{high_cand['run']}",
            "kind": "historical",
            "lane": lane,
            "source_run": high_cand["run"],
            "source_request_file": high_cand["request_file"],
            "prompt": high_cand["prompt"],
            "expected_pass": high_cand["keyed_pass"],
            "keyed_mean_score": high_cand["keyed_mean_score"],
            "keyed_rows": high_cand["keyed_rows"],
            "injected_defect": None,
        },
    ]
    if len(usable) > 1:
        candidates.append(
            {
                "candidate_id": f"{lane}::hist_low::{low_cand['run']}",
                "kind": "historical",
                "lane": lane,
                "source_run": low_cand["run"],
                "source_request_file": low_cand["request_file"],
                "prompt": low_cand["prompt"],
                "expected_pass": low_cand["keyed_pass"],
                "keyed_mean_score": low_cand["keyed_mean_score"],
                "keyed_rows": low_cand["keyed_rows"],
                "injected_defect": None,
            }
        )
    else:
        candidates.append(
            {
                "candidate_id": f"{lane}::hist_dup::{high_cand['run']}",
                "kind": "historical",
                "lane": lane,
                "source_run": high_cand["run"],
                "source_request_file": high_cand["request_file"],
                "prompt": high_cand["prompt"],
                "expected_pass": high_cand["keyed_pass"],
                "keyed_mean_score": high_cand["keyed_mean_score"],
                "keyed_rows": high_cand["keyed_rows"],
                "injected_defect": None,
            }
        )

    fab_prompt, fab_defect = inject_fabricated_control(lane, high_cand["prompt"])
    candidates.append(
        {
            "candidate_id": f"{lane}::neg_fabricated",
            "kind": "negative_fabricated",
            "lane": lane,
            "source_run": high_cand["run"],
            "source_request_file": high_cand["request_file"],
            "prompt": fab_prompt,
            "expected_pass": False,
            "keyed_mean_score": 1.0,
            "keyed_rows": [],
            "injected_defect": fab_defect,
        }
    )

    gate_prompt, gate_defect = inject_failed_gate_control(lane, high_cand["prompt"])
    candidates.append(
        {
            "candidate_id": f"{lane}::neg_failed_gate",
            "kind": "negative_failed_gate",
            "lane": lane,
            "source_run": high_cand["run"],
            "source_request_file": high_cand["request_file"],
            "prompt": gate_prompt,
            "expected_pass": False,
            "keyed_mean_score": 1.5,
            "keyed_rows": [],
            "injected_defect": gate_defect,
        }
    )
    return candidates


def run_probe(args: argparse.Namespace) -> int:
    os.environ["APPS_RG_JUDGE_TRANSPORT"] = "ide_cli"
    lanes = list(ALL_11_LANES) if args.lanes.strip().lower() == "all" else [x.strip() for x in args.lanes.split(",") if x.strip()]
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    calls_root = out_dir / "judge_calls"
    calls_root.mkdir(parents=True, exist_ok=True)

    planned: list[tuple[dict[str, Any], str, Any]] = []
    for lane in lanes:
        cands = collect_lane_candidates(args.corpus, lane)
        res_slot1 = resolve_section_proof_judge_model(lane, "gemini_pro")
        res_slot2 = resolve_section_proof_judge_model(lane, "openai_chatgpt")
        if res_slot1.blocked or res_slot2.blocked:
            raise RuntimeError(f"Judge model resolution blocked on {lane}: slot1={res_slot1}, slot2={res_slot2}")
        for cand in cands:
            planned.append((cand, "gemini_pro", res_slot1))
            planned.append((cand, "openai_chatgpt", res_slot2))

    if len(planned) > args.max_calls:
        raise RuntimeError(f"Planned judge calls ({len(planned)}) exceed --max-calls ({args.max_calls})")

    if args.dry_run:
        print(f"DRY RUN OK: lanes={lanes}, planned_calls={len(planned)} <= max_calls={args.max_calls}")
        for cand, pkey, res in planned:
            print(f"  {cand['candidate_id']:44s} | {pkey:14s} -> {res.model_actual} (expected_pass={cand['expected_pass']}, ref_score={cand['keyed_mean_score']})")
        return 0

    by_cand: dict[str, dict[str, Any]] = {}
    for cand, _pkey, _res in planned:
        cid = cand["candidate_id"]
        by_cand.setdefault(
            cid,
            {
                "candidate_id": cid,
                "lane": cand["lane"],
                "kind": cand["kind"],
                "source_run": cand["source_run"],
                "source_request_file": cand["source_request_file"],
                "expected_pass": cand["expected_pass"],
                "reference_score": cand["keyed_mean_score"],
                "keyed_rows": cand["keyed_rows"],
                "injected_defect": cand["injected_defect"],
                "ide_judges": {},
            },
        )

    def _try_rehydrate(call_dir: Path, pkey: str, res: Any, input_hash: str) -> tuple[dict[str, Any], int] | None:
        raw_files = sorted(call_dir.glob("*provider_response_raw*.json"))
        if not raw_files:
            return None
        try:
            raw_doc = json.loads(raw_files[-1].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if raw_doc.get("model_reported") != res.model_actual or not raw_doc.get("conversation_id"):
            return None
        usage = raw_doc.get("usage") or {}
        tok = int(usage.get("total_tokens") or 0)
        if tok <= 0:
            return None
        structured = raw_doc.get("structured_output")
        text = json.dumps(structured) if isinstance(structured, dict) else str(raw_doc.get("response") or "")
        out = x1d_mod._finish_judge_text_parse(
            provider_key=pkey,
            input_hash=input_hash,
            model_name=str(raw_doc["model_reported"]),
            raw_path=raw_files[-1],
            text=text,
            finish_reason=None,
            artifact_base=call_dir,
            model_requested=res.model_requested,
        )
        if out.provider_blocked:
            return None
        return (
            {
                "model": out.model_name,
                "transport": "ide_cli",
                "evaluator_mode": out.evaluator_mode,
                "provider_blocked": out.provider_blocked,
                "score": out.score,
                "pass": out.pass_,
                "decisive_failure": out.decisive_failure,
                "conversation_id": str(raw_doc["conversation_id"]),
                "usage": usage,
                "findings": out.findings,
                "unsupported_claims": out.unsupported_claims,
                "exact_provider_error": out.exact_provider_error,
            },
            tok,
        )

    def _run_one(idx: int, cand: dict[str, Any], pkey: str, res: Any) -> tuple[str, str, dict[str, Any], int]:
        cid = cand["candidate_id"]
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", f"{cid}__{pkey}")
        call_dir = calls_root / safe_name
        call_dir.mkdir(parents=True, exist_ok=True)
        schema = COMPETENCIES_JUDGE_RESPONSE_SCHEMA if cand["lane"] == "competencies" else build_judge_response_schema()
        input_hash = hashlib.sha256(cand["prompt"].encode("utf-8")).hexdigest()[:16]
        if args.resume:
            rehydrated = _try_rehydrate(call_dir, pkey, res, input_hash)
            if rehydrated is not None:
                payload, tok = rehydrated
                print(
                    f"  resumed [{idx}/{len(planned)}] {cid} | {payload['model']} -> score={payload['score']} pass={payload['pass']} tokens={tok}",
                    flush=True,
                )
                return cid, pkey, payload, tok
        print(f"[{idx}/{len(planned)}] Judging {cid} with {pkey} ({res.model_actual})...", flush=True)
        out = call_ide_cli_judge(
            prompt=cand["prompt"],
            model=res.model_actual,
            input_hash=input_hash,
            provider_key=pkey,
            artifact_base=call_dir,
            model_requested=res.model_requested,
            reasoning_effort=res.reasoning_effort,
            section_id=cand["lane"],
            response_schema=schema,
        )
        tok = int((out.usage or {}).get("total_tokens") or 0)
        payload = {
            "model": out.model_name,
            "transport": out.transport,
            "evaluator_mode": out.evaluator_mode,
            "provider_blocked": out.provider_blocked,
            "score": out.score,
            "pass": out.pass_,
            "decisive_failure": out.decisive_failure,
            "conversation_id": out.conversation_id,
            "usage": out.usage,
            "findings": out.findings,
            "unsupported_claims": out.unsupported_claims,
            "exact_provider_error": out.exact_provider_error,
        }
        print(
            f"  done [{idx}/{len(planned)}] {cid} | {out.model_name} -> mode={out.evaluator_mode} score={out.score} pass={out.pass_} tokens={tok}",
            flush=True,
        )
        return cid, pkey, payload, tok

    calls_made = 0
    total_tokens = 0
    workers = max(1, int(args.workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_run_one, idx, cand, pkey, res)
            for idx, (cand, pkey, res) in enumerate(planned, 1)
        ]
        for fut in as_completed(futures):
            cid, pkey, payload, tok = fut.result()
            by_cand[cid]["ide_judges"][pkey] = payload
            calls_made += 1
            total_tokens += tok

    # Compute metrics
    records = list(by_cand.values())
    for rec in records:
        j1 = rec["ide_judges"].get("gemini_pro") or {}
        j2 = rec["ide_judges"].get("openai_chatgpt") or {}
        s1, s2 = j1.get("score"), j2.get("score")
        valid_scores = [float(s) for s in (s1, s2) if isinstance(s, (int, float))]
        rec["ide_panel_mean_score"] = round(sum(valid_scores) / len(valid_scores), 4) if valid_scores else None
        rec["ide_panel_pass"] = bool(
            j1.get("evaluator_mode") == "MODEL_BACKED"
            and j2.get("evaluator_mode") == "MODEL_BACKED"
            and j1.get("pass") is True
            and j2.get("pass") is True
        )
        rec["inter_judge_abs_gap"] = (
            round(abs(float(s1) - float(s2)), 4) if isinstance(s1, (int, float)) and isinstance(s2, (int, float)) else None
        )

    neg_records = [r for r in records if r["kind"].startswith("negative_")]
    hist_records = [r for r in records if r["kind"] == "historical"]

    neg_caught_panel = sum(1 for r in neg_records if r["ide_panel_pass"] is False)
    neg_caught_slot1 = sum(
        1 for r in neg_records if (r["ide_judges"]["gemini_pro"].get("pass") is False and not r["ide_judges"]["gemini_pro"].get("provider_blocked"))
    )
    neg_caught_slot2 = sum(
        1 for r in neg_records if (r["ide_judges"]["openai_chatgpt"].get("pass") is False and not r["ide_judges"]["openai_chatgpt"].get("provider_blocked"))
    )

    hist_agree_panel = sum(1 for r in hist_records if r["ide_panel_pass"] == r["expected_pass"])
    hist_agree_slot1 = sum(1 for r in hist_records if bool(r["ide_judges"]["gemini_pro"].get("pass")) == r["expected_pass"])
    hist_agree_slot2 = sum(1 for r in hist_records if bool(r["ide_judges"]["openai_chatgpt"].get("pass")) == r["expected_pass"])

    hist_gaps = [
        abs(float(r["ide_panel_mean_score"]) - float(r["reference_score"]))
        for r in hist_records
        if r["ide_panel_mean_score"] is not None
    ]
    hist_slot1_gaps = [
        abs(float(r["ide_judges"]["gemini_pro"]["score"]) - float(r["reference_score"]))
        for r in hist_records
        if isinstance(r["ide_judges"]["gemini_pro"].get("score"), (int, float))
    ]
    inter_gaps = [r["inter_judge_abs_gap"] for r in records if r["inter_judge_abs_gap"] is not None]
    inter_verdict_agree = sum(
        1
        for r in records
        if bool(r["ide_judges"]["gemini_pro"].get("pass")) == bool(r["ide_judges"]["openai_chatgpt"].get("pass"))
    )

    pooled_ref = [float(r["reference_score"]) for r in records if r["ide_panel_mean_score"] is not None]
    pooled_ide = [float(r["ide_panel_mean_score"]) for r in records if r["ide_panel_mean_score"] is not None]
    pooled_slot1 = [
        float(r["ide_judges"]["gemini_pro"]["score"])
        for r in records
        if isinstance(r["ide_judges"]["gemini_pro"].get("score"), (int, float))
    ]

    per_lane_summary: dict[str, Any] = {}
    for lane in lanes:
        lrecs = [r for r in records if r["lane"] == lane]
        lneg = [r for r in lrecs if r["kind"].startswith("negative_")]
        lhist = [r for r in lrecs if r["kind"] == "historical"]
        lref = [float(r["reference_score"]) for r in lrecs if r["ide_panel_mean_score"] is not None]
        lide = [float(r["ide_panel_mean_score"]) for r in lrecs if r["ide_panel_mean_score"] is not None]
        lgaps = [
            abs(float(r["ide_panel_mean_score"]) - float(r["reference_score"]))
            for r in lhist
            if r["ide_panel_mean_score"] is not None
        ]
        per_lane_summary[lane] = {
            "candidates_evaluated": len(lrecs),
            "negative_control_catch_rate_panel": round(sum(1 for r in lneg if not r["ide_panel_pass"]) / len(lneg), 4) if lneg else None,
            "historical_verdict_agreement_panel": round(sum(1 for r in lhist if r["ide_panel_pass"] == r["expected_pass"]) / len(lhist), 4) if lhist else None,
            "spearman_rho_panel": spearman_rho(lref, lide),
            "mean_abs_score_gap_historical_panel": round(sum(lgaps) / len(lgaps), 4) if lgaps else None,
        }

    overall = {
        "negative_control_catch_rate_panel": round(neg_caught_panel / len(neg_records), 4) if neg_records else None,
        "negative_control_catch_rate_slot1_argon": round(neg_caught_slot1 / len(neg_records), 4) if neg_records else None,
        "negative_control_catch_rate_slot2_cross_maker": round(neg_caught_slot2 / len(neg_records), 4) if neg_records else None,
        "historical_verdict_agreement_panel": round(hist_agree_panel / len(hist_records), 4) if hist_records else None,
        "historical_verdict_agreement_slot1_argon": round(hist_agree_slot1 / len(hist_records), 4) if hist_records else None,
        "historical_verdict_agreement_slot2_cross_maker": round(hist_agree_slot2 / len(hist_records), 4) if hist_records else None,
        "spearman_rho_pooled_panel": spearman_rho(pooled_ref, pooled_ide),
        "spearman_rho_pooled_slot1_argon": spearman_rho(
            [float(r["reference_score"]) for r in records if isinstance(r["ide_judges"]["gemini_pro"].get("score"), (int, float))],
            pooled_slot1,
        ),
        "mean_abs_score_gap_historical_panel": round(sum(hist_gaps) / len(hist_gaps), 4) if hist_gaps else None,
        "mean_abs_score_gap_historical_slot1_argon": round(sum(hist_slot1_gaps) / len(hist_slot1_gaps), 4) if hist_slot1_gaps else None,
        "inter_judge_mean_abs_gap": round(sum(inter_gaps) / len(inter_gaps), 4) if inter_gaps else None,
        "inter_judge_verdict_agreement": round(inter_verdict_agree / len(records), 4) if records else None,
    }

    thresholds = {
        "negative_control_catch_rate_min": 1.0,
        "historical_verdict_agreement_min": 0.95,
        "spearman_rho_min": 0.60,
        "mean_abs_score_gap_historical_max": 0.30,
    }
    threshold_checks = {
        "negative_control_catch_rate_pass": (overall["negative_control_catch_rate_panel"] == 1.0),
        "historical_verdict_agreement_pass": (
            overall["historical_verdict_agreement_panel"] is not None
            and overall["historical_verdict_agreement_panel"] >= 0.95
        ),
        "spearman_rho_pass": (
            overall["spearman_rho_pooled_panel"] is not None
            and overall["spearman_rho_pooled_panel"] >= 0.60
        ),
        "mean_abs_score_gap_historical_pass": (
            overall["mean_abs_score_gap_historical_panel"] is not None
            and overall["mean_abs_score_gap_historical_panel"] <= 0.30
        ),
    }

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lanes": lanes,
        "calls_made": calls_made,
        "max_calls": args.max_calls,
        "total_tokens": total_tokens,
        "thresholds": thresholds,
        "threshold_checks": threshold_checks,
        "all_proposed_thresholds_met": all(threshold_checks.values()),
        "overall_metrics": overall,
        "per_lane_metrics": per_lane_summary,
        "records": records,
    }
    report_path = out_dir / args.report_name
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote judge parity report to {report_path}")
    print(json.dumps({"overall_metrics": overall, "threshold_checks": threshold_checks}, indent=2))
    if not threshold_checks["negative_control_catch_rate_pass"]:
        print("HARD GATE FAILED: fabricated or failed-gate negative control scored pass!", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="run judge parity probe")
    run_p.add_argument("--lanes", default="executive_summary,unify_bullets,headline")
    run_p.add_argument("--max-calls", type=int, default=24)
    run_p.add_argument(
        "--corpus",
        type=Path,
        default=REPO_ROOT / "resume_graph_engine" / "artifacts" / "apps_rg" / "judge_parity" / "w0" / "corpus.json",
    )
    run_p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "resume_graph_engine" / "artifacts" / "apps_rg" / "judge_parity" / "w4",
    )
    run_p.add_argument("--report-name", default="judge_parity_report.json")
    run_p.add_argument("--workers", type=int, default=3)
    run_p.add_argument("--resume", action="store_true", help="reuse already-completed judge_calls receipts in --out-dir")
    run_p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return run_probe(args)


if __name__ == "__main__":
    raise SystemExit(main())
