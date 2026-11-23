#!/usr/bin/env python3
"""On-demand live IDE LLM-as-a-Judge drift sweep runner and fast offline receipt verifier."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.graders.judge.drift_monitor import (
    evaluate_full_drift_suite,
    extract_active_ide_judge_pins,
    verify_ide_judge_drift_receipt,
)
from apps_eval.graders.judge.gold_corpus import (
    GoldCandidateRecord,
    canonical_sha256,
    load_external_stakeholder_rubric,
    load_gold_candidates_jsonl,
)
from apps_eval.graders.judge.human_provenance import verify_human_label_ledger
from infrastructure.sdks_mcps.agy_cli_transport import run_agy

DEFAULT_CACHE_PATH = REPO_ROOT / "artifacts" / "eval_harness" / "ide_judge_drift_cache.json"
DEFAULT_RECEIPT_PATH = REPO_ROOT / "artifacts" / "eval_harness" / "ide_judge_drift_receipt.json"
DEFAULT_BASELINE_PATH = REPO_ROOT / "artifacts" / "eval_harness" / "ide_judge_drift_baseline.json"

LIVE_DRIFT_SCORE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["judge_score_1_5", "judge_pass", "rationale"],
    "properties": {
        "judge_score_1_5": {"type": "number", "minimum": 1.0, "maximum": 5.0},
        "judge_pass": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
    "additionalProperties": False,
}


def _load_cache(cache_path: Path) -> dict[str, Any]:
    if cache_path.is_file():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save_cache(cache_path: Path, cache: Mapping[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(dict(cache), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_live_probe_prompt(item: GoldCandidateRecord, rubric_doc: Mapping[str, Any]) -> str:
    return (
        f"You are an independent {item.engine} proof judge evaluating a {item.judge_family} candidate.\n"
        "Grade strictly against the external stakeholder rubric on a 1.0 to 5.0 scale.\n"
        "Set judge_pass=false if ANY hard-fail condition (stretched/invented metric, fake familiarity, "
        "JD mimicry, employer distortion, confidential leak, spam hype) is present.\n"
        "Return strict JSON matching the schema.\n\n"
        f"RUBRIC:\n{json.dumps(dict(rubric_doc), indent=2, sort_keys=True)}\n\n"
        f"TARGET_CONTEXT:\n{item.target_context}\n\n"
        f"ALLOWED_FACTS:\n{json.dumps(list(item.allowed_facts), indent=2)}\n\n"
        f"CANDIDATE_TEXT:\n{item.candidate_text}\n"
    )


def score_candidate_cached(
    item: GoldCandidateRecord,
    *,
    model_slug: str,
    rubric_doc: Mapping[str, Any],
    rubric_sha256: str,
    cache: dict[str, Any],
    agy_bin: str | None = None,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    """Score one gold candidate via live keyless `agy -p`, cached by `(item_digest, rubric_sha256, model_slug)`."""
    cache_key = canonical_sha256(
        {"item_digest": item.item_digest(), "rubric_sha256": rubric_sha256, "model_slug": model_slug}
    )
    if not bypass_cache and cache_key in cache:
        return dict(cache[cache_key])

    res = run_agy(
        _build_live_probe_prompt(item, rubric_doc),
        model=model_slug,
        json_schema=LIVE_DRIFT_SCORE_SCHEMA,
        timeout_s=240,
        agy_bin=agy_bin,
    )
    parsed = res.structured_output if isinstance(res.structured_output, dict) else json.loads(res.response)
    entry = {
        "item_id": item.item_id,
        "model_slug": res.model_reported,
        "judge_score_1_5": round(max(1.0, min(5.0, float(parsed["judge_score_1_5"]))), 4),
        "judge_pass": bool(parsed["judge_pass"]),
        "rationale": str(parsed.get("rationale") or ""),
        "conversation_id": res.conversation_id,
        "total_tokens": int((res.usage or {}).get("total_tokens", 0)),
    }
    cache[cache_key] = entry
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IDE LLM-as-a-Judge live drift runner and fast receipt verifier.")
    parser.add_argument("--check-receipt", action="store_true", help="Fast offline verification of sealed drift receipt.")
    parser.add_argument("--receipt", default=str(DEFAULT_RECEIPT_PATH))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH))
    parser.add_argument("--agy-bin", default=None)
    parser.add_argument("--bypass-cache", action="store_true")
    parser.add_argument("--models", default="", help="Optional comma-separated subset of model slugs to refresh.")
    args = parser.parse_args(argv)

    if args.check_receipt:
        ok, viols, summary = verify_ide_judge_drift_receipt(Path(args.receipt), repo_root=REPO_ROOT)
        print(json.dumps(summary, indent=2))
        return 0 if ok else 1

    human_gold: dict[str, dict[str, Any]] = {}
    chain_hashes: dict[str, str] = {}
    candidates_by_eng: dict[str, list[GoldCandidateRecord]] = {}

    for eng, prefix in (("resume_engine", "resume"), ("outreach_engine", "outreach")):
        cand_path = REPO_ROOT / "data" / "judge_calibration" / f"{prefix}_gold_candidates.v1.jsonl"
        ledger_path = REPO_ROOT / "data" / "judge_calibration" / f"{prefix}_human_gold.v1.jsonl"
        adj_path = REPO_ROOT / "data" / "judge_calibration" / f"{prefix}_human_adjudicated.v1.json"
        if not adj_path.is_file():
            raise SystemExit(
                f"Missing adjudicated human gold file {adj_path}. Complete blind human grading via "
                "ops_scripts/blind_human_grading_cli.py before running live drift calibration."
            )
        ok, viols, l_meta = verify_human_label_ledger(ledger_path)
        if not ok:
            raise SystemExit(f"Invalid human label ledger {ledger_path}: {viols}")
        adj_doc = json.loads(adj_path.read_text(encoding="utf-8"))
        human_gold[eng] = adj_doc.get("items") or {}
        chain_hashes[eng] = str(l_meta.get("chain_head_sha256") or "")
        candidates_by_eng[eng] = load_gold_candidates_jsonl(cand_path)

    active_pins = extract_active_ide_judge_pins(REPO_ROOT)
    filter_models = {m.strip() for m in args.models.split(",") if m.strip()}
    cache_path = Path(args.cache)
    cache = _load_cache(cache_path)

    preds_by_eng: dict[str, dict[str, dict[str, Any]]] = {"resume_engine": {}, "outreach_engine": {}}
    for eng in ("resume_engine", "outreach_engine"):
        rubric_doc, rubric_sha = load_external_stakeholder_rubric(eng, repo_root=REPO_ROOT)
        models = [m for m in active_pins[eng] if not filter_models or m in filter_models]
        for model_slug in models:
            preds_by_eng[eng][model_slug] = {}
            for item in candidates_by_eng[eng]:
                preds_by_eng[eng][model_slug][item.item_id] = score_candidate_cached(
                    item,
                    model_slug=model_slug,
                    rubric_doc=rubric_doc,
                    rubric_sha256=rubric_sha,
                    cache=cache,
                    agy_bin=args.agy_bin,
                    bypass_cache=args.bypass_cache,
                )
            _save_cache(cache_path, cache)

    baseline_path = Path(args.baseline)
    baseline_preds = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.is_file() else None
    receipt = evaluate_full_drift_suite(
        human_gold_by_engine=human_gold,
        judge_predictions_by_engine_model=preds_by_eng,
        human_chain_hashes=chain_hashes,
        repo_root=REPO_ROOT,
        baseline_predictions_by_engine_model=baseline_preds,
    )
    out_path = Path(args.receipt)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if receipt["passed"] and not baseline_path.is_file():
        baseline_path.write_text(json.dumps(preds_by_eng, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(out_path), "status": receipt["status"], "pooled_summary": receipt["pooled_summary"]}, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
