"""Helper utilities for bullet-pool self-consistency budgets and selector score aggregation."""
from __future__ import annotations

import os
from typing import Any

from apps_rg.runtime.section_model_limits import (
    SectionModelSSOTError,
    resolve_selector_provider_model,
    selector_role_for_section,
)


def format_bullet_pool_entry(bid: str, bullet: dict[str, Any] | None) -> str:
    if bullet is None:
        return f"[{bid}] MISSING"
    sfids = bullet.get("source_fact_ids") or []
    mraw = bullet.get("metric_raw") or ""
    meta_suffix = f" | source_fact_ids={sfids}" if sfids else ""
    if mraw:
        meta_suffix += f" | metric_raw={mraw!r}"
    return f"[{bid}] text={bullet.get('bullet_text', '')}{meta_suffix}"


def resolve_employment_lane_sc_budgets(
    *,
    section_lane: str,
    targeting_context: dict[str, Any] | None,
    judge_mode: str,
    sc_path_count_fn: Any,
    max_sc_path_count_fn: Any,
    adaptive_sc_fn: Any,
    max_regen_fn: Any,
) -> tuple[int, int, bool, int, int]:
    frozen_materialized = bool((targeting_context or {}).get("frozen_allocation_materialized"))
    initial_paths = 1 if frozen_materialized else sc_path_count_fn(section_lane)
    max_paths = 1 if frozen_materialized else max_sc_path_count_fn(section_lane)
    adaptive_sc = False if frozen_materialized else adaptive_sc_fn(section_lane)
    configured_regen = 0 if (judge_mode == "mocked" or frozen_materialized) else max_regen_fn()
    max_regen = max(configured_regen, 1) if adaptive_sc else configured_regen
    return initial_paths, max_paths, adaptive_sc, configured_regen, max_regen


def resolve_competencies_lane_sc_budgets(
    *,
    section_lane: str,
    targeting_context: dict[str, Any] | None,
    judge_mode: str,
    max_sc_path_count_fn: Any,
    max_regen_fn: Any,
    single_path_override: bool = False,
) -> tuple[int, int]:
    frozen_materialized = bool((targeting_context or {}).get("frozen_allocation_materialized")) or single_path_override
    max_regen = 0 if (judge_mode == "mocked" or frozen_materialized) else max_regen_fn()
    max_paths = 1 if frozen_materialized else max_sc_path_count_fn(section_lane)
    return max_paths, max_regen


def resolve_competencies_round_batch(
    *,
    section_lane: str,
    regen_round: int,
    judge_mode: str,
    sc_path_count_fn: Any,
    regen_extra_fn: Any,
    single_path_override: bool = False,
) -> int:
    if single_path_override:
        return 1
    sample_fast_path = (
        judge_mode != "mocked"
        and os.environ.get("APPS_RG_SAMPLE_FAST_PATH", "1").strip().lower() in ("1", "true", "yes")
        and not os.environ.get("PYTEST_CURRENT_TEST")
    )
    if regen_round == 0 and sample_fast_path:
        return 1
    return sc_path_count_fn(section_lane) if regen_round == 0 else regen_extra_fn(section_lane)


def build_mocked_single_path_competencies_pool(
    all_paths: list[Any],
    *,
    min_score: float,
) -> Any:
    from apps_rg.runtime.judges.bullet_pool_claude_selector import (
        PoolSelectionResult,
        merge_competencies_graph_pool_top_eight,
    )

    valid = [p for p in all_paths if getattr(p, "parsed", None)]
    if not valid:
        return PoolSelectionResult(
            merged_parsed={"competencies": [], "claim_ledger": []},
            selections=[],
            judge_output=None,
            selection_mode="mocked_single_path_empty",
            source_path_by_slot={},
        )
    first = valid[0]
    cats = list((first.parsed or {}).get("categories") or (first.parsed or {}).get("competencies") or [])
    selections = [
        {
            "category_label": str(c.get("category_label") or c.get("category") or c.get("label") or f"Cat_{i}"),
            "path_index": int(getattr(first, "path_index", 0)),
            "score": round(max(min_score + 0.12, 0.88), 2),
            "passes": True,
        }
        for i, c in enumerate(cats)
        if isinstance(c, dict)
    ]
    merged, source_map = merge_competencies_graph_pool_top_eight(
        valid,
        selections,
        min_score_threshold=min_score,
    )
    return PoolSelectionResult(
        merged_parsed=merged,
        selections=selections,
        judge_output=None,
        selection_mode="mocked_single_path_competencies_pool",
        source_path_by_slot=source_map,
    )


def resolve_selector_model_for_slot(section_id: str, *, slot_kind: str) -> tuple[str, str, str]:
    try:
        role = selector_role_for_section(section_id, slot_kind=slot_kind)
    except SectionModelSSOTError:
        if slot_kind == "bullets":
            role = "employment_bullet_pool_selector"
        else:
            raise
    return resolve_selector_provider_model(role)


def apply_selector_mean_and_min_scores(
    row: dict[str, Any],
    selections: list[dict[str, Any]],
) -> float:
    scores = [float(s.get("score") or 0.0) for s in selections if s.get("passes", True) is not False]
    min_score = min(scores) if scores else 0.0
    mean_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    row["score_scale"] = "0_to_1"
    row["score"] = mean_score
    row["normalized_score"] = mean_score
    row["min_slot_score"] = min_score
    return min_score


def execute_sc_paths_batch(
    temps: list[float],
    *,
    execution_mode: str,
    max_parallel: int,
    thread_prefix: str,
    section_lane: str,
    run_fn: Any,
    zero_output_timeout_fn: Any,
) -> list[Any]:
    """Execute self-consistency paths concurrently via DaemonWorkerPool without serial path-0 stalls."""
    import time

    from apps_rg.runtime.providers.wallclock_http_guard import (
        DaemonWorkerPool,
        resolve_section_lane_timeout_s,
    )

    paths: list[Any] = []
    if execution_mode == "parallel" and len(temps) > 1 and max_parallel > 1:
        batch_budget_s = max(15.0, resolve_section_lane_timeout_s())
        deadline = time.monotonic() + batch_budget_s
        with DaemonWorkerPool(
            max_workers=min(max_parallel, len(temps)),
            thread_name_prefix=thread_prefix,
        ) as pool:
            futures = [(offset, pool.submit(run_fn, offset, temp)) for offset, temp in enumerate(temps)]
            for offset, fut in futures:
                remaining = max(0.05, deadline - time.monotonic())
                try:
                    paths.append(fut.result(timeout=remaining))
                except TimeoutError as exc:
                    raise TimeoutError(
                        f"SC_BATCH_PATH_TIMEOUT:lane={section_lane}:offset={offset}:budget_s={batch_budget_s}"
                    ) from exc
        return paths

    for offset, temp in enumerate(temps):
        path = run_fn(offset, temp)
        paths.append(path)
        if section_lane == "competencies" and zero_output_timeout_fn(path):
            break
    return paths
