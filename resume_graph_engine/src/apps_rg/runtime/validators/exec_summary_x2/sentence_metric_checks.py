"""Sentence coverage, metric matching, and roundtrip integrity checks."""

from __future__ import annotations

import json
import re
from typing import Any

from apps_rg.runtime.contracts.metric_lexical_primitives import COVERAGE_WS_RE
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
from apps_rg.runtime.validators.exec_summary_x2.narrative_grounding_checks import (
    _ledger_claim_tokens,
)

def _normalize_display_clause(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _token_overlap_matches(reference_lower: str, sentence_lower: str) -> bool:
    tokens = _ledger_claim_tokens(reference_lower)
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in sentence_lower)
    return hits >= max(1, min(3, len(tokens)))


def _display_claim_token_overlap_matches(claim_display: str, sentence_lower: str) -> bool:
    """Display ``claim`` overlap: avoid binding S6 capstone to thesis row via generic tokens only."""
    display_norm = _normalize_display_clause(claim_display)
    tokens = _ledger_claim_tokens(display_norm)
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in sentence_lower)
    need = max(1, min(3, len(tokens)))
    if hits < need:
        return False
    return (hits / len(tokens)) >= 0.45


def _row_sentence_match_strength(sentence: str, row: dict[str, Any]) -> int:
    """Score how well a ledger row binds to one display sentence (higher = display-bound)."""
    sentence_lower = sentence.lower().strip()
    claim_display = str(row.get("claim") or "").strip()
    claim_text = str(row.get("claim_text") or "").strip()

    if claim_display:
        display_norm = _normalize_display_clause(claim_display)
        sentence_norm = _normalize_display_clause(sentence)
        if display_norm == sentence_norm:
            return 100
        if display_norm in sentence_norm or sentence_norm in display_norm:
            return 90
        if _display_claim_token_overlap_matches(claim_display, sentence_lower):
            return 70

    if claim_text and _token_overlap_matches(claim_text.lower(), sentence_lower):
        return 50

    return 0


def _matching_ledger_rows_for_display_sentence(
    sentence: str,
    claim_ledger: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rows that support this sentence; prefer display ``claim`` over fact ``claim_text`` only."""
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in claim_ledger:
        strength = _row_sentence_match_strength(sentence, row)
        if strength > 0:
            scored.append((strength, row))
    if not scored:
        return []
    scored.sort(key=lambda item: item[0], reverse=True)
    best = scored[0][0]
    if best >= 70:
        top = [row for strength, row in scored if strength == best]
        return top[:1]
    return [row for strength, row in scored if strength == best]


def build_sentence_claim_coverage(
    resume_display_text: str,
    claim_ledger: list[dict[str, Any]],
    allowed_fact_ids: set[str],
) -> dict[str, Any]:
    """Map every displayed sentence to material claim support.

    Display sentences bind to ledger ``claim`` (paraphrase shown in resume_display_text);
    fact proof remains ``claim_text`` + ``source_fact_ids``. Does not invent support.
    """
    sentences = split_sentences(resume_display_text)
    coverage_rows = []
    overall_pass = True

    for idx, sentence in enumerate(sentences, 1):
        matching_claims = _matching_ledger_rows_for_display_sentence(sentence, claim_ledger)

        material_claims = []
        if not matching_claims:
            material_claims.append({
                "claim_text": sentence,
                "source_fact_ids": [],
                "support_status": "UNSUPPORTED",
                "reason": "No claim_ledger row maps to this displayed sentence.",
            })
            sentence_pass = False
            overall_pass = False
        else:
            sentence_pass = True
            for claim in matching_claims:
                claim_line = str(claim.get("claim_text") or "").strip()
                source_ids = list(claim.get("source_fact_ids") or [])
                valid_source_ids = [sid for sid in source_ids if sid in allowed_fact_ids or "_metric_" in sid]
                status = "SUPPORTED" if valid_source_ids else "UNSUPPORTED"
                if status != "SUPPORTED":
                    sentence_pass = False
                    overall_pass = False
                material_claims.append({
                    "claim_text": claim_line,
                    "source_fact_ids": source_ids,
                    "support_status": status,
                    "reason": "Mapped from claim_ledger.",
                })
        coverage_rows.append({
            "sentence_index": idx,
            "sentence_text": sentence,
            "material_claims": material_claims,
            "sentence_pass": sentence_pass,
        })

    return {"sentences": coverage_rows, "overall_pass": overall_pass}


def check_claim_ledger_row_count_matches_sentence_count(
    resume_display_text: str,
    claim_ledger: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Strategy lane: one claim_ledger row per displayed sentence."""
    n_sentences = len([s for s in split_sentences(resume_display_text) if str(s).strip()])
    n_rows = len(claim_ledger)
    if n_sentences == n_rows:
        return True, None
    return False, f"display_sentences={n_sentences} claim_ledger_rows={n_rows}"


def check_self_check_claim_ledger_consistent(
    parsed_output: dict[str, Any] | None,
    text_claim_coverage: dict[str, Any],
) -> tuple[bool, str | None]:
    """When the model asserts full ledger coverage, coverage must agree."""
    if not isinstance(parsed_output, dict):
        return True, None
    sc = parsed_output.get("self_check")
    if not isinstance(sc, dict):
        return True, None
    if sc.get("every_material_claim_in_claim_ledger") is not True:
        return True, None
    if text_claim_coverage.get("overall_pass") is True:
        return True, None
    return (
        False,
        "self_check.every_material_claim_in_claim_ledger=true but "
        "text_claim_coverage.overall_pass is false.",
    )


def ledger_row_display_claim_materialized(row: dict[str, Any], resume_display_text: str) -> bool:
    """True when ledger display ``claim`` (not fact ``claim_text`` alone) appears in resume body."""
    claim_display = str(row.get("claim") or "").strip()
    if not claim_display:
        return True
    resume_norm = _normalize_display_clause(resume_display_text)
    display_norm = _normalize_display_clause(claim_display)
    if display_norm and display_norm in resume_norm:
        return True
    return _display_claim_token_overlap_matches(claim_display, resume_display_text.lower())


def check_claim_field_maps_to_display_sentence(
    resume_display_text: str,
    claim_ledger: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Each non-empty ledger ``claim`` must corroborate resume_display_text."""
    orphans: list[str] = []
    for idx, row in enumerate(claim_ledger, 1):
        if not str(row.get("claim") or "").strip():
            continue
        if not ledger_row_display_claim_materialized(row, resume_display_text):
            orphans.append(f"row_{idx}")
    if orphans:
        return False, f"ledger claim not materialized in resume_display_text: {', '.join(orphans)}"
    return True, None


def _selected_facts_support_blob(selected_facts: list[dict[str, Any]] | None) -> str:
    parts: list[str] = []
    for fact in selected_facts or []:
        if not isinstance(fact, dict):
            continue
        parts.append(str(fact.get("claim_text") or ""))
        parts.append(str(fact.get("achievement_summary") or ""))
        parts.append(str(fact.get("metric_raw") or ""))
        parts.append(str(fact.get("text") or ""))
        for value in fact.get("metric_values") or []:
            parts.append(str(value or ""))
    return " ".join(parts).lower()


def _percent_values_from_text(text: str) -> set[str]:
    """Capture N% tokens; avoid trailing \\b after % (fails before punctuation)."""
    return set(_GRAPH_EVIDENCE_PERCENT_CAPTURE_RE.findall(str(text or "").lower()))


def _metric_tokens_from_text(text: str) -> list[str]:
    tokens: list[str] = []
    for m in _GRAPH_EVIDENCE_PERCENT_CAPTURE_RE.findall(str(text or "").lower()):
        tokens.append(f"{m}%")
    if "gross margin" in str(text or "").lower():
        tokens.append("gross margin")
    return tokens


def _north_star_signature_supported_by_blob(phrase: str, support_blob: str) -> bool:
    p = phrase.lower()
    blob = support_blob.lower()
    if p in blob:
        return True
    if p in {"gross margins", "expanding gross margins"}:
        return "gross margin expansion" in blob or "gross margins by" in blob
    return False


def check_north_star_style_example_echo_unsupported(
    resume_display_text: str,
    selected_facts: list[dict[str, Any]] | None,
) -> tuple[bool, str | None]:
    """Reject visible paste of gold-example metrics/credentials absent from selected facts."""
    blob = _selected_facts_support_blob(selected_facts)
    lower = resume_display_text.lower()
    hits: list[str] = []
    for phrase in NORTH_STAR_SIGNATURE_PHRASES:
        p = phrase.lower()
        if p in lower and not _north_star_signature_supported_by_blob(p, blob):
            hits.append(phrase)
    if hits:
        return False, "Style-example echo without selected-fact support: " + ", ".join(hits)
    return True, None


def check_raw_json_no_selected_fact_plan_echo(raw_output: str | None) -> tuple[bool, str | None]:
    """Model JSON must not echo selected_fact_plan; runtime injects it before X2."""
    if raw_output is None or not str(raw_output).strip():
        return True, None
    stripped = str(raw_output).strip()
    if not stripped.startswith("{"):
        return True, None
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return True, None
    if isinstance(obj, dict) and "selected_fact_plan" in obj:
        return (
            False,
            "Model emitted selected_fact_plan in raw JSON; runtime owns selected_fact_plan.json",
        )
    return True, None


def check_exec_summary_sentence_count_6(resume_display_text: str) -> tuple[bool, str | None]:
    """Single product shape: 4 to 6 polished sentences (target 5)."""
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MAX_SENTENCES, EXEC_SUMMARY_MIN_SENTENCES, EXEC_SUMMARY_TARGET_SENTENCES
    sentences = [s for s in split_sentences(resume_display_text) if str(s).strip()]
    n = len(sentences)
    if not (EXEC_SUMMARY_MIN_SENTENCES <= n <= EXEC_SUMMARY_MAX_SENTENCES):
        return (
            False,
            f"resume_display_text must have {EXEC_SUMMARY_MIN_SENTENCES}–{EXEC_SUMMARY_MAX_SENTENCES} sentences; found {n} "
            "(legacy 2–3 band retired)",
        )
    return True, None


def _collapse_display_whitespace(text: str) -> str:
    return COVERAGE_WS_RE.sub(" ", str(text or "")).strip()


def check_exec_summary_display_roundtrip_integrity(resume_display_text: str) -> tuple[bool, str | None]:
    """Fail when split/join mutates display text or leaves abbrev-guard control bytes."""
    text = str(resume_display_text or "").strip()
    if not text:
        return True, None
    if any(ord(ch) < 32 and ch not in ("\n", "\t") for ch in text):
        return False, "control_characters_in_resume_display_text"
    if "\x1f" in text or "\ue000" in text or "\ue001" in text:
        return False, "abbrev_guard_token_leaked_into_display_text"
    parts = [s for s in split_sentences(text) if str(s).strip()]
    joined = " ".join(parts)
    if _collapse_display_whitespace(joined) != _collapse_display_whitespace(text):
        return False, "split_sentences_join_roundtrip_mismatch"
    return True, None


def check_exec_summary_cross_sentence_metric_dedup(resume_display_text: str) -> tuple[bool, str | None]:
    """Fail when the same high-signal metric clause appears in multiple sentences."""
    sentences = split_sentences(resume_display_text)
    for _pat, label in _CROSS_SENTENCE_DEDUP_PATTERNS:
        hits = sum(1 for sent in sentences if _pat.search(sent))
        if hits > 1:
            return False, f"duplicate_metric_across_sentences:{label}:{hits}"
    return True, None


def check_c03_selected_fact_ids_claimable_subset_allowed_fact_ids(
    *,
    allowed_fact_ids: set[str] | list[str] | None,
    proof_pool_metadata: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Fail when track/C03 expansion advertises claimable facts outside the proof pool."""
    allowed = {str(x).strip() for x in (allowed_fact_ids or []) if str(x).strip()}
    if not allowed:
        return False, "missing_allowed_fact_ids"
    from apps_rg.runtime.c0.c03_allowlist_coherence import (
        collect_expansion_fact_ids,
        fact_id_in_allowed_pool,
    )

    meta = proof_pool_metadata if isinstance(proof_pool_metadata, dict) else {}
    c03 = meta.get("c03_graphrag_bound")
    track = meta.get("track_weighted_graph_expansion") or {}
    expansion_ids = collect_expansion_fact_ids(c03_bound=c03 if isinstance(c03, dict) else None, track_expansion=track)
    violations = sorted({fid for fid in expansion_ids if not fact_id_in_allowed_pool(fid, allowed)})
    filtered = meta.get("c03_filtered_out_fact_ids") or []
    if violations and not filtered:
        return False, f"claimable_outside_pool:{violations}"
    # ``filtered`` is the complete C0 context slice excluded from the claimable
    # pool; ``violations`` is only the subset that the generated expansion
    # attempted to use.  Extra, correctly filtered context facts are expected
    # and must not turn a fail-closed exclusion receipt into a false negative.
    # Every violating id must still be accounted for by the upstream filter.
    filtered_ids = {str(value).strip() for value in filtered if str(value).strip()}
    missing_from_filter = sorted(set(violations) - filtered_ids)
    if violations and missing_from_filter:
        return False, (
            f"filtered_out_mismatch:violations={violations}:filtered={filtered}:"
            f"missing={missing_from_filter}"
        )
    return True, None


def check_exec_summary_sentence_count_5_6(resume_display_text: str) -> tuple[bool, str | None]:
    """Deprecated alias — product band is exactly six sentences."""
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MAX_SENTENCES, EXEC_SUMMARY_MIN_SENTENCES, EXEC_SUMMARY_TARGET_SENTENCES
    return check_exec_summary_sentence_count_6(resume_display_text)


def check_exec_summary_sentence_count_4_5(resume_display_text: str) -> tuple[bool, str | None]:
    """Deprecated alias — product band is exactly six sentences."""
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MAX_SENTENCES, EXEC_SUMMARY_MIN_SENTENCES, EXEC_SUMMARY_TARGET_SENTENCES
    return check_exec_summary_sentence_count_6(resume_display_text)


def check_exec_summary_jd_alignment_proof_flags(
    parsed_output: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Align with headline/competencies spine: JD/briefing/companion never proof."""
    if not isinstance(parsed_output, dict):
        return False, "missing parsed output"
    jd = parsed_output.get("jd_alignment")
    if not isinstance(jd, dict):
        return False, "jd_alignment must be object"
    if jd.get("targeting_only") is not True:
        return False, "jd_alignment.targeting_only must be true"
    if "jd_used_as_proof" not in jd or jd.get("jd_used_as_proof") is not False:
        return False, "jd_used_as_proof must be present and exactly false"
    if "briefing_used_as_proof" not in jd or jd.get("briefing_used_as_proof") is not False:
        return False, "briefing_used_as_proof must be present and exactly false"
    cmp_raw = jd.get("companion_context_used_as_proof")
    if cmp_raw is True:
        return False, "companion_context_used_as_proof must not be true"
    if cmp_raw is not None and cmp_raw is not False:
        return False, "companion_context_used_as_proof must be boolean false when present"
    gt = jd.get("graph_targeting")
    if not isinstance(gt, dict):
        return False, "jd_alignment.graph_targeting required for executive_summary C0.3 posture"
    if gt.get("fallback_pillar_bridge_used") is True:
        return (
            False,
            "fallback_pillar_bridge_used=true; generic pillar bridge is not release-eligible targeting",
        )
    if gt.get("projection_source") != "sqlite_role_family_projection":
        return False, "graph targeting requires sqlite_role_family_projection"
    if gt.get("sqlite_projection_row_found") is not True:
        return False, "graph targeting requires a role_family_projection row"
    if gt.get("release_eligible_targeting_proof") is not True:
        return False, "graph targeting requires release_eligible_targeting_proof"
    if gt.get("targeting_degraded_explicit") is True:
        return False, "targeting_degraded_explicit is not release-eligible"
    return True, None
