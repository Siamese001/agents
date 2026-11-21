"""Wave 2 unit tests for SQLite FindingsQueueStore, multi-surface consolidator, golden promoter, and holdout isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.observability.eval_flywheel import EvalFlywheelEngine
from agents.observability.findings_consolidator import (
    build_failure_clusters,
    consolidate_all_findings,
)
from agents.observability.trace_collector import build_run_trace
from agents.orchestration.learning_store import FeedbackLearningStore
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from apps_eval.online_grader import backfill_online_grades
from apps_eval.triage_promoter import load_holdout_cases, promote_golden_cases


def test_findings_queue_deduplicates_preserves_human_status_and_archives_pre_cutoff(tmp_path: Path) -> None:
    db = tmp_path / "remediation_queue.sqlite"
    store = SqliteFindingsQueueStore(db)
    try:
        f1 = store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_rg",
            failed_gate_signature="x2_gates_passed",
            root_cause_bucket="apps_rg_x2_defect",
            owner_subsystem="resume_graph_engine",
            track="TRACK_2_CODE_FIX",
            priority="P1",
            title="X2 defect",
            summary="First occurrence",
            recommended_action="Fix validator",
            occurrence_count=1,
            sample_trace_ids=["trace-1"],
            seen_at_utc="2026-11-21T05:00:00Z",
            cutoff_utc="2026-11-20T00:00:00Z",
        )
        assert f1.status == "OPEN"
        store.transition_status(f1.finding_id, "APPROVED", actor="operator", rationale="Approved for wave")

        # Re-ingesting same fingerprint merges samples and preserves APPROVED status.
        f2 = store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_rg",
            failed_gate_signature="x2_gates_passed",
            root_cause_bucket="apps_rg_x2_defect",
            owner_subsystem="resume_graph_engine",
            track="TRACK_2_CODE_FIX",
            priority="P0",
            title="X2 defect",
            summary="Second occurrence",
            recommended_action="Fix validator",
            occurrence_count=3,
            sample_trace_ids=["trace-2", "trace-3"],
            seen_at_utc="2026-11-21T06:00:00Z",
            cutoff_utc="2026-11-20T00:00:00Z",
        )
        assert f2.finding_id == f1.finding_id
        assert f2.status == "APPROVED"
        assert f2.priority == "P0"
        assert f2.occurrence_count == 3
        assert set(f2.sample_trace_ids) == {"trace-1", "trace-2", "trace-3"}

        # Pre-cutoff legacy failure enters ARCHIVED directly.
        legacy = store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_lic",
            failed_gate_signature="legacy_gate",
            root_cause_bucket="legacy_bucket",
            owner_subsystem="outreach_engine",
            track="TRACK_2_CODE_FIX",
            priority="P2",
            title="Legacy",
            summary="Old",
            recommended_action="Ignore",
            seen_at_utc="2026-10-01T00:00:00Z",
            cutoff_utc="2026-11-20T00:00:00Z",
        )
        assert legacy.status == "ARCHIVED"
        assert len(store.list_events(f1.finding_id)) >= 2
    finally:
        store.close()


def test_consolidator_distinct_sandbox_roots_idempotency_and_correction_key(tmp_path: Path) -> None:
    source_root = tmp_path / "source_learning"
    output_root = tmp_path / "sandbox_output"
    source_root.mkdir()

    traces = [
        build_run_trace(
            app_id="apps_rg",
            run_id=f"run-{i}",
            session_id=f"sess-{i}",
            terminal_status="FAIL",
            raw_input={"jd_snippet": f"Principal AI Architect {i}", "contact": f"user{i}@secret.com"},
            gate_outcomes={"x2_gates": {"grounding": False}},
            finished_at_utc=f"2026-11-21T0{i}:00:00Z",
        )
        for i in range(1, 4)
    ]
    backfill_online_grades(traces, source_root / "online_eval_ledger.jsonl")

    # Write recurring operator corrections using canonical source_identifier key (DIE bug fix).
    corr_lines = [
        json.dumps(
            {
                "correction_id": f"corr-{i}",
                "category": "routing",
                "app_id": "apps_research",
                "source_identifier": "legacy_route",
                "corrected_identifier": "hybrid_route_v2",
                "operator_id": "amit",
                "session_id": f"sess-{i}",
                "recorded_at": "2026-11-21T05:00:00Z",
            }
        )
        for i in range(1, 4)
    ]
    (source_root / "operator_corrections.jsonl").write_text("\n".join(corr_lines) + "\n", encoding="utf-8")

    # Separate source_root and output_root must read source_root and write only to output_root.
    res1 = consolidate_all_findings(source_root, output_root, cutoff_utc="2026-11-20T00:00:00Z")
    assert res1["total_findings"] == 2
    assert res1["ingested_by_surface"]["online_eval"] == 1
    assert res1["ingested_by_surface"]["operator_correction"] == 1
    assert not (source_root / "remediation_queue.sqlite").exists()
    assert (output_root / "remediation_queue.sqlite").is_file()
    assert (output_root / "remediation_queue_snapshot.json").is_file()

    # Repeat consolidation is 100% idempotent.
    res2 = consolidate_all_findings(source_root, output_root, cutoff_utc="2026-11-20T00:00:00Z")
    assert res2["total_findings"] == res1["total_findings"]
    assert res2["cluster_count"] == 2


def test_golden_promoter_80_20_stratification_real_payloads_and_output_guard(tmp_path: Path) -> None:
    traces = [
        build_run_trace(
            app_id="apps_rg",
            run_id=f"run-{i}",
            session_id=f"sess-{i}",
            terminal_status="FAIL",
            raw_input={"jd_text": f"Lead ML Platform Engineer role #{i}", "email": f"person{i}@acme.org"},
            gate_outcomes={"x2_gates": {"grounding": False}},
        )
        for i in range(1, 6)
    ]
    # Build clusters that qualify all 5 traces.
    store = SqliteFindingsQueueStore(tmp_path / "q.sqlite")
    try:
        store.upsert_finding(
            source_surface="online_eval",
            app_id="apps_rg",
            failed_gate_signature="x2_gates_passed",
            root_cause_bucket="apps_rg_grounding",
            owner_subsystem="resume_graph_engine",
            track="TRACK_2_CODE_FIX",
            priority="P0",
            title="Grounding fail",
            summary="5 traces",
            recommended_action="Fix",
            occurrence_count=5,
            sample_trace_ids=[t.trace_id for t in traces],
            metadata={"run_ids": [t.run_id for t in traces], "session_ids": [t.session_id for t in traces]},
        )
        clusters = build_failure_clusters(store.list_findings())
    finally:
        store.close()

    dataset_path = tmp_path / "golden_eval_cases.json"
    dataset = promote_golden_cases(
        output_dataset_path=dataset_path,
        traces=traces,
        eligible_clusters=clusters,
        curated_holdout_seeds=[
            {
                "case_id": "locked-seed-1",
                "app_id": "apps_rg",
                "split": "holdout",
                "unlabeled_input": {"jd_text": "Locked anchor JD"},
                "expected_contract": {"reference_label": "PASS"},
            }
        ],
    )
    assert dataset["total_cases"] == 6
    assert dataset["counts_by_split"]["development"] >= 1
    assert dataset["counts_by_split"]["holdout"] >= 2
    raw_text = dataset_path.read_text(encoding="utf-8")
    assert "acme.org" not in raw_text
    assert "Lead ML Platform Engineer role #1" in raw_text
    assert "Promoted resume governance regression case." not in raw_text

    # load_holdout_cases returns strictly holdout split and exposes unlabeled_view without ground truth.
    digest, holdouts = load_holdout_cases(dataset_path, app_id="apps_rg")
    assert digest == dataset["dataset_digest"]
    assert all(h.split == "holdout" for h in holdouts)
    assert any(h.case_id == "locked-seed-1" for h in holdouts)

    # Production output/ path is strictly blocked.
    with pytest.raises(ValueError, match="Refusing"):
        promote_golden_cases(output_dataset_path=tmp_path / "output" / "golden.json", traces=traces)


def test_eval_flywheel_does_not_inflate_success_rate_with_unverified_canned_hints(tmp_path: Path) -> None:
    db_path = tmp_path / "fb.sqlite"
    engine = EvalFlywheelEngine(
        learning_db_path=db_path,
        trajectory_store_path=tmp_path / "traj.json",
        calibration_history_path=tmp_path / "cal.json",
        graduation_state_path=tmp_path / "grad.json",
        triage_root=tmp_path / "triage",
    )
    manifest = {
        "generated_at": "2026-11-21T05:00:00Z",
        "suite_receipts": {
            "apps_rg.dev.resume_generation": {
                "app_id": "apps_rg",
                "record_id": "rec-fail-1",
                "finding_count": 10,
                "passed_findings": 8,
                "score": 0.80,
                "suite_passed": False,
                "regression_flywheel": {"failure_mode_counts": {"grounding.ungrounded_claim": 2}},
            }
        },
    }
    engine.ingest_manifest(manifest)
    fb = FeedbackLearningStore(db_path)
    try:
        stats = fb.get_failure_statistics()
        assert len(stats) == 1
        assert stats[0]["success_rate"] == 0.0
        assert stats[0]["resolution_count"] == 0
        # Diagnostic hint is still retrievable as fallback without lying about success_rate.
        hints = fb.get_repair_hints("FACTUAL_CONFLICT", "apps_rg.dev.resume_generation:grounding.ungrounded_claim")
        assert len(hints) >= 1
    finally:
        fb.close()
