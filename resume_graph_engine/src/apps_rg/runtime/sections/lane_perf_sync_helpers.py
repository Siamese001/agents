"""Companion helpers for Competencies, Headline, Role Episode, and Graph Selector lanes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
    }
)
_INSURANCE_CONTEXT_TOKENS = frozenset(
    {"insurance", "brokerage", "underwriting", "claims", "guidewire", "actuarial", "carrier", "solvency"}
)
_AI_GOVERNANCE_CONTEXT_TOKENS = frozenset(
    {"agentic", "llm", "frontier", "safety", "anthropic", "guardrail", "sandbox", "route", "model"}
)


def mark_frozen_competencies_targeting(
    targeting_context: dict[str, Any],
    pp_meta: dict[str, Any],
) -> bool:
    graph_plan = pp_meta.get("selected_graph_evidence_plan")
    has_frozen = bool(isinstance(graph_plan, dict) and graph_plan.get("allocation_assignments"))
    if has_frozen:
        targeting_context["frozen_allocation_materialized"] = True
    return has_frozen


def extract_lane_targeting_kwargs(args: Any) -> dict[str, str]:
    return {
        "target_role": str(getattr(args, "target_title", "") or getattr(args, "target_role", "") or ""),
        "target_company": str(getattr(args, "target_company", "") or ""),
        "jd_text": str(getattr(args, "jd_text", "") or ""),
    }


def select_non_colliding_competency_synonym(
    worst: str,
    words: list[str],
    synonym_map: dict[str, str],
) -> str:
    sub = synonym_map.get(worst.lower(), "delivery")
    lower_words = [w.lower() for w in words]
    if sub.lower() in lower_words:
        return "operational" if "operational" not in lower_words else "enterprise"
    return sub


def score_domain_aware_target_alignment(
    target: str,
    candidate: str,
    target_terms: tuple[str, ...] | list[str],
) -> float:
    if not target or not candidate:
        return 0.0
    padded_target = f" {target} "
    padded_candidate = f" {candidate} "
    target_words = set(target.split())
    candidate_words = set(candidate.split())
    score = 0.0
    for term in target_terms:
        if term == "policy":
            if f" {term} " not in padded_target or f" {term} " not in padded_candidate:
                continue
            same_domain = bool(
                (target_words & _INSURANCE_CONTEXT_TOKENS and candidate_words & _INSURANCE_CONTEXT_TOKENS)
                or (target_words & _AI_GOVERNANCE_CONTEXT_TOKENS and candidate_words & _AI_GOVERNANCE_CONTEXT_TOKENS)
            )
            if not same_domain:
                continue
        elif term not in target or term not in candidate:
            continue
        score += 1.0
    overlap = len((target_words - _STOPWORDS) & (candidate_words - _STOPWORDS))
    score += min(overlap, 8) * 0.1
    return round(score, 6)


def format_headline_clarity_reason(clarity_pre: dict[str, Any]) -> str:
    reasons = list(clarity_pre.get("opaque_segments") or []) + list(
        clarity_pre.get("semantic_overlap_issues") or []
    )
    return "headline_pre_x1d_resume_native_clarity:" + "|".join(reasons)


def remap_trimmed_headline_claim_ledger(
    fixed_parsed: dict[str, Any],
    old_segments: tuple[str, ...],
    new_segments: list[str],
) -> None:
    ledger = fixed_parsed.get("claim_ledger")
    if not isinstance(ledger, list):
        return
    seg_map = {
        old.strip().lower(): new.strip()
        for old, new in zip(old_segments, new_segments)
        if old.strip() and new.strip()
    }
    rebuilt: list[Any] = []
    for idx, row in enumerate(ledger):
        if not isinstance(row, dict):
            rebuilt.append(row)
            continue
        nr = dict(row)
        cur = str(nr.get("claim_text") or "").strip()
        mapped = seg_map.get(cur.lower())
        if mapped:
            nr["claim_text"] = mapped
        elif idx < len(new_segments):
            nr["claim_text"] = new_segments[idx]
        rebuilt.append(nr)
    fixed_parsed["claim_ledger"] = rebuilt


def evaluate_final_headline_pre_judge_contract(
    *,
    headline_line: str,
    parsed_output: dict[str, Any] | None,
    claim_ledger: list[dict[str, Any]],
    allowed_fact_ids: set[str],
    proof_pool_metadata: dict[str, Any] | None,
    fallback_facts: list[dict[str, Any]] | None,
    word_min: int,
    word_max: int,
    word_count_fn: Any,
    has_valid_prefix_fn: Any,
    clarity_report_fn: Any,
    evaluate_grounding_fn: Any,
) -> dict[str, Any]:
    hl = str(headline_line or "").strip()
    pipe_ok = hl.count(" | ") == 3 and "\n" not in hl
    prefix_ok = bool(hl) and bool(has_valid_prefix_fn(hl))
    wc = int(word_count_fn(hl)) if hl else 0
    wc_ok = word_min <= wc <= word_max
    clarity = clarity_report_fn(hl) if hl else {"pass": False, "opaque_segments": [], "semantic_overlap_issues": ["empty_headline"]}
    pairwise_overlaps: list[str] = []
    if pipe_ok:
        tail_segs = [p.strip() for p in hl.split(" | ")[1:4]]
        seg_stems = [
            {
                w[:-1] if len(w) > 4 and w.endswith("s") else w
                for w in seg.lower().replace("-", " ").split()
                if len(w) >= 4 and w not in _STOPWORDS
            }
            for seg in tail_segs
        ]
        for i in range(len(seg_stems)):
            for j in range(i + 1, len(seg_stems)):
                shared = sorted(seg_stems[i] & seg_stems[j])
                if len(shared) >= 2 or tail_segs[i].lower() == tail_segs[j].lower():
                    pairwise_overlaps.append(f"seg{i + 2}_seg{j + 2}:{','.join(shared or ['duplicate'])}")
    if pairwise_overlaps:
        clarity = dict(clarity)
        clarity["semantic_overlap_issues"] = list(clarity.get("semantic_overlap_issues") or []) + pairwise_overlaps
        clarity["pass"] = False
    clarity_ok = bool(clarity.get("pass"))
    grounding_ok, grounding_obs, grounding_failure = evaluate_grounding_fn(
        headline_line=hl,
        parsed_output=parsed_output or {},
        claim_ledger=claim_ledger,
        proof_pool_metadata=proof_pool_metadata,
        allowed_fact_ids=allowed_fact_ids,
        fallback_facts=fallback_facts,
    )
    dict_rows = [r for r in (claim_ledger or []) if isinstance(r, dict)]
    ledger_rows_ok = bool(dict_rows) and all(
        bool(str(r.get("claim_text") or "").strip())
        and str(r.get("claim_text") or "").strip() != hl
        and any(str(fid) in allowed_fact_ids for fid in (r.get("source_fact_ids") or []))
        for r in dict_rows
    )
    issues: list[str] = []
    if not pipe_ok:
        issues.append("invalid_pipe_segment_count")
    if not prefix_ok:
        issues.append("invalid_executive_prefix")
    if not wc_ok:
        issues.append(f"word_count_out_of_range:{wc}")
    if not clarity_ok:
        for op in clarity.get("opaque_segments") or []:
            issues.append(f"opaque_segment:{op}")
        for ov in clarity.get("semantic_overlap_issues") or []:
            issues.append(f"segment_overlap:{ov}")
        if not (clarity.get("opaque_segments") or clarity.get("semantic_overlap_issues")):
            issues.append("clarity_gate_failed")
    if not ledger_rows_ok:
        issues.append("claim_ledger_ungrounded_or_malformed")
    if not grounding_ok:
        issues.append(f"literal_grounding_failed:{grounding_failure or 'ungrounded_segment'}")
    return {
        "pass": not issues,
        "headline_line": hl,
        "word_count": wc,
        "word_count_in_range": wc_ok,
        "valid_prefix": prefix_ok,
        "pipe_count_valid": pipe_ok,
        "clarity_report": clarity,
        "grounding_ok": bool(grounding_ok),
        "grounding_failure": str(grounding_failure or ""),
        "grounding_observation": grounding_obs,
        "ledger_rows_grounded": ledger_rows_ok,
        "issues": issues,
    }


def execute_headline_judges_with_final_display_gate(
    *,
    headline_line: str,
    parsed: dict[str, Any] | None,
    parsed_for_x2: dict[str, Any],
    claim_ledger: list[dict[str, Any]],
    canon_doc: dict[str, Any],
    coverage: dict[str, Any],
    allowed_fact_ids: set[str],
    proof_pool_metadata: dict[str, Any] | None,
    runtime_payload: dict[str, Any],
    judge_keys: list[str],
    companion_context: str,
    judge_mode: str,
    judge_allowed_mock: bool,
    artifact_dir: Path,
    allowed_fact_packet: Any,
    target_title: str,
    target_company: str,
    word_min: int,
    word_max: int,
    word_count_fn: Any,
    has_valid_prefix_fn: Any,
    clarity_report_fn: Any,
    evaluate_grounding_fn: Any,
    coerce_segment_ledger_fn: Any,
    recite_bundle_fn: Any,
    repair_grounding_fn: Any,
    normalize_ledger_fn: Any,
    build_canon_fn: Any,
    build_coverage_fn: Any,
    run_judges_fn: Any,
    write_json_fn: Any,
) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput
    from apps_rg.runtime.judges.headline_x1d import JUDGE_RUBRIC_VERSION
    from apps_rg.runtime.judges.x1d_panel_harness import extract_x1d_diagnostic
    from apps_rg.runtime.sections.ExecutiveVoiceRepairAgent import (
        repair_section_with_executive_voice_agent,
    )

    sfp = runtime_payload.get("selected_fact_plan")
    fallback_facts = sfp.get("facts") if isinstance(sfp, dict) else None
    pre_gate = evaluate_final_headline_pre_judge_contract(
        headline_line=headline_line,
        parsed_output=parsed,
        claim_ledger=claim_ledger,
        allowed_fact_ids=allowed_fact_ids,
        proof_pool_metadata=proof_pool_metadata,
        fallback_facts=fallback_facts,
        word_min=word_min,
        word_max=word_max,
        word_count_fn=word_count_fn,
        has_valid_prefix_fn=has_valid_prefix_fn,
        clarity_report_fn=clarity_report_fn,
        evaluate_grounding_fn=evaluate_grounding_fn,
    )
    write_json_fn(artifact_dir / "headline_final_display_pre_judge_gate.json", pre_gate)

    if not pre_gate["pass"]:
        blocked = [
            JudgeOutput(
                judge_id=f"x1d_{jk}_headline",
                provider_name=jk,
                provider_key=jk,
                evaluator_mode="BLOCKED_PRE_JUDGE_GATE",
                provider_status="BLOCKED_PRE_JUDGE_DETERMINISTIC_GATE",
                model_name="deterministic_pre_judge_gate",
                provider_available=False,
                provider_blocked=True,
                exact_provider_error="; ".join(pre_gate["issues"]),
                rubric_version=JUDGE_RUBRIC_VERSION,
                pass_=False,
                decisive_failure=True,
                findings=list(pre_gate["issues"]),
                fail_reasons=list(pre_gate["issues"]),
                section_id="headline",
            ).to_dict()
            for jk in (judge_keys or ["gemini_pro", "openai_chatgpt", "anthropic_claude"])
        ]
        return headline_line, claim_ledger, canon_doc, coverage, blocked

    x1d = [
        j.to_dict()
        for j in run_judges_fn(
            headline_line=headline_line,
            claim_ledger=claim_ledger,
            judge_keys=judge_keys,
            companion_context=companion_context,
            mode=judge_mode,
            artifact_base=artifact_dir,
            deterministic_gate_summary=pre_gate,
            allowed_fact_packet=allowed_fact_packet,
        )
    ]
    hl_diag = extract_x1d_diagnostic(x1d, "headline")
    if hl_diag.get("repair_needed"):
        repaired_data, hl_repair_receipt = repair_section_with_executive_voice_agent(
            section_id="headline",
            candidate_data={"headline_line": headline_line, "claim_ledger": claim_ledger},
            diagnostic=hl_diag,
            targeting_context={"target_title": target_title, "target_company": target_company},
            mock_mode=judge_allowed_mock,
            artifact_dir=artifact_dir,
        )
        cand_hl = str(repaired_data.get("headline_line") or "").strip()
        if hl_repair_receipt.repair_succeeded and cand_hl and cand_hl != headline_line:
            all_ids = [
                str(fid)
                for row in claim_ledger
                if isinstance(row, dict)
                for fid in (row.get("source_fact_ids") or [])
                if str(fid) in allowed_fact_ids
            ]
            cand_ledger = coerce_segment_ledger_fn(cand_hl, all_ids, repaired_data.get("claim_ledger") or claim_ledger)
            cand_parsed = {**(parsed or {}), "headline_line": cand_hl, "claim_ledger": cand_ledger}
            bundles = proof_pool_metadata.get("headline_positioning_bundles") if isinstance(proof_pool_metadata, dict) else None
            if isinstance(bundles, list) and cand_ledger:
                recited, b_rec = recite_bundle_fn(
                    headline_line=cand_hl,
                    claim_ledger=cand_ledger,
                    positioning_bundles=bundles,
                    allowed_fact_ids=allowed_fact_ids,
                )
                if b_rec.get("any_changed"):
                    cand_ledger = recited
                    cand_parsed["claim_ledger"] = cand_ledger
            if cand_ledger:
                rep_led, g_rec = repair_grounding_fn(
                    headline_line=cand_hl,
                    parsed_output=cand_parsed,
                    claim_ledger=cand_ledger,
                )
                if g_rec.get("any_changed"):
                    cand_ledger = rep_led
                    cand_parsed["claim_ledger"] = cand_ledger
            rep_gate = evaluate_final_headline_pre_judge_contract(
                headline_line=cand_hl,
                parsed_output=cand_parsed,
                claim_ledger=cand_ledger,
                allowed_fact_ids=allowed_fact_ids,
                proof_pool_metadata=proof_pool_metadata,
                fallback_facts=fallback_facts,
                word_min=word_min,
                word_max=word_max,
                word_count_fn=word_count_fn,
                has_valid_prefix_fn=has_valid_prefix_fn,
                clarity_report_fn=clarity_report_fn,
                evaluate_grounding_fn=evaluate_grounding_fn,
            )
            if rep_gate["pass"]:
                headline_line = cand_hl
                claim_ledger = cand_ledger
                if isinstance(parsed, dict):
                    parsed["headline_line"] = headline_line
                    parsed["claim_ledger"] = claim_ledger
                norm_rows = normalize_ledger_fn(claim_ledger)
                canon_doc = build_canon_fn(norm_rows, parse_status="OK", invalid_reason=None)
                coverage = build_coverage_fn(headline_line, claim_ledger, allowed_fact_ids)
                parsed_for_x2["headline_line"] = headline_line
                parsed_for_x2["claim_ledger"] = claim_ledger
                parsed_for_x2["text_claim_coverage"] = coverage
                write_json_fn(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)
                write_json_fn(artifact_dir / "text_claim_coverage.json", coverage)
                rep_gate["voice_repair_accepted"] = True
                write_json_fn(artifact_dir / "headline_final_display_pre_judge_gate.json", rep_gate)
                x1d = [
                    j.to_dict()
                    for j in run_judges_fn(
                        headline_line=headline_line,
                        claim_ledger=claim_ledger,
                        judge_keys=judge_keys,
                        companion_context=companion_context,
                        mode=judge_mode,
                        artifact_base=artifact_dir,
                        deterministic_gate_summary=rep_gate,
                        allowed_fact_packet=allowed_fact_packet,
                    )
                ]
            else:
                pre_gate["voice_repair_rejected"] = {
                    "candidate_headline": cand_hl,
                    "issues": rep_gate["issues"],
                }
                write_json_fn(artifact_dir / "headline_final_display_pre_judge_gate.json", pre_gate)
    return headline_line, claim_ledger, canon_doc, coverage, x1d


def invoke_role_episode_gateway_with_usage_scope(
    *,
    artifact_dir: Path,
    run_id: str,
    sid: str,
    provider: str,
    gateway_fn: Any,
    compiled_obj: Any,
    max_output_tokens: int,
    temperature: float,
) -> Any:
    from apps_model_telemetry.external_model_usage import external_model_usage_scope

    with external_model_usage_scope(
        artifact_dir=artifact_dir,
        run_id=run_id,
        stage="L2.section_generation",
        section_id=sid,
        trace_id=run_id,
        app_id="apps_rg",
    ):
        return gateway_fn(sid, provider).generate(
            provider,
            compiled_obj,
            token_budget=max_output_tokens,
            temperature=temperature,
        )


def extract_all_headline_graph_allocations(
    parsed: dict[str, Any] | None,
    runtime_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return all mandatory whole-resume allocation rows assigned to headline."""
    plan = (
        parsed.get("selected_fact_plan")
        if isinstance(parsed, dict) and isinstance(parsed.get("selected_fact_plan"), dict)
        else runtime_payload.get("selected_fact_plan")
    )
    if not isinstance(plan, dict):
        return []
    out: list[dict[str, Any]] = []
    for row in plan.get("allocation_assignments") or []:
        if not isinstance(row, dict) or str(row.get("section_id") or "") != "headline":
            continue
        out.append(
            {
                "claim_unit_id": str(row.get("claim_unit_id") or ""),
                "root_id": str(row.get("root_id") or ""),
                "skill_id": str(row.get("skill_id") or ""),
                "root_claim_text": str(row.get("root_claim_text") or ""),
            }
        )
    return out


def compact_overlong_headline_and_ledger(
    headline_line: str,
    parsed_out: dict[str, Any],
    *,
    clarity_report_fn: Any,
) -> str:
    """Deterministically compact >=14-word 4-segment headlines into the 10..13 word window."""
    from apps_rg.runtime.claim_ledger.headline_claim_ledger import _headline_positioning_segments
    from apps_rg.runtime.sections.section_product_shape_ssot import (
        HEADLINE_MAX_CHARS,
        HEADLINE_WORD_MAX,
        HEADLINE_WORD_MIN,
    )
    from apps_rg.runtime.validators.headline_positioning_x2 import (
        POSITIONING_FAMILY_FLOOR,
        governance_signal_families_matched,
        positioning_families_matched,
    )
    from apps_rg.runtime.validators.headline_x2 import (
        has_valid_headline_prefix,
        headline_executive_abstraction_report,
        headline_word_count,
    )

    hl = str(headline_line or "").strip()
    wc = headline_word_count(hl)
    if wc <= HEADLINE_WORD_MAX or not has_valid_headline_prefix(hl) or hl.count(" | ") != 3:
        return hl
    segments = _headline_positioning_segments(hl)
    if segments is None or len(segments) != 3:
        return hl

    prefix = hl.split(" | ")[0].strip()
    had_gov = bool(governance_signal_families_matched(hl))
    had_spec = len(positioning_families_matched(hl)) >= POSITIONING_FAMILY_FLOOR
    opaque0 = set((clarity_report_fn(hl) or {}).get("opaque_segments") or [])
    new_segs = list(segments)
    modified = False
    ordered_indices = [i for i, s in enumerate(new_segs) if s in opaque0] + [
        i for i, s in enumerate(new_segs) if s not in opaque0
    ]
    for idx in ordered_indices:
        cur_line = f"{prefix} | {' | '.join(new_segs)}"
        cur_wc = headline_word_count(cur_line)
        cur_opaque = set((clarity_report_fn(cur_line) or {}).get("opaque_segments") or [])
        if cur_wc <= HEADLINE_WORD_MAX and len(cur_line) <= HEADLINE_MAX_CHARS and new_segs[idx] not in cur_opaque:
            continue
        words = new_segs[idx].split()
        if len(words) < 4:
            continue
        from apps_rg.runtime.sections.headline_repair_policy import candidate_3word_subsequences

        for candidate_seg in candidate_3word_subsequences(new_segs[idx]):
            trial_segs = list(new_segs)
            trial_segs[idx] = candidate_seg
            trial_line = f"{prefix} | {' | '.join(trial_segs)}"
            if headline_word_count(trial_line) < HEADLINE_WORD_MIN:
                continue
            if headline_executive_abstraction_report(trial_line).get("segments_missing_executive_abstraction"):
                continue
            if had_gov and not governance_signal_families_matched(trial_line):
                continue
            if had_spec and len(positioning_families_matched(trial_line)) < POSITIONING_FAMILY_FLOOR:
                continue
            trial_opaque = set((clarity_report_fn(trial_line) or {}).get("opaque_segments") or [])
            if candidate_seg in trial_opaque:
                continue
            new_segs = trial_segs
            modified = True
            break

    if not modified:
        return hl
    final_line = f"{prefix} | {' | '.join(new_segs)}"
    if not (HEADLINE_WORD_MIN <= headline_word_count(final_line) <= HEADLINE_WORD_MAX):
        return hl
    remap_trimmed_headline_claim_ledger(parsed_out, segments, new_segs)
    change_log = parsed_out.setdefault("change_log", [])
    if isinstance(change_log, list):
        change_log.append(
            {
                "operation": "headline_word_count_deterministic_compact",
                "reason": f"word_count={wc} above {HEADLINE_WORD_MAX}",
                "from": hl,
                "to": final_line,
            }
        )
    return final_line

