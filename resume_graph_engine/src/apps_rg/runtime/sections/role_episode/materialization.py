"""Model output JSON parsing, pool normalization, and proof-authorized materialization."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    FINAL_BULLET_COUNT,
    REQUIRED_BULLET_IDS,
    evaluate_employment_selection_quality,
    is_employment_bullet_lane,
)
from apps_rg.runtime.sections.lane_artifact_io import write_json
from ._parent import parent_attr
from .bullet_normalization import (
    _deterministic_graph_bullet_render,
    _normalize_bullets,
    _repair_role_episode_bullet_evidence_density,
    _source_fact_ids_from_bullets,
)
from .lane_config import (
    ROLE_EPISODE_FINAL_BULLET_COUNT,
    ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION,
    RoleEpisodeLaneConfig,
    _compact_text,
    _facts_from_plan,
    _normalize_source_ids,
    _sentence,
)
from .narrative_binding import (
    _narrative_source_ids_for_claim,
    _parsed_claim_ledger_source_ids_for_narrative,
    _strip_targeting_only_experience_claims,
)
from .proof_selection import (
    _ordered_ids_from_bullets,
    _ordered_ids_from_bullets_with_contract,
    _proof_authorized_bullets_from_selection,
    _proof_authorized_bullets_from_selection_with_contract,
    _proof_authorized_narrative_from_selection,
)

def _llm_generation_status(
    *,
    provider_runtime_generation_status: str,
    parsed: dict[str, Any] | None,
    parse_error: str,
    model_bullets: list[dict[str, Any]],
) -> str:
    if provider_runtime_generation_status != "REAL_LLM":
        return "not_run"
    if parse_error == "empty_model_output":
        return "empty_output"
    if parsed is None or not model_bullets:
        return "invalid_output"
    return "usable_output"


def _materialize_bullet_generation(
    *,
    cfg: RoleEpisodeLaneConfig,
    parsed: dict[str, Any] | None,
    parse_error: str,
    provider_runtime_generation_status: str,
    facts: list[dict[str, Any]],
    allowed: list[str],
    graph_packet_digest: str,
    allow_prose_mutation: bool | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    effective_allow_mutation = (
        provider_runtime_generation_status != "REAL_LLM"
        if allow_prose_mutation is None
        else bool(allow_prose_mutation)
    )
    model_bullets = _normalize_bullets(
        parsed or {},
        cfg=cfg,
        allowed=allowed,
        allow_prose_mutation=effective_allow_mutation,
    )
    llm_status = _llm_generation_status(
        provider_runtime_generation_status=provider_runtime_generation_status,
        parsed=parsed,
        parse_error=parse_error,
        model_bullets=model_bullets,
    )
    if model_bullets:
        bullets, final_contract = _proof_authorized_bullets_from_selection_with_contract(
            cfg=cfg,
            model_bullets=model_bullets,
            facts=facts,
            allowed=allowed,
        )
        final_ok = bool(final_contract.get("final_materialized_acceptance_ok"))
        model_surface_used = bool(final_contract.get("model_surface_bullet_ids"))
        generation_method = (
            "llm_selected_graph_bound_surface"
            if final_ok and model_surface_used
            else "llm_selected_proof_render"
            if final_ok
            else "model_output_invalid"
        )
        llm_output_used = bool(final_ok and model_surface_used)
        renderer_version = (
            "model_selected_graph_bound_surface.v1"
            if final_ok and model_surface_used
            else ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION
            if final_ok
            else ""
        )
        if effective_allow_mutation:
            bullets, density_repairs = _repair_role_episode_bullet_evidence_density(
                bullets,
                facts=facts,
            )
        else:
            density_repairs = []
    else:
        bullets = []
        density_repairs = []
        expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT)
        is_zero_expected = (expected_bullet_count == 0)
        final_contract = {
            "schema_version": "role_episode_final_materialized_selection_contract.v1",
            "expected_bullet_count": expected_bullet_count,
            "model_bullet_count": 0,
            "selected_source_fact_ids": [],
            "selected_unique_source_fact_count": 0,
            "duplicate_source_fact_ids_ignored": [],
            "rejected_source_fact_ids": [],
            "deterministic_reselect_source_fact_ids": [],
            "deterministic_reselect_applied": False,
            "rendered_bullet_count": 0,
            "rendered_source_fact_ids": [],
            "final_materialized_acceptance_ok": is_zero_expected,
        }
        generation_method = (
            "zero_bullet_consolidated"
            if is_zero_expected
            else "model_output_invalid"
            if provider_runtime_generation_status == "REAL_LLM"
            else "blocked"
        )
        llm_output_used = False
        renderer_version = ""

    source_fact_ids = _source_fact_ids_from_bullets(bullets)
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    receipt = {
        "generation_method": generation_method,
        "llm_generation_status": llm_status,
        "llm_output_used": llm_output_used,
        "llm_selection_used": bool(model_bullets and final_contract.get("final_materialized_acceptance_ok")),
        "model_display_text_discarded": bool(
            model_bullets and not final_contract.get("model_surface_bullet_ids")
        ),
        "display_text_authority": (
            "model_selected_graph_bound_surface"
            if final_contract.get("final_materialized_acceptance_ok")
            and final_contract.get("model_surface_bullet_ids")
            else "selected_fact_plan_claim_text"
            if final_contract.get("final_materialized_acceptance_ok")
            else ""
        ),
        "evidence_authority": "augmented_skills_graph",
        "source_fact_ids": source_fact_ids,
        "graph_packet_digest": str(graph_packet_digest or ""),
        "renderer_version": renderer_version,
        "lane_contract_allows_deterministic_graph_render": bool(
            cfg.allow_deterministic_graph_render
        ),
        "allowed_graph_packet_fact_count": len(allowed_set),
        "rendered_source_fact_ids_within_allowed_packet": set(source_fact_ids).issubset(allowed_set),
        "graph_bound_evidence_density_repairs": density_repairs,
        "final_materialized_selection_contract": final_contract,
        "final_materialized_acceptance_ok": bool(
            final_contract.get("final_materialized_acceptance_ok")
            and set(source_fact_ids).issubset(allowed_set)
        ),
    }
    return bullets, receipt


def _reconcile_final_materialized_selection_gate(
    *,
    artifact_dir: Path,
    section_id: str,
    bullets: list[dict[str, Any]],
    generation_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Re-evaluate selector quality against the bullets that actually ship.

    The selector gate is initially computed over the model-merged pool.  Some
    graph-governed lanes then rehydrate the selected slots from frozen proof,
    which can correct duplicate/mis-bound source ids.  X1D must grade that
    final materialized object, while retaining the producer gate as audit
    evidence; carrying the stale pre-materialization gate produced a false EY
    selector failure even though all three Claude scores and final source ids
    passed.
    """

    required = REQUIRED_BULLET_IDS.get(str(section_id or "").strip().lower())
    if not required and bullets:
        required = tuple(
            str(b.get("bullet_id") or "").strip()
            for b in bullets
            if isinstance(b, Mapping) and str(b.get("bullet_id") or "").strip()
        )
    selection_path = artifact_dir / "bullet_pool_selection.json"
    if not required or not selection_path.is_file():
        return None
    try:
        selection_doc = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    selections = [
        dict(row)
        for row in selection_doc.get("selections") or []
        if isinstance(row, Mapping)
    ] if isinstance(selection_doc, Mapping) else []
    if not selections:
        return None
    final_gate = evaluate_employment_selection_quality(
        section_lane=section_id,
        required_bullet_ids=required,
        selections=selections,
        merged_parsed={"bullets": bullets},
    ).to_dict()
    if "producer_selection_gate" not in generation_meta:
        generation_meta["producer_selection_gate"] = dict(generation_meta.get("selection_gate") or {})
    generation_meta["final_materialized_selection_gate"] = final_gate
    generation_meta["selection_gate"] = final_gate
    return final_gate


def _normalize_role_episode_bullet_pool_parsed(
    parsed: dict[str, Any],
    *,
    cfg: RoleEpisodeLaneConfig,
    allowed: list[str],
    allow_prose_mutation: bool = True,
) -> dict[str, Any]:
    """Normalize one SC path into the employment-pool shape for InsurTech/EY bullets."""
    out = dict(parsed or {})
    bullets = _normalize_bullets(
        out,
        cfg=cfg,
        allowed=allowed,
        allow_prose_mutation=allow_prose_mutation,
    )
    out["bullets"] = bullets
    out["claim_ledger"] = _claim_ledger_from_bullets(bullets)
    out.setdefault("jd_alignment", {"targeting_only": True, "jd_used_as_proof": False})
    return out


def _claim_ledger_from_bullets(bullets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_text": str(row.get("bullet_text") or ""),
            "source_fact_ids": list(row.get("source_fact_ids") or []),
        }
        for row in bullets
        if row.get("bullet_text")
    ]


def _display_text(l2: dict[str, Any], cfg: RoleEpisodeLaneConfig) -> str:
    if cfg.is_bullet_lane:
        return "\n".join(f"- {b['bullet_text']}" for b in l2.get("bullets") or [])
    return str(l2.get("narrative_sentence") or "")


def _parse_json_object(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    if not text:
        return None, "empty_model_output"
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}"
    if not isinstance(loaded, dict):
        return None, "json_root_not_object"
    return loaded, ""

