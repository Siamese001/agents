"""Zero-API-cost deterministic post-runtime online run grader and chronological backfill ledger.

Strictly pure JSON/filesystem inside apps_eval/ (zero sqlite3 imports).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.contracts.digests import canonical_sha256, verify_canonical_digest
from apps_eval.contracts.schemas import RunTrace, utc_now_iso
from apps_eval.graders.trajectory import (
    TrajectoryEvaluator,
    TrajectoryTrace,
    steps_from_trace_dicts,
)

ONLINE_EVAL_CONTRACT_ID = "urn:agents:eval:online-eval-record:1.0.0"

DEFAULT_LATENCY_SLA_MS: dict[str, float] = {
    "apps_rg": 60000.0,
    "apps_lic": 45000.0,
    "apps_research": 30000.0,
    "agents_core": 30000.0,
    "agents_cli": 90000.0,
    "antigravity_turn": 20000.0,
}


@dataclass(frozen=True)
class OnlineEvalRecord:
    """Canonical deterministic post-runtime grade emitted at $0.00 marginal API cost."""

    trace_id: str
    app_id: str
    run_id: str
    session_id: str
    git_sha: str
    evaluated_at_utc: str
    trace_finished_at_utc: str
    metrics: dict[str, float]
    gates: dict[str, bool]
    failed_gates: list[str]
    composite_score: float
    passed: bool
    marginal_api_cost_usd: float = 0.0
    external_http_allowed: bool = False
    model_id: str = "local-deterministic"
    deterministic_passed: bool | None = None
    judge_passed: bool | None = None
    groundedness: float | None = None
    prompt_text: str = ""
    output_text: str = ""
    topic_family: str = ""
    contract_id: str = ONLINE_EVAL_CONTRACT_ID
    schema_version: str = "1.0.0"
    record_digest: str = ""

    def __post_init__(self) -> None:
        if not self.record_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("record_digest",))
            object.__setattr__(self, "record_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def verify_digest(self) -> bool:
        return verify_canonical_digest(self.to_dict(), digest_field="record_digest")


def grade_run_trace(
    trace: RunTrace,
    *,
    latency_sla_ms_by_app: Mapping[str, float] | None = None,
) -> OnlineEvalRecord:
    """Grade a RunTrace deterministically with zero external LLM calls."""
    sla_map = dict(DEFAULT_LATENCY_SLA_MS)
    if latency_sla_ms_by_app:
        sla_map.update(latency_sla_ms_by_app)
    sla_ms = float(sla_map.get(trace.app_id, 30000.0))

    terminal_ok = trace.terminal_status == "PASS"
    latency_ms = float(trace.telemetry.get("latency_ms", 0.0))
    cost_usd = float(trace.telemetry.get("cost_usd", 0.0))
    retry_count = int(trace.telemetry.get("retry_count", 0))

    # Gate outcomes from domain pipelines (X2, X1D, X3).
    x2_gates = trace.gate_outcomes.get("x2_gates") or {}
    if isinstance(x2_gates, Mapping) and x2_gates:
        x2_passed_count = sum(1 for v in x2_gates.values() if bool(v))
        x2_pass_rate = x2_passed_count / float(len(x2_gates))
        x2_ok = x2_passed_count == len(x2_gates)
    else:
        x2_pass_rate = 1.0 if terminal_ok else 0.0
        x2_ok = terminal_ok

    # Trajectory evaluation when steps are present.
    traj_score = 100.0 if terminal_ok else 0.0
    traj_ok = terminal_ok
    unresolved_errors = 0 if terminal_ok else 1
    if trace.trajectory_steps:
        steps = steps_from_trace_dicts(trace.trajectory_steps)
        t_trace = TrajectoryTrace(
            trace_id=trace.trace_id,
            steps=steps,
            optimal_step_count=max(1, len(steps)),
            terminal_task_success=terminal_ok,
        )
        t_card = TrajectoryEvaluator().evaluate(t_trace)
        traj_score = t_card.composite_score
        traj_ok = t_card.hard_gates.get("loop_count_zero", False) and t_card.hard_gates.get(
            "zero_unresolved_errors", False
        )
        unresolved_errors = t_card.unresolved_error_count

    hitl_override = bool(trace.user_feedback.get("hitl_override", False))
    latency_ok = latency_ms <= sla_ms
    no_override_ok = not hitl_override

    gates = {
        "terminal_success": terminal_ok,
        "x2_gates_passed": x2_ok,
        "trajectory_healthy": traj_ok,
        "latency_sla": latency_ok,
        "no_hitl_override": no_override_ok,
    }
    failed_gates = sorted(k for k, v in gates.items() if not v)

    composite = round(
        (
            0.35 * (1.0 if terminal_ok else 0.0)
            + 0.30 * x2_pass_rate
            + 0.20 * (traj_score / 100.0)
            + 0.10 * (1.0 if latency_ok else 0.0)
            + 0.05 * (1.0 if no_override_ok else 0.0)
        )
        * 100.0,
        2,
    )

    raw_judge = trace.gate_outcomes.get("judge_passed")
    if raw_judge is None and isinstance(trace.gate_outcomes.get("x1d_judge"), Mapping):
        raw_judge = trace.gate_outcomes["x1d_judge"].get("passed")
    judge_passed = bool(raw_judge) if raw_judge is not None else None

    raw_grnd = trace.telemetry.get("groundedness", trace.gate_outcomes.get("groundedness"))
    groundedness = round(float(raw_grnd), 4) if raw_grnd is not None and not isinstance(raw_grnd, bool) else None

    prompt_text = str(
        trace.input_redacted.get("prompt_text")
        or trace.input_redacted.get("target_context")
        or trace.input_redacted.get("query")
        or ""
    )
    output_text = str(
        trace.output_summary.get("output_text")
        or trace.output_summary.get("candidate_text")
        or trace.output_summary.get("summary")
        or ""
    )
    topic_family = str(
        trace.input_redacted.get("topic_family")
        or trace.telemetry.get("topic_family")
        or f"{trace.app_id}_{trace.run_id}"
    )

    metrics_dict: dict[str, float] = {
        "x2_pass_rate": round(x2_pass_rate, 4),
        "trajectory_score": round(traj_score, 2),
        "latency_ms": round(latency_ms, 2),
        "cost_usd": round(cost_usd, 6),
        "retry_count": float(retry_count),
        "unresolved_errors": float(unresolved_errors),
    }
    if groundedness is not None:
        metrics_dict["groundedness"] = groundedness

    return OnlineEvalRecord(
        trace_id=trace.trace_id,
        app_id=trace.app_id,
        run_id=trace.run_id,
        session_id=trace.session_id,
        git_sha=trace.git_sha,
        evaluated_at_utc=utc_now_iso(),
        trace_finished_at_utc=trace.finished_at_utc,
        metrics=metrics_dict,
        gates=gates,
        failed_gates=failed_gates,
        composite_score=composite,
        passed=all(gates.values()),
        deterministic_passed=x2_ok and traj_ok,
        judge_passed=judge_passed,
        groundedness=groundedness,
        prompt_text=prompt_text,
        output_text=output_text,
        topic_family=topic_family,
    )


def append_online_eval_record(record: OnlineEvalRecord, ledger_path: Path) -> Path:
    """Append an OnlineEvalRecord to an append-only JSONL ledger."""
    target = Path(ledger_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")
    return target


def load_online_eval_records(ledger_path: Path) -> list[dict[str, Any]]:
    """Load online eval records from JSONL, deduplicating by latest record per trace_id."""
    target = Path(ledger_path).resolve()
    if not target.is_file():
        return []
    by_trace: dict[str, dict[str, Any]] = {}
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            s = line.strip()
            if not s:
                continue
            try:
                row = json.loads(s)
            except json.JSONDecodeError:
                continue
            tid = str(row.get("trace_id") or "")
            if tid:
                by_trace[tid] = row
    return list(by_trace.values())


def backfill_online_grades(
    traces: Sequence[RunTrace],
    ledger_path: Path,
    *,
    latency_sla_ms_by_app: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Chronologically backfill grades for any RunTrace not yet recorded in ledger_path."""
    existing = {str(r.get("trace_id") or "") for r in load_online_eval_records(ledger_path)}
    ordered = sorted(traces, key=lambda t: (t.finished_at_utc, t.trace_id))
    graded = 0
    skipped = 0
    failed = 0
    for trace in ordered:
        if trace.trace_id in existing:
            skipped += 1
            continue
        rec = grade_run_trace(trace, latency_sla_ms_by_app=latency_sla_ms_by_app)
        append_online_eval_record(rec, ledger_path)
        existing.add(trace.trace_id)
        graded += 1
        if not rec.passed:
            failed += 1
    return {
        "graded_count": graded,
        "skipped_existing": skipped,
        "failed_count": failed,
        "marginal_api_cost_usd": 0.0,
        "ledger_path": str(Path(ledger_path).resolve()),
    }
