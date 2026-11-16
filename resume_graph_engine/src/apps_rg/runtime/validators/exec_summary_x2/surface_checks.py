"""Display surface, fragment, stacking, and bridge pattern checks for executive summary X2."""

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
    EXEC_SUMMARY_INTERNAL_PLUMBING_BANNED_SUBSTRINGS,
    EXEC_SUMMARY_MECHANICAL_OPENERS,
    EXEC_SUMMARY_ROBOTIC_TRANSITION_PREFIXES,
    EXEC_SUMMARY_STUTTERED_STEM_PATTERNS,
    EXEC_SUMMARY_WEAK_S1_SUBJECT_OPENERS,
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

def check_exec_summary_no_sentence_fragment(
    resume_display_text: str,
) -> tuple[bool, str | None]:
    """Reject executive summary display text that contains a grammatical fragment."""
    fragments: list[str] = []
    for i, sent in enumerate(split_sentences(resume_display_text)):
        sent_stripped = sent.strip()
        if not sent_stripped:
            continue
        if sent_stripped[0].isalpha() and sent_stripped[0].islower():
            fragments.append(f"S{i + 1}(lowercase_sentence_start): {sent_stripped[:80]}")
            continue
        if _SUBJECTLESS_VERB_OPENER_RE.search(sent_stripped):
            fragments.append(f"S{i + 1}(subjectless_verb_opener): {sent_stripped[:80]}")
            continue
        if _PARTICIPIAL_OPENER_RE.search(sent_stripped):
            fragments.append(f"S{i + 1}(participial_fragment): {sent_stripped[:80]}")
            continue
        if not _FINITE_VERB_RE.search(sent_stripped):
            fragments.append(f"S{i + 1}(no_finite_verb): {sent_stripped[:80]}")
    if fragments:
        return False, f"Sentence fragment(s) detected in resume_display_text: {fragments}"
    return True, None


_DISPLAY_OVERRIDE_REQUIRED_SUBSTRINGS: dict[str, str] = {
    "fact_quant_hpc_003": "fsa-chartered actuarial work in capital modeling",
}


def check_exec_summary_display_override_compliance(
    resume_display_text: str,
    claim_ledger: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """When a DISPLAY_OVERRIDE fact is cited, require its stable middle anchor in display prose."""
    from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
        FACT_C0_DISPLAY_OVERRIDES,
    )

    low = str(resume_display_text or "").lower()
    cited: set[str] = set()
    for row in claim_ledger:
        if not isinstance(row, dict):
            continue
        for fid in row.get("source_fact_ids") or []:
            base = str(fid).split("_metric_")[0]
            if base:
                cited.add(base)
    missing: list[str] = []
    for fid in FACT_C0_DISPLAY_OVERRIDES:
        if fid not in cited:
            continue
        anchor = _DISPLAY_OVERRIDE_REQUIRED_SUBSTRINGS.get(fid, "")
        if anchor and anchor not in low:
            missing.append(f"{fid} missing anchor '{anchor}'")
    if missing:
        return False, "DISPLAY_OVERRIDE compliance failed: " + "; ".join(missing)
    return True, None


def check_judge_packet_display_override_parity(
    *,
    judge_allowed_fact_packet: list[dict[str, Any]] | None,
    cited_fact_ids: list[str] | set[str] | None,
) -> tuple[bool, str | None]:
    """Verify every cited fact with a C0 display override carries display_override_text in the judge packet.

    Closes Bug:ExecSummaryJudgeDisplayOverrideInvisible by failing the lane closed when the X1D
    judge packet rows lose the FACT_C0_DISPLAY_OVERRIDES substrate that PROVIDER_MODEL receives. Symmetry
    requirement: gen-prompt DISPLAY_OVERRIDE present <=> judge-packet display_override_text present.
    """
    from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
        FACT_C0_DISPLAY_OVERRIDES,
    )

    rows = judge_allowed_fact_packet or []
    cited_raw = list(cited_fact_ids or [])
    cited: set[str] = set()
    for fid in cited_raw:
        s = str(fid).strip()
        if not s:
            continue
        cited.add(s)
        base = s.split("_metric_")[0]
        if base:
            cited.add(base)
    packet_overrides_by_fid: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("fact_id") or "").strip()
        if not fid:
            continue
        text = str(row.get("display_override_text") or "").strip()
        if text:
            packet_overrides_by_fid[fid] = text
    missing: list[str] = []
    for fid, expected in FACT_C0_DISPLAY_OVERRIDES.items():
        if fid not in cited:
            continue
        expected_clean = str(expected or "").strip()
        if not expected_clean:
            continue
        actual = packet_overrides_by_fid.get(fid, "").strip()
        if not actual:
            base = fid.split("_metric_")[0]
            actual = packet_overrides_by_fid.get(base, "").strip()
        if actual != expected_clean:
            missing.append(fid)
    if missing:
        return (
            False,
            f"judge_packet_missing_display_override_text:{','.join(sorted(missing))} "
            f"(see Bug:ExecSummaryJudgeDisplayOverrideInvisible)",
        )
    return True, None


def check_exec_summary_strategy_no_commercialization_thread(
    resume_display_text: str,
    *,
    target_role: str | None = None,
) -> tuple[bool, str | None]:
    """SVP strategy lane must not resurrect the deprecated commercialization identity thread."""
    from apps_rg.runtime.sections.executive_summary_pa import is_strategy_executive_target_title

    if not is_strategy_executive_target_title(str(target_role or "")):
        return True, "skipped_not_strategy_lane"
    if "commercialization" in str(resume_display_text or "").lower():
        return (
            False,
            "SVP strategy lane forbids 'commercialization' in resume_display_text; use digital innovation framing",
        )
    return True, None


def check_exec_summary_no_internal_plumbing_or_stutter(
    resume_display_text: str,
) -> tuple[bool, str | None]:
    """Fail immediately on internal repo micro-plumbing specs, stuttered stems, or weak S1 subject openers."""
    text = str(resume_display_text or "")
    lowered = text.lower()
    hits: list[str] = []
    for token in EXEC_SUMMARY_INTERNAL_PLUMBING_BANNED_SUBSTRINGS:
        if token in lowered:
            hits.append(f"internal_plumbing:{token}")
    for pat in EXEC_SUMMARY_STUTTERED_STEM_PATTERNS:
        if pat in lowered:
            hits.append(f"stuttered_stem:{pat}")
    if re.search(r"\bregulated[\s-]+enterprises?\s+regulatory\b", lowered):
        if not any(h.startswith("stuttered_stem:") for h in hits):
            hits.append("stuttered_stem:regulated_enterprise_regulatory")
    sentences = split_sentences(text)
    if sentences:
        s1_low = sentences[0].strip().lower()
        for opener in EXEC_SUMMARY_WEAK_S1_SUBJECT_OPENERS:
            if s1_low.startswith(opener):
                hits.append(f"weak_s1_opener:{opener.strip()}")
    if hits:
        return False, f"Executive summary internal plumbing, stutter, or weak S1 opener: {hits}"
    return True, None


def check_exec_summary_meta_filler_patterns(resume_display_text: str) -> tuple[bool, str | None]:
    lowered = resume_display_text.lower()
    hits: list[str] = []
    for phrase in EXEC_SUMMARY_FORBIDDEN_META_PHRASES:
        if phrase in lowered:
            hits.append(phrase)
    for phrase in EXEC_SUMMARY_FORBIDDEN_META_PHRASES_LOOSE:
        if phrase in lowered:
            hits.append(phrase)
    for i, sent in enumerate(split_sentences(resume_display_text)):
        words = [w.lower().strip(".,;:") for w in sent.split() if w.strip()]
        if words and words[0] in ("additionally", "furthermore", "moreover"):
            hits.append(f"sentence_{i}_opens_with_{words[0]}")
    plumbing_ok, plumbing_reason = check_exec_summary_no_internal_plumbing_or_stutter(resume_display_text)
    if not plumbing_ok and plumbing_reason:
        hits.append(plumbing_reason)
    if hits:
        return False, f"Executive summary meta or filler scaffolding: {hits}"
    return True, None


def check_resume_display_colon_space_discipline(resume_display_text: str) -> tuple[bool, str | None]:
    """Block colon-space clause stitching (claim-title : prose) in user-visible summary."""
    if ": " in resume_display_text:
        return False, "Colon-space clause stitching is forbidden in resume_display_text."
    return True, None


def check_transport_envelope_stub_false(
    artifacts_dir: Path | None,
    provider_requested: str | None,
) -> tuple[bool, str | None]:
    """Reject synthetic harness responses that set stub:true on the external model JSON envelope."""
    if str(provider_requested or "").strip().lower() != "external_claude":
        return True, None
    if artifacts_dir is None:
        return True, None
    path = artifacts_dir / "provider_response.json"
    if not path.is_file():
        return True, None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"provider_response.json unreadable for stub check: {exc}"
    nested: dict[str, Any] | None = None
    if isinstance(envelope, dict):
        pr = envelope.get("provider_response")
        nested = pr if isinstance(pr, dict) else None
        if nested is None and envelope.get("stub") is True:
            nested = envelope
    if nested is None:
        return True, None
    if nested.get("stub") is True:
        return (
            False,
            "provider_response.stub is true — synthetic/test harness; not REAL_LLM transport proof.",
        )
    return True, None


def has_jd_phrase_copy(text: str, jd_text: str, max_words: int = 4) -> tuple[bool, str | None]:
    """Detect copied JD phrases longer than max_words."""
    if not text or not jd_text:
        return False, None
    words = re.findall(r"[A-Za-z0-9#+/.]+", jd_text.lower())
    text_lower = " ".join(re.findall(r"[A-Za-z0-9#+/.]+", text.lower()))
    if len(words) <= max_words:
        return False, None
    for i in range(0, len(words) - max_words):
        phrase = " ".join(words[i : i + max_words + 1])
        if phrase and phrase in text_lower:
            return True, phrase
    return False, None


def check_exec_summary_stock_bridge_count(
    text: str,
    *,
    max_bridges: int = 2,
) -> tuple[bool, str | None]:
    """Advisory/runtime lint: at most ``max_bridges`` stock connectives in display S2–S5."""
    from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
        EXEC_SUMMARY_STOCK_BRIDGE_PREFIXES,
    )

    sentences = split_sentences(text)
    if len(sentences) < 3:
        return True, None
    body = sentences[1:5] if len(sentences) >= 6 else sentences[1:]
    hits = 0
    matched: list[str] = []
    for sentence in body:
        low = sentence.strip().lower()
        for prefix in EXEC_SUMMARY_STOCK_BRIDGE_PREFIXES:
            if low.startswith(prefix):
                hits += 1
                matched.append(prefix)
                break
    if hits > max_bridges:
        return (
            False,
            f"stock_bridge_stack:{hits}_in_s2_s5_max_{max_bridges}_matched={','.join(matched)}",
        )
    return True, None


def check_exec_summary_mechanical_opener_stack(
    text: str,
    *,
    min_hits: int = 3,
) -> tuple[bool, str | None]:
    """Fail when too many sentences start with resume bullet-chain openers."""
    sentences = split_sentences(text)
    if len(sentences) < min_hits:
        return True, None
    hits = 0
    for sentence in sentences:
        first = sentence.split()[0].lower().strip(",.;:") if sentence.split() else ""
        if first in EXEC_SUMMARY_MECHANICAL_OPENERS:
            hits += 1
    if hits >= min_hits:
        return (
            False,
            f"mechanical_opener_stack:{hits}_sentences_with_{','.join(EXEC_SUMMARY_MECHANICAL_OPENERS[:5])}_style_openers",
        )
    return True, None


def check_exec_summary_robotic_transition_stack(
    text: str,
    *,
    min_hits: int = 3,
) -> tuple[bool, str | None]:
    """Fail stacked synthetic bridge openers in S2-S5."""
    sentences = split_sentences(text)
    if len(sentences) < min_hits:
        return True, None
    body = sentences[1:5] if len(sentences) >= 6 else sentences[1:]
    matched: list[str] = []
    for sentence in body:
        low = sentence.strip().lower()
        for prefix in EXEC_SUMMARY_ROBOTIC_TRANSITION_PREFIXES:
            if low.startswith(prefix):
                matched.append(prefix)
                break
    if len(matched) >= min_hits:
        return (
            False,
            f"robotic_transition_stack:{len(matched)}_in_s2_s5_matched={','.join(matched)}",
        )
    return True, None


def _source_fact_base_id(fid: str) -> str:
    s = str(fid or "").strip()
    if "_metric_" in s:
        return s.split("_metric_", 1)[0]
    return s


def check_cross_fact_display_conflation(
    resume_display_text: str,
    claim_ledger: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Detect platform + governance (+ margin) merged into one display sentence."""
    text = str(resume_display_text or "")
    if not text.strip():
        return True, None
    gov_ids = {"fact_governance_003"}
    plat_ids = {"fact_engineering_platform_001", "fact_engineering_platform_006"}
    margin_markers = re.compile(
        r"(?:gross\s+margins?|margin\s+expansion|regulatory\s+reporting\s+errors?|40\s*%)",
        re.IGNORECASE,
    )
    platform_markers = re.compile(
        r"\b(governed\s+enterprise\s+ai\s+platform|agentic\s+ai\s+platform|enterprise\s+ai\s+platform)\b",
        re.IGNORECASE,
    )
    for sentence in split_sentences(text):
        sl = sentence.lower()
        if not margin_markers.search(sentence):
            continue
        has_platform = bool(platform_markers.search(sentence))
        ledger_bases: set[str] = set()
        for row in claim_ledger:
            if not isinstance(row, dict):
                continue
            ct = str(row.get("claim_text") or "").strip()
            if ct and ct not in sentence:
                continue
            for raw in row.get("source_fact_ids") or []:
                ledger_bases.add(_source_fact_base_id(str(raw)))
        row_has_gov = bool(ledger_bases & gov_ids) or (
            "reporting error" in sl and "40" in sl
        )
        row_has_plat = bool(ledger_bases & plat_ids) or has_platform
        if row_has_gov and row_has_plat and margin_markers.search(sentence):
            return (
                False,
                "cross_fact_display_conflation:platform_and_governance_metrics_in_one_sentence",
            )
    for row in claim_ledger:
        if not isinstance(row, dict):
            continue
        source_ids = [
            _source_fact_base_id(str(x))
            for x in (row.get("source_fact_ids") or [])
            if str(x or "").strip()
        ]
        if len(dict.fromkeys(source_ids)) > 3:
            return (
                False,
                "cross_fact_display_conflation:too_many_source_fact_ids_in_one_sentence",
            )
        bases = {_source_fact_base_id(str(x)) for x in (row.get("source_fact_ids") or [])}
        if bases & gov_ids and bases & plat_ids:
            ct = str(row.get("claim_text") or "")
            if margin_markers.search(ct) and platform_markers.search(ct):
                return (
                    False,
                    "cross_fact_display_conflation:ledger_row_merges_platform_and_governance",
                )
    return True, None


def detect_bullet_like_stacking(text: str) -> tuple[bool, str | None, int]:
    """Heuristic for one-fact-per-sentence action-verb stacking.
    
    Returns: (is_stacking, reason, consecutive_action_count)
    """
    sentences = split_sentences(text)
    if len(sentences) < 3:
        return False, None, 0
    
    action_openers = 0
    consecutive_actions = 0
    max_consecutive = 0
    
    for sentence in sentences:
        first = sentence.split()[0].lower().strip(",.;:") if sentence.split() else ""
        if first in ACTION_VERB_OPENERS:
            action_openers += 1
            consecutive_actions += 1
            max_consecutive = max(max_consecutive, consecutive_actions)
        else:
            consecutive_actions = 0
    
    # Fail if 4+ consecutive action verbs or 4+ total action openers
    if max_consecutive >= 4:
        return True, f"{max_consecutive} consecutive sentences start with action verbs (bullet pattern)", max_consecutive
    if action_openers >= 4:
        return True, f"{action_openers} sentences start with action verbs (mechanical list)", action_openers
    
    return False, None, action_openers
