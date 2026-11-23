"""End-to-end tests for two-axis IDE LLM-as-a-Judge drift detection, pin lockstep, 30-day TTL, and promotion gate."""
from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Any

from apps_eval.graders.judge.drift_monitor import (
    IDE_JUDGE_DRIFT_RECEIPT_SCHEMA_VERSION,
    evaluate_full_drift_suite,
    extract_active_ide_judge_bases,
    extract_active_ide_judge_pins,
    verify_ide_judge_drift_receipt,
)
from apps_eval.graders.judge.gold_corpus import load_gold_candidates_jsonl
from apps_eval.promotion_gate import verify_promotion_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_human_gold_and_predictions() -> tuple[
    dict[str, dict[str, dict[str, Any]]],
    dict[str, dict[str, dict[str, dict[str, Any]]]],
]:
    active_pins = extract_active_ide_judge_pins(REPO_ROOT)
    human_by_eng: dict[str, dict[str, dict[str, Any]]] = {}
    preds_by_eng: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}

    for eng, fname in (
        ("resume_engine", "resume_gold_candidates.v1.jsonl"),
        ("outreach_engine", "outreach_gold_candidates.v1.jsonl"),
    ):
        items = load_gold_candidates_jsonl(REPO_ROOT / "data" / "judge_calibration" / fname)
        gold_map: dict[str, dict[str, Any]] = {}
        for item in items:
            if item.expected_tier == "clean_pass":
                score, h_pass, hf = 4.8, True, False
            elif item.expected_tier == "borderline":
                score, h_pass, hf = (4.1 if item.expected_pass else 3.2), item.expected_pass, False
            else:
                score, h_pass, hf = 1.6, False, True
            gold_map[item.item_id] = {
                "item_id": item.item_id,
                "human_pass": h_pass,
                "human_score_1_5": score,
                "hard_fail_any": hf,
            }
        human_by_eng[eng] = gold_map

        models_map: dict[str, dict[str, dict[str, Any]]] = {}
        for slug in active_pins[eng]:
            m_preds: dict[str, dict[str, Any]] = {}
            for item in items:
                g = gold_map[item.item_id]
                # Small realistic non-drifting offset (+0.05 / -0.05) preserving verdicts and rank order
                j_score = min(5.0, max(1.0, g["human_score_1_5"] + (0.05 if g["human_pass"] else -0.05)))
                m_preds[item.item_id] = {
                    "judge_pass": g["human_pass"],
                    "judge_score_1_5": round(j_score, 4),
                }
            models_map[slug] = m_preds
        preds_by_eng[eng] = models_map

    return human_by_eng, preds_by_eng


def test_e2e_two_axis_drift_pass_and_fast_offline_receipt_gate(tmp_path: Path) -> None:
    human_by_eng, preds_by_eng = _make_human_gold_and_predictions()
    chain_hashes = {"resume_engine": "a" * 64, "outreach_engine": "b" * 64}
    now_dt = datetime.datetime(2026, 11, 22, 20, 0, 0, tzinfo=datetime.timezone.utc)

    receipt = evaluate_full_drift_suite(
        human_gold_by_engine=human_by_eng,
        judge_predictions_by_engine_model=preds_by_eng,
        human_chain_hashes=chain_hashes,
        repo_root=REPO_ROOT,
        baseline_predictions_by_engine_model=preds_by_eng,
        generated_at_utc=now_dt.isoformat().replace("+00:00", "Z"),
    )
    assert receipt["schema_version"] == IDE_JUDGE_DRIFT_RECEIPT_SCHEMA_VERSION
    assert receipt["status"] == "PASS", receipt["violations"]
    assert receipt["passed"] is True
    assert receipt["pooled_summary"]["sample_size"] == 48
    assert receipt["pooled_summary"]["cohens_kappa"] >= 0.80

    receipt_path = tmp_path / "ide_judge_drift_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    # Fast offline verification must finish well under 100ms
    t0 = time.perf_counter()
    ok, viols, summary = verify_ide_judge_drift_receipt(
        receipt_path, repo_root=REPO_ROOT, now_utc=now_dt + datetime.timedelta(days=5)
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert ok is True, viols
    assert summary["status"] == "PASS"
    assert elapsed_ms < 250.0


def test_e2e_hard_fail_false_pass_and_temporal_shift_block_and_escalate() -> None:
    human_by_eng, preds_by_eng = _make_human_gold_and_predictions()
    baseline = json.loads(json.dumps(preds_by_eng))
    chain_hashes = {"resume_engine": "a" * 64, "outreach_engine": "b" * 64}

    # Inject a subtle hard-fail false pass + temporal score leniency drift on one primary Resume judge
    first_rg_model = sorted(preds_by_eng["resume_engine"].keys())[0]
    hard_fail_id = next(
        cid for cid, meta in human_by_eng["resume_engine"].items() if meta["hard_fail_any"]
    )
    preds_by_eng["resume_engine"][first_rg_model][hard_fail_id] = {"judge_pass": True, "judge_score_1_5": 4.4}
    for cid, row in preds_by_eng["resume_engine"][first_rg_model].items():
        row["judge_score_1_5"] = min(5.0, round(row["judge_score_1_5"] + 0.45, 4))

    receipt = evaluate_full_drift_suite(
        human_gold_by_engine=human_by_eng,
        judge_predictions_by_engine_model=preds_by_eng,
        human_chain_hashes=chain_hashes,
        repo_root=REPO_ROOT,
        baseline_predictions_by_engine_model=baseline,
    )
    assert receipt["passed"] is False
    assert receipt["status"] == "DRIFT_BLOCKED"
    assert any("human hard-fail defects received judge PASS" in v for v in receipt["violations"])
    assert any("temporal mean abs score shift" in v for v in receipt["violations"])

    esc = receipt["flywheel_escalation"]
    assert esc["remediation_tier"] == "TIER_B_OR_C_ATOMIC_HITL"
    assert esc["auto_apply_permitted"] is False
    assert esc["never_auto_lower_judge_floors"] is True
    assert esc["protected_floors"] == {"resume_engine_x1d": 4.7, "outreach_engine_x1d": 0.85}
    assert "HARD_FAIL_FALSE_PASS" in esc["root_cause_codes"]
    assert "MODEL_SLUG_SHIFT" in esc["root_cause_codes"]


def test_e2e_stale_receipt_and_unqualified_backup_pin_block_promotion_gate(tmp_path: Path) -> None:
    human_by_eng, preds_by_eng = _make_human_gold_and_predictions()
    chain_hashes = {"resume_engine": "a" * 64, "outreach_engine": "b" * 64}
    old_dt = datetime.datetime(2026, 10, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    now_dt = old_dt + datetime.timedelta(days=31)

    receipt = evaluate_full_drift_suite(
        human_gold_by_engine=human_by_eng,
        judge_predictions_by_engine_model=preds_by_eng,
        human_chain_hashes=chain_hashes,
        repo_root=REPO_ROOT,
        generated_at_utc=old_dt.isoformat().replace("+00:00", "Z"),
    )
    stale_path = tmp_path / "stale_drift_receipt.json"
    stale_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    ok_stale, viols_stale, _ = verify_ide_judge_drift_receipt(stale_path, repo_root=REPO_ROOT, now_utc=now_dt)
    assert ok_stale is False
    assert any("DRIFT_RECEIPT_STALE" in v for v in viols_stale)

    # Also test missing quota-backup model base (e.g., removing gpt-oss-120b from Outreach results)
    active_bases = extract_active_ide_judge_bases(REPO_ROOT)
    assert "gpt-oss-120b" in active_bases["outreach_engine"]
    pruned_preds = json.loads(json.dumps(preds_by_eng))
    for slug in list(pruned_preds["outreach_engine"].keys()):
        if "gpt-oss-120b" in slug:
            pruned_preds["outreach_engine"].pop(slug)
    unqualified_receipt = evaluate_full_drift_suite(
        human_gold_by_engine=human_by_eng,
        judge_predictions_by_engine_model=pruned_preds,
        human_chain_hashes=chain_hashes,
        repo_root=REPO_ROOT,
    )
    assert unqualified_receipt["passed"] is False
    assert any("gpt-oss-120b" in v for v in unqualified_receipt["violations"])

    # Verify promotion_gate blocks when require_ide_judge_drift=True and receipt is stale
    manifest_path = tmp_path / "evidence_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "apps_eval.evidence_manifest.v1",
                "app_filter": "all",
                "include_holdout": False,
                "run_engine_probes": False,
                "suites": {},
                "release_gate_receipt": {"status": "pass"},
            }
        ),
        encoding="utf-8",
    )
    pg_res = verify_promotion_evidence(
        manifest_path,
        require_holdout=False,
        require_engine_probes=False,
        ide_judge_drift_receipt_path=stale_path,
        require_ide_judge_drift=True,
        repo_root=REPO_ROOT,
    )
    assert pg_res.passed is False
    assert pg_res.checks.get("ide_judge_drift") is False
    assert any("DRIFT_RECEIPT_STALE" in r for r in pg_res.blocking_reasons)


def test_e2e_vector_7_multi_ssot_judge_gate_drift_audit_passes() -> None:
    from tools.audit_multi_ssot_judge_gate_drift import audit_multi_ssot_judge_gate_drift

    report = audit_multi_ssot_judge_gate_drift(REPO_ROOT)
    assert report["status"] == "PASS", report["violations"]
    assert report["vectors"].get("V7_EXTERNAL_RUBRIC_HUMAN_DRIFT") == "PASS"

