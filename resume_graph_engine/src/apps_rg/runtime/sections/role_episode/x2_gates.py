"""Role-episode X2 validation gates and X1D judge row builders."""
from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from apps_rg.runtime.reasoning.employment_bullet_pool import (
    FINAL_BULLET_COUNT,
    employment_pool_x1d_judge_rows,
    evaluate_employment_selection_quality,
    is_employment_bullet_lane,
    is_employment_pool_generation,
)
from apps_rg.runtime.sections.section_product_shape_ssot import (
    NARRATIVE_MAX_CHARS,
    NARRATIVE_MAX_WORDS,
    product_shape_gate_ids_for_lane,
)
from apps_rg.runtime.validators.bullet_line_discipline_x2 import check_bullet_single_thought
from apps_rg.runtime.validators.bullet_quality_floor_x2 import check_experience_bullet_evidence_density
from apps_rg.runtime.validators.narrative_mechanical_x2 import check_narrative_exactly_one_sentence
from apps_rg.runtime.quality.overlap_engine import (
    evaluate_bullets_section_overlap,
    evaluate_narrative_section_overlap,
)
from apps_rg.runtime.validators.narrative_quality_x2 import (
    repair_narrative_bullet_echo_from_graph,
)
from ._parent import parent_attr
from .bullet_normalization import _fact_id_from_row, _normalize_bullets
from .lane_config import (
    ROLE_EPISODE_FINAL_BULLET_COUNT,
    RoleEpisodeLaneConfig,
    _ROLE_LANES,
    _bullet_sentence,
    _facts_from_plan,
    _normalize_source_ids,
    _sentence,
)
from .materialization import _claim_ledger_from_bullets, _display_text
from .narrative_binding import _narrative_from_parsed, _targeting_only_experience_hits
from .proof_selection import _model_bullet_surface_binding, _ordered_ids_from_bullets, _proof_fact_by_id, _proof_fact_text

def _x2_gate(gate_id: str, ok: bool, reason: str = "", observed: Any = None) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "gate_type": "deterministic",
        "pass": bool(ok),
        "failure_reason": None if ok else reason,
        "observed_value": observed,
    }


def _display_text_for_x2(l2: dict[str, Any], cfg: RoleEpisodeLaneConfig) -> str:
    if cfg.is_bullet_lane:
        return "\n".join(
            str(b.get("bullet_text") or "")
            for b in (l2.get("bullets") or [])
            if isinstance(b, dict)
        )
    return str(l2.get("narrative_sentence") or "")


def _selected_fact_plan_authorized_texts(
    l2: dict[str, Any], *, is_bullet_lane: bool = True
) -> dict[str, str]:
    facts = _facts_from_plan(l2.get("selected_fact_plan") or {})
    norm = _bullet_sentence if is_bullet_lane else _sentence
    return {
        fid: norm(raw_text)
        for fact in facts
        if (fid := _fact_id_from_row(fact)) and (raw_text := _proof_fact_text(fact))
    }


def _display_text_is_proof_authorized(
    *,
    cfg: RoleEpisodeLaneConfig,
    l2: dict[str, Any],
    allowed: list[str],
) -> tuple[bool, dict[str, Any]]:
    authority = str(l2.get("display_text_authority") or "").strip()
    authorized_by_id = _selected_fact_plan_authorized_texts(
        l2, is_bullet_lane=cfg.is_bullet_lane
    )
    authorized_facts_by_id = {
        fid: fact
        for fact in _facts_from_plan(l2.get("selected_fact_plan") or {})
        if (fid := _fact_id_from_row(fact))
    }
    if not authority and not authorized_by_id:
        return True, {"status": "not_evaluated_legacy_payload"}
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    rows: list[dict[str, Any]] = []
    if cfg.is_bullet_lane:
        display_rows = [
            (str(b.get("bullet_id") or ""), str(b.get("bullet_text") or ""), list(b.get("source_fact_ids") or []))
            for b in (l2.get("bullets") or [])
            if isinstance(b, dict)
        ]
    else:
        display_rows = [
            (
                "narrative_sentence",
                str(l2.get("narrative_sentence") or ""),
                [sid for row in (l2.get("claim_ledger") or []) if isinstance(row, dict) for sid in row.get("source_fact_ids") or []],
            )
        ]
    if not display_rows and cfg.section_id in ("ey_bullets", "ey_narrative"):
        return True, {"status": "PASS", "display_text_authority": authority, "rows": []}
    graph_bound_model_surface = authority == "model_selected_graph_bound_surface"
    ok = authority == "selected_fact_plan_claim_text" or graph_bound_model_surface
    for row_id, text, source_ids in display_rows:
        normalized_text = _bullet_sentence(text) if cfg.is_bullet_lane else _sentence(text)
        normalized_ids = [str(sid).strip() for sid in source_ids if str(sid).strip()]
        source_ok = bool(normalized_ids) and all(sid in allowed_set for sid in normalized_ids)
        binding_rows = []
        if graph_bound_model_surface:
            for source_id in normalized_ids:
                fact = authorized_facts_by_id.get(source_id)
                bound, anchors = _model_bullet_surface_binding(normalized_text, fact or {})
                binding_rows.append(
                    {
                        "source_fact_id": source_id,
                        "candidate_graph_bound": bound,
                        "anchor_tokens": anchors,
                    }
                )
            text_ok = any(row["candidate_graph_bound"] for row in binding_rows)
        else:
            text_ok = any(authorized_by_id.get(sid) == normalized_text for sid in normalized_ids)
        rows.append(
            {
                "row_id": row_id,
                "source_fact_ids": normalized_ids,
                "source_fact_ids_allowed": source_ok,
                "text_matches_selected_fact_claim_text": text_ok,
                "model_surface_binding": binding_rows,
            }
        )
        ok = ok and source_ok and text_ok
    return ok, {
        "status": "PASS" if ok else "FAIL",
        "display_text_authority": authority,
        "rows": rows,
    }


def _has_first_person(text: str) -> bool:
    return bool(re.search(r"\b(I|me|my|mine|we|us|our|ours)\b", str(text or ""), flags=re.IGNORECASE))


def _x2_gates(
    *,
    cfg: RoleEpisodeLaneConfig,
    l2: dict[str, Any],
    allowed: list[str],
    runtime_generation_status: str,
) -> list[dict[str, Any]]:
    claim_ledger = list(l2.get("claim_ledger") or [])
    cited: list[str] = []
    for row in claim_ledger:
        if isinstance(row, dict):
            cited.extend(str(x) for x in row.get("source_fact_ids") or [])
    bad = sorted({x for x in cited if x not in set(allowed)})
    display_text = _display_text_for_x2(l2, cfg)
    proof_text_ok, proof_text_obs = _display_text_is_proof_authorized(
        cfg=cfg,
        l2=l2,
        allowed=allowed,
    )
    is_ey = cfg.section_id in ("ey_bullets", "ey_narrative")
    expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT)
    gates = [
        _x2_gate(
            f"x2_{cfg.section_id}_allowed_fact_ids_non_empty",
            bool(allowed) or is_ey,
            "allowed_fact_ids empty",
            len(allowed),
        ),
        _x2_gate(
            f"x2_{cfg.section_id}_source_fact_ids_supported",
            (not bad and bool(cited)) if (not is_ey or bool(cited)) else not bad,
            "claim source_fact_ids missing or outside allowed pool",
            {"bad": bad, "cited_count": len(cited)},
        ),
        _x2_gate(
            "x2_claim_ledger_claim_text_non_empty",
            (bool(claim_ledger) and all(str(r.get("claim_text") or "").strip() for r in claim_ledger if isinstance(r, dict))) if (not is_ey or bool(claim_ledger)) else True,
            "claim_ledger missing or empty claim_text",
            len(claim_ledger),
        ),
        _x2_gate(
            f"x2_{cfg.section_id}_display_text_proof_authorized",
            proof_text_ok or (is_ey and not display_text),
            "display text must be rendered from selected proof fact claim_text",
            proof_text_obs,
        ),
        _x2_gate(
            f"x2_{cfg.section_id}_runtime_real_llm",
            runtime_generation_status == "REAL_LLM",
            f"runtime_generation_status={runtime_generation_status}",
            runtime_generation_status,
        ),
        _x2_gate(
            "x2_no_first_person",
            not _has_first_person(display_text),
            "first-person language detected",
        ),
        _x2_gate(
            "x2_no_em_dash",
            "—" not in display_text,
            "em dash detected",
        ),
        _x2_gate(
            f"x2_{cfg.section_id}_targeting_only_not_experience_claim",
            not _targeting_only_experience_hits(display_text, target_company=str(l2.get("target_company") or "")),
            "targeting/JD-only phrase used as experience claim",
            _targeting_only_experience_hits(display_text, target_company=str(l2.get("target_company") or "")),
        ),
    ]
    if cfg.is_bullet_lane:
        bundle_consumed = bool(l2.get("role_episode_bundle_consumed", True))
        bullets = list(l2.get("bullets") or [])
        gates.extend(
            [
                _x2_gate(
                    f"x2_{cfg.section_id}_graph_role_episode_bundle_consumed",
                    bundle_consumed,
                    "role episode bundles not consumed from proof pool metadata",
                    bundle_consumed,
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_bullet_count_{expected_bullet_count}",
                    len(bullets) == expected_bullet_count,
                    f"expected exactly {expected_bullet_count} bullets",
                    len(bullets),
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_bullet_single_thought",
                    all(
                        check_bullet_single_thought(str(b.get("bullet_text") or ""))[0]
                        for b in bullets
                        if isinstance(b, dict)
                    ),
                    # Sentence-aware (shared validator): a decimal like "99.99%" is one thought,
                    # not two sentences — the prior raw '.'-count false-failed legitimate metrics.
                    "bullet contains multiple sentence-like thoughts",
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_bullet_no_embedded_newline",
                    all("\n" not in str(b.get("bullet_text") or "") for b in bullets if isinstance(b, dict)),
                    "bullet contains embedded newline",
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_bullet_evidence_density_required",
                    (
                        bool(bullets)
                        and all(
                            check_experience_bullet_evidence_density(
                                str(b.get("bullet_id") or ""),
                                str(b.get("bullet_text") or ""),
                            ).passed
                            for b in bullets
                            if isinstance(b, dict)
                        )
                    )
                    if expected_bullet_count > 0
                    else all(
                        check_experience_bullet_evidence_density(
                            str(b.get("bullet_id") or ""),
                            str(b.get("bullet_text") or ""),
                        ).passed
                        for b in bullets
                        if isinstance(b, dict)
                    ),
                    "each experience bullet needs an action, concrete delivery detail, and a graph-bound outcome",
                    [asdict(check_experience_bullet_evidence_density(str(b.get("bullet_id") or ""), str(b.get("bullet_text") or ""))) for b in bullets if isinstance(b, dict)],
                ),
            ]
        )
        b_ov = evaluate_bullets_section_overlap(bullets, section_id=cfg.section_id)
        gates.append(_x2_gate("x2_overlap_engine", b_ov.passed, b_ov.diagnostic_summary(section_id=cfg.section_id) if not b_ov.passed else "", b_ov.to_dict()))
        gates.append(_x2_gate(f"x2_{cfg.section_id}_within_section_bullet_cosine_similarity", b_ov.passed, b_ov.diagnostic_summary(section_id=cfg.section_id) if not b_ov.passed else "", {"max_pairwise_content_cosine": b_ov.max_within_section_idf_cosine}))
    else:
        sent = str(l2.get("narrative_sentence") or "").strip()
        sent_ok, sent_count, _sent_reason = check_narrative_exactly_one_sentence(sent)
        is_ey_narrative = (cfg.section_id == "ey_narrative")
        words = sent.split()
        first_word = words[0].rstrip(",.:;") if words else ""
        _FORBIDDEN_OPENERS = {"senior", "director", "vp", "svp", "the", "he", "she", "amit", "candidate", "in", "as"}
        action_verb_ok = (not sent) or bool(first_word and first_word.lower() not in _FORBIDDEN_OPENERS)
        min_words_ok = (len(words) == 0) if is_ey_narrative else (len(words) >= 15 if cfg.section_id in ("slalom_narrative", "insurtech_narrative") else len(words) >= 10)
        word_budget_ok = (
            (len(words) == 0 or (8 <= len(words) <= NARRATIVE_MAX_WORDS))
            if is_ey_narrative
            else (min_words_ok and len(words) <= NARRATIVE_MAX_WORDS)
        )
        gates.extend(
            [
                _x2_gate(
                    f"x2_{cfg.section_id}_exactly_one_sentence",
                    (sent == "" or sent_ok) if is_ey_narrative else sent_ok,
                    "expected exactly one sentence" if not is_ey_narrative else "expected empty or single sentence for ey_narrative",
                    {"sentence_count": sent_count, "text": sent},
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_word_budget",
                    word_budget_ok,
                    f"narrative outside word budget (min 15 words for {cfg.section_id}, max {NARRATIVE_MAX_WORDS})",
                    len(words),
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_char_budget",
                    (len(sent) == 0 or (0 < len(sent) <= NARRATIVE_MAX_CHARS)) if is_ey_narrative else (0 < len(sent) <= NARRATIVE_MAX_CHARS),
                    "narrative outside char budget",
                    len(sent),
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_executive_action_verb",
                    action_verb_ok,
                    f"narrative must start with an executive action verb, not a title or filler token (got {first_word!r})",
                    first_word,
                ),
            ]
        )
        companion_text_for_x2 = str(l2.get("companion_bullet_texts") or "").strip()
        n_ov = evaluate_narrative_section_overlap(sent, companion_text_for_x2, section_id=cfg.section_id)
        gates.append(_x2_gate("x2_overlap_engine", n_ov.passed, n_ov.diagnostic_summary(section_id=cfg.section_id) if not n_ov.passed else "", n_ov.to_dict()))
        if companion_text_for_x2:
            gates.append(_x2_gate(f"x2_{cfg.section_id}_narrative_bullet_cosine_similarity", n_ov.passed, n_ov.diagnostic_summary(section_id=cfg.section_id) if not n_ov.passed else "", {"max_pairwise_content_cosine": n_ov.max_narrative_to_bullet_idf_cosine}))
    return gates


def run_role_episode_x2_gates(
    *,
    section_id: str,
    l2: dict[str, Any],
    allowed: list[str],
    runtime_generation_status: str,
) -> list[dict[str, Any]]:
    cfg = _ROLE_LANES[str(section_id or "").strip().lower()]
    return parent_attr("_x2_gates", _x2_gates)(
        cfg=cfg,
        l2=l2,
        allowed=allowed,
        runtime_generation_status=runtime_generation_status,
    )


def run_slalom_bullets_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return parent_attr("run_role_episode_x2_gates", run_role_episode_x2_gates)(section_id="slalom_bullets", **kwargs)


def run_slalom_narrative_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return parent_attr("run_role_episode_x2_gates", run_role_episode_x2_gates)(section_id="slalom_narrative", **kwargs)


def run_insurtech_bullets_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return parent_attr("run_role_episode_x2_gates", run_role_episode_x2_gates)(section_id="insurtech_bullets", **kwargs)


def run_insurtech_narrative_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return parent_attr("run_role_episode_x2_gates", run_role_episode_x2_gates)(section_id="insurtech_narrative", **kwargs)


def run_ey_bullets_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return parent_attr("run_role_episode_x2_gates", run_role_episode_x2_gates)(section_id="ey_bullets", **kwargs)


def run_ey_narrative_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return parent_attr("run_role_episode_x2_gates", run_role_episode_x2_gates)(section_id="ey_narrative", **kwargs)


def _judge_rows(
    *,
    cfg: RoleEpisodeLaneConfig,
    provider_result: ProviderResult,
    x2_gates: list[dict[str, Any]],
    l2: dict[str, Any],
    allowed_fact_ids: list[str],
    mock_judges: bool,
    artifact_dir: Path | None = None,
    generation_meta: dict[str, Any] | None = None,
    runtime_payload: dict[str, Any] | None = None,
    product_quality_status: str = "PASS",
) -> list[dict[str, Any]]:
    from apps_rg.runtime.judges.role_episode_x1d import run_role_episode_judges
    from apps_rg.runtime.section_judge_policy import get_section_judge_policy

    required_judge_keys = list(get_section_judge_policy(cfg.section_id).required_judge_providers)
    if provider_result.runtime_generation_status != "REAL_LLM":
        return [
            {
                "provider_key": provider_key,
                "provider_status": "BLOCKED_PROVIDER_UNAVAILABLE",
                "evaluator_mode": "BLOCKED_PROVIDER_UNAVAILABLE",
                "provider_blocked": True,
                "exact_provider_error": provider_result.exact_provider_error,
                "pass": False,
                "proof_eligible_judge": False,
                "advisory_only": False,
                "section_id": cfg.section_id,
            }
            for provider_key in required_judge_keys
        ]
    x2_failed_ids = [str(g.get("gate_id") or "") for g in x2_gates if not g.get("pass")]
    if (product_quality_status != "PASS" or x2_failed_ids) and not mock_judges:
        return [
            {
                "judge_id": f"x1d_{provider_key}_{cfg.section_id}",
                "provider_name": provider_key,
                "provider_key": provider_key,
                "provider_status": "BLOCKED_PRE_JUDGE_DETERMINISTIC_GATE",
                "evaluator_mode": "BLOCKED_PRE_JUDGE_GATE",
                "model_name": "deterministic_pre_judge_gate",
                "provider_available": False,
                "provider_blocked": True,
                "exact_provider_error": f"Skipped LLM judge due to X2 failure: {', '.join(x2_failed_ids[:5]) or product_quality_status}",
                "pass": False,
                "decisive_failure": True,
                "findings": list(x2_failed_ids),
                "proof_eligible_judge": False,
                "advisory_only": False,
                "section_id": cfg.section_id,
            }
            for provider_key in required_judge_keys
        ]
    mode = "mocked" if mock_judges else "blocked_if_unavailable"
    candidate_for_judge = {k: v for k, v in l2.items() if k != "selected_fact_plan"}
    sfp = l2.get("selected_fact_plan") if isinstance(l2.get("selected_fact_plan"), dict) else {}
    plan_facts = [
        {
            "fact_id": f.get("fact_id"),
            "role_episode_bundle_id": f.get("role_episode_bundle_id"),
            "claim_text": f.get("claim_text"),
            "domain": f.get("domain"),
            "allowed_graph_evidence_ids": f.get("allowed_graph_evidence_ids"),
            "raw_chunk": str(f.get("raw_chunk") or "")[:1500],
        }
        for f in list(sfp.get("facts") or [])
        if isinstance(f, dict)
    ]
    rp = runtime_payload or {}
    proof_rows = [
        judge.to_dict()
        for judge in run_role_episode_judges(
            section_id=cfg.section_id,
            candidate_output=candidate_for_judge,
            claim_ledger=list(l2.get("claim_ledger") or []),
            judge_keys=required_judge_keys,
            mode=mode,
            artifact_base=artifact_dir,
            targeting_context={
                "target_title": str(rp.get("target_title") or l2.get("target_title") or ""),
                "target_company": str(rp.get("target_company") or l2.get("target_company") or ""),
                "jd_text": str(rp.get("jd_text") or ""),
                "briefing": str(rp.get("briefing") or ""),
                "jd_alignment": l2.get("jd_alignment"),
                "targeting_only": True,
            },
            deterministic_gate_summary={"x2_gates": x2_gates},
            allowed_fact_packet={
                "allowed_fact_ids": allowed_fact_ids,
                "facts": plan_facts,
            },
        )
    ]
    if cfg.is_bullet_lane and artifact_dir is not None and is_employment_pool_generation(generation_meta):
        proof_rows.extend(
            employment_pool_x1d_judge_rows(
                artifact_dir=artifact_dir,
                section_id=cfg.section_id,
                gen_meta=generation_meta,
            )
        )
    return proof_rows

