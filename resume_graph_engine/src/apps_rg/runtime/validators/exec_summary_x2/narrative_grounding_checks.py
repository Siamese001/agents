"""Narrative continuity, claim ledger grounding, and artifact completeness checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.contracts.metric_lexical_primitives import surface_norm
from apps_rg.runtime.validators.exec_summary_x2.constants import (
    ACTION_VERB_OPENERS,
    ALLOWED_MODELS,
    ALLOWED_TOP_LEVEL_FIELDS,
    CREDENTIAL_CONTEXT_MARKERS,
    EM_DASH,
    EVIDENCE_UTIL_MIN_LEDGER_ROWS_WHEN_POOL_LARGE,
    EVIDENCE_UTIL_MIN_POOL_FOR_LEDGER_DEPTH,
    EVIDENCE_UTIL_MIN_POOL_FOR_THIN_SENTENCE,
    EVIDENCE_UTIL_MIN_WORDS_PER_SENTENCE_WHEN_FOUR,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES_LOOSE,
    EXEC_SUMMARY_MECHANICAL_OPENERS,
    EXEC_SUMMARY_ROBOTIC_TRANSITION_PREFIXES,
    EXECUTIVE_SUMMARY_SECTION_ID,
    EXPECTED_PA_SHELL_TEMPLATE_ID,
    EXPECTED_PROMPT_ID,
    EXPECTED_PROMPT_TEMPLATE_REF,
    FIRST_PERSON_PATTERN,
    FSA_RIGOR_MARKERS,
    FSA_WORD_RE,
    GENERIC_FILLER,
    INDUSTRY_DOMAIN_CLAIMS,
    INFERRED_BRIDGE_PHRASES,
    INLINE_SOURCE_PATTERN,
    MECHANICAL_PROOF_OPENERS,
    NORTH_STAR_SIGNATURE_PHRASES,
    POST_X2_REQUIRED_ARTIFACTS,
    POST_X2_X1D_WIRING_GATE_IDS,
    PRE_X2_REQUIRED_ARTIFACTS,
    REQUIRED_ARTIFACTS,
    REQUIRED_JUDGE_PROVIDER_KEYS,
    REQUIRED_JUDGE_PROVIDERS,
    SOURCE_SENSITIVE_PHRASES,
    VENDOR_NAMED_CERT_LABELS,
    X2GateResult,
    _CROSS_SENTENCE_DEDUP_PATTERNS,
    _FINITE_VERB_RE,
    _GRAPH_EVIDENCE_PERCENT_CAPTURE_RE,
    _GRAPH_EVIDENCE_S1_CONNECTOR_PHRASES,
    _GRAPH_EVIDENCE_S1_CONNECTOR_WORDS,
    _GRAPH_EVIDENCE_S1_MECHANISM_TERMS,
    _PARTICIPIAL_OPENER_RE,
    _SUBJECTLESS_VERB_OPENER_RE,
    resolve_section_generation_model,
    split_sentences,
)
from apps_rg.runtime.validators.exec_summary_x2.surface_checks import (
    check_exec_summary_mechanical_opener_stack,
    check_exec_summary_robotic_transition_stack,
    detect_bullet_like_stacking,
)

def check_synthesis_quality(text: str) -> tuple[bool, str | None]:
    """Check if output reads like executive synthesis vs bullet conversion.
    
    Returns: (pass, reason)
    """
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MAX_SENTENCES, EXEC_SUMMARY_MIN_SENTENCES
    if re.search(r"\bthis was achieved while\b", text, re.IGNORECASE):
        return False, "Bridge phrase 'This was achieved while' indicates bullet-like stacking"

    sentences = split_sentences(text)
    if len(sentences) < EXEC_SUMMARY_MIN_SENTENCES:
        if EXEC_SUMMARY_MIN_SENTENCES == EXEC_SUMMARY_MAX_SENTENCES:
            return (
                False,
                f"Output has {len(sentences)} sentences; executive synthesis requires exactly "
                f"{EXEC_SUMMARY_MIN_SENTENCES} sentences",
            )
        return (
            False,
            f"Output has {len(sentences)} sentences; executive synthesis requires "
            f"{EXEC_SUMMARY_MIN_SENTENCES}-{EXEC_SUMMARY_MAX_SENTENCES}",
        )
    if len(sentences) < 2:
        return False, "Output too short for executive summary"

    mechanical_hits = 0
    for sentence in sentences:
        first = sentence.split()[0].lower().strip(",.;:") if sentence.split() else ""
        if first in MECHANICAL_PROOF_OPENERS:
            mechanical_hits += 1
    if mechanical_hits >= 3:
        return False, (
            "Mechanical proof sequence detected "
            "(Productized/Designed/Strengthened/Standardized opener pattern)"
        )

    # Check for mechanical one-fact-per-sentence pattern
    is_stacking, reason, _ = detect_bullet_like_stacking(text)
    if is_stacking:
        return False, f"Sentence stacking detected: {reason}"

    mech_ok, mech_reason = check_exec_summary_mechanical_opener_stack(text)
    if not mech_ok and mech_reason:
        return False, mech_reason

    transition_ok, transition_reason = check_exec_summary_robotic_transition_stack(text)
    if not transition_ok and transition_reason:
        return False, transition_reason

    if len(sentences) >= 4:
        short_action_sentences = 0
        for sentence in sentences:
            words = sentence.split()
            if not words:
                continue
            first = words[0].lower().strip(",.;:")
            if first in ACTION_VERB_OPENERS and len(words) <= 22:
                short_action_sentences += 1
        if short_action_sentences >= 4:
            return False, "One short proof-style sentence per fact (bullet conversion pattern)"

    # Check average sentence length (executive summaries have varied length)
    avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
    if avg_len < 12:
        return False, f"Average sentence length {avg_len:.1f} words suggests choppy bullet conversion"
    
    return True, None


def check_exec_summary_partner_narrative_continuity(
    text: str,
    selected_facts: list[dict[str, Any]] | None,
) -> tuple[bool, str | None]:
    """Keep dependency-graph proof connected to an active partnership/platform arc.

    Retry 15 contained valid graph proof, but its unconnected S3 read as a technical
    detour in the whole resume. This gate activates only when the selected evidence
    itself contains both dependency-graph and partnership roots.
    """

    fact_ids = {
        str(row.get("fact_id") or row.get("candidate_fact_id") or "").strip()
        for row in selected_facts or []
        if isinstance(row, dict)
    }
    partner_arc = bool(
        {
            "reb_unify_partner_channel_cosell",
            "reb_ibm_aws_alliance_partner_cosell_gtm",
        }
        & fact_ids
    )
    if "fact_engineering_platform_002" not in fact_ids or not partner_arc:
        return True, None
    graph_sentences = [
        sentence
        for sentence in split_sentences(text)
        if "dependency graph intelligence" in sentence.casefold()
    ]
    if not graph_sentences:
        return True, None
    if any(
        "partner-platform" in sentence.casefold()
        or "partner platform" in sentence.casefold()
        or "alliance-led platform" in sentence.casefold()
        for sentence in graph_sentences
    ):
        return True, None
    return False, "dependency_graph_sentence_missing_partner_platform_bridge"


def check_exec_summary_speculative_capstone(text: str) -> tuple[bool, str | None]:
    """Reject cover-letter-style future speculation in the 4-6 sentence capstone."""
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MAX_SENTENCES, EXEC_SUMMARY_MIN_SENTENCES

    sentences = split_sentences(text)
    if not (EXEC_SUMMARY_MIN_SENTENCES <= len(sentences) <= EXEC_SUMMARY_MAX_SENTENCES):
        return True, None
    s6 = sentences[-1].casefold()
    if re.search(r"\bcan\s+guide\s+future\b|\bguide\s+future\s+partner\b", s6):
        return False, "s6_speculative_future_guidance_not_demonstrated_impact"
    return True, None


def check_claim_ledger_orphan_source_ids(
    claim_ledger: list[dict[str, Any]], allowed_fact_ids: set[str]
) -> tuple[bool, str | None]:
    """Every ledger row must cite only allowed_fact_ids (including metric-suffixed ids)."""
    for i, row in enumerate(claim_ledger):
        if not isinstance(row, dict):
            continue
        ids = row.get("source_fact_ids") or []
        if not ids:
            return False, f"claim_ledger[{i}] missing source_fact_ids"
        for sid in ids:
            if sid not in allowed_fact_ids:
                return False, f"claim_ledger[{i}] orphan source_fact_id {sid!r} (not in allowed set)"
    return True, None


def check_claim_coverage_accounting(
    resume_display_text: str,
    parsed_output: dict[str, Any] | None,
    text_claim_coverage: dict[str, Any],
    claim_ledger: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Verify coverage accounting consistency.
    
    Returns: (pass, reason)
    """
    # Count sentences in displayed text
    displayed_sentences = split_sentences(resume_display_text)
    displayed_count = len(displayed_sentences)
    
    # Count sentences in coverage
    coverage_sentences = text_claim_coverage.get("sentences", [])
    coverage_count = len(coverage_sentences)
    
    if displayed_count != coverage_count:
        return False, f"Sentence count mismatch: displayed={displayed_count}, coverage={coverage_count}"
    
    # Build set of all source_fact_ids in claim_ledger
    ledger_fact_ids = set()
    for claim in claim_ledger:
        source_ids = claim.get("source_fact_ids", [])
        ledger_fact_ids.update(source_ids)
    
    # Every sentence must have at least one material claim
    # Every material claim must map to source_fact_ids that exist in ledger
    for row in coverage_sentences:
        material_claims = row.get("material_claims", [])
        if not material_claims:
            return False, f"Sentence {row.get('sentence_index')} has no material claims"
        
        for claim in material_claims:
            source_ids = claim.get("source_fact_ids", [])
            if not source_ids:
                return False, f"Material claim has no source_fact_ids"
            # Check that at least one source fact ID is in the ledger
            if not any(sid in ledger_fact_ids or "_metric_" in sid for sid in source_ids):
                return False, f"Material claim has source_fact_ids not found in claim_ledger"
    
    return True, None


def _ledger_claim_tokens(claim_text: str) -> list[str]:
    return [t for t in surface_norm(claim_text).split() if len(t) > 3]


def ledger_row_materialized_in_display(claim: dict[str, Any], resume_display_text: str) -> bool:
    """Rough token-overlap check: claim corroborated by resume body (mirrors sentence coverage heuristics)."""
    ct = str(claim.get("claim_text") or "").strip()
    if not ct:
        return False
    resume_l = resume_display_text.lower()
    tokens = _ledger_claim_tokens(ct)
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in resume_l)
    need = max(1, min(3, len(tokens)))
    return hits >= need


def gap_notes_excuse_ledger_claim(claim: dict[str, Any], gap_notes: list[Any]) -> bool:
    """Explicit escape: gap_notes must name a source_fact_id and/or a long token from the claim."""
    if not isinstance(gap_notes, list) or not gap_notes:
        return False
    blob = " ".join(str(g) for g in gap_notes).lower()
    for sid in claim.get("source_fact_ids") or []:
        base = str(sid).split("_metric_")[0].lower()
        if len(base) > 3 and base in blob:
            return True
    for t in _ledger_claim_tokens(str(claim.get("claim_text") or "").strip())[:8]:
        if len(t) >= 8 and t in blob:
            return True
    return False


def check_claim_ledger_claim_text_non_empty(claim_ledger: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """Each ledger row must carry non-empty material claim prose (post normalize: claim_text only).

    Rows with only source_fact_ids and no claim/claim_text fail here before coverage gates.
    """
    bad_parts: list[str] = []
    for i, row in enumerate(claim_ledger):
        if not isinstance(row, dict):
            bad_parts.append(f"idx={i} source_fact_ids=[] reason=not_a_dict")
            continue
        ct = str(row.get("claim_text") or "").strip()
        if not ct:
            ids = list(row.get("source_fact_ids") or [])
            bad_parts.append(f"idx={i} source_fact_ids={ids!r}")
    if bad_parts:
        return False, "claim_ledger rows missing non-empty claim_text: " + "; ".join(bad_parts)
    return True, None


def check_claim_ledger_materialized_or_gap_excused(
    resume_display_text: str,
    claim_ledger: list[dict[str, Any]],
    gap_notes: list[Any],
) -> tuple[bool, str | None]:
    """Each claim_ledger row must appear in resume text OR be explicitly excused in gap_notes."""
    bad: list[str] = []
    for i, claim in enumerate(claim_ledger):
        if not isinstance(claim, dict):
            continue
        if ledger_row_materialized_in_display(claim, resume_display_text):
            continue
        if gap_notes_excuse_ledger_claim(claim, gap_notes):
            continue
        bad.append(f"idx={i}")
    if bad:
        return False, "claim_ledger rows not materialized in resume_display_text without gap_notes excuse: " + ", ".join(
            bad
        )
    return True, None


def _sensitive_phrase_present(text_lower: str, phrase: str) -> bool:
    """Detect phrase in lowered text without substring false positives on stems.

    Multi-word phrases use substring match. Single-token phrases use word boundaries
    so ``audit`` does not fire on ``auditability`` unless the fact or output actually
    contains the word ``audit``.
    """
    pl = phrase.lower()
    if " " in pl:
        return pl in text_lower
    return re.search(rf"\b{re.escape(pl)}\b", text_lower) is not None


def check_source_sensitive_phrases(
    text: str,
    selected_facts: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Check if sensitive phrases have direct source support.
    
    Returns: (pass, reason)
    """
    text_lower = text.lower()
    
    # Build set of supported phrases from selected facts
    supported_phrases = set()
    for fact in selected_facts:
        claim_text = fact.get("claim_text", "").lower()
        achievement = fact.get("achievement_summary", "").lower()
        combined = claim_text + " " + achievement
        
        # Check if any sensitive phrase appears in source facts
        for phrase in SOURCE_SENSITIVE_PHRASES:
            if _sensitive_phrase_present(combined, phrase):
                supported_phrases.add(phrase)
    
    # Check if any sensitive phrase in output is NOT supported
    unsupported_in_output = []
    for phrase in SOURCE_SENSITIVE_PHRASES:
        if _sensitive_phrase_present(text_lower, phrase) and phrase not in supported_phrases:
            unsupported_in_output.append(phrase)
    
    if unsupported_in_output:
        return False, f"Unsupported sensitive phrases: {unsupported_in_output}"
    
    return True, None


def check_executive_strategy_thesis(parsed_output: dict[str, Any] | None) -> tuple[bool, str | None]:
    """SVP strategy lanes require a non-empty executive_strategy_thesis before display prose."""
    if parsed_output is None:
        return False, "parsed_output is None"
    thesis = str(parsed_output.get("executive_strategy_thesis") or "").strip()
    if not thesis:
        return False, "executive_strategy_thesis missing or empty"
    if len(thesis.split()) < 8:
        return False, "executive_strategy_thesis too short for SVP strategy framing"
    return True, None


def check_required_fields(parsed_output: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Check if required L2 fields exist and are non-empty."""
    if parsed_output is None:
        return False, "parsed_output is None"
    
    required_fields = [
        "resume_display_text",
        "selected_fact_plan",
        "claim_ledger",
        "jd_alignment",
        "gap_notes",
        "change_log",
        "self_check",
        "text_claim_coverage",
    ]
    
    missing_fields = []
    empty_fields = []
    
    for field in required_fields:
        if field not in parsed_output:
            missing_fields.append(field)
        elif parsed_output[field] is None or parsed_output[field] == "":
            empty_fields.append(field)
        elif field == "claim_ledger" and not parsed_output[field]:
            empty_fields.append(field)
    
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    if empty_fields:
        return False, f"Empty required fields: {', '.join(empty_fields)}"
    
    return True, None


def check_required_artifacts(
    artifacts_dir: Path,
    *,
    include_post_x2_receipts: bool = True,
) -> tuple[bool, str | None]:
    """Check if required runtime artifacts exist."""
    missing = []
    required = REQUIRED_ARTIFACTS if include_post_x2_receipts else PRE_X2_REQUIRED_ARTIFACTS
    for artifact in required:
        artifact_path = artifacts_dir / artifact
        if not artifact_path.exists():
            missing.append(artifact)
    
    if missing:
        return False, f"Missing required artifacts: {', '.join(missing)}"
    return True, None
