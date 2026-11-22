"""Prompt compilation and blocked provider fallback constructors for role-episode lanes."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Mapping

from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    FINAL_BULLET_COUNT,
    REQUIRED_BULLET_IDS,
    build_employment_targeting_context,
    is_employment_bullet_lane,
)
from apps_rg.runtime.sections.section_product_shape_ssot import (
    NARRATIVE_MAX_CHARS,
    NARRATIVE_MAX_WORDS,
)
from .lane_config import RoleEpisodeLaneConfig, _compact_text, _facts_from_plan, _role_header

def _role_episode_evidence_block(runtime_payload: dict[str, Any]) -> str:
    """Proof-substrate block from role-episode bundles plus allocated metric_outcome_id/metric_text."""
    ppm = runtime_payload.get("proof_pool_metadata") or {}
    bundles = ppm.get("role_episode_bundles") or []
    sfp = runtime_payload.get("selected_fact_plan") or {}
    alloc_by_root: dict[str, dict[str, str]] = {}
    for row in (sfp.get("allocation_assignments") or sfp.get("assignments") or []):
        if isinstance(row, Mapping):
            rid, mid, mtxt = str(row.get("root_id") or row.get("role_episode_bundle_id") or "").strip(), str(row.get("metric_outcome_id") or "").strip(), str(row.get("metric_text") or "").strip()
            if rid and (mid or mtxt):
                alloc_by_root[rid] = {"metric_outcome_id": mid, "metric_text": mtxt}
    for row in (sfp.get("selected_metrics_detail") or []):
        if isinstance(row, Mapping):
            rid, mid, mtxt = str(row.get("root_id") or "").strip(), str(row.get("metric_id") or row.get("metric_outcome_id") or "").strip(), str(row.get("metric") or row.get("metric_text") or "").strip()
            if rid and (mid or mtxt) and rid not in alloc_by_root:
                alloc_by_root[rid] = {"metric_outcome_id": mid, "metric_text": mtxt}
    if not bundles and not alloc_by_root:
        return ""
    lines = ["GRAPH_SKILL_EVIDENCE (use these bound skills only to choose and order allowed source_fact_ids; phrases are ranking vocabulary, NOT display-text authority; skill_id alone is not proof):"]
    seen_roots: set[str] = set()
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        rid = str(bundle.get("role_episode_bundle_id") or "").strip()
        seen_roots.add(rid)
        intent = str(bundle.get("bullet_intent") or "").strip()
        outcome = str(bundle.get("claim_outcome") or "").strip()
        lines.append(f"- role_episode_bundle_id: {rid}" + (f" | intent: {intent}" if intent else ""))
        if outcome:
            lines.append(f"  graph_business_outcome: {outcome}")
        if rid in alloc_by_root:
            lines.append(f"  allocated_metric_outcome_id: {alloc_by_root[rid]['metric_outcome_id']} | metric_text: {alloc_by_root[rid]['metric_text']} (MANDATORY: include this exact numeric metric proof in the bullet for this bundle)")
        primary, optional = [], []
        for skill in bundle.get("bound_skills") or []:
            if not isinstance(skill, dict):
                continue
            phrases = [str(p).strip() for p in (skill.get("allowed_phrases") or []) if str(p).strip()]
            if phrases:
                entry = f"    {skill.get('skill_id')}: {', '.join(phrases)}"
                (primary if str(skill.get("activation_status") or "").upper() == "ACTIVE_CONFIRMED" else optional).append(entry)
        if primary:
            lines.extend(["  primary_skills (foreground these for source_fact_id selection):", *primary])
        if optional:
            lines.extend(["  optional_skills (use only for JD-relevant source_fact_id selection):", *optional])
    for rid, am in sorted(alloc_by_root.items()):
        if rid not in seen_roots:
            lines.extend([f"- role_episode_bundle_id: {rid}", f"  allocated_metric_outcome_id: {am['metric_outcome_id']} | metric_text: {am['metric_text']} (MANDATORY: include this exact numeric metric proof in the bullet for this bundle)"])
    return "\n".join(lines)


def _compiled_prompt(cfg: RoleEpisodeLaneConfig, runtime_payload: dict[str, Any]) -> str:
    facts = _facts_from_plan(runtime_payload.get("selected_fact_plan") or {})
    fact_lines = [
        f"- {f.get('fact_id')}: {_compact_text(str((f.get('fact_anchor') or {}).get('resolved_raw_chunk') or f.get('raw_chunk') or f.get('claim_text') or f.get('text') or ''), max_chars=280)}"
        for f in facts
    ]
    role_methodology = (
        "METHODOLOGY:\n"
        "- Bullets do the hard proof work: each bullet must carry one evidence-bound achievement, "
        "cite only allowed source_fact_ids, and avoid generic substitution.\n"
        "- Quality floor for every bullet: state a specific action, a named delivery detail, and an "
        "evidence-backed business, adoption, risk, or delivery result. A capability-only statement "
        "such as a framework, service, or platform with no result is invalid.\n"
        "- Narratives are the lightweight synthesis step above finalized bullets: turn accepted "
        "bullet themes into one higher-level role thesis. The narrative states why the role mattered; "
        "the bullets prove what was delivered.\n"
        "- Do not redo first-principles graph traversal in the narrative. Use the accepted bullet "
        "themes as primary synthesis context after finalization; the active proof pool and "
        "claim_ledger remain the only proof authority.\n"
        "- Prefer one clean executive through-line over a comma-packed list of bullet topics."
    )
    expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, 3)
    shape = (
        f"Return JSON with exactly {expected_bullet_count} bullets: "
        "{bullets:[{bullet_id, bullet_text, source_fact_ids}], claim_ledger:[{claim_text, source_fact_ids}], "
        "jd_alignment:{targeting_only:true,jd_used_as_proof:false}}. Each bullet is a single "
        "proof-bearing achievement with action, delivery detail, and result; do not write a role summary "
        "or narrative sentence in bullet form."
        if cfg.is_bullet_lane
        else "Return JSON with narrative_sentence, claim_ledger:[{claim_text, source_fact_ids}], "
        "jd_alignment:{targeting_only:true,jd_used_as_proof:false}. The narrative is exactly one complete, inspiring executive sentence "
        f"of between 15 and {NARRATIVE_MAX_WORDS} words (at most {NARRATIVE_MAX_CHARS} characters), "
        "in first-person-implied resume voice: MUST start with an executive action verb (e.g. Built, Commercialized, Delivered, Operationalized, Drove, Transformed, Architected) and NEVER start with 'Led' or a title fragment ('Senior Director ...') or third-person subject. "
        "VALUE-OUTCOME MANDATE: State concretely what was built, commercialized, or delivered and what business, commercial, or operational outcome it drove (drawing on graph_business_outcome); NEVER write practice-leadership-only filler ('led this practice', 'oversaw consulting delivery') without concrete delivered capabilities and business impact. "
        "Do NOT repeat numeric metrics from the companion bullets (e.g. 105, 100%) and do NOT list bullet phrases in a comma-packed inventory. "
        "Do NOT use targeting buzzwords like 'frontier AI' as an experience claim (use 'enterprise AI' or 'next-generation AI'). "
        "Synthesize the delivered value and business outcome by connecting the candidate's bound graph capabilities to the target JD's strategic priorities, "
        "keeping pairwise cosine similarity against every companion bullet low (<= 0.35)."
    )

    companion_text = str(runtime_payload.get("companion_bullet_texts") or "").strip()
    companion_block = (
        f"ACCEPTED_COMPANION_BULLETS (READ_ONLY_SYNTHESIS_CONTEXT — DO NOT COPY PHRASES, OPENERS, OR METRICS):\n{companion_text}"
        if (not cfg.is_bullet_lane and companion_text) else ""
    )
    ppm = runtime_payload.get("proof_pool_metadata") or {}
    evidence_block = _role_episode_evidence_block(runtime_payload) if ppm.get("role_episode_bundle_consumption") else ""
    focus = str(runtime_payload.get("recovery_diagnostic_focus") or "").strip()
    focus_block = f"<RECOVERY_DIAGNOSTIC_FOCUS>\n{focus}\n</RECOVERY_DIAGNOSTIC_FOCUS>" if focus else ""
    if evidence_block:
        from apps_rg.runtime.sections.executive_summary_pa import format_jd_targeting_block
        jd_block = format_jd_targeting_block(
            target_title=str(runtime_payload.get("target_title") or ""),
            target_company=str(runtime_payload.get("target_company") or ""),
            jd_text=str(runtime_payload.get("jd_text") or ""),
            briefing=str(runtime_payload.get("briefing") or ""),
            graph_proof_pool_mode=True,
        )
        instruction = (
            "Use JD_TEXT and BRIEFING only to choose emphasis, ordering, and allowed source_fact_ids "
            "for the target role — NOT to create display claim wording, employers, tools, or metrics. "
            "Compose each bullet as a complete, single-sentence executive achievement starting with a strong past-tense action verb, "
            "pairing the bundle's concrete delivered capability directly with its graph_business_outcome and any allocated metric_text from GRAPH_SKILL_EVIDENCE. "
            "OUTCOME TIE-BACK: Every bullet must prove what was concretely built or delivered AND what measurable business, commercial, accuracy, adoption, or risk-reduction outcome it produced; practice-leadership-only or capability-only bullets are invalid. "
            "SENTENCE CADENCE VARIETY: Vary clause structures across the bullet set (mix 'by <gerund>', 'to <verb>', and 'that/which <verb>' clauses; "
            "do not end every bullet with an identical ', <gerund>ing ...' participial tail). "
            "EXECUTIVE REGISTER: Frame every bullet at C-suite/SVP engineering and client-delivery level; never list internal codebase package counts, "
            "MCP server counts, readiness gate counts, or low-level database file internals (e.g. SQLite WAL, FTS5, 119-package, 32 readiness gates, "
            "6 MCP servers, Dirichlet-Laplace, Universal Write Gateway). "
            "Every claim MUST cite only allowed source_fact_ids. targeting_only=true; jd_used_as_proof=false."
            if cfg.is_bullet_lane
            else "Use JD_TEXT, BRIEFING, GRAPH_SKILL_EVIDENCE, and ACCEPTED_COMPANION_BULLETS to synthesize "
            "one value-outcome-oriented executive sentence grounded in the candidate's allowed graph bundles: state concretely what was built, commercialized, or delivered and what business or operational outcome it drove (never generic practice-leadership-only phrasing). Do NOT copy verbatim "
            "fact claim_text lists or companion bullet metrics; retain graph anchor vocabulary across cited "
            "source_fact_ids while keeping pairwise cosine similarity against each companion bullet <= 0.35. "
            "targeting_only=true; jd_used_as_proof=false."
        )
        return "\n".join([b for b in [focus_block, f"Section: {cfg.section_id}", role_methodology, instruction, jd_block, evidence_block, companion_block, shape, "Allowed facts (claim proof — source_fact_ids must cite only these):", *fact_lines] if b])

    return "\n".join([b for b in [focus_block, f"Section: {cfg.section_id}", role_methodology, "Use only source_fact_ids from the allowed facts below. Do not use JD or briefing as claim proof.", companion_block, shape, "Allowed facts:", *fact_lines] if b])


def _prompt_object(prompt_text: str, *, run_id: str, prompt_hash: str) -> SimpleNamespace:
    return SimpleNamespace(
        request_id=run_id,
        run_id=run_id,
        compilation_hash=prompt_hash,
        system_preamble="You are an apps_rg section generator. Emit compact JSON only.",
        user_instruction=prompt_text,
        prompt_blocks=(
            SimpleNamespace(role="system", content="You are an apps_rg section generator. Emit compact JSON only."),
            SimpleNamespace(role="user", content=prompt_text),
        ),
    )


def _blocked_provider_result(provider: str, message: str, *, model: str = "") -> ProviderResult:
    return ProviderResult(
        provider_requested=provider,
        provider_attempted=False,
        provider_available=False,
        exact_provider_error=message,
        runtime_generation_status="BLOCKED",
        model=model,
        raw_model_output="",
        provider_response=None,
    )

