"""Managed wave-based Phase-1 lane dispatcher (external model-safe parallelism)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from apps_rg.runtime.orchestration.section_lane_concurrency import LaneWave, section_dag_dependencies
from apps_rg.runtime.orchestration.section_lane_executor import (
    LaneDispatchOutcome,
    LaneExecutionContext,
    ensure_sections_root_manifest,
    run_lane_in_context,
)
from apps_rg.runtime.product_output_policy import PHASE1_PRIOR_LANE_FAILED_BLOCKER


class ProgressReporter:  # pragma: no cover - exercised via the public dispatcher
    """App-owned progress fallback; it carries no workflow authority."""

    def __init__(self, total: int, label: str = "", unit: str = "") -> None:
        self.total = total
        self.label = label
        self.unit = unit
        self.completed = 0

    def update(self, label: str = "") -> None:
        self.completed += 1
        logging.getLogger(__name__).info(
            "%s: %s/%s %s %s",
            self.label,
            self.completed,
            self.total,
            self.unit,
            label,
        )

    def done(self) -> None:
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


def dispatch_phase1_lanes_managed(
    lanes_in_order: tuple[str, ...],
    ctx: LaneExecutionContext,
    *,
    dispatch_fn: Callable[..., dict[str, Any]],
    parallel: bool,
    max_parallel: int = 2,
    should_skip_remaining_waves: Callable[[], bool] | None = None,
    dependency_ready_fn: Callable[[str], bool | tuple[bool, str]] | None = None,
) -> dict[str, LaneDispatchOutcome]:
    """Dispatch Phase-1 lanes with a bounded, dependency-aware ready queue.

    Parallel execution is work-conserving: as soon as a bullets lane completes
    and its acceptance receipt validates, its paired narrative can start while
    other independent bullets are still running.  The manifest's waves remain
    an observability grouping, not an all-of-wave completion barrier.  A caller
    that supplies ``should_skip_remaining_waves`` retains the legacy global
    abort behavior for a true run-wide abort condition.
    """
    outcomes: dict[str, LaneDispatchOutcome] = {}

    # §16 query-progress (constitutional): a Phase-1 dispatch runs N section lanes, each an
    # ~1-2 min LLM generation, so the loop is a multi-minute operation that MUST surface a
    # progress bar — the static check_query_progress_bar gate misses it because the loop body
    # is short and the function is not a scan_/query_-prefixed "heavy" name. The bar ticks on
    # lane COMPLETION from the MAIN thread only (the serial loops + the parallel as_completed
    # loop), never from a worker thread, so it is concurrency-safe under ThreadPoolExecutor.
    reporter = ProgressReporter(
        total=max(len(lanes_in_order), 1), label="apps_rg section lanes", unit="lane"
    )

    # Guarantee sections_root_manifest.json exists beside ctx.sections_root
    # so child lane dispatches and finalize_runtime_proof_run never trigger
    # require_manifest_for_modular_sections_root fail-closed gate.
    ensure_sections_root_manifest(ctx)

    def _record(lane: str, outcome: LaneDispatchOutcome) -> None:
        outcomes[lane] = outcome
        reporter.update(label=f"{lane} [{str(getattr(outcome, 'exec_status', '') or 'done')}]")

    if not parallel:
        for lane in lanes_in_order:
            if should_skip_remaining_waves and should_skip_remaining_waves():
                _record(lane, _skipped_prior_lane_abort(lane))
                continue
            _record(lane, run_lane_in_context(ctx, lane, dispatch_fn=dispatch_fn))
        reporter.done()
        return outcomes

    selected = tuple(dict.fromkeys(lanes_in_order))
    dependencies = section_dag_dependencies(lanes=selected)
    pending = set(selected)
    running: dict[Any, str] = {}
    cap = max(1, min(int(max_parallel), len(selected) or 1))

    with ThreadPoolExecutor(max_workers=cap) as pool:
        while pending or running:
            if should_skip_remaining_waves and should_skip_remaining_waves():
                for lane in selected:
                    if lane in pending:
                        pending.remove(lane)
                        _record(lane, _skipped_prior_lane_abort(lane))
            made_progress = False

            # A failed prerequisite blocks its descendants only.  Independent
            # branches continue, preserving their receipts for diagnosis/rerun.
            for lane in selected:
                if lane not in pending:
                    continue
                deps = dependencies.get(lane, ())
                failed = tuple(dep for dep in deps if dep in outcomes and not _outcome_succeeded(outcomes[dep]))
                if failed:
                    pending.remove(lane)
                    _record(lane, _skipped_dependency(lane, failed, "dependency_failed"))
                    made_progress = True

            # Submit deterministic ready lanes until the global provider-safe
            # capacity is full.  This is deliberately a single shared cap, not
            # a per-wave cap that can accidentally over-fan-out requests.
            for lane in selected:
                if len(running) >= cap or lane not in pending:
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
                fut = pool.submit(run_lane_in_context, ctx, lane, dispatch_fn=dispatch_fn)
                running[fut] = lane
                made_progress = True

            if running:
                fut = next(as_completed(tuple(running)))
                lane = running.pop(fut)
                _record(lane, fut.result())
                continue

            if pending and not made_progress:
                # The manifest validator rejects cycles, so reaching here means
                # a subset caller omitted or could not satisfy a prerequisite.
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
