"""Unit tests for tamper-evident human provenance ledger, synthetic batch rejection, and intra-rater unsealing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_eval.construct_validity import check_human_label_file_validity
from apps_eval.graders.judge.gold_corpus import build_blind_grading_packet, load_gold_candidates_jsonl
from apps_eval.graders.judge.human_provenance import (
    append_human_grade_entry,
    unseal_and_adjudicate_human_gold,
    verify_human_label_ledger,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_sequential_hash_chained_human_grades_verify_and_unseal(tmp_path: Path) -> None:
    candidates = load_gold_candidates_jsonl(REPO_ROOT / "data" / "judge_calibration" / "resume_gold_candidates.v1.jsonl")
    pkt = build_blind_grading_packet(candidates, engine="resume_engine", blinding_seed="prov-seed-1", repeat_count=3, repo_root=REPO_ROOT)
    ledger = tmp_path / "resume_human_gold.v1.jsonl"

    for idx, prompt in enumerate(pkt.prompts, start=1):
        meta = pkt.sealed_mapping[prompt.blind_id]
        is_pass = bool(meta["expected_pass"])
        scores = {
            "role_mandate_fit": 5 if is_pass else 2,
            "claim_credibility_and_grounding": 5 if is_pass else 1,
            "executive_signal_density": 4 if is_pass else 2,
            "authentic_human_voice": 4 if is_pass else 2,
            "decision_usefulness": 5 if is_pass else 1,
        }
        flags = {"fabricated_or_stretched_metric": not is_pass}
        append_human_grade_entry(
            ledger,
            blind_id=prompt.blind_id,
            engine="resume_engine",
            prompt_sha256=prompt.prompt_sha256,
            dimension_scores=scores,
            hard_fail_flags=flags,
            overall_pass=is_pass,
            provenance_mode="in_chat_blind",
            provenance_ref="conv_human_session_01",
            reviewer_notes=f"Human review of item {idx}",
            recorded_at=f"2026-11-22T20:{idx:02d}:10Z",
            repo_root=REPO_ROOT,
        )

    ok, viols, summary = verify_human_label_ledger(ledger)
    assert ok is True, viols
    assert summary["entry_count"] == 27
    assert check_human_label_file_validity(ledger) == []

    adj = unseal_and_adjudicate_human_gold(ledger, pkt.sealed_mapping)
    assert adj["adjudicated_count"] == 24
    assert adj["repeat_pairs_evaluated"] == 3
    assert adj["intra_rater_repeat_kappa"] == 1.0
    assert adj["intra_rater_repeat_agreement_rate"] == 1.0


def test_construct_validity_rejects_batch_stamped_synthetic_csv_and_tampered_ledger(tmp_path: Path) -> None:
    # 1. Verify historical synthetic planted seed CSV is caught by construct validity
    synth_csv = REPO_ROOT / "outreach_engine" / "data" / "evals" / "holdout" / "synthetic_planted_seed.outreach_quality.v1.csv"
    synth_viols = check_human_label_file_validity(synth_csv)
    assert any(v["code"] == "SYNTHETIC_BATCH_HUMAN_LABELS" for v in synth_viols)

    # 2. Verify cleaned human_labels.outreach_quality.v1.csv has zero synthetic violations
    clean_csv = REPO_ROOT / "outreach_engine" / "data" / "evals" / "holdout" / "human_labels.outreach_quality.v1.csv"
    assert check_human_label_file_validity(clean_csv) == []

    # 3. Verify non-monotonic timestamp is rejected on append
    ledger = tmp_path / "bad_ledger.jsonl"
    base_scores = {
        "reply_willingness": 4,
        "peer_executive_tone": 4,
        "grounded_relevance": 5,
        "low_friction_clarity": 4,
    }
    append_human_grade_entry(
        ledger,
        blind_id="LIC_BLIND_001",
        engine="outreach_engine",
        prompt_sha256="a" * 64,
        dimension_scores=base_scores,
        hard_fail_flags={},
        overall_pass=True,
        provenance_mode="in_chat_blind",
        provenance_ref="conv_01",
        recorded_at="2026-11-22T20:01:00Z",
        repo_root=REPO_ROOT,
    )
    with pytest.raises(ValueError, match="Non-monotonic timestamp"):
        append_human_grade_entry(
            ledger,
            blind_id="LIC_BLIND_002",
            engine="outreach_engine",
            prompt_sha256="b" * 64,
            dimension_scores=base_scores,
            hard_fail_flags={},
            overall_pass=True,
            provenance_mode="in_chat_blind",
            provenance_ref="conv_01",
            recorded_at="2026-11-22T20:01:00Z",
            repo_root=REPO_ROOT,
        )

    # 4. Verify tampering with a recorded score invalidates SHA-256 chain
    row = json.loads(ledger.read_text(encoding="utf-8").strip())
    row["overall_pass"] = False
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    ok, viols, _ = verify_human_label_ledger(ledger)
    assert ok is False
    assert any("tamper mismatch" in v for v in viols)
