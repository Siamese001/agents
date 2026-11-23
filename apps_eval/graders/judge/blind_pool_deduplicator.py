"""Five-Layer Deduplicator, Query-Input Quality Gate, and Anti-Obviousness Nuanced Answer Validator (DIE Parity+).

Enforces:
1. Self-contained natural-language query/prompt validation (`is_clear_reactable_prompt`
   and `validate_query_input_quality`) blocking bare role headers, keyword soup,
   synthetic benchmark probes, and dangling follow-ups.
2. Anti-obviousness & nuanced answer differentiation (`validate_nuanced_answer_calibration_difficulty`)
   blocking cartoon/caricature defects, noun-stack walls, and ungrounded giveaways while
   requiring `>= 2` verified source-evidence anchors and explicit multi-pillar trade-off tension.
3. Separation of `prompt_text`, `core_answer_text`, and `lineage_footer_text`.
4. Five-layer deduplication across exact `artifact_sha256`, lineage-invariant `core_answer_sha256`,
   `topic_family`, prompt Jaccard `< 0.40`, and body Jaccard `< 0.35`.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Sequence

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "is", "are", "was", "were", "do", "does", "did", "what", "who",
        "how", "why", "when", "where", "which", "for", "of", "in", "on", "to",
        "and", "or", "with", "from", "about", "across", "between", "our", "we",
        "can", "should", "have", "has", "at", "by", "into", "under", "during",
        "that", "this", "without", "while", "against", "whether", "as", "an", "a",
    }
)

_LEAD_VERBS: frozenset[str] = frozenset(
    {
        "what", "who", "how", "why", "when", "where", "which", "does", "do", "is", "are",
        "summarize", "explain", "compare", "list", "describe", "outline", "provide",
        "evaluate", "assess", "verify",
    }
)

_GENERIC_ACRONYMS: frozenset[str] = frozenset({"URL", "URLS", "API", "APIS", "SQL", "JSON", "CLI", "UI", "ID", "IDS"})

_BAD_BODY_SUBSTRINGS: tuple[str, ...] = (
    "'status':",
    '"status":',
    "'missing_fields'",
    '"missing_fields"',
    "retrieval_execution_failed",
    "x3d_allow_finish",
    "x3b_escalate_hitl",
    "x3f_block",
    "x3e_allow_evidence_only",
)

_BARE_HEADER_PREFIX_RE = re.compile(
    r"^\s*(?:target\s+role|target|role|query|prompt|section|candidate)\s*:",
    flags=re.IGNORECASE,
)

_OBVIOUS_CARICATURE_RE = re.compile(
    r"(?:\bACT\s+NOW\b|\bMUST\s+CONNECT\s+NOW\b|\bdesperately\s+seeking\b|\bforever\s+grateful\b|"
    r"\bplease\s+hire\s+me\b|\bblown\s+away\s+by\s+your\s+visionary\b|\bthree\s+PhDs\b|"
    r"\bGoldman\s+Sachs\s+sovereign\b|\[CONFIDENTIAL_BRIEF|\bholistic\s+AI\s+revolution\b|"
    r"\bdon't\s+miss\s+this\s+chance\b|!!!+)",
    flags=re.IGNORECASE,
)

VALID_NUANCE_PROFILES: frozenset[str] = frozenset(
    {
        "CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
        "SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
        "MANDATE_CONSTRAINT_OMISSION",
        "DENSE_INSIDER_SHORTHAND_OR_CADENCE",
        "FRICTION_OR_PROPORTION_MISMATCH",
    }
)

_PROMPT_LINE_RE = re.compile(r"^\s*\*\*(?:Original\s+)?Prompt:\*\*\s*(.+?)\s*$", flags=re.IGNORECASE)
_LINEAGE_SPLIT_RE = re.compile(r"\n+(?:---\s*\n+)?###\s+Evidence\s*&\s*Graph\s+Lineage\b", flags=re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"\n*<!--.*?-->\s*", flags=re.DOTALL)


def _has_named_subject_anchor(words: Sequence[str]) -> bool:
    for w in words[1:]:
        bare = w.strip("?,.:;()'\"[]")
        if len(bare) < 3 or bare.upper() in _GENERIC_ACRONYMS:
            continue
        if bare[0].isupper() or any(ch.isdigit() for ch in bare):
            return True
    return False


def _has_keyword_soup_run(clean: str, words: Sequence[str]) -> bool:
    cap_run = 0
    for w in words[1:]:
        bare = w.strip("?,.:;()'\"[]")
        if bare and bare[0].isupper():
            cap_run += 1
            if cap_run >= 4 and "?" not in clean and "," not in clean:
                return True
        else:
            cap_run = 0
    return False


def is_clear_reactable_prompt(prompt: str) -> bool:
    """Return True iff `prompt` is a clear, self-contained natural-language question or directive."""
    clean = str(prompt or "").strip()
    if len(clean) < 18 or len(clean) > 280 or "\n" in clean or "{" in clean or "}" in clean:
        return False
    if clean.lower().startswith("what is recorded about ") or _BARE_HEADER_PREFIX_RE.match(clean):
        return False
    words = clean.split()
    if len(words) < 5 or len(words) > 48:
        return False
    first = words[0].lower().rstrip(",:")
    if not (clean.endswith("?") or first in _LEAD_VERBS):
        return False
    if not _has_named_subject_anchor(words) or _has_keyword_soup_run(clean, words):
        return False
    stop_cnt = sum(1 for w in words if w.lower().strip("?,.:;()'\"[]") in _STOPWORDS)
    return (stop_cnt / len(words)) >= 0.18


def validate_query_input_quality(
    prompt: str,
    source_evidence_excerpts: Sequence[Mapping[str, Any] | str] = (),
) -> tuple[bool, list[str]]:
    """Validate that a query input is a self-contained, decision-anchored evaluation question."""
    reasons: list[str] = []
    clean = str(prompt or "").strip()
    if _BARE_HEADER_PREFIX_RE.match(clean):
        reasons.append("QUERY_BARE_HEADER_PREFIX: Query cannot be a bare 'Target Role:' or 'Target:' label.")
    if not is_clear_reactable_prompt(clean):
        reasons.append("QUERY_NOT_CLEAR_REACTABLE_PROMPT: Fails self-contained natural-language question checks.")

    words_low = {w.lower().strip("?,.:;()'\"[]") for w in clean.split()}
    criterion_tokens = {
        "grounding", "grounded", "scope", "metric", "metrics", "mandate", "governance",
        "peer", "friction", "clarity", "attribution", "coherence", "positioning",
        "licensing", "alliance", "alliances", "adoption", "compliance", "velocity",
        "tenure", "explainability", "actionable", "proportion", "concision", "evidence",
        "credible", "credibility", "differentiate", "differentiation", "authority",
        "cadence", "sequence", "factual", "factually", "accurate", "accuracy",
        "coherent", "consistent", "consistency", "chronological", "faithfulness",
        "relevance", "completeness", "actionability",
    }
    if not (words_low & criterion_tokens):
        reasons.append("QUERY_MISSING_EVALUATION_CRITERION: Query must specify a concrete evaluation dimension or tension.")

    if source_evidence_excerpts:
        ev_text = " ".join(
            (str(e.get("excerpt") or "") + " " + str(e.get("source") or ""))
            if isinstance(e, Mapping)
            else str(e)
            for e in source_evidence_excerpts
        ).lower()
        ev_tokens = {t for t in re.findall(r"[a-z0-9]{4,}", ev_text) if t not in _STOPWORDS}
        q_tokens = {t for t in re.findall(r"[a-z0-9]{4,}", clean.lower()) if t not in _STOPWORDS}
        if ev_tokens and not (q_tokens & ev_tokens):
            reasons.append("QUERY_DISCONNECTED_FROM_EVIDENCE: Query shares zero domain anchors with source evidence excerpts.")

    return len(reasons) == 0, reasons


def _has_noun_stack_wall(text: str, max_consecutive_content_words: int = 7) -> bool:
    """Detect dense 7+ consecutive content-word noun stacks with zero function words or punctuation breaks."""
    connectors = _STOPWORDS | {
        "not", "no", "all", "any", "each", "both", "more", "most", "other", "some", "such",
        "than", "too", "very", "via", "per", "over", "after", "before", "through", "while",
        "where", "when", "who", "whom", "whose", "which", "that", "these", "those", "their",
        "his", "her", "its", "our", "your", "my", "up", "out", "off", "down", "beyond",
        "hinges", "would", "could", "will", "useful", "next", "week",
    }
    for clause in re.split(r"[.!?;:,\n|()\[\]\u2014]+", text):
        run = 0
        for raw_w in clause.split():
            w = raw_w.strip("\"'").lower()
            if not w or w == "-":
                continue
            if w in connectors or any(ch.isdigit() for ch in w) or len(w) <= 3:
                run = 0
            else:
                run += 1
                if run >= max_consecutive_content_words:
                    return True
    return False


def validate_nuanced_answer_calibration_difficulty(
    core_answer_text: str,
    source_evidence_excerpts: Sequence[Mapping[str, Any] | str],
    *,
    judge_surface: str = "",
    nuance_profile: str = "",
) -> tuple[bool, list[str]]:
    """Ensure candidate answers are nuanced, grounded in source context, and free of obvious caricature giveaways."""
    reasons: list[str] = []
    clean = str(core_answer_text or "").strip()
    if not clean:
        return False, ["ANSWER_EMPTY"]

    m_car = _OBVIOUS_CARICATURE_RE.search(clean)
    if m_car:
        reasons.append(f"ANSWER_OBVIOUS_CARICATURE_DEFECT: Contains blatant giveaway token {m_car.group(0)!r}.")

    if _has_noun_stack_wall(clean, max_consecutive_content_words=7):
        reasons.append("ANSWER_NOUN_STACK_CARICATURE: Contains >= 7 consecutive unpunctuated content-word noun stack.")

    words = clean.split()
    is_headline = "headline" in str(judge_surface or "").lower()
    min_words = 10 if is_headline else 26
    if len(words) < min_words:
        reasons.append(f"ANSWER_TOO_SHALLOW: Word count {len(words)} < minimum {min_words} for nuanced evaluation.")

    if nuance_profile and nuance_profile not in VALID_NUANCE_PROFILES:
        reasons.append(f"ANSWER_INVALID_NUANCE_PROFILE: {nuance_profile!r} not in {sorted(VALID_NUANCE_PROFILES)}.")

    # Every candidate (including subtle FAIL items) must share >= 2 substantive anchors with source_evidence_excerpts
    ev_text = " ".join(
        (str(e.get("excerpt") or "") + " " + str(e.get("source") or ""))
        if isinstance(e, Mapping)
        else str(e)
        for e in (source_evidence_excerpts or ())
    ).lower()
    ev_anchors = {t for t in re.findall(r"[a-z0-9$%]{3,}", ev_text) if t not in _STOPWORDS and len(t) >= 3}
    ans_anchors = {t for t in re.findall(r"[a-z0-9$%]{3,}", clean.lower()) if t not in _STOPWORDS and len(t) >= 3}
    shared = ev_anchors & ans_anchors
    if ev_anchors and len(shared) < 2:
        reasons.append(
            f"ANSWER_UNGROUNDED_GIVEAWAY: Shares only {len(shared)} anchor(s) with source evidence (requires >= 2 so raters must cross-check evidence)."
        )

    return len(reasons) == 0, reasons


def split_prompt_core_and_lineage(raw_text: str, explicit_prompt: str = "") -> tuple[str, str, str]:
    """Split blinded text into `(prompt_text, core_answer_text, lineage_footer_text)` fail-closed on malformed bodies."""
    cleaned = _HTML_COMMENT_RE.sub("", str(raw_text or "")).strip()
    prompt = str(explicit_prompt or "").strip()
    lines = cleaned.splitlines()
    if lines:
        m = _PROMPT_LINE_RE.match(lines[0])
        if m:
            if not prompt:
                prompt = m.group(1).strip()
            cleaned = "\n".join(lines[1:]).strip()
    low = cleaned.lower()
    if not cleaned or any(tok in low for tok in _BAD_BODY_SUBSTRINGS):
        raise ValueError("Candidate body contains raw error dictionary or internal disposition dump.")
    parts = _LINEAGE_SPLIT_RE.split(cleaned, maxsplit=1)
    core_body = parts[0].strip()
    lineage_footer = f"### Evidence & Graph Lineage\n{parts[1].lstrip()}" if len(parts) > 1 else ""
    if not core_body:
        raise ValueError("Candidate core answer text is empty after lineage separation.")
    return prompt, core_body, lineage_footer


def _feature_set(text: str) -> set[str]:
    tokens = [w for w in re.findall(r"[a-z0-9]{3,}", str(text or "").lower()) if w not in _STOPWORDS]
    shingles = [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]
    return set(tokens) | set(shingles)


def compute_content_jaccard(text_a: str, text_b: str) -> float:
    """Compute token + 2-shingle Jaccard overlap in `[0.0, 1.0]`."""
    fa = _feature_set(text_a)
    fb = _feature_set(text_b)
    if not fa or not fb:
        return 0.0
    return round(len(fa & fb) / len(fa | fb), 4)


def _compute_core_sha256(core_text: str) -> str:
    norm = re.sub(r"\s+", " ", str(core_text or "").strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _is_near_duplicate(
    prompt: str,
    core_body: str,
    kept_prompts: Sequence[str],
    kept_bodies: Sequence[str],
    max_prompt_jaccard: float,
    max_body_jaccard: float,
) -> tuple[str | None, float, float]:
    max_p = max((compute_content_jaccard(prompt, kp) for kp in kept_prompts if prompt and kp), default=0.0)
    if prompt and max_p >= max_prompt_jaccard:
        return "dropped_near_duplicate_prompt", max_p, 0.0
    max_b = max((compute_content_jaccard(core_body, kb) for kb in kept_bodies if kb), default=0.0)
    if max_b >= max_body_jaccard:
        return "dropped_near_duplicate_body", max_p, max_b
    return None, max_p, max_b


def deduplicate_blind_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    existing_records: Sequence[Any] = (),
    max_prompt_jaccard: float = 0.40,
    max_body_jaccard: float = 0.35,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Enforce 5-layer deduplication across exact SHA, core SHA, topic, prompt overlap, and body overlap."""
    seen_art_shas = {
        str(getattr(r, "artifact_sha256", "")) for r in existing_records if getattr(r, "artifact_sha256", "")
    }
    seen_topics = {
        str(getattr(r, "topic_family", "")).lower() for r in existing_records if getattr(r, "topic_family", "")
    }
    seen_core_shas: set[str] = set()
    kept_prompts: list[str] = []
    kept_bodies: list[str] = []
    kept: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "input_count": len(candidates),
        "dropped_exact_or_core_sha": 0,
        "dropped_duplicate_topic": 0,
        "dropped_near_duplicate_prompt": 0,
        "dropped_near_duplicate_body": 0,
        "kept_unique_count": 0,
        "max_observed_prompt_jaccard": 0.0,
        "max_observed_body_jaccard": 0.0,
    }
    for raw in candidates:
        art_sha = str(raw.get("artifact_sha256") or "")
        core_body = str(raw.get("core_answer_text") or raw.get("blinded_text") or "")
        core_sha = _compute_core_sha256(core_body)
        topic = str(raw.get("topic_family") or "").strip().lower()
        prompt = str(raw.get("prompt_text") or "").strip()
        if art_sha in seen_art_shas or core_sha in seen_core_shas:
            stats["dropped_exact_or_core_sha"] += 1
            continue
        if topic and topic in seen_topics:
            stats["dropped_duplicate_topic"] += 1
            continue
        drop_key, obs_p, obs_b = _is_near_duplicate(
            prompt, core_body, kept_prompts, kept_bodies, max_prompt_jaccard, max_body_jaccard
        )
        if drop_key is not None:
            stats[drop_key] += 1
            continue
        stats["max_observed_prompt_jaccard"] = max(float(stats["max_observed_prompt_jaccard"]), obs_p)
        stats["max_observed_body_jaccard"] = max(float(stats["max_observed_body_jaccard"]), obs_b)
        seen_art_shas.add(art_sha)
        seen_core_shas.add(core_sha)
        if topic:
            seen_topics.add(topic)
        kept_prompts.append(prompt)
        kept_bodies.append(core_body)
        kept.append({**dict(raw), "core_answer_sha256": core_sha})
    stats["kept_unique_count"] = len(kept)
    return kept, stats


__all__ = [
    "VALID_NUANCE_PROFILES",
    "compute_content_jaccard",
    "deduplicate_blind_candidates",
    "is_clear_reactable_prompt",
    "split_prompt_core_and_lineage",
    "validate_nuanced_answer_calibration_difficulty",
    "validate_query_input_quality",
]
