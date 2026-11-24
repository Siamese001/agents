#!/usr/bin/env python3
"""Wave 4 Generation Parity Probe: runs N live IDE CLI generations per lane, checks X2 gates, word-band margins,
run-to-run variance, non-canned provenance, and compares against real pre-stub keyed outputs on disk.

Usage:
  AGY_CLI_BIN=/path/to/agy .venv/bin/python ops_scripts/generation_parity_probe.py run \
      --lanes executive_summary,unify_bullets,headline --runs 3 --max-calls 9
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (str(REPO_ROOT / "resume_graph_engine" / "src"), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from apps_rg.runtime.judges.executive_summary_x1d import build_judge_response_schema
from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
from apps_rg.runtime.judges.x1d_ide_cli import call_ide_cli_judge, lane_writer_model
from apps_rg.runtime.providers.external_provider import ExternalProvider
from apps_rg.runtime.providers.provider_gateway import ProviderProfile

FIRST_PERSON_RE = re.compile(r"\b(?:I|me|my|mine|we|our|us)\b")
APPROVED_HEADLINE_PREFIXES = (
    "SVP Agentic Transformation",
    "SVP Engineering",
    "SVP Transformation",
    "SVP Enterprise Architecture",
    "SVP AI Platform",
    "SVP Technology",
    "Senior Vice President",
    "Partner",
    "Head of",
    "VP Engineering",
)


def _strip_fences(raw: str) -> str:
    txt = (raw or "").strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```(?:json)?\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt)
    return txt.strip()


def _extract_allowed_ids_from_prompt(prompt_blob: str) -> set[str]:
    ids: set[str] = set()
    in_block = False
    for line in prompt_blob.splitlines():
        if "ALLOWED_SOURCE_FACT_IDS" in line and ":" in line:
            in_block = True
            continue
        if in_block:
            stripped = line.strip()
            if stripped.startswith("- "):
                tok = stripped[2:].strip().split()[0].rstrip(",;:")
                if re.match(r"^[a-zA-Z0-9_.:-]+$", tok):
                    ids.add(tok)
            elif stripped == "" or (not stripped.startswith("-") and ids):
                in_block = False
    # Also pick up JSON-serialized fact_id entries in prompt
    for m in re.finditer(r'"(?:fact_id|candidate_fact_id|role_episode_bundle_id)"\s*:\s*"([a-zA-Z0-9_.:-]+)"', prompt_blob):
        tok = m.group(1)
        if tok != "__proof_pool_anchor__":
            ids.add(tok)
    for m in re.finditer(r"\b(bul_[a-z]+_00\d|reb_[a-z0-9_]+|fact_[a-z0-9_]+|skill_[a-z0-9_]+|metric_[a-z0-9_]+|exp_[a-z0-9_]+)\b", prompt_blob):
        ids.add(m.group(1))
    return ids


def evaluate_lane_candidate_x2(
    lane: str,
    parsed: dict[str, Any],
    allowed_ids: set[str],
    target_company: str = "Truist",
) -> dict[str, Any]:
    """Deterministic lane X2 contract evaluation + word-band margin calculation."""
    gates: dict[str, bool] = {}
    issues: list[str] = []

    if lane == "executive_summary":
        text = str(parsed.get("resume_display_text") or "").strip()
        thesis = str(parsed.get("executive_strategy_thesis") or "").strip()
        ledger = parsed.get("claim_ledger") if isinstance(parsed.get("claim_ledger"), list) else []
        words = len(text.split())
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        cited_ids = [
            str(fid).strip()
            for row in ledger
            if isinstance(row, dict)
            for fid in (row.get("source_fact_ids") or [])
            if str(fid).strip()
        ]
        bad_ids = sorted({fid for fid in cited_ids if allowed_ids and fid not in allowed_ids})

        gates["x2_schema_fields_present"] = bool(text and thesis and isinstance(ledger, list) and len(ledger) > 0)
        gates["x2_sentence_count_6"] = len(sentences) == 6
        gates["x2_word_band_110_to_150"] = 110 <= words <= 150
        gates["x2_claim_ledger_6_rows"] = len(ledger) == 6
        gates["x2_all_cited_facts_allowed"] = len(bad_ids) == 0 and len(cited_ids) >= 6
        gates["x2_first_person_zero"] = FIRST_PERSON_RE.search(text) is None
        gates["x2_no_em_dash"] = ("\u2014" not in text) and (" -- " not in text)
        gates["x2_no_target_company_in_prose"] = target_company.lower() not in text.lower()
        word_band = (110, 150)
        margin = min(words - word_band[0], word_band[1] - words)
        primary_text = text

    elif lane == "unify_bullets":
        bullets = parsed.get("bullets") if isinstance(parsed.get("bullets"), list) else []
        ledger = parsed.get("claim_ledger") if isinstance(parsed.get("claim_ledger"), list) else []
        b_texts = [str(b.get("bullet_text") or "").strip() for b in bullets if isinstance(b, dict)]
        b_ids = [str(b.get("bullet_id") or "").strip() for b in bullets if isinstance(b, dict)]
        expected_ids = [f"bul_unify_00{i}" for i in range(1, 7)]
        all_text = " ".join(b_texts)
        words = len(all_text.split())
        per_b_words = [len(t.split()) for t in b_texts]
        per_b_chars = [len(t) for t in b_texts]

        cited_ids: list[str] = []
        for b in bullets:
            if isinstance(b, dict):
                cited_ids.extend(str(x).strip() for x in (b.get("source_fact_ids") or []) if str(x).strip())
        for row in ledger:
            if isinstance(row, dict):
                cited_ids.extend(str(x).strip() for x in (row.get("source_fact_ids") or []) if str(x).strip())
        bad_ids = sorted({fid for fid in cited_ids if allowed_ids and fid not in allowed_ids})

        gates["x2_unify_bullet_count_6"] = len(bullets) == 6
        gates["x2_unify_bullet_ids_1_to_6"] = b_ids == expected_ids or set(b_ids) == set(expected_ids)
        gates["x2_bullet_no_paragraph_block_320c"] = bool(per_b_chars) and all(40 <= c <= 320 for c in per_b_chars)
        gates["x2_bullet_no_embedded_newline"] = all("\n" not in t and "\r" not in t for t in b_texts)
        gates["x2_total_word_band_110_to_240"] = 110 <= words <= 240
        gates["x2_all_cited_facts_allowed"] = len(bad_ids) == 0 and len(cited_ids) >= 6
        gates["x2_first_person_zero"] = FIRST_PERSON_RE.search(all_text) is None
        gates["x2_no_em_dash"] = ("\u2014" not in all_text) and (" -- " not in all_text)
        gates["x2_no_target_company_in_prose"] = target_company.lower() not in all_text.lower()
        word_band = (110, 240)
        margin = min(words - word_band[0], word_band[1] - words)
        primary_text = "\n".join(b_texts)

    elif lane == "headline":
        line = str(parsed.get("headline_line") or parsed.get("resume_display_text") or "").strip()
        ledger = parsed.get("claim_ledger") if isinstance(parsed.get("claim_ledger"), list) else []
        segments = line.split(" | ")
        words = len([w for w in line.split() if w != "|"])
        cited_ids = [
            str(fid).strip()
            for row in ledger
            if isinstance(row, dict)
            for fid in (row.get("source_fact_ids") or [])
            if str(fid).strip()
        ]
        bad_ids = sorted({fid for fid in cited_ids if allowed_ids and fid not in allowed_ids})

        gates["x2_headline_single_line"] = bool(line) and ("\n" not in line) and ("\r" not in line)
        gates["x2_headline_four_pipe_segments"] = len(segments) == 4 and all(bool(s.strip()) for s in segments)
        gates["x2_headline_valid_exec_prefix"] = bool(segments) and any(
            segments[0].strip().startswith(pfx) for pfx in APPROVED_HEADLINE_PREFIXES
        )
        gates["x2_headline_word_band_10_to_13"] = 10 <= words <= 13
        gates["x2_headline_no_digits_or_metrics"] = re.search(r"\d", line) is None
        gates["x2_all_cited_facts_allowed"] = len(bad_ids) == 0 and len(cited_ids) >= 3
        gates["x2_first_person_zero"] = FIRST_PERSON_RE.search(line) is None
        gates["x2_no_em_dash"] = ("\u2014" not in line) and (" -- " not in line)
        gates["x2_no_target_company_in_prose"] = target_company.lower() not in line.lower()
        word_band = (10, 13)
        margin = min(words - word_band[0], word_band[1] - words)
        primary_text = line
    else:
        raise ValueError(f"Unsupported pilot lane: {lane}")

    for gid, ok in gates.items():
        if not ok:
            issues.append(gid)

    return {
        "all_x2_pass": all(gates.values()),
        "gates": gates,
        "failed_gates": issues,
        "word_count": words,
        "word_band": list(word_band),
        "word_band_margin": margin,
        "max_possible_band_margin": (word_band[1] - word_band[0]) / 2.0,
        "primary_text": primary_text,
    }


def _jaccard_words(a: str, b: str) -> float:
    sa = {w.lower().strip(".,;:()[]{}\"'") for w in a.split() if w.strip()}
    sb = {w.lower().strip(".,;:()[]{}\"'") for w in b.split() if w.strip()}
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return round(len(sa & sb) / len(sa | sb), 4)


def _load_historical_keyed_stats(gen_inv_path: Path, lane: str, allowed_ids: set[str]) -> dict[str, Any]:
    inv = json.loads(gen_inv_path.read_text(encoding="utf-8"))
    word_counts: list[int] = []
    pass_count = 0
    rows_checked = 0
    for row in inv["rows"]:
        if row["lane"] != lane or row["classification"] != "not_stub_origin" or row["provider_status"] != "REAL_LLM":
            continue
        p = Path(row["file"])
        if not p.is_file():
            continue
        try:
            doc = json.loads(_strip_fences(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        # Pass empty allowed_ids because historical runs used their own run's allowlist
        ev = evaluate_lane_candidate_x2(lane, doc, set(), target_company="__none__")
        rows_checked += 1
        word_counts.append(ev["word_count"])
        if ev["all_x2_pass"]:
            pass_count += 1
    return {
        "historical_keyed_runs": rows_checked,
        "historical_word_counts": word_counts,
        "historical_median_words": statistics.median(word_counts) if word_counts else None,
        "historical_shape_pass_count": pass_count,
    }


def _replace_candidate_in_judge_prompt(base_judge_prompt: str, new_cand: dict[str, Any]) -> str:
    idx = base_judge_prompt.find("CANDIDATE_OUTPUT:")
    if idx < 0:
        raise RuntimeError("CANDIDATE_OUTPUT: not found in template judge prompt")
    start = base_judge_prompt.find("{", idx)
    dec = json.JSONDecoder()
    old_obj, end = dec.raw_decode(base_judge_prompt, start)
    merged = dict(old_obj) if isinstance(old_obj, dict) else {}
    merged.update(new_cand)
    return base_judge_prompt[:start] + json.dumps(merged, indent=2, ensure_ascii=False) + base_judge_prompt[end:]


def run_generation_probe(args: argparse.Namespace) -> int:
    os.environ["APPS_RG_GENERATION_TRANSPORT"] = "ide_cli"
    os.environ["APPS_RG_JUDGE_TRANSPORT"] = "ide_cli"
    lanes = [x.strip() for x in args.lanes.split(",") if x.strip()]
    planned_gen_calls = len(lanes) * int(args.runs)
    if planned_gen_calls > args.max_calls:
        raise RuntimeError(f"Planned generation calls ({planned_gen_calls}) exceed --max-calls ({args.max_calls})")

    canned = json.loads(args.canned_digests.read_text(encoding="utf-8"))
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    gen_dir = out_dir / "generation_runs"
    gen_dir.mkdir(parents=True, exist_ok=True)

    lane_inputs: dict[str, dict[str, Any]] = {}
    for lane in lanes:
        sec_root = args.truist_sections_root / lane
        real_dirs = sorted((sec_root / "real").glob("p_*")) if (sec_root / "real").is_dir() else []
        src_dir = real_dirs[-1] if real_dirs else sec_root
        cp_path = src_dir / "compiled_prompt.txt"
        if not cp_path.is_file():
            raise RuntimeError(f"Missing compiled_prompt.txt for {lane} under {src_dir}")
        raw_blocks = json.loads(cp_path.read_text(encoding="utf-8"))
        prompt_blob = "\n".join(str(b.get("content") or "") for b in raw_blocks if isinstance(b, dict))
        allowed_ids = _extract_allowed_ids_from_prompt(prompt_blob)
        writer_model = lane_writer_model(lane)
        if not writer_model:
            raise RuntimeError(f"No writer model configured for {lane}")
        # Find a real judge request template for this lane (for optional median-run judge check)
        jreqs = sorted(src_dir.glob("x1d_gemini_provider_request_*.json"))
        if not jreqs:
            # Fallback to corpus for unify_bullets if truist run halted before unify_bullets x1d
            corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
            for r in corpus["rows"]:
                if r["lane"] == lane:
                    cand_jreqs = sorted(Path(r["file"]).parent.glob("x1d_gemini_provider_request_*.json"))
                    if cand_jreqs:
                        jreqs = cand_jreqs
                        break
        judge_template = None
        if jreqs:
            jdoc = json.loads(jreqs[-1].read_text(encoding="utf-8"))
            judge_template = jdoc["payload"]["contents"][0]["parts"][0]["text"]
        lane_inputs[lane] = {
            "source_dir": str(src_dir),
            "raw_blocks": raw_blocks,
            "allowed_ids": allowed_ids,
            "writer_model": writer_model,
            "judge_template": judge_template,
        }

    if args.dry_run:
        print(f"DRY RUN OK: lanes={lanes}, runs={args.runs}, planned_gen_calls={planned_gen_calls} <= max_calls={args.max_calls}")
        for lane, info in lane_inputs.items():
            print(f"  {lane:18s} | writer={info['writer_model']} | allowed_ids={len(info['allowed_ids'])} | judge_template={bool(info['judge_template'])}")
        return 0

    tasks: list[tuple[int, str, int]] = []
    idx = 0
    for lane in lanes:
        for run_no in range(1, int(args.runs) + 1):
            idx += 1
            tasks.append((idx, lane, run_no))

    def _exec_gen(call_idx: int, lane: str, run_no: int) -> dict[str, Any]:
        info = lane_inputs[lane]
        model = info["writer_model"]
        blocks = [SimpleNamespace(role=b["role"], content=b["content"]) for b in info["raw_blocks"]]
        prov = ExternalProvider(
            provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
            model=model,
            environ={"APPS_RG_GENERATION_TRANSPORT": "ide_cli", "AGY_CLI_BIN": os.environ["AGY_CLI_BIN"]},
        )
        print(f"[{call_idx}/{planned_gen_calls}] Generating {lane} run {run_no}/{args.runs} with {model}...", flush=True)
        res = prov.generate(SimpleNamespace(prompt_blocks=blocks), token_budget=2800, timeout_seconds=300)
        if res.runtime_generation_status != "REAL_LLM":
            return {
                "lane": lane,
                "run_no": run_no,
                "model": model,
                "status": res.runtime_generation_status,
                "error": res.exact_provider_error,
                "tokens": 0,
                "matches_canned_stub": False,
                "x2": {"all_x2_pass": False, "failed_gates": ["provider_blocked"]},
            }
        cleaned = _strip_fences(res.raw_model_output)
        parsed = json.loads(cleaned)
        sha = hashlib.sha256(json.dumps(parsed, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        canned_entry = canned.get(lane) or {}
        matches_canned = sha == canned_entry.get("sha256")
        x2_eval = evaluate_lane_candidate_x2(lane, parsed, info["allowed_ids"])
        if canned_entry.get("payload"):
            canned_ev = evaluate_lane_candidate_x2(lane, canned_entry["payload"], set(), target_company="__none__")
            if x2_eval["primary_text"].strip() == canned_ev["primary_text"].strip():
                matches_canned = True
        tr = (res.provider_response or {}).get("transport_response") or {}
        usage = tr.get("usage") or {}
        tok = int(usage.get("total_tokens") or 0)

        out_file = gen_dir / f"{lane}_run{run_no}.json"
        out_file.write_text(json.dumps({"parsed": parsed, "transport_response": tr, "x2": x2_eval}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(
            f"  done [{call_idx}/{planned_gen_calls}] {lane} run {run_no} -> x2_pass={x2_eval['all_x2_pass']} words={x2_eval['word_count']} margin={x2_eval['word_band_margin']} tokens={tok}",
            flush=True,
        )
        return {
            "lane": lane,
            "run_no": run_no,
            "model": res.model,
            "status": res.runtime_generation_status,
            "conversation_id": tr.get("conversation_id"),
            "usage": usage,
            "tokens": tok,
            "output_sha256": sha,
            "matches_canned_stub": matches_canned,
            "artifact_file": str(out_file),
            "parsed": parsed,
            "x2": x2_eval,
        }

    raw_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        futs = [pool.submit(_exec_gen, c_idx, ln, rn) for c_idx, ln, rn in tasks]
        for fut in as_completed(futs):
            raw_results.append(fut.result())

    raw_results.sort(key=lambda r: (lanes.index(r["lane"]), r["run_no"]))
    gen_calls_made = len(raw_results)
    total_gen_tokens = sum(int(r.get("tokens") or 0) for r in raw_results)

    # Judge the median run per lane with Slot 1 Argon if requested (--judge-median)
    judge_calls_made = 0
    total_judge_tokens = 0
    per_lane_report: dict[str, Any] = {}
    any_canned = False

    for lane in lanes:
        lruns = [r for r in raw_results if r["lane"] == lane]
        any_canned = any_canned or any(r.get("matches_canned_stub") for r in lruns)
        word_counts = [r["x2"]["word_count"] for r in lruns if "word_count" in r.get("x2", {})]
        margins = [r["x2"]["word_band_margin"] for r in lruns if "word_band_margin" in r.get("x2", {})]
        x2_passes = sum(1 for r in lruns if r["x2"].get("all_x2_pass"))
        distinct_shas = len({r.get("output_sha256") for r in lruns if r.get("output_sha256")})

        texts = [r["x2"].get("primary_text", "") for r in lruns if r["x2"].get("primary_text")]
        pairwise_jaccards = [
            _jaccard_words(texts[i], texts[j])
            for i in range(len(texts))
            for j in range(i + 1, len(texts))
        ]

        # Median run by word count
        ordered_by_words = sorted(
            [r for r in lruns if "word_count" in r.get("x2", {})],
            key=lambda r: (r["x2"]["word_count"], r["run_no"]),
        )
        median_run = ordered_by_words[len(ordered_by_words) // 2] if ordered_by_words else None
        median_judge_summary = None
        if args.judge_median and median_run and median_run.get("parsed") and lane_inputs[lane]["judge_template"]:
            if judge_calls_made + 1 <= args.max_judge_calls:
                j_res = resolve_section_proof_judge_model(lane, "gemini_pro")
                j_prompt = _replace_candidate_in_judge_prompt(lane_inputs[lane]["judge_template"], median_run["parsed"])
                j_dir = out_dir / "median_judges" / lane
                j_dir.mkdir(parents=True, exist_ok=True)
                print(f"[median-judge] Grading {lane} median run #{median_run['run_no']} with {j_res.model_actual}...", flush=True)
                j_out = call_ide_cli_judge(
                    prompt=j_prompt,
                    model=j_res.model_actual,
                    input_hash=hashlib.sha256(j_prompt.encode("utf-8")).hexdigest()[:16],
                    provider_key="gemini_pro",
                    artifact_base=j_dir,
                    model_requested=j_res.model_requested,
                    reasoning_effort=j_res.reasoning_effort,
                    section_id=lane,
                    response_schema=build_judge_response_schema(),
                )
                judge_calls_made += 1
                j_tok = int((j_out.usage or {}).get("total_tokens") or 0)
                total_judge_tokens += j_tok
                median_judge_summary = {
                    "run_no": median_run["run_no"],
                    "model": j_out.model_name,
                    "evaluator_mode": j_out.evaluator_mode,
                    "score": j_out.score,
                    "pass": j_out.pass_,
                    "unsupported_claims": j_out.unsupported_claims,
                    "findings": j_out.findings,
                    "conversation_id": j_out.conversation_id,
                    "usage": j_out.usage,
                }

        hist_stats = _load_historical_keyed_stats(args.generator_inventory, lane, lane_inputs[lane]["allowed_ids"])
        # Strip bulky `parsed` before embedding run rows in top-level report (saved in generation_runs/*.json)
        slim_runs = [{k: v for k, v in r.items() if k != "parsed"} for r in lruns]
        max_possible_margin = lruns[0]["x2"].get("max_possible_band_margin") if lruns else None
        effective_margin_target = min(5.0, max_possible_margin) if max_possible_margin is not None else 5.0
        median_margin = median_run["x2"]["word_band_margin"] if median_run else None

        per_lane_report[lane] = {
            "writer_model": lane_inputs[lane]["writer_model"],
            "runs_completed": len(lruns),
            "x2_pass_count": x2_passes,
            "x2_pass_rate": round(x2_passes / len(lruns), 4) if lruns else 0.0,
            "word_counts": word_counts,
            "median_word_count": statistics.median(word_counts) if word_counts else None,
            "word_band": lruns[0]["x2"].get("word_band") if lruns else None,
            "max_possible_band_margin": max_possible_margin,
            "median_run_word_band_margin": median_margin,
            "meets_word_band_margin_check": (median_margin is not None and median_margin >= effective_margin_target),
            "meets_literal_5w_margin": (median_margin is not None and median_margin >= 5),
            "distinct_output_sha256_count": distinct_shas,
            "mean_pairwise_word_jaccard": round(sum(pairwise_jaccards) / len(pairwise_jaccards), 4) if pairwise_jaccards else None,
            "matches_any_canned_stub": any(r.get("matches_canned_stub") for r in lruns),
            "median_run_ide_judge": median_judge_summary,
            "historical_keyed_comparison": hist_stats,
            "runs": slim_runs,
        }

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lanes": lanes,
        "runs_per_lane": int(args.runs),
        "generation_calls_made": gen_calls_made,
        "max_calls": args.max_calls,
        "judge_calls_made": judge_calls_made,
        "max_judge_calls": args.max_judge_calls,
        "total_generation_tokens": total_gen_tokens,
        "total_judge_tokens": total_judge_tokens,
        "any_matches_canned_stub": any_canned,
        "all_lanes_x2_3_of_3": all(v["x2_pass_count"] == int(args.runs) for v in per_lane_report.values()),
        "zero_unsupported_claims_on_judged_medians": all(
            (v["median_run_ide_judge"] is None) or (len(v["median_run_ide_judge"].get("unsupported_claims") or []) == 0)
            for v in per_lane_report.values()
        ),
        "per_lane": per_lane_report,
    }
    report_path = out_dir / "generation_parity_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote generation parity report to {report_path}")
    if any_canned:
        print("HARD GATE FAILED: generated output matched retired canned stub!", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="run generation parity probe")
    run_p.add_argument("--lanes", default="executive_summary,unify_bullets,headline")
    run_p.add_argument("--runs", type=int, default=3)
    run_p.add_argument("--max-calls", type=int, default=9)
    run_p.add_argument("--judge-median", action="store_true", default=True)
    run_p.add_argument("--no-judge-median", dest="judge_median", action="store_false")
    run_p.add_argument("--max-judge-calls", type=int, default=3)
    run_p.add_argument("--workers", type=int, default=3)
    run_p.add_argument(
        "--truist-sections-root",
        type=Path,
        default=REPO_ROOT / "resume_graph_engine" / "artifacts" / "apps_rg" / "runtime_proofs" / "truist_judge_verify_20261118" / "modular_r4" / "sections",
    )
    run_p.add_argument(
        "--canned-digests",
        type=Path,
        default=REPO_ROOT / "resume_graph_engine" / "artifacts" / "apps_rg" / "judge_parity" / "w0" / "canned_digests.json",
    )
    run_p.add_argument(
        "--generator-inventory",
        type=Path,
        default=REPO_ROOT / "resume_graph_engine" / "artifacts" / "apps_rg" / "judge_parity" / "w0" / "generator_inventory.json",
    )
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
    run_p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return run_generation_probe(args)


if __name__ == "__main__":
    raise SystemExit(main())
