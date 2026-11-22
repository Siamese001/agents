"""Proof-authorized fact surface binding, contract ordering, and selection reconciliation."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    MODEL_SURFACE_NON_ANCHOR_TOKENS,
    PROOF_FACT_COMPOSITION_CONNECTIVES,
    proof_fact_surface_tokens,
)
from apps_rg.runtime.reasoning.employment_bullet_pool import FINAL_BULLET_COUNT
from apps_rg.runtime.sections.lane_artifact_io import write_json
from apps_rg.runtime.validators.narrative_quality_x2 import repair_narrative_bullet_echo_from_graph
from ._parent import parent_attr
from .bullet_normalization import _fact_id_from_row, _normalize_bullets, _source_fact_ids_from_bullets
from .lane_config import (
    ROLE_EPISODE_FINAL_BULLET_COUNT,
    ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
    ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION,
    RoleEpisodeLaneConfig,
    _bullet_sentence,
    _compact_text,
    _facts_from_plan,
    _normalize_source_ids,
    _sentence,
)
from .narrative_binding import _TARGETING_ONLY_EXPERIENCE_MARKERS, _narrative_from_parsed

_PROOF_FACT_COMPOSITION_CONNECTIVES = PROOF_FACT_COMPOSITION_CONNECTIVES
_MODEL_SURFACE_NON_ANCHOR_TOKENS = MODEL_SURFACE_NON_ANCHOR_TOKENS
_proof_fact_surface_tokens = proof_fact_surface_tokens

_PROOF_FACT_SURFACE_COMPOSITIONS: Mapping[tuple[str, str], str] = {
    # The frozen allocation has two distinct leaf skills under the same
    # migration bundle. This concise, source-vocabulary-only projection keeps
    # the legacy-modernization leaf distinguishable from the generic AWS
    # modernization bullet while retaining its exact fact and graph path.
    (
        "bul_insurtech_003",
        "skill_sr_insurtech_legacy_cloud_modernization",
    ): "Led legacy cloud modernization for AWS insurance platforms",
}

def _proof_fact_composition_is_bound(phrase: str, fact: Mapping[str, Any]) -> bool:
    source_tokens = _proof_fact_surface_tokens(fact)
    for token in re.findall(r"[a-z0-9]+", str(phrase or "").casefold()):
        if token in _PROOF_FACT_COMPOSITION_CONNECTIVES or token in source_tokens:
            continue
        if token.endswith("s") and token[:-1] in source_tokens:
            continue
        if f"{token}s" in source_tokens:
            continue
        return False
    return True


def _model_bullet_surface_binding(
    text: str,
    fact: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """Require a model surface to retain several meaningful graph anchors.

    The model may improve readable phrasing, but it cannot turn an approved
    source id into an ungrounded target-role claim.  A rejected model surface
    is rendered from the graph's exact claim text instead.
    """
    source_tokens = {
        token
        for token in _proof_fact_surface_tokens(fact)
        if len(token) > 2 and token not in _MODEL_SURFACE_NON_ANCHOR_TOKENS
    }
    text_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", str(text or "").casefold())
        if len(token) > 2 and token not in _MODEL_SURFACE_NON_ANCHOR_TOKENS
    }
    anchors = sorted(source_tokens & text_tokens)
    required_anchor_count = min(3, len(source_tokens))
    return len(anchors) >= required_anchor_count, anchors


def _proof_fact_text(fact: dict[str, Any]) -> str:
    fact_id = _fact_id_from_row(fact)
    skill_ids = [str(value or "").strip() for value in fact.get("graph_skill_node_ids") or []]
    if len(skill_ids) == 1:
        composition = _PROOF_FACT_SURFACE_COMPOSITIONS.get((fact_id, skill_ids[0]))
        if composition and _proof_fact_composition_is_bound(composition, fact):
            return _bullet_sentence(composition)
    anchor = fact.get("fact_anchor") if isinstance(fact.get("fact_anchor"), Mapping) else {}
    base = str(fact.get("claim_text") or fact.get("text") or anchor.get("resolved_raw_chunk") or fact.get("raw_chunk") or "")
    return _bullet_sentence(base)


def _proof_fact_by_id(facts: list[dict[str, Any]], allowed: list[str]) -> dict[str, dict[str, Any]]:
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    out: dict[str, dict[str, Any]] = {}
    for fact in facts:
        fid = _fact_id_from_row(fact)
        if fid and fid in allowed_set and _proof_fact_text(fact):
            out[fid] = fact
    return out


def _ordered_ids_from_bullets(
    bullets: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> list[str]:
    selected, _contract = _ordered_ids_from_bullets_with_contract(
        bullets,
        facts=facts,
        allowed=allowed,
        expected_count=ROLE_EPISODE_FINAL_BULLET_COUNT,
        allow_deterministic_reselect=False,
    )
    return selected


def _ordered_ids_from_bullets_with_contract(
    bullets: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
    allowed: list[str],
    expected_count: int,
    allow_deterministic_reselect: bool,
) -> tuple[list[str], dict[str, Any]]:
    if expected_count == 0 and bullets:
        expected_count = len(bullets)
    proof_by_id = _proof_fact_by_id(facts, allowed)
    seen: set[str] = set()
    out: list[str] = []
    duplicate_source_fact_ids: list[str] = []
    rejected_source_fact_ids: list[str] = []
    for bullet in bullets:
        if not isinstance(bullet, dict):
            continue
        for raw in bullet.get("source_fact_ids") or []:
            fid = str(raw or "").strip()
            if not fid:
                continue
            if fid not in proof_by_id:
                if fid not in rejected_source_fact_ids:
                    rejected_source_fact_ids.append(fid)
                continue
            if fid in seen:
                if fid not in duplicate_source_fact_ids:
                    duplicate_source_fact_ids.append(fid)
                continue
            seen.add(fid)
            out.append(fid)
            if len(out) >= expected_count:
                break
        if len(out) >= expected_count:
            break
    deterministic_reselect_source_fact_ids: list[str] = []
    if out and len(out) < expected_count and allow_deterministic_reselect:
        for fact in facts:
            fid = _fact_id_from_row(fact)
            if fid and fid in proof_by_id and fid not in seen:
                seen.add(fid)
                out.append(fid)
                deterministic_reselect_source_fact_ids.append(fid)
                if len(out) >= expected_count:
                    break
    for fact in facts:
        if out:
            break
        fid = _fact_id_from_row(fact)
        if fid and fid in proof_by_id and fid not in seen:
            seen.add(fid)
            out.append(fid)
            if len(out) >= expected_count:
                break
    contract = {
        "schema_version": "role_episode_final_materialized_selection_contract.v1",
        "expected_bullet_count": expected_count,
        "model_bullet_count": len([b for b in bullets if isinstance(b, dict)]),
        "selected_source_fact_ids": list(out),
        "selected_unique_source_fact_count": len(set(out)),
        "duplicate_source_fact_ids_ignored": duplicate_source_fact_ids,
        "rejected_source_fact_ids": rejected_source_fact_ids,
        "deterministic_reselect_source_fact_ids": deterministic_reselect_source_fact_ids,
        "deterministic_reselect_applied": bool(deterministic_reselect_source_fact_ids),
    }
    return out, contract


def _proof_authorized_bullets_from_selection_with_contract(
    *,
    cfg: RoleEpisodeLaneConfig,
    model_bullets: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT) or len(model_bullets)
    contract: dict[str, Any] = {
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
        "final_materialized_acceptance_ok": False,
    }
    if not model_bullets:
        return [], contract
    proof_by_id = _proof_fact_by_id(facts, allowed)
    selected_ids, contract = _ordered_ids_from_bullets_with_contract(
        model_bullets,
        facts=facts,
        allowed=allowed,
        expected_count=expected_bullet_count,
        allow_deterministic_reselect=cfg.allow_deterministic_graph_render,
    )
    # When a selected source is itself a canonical role-bullet slot id, retain
    # that identity through the final deterministic render.  This makes the
    # visible bullet, claim ledger, and whole-resume allocation refer to the
    # same slot even when two source facts render to identical prose.
    expected_slot_ids = {
        f"{cfg.bullet_prefix}_{index:03d}"
        for index in range(1, expected_bullet_count + 1)
    }
    slot_bound_ordering_applied = (
        len(selected_ids) == expected_bullet_count
        and len(set(selected_ids)) == expected_bullet_count
        and set(selected_ids) == expected_slot_ids
    )
    render_ids = (
        sorted(selected_ids)
        if slot_bound_ordering_applied
        else list(selected_ids)
    )

    model_surface_by_fact_id: dict[str, dict[str, Any]] = {}
    for row in model_bullets:
        text = _bullet_sentence(str(row.get("bullet_text") or ""))
        if not text:
            continue
        for raw_source_id in row.get("source_fact_ids") or []:
            source_id = str(raw_source_id or "").strip()
            if source_id and source_id not in model_surface_by_fact_id:
                model_surface_by_fact_id[source_id] = row

    out: list[dict[str, Any]] = []
    model_surface_binding_rows: list[dict[str, Any]] = []
    model_surface_bullet_ids: list[str] = []
    proof_text_fallback_bullet_ids: list[str] = []
    for fid in render_ids:
        fact = proof_by_id.get(fid)
        if not fact:
            continue
        candidate = model_surface_by_fact_id.get(fid)
        candidate_text = _bullet_sentence(str((candidate or {}).get("bullet_text") or ""))
        candidate_bound, anchors = _model_bullet_surface_binding(candidate_text, fact)
        model_surface_binding_rows.append(
            {
                "bullet_id": fid,
                "candidate_present": candidate is not None,
                "candidate_graph_bound": candidate_bound,
                "anchor_tokens": anchors,
            }
        )
        if candidate and candidate_bound:
            text = candidate_text
            model_surface_bullet_ids.append(fid)
        else:
            text = _proof_fact_text(fact)
            proof_text_fallback_bullet_ids.append(fid)
        if not text:
            continue
        idx = len(out)
        out.append(
            {
                "bullet_id": fid if slot_bound_ordering_applied else f"{cfg.bullet_prefix}_{idx + 1:03d}",
                "bullet_text": text,
                "source_fact_ids": [fid],
            }
        )
        if len(out) >= expected_bullet_count:
            break
    rendered_source_fact_ids = _source_fact_ids_from_bullets(out)
    contract.update(
        {
            "rendered_bullet_count": len(out),
            "rendered_source_fact_ids": rendered_source_fact_ids,
            "slot_bound_ordering_applied": slot_bound_ordering_applied,
            "model_surface_binding_rows": model_surface_binding_rows,
            "model_surface_bullet_ids": model_surface_bullet_ids,
            "proof_text_fallback_bullet_ids": proof_text_fallback_bullet_ids,
            "final_materialized_acceptance_ok": (
                len(out) == expected_bullet_count
                and len(set(rendered_source_fact_ids)) == expected_bullet_count
            ),
        }
    )
    return out, contract


def _proof_authorized_bullets_from_selection(
    *,
    cfg: RoleEpisodeLaneConfig,
    model_bullets: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> list[dict[str, Any]]:
    bullets, _contract = _proof_authorized_bullets_from_selection_with_contract(
        cfg=cfg,
        model_bullets=model_bullets,
        facts=facts,
        allowed=allowed,
    )
    return bullets


def _source_ids_from_parsed_claim_ledger(parsed: dict[str, Any], allowed: list[str]) -> list[str]:
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    seen: set[str] = set()
    out: list[str] = []
    for raw in parsed.get("source_fact_ids") or []:
        fid = str(raw or "").strip()
        if fid and fid in allowed_set and fid not in seen:
            seen.add(fid)
            out.append(fid)
    for row in parsed.get("claim_ledger") or []:
        if not isinstance(row, dict):
            continue
        for raw in row.get("source_fact_ids") or []:
            fid = str(raw or "").strip()
            if fid and fid in allowed_set and fid not in seen:
                seen.add(fid)
                out.append(fid)
    return out


def _proof_authorized_narrative_from_selection(
    *,
    parsed: dict[str, Any],
    facts: list[dict[str, Any]],
    allowed: list[str],
    section_id: str = "",
    companion_bullet_texts: str = "",
    allow_prose_mutation: bool = True,
) -> tuple[str, list[str], str, bool]:
    proof_by_id = _proof_fact_by_id(facts, allowed)
    source_ids = _source_ids_from_parsed_claim_ledger(parsed, allowed)
    selected_source = "llm_source_fact_ids"
    if not source_ids:
        source_ids = [fid for fid in allowed if fid in proof_by_id][:1]
        selected_source = "selected_fact_plan_order"
    candidate_text = _narrative_from_parsed(parsed, allow_prose_mutation=allow_prose_mutation)
    if candidate_text:
        if allow_prose_mutation:
            for _t_label, _t_pat in _TARGETING_ONLY_EXPERIENCE_MARKERS:
                if _t_pat.search(candidate_text):
                    if _t_label == "frontier_ai_as_experience":
                        candidate_text = _t_pat.sub("enterprise AI", candidate_text)
                    elif _t_label == "partner_led_deployment_as_experience":
                        candidate_text = re.sub(
                            r"\bpartner-led\s+deployments\b",
                            "client deployments",
                            re.sub(
                                r"\bpartner-led\s+deployment\b",
                                "client deployment",
                                candidate_text,
                                flags=re.IGNORECASE,
                            ),
                            flags=re.IGNORECASE,
                        )
            candidate_text = repair_narrative_bullet_echo_from_graph(
                candidate_text,
                facts=facts,
                companion_bullet_texts=companion_bullet_texts,
                section_id=section_id,
            )
        for fid in source_ids:
            fact = proof_by_id.get(fid)
            if fact:
                bound, _ = _model_bullet_surface_binding(candidate_text, fact)
                if bound:
                    bound_ids = [
                        s_id
                        for s_id in source_ids
                        if s_id in proof_by_id
                        and _model_bullet_surface_binding(candidate_text, proof_by_id[s_id])[0]
                    ]
                    return candidate_text, bound_ids or [fid], selected_source, True
    for fid in source_ids:
        fact = proof_by_id.get(fid)
        if fact:
            text = _sentence(_proof_fact_text(fact))
            if text:
                if allow_prose_mutation:
                    text = repair_narrative_bullet_echo_from_graph(
                        text,
                        facts=facts,
                        companion_bullet_texts=companion_bullet_texts,
                        section_id=section_id,
                    )
                return text, [fid], selected_source, False
    return "", [], selected_source, False

