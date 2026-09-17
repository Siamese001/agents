"""Comprehensive unit and integration test suite for System Learning Rigor.

Validates Waves 1 through 5:
1. FeedbackLearningStore: Failure signature hashing, recurrence tracking, and repair hint retrieval.
2. FeedbackController Learning Integration: Closed-loop hint enrichment and resolution recording.
3. StatisticalDriftDetector & Inter-Rater Concordance: EWMA, z-scores, Cohen's Kappa.
4. TrajectoryLearningEngine: Event-sourced efficiency scoring and golden exemplar extraction.
5. TrajectoryExemplarIndex & TokenBudget: Integration of mined exemplars into prompt budgeting.
6. RuntimePrecedentBridge: Bayesian learning factor querying and ambiguity margin gating.
7. Unified CLI (python -m agents learning): Status, drift, trajectories, and JSON serialization.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import pytest

from agents.cli import run_learning
from agents.context.budgeting import TokenBudget, TrajectoryExemplarIndex
from agents.context.precedent_bridge import RuntimePrecedentBridge
from agents.context.provenance import ContextSourceType
from agents.observability.events import (
    AgentEventEnvelope,
    AgentEventType,
    create_event_envelope,
)
from agents.observability.trajectory_learning import (
    TrajectoryExemplar,
    TrajectoryLearningEngine,
)
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
    FeedbackLearningStore,
    compute_failure_signature,
    normalize_constraint_key,
)
from agents.persistence.sqlite.event_store import SqliteEventStore
from agents.telemetry.calibration import (
    EvaluationTelemetry,
    EvaluationVerdict,
    JudgeCalibrator,
    StatisticalDriftDetector,
    calculate_inter_rater_concordance,
)


# ===========================================================================
# 1. FeedbackLearningStore Tests (Wave 1)
# ===========================================================================

def test_feedback_learning_store_lifecycle() -> None:
    """Wave 1: Test failure recording, recurrence increments, and hint retrieval."""
    store = FeedbackLearningStore(":memory:")

    sig1 = store.record_failure(FailureKind.DETERMINISTIC_QUALITY, "Bullet point exceeds 24 words")
    sig2 = store.record_failure(FailureKind.DETERMINISTIC_QUALITY, "Bullet point exceeds 24 words")
    assert sig1 == sig2

    stats = store.get_failure_statistics(sig1)
    assert len(stats) == 1
    assert stats[0]["occurrence_count"] == 2
    assert stats[0]["resolution_count"] == 0

    # Record resolution with repair hint
    store.record_resolution(
        sig1,
        run_id="run-001",
        action_taken="SEMANTIC_REVISION",
        repair_hint="Shorten bullet by removing adjectives",
        outcome="SUCCESS",
    )

    hints = store.get_repair_hints(FailureKind.DETERMINISTIC_QUALITY, "Bullet point exceeds 24 words")
    assert len(hints) == 1
    assert "Shorten bullet" in hints[0]

    summary = store.get_summary()
    assert summary["total_failure_signatures"] == 1
    assert summary["total_resolutions_recorded"] == 1
    assert summary["successful_resolutions"] == 1
    assert summary["overall_success_rate"] == 1.0
    store.close()


def test_feedback_controller_learning_integration() -> None:
    """Wave 1: Test FeedbackController auto-enriches repair hints from learning store."""
    store = FeedbackLearningStore(":memory:")
    sig = store.record_failure(FailureKind.DETERMINISTIC_QUALITY, "Missing metric number")
    store.record_resolution(
        sig,
        run_id="run-prior",
        repair_hint="Add quantified percentage or dollar metric",
        outcome="SUCCESS",
    )

    controller = FeedbackController(learning_store=store)
    state = ResumeRunState(
        run_id="run-current",
        workflow_id="wf-001",
        phase=RunPhase.RUNNING,
        counters=RecoveryCounters(semantic_revisions=0),
        budget=RecoveryBudget(max_semantic_revisions=2),
    )

    decision = controller.evaluate_result(
        validation_passed=False,
        errors=["Missing metric number"],
        failure_kind=FailureKind.DETERMINISTIC_QUALITY,
        state=state,
    )

    assert decision.action == ControllerAction.REQUEST_SEMANTIC_REVISION
    assert "Add quantified percentage" in decision.repair_hint

    # Record successful resolution
    controller.record_resolution_outcome(
        FailureKind.DETERMINISTIC_QUALITY,
        "Missing metric number",
        run_id="run-current",
        repair_hint="Add quantified percentage or dollar metric",
        outcome="SUCCESS",
    )

    summary = store.get_summary()
    assert summary["successful_resolutions"] == 2
    store.close()


# ===========================================================================
# 2. Statistical Calibration & Concordance Tests (Wave 2)
# ===========================================================================

def test_statistical_drift_detector_ewma_and_z_score() -> None:
    """Wave 2: Test EWMA calculation, rolling stats, and z-score anomaly detection."""
    detector = StatisticalDriftDetector(window_size=20, alpha=0.30)

    # Feed steady high scores
    for _ in range(10):
        detector.record("groundedness", 0.90)

    stats = detector.get_stats("groundedness")
    assert stats["count"] == 10
    assert stats["mean"] == 0.90
    assert stats["ewma"] == 0.90

    # Introduce sudden degradation
    for _ in range(5):
        detector.record("groundedness", 0.50)

    stats_drifted = detector.get_stats("groundedness")
    assert stats_drifted["ewma"] < 0.80

    # Check drift detection against baseline 0.80
    drift_res = detector.detect_drift("groundedness", baseline_threshold=0.80, z_threshold=1.5)
    assert drift_res["drift_detected"] is True
    assert "score deflation detected" in drift_res["reason"].lower() or drift_res["z_score"] < 0


def test_inter_rater_concordance_cohens_kappa() -> None:
    """Wave 2: Test Cohen's Kappa agreement calculation across dual evaluators."""
    calibrator = JudgeCalibrator()

    # Evaluator A: Consistent passes
    eval_a = [
        EvaluationTelemetry("judge_a", "groundedness", 0.95, 0.80, EvaluationVerdict.PASS),
        EvaluationTelemetry("judge_a", "brevity", 0.85, 0.70, EvaluationVerdict.PASS),
        EvaluationTelemetry("judge_a", "relevance", 0.50, 0.75, EvaluationVerdict.FAIL),
    ]

    # Evaluator B: Identical verdicts
    eval_b = [
        EvaluationTelemetry("judge_b", "groundedness", 0.90, 0.80, EvaluationVerdict.PASS),
        EvaluationTelemetry("judge_b", "brevity", 0.75, 0.70, EvaluationVerdict.PASS),
        EvaluationTelemetry("judge_b", "relevance", 0.40, 0.75, EvaluationVerdict.FAIL),
    ]

    concordance = calculate_inter_rater_concordance(eval_a, eval_b)
    assert concordance["paired_count"] == 3
    assert concordance["observed_agreement"] == 1.0
    assert concordance["cohens_kappa"] == 1.0
    assert concordance["agreement_strength"] == "ALMOST_PERFECT"


# ===========================================================================
# 3. Trajectory Learning & Golden Trace Mining Tests (Wave 3)
# ===========================================================================

def test_trajectory_learning_golden_exemplar_extraction() -> None:
    """Wave 3: Test event-sourced trajectory scoring and golden exemplar extraction."""
    engine = TrajectoryLearningEngine(min_efficiency=0.75)

    # Construct synthetic clean passing run
    events: list[AgentEventEnvelope] = [
        create_event_envelope(
            run_id="run_clean_101",
            correlation_id="corr_101",
            sequence=1,
            event_type=AgentEventType.PHASE_TRANSITION,
            producer="test_runner",
            payload={"step_name": "resume_tailoring", "task_type": "tailoring"},
        ),
        create_event_envelope(
            run_id="run_clean_101",
            correlation_id="corr_101",
            sequence=2,
            event_type=AgentEventType.FEEDBACK_DECISION,
            producer="test_runner",
            payload={"action": "ACCEPT", "score": 0.95},
        ),
    ]

    metrics = engine.score_run_events(events)
    assert metrics["is_golden"] is True
    assert metrics["efficiency_score"] >= 0.80

    exemplar = engine.mine_from_events(events)
    assert exemplar is not None
    assert exemplar.run_id == "run_clean_101"
    assert exemplar.task_type == "tailoring"

    # Verify query
    retrieved = engine.get_exemplars_for_task("tailoring")
    assert len(retrieved) == 1
    assert retrieved[0].exemplar_id == exemplar.exemplar_id


def test_trajectory_exemplar_index_budgeting_integration() -> None:
    """Wave 3: Test TrajectoryExemplarIndex integration with TokenBudget."""
    index = TrajectoryExemplarIndex()
    ex = TrajectoryExemplar(
        exemplar_id="ex_001",
        run_id="run_001",
        task_type="outreach",
        efficiency_score=0.92,
        step_sequence=("research", "outreach_planner", "eval"),
        key_decisions=("ACCEPT",),
        summary_text="Flawless executive email generation with 0 retries.",
    )
    index.add_exemplar(ex)

    context_items = index.to_context_items("outreach")
    assert len(context_items) == 1
    assert context_items[0].source_type == ContextSourceType.RETRIEVED_EVIDENCE
    assert "Golden Trajectory Exemplar" in context_items[0].content

    # Fit into token budget
    budget = TokenBudget(max_total_tokens=4000, reserved_output_tokens=1000)
    snapshot = budget.fit_items_to_budget(context_items)
    assert len(snapshot.items) == 1
    assert snapshot.items[0].source_id == "trajectory_exemplar_ex_001"


# ===========================================================================
# 4. Runtime Precedent Bridge Tests (Wave 4)
# ===========================================================================

def test_runtime_precedent_bridge_ambiguity_gating() -> None:
    """Wave 4: Test in-process ambiguity margin evaluation and decision recording."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_prec.sqlite"
        bridge = RuntimePrecedentBridge(db_path=db_path)
        assert bridge.is_healthy() is True

        # Test decisive option (margin > 20% -> proceed autonomously)
        decisive_opts = [
            {"label": "Standard Pipeline", "confidence_score": 0.90},
            {"label": "Experimental Strategy", "confidence_score": 0.50},
        ]
        gate_decisive = bridge.evaluate_runtime_ambiguity(decisive_opts)
        assert gate_decisive["should_surface"] is False
        assert gate_decisive["action"] == "PROCEED_AUTONOMOUSLY"

        # Test ambiguous option (margin <= 20% -> surface atomic HITL)
        ambiguous_opts = [
            {"label": "Strategy A", "confidence_score": 0.65},
            {"label": "Strategy B", "confidence_score": 0.55},
        ]
        gate_ambiguous = bridge.evaluate_runtime_ambiguity(ambiguous_opts)
        assert gate_ambiguous["should_surface"] is True
        assert gate_ambiguous["action"] == "SURFACE_HITL_ATOMIC"

        # Record runtime decision
        rec = bridge.record_runtime_decision(
            decision_id="dec_run_01",
            category="pipeline_routing",
            options=decisive_opts,
            selected_option="Standard Pipeline",
            outcome="SUCCESS",
        )
        assert rec["status"] == "STORED"
        bridge.close()


# ===========================================================================
# 5. CLI Inspection Tests (Wave 5)
# ===========================================================================

def test_cli_learning_commands(capsys: pytest.CaptureFixture[str]) -> None:
    """Wave 5: Test python -m agents learning status, drift, trajectories."""
    # Test status
    args_status = argparse.Namespace(learning_command="status", json=False)
    assert run_learning(args_status) == 0
    captured = capsys.readouterr()
    assert "Sovereign Agentic Platform: System Learning Status" in captured.out

    # Test status --json
    args_status_json = argparse.Namespace(learning_command="status", json=True)
    assert run_learning(args_status_json) == 0
    captured_json = capsys.readouterr()
    parsed = json.loads(captured_json.out)
    assert parsed["status"] == "HEALTHY"
    assert "feedback_learning" in parsed

    # Test drift
    args_drift = argparse.Namespace(learning_command="drift", criterion="groundedness", json=False)
    assert run_learning(args_drift) == 0
    captured_drift = capsys.readouterr()
    assert "Judge Calibration & Statistical Drift Audit" in captured_drift.out

    # Test trajectories
    args_traj = argparse.Namespace(learning_command="trajectories", task_type="general", json=False)
    assert run_learning(args_traj) == 0
    captured_traj = capsys.readouterr()
    assert "Mined Golden Trajectories" in captured_traj.out
