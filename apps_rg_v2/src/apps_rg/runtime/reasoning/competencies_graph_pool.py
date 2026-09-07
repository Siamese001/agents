"""Competencies graph_8x8 pool — adaptive paths → 6-8 graph-grounded categories."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.sections.competencies_rigor import (
    CANDIDATE_CATEGORY_COUNT,
    MAX_CATEGORY_COUNT,
    MIN_CATEGORY_COUNT,
)

DEFAULT_COMPETENCIES_INITIAL_SC_PATH_COUNT: Final[int] = 4
COMPETENCIES_MAX_SC_PATH_COUNT: Final[int] = CANDIDATE_CATEGORY_COUNT
COMPETENCIES_SC_PATH_COUNT: Final[int] = DEFAULT_COMPETENCIES_INITIAL_SC_PATH_COUNT
COMPETENCIES_MIN_CATEGORY_COUNT: Final[int] = MIN_CATEGORY_COUNT
COMPETENCIES_MAX_CATEGORY_COUNT: Final[int] = MAX_CATEGORY_COUNT
COMPETENCIES_FINAL_CATEGORY_COUNT: Final[int] = MAX_CATEGORY_COUNT
COMPETENCIES_CANDIDATE_CATEGORY_COUNT: Final[int] = CANDIDATE_CATEGORY_COUNT
COMPETENCIES_REGEN_EXTRA_PATHS: Final[int] = 4

DEFAULT_COMPETENCIES_MIN_SELECTION_SCORE: Final[float] = 0.72
DEFAULT_COMPETENCIES_HIGH_SIGNAL_SELECTION_SCORE: Final[float] = 0.84
MIN_COMPETENCIES_SUPPORTED_TERM_RATIO: Final[float] = 1.0 / 3.0
REQUIRED_COMPETENCY_BUNDLE_BY_FAMILY: Final[dict[str, str]] = {
    "agentic_platform": "ccb_agentic_platforms",
    "runtime_governance": "ccb_runtime_governance",
    "retrieval_context": "ccb_retrieval_context_engineering",
    "llmops": "ccb_llmops_reliability",
    "distributed_infra": "ccb_distributed_systems_engineering",
    "productization": "ccb_platform_productization",
    "partner_architecture": "ccb_partner_applied_ai_architecture",
    "engineering_leadership": "ccb_engineering_leadership",
}
# W6: closeout-mode regen cap when APPS_RG_E2E_CLOSEOUT_MODE=1 and no explicit regen-round env.
DEFAULT_COMPETENCIES_CLOSEOUT_MAX_REGEN_ROUNDS: Final[int] = 1


def e2e_closeout_mode_active() -> bool:
    """True when the operator has explicitly opted into E2E closeout mode (APPS_RG_E2E_CLOSEOUT_MODE).

    Closeout mode is an EXPLICIT, AUDITABLE bias toward finishing the full-resume E2E: it keeps the
    8 final categories, graph authority, and X2/X3 fully intact, and only (optionally) caps regen
    rounds so a long run converges. It is NEVER the product default — the strict product path is
    unchanged unless this flag is set. Artifacts stamp ``e2e_closeout_mode`` so a closeout run is
    distinguishable from a strict one.
    """
    return os.environ.get("APPS_RG_E2E_CLOSEOUT_MODE", "").strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class CompetenciesSelectionGate:
    ok: bool
    section_lane: str
    final_category_count: int
    min_category_count: int
    max_category_count: int
    min_score_threshold: float
    categories_passing: tuple[str, ...]
    categories_below_threshold: tuple[str, ...]
    categories_missing: tuple[str, ...]
    categories_in_merged: int
    bundle_ids_missing: tuple[str, ...]
    duplicate_bundle_ids: tuple[str, ...]
    taxonomy_category_ids_missing: tuple[str, ...]
    duplicate_taxonomy_category_ids: tuple[str, ...]
    missing_capability_families: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "section_lane": self.section_lane,
            "final_category_count": self.final_category_count,
            "min_category_count": self.min_category_count,
            "max_category_count": self.max_category_count,
            "min_score_threshold": self.min_score_threshold,
            "categories_passing": list(self.categories_passing),
            "categories_below_threshold": list(self.categories_below_threshold),
            "categories_missing": list(self.categories_missing),
            "categories_in_merged": self.categories_in_merged,
            "bundle_ids_missing": list(self.bundle_ids_missing),
            "duplicate_bundle_ids": list(self.duplicate_bundle_ids),
            "taxonomy_category_ids_missing": list(self.taxonomy_category_ids_missing),
            "duplicate_taxonomy_category_ids": list(self.duplicate_taxonomy_category_ids),
            "missing_capability_families": list(self.missing_capability_families),
        }


def _int_env_bounded(name: str, *, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw:
        try:
            return max(low, min(high, int(raw)))
        except ValueError:  # guardian: allow-silent-swallow -- optional operator override
            pass
    return max(low, min(high, default))


def _float_env_bounded(name: str, *, default: float, low: float, high: float) -> float:
    raw = os.environ.get(name, "").strip()
    if raw:
        try:
            return max(low, min(high, float(raw)))
        except ValueError:  # guardian: allow-silent-swallow -- optional operator override
            pass
    return max(low, min(high, default))


def competencies_initial_sc_path_count() -> int:
    return _int_env_bounded(
        "APPS_RG_COMPETENCIES_INITIAL_SC_PATHS",
        default=DEFAULT_COMPETENCIES_INITIAL_SC_PATH_COUNT,
        low=1,
        high=COMPETENCIES_MAX_SC_PATH_COUNT,
    )


def competencies_max_sc_path_count() -> int:
    return _int_env_bounded(
        "APPS_RG_COMPETENCIES_MAX_SC_PATHS",
        default=COMPETENCIES_MAX_SC_PATH_COUNT,
        low=competencies_initial_sc_path_count(),
        high=CANDIDATE_CATEGORY_COUNT,
    )


def min_competencies_selection_score() -> float:
    override = os.environ.get("APPS_RG_COMPETENCIES_MIN_SELECTION_SCORE", "").strip()
    if not override:
        override = os.environ.get("APPS_RG_EMPLOYMENT_BULLET_MIN_SELECTION_SCORE", "").strip()
    if override:
        try:
            return max(0.0, min(1.0, float(override)))
        except ValueError:  # guardian: allow-silent-swallow -- P2 burndown: fail-soft optional boundary
            pass
    return DEFAULT_COMPETENCIES_MIN_SELECTION_SCORE


def high_signal_competencies_selection_score() -> float:
    return _float_env_bounded(
        "APPS_RG_COMPETENCIES_HIGH_SIGNAL_SCORE",
        default=DEFAULT_COMPETENCIES_HIGH_SIGNAL_SELECTION_SCORE,
        low=min_competencies_selection_score(),
        high=1.0,
    )


def competencies_regen_extra_path_count() -> int:
    raw = os.environ.get("APPS_RG_COMPETENCIES_REGEN_EXTRA_PATHS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:  # guardian: allow-silent-swallow -- P2 burndown: fail-soft optional boundary
            pass
    # W6: in closeout mode with no explicit override, suppress extra regen breadth so the run
    # converges on the initial pool. Strict product default is unchanged.
    if e2e_closeout_mode_active():
        return 0
    return COMPETENCIES_REGEN_EXTRA_PATHS


def max_competencies_regen_rounds() -> int:
    raw = os.environ.get("APPS_RG_COMPETENCIES_MAX_REGEN_ROUNDS", "").strip()
    explicit_emp = os.environ.get("APPS_RG_EMPLOYMENT_BULLET_MAX_REGEN_ROUNDS", "").strip()
    if not raw and not explicit_emp and e2e_closeout_mode_active():
        # W6: closeout-mode cap when neither explicit regen env is set. Caps rounds (default 1) so a
        # long competencies run converges; the strict product path (no closeout flag) is unchanged.
        cap_raw = os.environ.get("APPS_RG_COMPETENCIES_CLOSEOUT_MAX_REGEN_ROUNDS", "").strip()
        try:
            return max(0, int(cap_raw)) if cap_raw else DEFAULT_COMPETENCIES_CLOSEOUT_MAX_REGEN_ROUNDS
        except ValueError:
            return DEFAULT_COMPETENCIES_CLOSEOUT_MAX_REGEN_ROUNDS
    if not raw:
        raw = explicit_emp or "2"
    try:
        return max(0, int(raw))
    except ValueError:
        return 2


def is_competencies_pool_generation(gen_meta: dict[str, Any] | None) -> bool:
    mode = str((gen_meta or {}).get("generation_mode") or "")
    return mode.startswith("model_competencies_graph_pool")


def build_competencies_targeting_context(
    runtime_payload: dict[str, Any],
    *,
    allowed_fact_ids: set[str] | None = None,
    allowed_skill_ids: set[str] | None = None,
) -> dict[str, Any]:
    """JD/briefing + graph proof metadata for pool selector (targeting only, not proof)."""
    pp = runtime_payload.get("proof_pool_metadata") or {}
    allowed = allowed_fact_ids or set()
    skill_ids: set[str] = set(allowed_skill_ids or [])
    for row in pp.get("selected_skill_rows") or []:
        if isinstance(row, dict):
            sid = str(row.get("skill_id") or "").strip()
            if sid:
                skill_ids.add(sid)
    for sid in pp.get("c03_selected_skill_ids") or []:
        if str(sid).strip():
            skill_ids.add(str(sid).strip())
    packet = (
        pp.get("competency_capability_section_packet")
        or runtime_payload.get("competency_capability_section_packet")
        or {}
    )
    selected_plan = runtime_payload.get("selected_fact_plan") or {}
    from apps_rg.runtime.sections.competency_capability_evidence import (
        _plan_fact_ids_for_bundle,
        visible_graph_surface_taxonomy_for_bundle,
    )

    records_by_id = {
        str(row.get("competency_bundle_id") or "").strip(): row
        for row in packet.get("competency_bundles") or []
        if isinstance(row, dict) and str(row.get("competency_bundle_id") or "").strip()
    }
    governed_required_candidates: list[dict[str, Any]] = []
    for family, bundle_id in REQUIRED_COMPETENCY_BUNDLE_BY_FAMILY.items():
        record = records_by_id.get(bundle_id)
        if not isinstance(record, dict):
            continue
        taxonomy_id, taxonomy_label = visible_graph_surface_taxonomy_for_bundle(
            bundle_id,
            record=record,
        )
        fact_ids = _plan_fact_ids_for_bundle(
            record,
            selected_graph_evidence_plan=selected_plan,
            allowed_fact_ids=allowed,
        )
        graph_skill_ids = [
            str(value).strip()
            for value in record.get("graph_skill_node_ids") or []
            if str(value).strip()
        ]
        terms = []
        for phrase in record.get("vocabulary_anchors") or []:
            text = str(phrase or "").strip()
            if not text:
                continue
            term = {
                "text": text,
                "term": text,
                "source_fact_ids": list(fact_ids),
                "source_skill_ids": list(graph_skill_ids),
                "graph_skill_node_ids": list(graph_skill_ids),
                "support_class": "GOVERNED_COMPETENCY_BUNDLE_CANDIDATE",
                "proof_source": "competency_bundle_governed_selector_baseline",
            }
            if fact_ids:
                term["source_fact_id"] = fact_ids[0]
            terms.append(term)
        governed_required_candidates.append(
            {
                "category_id": taxonomy_id,
                "category_label": str(
                    record.get("display_label_candidate") or taxonomy_label
                ).strip(),
                "resume_display_label": str(
                    record.get("display_label_candidate") or taxonomy_label
                ).strip(),
                "competency_bundle_id": bundle_id,
                "capability_family": str(record.get("capability_family") or family),
                "graph_skill_node_ids": graph_skill_ids,
                "source_fact_ids": list(fact_ids),
                "terms": terms,
                "candidate_origin": "governed_required_bundle_baseline",
            }
        )

    return {
        "target_title": runtime_payload.get("target_title"),
        "target_company": runtime_payload.get("target_company"),
        "jd_text": (runtime_payload.get("jd_text") or "")[:4000],
        "briefing": (runtime_payload.get("briefing") or "")[:2500],
        "jd_used_as_proof": False,
        "briefing_used_as_proof": False,
        "skills_graph_ref": pp.get("graph_ref") or pp.get("augmented_skills_graph_ref"),
        "proof_pool_type": pp.get("proof_pool_type"),
        "selection_method": (runtime_payload.get("selected_fact_plan") or {}).get("selection_method"),
        "pool_path_count": competencies_initial_sc_path_count(),
        "initial_sc_path_count": competencies_initial_sc_path_count(),
        "max_sc_path_count": competencies_max_sc_path_count(),
        "candidate_category_count": COMPETENCIES_CANDIDATE_CATEGORY_COUNT,
        "min_category_count": COMPETENCIES_MIN_CATEGORY_COUNT,
        "max_category_count": COMPETENCIES_MAX_CATEGORY_COUNT,
        "final_category_count": COMPETENCIES_FINAL_CATEGORY_COUNT,
        "min_selection_score": min_competencies_selection_score(),
        "high_signal_selection_score": high_signal_competencies_selection_score(),
        "selection_model": "graph_8x8_v1",
        "allowed_fact_ids_count": len(allowed),
        "allowed_fact_ids": sorted(allowed),
        "allowed_skill_ids": sorted(skill_ids),
        "governed_required_bundle_candidates": governed_required_candidates,
    }


def _selection_row_score(row: dict[str, Any]) -> float:
    try:
        return float(row.get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _selection_row_passes(row: dict[str, Any]) -> bool:
    if "passes" not in row:
        return True
    val = row.get("passes")
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


def _category_by_label(parsed: dict[str, Any], label: str) -> dict[str, Any] | None:
    norm = label.strip().lower()
    for key in ("competencies", "categories"):
        for row in parsed.get(key) or []:
            if not isinstance(row, dict):
                continue
            if str(
                row.get("category_label")
                or row.get("display_label")
                or row.get("resume_display_label")
                or row.get("category")
                or ""
            ).strip().lower() == norm:
                return row
    return None


def _heuristic_category_score(
    cat: dict[str, Any],
    *,
    allowed_fact_ids: set[str],
    allowed_skill_ids: set[str],
    resume_support_blob_lower: str,
) -> float:
    from apps_rg.runtime.validators.competencies_x2 import term_supports_resume_or_graph

    terms = cat.get("terms") or []
    if not isinstance(terms, list) or not terms:
        return 0.0
    supported = 0
    for raw_t in terms:
        term = raw_t if isinstance(raw_t, dict) else {"text": str(raw_t)}
        if term_supports_resume_or_graph(
            term,
            allowed_fact_ids=allowed_fact_ids,
            allowed_skill_ids=allowed_skill_ids,
            resume_support_blob_lower=resume_support_blob_lower,
        ):
            supported += 1
    base = supported / max(1, len(terms))
    cat_ids = [str(x).split("_metric_")[0] for x in (cat.get("source_fact_ids") or []) if x]
    if cat_ids and all(fid in allowed_fact_ids for fid in cat_ids):
        base = min(1.0, base + 0.05)
    return base


def competencies_candidate_support_score(
    category: dict[str, Any],
    *,
    allowed_fact_ids: set[str],
    allowed_skill_ids: set[str],
    resume_support_blob_lower: str = "",
) -> float:
    """Public evidence-support score for governed selector completion rows."""
    return _heuristic_category_score(
        category,
        allowed_fact_ids=allowed_fact_ids,
        allowed_skill_ids=allowed_skill_ids,
        resume_support_blob_lower=resume_support_blob_lower,
    )


def _collect_category_candidates(
    paths: list[Any],
    selections: list[dict[str, Any]],
) -> dict[str, list[tuple[float, int, dict[str, Any]]]]:
    """label_lower -> [(score, path_index, category_dict), ...]"""
    out: dict[str, list[tuple[float, int, dict[str, Any]]]] = {}
    path_by_index = {p.path_index: p for p in paths}

    for sel in selections:
        if not isinstance(sel, dict):
            continue
        label = str(sel.get("category_label") or "").strip()
        if not label:
            continue
        key = label.lower()
        path_idx = int(sel.get("path_index", 0))
        path = path_by_index.get(path_idx)
        cat = _category_by_label(path.parsed or {}, label) if path and path.parsed else None
        if cat is None:
            continue
        score = _selection_row_score(sel)
        out.setdefault(key, []).append((score, path_idx, dict(cat)))

    for path in paths:
        if not path.parsed:
            continue
        for cat in (path.parsed.get("competencies") or path.parsed.get("categories") or []):
            if not isinstance(cat, dict):
                continue
            label = str(
                cat.get("category_label")
                or cat.get("display_label")
                or cat.get("resume_display_label")
                or cat.get("category")
                or ""
            ).strip()
            if not label:
                continue
            key = label.lower()
            if key in out:
                continue
            out.setdefault(key, []).append((0.5, path.path_index, dict(cat)))
    return out


def _category_graph_skill_node_ids(cat: dict[str, Any]) -> list[str]:
    out: set[str] = set()
    for sid in cat.get("graph_skill_node_ids") or []:
        if str(sid).strip():
            out.add(str(sid).strip())
    for term in cat.get("terms") or []:
        if not isinstance(term, dict):
            continue
        for sid in term.get("graph_skill_node_ids") or term.get("source_skill_ids") or []:
            if str(sid).strip():
                out.add(str(sid).strip())
    return sorted(out)


def _category_source_fact_ids(cat: dict[str, Any]) -> list[str]:
    out: set[str] = set()
    for fid in cat.get("source_fact_ids") or []:
        if str(fid).strip():
            out.add(str(fid).strip())
    for term in cat.get("terms") or []:
        if not isinstance(term, dict):
            continue
        for fid in term.get("source_fact_ids") or []:
            if str(fid).strip():
                out.add(str(fid).strip())
        fid = str(term.get("source_fact_id") or "").strip()
        if fid:
            out.add(fid)
    return sorted(out)


def _selection_score_maps(
    selections: list[dict[str, Any]],
) -> tuple[dict[tuple[str, int], float], dict[str, float], set[tuple[str, int]]]:
    by_label_path: dict[tuple[str, int], float] = {}
    best_by_label: dict[str, float] = {}
    failed_rows: set[tuple[str, int]] = set()
    for sel in selections:
        if not isinstance(sel, dict):
            continue
        label = str(sel.get("category_label") or "").strip().lower()
        if not label:
            continue
        try:
            path_idx = int(sel.get("path_index", 0))
        except (TypeError, ValueError):
            path_idx = 0
        score = _selection_row_score(sel)
        by_label_path[(label, path_idx)] = score
        best_by_label[label] = max(best_by_label.get(label, 0.0), score)
        if not _selection_row_passes(sel):
            failed_rows.add((label, path_idx))
    return by_label_path, best_by_label, failed_rows


def _all_category_candidate_rows(paths: list[Any]) -> list[tuple[str, int, dict[str, Any]]]:
    rows: list[tuple[str, int, dict[str, Any]]] = []
    for path in paths:
        parsed = getattr(path, "parsed", None)
        if not isinstance(parsed, dict):
            continue
        try:
            path_idx = int(getattr(path, "path_index", 0))
        except (TypeError, ValueError):
            path_idx = 0
        for cat in parsed.get("competencies") or parsed.get("categories") or []:
            if not isinstance(cat, dict):
                continue
            label = str(
                cat.get("category_label")
                or cat.get("display_label")
                or cat.get("resume_display_label")
                or cat.get("category")
                or ""
            ).strip()
            if not label:
                continue
            rows.append((label, path_idx, dict(cat)))
    return rows


def build_competencies_rejected_neighbor_audit(
    paths: list[Any],
    selections: list[dict[str, Any]],
    merged_parsed: dict[str, Any],
    source_path_by_slot: dict[str, int],
    *,
    min_score_threshold: float | None = None,
    allowed_fact_ids: set[str] | None = None,
    allowed_skill_ids: set[str] | None = None,
    resume_support_blob_lower: str = "",
) -> dict[str, Any]:
    """Record selected and rejected graph-pool candidates for auditability."""
    threshold = (
        min_score_threshold
        if min_score_threshold is not None
        else min_competencies_selection_score()
    )
    allowed_fact_ids = allowed_fact_ids or set()
    allowed_skill_ids = allowed_skill_ids or set()
    selected_categories = merged_parsed.get("competencies") or merged_parsed.get("categories") or []
    selected_labels = {
        str(cat.get("category_label") or "").strip().lower()
        for cat in selected_categories
        if isinstance(cat, dict) and str(cat.get("category_label") or "").strip()
    }
    source_map = {str(k).strip().lower(): int(v) for k, v in (source_path_by_slot or {}).items()}
    score_by_label_path, score_by_label, failed_rows = _selection_score_maps(selections)

    selected_neighbors: list[dict[str, Any]] = []
    rejected_neighbors: list[dict[str, Any]] = []
    candidate_label_keys: set[str] = set()

    for label, path_idx, cat in _all_category_candidate_rows(paths):
        label_key = label.lower()
        candidate_label_keys.add(label_key)
        selector_score = score_by_label_path.get((label_key, path_idx))
        heuristic_score = _heuristic_category_score(
            cat,
            allowed_fact_ids=allowed_fact_ids,
            allowed_skill_ids=allowed_skill_ids,
            resume_support_blob_lower=resume_support_blob_lower,
        )
        effective_score = selector_score if selector_score is not None else heuristic_score
        row = {
            "category_label": label,
            "path_index": path_idx,
            "selector_score": round(float(selector_score), 4) if selector_score is not None else None,
            "best_selector_score_for_label": (
                round(float(score_by_label[label_key]), 4) if label_key in score_by_label else None
            ),
            "heuristic_support_score": round(float(heuristic_score), 4),
            "effective_score": round(float(effective_score), 4),
            "source_fact_ids": _category_source_fact_ids(cat),
            "graph_skill_node_ids": _category_graph_skill_node_ids(cat),
            "competency_bundle_id": str(cat.get("competency_bundle_id") or "").strip(),
        }
        selected_path_idx = source_map.get(label_key)
        if label_key in selected_labels and selected_path_idx == path_idx:
            selected_neighbors.append({**row, "selection_status": "selected"})
            continue
        if (label_key, path_idx) in failed_rows:
            reason = "selector_marked_failed"
        elif selector_score is not None and selector_score < threshold:
            reason = "below_selector_threshold"
        elif heuristic_score < MIN_COMPETENCIES_SUPPORTED_TERM_RATIO and allowed_fact_ids:
            reason = "unsupported_by_allowed_graph_evidence"
        elif label_key in selected_labels:
            reason = "duplicate_label_lower_score"
        elif score_by_label and label_key not in score_by_label:
            reason = "not_selected_by_model"
        else:
            reason = "overflow_after_adaptive_emit"
        rejected_neighbors.append(
            {
                **row,
                "selection_status": "rejected",
                "rejection_reason": reason,
            }
        )

    selected_count = len(selected_labels)
    candidate_label_count = len(candidate_label_keys)
    rejected_count = len(rejected_neighbors)
    audit_status = (
        "present"
        if candidate_label_count > selected_count and rejected_count > 0
        else "thin_candidate_pool"
    )
    return {
        "schema_version": "competencies_rejected_neighbor_audit_v1",
        "audit_status": audit_status,
        "min_score_threshold": threshold,
        "candidate_variant_count": len(selected_neighbors) + rejected_count,
        "candidate_label_count": candidate_label_count,
        "selected_count": selected_count,
        "rejected_neighbor_count": rejected_count,
        "selected_labels": sorted(selected_labels),
        "selected_neighbors": selected_neighbors,
        "rejected_neighbors": rejected_neighbors,
    }


def _adaptive_emit_count(
    ranked: list[tuple[float, str, int, dict[str, Any]]],
    *,
    min_count: int = COMPETENCIES_MIN_CATEGORY_COUNT,
    max_count: int = COMPETENCIES_MAX_CATEGORY_COUNT,
    high_signal_threshold: float | None = None,
) -> int:
    if not ranked:
        return 0
    threshold = (
        high_signal_threshold
        if high_signal_threshold is not None
        else high_signal_competencies_selection_score()
    )
    high_signal = sum(1 for score, *_ in ranked if float(score) >= threshold)
    target = max(min_count, high_signal)
    return min(max_count, min(len(ranked), target))


def merge_competencies_graph_pool_top_eight(
    paths: list[Any],
    selections: list[dict[str, Any]],
    *,
    base_parsed: dict[str, Any] | None = None,
    min_score_threshold: float | None = None,
    allowed_fact_ids: set[str] | None = None,
    allowed_skill_ids: set[str] | None = None,
    resume_support_blob_lower: str = "",
) -> tuple[dict[str, Any], dict[str, int]]:
    """Merge pool into adaptive 6-8 categories (top scores, graph-reality filtered)."""
    threshold = (
        min_score_threshold
        if min_score_threshold is not None
        else min_competencies_selection_score()
    )
    allowed_fact_ids = allowed_fact_ids or set()
    allowed_skill_ids = allowed_skill_ids or set()
    anchor = dict(base_parsed or (paths[0].parsed if paths else {}) or {})

    candidates = _collect_category_candidates(paths, selections)
    ranked: list[tuple[float, str, int, dict[str, Any]]] = []
    for key, variants in candidates.items():
        best_score = max((v[0] for v in variants), default=0.0)
        best = max(variants, key=lambda v: v[0])
        ranked.append((best_score, key, best[1], best[2]))

    passing_sel = [
        s
        for s in selections
        if isinstance(s, dict)
        and _selection_row_passes(s)
        and _selection_row_score(s) >= threshold
    ]
    if passing_sel:
        ranked = []
        seen_bundle_ids: set[str] = set()
        seen_taxonomy_ids: set[str] = set()
        from apps_rg.runtime.sections.competency_capability_evidence import (
            visible_graph_surface_taxonomy_for_bundle,
        )

        for sel in sorted(passing_sel, key=_selection_row_score, reverse=True):
            label = str(sel.get("category_label") or "").strip()
            if not label:
                continue
            path_idx = int(sel.get("path_index", 0))
            path = next((p for p in paths if p.path_index == path_idx), paths[0] if paths else None)
            cat = _category_by_label(path.parsed or {}, label) if path and path.parsed else None
            if cat is None:
                continue
            bundle_id = str(cat.get("competency_bundle_id") or "").strip()
            taxonomy_id, _ = visible_graph_surface_taxonomy_for_bundle(bundle_id)
            if (
                not bundle_id
                or not taxonomy_id
                or bundle_id in seen_bundle_ids
                or taxonomy_id in seen_taxonomy_ids
            ):
                continue
            seen_bundle_ids.add(bundle_id)
            seen_taxonomy_ids.add(taxonomy_id)
            ranked.append((_selection_row_score(sel), label.lower(), path_idx, dict(cat)))
        ranked.sort(key=lambda t: (-t[0], t[1]))
    else:
        for key, variants in candidates.items():
            best = max(variants, key=lambda v: v[0])
            h_score = _heuristic_category_score(
                best[2],
                allowed_fact_ids=allowed_fact_ids,
                allowed_skill_ids=allowed_skill_ids,
                resume_support_blob_lower=resume_support_blob_lower,
            )
            ranked.append((max(best[0], h_score), key, best[1], best[2]))
        ranked.sort(key=lambda t: (-t[0], t[1]))

    # In provider-backed selection, the selector's distinct passing rows are
    # the requested 6-8 shape.  Recomputing that count from the number of
    # high-score rows silently truncated valid lower-scoring family coverage
    # (notably Retrieval/Context) back to six.
    target_count = (
        min(COMPETENCIES_MAX_CATEGORY_COUNT, len(ranked))
        if passing_sel
        else _adaptive_emit_count(ranked)
    )
    comps_out: list[dict[str, Any]] = []
    source_map: dict[str, int] = {}
    for score, key, path_idx, cat in ranked:
        if len(comps_out) >= target_count:
            break
        if score < threshold and passing_sel:
            continue
        h_score = _heuristic_category_score(
            cat,
            allowed_fact_ids=allowed_fact_ids,
            allowed_skill_ids=allowed_skill_ids,
            resume_support_blob_lower=resume_support_blob_lower,
        )
        if h_score < MIN_COMPETENCIES_SUPPORTED_TERM_RATIO and allowed_fact_ids:
            continue
        label = str(
            cat.get("category_label")
            or cat.get("display_label")
            or cat.get("resume_display_label")
            or cat.get("category")
            or ""
        ).strip()
        cat_out = dict(cat)
        cat_out.setdefault("selection_score", round(float(score), 4))
        comps_out.append(cat_out)
        source_map[label.lower()] = path_idx

    fallback_target = target_count if passing_sel else min(
        target_count, COMPETENCIES_MIN_CATEGORY_COUNT
    )
    if len(comps_out) < fallback_target:
        for _score, key, path_idx, cat in ranked:
            if len(comps_out) >= fallback_target:
                break
            label = str(
                cat.get("category_label")
                or cat.get("display_label")
                or cat.get("resume_display_label")
                or cat.get("category")
                or ""
            ).strip()
            if not label or label.lower() in source_map:
                continue
            cat_out = dict(cat)
            cat_out.setdefault("selection_score", round(float(_score), 4))
            comps_out.append(cat_out)
            source_map[label.lower()] = path_idx

    merged = dict(anchor)
    selected_categories = comps_out[:target_count]
    # ``base_parsed`` is an anchor path and can carry its own canonical V3
    # ``categories`` surface.  The selector merge previously replaced only the
    # legacy ``competencies`` mirror, leaving those stale anchor categories in
    # place.  The next V3 synchronization correctly treats ``categories`` as
    # canonical and therefore erased the selector-authorized bundle/taxonomy
    # identities.  Commit the selector result atomically to both mirrors.
    merged["categories"] = copy.deepcopy(selected_categories)
    merged["competencies"] = copy.deepcopy(selected_categories)
    merged["adaptive_category_policy"] = {
        "min_category_count": COMPETENCIES_MIN_CATEGORY_COUNT,
        "max_category_count": COMPETENCIES_MAX_CATEGORY_COUNT,
        "candidate_category_count": COMPETENCIES_CANDIDATE_CATEGORY_COUNT,
        "selected_category_count": len(selected_categories),
        "high_signal_selection_score": high_signal_competencies_selection_score(),
    }
    if paths and paths[0].parsed and paths[0].parsed.get("claim_ledger"):
        merged["claim_ledger"] = list(paths[0].parsed.get("claim_ledger") or [])
    return merged, source_map


def evaluate_competencies_selection_quality(
    *,
    selections: list[dict[str, Any]],
    merged_parsed: dict[str, Any],
    min_score: float | None = None,
) -> CompetenciesSelectionGate:
    threshold = min_score if min_score is not None else min_competencies_selection_score()
    min_final = COMPETENCIES_MIN_CATEGORY_COUNT
    max_final = COMPETENCIES_MAX_CATEGORY_COUNT
    comps = merged_parsed.get("competencies") or merged_parsed.get("categories") or []
    comps_n = len(comps) if isinstance(comps, list) else 0

    by_label: dict[str, dict[str, Any]] = {}
    for row in selections:
        if isinstance(row, dict):
            lab = str(row.get("category_label") or "").strip().lower()
            if lab:
                by_label[lab] = row

    passing: list[str] = []
    below: list[str] = []
    missing: list[str] = []

    merged_labels = {
        str(c.get("category_label") or "").strip().lower()
        for c in comps
        if isinstance(c, dict) and str(c.get("category_label") or "").strip()
    }

    from collections import Counter
    from apps_rg.runtime.sections.competency_capability_evidence import (
        visible_graph_surface_taxonomy_for_bundle,
    )

    merged_rows = [c for c in comps if isinstance(c, dict)]
    bundle_ids = [str(c.get("competency_bundle_id") or "").strip() for c in merged_rows]
    taxonomy_ids = [
        visible_graph_surface_taxonomy_for_bundle(bundle_id)[0] if bundle_id else ""
        for bundle_id in bundle_ids
    ]
    bundle_ids_missing = tuple(
        str(c.get("category_label") or "") for c, bid in zip(merged_rows, bundle_ids, strict=True) if not bid
    )
    taxonomy_ids_missing = tuple(
        str(c.get("category_label") or "")
        for c, taxonomy_id in zip(merged_rows, taxonomy_ids, strict=True)
        if not taxonomy_id
    )
    duplicate_bundle_ids = tuple(
        sorted(bundle_id for bundle_id, count in Counter(bundle_ids).items() if bundle_id and count > 1)
    )
    duplicate_taxonomy_ids = tuple(
        sorted(taxonomy_id for taxonomy_id, count in Counter(taxonomy_ids).items() if taxonomy_id and count > 1)
    )

    # The visible-surface enrichment stage replaces each selected category's
    # provider terms with the governed anchors for its single bundle. Text in
    # one category therefore cannot stand in for a different bundle family.
    # The old union of text matches and bundle identities let six rows claim
    # all eight families, only to lose two families after enrichment. Require
    # the exact governed bundle for every family at the selector boundary.
    covered_families = {
        family
        for family, required_bundle_id in REQUIRED_COMPETENCY_BUNDLE_BY_FAMILY.items()
        if required_bundle_id in bundle_ids
    }
    missing_capability_families = tuple(
        family
        for family in REQUIRED_COMPETENCY_BUNDLE_BY_FAMILY
        if family not in covered_families
    )

    for lab in sorted(merged_labels):
        sel = by_label.get(lab)
        if sel is None or not _selection_row_passes(sel):
            missing.append(lab)
            continue
        score = _selection_row_score(sel)
        if score < threshold:
            below.append(lab)
        else:
            passing.append(lab)

    identity_ok = not (
        bundle_ids_missing
        or taxonomy_ids_missing
        or duplicate_bundle_ids
        or duplicate_taxonomy_ids
    )
    ok = (
        min_final <= comps_n <= max_final
        and len(passing) == comps_n
        and not below
        and not missing
        and identity_ok
        and not missing_capability_families
    )
    return CompetenciesSelectionGate(
        ok=ok,
        section_lane="competencies",
        final_category_count=comps_n,
        min_category_count=min_final,
        max_category_count=max_final,
        min_score_threshold=threshold,
        categories_passing=tuple(passing),
        categories_below_threshold=tuple(below),
        categories_missing=tuple(missing),
        categories_in_merged=comps_n,
        bundle_ids_missing=bundle_ids_missing,
        duplicate_bundle_ids=duplicate_bundle_ids,
        taxonomy_category_ids_missing=taxonomy_ids_missing,
        duplicate_taxonomy_category_ids=duplicate_taxonomy_ids,
        missing_capability_families=missing_capability_families,
    )


def write_competencies_regen_artifact(artifact_dir: Path, doc: dict[str, Any]) -> None:
    path = artifact_dir / "competencies_graph_pool_regen.json"
    prior: list[dict[str, Any]] = []
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded.get("rounds"), list):
                prior = loaded["rounds"]
        except (json.JSONDecodeError, OSError):
            prior = []
    path.write_text(
        json.dumps({"rounds": prior + [doc]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "COMPETENCIES_CANDIDATE_CATEGORY_COUNT",
    "COMPETENCIES_FINAL_CATEGORY_COUNT",
    "COMPETENCIES_MAX_CATEGORY_COUNT",
    "COMPETENCIES_MAX_SC_PATH_COUNT",
    "COMPETENCIES_MIN_CATEGORY_COUNT",
    "COMPETENCIES_REGEN_EXTRA_PATHS",
    "REQUIRED_COMPETENCY_BUNDLE_BY_FAMILY",
    "COMPETENCIES_SC_PATH_COUNT",
    "DEFAULT_COMPETENCIES_HIGH_SIGNAL_SELECTION_SCORE",
    "DEFAULT_COMPETENCIES_INITIAL_SC_PATH_COUNT",
    "CompetenciesSelectionGate",
    "build_competencies_rejected_neighbor_audit",
    "build_competencies_targeting_context",
    "competencies_candidate_support_score",
    "competencies_initial_sc_path_count",
    "competencies_max_sc_path_count",
    "competencies_regen_extra_path_count",
    "e2e_closeout_mode_active",
    "evaluate_competencies_selection_quality",
    "high_signal_competencies_selection_score",
    "is_competencies_pool_generation",
    "max_competencies_regen_rounds",
    "merge_competencies_graph_pool_top_eight",
    "min_competencies_selection_score",
    "write_competencies_regen_artifact",
]
