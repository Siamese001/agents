"""Managed wave-based Phase-1 lane dispatcher (external model-safe parallelism)."""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, wait
from pathlib import Path
from typing import Any, Callable

from tqdm import tqdm

from apps_rg.config.runtime_env import get_runtime_env_str
from apps_rg.runtime.orchestration.section_lane_concurrency import LaneWave, section_dag_dependencies
from apps_rg.runtime.orchestration.section_lane_executor import (
    LaneDispatchOutcome,
    LaneExecutionContext,
    ensure_sections_root_manifest,
    run_lane_in_context,
)
from apps_rg.runtime.product_output_policy import PHASE1_PRIOR_LANE_FAILED_BLOCKER
from apps_rg.runtime.providers.wallclock_http_guard import (
    DaemonWorkerPool,
    mark_artifact_dir_cancelled,
    resolve_section_lane_timeout_s,
    resolve_section_run_timeout_s,
)


class ProgressReporter:  # pragma: no cover - exercised via the public dispatcher
    """App-owned progress reporter rendering a live tqdm progress bar on stderr with logger fallback."""

    def __init__(self, total: int, label: str = "apps_rg section lanes", unit: str = "lane") -> None:
        self.total = max(int(total or 1), 1)
        self.label = label or "apps_rg section lanes"
        self.unit = unit or "lane"
        self.completed = 0
        self._disabled = str(get_runtime_env_str("APPS_RG_DISABLE_PROGRESS", "") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self._pbar: Any | None = None
        if not self._disabled:
            try:
                self._pbar = tqdm(
                    total=self.total,
                    desc=self.label,
                    unit=self.unit,
                    file=sys.stderr,
                    dynamic_ncols=True,
                    leave=True,
                    mininterval=0.1,
                )
            except Exception:
                self._pbar = None

    def set_status(self, text: str) -> None:
        """Update the active in-progress status string without incrementing count."""
        clean = str(text or "").strip()
        if self._pbar is not None and clean:
            try:
                self._pbar.set_postfix_str(clean)
                sys.stderr.flush()
            except (OSError, ValueError, RuntimeError, AttributeError):
                pass

    def update(self, label: str = "") -> None:
        """Advance progress by one completed unit with an optional status label."""
        self.completed += 1
        clean = str(label or "").strip()
        if self._pbar is not None:
            try:
                if clean:
                    self._pbar.set_postfix_str(clean)
                self._pbar.update(1)
                sys.stderr.flush()
            except (OSError, ValueError, RuntimeError, AttributeError):
                pass
        logging.getLogger(__name__).info(
            "%s: %s/%s %s %s",
            self.label,
            self.completed,
            self.total,
            self.unit,
            clean,
        )

    def done(self) -> None:
        """Finalize and close the progress bar."""
        if self._pbar is not None:
            try:
                self._pbar.close()
                sys.stderr.flush()
            except (OSError, ValueError, RuntimeError, AttributeError):
                pass
            self._pbar = None
        logging.getLogger(__name__).info(
            "%s: complete (%s/%s %s)",
            self.label,
            self.completed,
            self.total,
            self.unit,
        )

_WAVE_ABORT_EXEC_STATUS = f"pre_run_blocked:{PHASE1_PRIOR_LANE_FAILED_BLOCKER}"
_DEPENDENCY_FAILED_BLOCKER = "UPSTREAM_DEPENDENCY_FAILED"


def _skipped_prior_lane_abort(lane: str) -> LaneDispatchOutcome:
    # Skipped wave after a prior-lane fail-closed abort. The lane never ran, so it
    # carries no real dispatch exit_status -- the blocker lives in exec_status
    # (pre_run_blocked:...) and dispatch_result["prior_abort"]. Emitting a generic
    # exit_status="error" here would let downstream status recompute mislabel the
    # skip as LANE_DISPATCH_EXIT_ERROR instead of PHASE1_PRIOR_LANE_FAILED.
    return LaneDispatchOutcome(
        lane=lane,
        dispatch_result={"prior_abort": PHASE1_PRIOR_LANE_FAILED_BLOCKER},
        exec_status=_WAVE_ABORT_EXEC_STATUS,
    )


def _skipped_dependency(lane: str, dependencies: tuple[str, ...], reason: str) -> LaneDispatchOutcome:
    """Return a truthful, non-dispatch outcome for a lane with failed prerequisites."""
    return LaneDispatchOutcome(
        lane=lane,
        dispatch_result={
            "blocked_by": list(dependencies),
            "dependency_reason": reason,
        },
        exec_status=f"pre_run_blocked:{_DEPENDENCY_FAILED_BLOCKER}",
    )


def _outcome_succeeded(outcome: LaneDispatchOutcome | None) -> bool:
    """Whether a completed lane is eligible to unlock direct dependents.

    This intentionally accepts the legacy empty exit status produced by some
    thin test/adapter call sites, but rejects all explicit dispatch faults,
    error exits, and pre-run blocks.  Product-level acceptance remains checked
    by ``dependency_ready_fn`` before a dependent is submitted.
    """
    if outcome is None or str(outcome.exec_status).startswith(("error:", "pre_run_blocked:")):
        return False
    result = outcome.dispatch_result if isinstance(outcome.dispatch_result, dict) else {}
    if str(result.get("fault") or "").strip():
        return False
    return str(result.get("exit_status") or "").strip().lower() not in {
        "error",
        "failed",
        "failure",
    }


def _readiness_result(
    dependency_ready_fn: Callable[[str], bool | tuple[bool, str]] | None,
    lane: str,
) -> tuple[bool, str]:
    """Evaluate an app-owned acceptance predicate without exposing scheduler internals."""
    if dependency_ready_fn is None:
        return True, ""
    try:
        value = dependency_ready_fn(lane)
    except Exception as exc:  # guardian: readiness is a fail-closed app boundary
        return False, f"readiness_exception:{exc!s}"
    if isinstance(value, tuple):
        ready, reason = value
        return bool(ready), str(reason or "dependency_not_certified")
    return bool(value), "" if value else "dependency_not_certified"


def _quarantine_timed_out_lane(ctx: LaneExecutionContext, lane: str) -> None:
    root_text = str(ctx.sections_root or "").strip()
    if root_text:
        mark_artifact_dir_cancelled(Path(root_text) / lane)


def _prewarm_parallel_graph_sqlite() -> None:
    """Materialize C0.3 graph SQLite once before spawning parallel Phase-1 worker threads."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from apps_rg.repository_layout import repository_root
        from apps_rg.runtime.c03_graph_sqlite_context import ensure_c03_graph_sqlite

        ensure_c03_graph_sqlite(repository_root(Path(__file__)))
    except Exception:  # guardian: prewarm is advisory; lane-level C0 enforces fail-closed contracts
        pass


def _lane_timeout_outcome(lane: str, budget_s: float, *, kind: str = "LANE_TIMEOUT") -> LaneDispatchOutcome:
    msg = f"Lane '{lane}' exceeded wall-clock deadline ({budget_s:.2f}s)"
    return LaneDispatchOutcome(
        lane=lane,
        dispatch_result={
            "section": lane,
            "fault": "timeout" if kind == "LANE_TIMEOUT" else "run_timeout",
            "exit_status": "error",
            "error": msg,
        },
        exec_status=f"error:{kind}",
        error=msg,
    )


def dispatch_phase1_lanes_managed(
    lanes_in_order: tuple[str, ...],
    ctx: LaneExecutionContext,
    *,
    dispatch_fn: Callable[..., dict[str, Any]],
    parallel: bool,
    max_parallel: int = 2,
    should_skip_remaining_waves: Callable[[], bool] | None = None,
    dependency_ready_fn: Callable[[str], bool | tuple[bool, str]] | None = None,
    lane_timeout_s: float | None = None,
    run_timeout_s: float | None = None,
) -> dict[str, LaneDispatchOutcome]:
    """Dispatch Phase-1 lanes with bounded ready queue and hard wall-clock deadlines."""
    outcomes: dict[str, LaneDispatchOutcome] = {}
    effective_lane_timeout = resolve_section_lane_timeout_s(lane_timeout_s)
    effective_run_timeout = resolve_section_run_timeout_s(run_timeout_s)
    run_deadline = time.monotonic() + effective_run_timeout

    reporter = ProgressReporter(
        total=max(len(lanes_in_order), 1), label="apps_rg section lanes", unit="lane"
    )
    ensure_sections_root_manifest(ctx)

    def _record(lane: str, outcome: LaneDispatchOutcome) -> None:
        outcomes[lane] = outcome
        reporter.update(label=f"{lane} [{str(getattr(outcome, 'exec_status', '') or 'done')}]")

    if not parallel:
        with DaemonWorkerPool(max_workers=1, thread_name_prefix="apps-rg-serial-lane") as pool:
            for lane in lanes_in_order:
                if should_skip_remaining_waves and should_skip_remaining_waves():
                    _record(lane, _skipped_prior_lane_abort(lane))
                    continue
                rem_run = run_deadline - time.monotonic()
                if rem_run <= 0:
                    _record(
                        lane,
                        LaneDispatchOutcome(
                            lane=lane,
                            dispatch_result={
                                "prior_abort": "PHASE1_RUN_TIMEOUT",
                                "fault": "run_timeout",
                                "exit_status": "error",
                            },
                            exec_status="pre_run_blocked:PHASE1_RUN_TIMEOUT",
                        ),
                    )
                    continue
                if hasattr(reporter, "set_status"):
                    reporter.set_status(f"running {lane}")
                cancel_ev = threading.Event()
                budget = min(effective_lane_timeout, rem_run)
                fut = pool.submit(
                    run_lane_in_context,
                    ctx,
                    lane,
                    dispatch_fn=dispatch_fn,
                    cancel_event=cancel_ev,
                )
                done, _ = wait((fut,), timeout=max(0.01, budget), return_when=FIRST_COMPLETED)
                if done:
                    _record(lane, fut.result())
                else:
                    cancel_ev.set()
                    _quarantine_timed_out_lane(ctx, lane)
                    kind = "RUN_TIMEOUT" if time.monotonic() >= run_deadline else "LANE_TIMEOUT"
                    _record(lane, _lane_timeout_outcome(lane, budget, kind=kind))
        reporter.done()
        return outcomes

    selected = tuple(dict.fromkeys(lanes_in_order))
    if len(selected) > 1:
        _prewarm_parallel_graph_sqlite()
    dependencies = section_dag_dependencies(lanes=selected)
    pending = set(selected)
    running: dict[Future[Any], tuple[str, float, threading.Event]] = {}
    cap = max(1, min(int(max_parallel), len(selected) or 1))

    with DaemonWorkerPool(max_workers=cap, thread_name_prefix="apps-rg-lane") as pool:
        while pending or running:
            now = time.monotonic()
            if now >= run_deadline and pending:
                for lane in selected:
                    if lane in pending:
                        pending.remove(lane)
                        _record(
                            lane,
                            LaneDispatchOutcome(
                                lane=lane,
                                dispatch_result={
                                    "prior_abort": "PHASE1_RUN_TIMEOUT",
                                    "fault": "run_timeout",
                                    "exit_status": "error",
                                },
                                exec_status="pre_run_blocked:PHASE1_RUN_TIMEOUT",
                            ),
                        )
            if should_skip_remaining_waves and should_skip_remaining_waves():
                for lane in selected:
                    if lane in pending:
                        pending.remove(lane)
                        _record(lane, _skipped_prior_lane_abort(lane))
            made_progress = False

            for lane in selected:
                if lane not in pending:
                    continue
                deps = dependencies.get(lane, ())
                failed = tuple(dep for dep in deps if dep in outcomes and not _outcome_succeeded(outcomes[dep]))
                if failed:
                    pending.remove(lane)
                    _record(lane, _skipped_dependency(lane, failed, "dependency_failed"))
                    made_progress = True

            for lane in selected:
                if len(running) >= cap or lane not in pending or time.monotonic() >= run_deadline:
                    continue
                deps = dependencies.get(lane, ())
                if not all(dep in outcomes and _outcome_succeeded(outcomes[dep]) for dep in deps):
                    continue
                ready, reason = _readiness_result(dependency_ready_fn, lane)
                if not ready:
                    pending.remove(lane)
                    _record(lane, _skipped_dependency(lane, deps, reason))
                    made_progress = True
                    continue
                pending.remove(lane)
                cancel_ev = threading.Event()
                lane_deadline = min(run_deadline, time.monotonic() + effective_lane_timeout)
                fut = pool.submit(
                    run_lane_in_context,
                    ctx,
                    lane,
                    dispatch_fn=dispatch_fn,
                    cancel_event=cancel_ev,
                )
                running[fut] = (lane, lane_deadline, cancel_ev)
                if hasattr(reporter, "set_status"):
                    reporter.set_status(
                        f"running: {', '.join(info[0] for info in running.values())}"
                    )
                made_progress = True

            if running:
                now = time.monotonic()
                earliest_deadline = min(
                    run_deadline,
                    *(info[1] for info in running.values()),
                )
                wait_s = max(0.0, earliest_deadline - now)
                done, _ = wait(tuple(running), timeout=wait_s, return_when=FIRST_COMPLETED)
                for fut in done:
                    lane, _, _ = running.pop(fut)
                    _record(lane, fut.result())
                now_after = time.monotonic()
                expired = [
                    fut
                    for fut, (_, lane_dl, _) in list(running.items())
                    if now_after >= lane_dl or now_after >= run_deadline
                ]
                for fut in expired:
                    lane, lane_dl, cancel_ev = running.pop(fut)
                    cancel_ev.set()
                    _quarantine_timed_out_lane(ctx, lane)
                    kind = "RUN_TIMEOUT" if now_after >= run_deadline and lane_dl >= run_deadline else "LANE_TIMEOUT"
                    _record(lane, _lane_timeout_outcome(lane, effective_lane_timeout, kind=kind))
                continue

            if pending and not made_progress:
                for lane in selected:
                    if lane in pending:
                        pending.remove(lane)
                        _record(
                            lane,
                            _skipped_dependency(
                                lane,
                                dependencies.get(lane, ()),
                                "dependencies_not_resolved",
                            ),
                        )
    for lane in lanes_in_order:
        if lane not in outcomes:
            _record(
                lane,
                LaneDispatchOutcome(lane=lane, exec_status="skipped", dispatch_result={}),
            )
    reporter.done()
    return {lane: outcomes[lane] for lane in lanes_in_order if lane in outcomes}


__all__ = ["dispatch_phase1_lanes_managed", "LaneWave"]
