"""Role-episode bullet normalization, density repair, and graph rendering helpers."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.reasoning.employment_bullet_pool import FINAL_BULLET_COUNT
from apps_rg.runtime.validators.bullet_quality_floor_x2 import check_experience_bullet_evidence_density
from .lane_config import (
    ROLE_EPISODE_FINAL_BULLET_COUNT,
    ROLE_EPISODE_GRAPH_BULLET_RENDERER_VERSION,
    RoleEpisodeLaneConfig,
    _ROLE_EPISODE_EVIDENCE_DENSITY_REPAIRS,
    _bullet_sentence,
    _compact_text,
    _facts_from_plan,
    _normalize_source_ids,
    _sentence,
)
from .narrative_binding import _strip_targeting_only_experience_claims

def _normalize_bullets(
    parsed: dict[str, Any],
    *,
    cfg: RoleEpisodeLaneConfig,
    allowed: list[str],
    allow_prose_mutation: bool = True,
) -> list[dict[str, Any]]:
    rows = parsed.get("bullets") if isinstance(parsed, dict) else None
    expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT)
    count = expected_bullet_count if expected_bullet_count > 0 else (len(rows) if isinstance(rows, list) else 0)
    out: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for idx, row in enumerate(rows[:count]):
            if not isinstance(row, dict):
                continue
            raw_txt = str(row.get("bullet_text") or row.get("text") or "")
            if allow_prose_mutation:
                text, _hits = _strip_targeting_only_experience_claims(raw_txt, allow_prose_mutation=True)
                from apps_rg.runtime.sections.cross_section_signal_guards import (
                    rewrite_generic_consulting_phrases,
                )

                text = rewrite_generic_consulting_phrases(text)
            else:
                text = raw_txt
            text = _bullet_sentence(text)
            if not text:
                continue
            source_fact_ids = _normalize_source_ids(
                row.get("source_fact_ids"), allowed, idx
            )
            expected_ids = {
                f"{cfg.bullet_prefix}_{slot + 1:03d}"
                for slot in range(count)
            }
            source_bound_ids = [
                fact_id for fact_id in source_fact_ids if fact_id in expected_ids
            ]
            canonical_id = (
                source_bound_ids[0]
                if len(set(source_bound_ids)) == 1
                else f"{cfg.bullet_prefix}_{idx + 1:03d}"
            )
            out.append(
                {
                    # An exact proof-fact id is the slot authority. Positional
                    # fallback remains for rows without a usable source id.
                    # Position-only normalization mislabeled out-of-order EY
                    # rows and created false cross-bullet duplicates.
                    "bullet_id": canonical_id,
                    "bullet_text": text,
                    "source_fact_ids": source_fact_ids,
                }
            )
    return out


def _repair_role_episode_bullet_evidence_density(
    bullets: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Complete a thin model bullet only with an approved graph-root outcome.

    This is deliberately a repair, not a second renderer.  The model still
    chooses the three graph-bound roots; a repair may replace only a selected
    row whose current prose fails the shared action/detail/outcome quality
    floor or omits the allocated numeric proof on ``reb_slalom_governed_runtime_scaling``.
    """
    fact_by_id = {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if isinstance(fact, dict) and str(fact.get("fact_id") or "").strip()
    }
    repaired: list[dict[str, Any]] = []
    repairs: list[dict[str, str]] = []
    for row in bullets:
        out = dict(row)
        text = str(out.get("bullet_text") or "").strip()
        source_ids = [str(fid).strip() for fid in (out.get("source_fact_ids") or [])]
        fact = next((fact_by_id.get(fid) for fid in source_ids if fact_by_id.get(fid)), None)
        root_id = str((fact or {}).get("role_episode_bundle_id") or "").strip()
        replacement = _ROLE_EPISODE_EVIDENCE_DENSITY_REPAIRS.get(root_id)
        density = check_experience_bullet_evidence_density(
            str(out.get("bullet_id") or ""), text
        )
        alloc_metric = str((fact or {}).get("metric_text") or (fact or {}).get("metric_outcome_id") or "").strip()
        requires_100pct = not alloc_metric or "100%" in alloc_metric or "conformance_pct" in alloc_metric
        if replacement and not density.passed:
            out["bullet_text"] = replacement
            repairs.append(
                {
                    "bullet_id": str(out.get("bullet_id") or ""),
                    "role_episode_bundle_id": root_id,
                    "reason": "graph_bound_evidence_density_completion",
                }
            )
        elif root_id == "reb_slalom_governed_runtime_scaling" and requires_100pct:
            pct_matches = list(re.finditer(r"\b100(?:\s*%|\s+percent\b)", text, re.IGNORECASE))
            if not pct_matches:
                if density.passed and len(text.split()) >= 14:
                    base_txt = text.rstrip(".!?").strip()
                    out["bullet_text"] = f"{base_txt}, enforcing 100% conformance to enterprise governance controls."
                else:
                    out["bullet_text"] = _ROLE_EPISODE_EVIDENCE_DENSITY_REPAIRS["reb_slalom_governed_runtime_scaling"]
                repairs.append(
                    {
                        "bullet_id": str(out.get("bullet_id") or ""),
                        "role_episode_bundle_id": root_id,
                        "reason": "allocated_metric_outcome_100pct_completion",
                    }
                )
            elif len(pct_matches) > 1:
                deduped = re.sub(
                    r",\s*(?:enforcing|achieving|delivering|sustaining)\s+100(?:\s*%|\s+percent\b)[^.]*\.$",
                    ".",
                    text,
                    flags=re.IGNORECASE,
                )
                if deduped != text and len(re.findall(r"\b100(?:\s*%|\s+percent\b)", deduped, re.IGNORECASE)) == 1:
                    out["bullet_text"] = deduped
        repaired.append(out)
    return repaired, repairs


def _source_fact_ids_from_bullets(bullets: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in bullets:
        if not isinstance(row, dict):
            continue
        for raw in row.get("source_fact_ids") or []:
            fid = str(raw or "").strip()
            if fid and fid not in seen:
                seen.add(fid)
                out.append(fid)
    return out


def _deterministic_graph_bullet_render(
    *,
    cfg: RoleEpisodeLaneConfig,
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    if not cfg.allow_deterministic_graph_render or not allowed_set:
        return out
    for fact in facts:
        fid = str(fact.get("fact_id") or fact.get("candidate_fact_id") or "")
        if fid not in allowed_set:
            continue
        text = _bullet_sentence(str(fact.get("claim_text") or fact.get("text") or ""))
        if not text:
            continue
        idx = len(out)
        out.append(
            {
                "bullet_id": f"{cfg.bullet_prefix}_{idx + 1:03d}",
                "bullet_text": text,
                "source_fact_ids": [fid],
            }
        )
        if len(out) >= 3:
            break
    return out


def _fact_id_from_row(fact: dict[str, Any]) -> str:
    return str(fact.get("fact_id") or fact.get("candidate_fact_id") or "").strip()

