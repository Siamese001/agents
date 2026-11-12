"""Wave-parallel patch lane dispatch and split pointer synchronization helpers."""
from __future__ import annotations

import concurrent.futures
import json
import threading
import time
from pathlib import Path
from typing import Any

from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.providers.wallclock_http_guard import (
    DaemonWorkerPool,
    mark_artifact_dir_cancelled,
)


def _load_json_dict(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def _write_json_doc(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_split_pointer_roots(run_dir: Path | str) -> None:
    """Synchronize split lane pointers and flat lane artifacts when both lanes/ and modular_r4/sections/ exist."""
    import shutil

    rd = Path(str(run_dir)).resolve()
    modular_root = rd / "modular_r4" / "sections"
    lanes_root = rd / "lanes"
    if not (modular_root.is_dir() and lanes_root.is_dir()):
        return
    lanes_has_manifest = (lanes_root / "sections_root_manifest.json").is_file()
    modular_has_manifest = (modular_root / "sections_root_manifest.json").is_file()
    for lane in GENERATED_LANES:
        winner_ptr: dict[str, Any] | None = None
        for ptr_name in ("latest_real_run.json", "latest_successful_real_run.json"):
            p_lanes = lanes_root / lane / ptr_name
            p_mod = modular_root / lane / ptr_name
            d_lanes = _load_json_dict(p_lanes)
            d_mod = _load_json_dict(p_mod)
            if d_lanes is None and d_mod is None:
                continue
            if d_lanes is not None and d_mod is None:
                _write_json_doc(p_mod, d_lanes)
                winner_ptr = d_lanes
                continue
            if d_mod is not None and d_lanes is None:
                _write_json_doc(p_lanes, d_mod)
                winner_ptr = d_mod
                continue
            assert d_lanes is not None and d_mod is not None
            ts_lanes = str(d_lanes.get("generated_at_utc") or "")
            ts_mod = str(d_mod.get("generated_at_utc") or "")
            if ts_lanes and ts_mod and ts_lanes != ts_mod:
                winner = d_lanes if ts_lanes > ts_mod else d_mod
            elif lanes_has_manifest and not modular_has_manifest:
                winner = d_lanes
            else:
                winner = d_mod
            if d_lanes != winner:
                _write_json_doc(p_lanes, winner)
            if d_mod != winner:
                _write_json_doc(p_mod, winner)
            winner_ptr = winner
        if winner_ptr is not None:
            rel_dir = str(winner_ptr.get("run_dir") or winner_ptr.get("run_dir_repo_relative") or "").strip()
            flat_dir = lanes_root / lane
            if rel_dir and flat_dir.is_dir():
                src_dir: Path | None = None
                cand_abs = Path(rel_dir)
                if cand_abs.is_absolute() and cand_abs.is_dir():
                    src_dir = cand_abs
                else:
                    for anc in [rd, *rd.parents]:
                        c = (anc / rel_dir).resolve()
                        if c.is_dir():
                            src_dir = c
                            break
                if src_dir is not None and src_dir.resolve() != flat_dir.resolve():
                    for item in src_dir.iterdir():
                        if item.is_file():
                            shutil.copy2(item, flat_dir / item.name)
            if (lanes_root / lane / "latest_successful_real_run.json").is_file() or (
                modular_root / lane / "latest_successful_real_run.json"
            ).is_file():
                for stale_dir in (lanes_root / lane, modular_root / lane):
                    stale_fail = stale_dir / "integrated_lane_pre_run_failure.json"
                    if stale_fail.is_file():
                        try:
                            stale_fail.unlink()
                        except OSError:
                            pass


def mirror_sibling_pointer_roots(
    msr: Path | None,
    lane: str,
    *,
    ptr_name: str,
    pointer: dict[str, Any],
    write_latest_success: bool,
    latest_filename: str,
    is_integrated_whole_run_fn: Any,
    write_json_fn: Any,
) -> None:
    if msr is None:
        return
    resolved_msr = msr.resolve()
    sibling_msr: Path | None = None
    if resolved_msr.name == "lanes" and is_integrated_whole_run_fn(resolved_msr.parent):
        cand = resolved_msr.parent / "modular_r4" / "sections"
        if cand.is_dir():
            sibling_msr = cand
    elif (
        resolved_msr.name == "sections"
        and resolved_msr.parent.name == "modular_r4"
        and is_integrated_whole_run_fn(resolved_msr.parent.parent)
    ):
        cand = resolved_msr.parent.parent / "lanes"
        if cand.is_dir():
            sibling_msr = cand
    if sibling_msr is not None:
        sibling_lane_root = sibling_msr / lane
        write_json_fn(sibling_lane_root / ptr_name, pointer)
        if write_latest_success:
            write_json_fn(sibling_lane_root / latest_filename, pointer)


def dispatch_patch_lanes_wave_parallel(
    plan: Any,
    *,
    lane_provider: str,
    dispatch: Any,
    sections_root: Path,
    lane_timeout: float,
    run_timeout: float,
    clock_start: float,
) -> dict[str, dict[str, Any]]:
    from apps_rg.runtime.integrated_lane_evidence_packaging import (
        emit_integrated_lane_pre_run_failure,
    )
    from apps_rg.runtime.orchestration.section_lane_concurrency import resolve_max_parallel
    from apps_rg.runtime.product_output_policy import (
        phase1_dispatch_hard_failed,
        product_fail_closed_runtime,
    )
    from apps_rg.runtime.reasoning.employment_bullet_pool import REQUIRED_BULLET_IDS
    from apps_rg.runtime.section_execution_plan import (
        NARRATIVE_UPSTREAM_BULLET_LANE,
        execution_waves_for_lanes,
    )
    from apps_rg.runtime.validators.companion_bullet_finalization import (
        PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER,
        companion_accepted_in_modular_sections_root,
    )

    repo = plan.repo
    results: dict[str, dict[str, Any]] = {}
    aborted = False
    abort_reason = ""
    total_lanes = len(plan.target_lanes)
    lane_idx_map = {lane: i for i, lane in enumerate(plan.target_lanes, start=1)}
    max_workers_cap = resolve_max_parallel(default=6)

    for wave_lanes in execution_waves_for_lanes(plan.target_lanes):
        ready_lanes: list[str] = []
        for lane in wave_lanes:
            idx = lane_idx_map.get(lane, 0)
            if aborted:
                results[lane] = {"prior_abort": abort_reason, "exit_status": "error"}
                print(
                    f"[patch_run] [{idx}/{total_lanes}] Skipping lane '{lane}' (prior abort: {abort_reason})",
                    flush=True,
                )
                emit_integrated_lane_pre_run_failure(
                    sections_root=sections_root,
                    integrated_dir=plan.run_dir,
                    repo_root=repo,
                    lane_id=lane,
                    blocker="PHASE1_PRIOR_LANE_FAILED",
                    dispatch_result=results[lane],
                    lane_exec_status="pre_run_blocked:PHASE1_PRIOR_LANE_FAILED",
                )
                continue

            if (time.monotonic() - clock_start) >= run_timeout:
                aborted = True
                abort_reason = f"run_timeout_exceeded:{run_timeout:.1f}s"
                results[lane] = {
                    "prior_abort": abort_reason,
                    "exit_status": "error",
                    "fault": "patch_run_timeout",
                }
                print(
                    f"[patch_run] [{idx}/{total_lanes}] Aborting lane '{lane}': "
                    f"total patch-run timeout exceeded ({run_timeout:.1f}s)",
                    flush=True,
                )
                emit_integrated_lane_pre_run_failure(
                    sections_root=sections_root,
                    integrated_dir=plan.run_dir,
                    repo_root=repo,
                    lane_id=lane,
                    blocker="PATCH_RUN_TIMEOUT",
                    dispatch_result=results[lane],
                    lane_exec_status="pre_run_blocked:PATCH_RUN_TIMEOUT",
                )
                continue

            upstream = NARRATIVE_UPSTREAM_BULLET_LANE.get(lane)
            if upstream is not None:
                expected_ids = tuple(REQUIRED_BULLET_IDS.get(upstream, ()))
                if not companion_accepted_in_modular_sections_root(
                    repo,
                    sections_root,
                    upstream_section_id=upstream,
                    expected_bullet_ids=expected_ids,
                ):
                    results[lane] = {
                        "fault": "upstream_not_finalized",
                        "upstream_lane": upstream,
                        "exit_status": "error",
                    }
                    print(
                        f"[patch_run] [{idx}/{total_lanes}] Lane '{lane}' blocked: "
                        f"upstream '{upstream}' not finalized",
                        flush=True,
                    )
                    emit_integrated_lane_pre_run_failure(
                        sections_root=sections_root,
                        integrated_dir=plan.run_dir,
                        repo_root=repo,
                        lane_id=lane,
                        blocker=PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER,
                        dispatch_result=results[lane],
                        lane_exec_status=f"pre_run_blocked:{PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER}",
                    )
                    continue
            ready_lanes.append(lane)

        if not ready_lanes:
            continue

        workers = min(len(ready_lanes), max_workers_cap)
        executor = DaemonWorkerPool(max_workers=workers, thread_name_prefix="apps-rg-patch-lane")
        futures: dict[str, tuple[float, concurrent.futures.Future[dict[str, Any]], threading.Event]] = {}
        any_timed_out = False
        try:
            for lane in ready_lanes:
                idx = lane_idx_map.get(lane, 0)
                print(
                    f"[patch_run] [{idx}/{total_lanes}] Dispatching lane '{lane}' "
                    f"(lane_timeout={lane_timeout:.0f}s)...",
                    flush=True,
                )
                l_start = time.monotonic()
                cancel_ev = threading.Event()
                fut = executor.submit(
                    dispatch,
                    plan=plan,
                    lane=lane,
                    lane_provider=lane_provider,
                    cancel_event=cancel_ev,
                )
                futures[lane] = (l_start, fut, cancel_ev)

            for lane in ready_lanes:
                idx = lane_idx_map.get(lane, 0)
                lane_start, future, cancel_ev = futures[lane]
                now_mono = time.monotonic()
                remaining_wait = max(
                    0.05,
                    min(
                        lane_timeout - (now_mono - lane_start),
                        run_timeout - (now_mono - clock_start),
                    ),
                )
                timed_out = False
                try:
                    results[lane] = future.result(timeout=remaining_wait)
                except concurrent.futures.TimeoutError:
                    timed_out = True
                    any_timed_out = True
                    cancel_ev.set()
                    results[lane] = {
                        "fault": "timeout",
                        "error": f"Lane '{lane}' timed out after {lane_timeout:.1f}s",
                        "exit_status": "error",
                    }
                    print(
                        f"[patch_run] [{idx}/{total_lanes}] ERROR: Lane '{lane}' TIMED OUT after {lane_timeout:.1f}s",
                        flush=True,
                    )
                    emit_integrated_lane_pre_run_failure(
                        sections_root=sections_root,
                        integrated_dir=plan.run_dir,
                        repo_root=repo,
                        lane_id=lane,
                        blocker="LANE_TIMEOUT",
                        dispatch_result=results[lane],
                        lane_exec_status="pre_run_blocked:LANE_TIMEOUT",
                    )
                    mark_artifact_dir_cancelled(sections_root / lane)
                    if getattr(plan, "run_dir", None) is not None:
                        mark_artifact_dir_cancelled(Path(plan.run_dir) / "lanes" / lane)
                        mark_artifact_dir_cancelled(Path(plan.run_dir) / "modular_r4" / "sections" / lane)
                except (
                    ImportError,
                    AttributeError,
                    KeyError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ) as exc:
                    results[lane] = {
                        "fault": "exception",
                        "error": str(exc),
                        "exit_status": "error",
                    }
                    print(
                        f"[patch_run] [{idx}/{total_lanes}] ERROR: Lane '{lane}' exception: {exc}",
                        flush=True,
                    )

                lane_elapsed = time.monotonic() - lane_start
                exit_status = str(results[lane].get("exit_status") or "unknown")
                x3_code = str(
                    results[lane].get("x3_disposition") or results[lane].get("fault") or ""
                )
                if not timed_out and "fault" not in results[lane]:
                    print(
                        f"[patch_run] [{idx}/{total_lanes}] Lane '{lane}' finished in {lane_elapsed:.1f}s "
                        f"(exit_status={exit_status}, x3={x3_code})",
                        flush=True,
                    )

                if product_fail_closed_runtime() and phase1_dispatch_hard_failed(results[lane]):
                    aborted = True
                    abort_reason = f"dispatch_failed:{lane}"
        finally:
            executor.shutdown(wait=False, cancel_futures=any_timed_out)
        sync_split_pointer_roots(plan.run_dir)
    return results
