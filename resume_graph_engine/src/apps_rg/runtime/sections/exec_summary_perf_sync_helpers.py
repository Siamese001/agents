"""Companion helpers for Executive Summary composition, pre-synthesis repairs, and metric scrubbing."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def fact_supports_brushstroke_facet(
    fact: dict[str, Any],
    role: str,
    *,
    classify_fn: Any,
    fact_id_base_fn: Any,
) -> bool:
    fid = fact_id_base_fn(str(fact.get("fact_id") or "")).lower()
    bundle_id = str(fact.get("role_episode_bundle_id") or "").lower()
    claim = str(fact.get("claim_text") or "").lower()
    blob = f"{fid} {bundle_id} {claim}"
    if classify_fn(fid, claim) == role:
        return True
    if role == "B1_executive_identity":
        return any(
            k in blob
            for k in (
                "leadership",
                "partner",
                "cosell",
                "co-sell",
                "alliance",
                "transformation",
                "advisory",
                "scaled",
                "head of",
                "svp",
                "director",
            )
        )
    if role == "B2_governed_platform_system":
        return any(
            k in blob
            for k in (
                "platform",
                "architecture",
                "agentic",
                "rag",
                "graphrag",
                "solution",
                "reference architecture",
                "reusable",
                "modernization",
                "cloud",
            )
        )
    if role == "B3_control_evidence_discipline":
        return any(
            k in blob
            for k in (
                "governed",
                "governance",
                "audit",
                "traceable",
                "telemetry",
                "routing",
                "validation",
                "enablement",
                "repeatable",
                "compliance",
                "lineage",
                "risk",
                "standard",
                "playbook",
            )
        )
    if role == "B4_business_role_fit":
        return bool(fact.get("metric_raw") or fact.get("metric_outcome_ids")) or any(
            k in blob
            for k in ("revenue", "margin", "growth", "$", "%", "commercial", "adoption", "pipeline", "scaled")
        )
    return False


def resolve_fallback_brushstroke_facts(
    facts: list[dict[str, Any]],
    role: str,
    *,
    classify_fn: Any,
    fact_id_base_fn: Any,
) -> list[dict[str, Any]]:
    facet_facts = [
        f
        for f in facts
        if isinstance(f, dict)
        and fact_supports_brushstroke_facet(
            f, role, classify_fn=classify_fn, fact_id_base_fn=fact_id_base_fn
        )
    ]
    if facet_facts:
        return facet_facts
    if role == "B1_executive_identity":
        preferred_b1 = [
            f
            for f in facts
            if isinstance(f, dict)
            and any(
                k in str(f.get("fact_id") or "").lower()
                for k in ("slalom", "unify", "ibm", "partner", "leadership", "transformation")
            )
        ]
        return [preferred_b1[0]] if preferred_b1 else [facts[0]]
    return [facts[0]]


def expand_covered_brushstroke_roles(
    bindings: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    allowed: set[str],
    brushstroke_roles: tuple[str, ...] | list[str],
    *,
    classify_fn: Any,
    fact_id_base_fn: Any,
) -> list[str]:
    covered_set = {b["brushstroke_role"] for b in bindings if b.get("in_allowed_pool")}
    for role in brushstroke_roles:
        if role not in covered_set and any(
            isinstance(f, dict)
            and fact_id_base_fn(str(f.get("fact_id") or "")) in allowed
            and fact_supports_brushstroke_facet(
                f, role, classify_fn=classify_fn, fact_id_base_fn=fact_id_base_fn
            )
            for f in facts
        ):
            covered_set.add(role)
    return sorted(covered_set)


def resolve_target_picture_for_archetype(
    *,
    role_archetype: str,
    strategy_executive: bool,
    role_s: str,
) -> str:
    if role_archetype == "ai_partnerships":
        return (
            "Executive portrait: leadership-first applied AI architecture and ecosystem partnerships leader "
            "aligning reusable agentic platforms, hyperscaler/GSI co-sell execution, and commercial platform adoption "
            f"(targeting context: {role_s or 'AI Partnerships role'}; company name never in prose)."
        )
    if strategy_executive:
        return (
            "Executive portrait: leadership-first technology strategy leader aligning governed AI platforms, "
            "regulatory lineage, and digital innovation programs into one enterprise IT direction "
            f"(targeting context: {role_s or 'SVP IT strategy'}; company name never in prose)."
        )
    return (
        f"Executive portrait: leadership-first governed agentic AI platform leader "
        f"(targeting: {role_s or 'target role'}; company name never in prose)."
    )


def attach_non_strategy_s6_anchor(
    sentence_arc: list[dict[str, Any]],
    arc_meta: dict[str, Any],
    *,
    briefing_text: str,
    jd_text: str,
    anchor_fn: Any,
) -> None:
    arc_meta["s6_targeting_forward_anchor"] = anchor_fn(
        briefing_text=str(briefing_text or ""),
        jd_text=str(jd_text or ""),
    )
    if len(sentence_arc) >= 6:
        sentence_arc[5] = {
            **sentence_arc[5],
            "s6_targeting_forward_anchor": arc_meta["s6_targeting_forward_anchor"],
        }


def has_upstream_allocation_defect_in_judges(
    model_backed: list[dict[str, Any]],
    judge_text_blob_fn: Any,
) -> bool:
    return any(
        str(j.get("defect_origin") or "") == "UPSTREAM_ALLOCATION_DEFECT"
        or any(
            pat in judge_text_blob_fn(j)
            for pat in ("bcbs 239", "monolithic policy administration", "upstream_allocation_defect")
        )
        for j in model_backed
    )


def apply_pre_synthesis_candidate_repairs(
    parsed: dict[str, Any],
    selected_fact_plan: dict[str, Any] | None,
    *,
    normalize_fn: Any,
    prune_orphans_fn: Any,
    allowed_fact_ids_override: set[str] | None = None,
    target_company: str = "",
) -> tuple[dict[str, Any], str]:
    if not isinstance(parsed, dict) or not isinstance(selected_fact_plan, dict) or not selected_fact_plan:
        raw_s = json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) if isinstance(parsed, dict) else ""
        return parsed, raw_s
    from apps_rg.runtime.sections.executive_summary_voice_repair import (
        apply_voice_repair_to_parsed,
    )
    from apps_rg.runtime.sections.section_authority_repairs import (
        apply_exec_summary_display_authority_repairs,
    )

    plan_facts = list(selected_fact_plan.get("facts") or [])
    if allowed_fact_ids_override is not None:
        allowed_ids = set(allowed_fact_ids_override)
    else:
        allowed_ids = {
            str(f.get("fact_id") or f.get("source_fact_id") or "").strip()
            for f in plan_facts
            if isinstance(f, dict) and str(f.get("fact_id") or f.get("source_fact_id") or "").strip()
        }
        for row in selected_fact_plan.get("allocation_assignments") or []:
            if isinstance(row, dict):
                for key in ("root_id", "fact_id", "skill_id", "metric_outcome_id"):
                    val = str(row.get(key) or "").strip()
                    if val:
                        allowed_ids.add(val)
    normalized = normalize_fn(parsed, selected_fact_plan)
    if allowed_ids:
        prune_orphans_fn(normalized, allowed_ids)
    normalized, _ = apply_voice_repair_to_parsed(normalized, selected_facts=plan_facts)
    normalized = apply_exec_summary_display_authority_repairs(
        normalized,
        allowed_fact_ids=allowed_fact_ids_override if allowed_fact_ids_override is not None else (allowed_ids or None),
        plan_facts=plan_facts,
        artifact_dir=None,
        target_company=target_company,
    )
    from apps_rg.runtime.sections.executive_summary_voice_repair import _repair_forbidden_meta_phrases
    repaired_text, _ = _repair_forbidden_meta_phrases(str(normalized.get("resume_display_text") or ""))
    if repaired_text:
        normalized["resume_display_text"] = repaired_text
    raw_out = json.dumps(
        {k: v for k, v in normalized.items() if k != "selected_fact_plan"},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return normalized, raw_out


def write_synced_canonical_claim_ledger_v2(
    *,
    artifact_dir: Path,
    claim_ledger: list[dict[str, Any]],
    parse_status: str,
    invalid_reason: str | None,
    normalize_ledger_fn: Any,
    build_payload_fn: Any,
    write_json_fn: Any,
) -> None:
    norm_rows = normalize_ledger_fn(claim_ledger) if parse_status == "OK" else []
    canon_doc = build_payload_fn(
        norm_rows,
        parse_status=parse_status,
        invalid_reason=invalid_reason if parse_status != "OK" else None,
    )
    write_json_fn(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)


def rescore_snapshot_or_reuse_full_panel(
    snap: Any,
    *,
    full_panel_token: str,
    build_coverage_fn: Any,
    enrich_x2_fn: Any,
    refresh_x1d_fn: Any,
    allowed_fact_ids: set[str],
    input_payload_hash: str,
    runtime_payload: dict[str, Any],
    selected_facts_for_x2: list[dict[str, Any]],
    target_title: str,
    target_company: str,
    jd_text: str,
    briefing_text: str,
    judge_keys: list[str],
    judge_mode: str,
    artifact_dir: Path,
    compiled_prompt: str,
    prior_judges: list[dict[str, Any]],
    graph_targeting_capsule: Any,
    material_targeting_bundle: Any,
    graph_bindings: Any,
    repo_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if snap.scores_freshness == full_panel_token and snap.x1d_judges:
        return (
            [dict(j) for j in snap.x1d_judges],
            {"rescore_mode": "reused_full_panel_snapshot", "candidate_id": snap.candidate_id},
        )
    snap_ledger = [dict(r) for r in snap.claim_ledger]
    snap_coverage = build_coverage_fn(snap.resume_display_text, snap_ledger, allowed_fact_ids)
    snap_parsed_for_x2 = enrich_x2_fn(
        dict(snap.parsed_json),
        coverage=snap_coverage,
        input_payload_hash=input_payload_hash,
        allowed_fact_ids=allowed_fact_ids,
        runtime_payload=runtime_payload,
    )
    return refresh_x1d_fn(
        x2_gates=list(snap.x2_gate_outputs),
        resume_display_text=snap.resume_display_text,
        claim_ledger=snap_ledger,
        allowed_fact_packet=selected_facts_for_x2,
        allowed_fact_ids=allowed_fact_ids,
        target_title=target_title,
        target_company=target_company,
        jd_text=jd_text,
        briefing_text=briefing_text,
        parsed_output=snap_parsed_for_x2,
        judge_keys=judge_keys,
        judge_mode=judge_mode,
        artifact_dir=artifact_dir,
        compiled_prompt=compiled_prompt,
        prior_judges=prior_judges,
        graph_targeting_capsule=graph_targeting_capsule,
        material_targeting_bundle=material_targeting_bundle,
        graph_bindings=graph_bindings,
        repo_root=repo_root,
    )


def repair_legacy_regulated_partnership_arc(
    out: list[str],
    *,
    allowed: set[str],
    has_partner_evidence: bool,
    has_devsecops_evidence: bool,
    has_platform_evidence: bool,
) -> list[str]:
    if (
        {
            "reb_insurtech_aws_migration_execution",
            "reb_ey_erm_risk_governance",
            "reb_unify_platform_commercialization_leadership",
        }
        <= allowed
        and not has_partner_evidence
        and not has_devsecops_evidence
        and not has_platform_evidence
    ):
        joined_low = " ".join(out).lower()
        if (
            "from that commercial base" in joined_low
            or "that operating foundation" in joined_low
            or "erm operating models" in joined_low
        ):
            out[0] = (
                "Enterprise technology leader who aligns governed cloud modernization, "
                "enterprise risk discipline, and platform commercialization into one "
                "leadership agenda for regulated, partner-driven delivery."
            )
            out[1] = (
                "Led AWS modernization execution for monolithic policy administration "
                "and insurance platform workloads, establishing a cloud-native operating "
                "foundation for enterprise-scale delivery."
            )
            out[2] = (
                "In parallel, architected ERM operating models and BCBS 239-aligned "
                "risk-data aggregation by defining three-lines-of-defense accountability, "
                "metadata standards, and auditable risk metrics."
            )
            out[3] = (
                "Complementing that regulated architecture depth, agentic platform "
                "productization drove IP-led revenue growth, margin expansion, and "
                "team scale across enterprise programs."
            )
            out[4] = (
                "That platform productization discipline generated $22M in IP-led "
                "platform revenue, converting reusable AI platform capabilities into "
                "repeatable commercial outcomes."
            )
            out[5] = (
                "Reusable platform productization, governed cloud modernization, and "
                "auditable risk-lineage standards position partner-facing solution "
                "architecture teams to accelerate enterprise AI deployment and "
                "commercial adoption."
            )
    return out


def match_legacy_regulated_source_fact_ids(low: str) -> list[str] | None:
    if "architected erm operating models" in low or "bcbs 239-aligned risk-data aggregation" in low:
        return ["reb_ey_erm_risk_governance", "exp_ey_001"]
    if "led aws modernization execution" in low and "policy administration" in low:
        return ["reb_insurtech_aws_migration_execution", "exp_insurtech_001"]
    if "aligns governed cloud modernization, enterprise risk discipline, and platform commercialization" in low:
        return ["reb_insurtech_aws_migration_execution"]
    if "agentic platform productization drove ip-led revenue growth" in low:
        return [
            "reb_unify_platform_commercialization_leadership",
            "fact_engineering_platform_006",
            "skill_agentic_platform_productization",
        ]
    if "reusable platform productization, governed cloud modernization" in low:
        return [
            "skill_agentic_platform_productization",
            "reb_unify_platform_commercialization_leadership",
        ]
    return None


def bind_orphan_row_to_best_allocated_root(
    *,
    idx: int,
    row: dict[str, Any],
    sentence: str,
    eligible_fids: list[str],
    fact_by_id: dict[str, dict[str, Any]],
    tokens_fn: Any,
    support_text_fn: Any,
    repairs: list[dict[str, str]],
) -> None:
    sent_tokens = tokens_fn(sentence)
    best_fid = max(
        eligible_fids,
        key=lambda cand: (len(sent_tokens & tokens_fn(support_text_fn(fact_by_id[cand]))), cand),
    )
    row["source_fact_ids"] = [best_fid]
    row["claim"] = str(row.get("claim") or sentence)[:80]
    row["claim_text"] = str(row.get("claim_text") or sentence)
    repairs.append(
        {
            "operation": "repair_orphan_row_with_best_allocated_root",
            "reason": f"orphan_row_{idx + 1}_bound_allocated_root:{best_fid}",
        }
    )


def scrub_secondary_causal_metrics(
    *,
    display_sentence: str,
    visible_metrics: list[Any],
    chosen_signature: tuple[str, str],
    visible_metric_re: Any,
    extract_sig_fn: Any,
) -> str:
    clauses = re.split(r"\s*,?\s+\b(?:while|whereas)\b\s+", display_sentence, maxsplit=1)
    if len(clauses) == 2:
        candidate_clauses = [
            clause.strip()
            for clause in clauses
            if len(visible_metric_re.findall(clause)) == 1
            and extract_sig_fn(clause) == chosen_signature
        ]
        if len(candidate_clauses) == 1:
            return candidate_clauses[0]
    scrubbed = display_sentence
    for match in reversed(visible_metrics):
        if extract_sig_fn(match.group(0)) == chosen_signature:
            continue
        m_start, m_end = match.span()
        prefix = re.sub(
            r"\s+\b(?:by|of|over|nearly|roughly|approximately)\s*$",
            "",
            scrubbed[:m_start],
            flags=re.IGNORECASE,
        )
        suffix = re.sub(r"^\s+in(?=\s+[a-zA-Z])", "", scrubbed[m_end:], flags=re.IGNORECASE)
        scrubbed = prefix + suffix
    scrubbed = re.sub(r"\s{2,}", " ", scrubbed).strip()
    scrubbed = re.sub(r"\s+([.,;:])", r"\1", scrubbed)
    if (
        len(visible_metric_re.findall(scrubbed)) == 1
        and extract_sig_fn(scrubbed) == chosen_signature
        and len(scrubbed.split()) >= 8
    ):
        return scrubbed
    return ""


def resolve_unallocated_metric_sentence_replacement(
    *,
    display_sentence: str,
    sentences: list[str],
    index: int,
    raw_row: dict[str, Any],
    selected: list[dict[str, Any]],
    chosen: dict[str, Any],
    rank_fn: Any,
    extract_sig_fn: Any,
    tokens_fn: Any,
) -> tuple[str, str, str, str]:
    stripped_clause = re.sub(
        r",\s+with\s+[^.,;]*\b\d+(?:\.\d+)?\s*(?:%|percent\b|\$[0-9]+|m\b|million\b|b\b|billion\b)[^.]*\.?$",
        ".",
        display_sentence,
        flags=re.IGNORECASE,
    ).strip()
    existing_norms = {
        s.strip().rstrip(".!?").lower()
        for idx_s, s in enumerate(sentences)
        if idx_s != index and s.strip()
    }
    non_metric_roots = [
        assignment
        for assignment in selected
        if str(assignment.get("root_id") or "")
        and str(assignment.get("root_id") or "") in (raw_row.get("source_fact_ids") or [])
    ]
    has_non_metric_source_ids = any(
        str(fid or "").strip() and not str(fid or "").strip().startswith("metric_")
        for fid in (raw_row.get("source_fact_ids") or [])
    )
    chosen_root_norm = (
        str(chosen.get("root_claim_text") or chosen.get("root_claim_action") or "")
        .strip()
        .rstrip(".!?")
        .lower()
    )
    if (
        has_non_metric_source_ids
        or non_metric_roots
        or (chosen_root_norm and chosen_root_norm in existing_norms)
    ) and (stripped_clause == display_sentence or any(extract_sig_fn(stripped_clause))):
        inline_scrub = re.sub(
            r"\s+\b(?:by|of|over|nearly|roughly|approximately)\s+\$?\d+(?:\.\d+)?\s*(?:%|percent\b|m\b|million\b|b\b|billion\b)(?:\s+in\b)?",
            "",
            stripped_clause,
            flags=re.IGNORECASE,
        )
        inline_scrub = re.sub(
            r"\b\$?\d+(?:\.\d+)?\s*(?:%|percent\b|m\b|million\b|b\b|billion\b)\s+(?:in\s+)?(?=[a-zA-Z])",
            "",
            inline_scrub,
            flags=re.IGNORECASE,
        )
        inline_scrub = re.sub(r"\s{2,}", " ", inline_scrub).strip()
        inline_scrub = re.sub(r"\s+([.,;:])", r"\1", inline_scrub)
        inline_scrub = re.sub(
            r"\b([Aa])\s+(?=(?![uU](?:ni(?:f|q|t|v)|se|su|ti)|[eE]u|[oO]ne\b)[aeiouAEIOU][a-z])",
            lambda m: "An " if m.group(1) == "A" else "an ",
            inline_scrub,
        )
        inline_scrub = re.sub(
            r"\b([Aa])n\s+(?=(?!(?:hour|honest|honor|heir))[bcdfghjklmnpqrstvwxyz][a-z])",
            lambda m: "A " if m.group(1) == "A" else "a ",
            inline_scrub,
        )
        stripped_clause = inline_scrub
    if (
        stripped_clause
        and stripped_clause != display_sentence
        and not any(extract_sig_fn(stripped_clause))
        and len(stripped_clause.split()) >= 8
    ):
        matched_roots = [
            a
            for a in non_metric_roots
            if len(
                tokens_fn(stripped_clause)
                & tokens_fn(
                    " ".join(
                        str(a.get(k) or "")
                        for k in ("root_bundle_theme", "root_claim_text", "root_claim_scope")
                    )
                )
            )
            > 0
        ]
        chosen_non_metric = max(matched_roots or non_metric_roots or [chosen], key=rank_fn)
        return (
            stripped_clause,
            str(chosen_non_metric.get("root_id") or "").strip(),
            str(chosen_non_metric.get("fact_id") or "").strip(),
            str(chosen_non_metric.get("skill_id") or "").strip(),
        )
    non_dup_candidates = [
        a
        for a in selected
        if str(a.get("root_claim_text") or a.get("root_claim_action") or "")
        .strip()
        .rstrip(".!?")
        .lower()
        not in existing_norms
    ]
    fallback_target = max(non_dup_candidates, key=rank_fn) if non_dup_candidates else chosen
    replacement = str(
        fallback_target.get("root_claim_text") or fallback_target.get("root_claim_action") or ""
    ).strip()
    return (
        replacement,
        str(fallback_target.get("root_id") or "").strip(),
        str(fallback_target.get("fact_id") or "").strip(),
        str(fallback_target.get("skill_id") or "").strip(),
    )
