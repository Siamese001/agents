"""14 non-overlapping deterministic X2 invariants for executive_summary_v2 (<5ms, zero text mutation)."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

MIN_SENTENCES, MAX_SENTENCES = 3, 4
MIN_CHARS, MAX_CHARS, MAX_CHARS_PER_SENTENCE, MAX_WORDS = 420, 680, 210, 110

EXEC_SUMMARY_V2_CORE_GATE_IDS: tuple[str, ...] = (
    "x2_v2_non_empty_display_text", "x2_v2_sentence_band_3_to_4", "x2_v2_visual_char_band_420_to_680",
    "x2_v2_no_first_person_pronouns", "x2_v2_no_em_dash_or_ai_punctuation", "x2_v2_no_ai_bridge_crutches",
    "x2_v2_no_abstract_noun_soup", "x2_v2_no_inanimate_subject_openers", "x2_v2_cadence_and_opener_variety",
    "x2_v2_claim_ledger_parity", "x2_v2_zero_unverified_numbers", "x2_v2_zero_unverified_vendors_or_employers",
    "x2_v2_no_jd_phrase_copy", "x2_v2_no_undefined_mga_acronym",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_ABBREV_RE = re.compile(r"\b(?:M\.S|B\.A|U\.S|Sr|Jr|Dr|Mr|Ms|Inc|Corp|Ltd|vs|e\.g|i\.e)\.$", re.IGNORECASE)
_FIRST_PERSON_RE = re.compile(r"\b(?:i|me|my|mine|myself|we|us|our|ours|ourselves)\b", re.IGNORECASE)
_AI_PUNCT_RE = re.compile(r"—|\s–\s|\s--\s|\[[a-z0-9_:-]{4,}\]", re.IGNORECASE)
_AI_CRUTCH_RE = re.compile(
    r"\b(?:in\s+parallel|building\s+on\s+that|from\s+that\s+commercial\s+base|across\s+enterprise\s+programs|"
    r"that\s+governed|at\s+the\s+same\s+time|taken\s+together|additionally|furthermore|moreover|notably|importantly)\b", re.I,
)
_ABSTRACT_SOUP_RE = re.compile(
    r"\b(?:operating-model\s+framing|governed\s+activation|durable\s+economics|strategic\s+optionality|"
    r"execution\s+substrates?|value-realization\s+flywheel|119-package|sqlite\s+wal|fts5|1024-d\s+bge-m3|"
    r"dirichlet-laplace|universal\s+write\s+gateway|six\s+mcp\s+servers)\b", re.I,
)
_INANIMATE_OPENER_RE = re.compile(
    r"^(?:platform\s+ownership|field\s+delivery|direct\s+ownership|modernization\s+playbooks?|production\s+telemetry|"
    r"architecture\s+governance|runtime\s+controls?|governance\s+frameworks?|fail-closed\s+validation\s+meshes?|"
    r"validation\s+meshes?|solution\s+accelerators?|reusable\s+(?:ai\s+)?(?:primitives|platforms?|accelerators?)|"
    r"enterprise\s+platforms?|commercial\s+(?:models?|ownership)|operational\s+(?:models?|resilience)|"
    r"the\s+(?:operating\s+model|platform|architecture|candidate|system|framework)|"
    r"this\s+(?:leader|executive|individual|candidate)|executive\s+leadership\s+architects?)\b", re.I,
)
_HUMAN_ROLE_NOUN_RE = re.compile(
    r"\b(?:executive|leader|architect|partner|director|founder|co-founder|builder|actuary|veteran|strategist|head|vp|svp|principal|officer|cto)\b", re.I,
)
_ACTIVE_HUMAN_LEAD_VERBS = frozenset({
    "architected", "automated", "built", "championed", "commercialized", "combines", "compressed", "consolidated",
    "converted", "created", "cut", "decoupled", "delivered", "deployed", "designed", "directed", "drove",
    "engineered", "established", "expanded", "forged", "founded", "co-founded", "generated", "guided", "headed",
    "implemented", "launched", "leads", "led", "managed", "mapped", "modernized", "operationalized", "orchestrated",
    "owned", "owns", "packaged", "paired", "pairs", "partnered", "pioneered", "productized", "re-architected",
    "reduced", "replatformed", "scaled", "scales", "shaped", "shipped", "spearheaded", "standardized", "steered",
    "strengthened", "structured", "transformed", "translated", "unified", "unifies",
})
_PREP_LEAD_STARTERS = frozenset({"at", "across", "within", "through", "over", "for", "in", "spanning", "combining", "pairing"})
_PARTICIPLE_TAIL_RE = re.compile(r",\s+[a-z]+ing\b", re.IGNORECASE)
_DISPLAY_NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:\s*(?:%|(?:m|b|k|tb|ms|x)\b))?", re.IGNORECASE)
_WATCHLIST_VENDORS = ("confluent", "kafka", "snowflake", "kubernetes", "spark", "palantir", "servicenow", "workday", "sap", "mulesoft", "pinecone", "weaviate", "langchain")
_TRIVIAL_SMALL_INTS = frozenset({"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"})
_WORD_TOKEN_RE = re.compile(r"[a-z0-9]+")


def split_sentences(text: str) -> list[str]:
    cleaned = " ".join(str(text or "").strip().split())
    if not cleaned:
        return []
    merged: list[str] = []
    for part in _SENTENCE_SPLIT_RE.split(cleaned):
        chunk = part.strip()
        if chunk:
            if merged and _ABBREV_RE.search(merged[-1]):
                merged[-1] = f"{merged[-1]} {chunk}"
            else:
                merged.append(chunk)
    return merged


def _sentence_has_human_agency(sentence: str) -> tuple[bool, str]:
    s = sentence.strip().lstrip("\"'(")
    if not s:
        return False, "empty_sentence"
    if _INANIMATE_OPENER_RE.search(s):
        return False, f"inanimate_datasheet_opener:{s[:48]}"
    words = [w for w in (re.sub(r"^[^a-zA-Z0-9-]+|[^a-zA-Z0-9-]+$", "", tok).lower() for tok in s.split()) if w]
    if not words:
        return False, "no_words"
    if words[0] in _ACTIVE_HUMAN_LEAD_VERBS:
        return True, "active_lead_verb"
    if _HUMAN_ROLE_NOUN_RE.search(" ".join(words[:10])):
        return True, "human_role_noun_lead"
    if words[0] in _PREP_LEAD_STARTERS and "," in s:
        after_words = [w for w in (re.sub(r"^[^a-zA-Z0-9-]+|[^a-zA-Z0-9-]+$", "", tok).lower() for tok in s.split(",", 1)[1].split()) if w]
        if after_words and (after_words[0] in _ACTIVE_HUMAN_LEAD_VERBS or bool(_HUMAN_ROLE_NOUN_RE.search(" ".join(after_words[:8])))):
            return True, "prepositional_human_verb"
    return False, f"non_human_grammatical_opener:{' '.join(words[:5])}"


def _gate(gate_id: str, passed: bool, observed: Any, threshold: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "gate_id": gate_id, "gate_type": "DETERMINISTIC_V2", "pass": bool(passed),
        "observed_value": observed, "threshold": threshold,
        "failure_reason": None if passed else (reason or f"{gate_id}_failed"), "evidence_ref": "l2_output.json",
    }


def evaluate_executive_summary_v2_x2(
    *, resume_display_text: str, claim_ledger: Sequence[Mapping[str, Any]], parsed_output: Mapping[str, Any] | None,
    allowed_fact_ids: set[str], verified_numbers: frozenset[str], verified_corpus_lower: str,
    target_company: str, jd_text: str, target_role: str = "", briefing_text: str = "",
    x1d_judges: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    text = str(resume_display_text or "").strip()
    sentences = split_sentences(text)
    char_len, word_len = len(text), len(text.split())
    max_sent_chars = max((len(s) for s in sentences), default=0)
    gates: list[dict[str, Any]] = [
        _gate("x2_v2_non_empty_display_text", bool(text), char_len, "> 0 chars", "empty_resume_display_text"),
        _gate("x2_v2_sentence_band_3_to_4", MIN_SENTENCES <= len(sentences) <= MAX_SENTENCES, len(sentences), f"{MIN_SENTENCES}-{MAX_SENTENCES} sentences", f"sentence_count={len(sentences)}"),
    ]
    char_reasons = [
        r for cond, r in (
            (not (MIN_CHARS <= char_len <= MAX_CHARS), f"total_chars={char_len} outside {MIN_CHARS}-{MAX_CHARS}"),
            (max_sent_chars > MAX_CHARS_PER_SENTENCE, f"max_sentence_chars={max_sent_chars}>{MAX_CHARS_PER_SENTENCE}"),
            (word_len > MAX_WORDS, f"word_count={word_len}>{MAX_WORDS}"),
        ) if cond
    ]
    gates.append(_gate("x2_v2_visual_char_band_420_to_680", not char_reasons, {"chars": char_len, "max_sentence_chars": max_sent_chars, "words": word_len}, f"{MIN_CHARS}-{MAX_CHARS} chars", "; ".join(char_reasons)))
    for gid, rx, label in (
        ("x2_v2_no_first_person_pronouns", _FIRST_PERSON_RE, "0 first-person pronouns"),
        ("x2_v2_no_em_dash_or_ai_punctuation", _AI_PUNCT_RE, "0 em-dashes / inline source tags"),
        ("x2_v2_no_ai_bridge_crutches", _AI_CRUTCH_RE, "0 AI transition crutches"),
        ("x2_v2_no_abstract_noun_soup", _ABSTRACT_SOUP_RE, "0 abstract noun soup / internal plumbing"),
    ):
        hit = rx.search(text)
        gates.append(_gate(gid, hit is None, hit.group(0) if hit else "none", label, f"{gid}:{hit.group(0)!r}" if hit else None))

    agency_failures = [f"S{i}:{det}" for i, s in enumerate(sentences, 1) for ok, det in (_sentence_has_human_agency(s),) if not ok]
    gates.append(_gate("x2_v2_no_inanimate_subject_openers", bool(sentences) and not agency_failures, agency_failures or "all_human_actor", "human executive actor in all sentences", "; ".join(agency_failures) or "no_sentences"))

    first_words = [re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", s.split()[0]).lower() for s in sentences if s.split()]
    sw_counts = [len(s.split()) for s in sentences]
    spread = (max(sw_counts) - min(sw_counts)) if len(sw_counts) >= 2 else 0
    ptails = len(_PARTICIPLE_TAIL_RE.findall(text))
    cad_reasons = [r for c, r in ((len(first_words) != len(set(first_words)), f"duplicate_openers:{first_words}"), (len(sentences) >= 3 and spread < 3, f"word_spread={spread}<3"), (ptails > 2, f"participle_tails={ptails}>2")) if c]
    gates.append(_gate("x2_v2_cadence_and_opener_variety", bool(sentences) and not cad_reasons, {"first_words": first_words, "word_spread": spread}, "distinct openers, >=3w spread", "; ".join(cad_reasons) or "no_sentences"))

    led_reasons: list[str] = [] if (sentences and len(claim_ledger) == len(sentences)) else [f"ledger_rows={len(claim_ledger)}!=sentences={len(sentences)}"]
    for i, row in enumerate(claim_ledger, 1):
        sids = [str(x).strip() for x in (row.get("source_fact_ids") or []) if str(x).strip()]
        if not str(row.get("claim_text") or "").strip():
            led_reasons.append(f"row_{i}_empty_claim_text")
        if not sids or any(sid not in allowed_fact_ids for sid in sids):
            led_reasons.append(f"row_{i}_invalid_source_fact_ids:{sids}")
    gates.append(_gate("x2_v2_claim_ledger_parity", not led_reasons, {"rows": len(claim_ledger), "sentences": len(sentences)}, "1 row/sentence in allowed_fact_ids", "; ".join(led_reasons)))

    unverified_nums = [
        raw.strip() for raw in _DISPLAY_NUMBER_RE.findall(text)
        for norm in (re.sub(r"\s+", "", raw.strip().lower()).rstrip("+"),)
        for bare in (norm.lstrip("$"),)
        if bare and bare not in _TRIVIAL_SMALL_INTS and norm not in verified_numbers and bare not in verified_numbers and bare not in verified_corpus_lower
    ]
    gates.append(_gate("x2_v2_zero_unverified_numbers", not unverified_nums, unverified_nums or "all_verified", "0 unverified numbers", f"unverified_numbers:{unverified_nums}" if unverified_nums else None))

    low_text = text.lower()
    vendor_v = [f"unverified_vendor:{v}" for v in _WATCHLIST_VENDORS if re.search(rf"\b{re.escape(v)}\b", low_text) and v not in verified_corpus_lower]
    co_head = (str(target_company or "").strip().lower().split() or [""])[0]
    if len(co_head) >= 4 and co_head not in {"slalom", "unify", "insurtech", "ernst", "synthetic", "enterprise"} and re.search(rf"\b(?:at|for|joined|employed\s+by)\s+{re.escape(co_head)}\b", low_text):
        vendor_v.append(f"target_company_claimed_as_employer:{co_head}")
    if target_role or jd_text or briefing_text:
        from apps_rg.runtime.validators.allocation_jd_alignment_gate import find_off_domain_clutter_hits

        for clutter_hit in find_off_domain_clutter_hits(text, target_role=target_role, jd_text=jd_text, briefing_text=briefing_text):
            vendor_v.append(f"off_domain_clutter:{clutter_hit}")
    gates.append(_gate("x2_v2_zero_unverified_vendors_or_employers", not vendor_v, vendor_v or "clean", "0 unverified vendors/employers/off-domain clutter", "; ".join(vendor_v)))

    jd_align = (parsed_output or {}).get("jd_alignment") if isinstance(parsed_output, Mapping) else {}
    jd_reasons = ["jd_or_briefing_marked_as_proof"] if isinstance(jd_align, Mapping) and (jd_align.get("jd_used_as_proof") is True or jd_align.get("briefing_used_as_proof") is True) else []
    dtoks, jtoks = _WORD_TOKEN_RE.findall(low_text), _WORD_TOKEN_RE.findall(str(jd_text or "").lower())
    if len(dtoks) >= 6 and len(jtoks) >= 6:
        jd_ngrams = {" ".join(jtoks[i : i + 6]) for i in range(len(jtoks) - 5)}
        for i in range(len(dtoks) - 5):
            span = " ".join(dtoks[i : i + 6])
            if span in jd_ngrams and span not in verified_corpus_lower:
                jd_reasons.append(f"jd_verbatim_6gram:{span!r}")
                break
    gates.append(_gate("x2_v2_no_jd_phrase_copy", not jd_reasons, jd_reasons or "clean", "0 verbatim >=6w JD spans", "; ".join(jd_reasons)))

    mga_m, def_m = re.search(r"\bMGAs?\b", text), re.search(r"managing\s+general\s+agents?", text, re.I)
    mga_ok = not mga_m or bool(def_m and def_m.start() < mga_m.start())
    gates.append(_gate("x2_v2_no_undefined_mga_acronym", mga_ok, "ok" if mga_ok else "undefined_MGA", "Managing General Agents defined before MGA", "undefined_MGA_acronym" if not mga_ok else None))

    parse_ok = isinstance(parsed_output, Mapping) and bool(text)
    gates.append(_gate("x2_json_parse_valid", parse_ok, "valid" if parse_ok else "invalid", "valid JSON object"))
    if x1d_judges is not None:
        present_ok = len(x1d_judges) >= 2
        schema_ok = present_ok and all(isinstance(j, Mapping) and j.get("score_scale") in {"0_to_5", "0_to_1"} and "pass" in j for j in x1d_judges)
        gates.append(_gate("x2_x1d_required_judges_present", present_ok, len(x1d_judges), ">=2 judges"))
        gates.append(_gate("x2_x1d_schema_valid", schema_ok, schema_ok, "valid X1D schema"))
    return gates


EXEC_SUMMARY_V2_RUNTIME_GATE_IDS: tuple[str, ...] = EXEC_SUMMARY_V2_CORE_GATE_IDS + ("x2_json_parse_valid", "x2_x1d_required_judges_present", "x2_x1d_schema_valid")
run_executive_summary_v2_x2_gates = evaluate_executive_summary_v2_x2
