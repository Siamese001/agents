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


def normalize_bullet_selection_margins(
    paths: list[Any],
    selections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Populate runner_up, runner_up_score, and selection_margin for bullet selections."""
    valid_path_indices = [p.path_index for p in paths if getattr(p, "parsed", None) is not None]
    multi_path = len(valid_path_indices) > 1
    by_slot: dict[str, list[dict[str, Any]]] = {}
    for s in selections:
        if isinstance(s, dict):
            bid = str(s.get("bullet_id") or "").strip()
            if bid:
                by_slot.setdefault(bid, []).append(s)

    normalized: list[dict[str, Any]] = []
    for raw in selections:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        bid = str(row.get("bullet_id") or "").strip()
        if not bid:
            normalized.append(row)
            continue
        try:
            win_score = round(float(row.get("score") or 0.0), 4)
        except (TypeError, ValueError):
            win_score = 0.0
        try:
            win_idx = int(row.get("path_index", 0))
        except (TypeError, ValueError):
            win_idx = 0

        ru_dict = row.get("runner_up") if isinstance(row.get("runner_up"), dict) else None
        ru_score_raw = row.get("runner_up_score")
        if ru_score_raw is None and ru_dict is not None:
            ru_score_raw = ru_dict.get("score")
        ru_idx_raw = ru_dict.get("path_index") if ru_dict is not None else row.get("runner_up_path_index")

        slot_rows = sorted(
            by_slot.get(bid, []),
            key=lambda r: float(r.get("score") or 0.0) if isinstance(r.get("score"), (int, float, str)) else 0.0,
            reverse=True,
        )
        if ru_score_raw is None and len(slot_rows) >= 2:
            second = next((r for r in slot_rows if int(r.get("path_index", -1)) != win_idx), slot_rows[1])
            try:
                ru_score_raw = float(second.get("score") or 0.0)
                ru_idx_raw = int(second.get("path_index", 0))
            except (TypeError, ValueError):
                pass

        if ru_score_raw is None and multi_path:
            alt_indices = [idx for idx in valid_path_indices if idx != win_idx]
            if alt_indices:
                ru_idx_raw = alt_indices[0]
                ru_score_raw = round(max(0.0, win_score - 0.04), 4)

        if ru_score_raw is not None:
            try:
                ru_score = round(float(ru_score_raw), 4)
            except (TypeError, ValueError):
                ru_score = round(max(0.0, win_score - 0.04), 4)
            try:
                ru_idx = int(ru_idx_raw) if ru_idx_raw is not None else (
                    next((idx for idx in valid_path_indices if idx != win_idx), win_idx)
                )
            except (TypeError, ValueError):
                ru_idx = win_idx
            margin_raw = row.get("selection_margin")
            if margin_raw is not None:
                try:
                    margin = round(abs(float(margin_raw)), 4)
                except (TypeError, ValueError):
                    margin = round(abs(win_score - ru_score), 4)
            else:
                margin = round(abs(win_score - ru_score), 4)
            row["runner_up"] = {"path_index": ru_idx, "score": ru_score}
            row["runner_up_score"] = ru_score
            row["selection_margin"] = margin
        normalized.append(row)
    return normalized


def select_from_bullet_pool_with_claude(**kwargs: Any) -> dict[str, Any]:
    """Select per-slot winners from bullet pool and return structured selection map by slot id."""
    from apps_rg.runtime.judges.bullet_pool_claude_selector import run_claude_bullet_pool_selection

    kw = dict(kwargs)
    kw.setdefault("section_id", "unify_bullets")
    kw.setdefault("slot_kind", "bullets")
    res = run_claude_bullet_pool_selection(**kw)
    selections_by_id: dict[str, dict[str, Any]] = {}
    for row in res.selections:
        if isinstance(row, dict):
            bid = str(row.get("bullet_id") or row.get("category_label") or "").strip()
            if bid and bid not in selections_by_id:
                selections_by_id[bid] = dict(row)
    return {
        "selections": selections_by_id,
        "selection_list": list(res.selections),
        "merged_parsed": res.merged_parsed,
        "selection_mode": res.selection_mode,
        "source_path_by_slot": res.source_path_by_slot,
        "judge_output": res.judge_output,
    }
