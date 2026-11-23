"""Unit and adversarial tests for Wave 1: DIE-Parity External Rubric, 6 Atomic Checks, Failure Tags & Store."""
from __future__ import annotations

from pathlib import Path

import pytest

from apps_eval.graders.judge.external_rubric_store import (
    DEFAULT_EXTERNAL_RUBRIC_REL_PATH,
    EXTERNAL_RUBRIC_DIMENSIONS,
    ExternalRubricHumanStore,
    compute_external_rubric_sha256,
    compute_payload_sha256,
    load_and_verify_external_rubric,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_external_judge_rubric_v1_matches_die_sha256_and_four_pillars() -> None:
    rubric = load_and_verify_external_rubric(REPO_ROOT / DEFAULT_EXTERNAL_RUBRIC_REL_PATH)
    assert rubric["rubric_id"] == "external_judge_rubric_v1"
    assert rubric["rubric_sha256"] == "d0888a34cf4d0154621eec3c347c29a6fbdc48f8e4f5d303b1e1dd4f4fd17607"
    assert compute_external_rubric_sha256(rubric) == rubric["rubric_sha256"]
    assert tuple(rubric["dimensions"].keys()) == EXTERNAL_RUBRIC_DIMENSIONS


def test_pass_rule_and_critique_before_fail_enforced_fail_closed(tmp_path: Path) -> None:
    store = ExternalRubricHumanStore(
        store_path=tmp_path / "labels.json",
        rubric_path=REPO_ROOT / DEFAULT_EXTERNAL_RUBRIC_REL_PATH,
    )
    txt = "Candidate executive summary draft with verified Unify and Slalom metrics."
    sha = compute_payload_sha256(txt)

    # 1. Valid PASS with F=4 and all pillars >= 3
    rec = store.append_label(
        {
            "case_id": "CAL-RG-001",
            "judge_surface": "resume_executive_summary",
            "topic_family": "rg_exec_summary_01",
            "partition": "calibration",
            "artifact_sha256": sha,
            "external_rubric_id": "external_judge_rubric_v1",
            "external_rubric_sha256": store.rubric_sha256,
            "dimension_grades": {
                "factual_faithfulness": 4,
                "completeness_and_relevance": 5,
                "cold_reader_clarity": 4,
                "actionability_and_proportion": 4,
            },
            "atomic_checks": {
                "unsupported_claim_absent": True,
                "source_contradiction_absent": True,
            },
            "human_verdict": "PASS",
            "annotator_id": "amit.ayer",
            "graded_at_utc": "2026-11-23T05:00:00Z",
        },
        candidate_text=txt,
        require_fail_critique=True,
    )
    assert rec.human_verdict == "PASS"
    assert rec.normalized_human_score() > 0.75

    # 2. PASS blocked when F < 4
    with pytest.raises(ValueError, match="factual_faithfulness >= 4"):
        store.append_label(
            {
                "case_id": "CAL-RG-002",
                "judge_surface": "resume_executive_summary",
                "topic_family": "rg_exec_summary_02",
                "partition": "calibration",
                "artifact_sha256": compute_payload_sha256("other"),
                "external_rubric_id": "external_judge_rubric_v1",
                "external_rubric_sha256": store.rubric_sha256,
                "dimension_grades": {
                    "factual_faithfulness": 3,
                    "completeness_and_relevance": 5,
                    "cold_reader_clarity": 5,
                    "actionability_and_proportion": 5,
                },
                "human_verdict": "PASS",
                "annotator_id": "amit.ayer",
                "graded_at_utc": "2026-11-23T05:01:00Z",
            },
            require_fail_critique=True,
        )

    # 3. PASS blocked when critical atomic check is False
    with pytest.raises(ValueError, match="failed critical faithfulness atomic check"):
        store.append_label(
            {
                "case_id": "CAL-RG-003",
                "judge_surface": "resume_executive_summary",
                "topic_family": "rg_exec_summary_03",
                "partition": "calibration",
                "artifact_sha256": compute_payload_sha256("other3"),
                "external_rubric_id": "external_judge_rubric_v1",
                "external_rubric_sha256": store.rubric_sha256,
                "dimension_grades": {
                    "factual_faithfulness": 4,
                    "completeness_and_relevance": 4,
                    "cold_reader_clarity": 4,
                    "actionability_and_proportion": 4,
                },
                "atomic_checks": {"unsupported_claim_absent": False},
                "human_verdict": "PASS",
                "annotator_id": "amit.ayer",
                "graded_at_utc": "2026-11-23T05:02:00Z",
            },
            require_fail_critique=True,
        )

    # 4. FAIL blocked without failure tag or critique (>= 8 chars)
    with pytest.raises(ValueError, match="FAIL requires >= 1 structured failure_tags"):
        store.append_label(
            {
                "case_id": "CAL-RG-004",
                "judge_surface": "resume_executive_summary",
                "topic_family": "rg_exec_summary_04",
                "partition": "calibration",
                "artifact_sha256": compute_payload_sha256("other4"),
                "external_rubric_id": "external_judge_rubric_v1",
                "external_rubric_sha256": store.rubric_sha256,
                "dimension_grades": {
                    "factual_faithfulness": 2,
                    "completeness_and_relevance": 3,
                    "cold_reader_clarity": 4,
                    "actionability_and_proportion": 4,
                },
                "human_verdict": "FAIL",
                "annotator_id": "amit.ayer",
                "graded_at_utc": "2026-11-23T05:03:00Z",
            },
            require_fail_critique=True,
        )


def test_quarantine_partition_isolation_and_synthetic_annotator_block(tmp_path: Path) -> None:
    store = ExternalRubricHumanStore(
        store_path=tmp_path / "labels.json",
        rubric_path=REPO_ROOT / DEFAULT_EXTERNAL_RUBRIC_REL_PATH,
    )
    q = store.append_quarantine(
        {
            "case_id": "CAL-LIC-001",
            "judge_surface": "outreach_x1d_quorum",
            "topic_family": "lic_seq_01",
            "partition": "calibration",
            "artifact_sha256": compute_payload_sha256("quarantined sequence"),
            "reason": "ABSTAIN_INSUFFICIENT_EVIDENCE",
            "annotator_id": "amit.ayer",
            "recorded_at_utc": "2026-11-23T05:05:00Z",
            "notes": "Missing target context excerpt.",
        }
    )
    assert q.reason == "ABSTAIN_INSUFFICIENT_EVIDENCE"
    assert len(store.load_quarantined()) == 1
    assert len(store.load_records()) == 0

    with pytest.raises(ValueError, match="Synthetic or automated annotator"):
        store.append_quarantine(
            {
                "case_id": "CAL-LIC-002",
                "judge_surface": "outreach_x1d_quorum",
                "topic_family": "lic_seq_02",
                "partition": "calibration",
                "artifact_sha256": compute_payload_sha256("q2"),
                "reason": "DEFECTIVE_PROMPT",
                "annotator_id": "mock_argon_bot",
                "recorded_at_utc": "2026-11-23T05:06:00Z",
            }
        )
