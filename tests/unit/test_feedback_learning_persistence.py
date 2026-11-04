"""Unit and integration verification for closed-loop FeedbackController persistence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

import pytest

from agents.learning_cli import run_learning
from agents.orchestration import (
    ControllerAction,
    FailureKind,
    FeedbackController,
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
    RunPhase,
)
from agents.orchestration.learning_store import (
    DEFAULT_LEARNING_STORE_PATH,
    FeedbackLearningStore,
)
from tools.backfill_feedback_learning_lessons import DEFAULT_MANIFEST_PATH, backfill_lessons


def test_feedback_controller_auto_persists_failures_and_resolutions(tmp_path: Path) -> None:
    """Verify SCHEMA and DETERMINISTIC_QUALITY failures auto-persist and resolve on ACCEPT."""
    db_file = tmp_path / "isolated_learning.sqlite"
    store = FeedbackLearningStore(db_file)
    controller = FeedbackController(learning_store=store)

    state = ResumeRunState(
        run_id="run-auto-persist-01",
        workflow_id="wf-auto-01",
        phase=RunPhase.RUNNING,
        counters=RecoveryCounters(semantic_revisions=0),
        budget=RecoveryBudget(max_semantic_revisions=3),
    )

    schema_decision = controller.evaluate_result(
        validation_passed=False,
        errors=["Missing required summary_bullets array"],
        failure_kind=FailureKind.SCHEMA,
        state=state,
    )
    assert schema_decision.action == ControllerAction.DETERMINISTIC_NORMALIZE

    qual_decision = controller.evaluate_result(
        validation_passed=False,
        errors=["Summary exceeds concise word ceiling"],
        failure_kind=FailureKind.DETERMINISTIC_QUALITY,
        state=state,
    )
    assert qual_decision.action == ControllerAction.REQUEST_SEMANTIC_REVISION

    accept_decision = controller.evaluate_result(
        validation_passed=True,
        state=state,
        step_name="post_repair_validation",
        repair_hint="Coerce summary_bullets list and trim filler words",
    )
    assert accept_decision.action == ControllerAction.ACCEPT

    # Subsequent failure on the same constraint should surface the learned empirical hint
    repeat_decision = controller.evaluate_result(
        validation_passed=False,
        errors=["Summary exceeds concise word ceiling"],
        failure_kind=FailureKind.DETERMINISTIC_QUALITY,
        state=ResumeRunState(
            run_id="run-auto-persist-02",
            workflow_id="wf-auto-02",
            phase=RunPhase.RUNNING,
        ),
    )
    assert "Coerce summary_bullets list and trim filler words" in repeat_decision.repair_hint
    store.close()

    # Independent read-only SQLite check
    ro_uri = f"file:{db_file.as_posix()}?mode=ro"
    conn = sqlite3.connect(ro_uri, uri=True)
    try:
        sig_count = conn.execute("SELECT COUNT(*) FROM failure_signatures").fetchone()[0]
        res_count = conn.execute(
            "SELECT COUNT(*) FROM resolution_events WHERE outcome = 'SUCCESS'"
        ).fetchone()[0]
        assert sig_count == 2
        assert res_count == 2
    finally:
        conn.close()


def test_learning_cli_record_lesson_and_status_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify CLI record-lesson writes durably and status --json reads back accurately."""
    db_file = tmp_path / "cli_learning.sqlite"
    monkeypatch.setenv("AGENTS_LEARNING_STORE_PATH", str(db_file))

    rec_args = argparse.Namespace(
        learning_command="record-lesson",
        failure_kind="PLANNING",
        constraint="Dual-engine verification skipped outreach workflow",
        repair_hint="Run both Resume and Outreach engine verification suites",
        run_id="chat:test-roundtrip",
        action_taken="OPERATOR_FEEDBACK_RESOLUTION",
        json=True,
    )
    assert run_learning(rec_args) == 0
    rec_out = json.loads(capsys.readouterr().out)
    assert rec_out["status"] == "RECORDED"
    assert rec_out["total_failure_signatures"] == 1
    assert rec_out["total_resolutions_recorded"] == 1

    status_args = argparse.Namespace(learning_command="status", json=True)
    assert run_learning(status_args) == 0
    status_out = json.loads(capsys.readouterr().out)
    assert status_out["feedback_learning"]["total_failure_signatures"] == 1
    assert status_out["feedback_learning"]["overall_success_rate"] == 1.0


def test_backfill_manifest_populates_all_seven_11_03_2026_lessons(tmp_path: Path) -> None:
    """Verify all 7 operator feedback sessions from 11/03/2026 backfill cleanly and idempotently."""
    assert DEFAULT_LEARNING_STORE_PATH.name == "feedback_learning.sqlite"
    assert ".worktrees" not in DEFAULT_LEARNING_STORE_PATH.parts

    sandbox_db = tmp_path / "backfill_verify.sqlite"
    first_run = backfill_lessons(DEFAULT_MANIFEST_PATH, db_path=sandbox_db)
    second_run = backfill_lessons(DEFAULT_MANIFEST_PATH, db_path=sandbox_db)

    assert first_run["lessons_processed"] == 7
    assert second_run["lessons_processed"] == 7

    ro_uri = f"file:{sandbox_db.as_posix()}?mode=ro"
    conn = sqlite3.connect(ro_uri, uri=True)
    try:
        sig_count = conn.execute("SELECT COUNT(*) FROM failure_signatures").fetchone()[0]
        res_count = conn.execute("SELECT COUNT(*) FROM resolution_events").fetchone()[0]
        succ_count = conn.execute(
            "SELECT COUNT(*) FROM resolution_events WHERE outcome = 'SUCCESS'"
        ).fetchone()[0]
        assert sig_count == 7
        assert res_count == 7
        assert succ_count == 7
    finally:
        conn.close()
