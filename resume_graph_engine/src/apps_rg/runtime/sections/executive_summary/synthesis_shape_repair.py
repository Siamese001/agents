"""Synthesis shape rejection and user repair message builder."""
from __future__ import annotations

import json
import re
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *

__all__ = ['_synthesis_shape_reject_reason', '_shape_failure_count', '_regen_candidate_preferred', '_build_synthesis_repair_user']

def _synthesis_shape_reject_reason(
    resume_display_text: str,
    parsed: dict[str, Any] | None,
    *,
    selected_facts: list[dict[str, Any]] | None = None,
    selected_fact_plan: dict[str, Any] | None = None,
    jd_text: str = "",
) -> tuple[bool, str]:
    """Return (all_ok, semicolon-joined failure reasons) for pre-X2 synthesis shape."""
    from apps_rg.runtime.sections.executive_summary_composition import check_human_exec_voice
    from apps_rg.runtime.validators.executive_summary_x2 import (
        GENERIC_FILLER,
        has_jd_phrase_copy,
        check_exec_summary_evidence_utilization,
        check_exec_summary_meta_filler_patterns,
        check_exec_summary_no_credential_dump,
        check_exec_summary_no_mechanism_inventory,
        check_exec_summary_no_sentence_fragment,
        check_exec_summary_display_override_compliance,
        check_exec_summary_paragraph_max_words,
        check_exec_summary_robotic_transition_stack,
        check_exec_summary_sentence_count_6,
        check_inferred_bridge_claims,
        check_north_star_style_example_echo_unsupported,
        check_cross_fact_display_conflation,
        check_exec_summary_mechanical_opener_stack,
        check_exec_summary_stock_bridge_count,
        check_resume_display_colon_space_discipline,
        check_synthesis_quality,
        FIRST_PERSON_PATTERN,
    )
    from apps_rg.runtime.sections.executive_summary_operator_reporting import (
        check_exec_summary_s5_no_derivatives_inventory,
    )

    text = str(resume_display_text or "")
    failures: list[str] = []
    if FIRST_PERSON_PATTERN.search(text):
        failures.append("First-person pronoun found")
    if jd_text:
        jd_copied, jd_phrase = has_jd_phrase_copy(text, jd_text)
        if jd_copied and jd_phrase:
            failures.append(f"jd_phrase_copied:{jd_phrase}")
    syn_ok, syn_reason = check_synthesis_quality(text)
    if not syn_ok and syn_reason:
        failures.append(syn_reason)
    mech_stack_ok, mech_stack_reason = check_exec_summary_mechanical_opener_stack(text)
    if not mech_stack_ok and mech_stack_reason:
        failures.append(mech_stack_reason)
    transition_ok, transition_reason = check_exec_summary_robotic_transition_stack(text)
    if not transition_ok and transition_reason:
        failures.append(transition_reason)
    stock_ok, stock_reason = check_exec_summary_stock_bridge_count(text, max_bridges=2)
    if not stock_ok and stock_reason:
        failures.append(stock_reason)
    allowed_ids: set[str] = set()
    if selected_facts:
        for fact in selected_facts:
            if isinstance(fact, dict):
                fid = str(fact.get("fact_id") or fact.get("source_fact_id") or "").strip()
                if fid:
                    allowed_ids.add(fid)
    if isinstance(parsed, dict) and allowed_ids:
        s5_ok, s5_reason = check_exec_summary_s5_no_derivatives_inventory(
            text,
            allowed_fact_ids=allowed_ids,
            selected_facts=selected_facts,
        )
        if not s5_ok and s5_reason:
            failures.append(s5_reason)
    if isinstance(parsed, dict):
        conf_ok, conf_reason = check_cross_fact_display_conflation(
            text, list(parsed.get("claim_ledger") or [])
        )
        if not conf_ok and conf_reason:
            failures.append(conf_reason)
        from apps_rg.runtime.c0.resume_graph_claim_binding import (
            validate_claim_rows_against_resume_graph_allocation,
        )

        graph_binding_failures = validate_claim_rows_against_resume_graph_allocation(
            section_id="executive_summary",
            claim_rows=list(parsed.get("claim_ledger") or []),
            selected_fact_plan=selected_fact_plan,
        )
        failures.extend(
            f"resume_graph_claim_binding:{reason}"
            for reason in graph_binding_failures
        )
    meta_ok, meta_reason = check_exec_summary_meta_filler_patterns(text)
    if not meta_ok and meta_reason:
        failures.append(meta_reason)
    frag_ok, frag_reason = check_exec_summary_no_sentence_fragment(text)
    if not frag_ok and frag_reason:
        failures.append(frag_reason)
    if isinstance(parsed, dict):
        override_ok, override_reason = check_exec_summary_display_override_compliance(
            text,
            list(parsed.get("claim_ledger") or []),
        )
        if not override_ok and override_reason:
            failures.append(override_reason)
    colon_ok, colon_reason = check_resume_display_colon_space_discipline(text)
    if not colon_ok and colon_reason:
        failures.append(colon_reason)
    sent_ok, sent_reason = check_exec_summary_sentence_count_6(text)
    if not sent_ok and sent_reason:
        failures.append(sent_reason)
    if sent_ok and isinstance(parsed, dict):
        from apps_rg.runtime.validators.executive_summary_x2 import (
            check_claim_ledger_row_count_matches_sentence_count,
        )

        ledger = list(parsed.get("claim_ledger") or [])
        row_count_ok, row_count_reason = check_claim_ledger_row_count_matches_sentence_count(
            text, ledger
        )
        if not row_count_ok and row_count_reason:
            failures.append(f"claim_ledger_row_count:{row_count_reason}")
    util_ok, util_reason = check_exec_summary_evidence_utilization(
        text, parsed, selected_facts=selected_facts
    )
    if not util_ok and util_reason:
        failures.append(util_reason)
    bounds_ok, bounds_reason = check_exec_summary_paragraph_max_words(text, parsed)
    if not bounds_ok and bounds_reason:
        failures.append(bounds_reason)
    voice_exec_ok, voice_exec_reason = check_human_exec_voice(text)
    if not voice_exec_ok and voice_exec_reason:
        failures.append(voice_exec_reason)
    filler_hits = [p for p in GENERIC_FILLER if p in text.lower()]
    if filler_hits:
        failures.append(f"generic_filler:{','.join(filler_hits)}")
    bridge_ok, bridge_reason = check_inferred_bridge_claims(text, selected_facts)
    if not bridge_ok and bridge_reason:
        failures.append(bridge_reason)
    mech_ok, mech_reason = check_exec_summary_no_mechanism_inventory(text)
    if not mech_ok and mech_reason:
        failures.append(mech_reason)
    cred_ok, cred_reason = check_exec_summary_no_credential_dump(text)
    if not cred_ok and cred_reason:
        failures.append(cred_reason)
    if selected_facts is not None:
        star_ok, star_reason = check_north_star_style_example_echo_unsupported(text, selected_facts)
        if not star_ok and star_reason:
            failures.append(star_reason)
    if isinstance(parsed, dict):
        from apps_rg.runtime.validators.executive_summary_x2 import (
            check_claim_ledger_materialized_or_gap_excused,
        )

        ledger = list(parsed.get("claim_ledger") or [])
        gaps = list(parsed.get("gap_notes") or [])
        mat_ok, mat_reason = check_claim_ledger_materialized_or_gap_excused(
            text, ledger, gaps
        )
        if not mat_ok and mat_reason:
            failures.append(mat_reason)
    if failures:
        return False, "; ".join(failures)
    return True, ""


def _shape_failure_count(
    resume_display_text: str,
    parsed: dict[str, Any] | None,
    *,
    selected_facts: list[dict[str, Any]] | None = None,
    selected_fact_plan: dict[str, Any] | None = None,
    jd_text: str = "",
) -> int:
    ok, reason = _synthesis_shape_reject_reason(
        resume_display_text,
        parsed,
        selected_facts=selected_facts,
        selected_fact_plan=selected_fact_plan,
        jd_text=jd_text,
    )
    if ok:
        return 0
    return len([part for part in str(reason).split(";") if part.strip()])


def _regen_candidate_preferred(
    *,
    new_fail_count: int,
    new_ledger_rows: int,
    new_word_count: int,
    best_fail_count: int,
    best_ledger_rows: int,
    best_word_count: int,
    monotonicity_accepted: bool,
) -> bool:
    """Prefer candidates that improve shape without trading away weave coverage."""
    if monotonicity_accepted:
        if new_fail_count < best_fail_count:
            return True
        if new_fail_count == best_fail_count and new_ledger_rows > best_ledger_rows:
            return True
        if (
            new_fail_count == best_fail_count
            and new_ledger_rows == best_ledger_rows
            and new_word_count >= best_word_count
        ):
            return True
        return False
    # Monotonicity-rejected drafts may not replace a stronger accepted baseline.
    if new_fail_count < best_fail_count:
        return new_ledger_rows >= best_ledger_rows and new_word_count >= int(best_word_count * 0.9)
    if new_fail_count == best_fail_count:
        return new_ledger_rows > best_ledger_rows and new_word_count >= best_word_count
    return False


def _build_synthesis_repair_user(
    reject_reason: str,
    *,
    attempt_index: int,
    prior_word_count: int,
    prior_ledger_rows: int,
    last_monotonicity_rejected: bool = False,
    strategy_executive: bool = False,
    selected_fact_plan: dict[str, Any] | None = None,
) -> str:
    blob = str(reject_reason or "").lower()
    attempt_note = ""
    if attempt_index == 1:
        attempt_note = "SECOND rewrite — prior draft still failed shape gates. "
    elif attempt_index >= 2:
        attempt_note = "FINAL rewrite — prior drafts still failed shape gates. "
    length_note = ""
    if "exceeds maximum" in blob:
        length_note = (
            f"LENGTH: trim to one executive paragraph (exactly 6 sentences, max {EXEC_SUMMARY_MAX_WORDS} words) without dropping supported proof; "
            "do not remove claim_ledger rows. "
        )
    else:
        length_note = (
            f"LENGTH: keep at least {prior_word_count} words unless trimming only to fix max-word overflow; "
            "do NOT compress or shorten to fix style — expand/restructure instead. "
        )
    if last_monotonicity_rejected:
        length_note += (
            "PRIOR REGEN SHRANK OR DROPPED CLAIM ROWS — next draft must maintain or increase word count "
            f"and claim_ledger rows (minimum {prior_ledger_rows} rows, prefer 5+ when pool has 6+ facts). "
        )
    sentence_count_note = ""
    if "found 5" in blob or "found 4" in blob or "sentences; found" in blob or "sentence_count" in blob:
        sentence_count_note = (
            "SENTENCE COUNT HARD FAIL: your previous draft had the wrong number of sentences. "
            "The output MUST have EXACTLY 6 period-terminated sentences — no more, no fewer. "
            "If the fact pool is tight, SPLIT a multi-beat sentence into two: e.g. S3 governance + S4 lineage outcome. "
            "Do NOT compress to 5 to 'fit' facts — add an S6 forward synthesis that is NOT a recap. "
        )
    utilization_note = ""
    if "claim_ledger_rows" in blob or "need_at_least" in blob or "sentences" in blob:
        utilization_note = (
            "EVIDENCE_WEAVE: add claim_ledger OBJECT rows (one per major sentence) with distinct source_fact_ids "
            "from selected_fact_plan; weave unused high-confidence facts into prose — no repeated sentence themes. "
            "Always produce exactly 6 sentences regardless of pool size — split multi-beat sentences to reach 6. "
        )
    mechanism_note = ""
    if (
        "mechanism_inventory" in blob
        or "mechanism inventory" in blob
        or "mechanism_comma_list" in blob
        or "mechanism_list_through_connector" in blob
        or "mechanism_chain_inventory" in blob
    ):
        mechanism_note = (
            "MECHANISM_CONTROL: sentence 1 = thesis + operating domain ONLY (no routing/orchestration/GraphRAG list). "
            "Max two mechanism terms in any later sentence, only when verbatim in facts. "
            "A sentence with two mechanism terms MUST NOT also contain two or more commas; "
            "rewrite it as one plain causal clause instead of a coordinated inventory. "
            "Do not repeat the same platform sentence twice. "
        )
    meta_note = ""
    if (
        "meta or filler" in blob
        or "this individual" in blob
        or "leadership profile" in blob
        or "can translate into" in blob
        or "additionally" in blob
    ):
        meta_note = (
        "VOICE: third-person executive (Technology strategy executive who… / Enterprise technology leader who… / Led…); "
        "avoid narrow 'engineering executive' opener when TARGET_TITLE is SVP IT strategy; "
        "no Additionally/Furthermore openers; no \"with extensive experience\" opener; "
        "no cover-letter meta phrasing such as \"this leadership profile\" or \"can translate into\". "
        )
    jd_copy_note = ""
    if "jd_phrase_copied" in blob:
        jd_copy_note = (
            "JD PHRASE COPY HARD FAIL: your draft copied 5+ consecutive words verbatim from JD_TEXT "
            "(e.g. 'sustainable governed scalable agentic workforce'). JD_TEXT is targeting framing ONLY — "
            "NEVER lift its phrasing into resume_display_text. Rewrite the offending sentence (usually S6) "
            "as a fact-grounded forward synthesis using an ALLOWED source_fact_id (e.g. fact_exec_002 "
            "team-scale / commercialization), not JD vocabulary. Paraphrase any targeting concept into "
            "your own executive register. "
        )
    filler_note = ""
    if "generic_filler" in blob or "proven track record" in blob or "bridge phrases" in blob:
        filler_note = (
            'FORBIDDEN PHRASES: "proven track record", "results-driven", "seasoned executive", '
            '"dynamic leader", "strategic leader" — use fact-backed outcomes instead. '
        )
    conflation_note = ""
    if (
        "cross_fact_display_conflation" in blob
        or "mechanical_opener_stack" in blob
        or "too_many_source_fact_ids" in blob
    ):
        conflation_note = (
            "ATTRIBUTION: one major proof theme per sentence — do NOT merge governed AI platform "
            "(fact_engineering_platform_001) with Basel/CCAR 40% reporting-error reduction "
            "(fact_governance_003) or margin expansion (fact_engineering_platform_006) in one causal line. "
            "Do not pack more than three source_fact_ids into a single claim_ledger row; split over-compressed alliance, "
            "platform architecture, and infrastructure themes into separate readable sentences. "
            "Weave team 8-to-28 scale (fact_exec_002) into commercialization when selected. "
            "Vary sentence openers; no Led/Successfully/Also/Built chains. "
        )
    graph_binding_note = ""
    if "resume_graph_claim_binding" in blob:
        plan = selected_fact_plan if isinstance(selected_fact_plan, dict) else {}
        facts_by_root: dict[str, list[str]] = {}
        for fact in plan.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            root_id = str(
                fact.get("role_episode_bundle_id") or fact.get("fact_id") or ""
            ).strip()
            if not root_id:
                continue
            aliases = {
                str(value).strip()
                for value in (
                    fact.get("fact_id"),
                    *list(fact.get("allowed_graph_evidence_ids") or []),
                    *list(fact.get("linked_identity_fact_ids") or []),
                    *list(fact.get("linked_source_fact_ids") or []),
                    *list(fact.get("graph_skill_node_ids") or []),
                    *list(fact.get("metric_outcome_ids") or []),
                )
                if str(value or "").strip()
            }
            facts_by_root[root_id] = sorted(aliases)
        root_groups = "; ".join(
            f"{root}=[{','.join(ids)}]" for root, ids in sorted(facts_by_root.items())
        )
        graph_binding_note = (
            "GRAPH ALLOCATION ROOT HARD FAIL: a causal sentence may not combine source_fact_ids "
            "from different allocated graph roots. Rewrite each failed claim as one root-supported "
            "thought; remove unrelated source ids from that row or move the material to a separate "
            "sentence while preserving exactly six rows/sentences. Do not imply that one root caused "
            f"another root's outcome. SAME-ROOT GROUPS: {root_groups}. "
        )
    stock_bridge_note = ""
    if "stock_bridge_stack" in blob or "robotic_transition_stack" in blob:
        stock_bridge_note = (
            "TRANSITIONS: At most TWO stock bridges in S2–S5 (From that / Against that / Complementing that / "
            "Building on that / Through that / With that governance). Use approved non-stock openers "
            "(From that commercial base / Against that lineage backdrop / In parallel). "
            "Do not chain synthetic 'Through that...', 'That operating foundation...', and 'Building on that...' openers; "
            "use concrete subjects and plain causal flow instead. "
        )
    s5_note = ""
    if "derivatives_inventory" in blob or "derivatives pricing" in blob:
        s5_note = (
            "S5: One clause pairing FSA-chartered quantitative foundation (fact_quant_hpc_003) with the "
            "allowed HPC stress-testing percent from fact_quant_hpc_001 in the SAME sentence — "
            "no derivatives-pricing or multi-Greek inventory lists. "
        )
    svp_note = ""
    if strategy_executive:
        from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
            format_synthesis_repair_directive,
        )

        svp_note = format_synthesis_repair_directive(strategy_executive=True)
    return (
        f"SYNTHESIS REJECTED: {reject_reason}. {attempt_note}{sentence_count_note}{length_note}{utilization_note}"
        f"{mechanism_note}{meta_note}{jd_copy_note}{filler_note}{conflation_note}{graph_binding_note}{stock_bridge_note}{s5_note}{svp_note}"
        "Return a NEW complete JSON object (RAW JSON only; first char {, last char }). "
        f"Rewrite resume_display_text as exactly 6 period-delimited sentences (one executive paragraph, max {EXEC_SUMMARY_MAX_WORDS} words), "
        "fit_to_evidence integrated narrative — not 4 compressed sentences; do not pad with filler. "
        "Sentence 1 must be grammatically complete; vary openers (avoid six Led/Built/Delivered chains). "
        "No certification labels in display text. "
        "FORBIDDEN: \"this individual\", \"this executive\", \"the candidate\", "
        "\"this leadership profile\", \"can translate into\", "
        "Additionally/Furthermore as sentence openers, "
        "\"An experienced engineering executive with a strong background\", "
        "\"An experienced technology strategy executive with a demonstrated ability\", recruiter filler. "
        "NEVER name TARGET_COMPANY in resume_display_text. "
        "Do NOT use label: detail stitching; no credential/certification dump. "
        "Do NOT end on Fellow of the Society of Actuaries, AWS Certified, Databricks, or credential inventories. "
        "Prioritize platform, governance, commercial, and scale facts from selected_fact_plan. "
        "Use ONLY selected facts for proof; JD and briefing are targeting-only. "
        "THIRD PERSON ONLY. Keep jd_used_as_proof=false. "
        "Expand claim_ledger when adding new supported claims; never emit flat fact-id strings only."
    )

