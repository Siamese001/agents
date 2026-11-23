"""Unit and adversarial tests for Wave 1 QRELS rubric contract and 4-channel TREC Depth-10 pooling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_eval.qrels.qrels_rubric_contract import (
    BLIND_FORBIDDEN_FIELDS,
    QrelsQuarantineDisposition,
    build_canonical_qrels_rubric_payload,
    enforce_qrels_grade_consistency,
    load_and_verify_qrels_rubric,
    normalize_display_dates,
    shuffle_qrels_pool_seeded,
    split_core_and_boilerplate,
    strip_blind_forbidden_fields,
)
from apps_eval.qrels.trec_pooling import (
    audit_cosine_stratification,
    build_blind_four_passage_panel,
    build_trec_depth_k_query_pool,
    compute_pre_grading_dominance_audit,
    validate_zero_leakage_partitions,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_external_qrels_rubric_loads_and_fails_closed_on_tamper(tmp_path: Path) -> None:
    rubric = load_and_verify_qrels_rubric(REPO_ROOT / "config/governance/external_qrels_rubric_v1.json")
    assert rubric["rubric_id"] == "external_qrels_rubric_v1"
    assert rubric["grade_values"] == [0, 1, 2, 3]
    assert len(rubric["atomic_checks"]) == 5
    assert len(rubric["rejection_tags"]) == 6

    tampered = dict(rubric)
    tampered["relevant_grade_floor"] = 1
    bad_path = tmp_path / "tampered_rubric.json"
    bad_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_and_verify_qrels_rubric(bad_path)


def test_core_and_boilerplate_split_and_mmddyyyy_dates() -> None:
    raw = (
        "Action: Built governed AI control plane on 2026-08-14 achieving 99.9% uptime. "
        "Scope: Enterprise Cloud Platform. Operating context: Global banking division updated 09.15.2026."
    )
    core, footer = split_core_and_boilerplate(raw)
    assert core == "Action: Built governed AI control plane on 08/14/2026 achieving 99.9% uptime."
    assert footer.startswith("Scope: Enterprise Cloud Platform.")
    assert "09/15/2026" in footer
    assert normalize_display_dates("Delivered 2026-11-23") == "Delivered 11/23/2026"


def test_mechanical_grade_consistency_locks_and_quarantine() -> None:
    # Valid Grade 3 with passing checks
    enforce_qrels_grade_consistency(
        3,
        atomic_checks={"core_answers_query": True, "not_boilerplate_stub": True, "section_and_role_fit": True},
    )
    # Grade 2/3 blocked when stub or section mismatch check fails
    with pytest.raises(ValueError, match="Maximum permitted grade is 1"):
        enforce_qrels_grade_consistency(3, atomic_checks={"not_boilerplate_stub": False})
    with pytest.raises(ValueError, match="Maximum permitted grade is 1"):
        enforce_qrels_grade_consistency(2, atomic_checks={"section_and_role_fit": False})
    # Grade 1 allowed even when stub check fails
    enforce_qrels_grade_consistency(1, atomic_checks={"not_boilerplate_stub": False})
    # Grade 0 requires >= 1 rejection tag or >= 8 char rationale
    with pytest.raises(ValueError, match="Grade 0 requires"):
        enforce_qrels_grade_consistency(0, rejection_tags=(), critique_rationale="short")
    enforce_qrels_grade_consistency(0, rejection_tags=("WRONG_EMPLOYER",))
    enforce_qrels_grade_consistency(0, critique_rationale="Wrong client domain and unrelated keywords.")

    q = QrelsQuarantineDisposition(
        pair_id="q1::rec1",
        query_id="q1",
        record_id="rec1",
        surface="resume_graph_engine",
        topic_family="topic_01",
        partition="calibration",
        artifact_sha256="a" * 64,
        reason="ABSTAIN_INSUFFICIENT_EVIDENCE",
        annotator_id="amit.ayer",
        recorded_at_utc="2026-11-23T06:00:00Z",
    )
    assert q.to_dict()["reason"] == "ABSTAIN_INSUFFICIENT_EVIDENCE"
    with pytest.raises(ValueError, match="Invalid quarantine reason"):
        QrelsQuarantineDisposition(
            pair_id="q1::rec1",
            query_id="q1",
            record_id="rec1",
            surface="resume_graph_engine",
            topic_family="topic_01",
            partition="calibration",
            artifact_sha256="a" * 64,
            reason="SKIP_BORED",
            annotator_id="amit.ayer",
            recorded_at_utc="2026-11-23T06:00:00Z",
        )


def test_trec_depth_k_pooling_dominance_and_blind_four_passage_panel() -> None:
    catalog = {
        f"rec_{i}": {
            "record_id": f"rec_{i}",
            "retrieval_text": f"Core evidence statement {i} dated 2026-10-0{min(i,9)}. Scope: Repeated context {i}.",
            "title": f"Record {i}",
            "employer": "Unify Consulting",
            "external_eligible": True,
        }
        for i in range(1, 16)
    }
    catalog["rec_secret"] = {
        "record_id": "rec_secret",
        "retrieval_text": "Private restricted salary record",
        "classification": "restricted",
        "external_eligible": False,
    }
    query = {
        "query_id": "q_01",
        "query_text": "Which platform initiative drove $22M IP revenue?",
        "topic_id": "topic_01",
        "partition": "dev",
        "answerable": True,
        "target_record_id": "rec_1",
    }
    channel_rankings = {
        "dense": [{"record_id": "rec_2", "score": 0.9}, {"record_id": "rec_1", "score": 0.85}, {"record_id": "rec_secret", "score": 0.99}],
        "sparse": [{"record_id": "rec_3", "score": 4.2}, {"record_id": "rec_1", "score": 4.0}],
        "colbert": [{"record_id": "rec_1", "score": 0.88}, {"record_id": "rec_4", "score": 0.7}],
        "bm25": [{"record_id": "rec_5", "score": 9.1}, {"record_id": "rec_6", "score": 8.0}],
    }
    fused = [
        {"record_id": "rec_1", "score": 0.062},
        {"record_id": "rec_2", "score": 0.041},
        {"record_id": "rec_3", "score": 0.038},
        {"record_id": "rec_5", "score": 0.032},
    ]
    pooled = build_trec_depth_k_query_pool(query, channel_rankings, catalog=catalog, fused_ranking=fused, top_k_per_channel=10)
    pooled_ids = {c["record_id"] for c in pooled["candidates"]}
    assert "rec_secret" not in pooled_ids
    assert {"rec_1", "rec_2", "rec_3", "rec_4", "rec_5", "rec_6"} <= pooled_ids
    assert pooled["top1_vs_top2_margin"] == pytest.approx(0.021)

    dom = compute_pre_grading_dominance_audit([pooled])
    assert dom["hybrid_beats_or_matches_single_channels_recall10"] is True
    assert dom["hybrid_beats_or_matches_single_channels_mrr10"] is True
    assert dom["channel_metrics"]["hybrid_fused"]["mrr_at_10"] == 1.0

    panel, slot_map = build_blind_four_passage_panel(pooled, seed=42)
    assert len(panel["passages"]) == 4
    assert set(slot_map.keys()) == {"A", "B", "C", "D"}
    assert "rec_1" in slot_map.values()
    for p in panel["passages"]:
        assert not (set(p.keys()) & BLIND_FORBIDDEN_FIELDS)
        assert "Scope:" not in p["core_statement"]
        assert p["boilerplate_footer"].startswith("Scope:")

    # Seeded shuffle determinism + forbidden field stripping
    s1 = shuffle_qrels_pool_seeded(pooled["candidates"], seed=7)
    s2 = shuffle_qrels_pool_seeded(pooled["candidates"], seed=7)
    assert [c["record_id"] for c in s1] == [c["record_id"] for c in s2]
    sanitized = strip_blind_forbidden_fields(pooled["candidates"][0])
    assert not (set(sanitized.keys()) & BLIND_FORBIDDEN_FIELDS)


def test_zero_leakage_partition_and_cosine_stratification() -> None:
    clean = validate_zero_leakage_partitions(
        {
            "topic_assignments": {"dev": ["t1"], "calibration": ["t2"], "final_holdout": ["t3"]},
            "query_partitions": {"dev": ["q1"], "calibration": ["q2"], "final_holdout": ["q3"]},
        }
    )
    assert clean["has_leakage"] is False

    leaked = validate_zero_leakage_partitions(
        {
            "topic_assignments": {"dev": ["t1"], "calibration": ["t1"], "final_holdout": ["t3"]},
            "query_partitions": {"dev": ["q1"], "calibration": ["q2"], "final_holdout": ["q3"]},
        }
    )
    assert leaked["has_leakage"] is True
    assert leaked["overlap_dev_cal"] == ["t1"]

    strat = audit_cosine_stratification(
        {"q1": [1.0, 0.0], "q2": [0.99, 0.14], "q3": [0.0, 1.0]},
        [
            {"query_id": "q1", "topic_id": "t1", "tier": "tier1_paraphrase"},
            {"query_id": "q2", "topic_id": "t1", "tier": "tier1_paraphrase"},
            {"query_id": "q3", "topic_id": "t2", "tier": "tier2_orthogonal"},
        ],
    )
    assert strat["mean_paraphrase_cosine"] > 0.95
    assert strat["mean_cross_topic_cosine"] < 0.05
    assert build_canonical_qrels_rubric_payload()["rubric_id"] == "external_qrels_rubric_v1"
