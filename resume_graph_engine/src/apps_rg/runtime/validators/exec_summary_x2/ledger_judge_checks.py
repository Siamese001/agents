"""Schema, bridge/JD proof hygiene, and X1D judge wiring checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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

def model_name_matches_allowed(observed_model: str | None, allowed_models: list[str]) -> bool:
    """Accept exact model pins plus provider-returned dated OpenAI aliases."""
    observed = str(observed_model or "").strip()
    if not observed:
        return False
    for allowed in allowed_models:
        model = str(allowed or "").strip()
        if not model:
            continue
        if observed == model:
            return True
        if model.startswith("gpt-") and observed.startswith(f"{model}-"):
            return True
    return False


def check_json_parse_valid(parsed_output: dict[str, Any] | None, raw_output: str | None) -> tuple[bool, str | None]:
    """Check if provider output was parsed from JSON without repair ambiguity."""
    if parsed_output is None:
        return False, "parsed_output is None - parsing failed"
    
    if raw_output is None or raw_output == "":
        return False, "raw_output is missing"

    if "```" in raw_output:
        return False, "Raw output contains markdown code fences"

    stripped = raw_output.strip()
    if not stripped.startswith("{"):
        return False, "Raw output must start with '{' (strict JSON only)"
    if not stripped.endswith("}"):
        return False, "Raw output must end with '}' (strict JSON only)"
    
    # Try to parse raw output to verify it's valid JSON
    try:
        json.loads(stripped)
    except json.JSONDecodeError as e:
        return False, f"Raw output is not valid JSON: {e}"
    
    return True, None


def check_no_extra_fields(parsed_output: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Check if model emits extra top-level fields outside the allowed schema."""
    if parsed_output is None:
        return False, "parsed_output is None"
    
    extra_fields = []
    for field in parsed_output.keys():
        if field not in ALLOWED_TOP_LEVEL_FIELDS:
            extra_fields.append(field)
    
    if extra_fields:
        return False, f"Extra unrecognized fields: {', '.join(extra_fields)}"
    return True, None


def check_material_clause_coverage(
    resume_display_text: str,
    text_claim_coverage: dict[str, Any],
    selected_facts: list[dict[str, Any]] | None,
) -> tuple[bool, str | None]:
    """Check if every material clause has support."""
    # Material clause types we care about
    material_keywords = [
        "platform", "architecture", "governance", "control",
        "retrieval", "context", "evaluation", "commercial impact",
        "team", "cycle-time", "delivery", "leadership", "senior",
        "industry", "domain", "$", "%", "revenue", "margin",
        "uptime", "cost", "month", "week", "year",
    ]
    
    sentences = split_sentences(resume_display_text)
    coverage_sentences = text_claim_coverage.get("sentences", [])
    
    unsupported_clauses = []
    
    for idx, sentence in enumerate(sentences):
        sentence_lower = sentence.lower()
        # Check if sentence contains material keywords
        is_material = any(kw in sentence_lower for kw in material_keywords)
        
        if is_material:
            # Find matching coverage row
            if idx < len(coverage_sentences):
                coverage_row = coverage_sentences[idx]
                material_claims = coverage_row.get("material_claims", [])
                has_supported_claim = any(
                    claim.get("support_status") == "SUPPORTED"
                    for claim in material_claims
                )
                if not has_supported_claim:
                    unsupported_clauses.append(sentence[:50])
    
    if unsupported_clauses:
        return False, f"Material clauses without support: {len(unsupported_clauses)}"
    return True, None


def check_metric_fact_id_granularity(text_claim_coverage: dict[str, Any]) -> tuple[bool, str | None]:
    """Ensure every metric maps to a granular metric fact ID."""
    coverage_sentences = text_claim_coverage.get("sentences", [])
    
    for row in coverage_sentences:
        material_claims = row.get("material_claims", [])
        for claim in material_claims:
            claim_text = claim.get("claim_text", "").lower()
            # Check for metrics
            has_metric = bool(
                re.search(r"\$\d+", claim_text) or  # Dollar amounts
                re.search(r"\d+%", claim_text) or  # Percentages
                re.search(r"\d+\s*(month|week|day|year|hour)", claim_text) or  # Time
                re.search(r"\d+\s*(team|staff|employee|person)", claim_text)  # Team size
            )
            if has_metric:
                source_ids = claim.get("source_fact_ids", [])
                # Check if any source ID is granular (contains metric indicator)
                has_granular = any(
                    "_metric_" in sid or "metric" in sid.lower() or 
                    any(ch.isdigit() for ch in sid)
                    for sid in source_ids
                )
                if not has_granular:
                    return False, f"Metric without granular source fact ID: {claim_text[:50]}"
    
    return True, None


def _fact_support_text_blob(fact: dict[str, Any]) -> str:
    anchor = fact.get("fact_anchor") if isinstance(fact.get("fact_anchor"), dict) else {}
    parts = [
        str(fact.get("fact_id") or ""),
        str(fact.get("candidate_fact_id") or ""),
        str(fact.get("role_episode_bundle_id") or ""),
        str(fact.get("claim_text") or ""),
        str(fact.get("achievement_summary") or ""),
        str(fact.get("domain") or ""),
        str(fact.get("claim_scope") or ""),
        str(fact.get("claim_outcome") or ""),
        str(fact.get("raw_chunk") or ""),
        str(anchor.get("resolved_raw_chunk") or ""),
        " ".join(str(x) for x in (fact.get("metric_values") or [])),
        " ".join(str(x) for x in (fact.get("metric_outcome_ids") or [])),
        " ".join(str(x) for x in (fact.get("selected_metric_ids") or [])),
    ]
    return " ".join(p for p in parts if p).lower()


def check_inferred_bridge_claims(resume_display_text: str, selected_facts: list[dict[str, Any]] | None) -> tuple[bool, str | None]:
    """Check for unsupported bridge language in text."""
    text_lower = resume_display_text.lower()
    
    # Build set of supported phrases from selected facts
    supported_phrases = set()
    if selected_facts:
        for fact in selected_facts:
            if not isinstance(fact, dict):
                continue
            combined = _fact_support_text_blob(fact)
            for phrase in INFERRED_BRIDGE_PHRASES:
                if phrase in combined:
                    supported_phrases.add(phrase)
    
    unsupported_phrases = []
    for phrase in INFERRED_BRIDGE_PHRASES:
        if phrase in text_lower and phrase not in supported_phrases:
            unsupported_phrases.append(phrase)
    
    if unsupported_phrases:
        return False, f"Unsupported bridge phrases: {', '.join(unsupported_phrases)}"
    return True, None


def check_jd_as_proof_zero(claim_ledger: list[dict[str, Any]], jd_text: str) -> tuple[bool, str | None]:
    """Block JD-derived experience claims."""
    for claim in claim_ledger:
        source_ids = claim.get("source_fact_ids", [])
        for sid in source_ids:
            if "jd" in sid.lower() or "target_role" in sid.lower() or "jd_only" in sid.lower():
                return False, f"JD-derived claim found: {sid}"
    return True, None


def check_briefing_as_proof_zero(claim_ledger: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """Block briefing-derived candidate claims."""
    for claim in claim_ledger:
        source_ids = claim.get("source_fact_ids", [])
        for sid in source_ids:
            if "briefing" in sid.lower() or "company_brief" in sid.lower():
                return False, f"Briefing-derived claim found: {sid}"
    return True, None


def check_target_title_inflation(resume_display_text: str, target_company: str, target_role: str | None = None) -> tuple[bool, str | None]:
    """Block inflated target-title framing."""
    text_lower = resume_display_text.lower()
    
    # Check if target company name appears with "at" or similar implying employment
    if target_company:
        company_lower = target_company.lower().strip()
        if company_lower:
            # Check for patterns like "SVP at {company}" or "CTO at {company}"
            patterns = [
                rf"\b(svp|cto|cfo|ceo|vp|director|head)\s+at\s+{re.escape(company_lower)}",
                rf"\bat\s+{re.escape(company_lower)}\b.*\b(svp|cto|cfo|ceo|vp|director|head)\b",
            ]
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return False, f"Target title inflation detected: claims role at {target_company}"
    
    return True, None


def check_unsupported_industry_claims(resume_display_text: str, selected_facts: list[dict[str, Any]] | None) -> tuple[bool, str | None]:
    """Block unsupported industry/domain claims."""
    text_lower = resume_display_text.lower()
    
    # Build set of supported industry phrases from selected facts
    supported_industries = set()
    if selected_facts:
        for fact in selected_facts:
            if not isinstance(fact, dict):
                continue
            combined = _fact_support_text_blob(fact)
            for industry in INDUSTRY_DOMAIN_CLAIMS:
                if industry in combined:
                    supported_industries.add(industry)
            if "banking" in combined or "financial_services" in combined or "financial services" in combined:
                supported_industries.update({"banking", "financial services", "regulated industries"})
            if "insurance" in combined or "insurtech" in combined:
                supported_industries.update({"insurance", "financial services", "regulated industries"})
    
    unsupported_industries = []
    for industry in INDUSTRY_DOMAIN_CLAIMS:
        if industry in text_lower and industry not in supported_industries:
            unsupported_industries.append(industry)
    
    if unsupported_industries:
        return False, f"Unsupported industry claims: {', '.join(unsupported_industries)}"
    return True, None


def check_x1d_judge_packet_hash_uniform(
    x1d_judges: list[dict[str, Any]] | None,
) -> tuple[bool, str | None]:
    """Every MODEL_BACKED judge must grade the same judge_packet_hash / input_hash."""
    hashes: set[str] = set()
    for judge in x1d_judges or []:
        if not isinstance(judge, dict):
            continue
        if str(judge.get("evaluator_mode") or "") != "MODEL_BACKED":
            continue
        if judge.get("provider_blocked"):
            continue
        h = str(judge.get("judge_packet_hash") or judge.get("input_hash") or "").strip()
        if h:
            hashes.add(h)
    if len(hashes) <= 1:
        return True, None
    return False, f"multiple judge_packet_hash values across panel: {sorted(hashes)}"


def append_executive_summary_x1d_x2_gate_dicts(
    *,
    x1d_judges: list[dict[str, Any]] | None,
    artifacts_dir: Path,
    required_providers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """X1D presence/schema gates — run only after post-X2 judge phase."""
    out: list[dict[str, Any]] = []

    def _row(gate_id: str, passed: bool, observed: Any, threshold: Any, reason: str | None) -> None:
        out.append(
            {
                "gate_id": gate_id,
                "gate_type": "deterministic",
                "pass": passed,
                "observed_value": observed,
                "threshold": threshold,
                "failure_reason": None if passed else reason,
                "evidence_ref": gate_id,
            }
        )

    required = (
        [str(p).strip() for p in required_providers if str(p).strip()]
        if required_providers is not None
        else required_judges_for_section("executive_summary")
    )
    judges_present_ok, judges_present_reason = check_judge_rows_present(
        x1d_judges, required_providers=required
    )
    _row(
        "x2_x1d_required_judges_present",
        judges_present_ok,
        judges_present_reason,
        None,
        judges_present_reason,
    )
    raw_responses_ok, raw_responses_reason = check_judge_raw_responses_written(artifacts_dir, x1d_judges)
    _row(
        "x2_x1d_raw_responses_written",
        raw_responses_ok,
        raw_responses_reason,
        None,
        raw_responses_reason,
    )
    if x1d_judges:
        invalid: list[str] = []
        for judge in x1d_judges:
            schema_ok, schema_reason = check_judge_schema_valid(judge)
            if not schema_ok:
                pk = judge.get("provider_key", "unknown")
                invalid.append(f"{pk}: {schema_reason}")
        x1d_schema_ok = len(invalid) == 0
        _row(
            "x2_x1d_schema_valid",
            x1d_schema_ok,
            invalid,
            [],
            None if x1d_schema_ok else "; ".join(invalid),
        )
    else:
        _row(
            "x2_x1d_schema_valid",
            False,
            "no judges",
            "judges present",
            "No X1D judges to validate.",
        )

    hash_uniform_ok, hash_uniform_reason = check_x1d_judge_packet_hash_uniform(x1d_judges)
    _row(
        "x2_x1d_judge_packet_hash_uniform",
        hash_uniform_ok,
        sorted(
            {
                str(j.get("judge_packet_hash") or j.get("input_hash") or "")
                for j in (x1d_judges or [])
                if isinstance(j, dict)
                and str(j.get("evaluator_mode") or "") == "MODEL_BACKED"
                and not j.get("provider_blocked")
            }
            - {""}
        ),
        "single_hash",
        hash_uniform_reason,
    )

    return out


def check_judge_rows_present(
    x1d_judges: list[dict[str, Any]] | None,
    *,
    required_providers: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Check if all required judge provider rows are present."""
    if x1d_judges is None:
        return False, "x1d_judges is None"

    required = list(required_providers or REQUIRED_JUDGE_PROVIDERS)
    present_providers = {j.get("provider_key") for j in x1d_judges}
    missing = [p for p in required if p not in present_providers]
    
    if missing:
        return False, f"Missing required judge providers: {', '.join(missing)}"
    return True, None


def required_judges_for_section(section_id: str) -> list[str]:
    """Per-lane required judge providers, sourced from the recalibrated ``section_judge_policy`` SSOT.

    W0-A (plan ``prompt-gate-ssot-consolidation-e7c9a2``): the Claude-base judge recalibration
    (dual panel = gemini_pro+openai_chatgpt; single panel = gemini_pro; anthropic_claude self-judge
    dropped) never propagated to the legacy module-level ``REQUIRED_JUDGE_PROVIDERS`` 3-list, so
    ``x2_x1d_required_judges_present`` demanded an ``anthropic_claude`` row no recalibrated lane emits
    and ``BLOCKS_GENERATION`` fired on a prompt<->gate disagreement. The required-judges gate must
    require exactly what the policy declares for the lane -- nothing more, nothing less.
    """
    from apps_rg.runtime.section_judge_policy import get_section_judge_policy

    return list(get_section_judge_policy(section_id).required_judge_providers)


def check_judge_raw_responses_written(artifacts_dir: Path, x1d_judges: list[dict[str, Any]] | None) -> tuple[bool, str | None]:
    """Check if raw response artifacts exist for attempted judges."""
    if x1d_judges is None:
        return False, "x1d_judges is None"
    
    missing = []
    for judge in x1d_judges:
        provider_key = judge.get("provider_key")
        raw_response_ref = judge.get("raw_response_ref")
        
        if not raw_response_ref and judge.get("evaluator_mode") in ("MODEL_BACKED", "BLOCKED_RESPONSE_PARSE_ERROR"):
            # Should have raw response for model-backed or parse error
            missing.append(f"{provider_key} (no raw_response_ref)")
    
    if missing:
        return False, f"Missing raw responses: {', '.join(missing)}"
    return True, None


def check_judge_schema_valid(judge: dict[str, Any]) -> tuple[bool, str | None]:
    """Check if a judge row has valid schema."""
    required_fields = [
        "judge_id", "provider_name", "provider_key", "evaluator_mode",
        "provider_status", "model_name", "pass", "decisive_failure",
    ]
    
    missing = [f for f in required_fields if f not in judge]
    if missing:
        return False, f"Missing fields: {', '.join(missing)}"
    
    return True, None
