"""Unit tests for independent external stakeholder rubrics, 48-item gold corpus stratification, blinding, and CSV round-trip."""
from __future__ import annotations

import csv
from pathlib import Path

from apps_eval.graders.judge.gold_corpus import (
    FORBIDDEN_BLIND_KEYS,
    OUTREACH_JUDGE_SURFACES,
    RESUME_JUDGE_FAMILIES,
    build_blind_grading_packet,
    export_blind_review_sheet_csv,
    import_blind_review_sheet_csv,
    load_external_stakeholder_rubric,
    load_gold_candidates_jsonl,
    validate_stratification,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_external_stakeholder_rubrics_load_and_weights_sum_to_one() -> None:
    for engine in ("resume_engine", "outreach_engine"):
        doc, sha = load_external_stakeholder_rubric(engine, repo_root=REPO_ROOT)
        assert len(sha) == 64
        dims = doc["dimensions"]
        assert len(dims) >= 4
        assert abs(sum(float(d["weight"]) for d in dims) - 1.0) < 1e-6
        assert len(doc["hard_fail_flags"]) >= 4


def test_frozen_48_item_gold_corpora_satisfy_stratification_invariants() -> None:
    rg = load_gold_candidates_jsonl(REPO_ROOT / "data" / "judge_calibration" / "resume_gold_candidates.v1.jsonl")
    lic = load_gold_candidates_jsonl(REPO_ROOT / "data" / "judge_calibration" / "outreach_gold_candidates.v1.jsonl")

    assert validate_stratification(rg, engine="resume_engine") == []
    assert validate_stratification(lic, engine="outreach_engine") == []
    assert len(rg) == 24 and len(lic) == 24
    assert {r.judge_family for r in rg} == set(RESUME_JUDGE_FAMILIES)
    assert {r.judge_family for r in lic} == set(OUTREACH_JUDGE_SURFACES)


def test_blinding_packet_has_zero_leakage_and_three_repeat_anchors() -> None:
    rg = load_gold_candidates_jsonl(REPO_ROOT / "data" / "judge_calibration" / "resume_gold_candidates.v1.jsonl")
    pkt = build_blind_grading_packet(
        rg,
        engine="resume_engine",
        blinding_seed="unit-test-seed-001",
        repeat_count=3,
        repo_root=REPO_ROOT,
    )
    assert len(pkt.prompts) == 27
    pkt.assert_zero_leakage()
    repeats = [k for k, v in pkt.sealed_mapping.items() if v["is_repeat_anchor"]]
    assert len(repeats) == 3
    for prompt in pkt.prompts:
        d = prompt.to_dict()
        assert not (set(d.keys()) & FORBIDDEN_BLIND_KEYS)


def test_offline_csv_review_sheet_export_and_import_roundtrip(tmp_path: Path) -> None:
    lic = load_gold_candidates_jsonl(REPO_ROOT / "data" / "judge_calibration" / "outreach_gold_candidates.v1.jsonl")
    pkt = build_blind_grading_packet(
        lic,
        engine="outreach_engine",
        blinding_seed="unit-test-seed-002",
        repeat_count=3,
        repo_root=REPO_ROOT,
    )
    sheet_path = export_blind_review_sheet_csv(pkt, tmp_path / "outreach_blind_sheet.csv", repo_root=REPO_ROOT)
    assert sheet_path.is_file()

    # Fill out sheet with valid sequential human timestamps and scores
    with sheet_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    assert len(rows) == 27
    assert not (set(fieldnames) & FORBIDDEN_BLIND_KEYS)

    for idx, row in enumerate(rows, start=1):
        row["reply_willingness"] = "4"
        row["peer_executive_tone"] = "4"
        row["grounded_relevance"] = "5"
        row["low_friction_clarity"] = "4"
        row["overall_pass"] = "true"
        row["reviewer_notes"] = f"Reviewed item {idx}"
        row["graded_at_utc"] = f"2026-11-22T20:{idx:02d}:05Z"

    filled_path = tmp_path / "outreach_blind_sheet_filled.csv"
    with filled_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    imported = import_blind_review_sheet_csv(filled_path, engine="outreach_engine", repo_root=REPO_ROOT)
    assert len(imported) == 27
    assert imported[0]["overall_pass"] is True
    assert imported[0]["dimension_scores"]["grounded_relevance"] == 5
    assert len(imported[0]["source_sheet_sha256"]) == 64
