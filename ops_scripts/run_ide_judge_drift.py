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
from apps_eval.graders.judge.human_provenance import (
    compute_weighted_stakeholder_score,
    verify_human_label_ledger,
)
from infrastructure.sdks_mcps.agy_cli_transport import run_agy

DEFAULT_CACHE_PATH = REPO_ROOT / "artifacts" / "eval_harness" / "ide_judge_drift_cache.json"
DEFAULT_RECEIPT_PATH = REPO_ROOT / "artifacts" / "eval_harness" / "ide_judge_drift_receipt.json"
DEFAULT_BASELINE_PATH = REPO_ROOT / "artifacts" / "eval_harness" / "ide_judge_drift_baseline.json"

LIVE_DRIFT_SCORE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["rationale", "dimension_scores", "hard_fail_flags", "judge_score_1_5", "judge_pass"],
    "properties": {
        "rationale": {"type": "string"},
        "dimension_scores": {
            "type": "object",
            "additionalProperties": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "hard_fail_flags": {
            "type": "object",
            "additionalProperties": {"type": "boolean"},
        },
        "judge_score_1_5": {"type": "number", "minimum": 1.0, "maximum": 5.0},
        "judge_pass": {"type": "boolean"},
    },
    "additionalProperties": False,
}


def build_v3_live_drift_score_schema(check_ids: list[str]) -> dict[str, Any]:
    """Build Judge v3 atomic binary JSON schema (`cold_read_takeaway` + `YES`/`NO` per check)."""
    check_props = {
        cid: {
            "type": "object",
            "required": ["verdict", "evidence_span"],
            "properties": {
                "verdict": {"type": "string", "enum": ["YES", "NO"]},
                "evidence_span": {"type": "string"},
            },
            "additionalProperties": False,
        }
        for cid in check_ids
    }
    return {
        "type": "object",
        "required": ["cold_read_takeaway", "checks"],
        "properties": {
            "cold_read_takeaway": {"type": "string"},
            "checks": {
                "type": "object",
                "required": list(check_ids),
                "properties": check_props,
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def compute_v3_drift_unit_score_and_pass(
    parsed: Mapping[str, Any],
    rubric_doc: Mapping[str, Any],
) -> tuple[float, bool, dict[str, bool]]:
    """Deterministically compute `(normalized_unit_score, judge_pass, atomic_bools)` for Judge v3 checks."""
    checks_spec = rubric_doc.get("checks") or []
    raw_checks = parsed.get("checks") if isinstance(parsed.get("checks"), Mapping) else {}
    atomic_bools: dict[str, bool] = {}
    unit_score = 0.0
    crit_ok = True
    for spec in checks_spec:
        if not isinstance(spec, Mapping):
            continue
        cid = str(spec.get("id") or "")
        entry = raw_checks.get(cid) if isinstance(raw_checks, Mapping) else None
        verdict = str((entry or {}).get("verdict") if isinstance(entry, Mapping) else entry or "NO").strip().upper()
        passed_check = verdict == "YES"
        atomic_bools[cid] = passed_check
        if passed_check:
            unit_score += float(spec.get("weight", 0.0))
        elif bool(spec.get("critical", False)):
            crit_ok = False
    unit_score = round(max(0.0, min(1.0, unit_score)), 4)
    pass_thresh = float(rubric_doc.get("pass_threshold", 0.80))
    return unit_score, (crit_ok and unit_score >= pass_thresh - 1e-9), atomic_bools


def build_live_drift_score_schema(rubric_doc: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build strict Chain-of-Thought-first multi-dimensional JSON schema bound to `rubric_doc`."""
    if isinstance(rubric_doc, Mapping) and isinstance(rubric_doc.get("checks"), list):
        check_ids = [str(c["id"]) for c in rubric_doc["checks"] if isinstance(c, Mapping) and c.get("id")]
        return build_v3_live_drift_score_schema(check_ids)
    if not isinstance(rubric_doc, Mapping) or not isinstance(rubric_doc.get("dimensions"), list):
        return dict(LIVE_DRIFT_SCORE_SCHEMA)
    dim_ids = [str(d["id"]) for d in (rubric_doc.get("dimensions") or []) if isinstance(d, Mapping) and d.get("id")]
    flag_ids = [str(f["id"]) for f in (rubric_doc.get("hard_fail_flags") or []) if isinstance(f, Mapping) and f.get("id")]
    return {
        "type": "object",
        "required": ["rationale", "dimension_scores", "hard_fail_flags", "judge_score_1_5", "judge_pass"],
        "properties": {
            "rationale": {"type": "string"},
            "dimension_scores": {
                "type": "object",
                "required": dim_ids,
                "properties": {did: {"type": "integer", "minimum": 1, "maximum": 5} for did in dim_ids},
                "additionalProperties": False,
            },
            "hard_fail_flags": {
                "type": "object",
                "required": flag_ids,
                "properties": {fid: {"type": "boolean"} for fid in flag_ids},
                "additionalProperties": False,
            },
            "judge_score_1_5": {"type": "number", "minimum": 1.0, "maximum": 5.0},
            "judge_pass": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


def compute_mechanical_drift_score_and_pass(
    parsed: Mapping[str, Any],
    rubric_doc: Mapping[str, Any],
) -> tuple[float, bool, dict[str, int], dict[str, bool]]:
    """Deterministically derive `(judge_score_1_5, judge_pass, dim_scores, hard_fail_flags)` from rubric grades."""
    raw_dims = parsed.get("dimension_scores")
    raw_flags = parsed.get("hard_fail_flags")
    dim_scores: dict[str, int] = (
        {str(k): max(1, min(5, int(v))) for k, v in raw_dims.items() if not isinstance(v, bool)}
        if isinstance(raw_dims, Mapping)
        else {}
    )
    hard_flags: dict[str, bool] = (
        {str(k): bool(v) for k, v in raw_flags.items()}
        if isinstance(raw_flags, Mapping)
        else {}
    )
    raw_score = round(max(1.0, min(5.0, float(parsed.get("judge_score_1_5", 1.0)))), 4)
    raw_pass = bool(parsed.get("judge_pass", False))
    if dim_scores and isinstance(rubric_doc.get("dimensions"), list):
        mech_score = compute_weighted_stakeholder_score(dim_scores, rubric_doc)
        if mech_score > 0.0:
            raw_score = mech_score
        for dim_spec in rubric_doc.get("dimensions") or []:
            if not isinstance(dim_spec, Mapping):
                continue
            did = str(dim_spec.get("id") or "")
            floor = int(dim_spec.get("hard_floor", 3))
            if did in dim_scores and dim_scores[did] < floor:
                raw_pass = False
    if any(hard_flags.values()):
        raw_pass = False
    pass_thresh = float(rubric_doc.get("pass_threshold_mean", 4.0)) if isinstance(rubric_doc, Mapping) else 4.0
    if raw_score < pass_thresh:
        raw_pass = False
    return raw_score, raw_pass, dim_scores, hard_flags


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
    if isinstance(rubric_doc.get("checks"), list):
        return (
            f"You are an independent {item.engine} proof judge evaluating a {item.judge_family} candidate.\n"
            "First write a cold_read_takeaway summarizing what stands out, then evaluate every atomic check "
            "as YES or NO. For any NO verdict, quote a verbatim evidence_span from CANDIDATE_TEXT (or prefix "
            "OMISSION: when required context is absent). Return strict JSON matching the schema.\n\n"
            f"RUBRIC:\n{json.dumps(dict(rubric_doc), indent=2, sort_keys=True)}\n\n"
            f"TARGET_CONTEXT:\n{item.target_context}\n\n"
            f"ALLOWED_FACTS:\n{json.dumps(list(item.allowed_facts), indent=2)}\n\n"
            f"CANDIDATE_TEXT:\n{item.candidate_text}\n"
        )
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
        json_schema=build_live_drift_score_schema(rubric_doc),
        timeout_s=240,
        agy_bin=agy_bin,
    )
    parsed = res.structured_output if isinstance(res.structured_output, dict) else json.loads(res.response)
    if isinstance(rubric_doc.get("checks"), list):
        unit_s, mech_pass, atomic_bools = compute_v3_drift_unit_score_and_pass(parsed, rubric_doc)
        entry = {
            "item_id": item.item_id,
            "model_slug": res.model_reported,
            "normalized_unit_score": unit_s,
            "judge_score_1_5": round(1.0 + 4.0 * unit_s, 4),
            "judge_pass": mech_pass,
            "atomic_checks": atomic_bools,
            "rationale": str(parsed.get("cold_read_takeaway") or ""),
            "conversation_id": res.conversation_id,
            "total_tokens": int((res.usage or {}).get("total_tokens", 0)),
        }
    else:
        mech_score, mech_pass, dim_scores, hard_flags = compute_mechanical_drift_score_and_pass(parsed, rubric_doc)
        entry = {
            "item_id": item.item_id,
            "model_slug": res.model_reported,
            "judge_score_1_5": mech_score,
            "judge_pass": mech_pass,
            "dimension_scores": dim_scores,
            "hard_fail_flags": hard_flags,
            "rationale": str(parsed.get("rationale") or ""),
            "conversation_id": res.conversation_id,
            "total_tokens": int((res.usage or {}).get("total_tokens", 0)),
        }
    cache[cache_key] = entry
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="IDE LLM-as-a-Judge live drift runner and fast receipt verifier.")
    parser.add_argument("--check-receipt", action="store_true", help="Fast offline verification of sealed drift receipt.")
    parser.add_argument(
        "--check-preflight",
        action="store_true",
        help="Preflight verification of 48-item gold pools, external rubrics, and drift receipt (when human gold is adjudicated).",
    )
    parser.add_argument("--receipt", default=str(DEFAULT_RECEIPT_PATH))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_PATH))
    parser.add_argument("--agy-bin", default=None)
    parser.add_argument("--bypass-cache", action="store_true")
    parser.add_argument("--models", default="", help="Optional comma-separated subset of model slugs to refresh.")
    args = parser.parse_args(argv)

    if args.check_preflight:
        from apps_eval.graders.judge.gold_corpus import validate_stratification

        preflight_violations: list[str] = []
        total_gold_items = 0
        both_adjudicated = True
        for eng, prefix in (("resume_engine", "resume"), ("outreach_engine", "outreach")):
            cand_path = REPO_ROOT / "data" / "judge_calibration" / f"{prefix}_gold_candidates.v1.jsonl"
            adj_path = REPO_ROOT / "data" / "judge_calibration" / f"{prefix}_human_adjudicated.v1.json"
            if not adj_path.is_file():
                both_adjudicated = False
            if not cand_path.is_file():
                preflight_violations.append(f"MISSING_GOLD_CANDIDATES:{cand_path}")
            else:
                recs = load_gold_candidates_jsonl(cand_path)
                total_gold_items += len(recs)
                preflight_violations.extend(validate_stratification(recs, engine=eng))
            try:
                load_external_stakeholder_rubric(eng, repo_root=REPO_ROOT)
            except Exception as exc:  # guardian: allow-broad-exception -- report external rubric load error in preflight
                preflight_violations.append(f"EXTERNAL_RUBRIC_ERROR:{eng}:{exc}")
        try:
            from apps_eval.graders.judge.external_rubric_store import load_and_verify_external_rubric_v2

            load_and_verify_external_rubric_v2(REPO_ROOT / "config" / "governance" / "external_judge_rubric_v2.json")
        except (OSError, ValueError, KeyError) as exc:
            preflight_violations.append(f"EXTERNAL_RUBRIC_V2_ERROR:{exc}")

        if preflight_violations:
            print(json.dumps({"status": "FAIL", "violations": preflight_violations}, indent=2))
            return 1
        receipt_fp = Path(args.receipt)
        if receipt_fp.is_file() or both_adjudicated:
            ok, _viols, summary = verify_ide_judge_drift_receipt(receipt_fp, repo_root=REPO_ROOT)
            print(json.dumps(summary, indent=2))
            return 0 if ok else 1
        print(
            json.dumps(
                {
                    "status": "AWAITING_HUMAN_ADJUDICATION",
                    "gold_candidates_verified": total_gold_items,
                    "external_rubrics_verified": True,
                    "advisory": "Complete blind human grading via ops_scripts/blind_human_grading_cli.py to seal live drift receipt.",
                },
                indent=2,
            )
        )
        return 0

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
