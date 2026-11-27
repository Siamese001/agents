"""apps_rg-specific metric canonicalization, visibility, and lexical primitives.

Composes cross-subsystem stdlib primitives from
``infrastructure.types.metric_lexical_primitives`` with domain-specific metric
normalization, visibility matching, and stopword catalogs for C0 allocation,
section lanes, and X2 validators.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Final, Mapping, Sequence

from infrastructure.types.metric_lexical_primitives import (
    COMMON_LEXICAL_STOPWORDS,
    METRIC_DOLLAR_PAT,
    METRIC_PERCENT_PAT,
    METRIC_SCALE_PAT,
    NUMERIC_TOKEN_RE,
    SURFACE_NORM_RE,
    TOKEN_RE,
    WORD_RE,
    WORD_TOKEN_RE,
    extract_normalized_dollars,
    extract_numeric_tokens,
    normalize_dollar_token,
    surface_norm,
    tokenize_words,
)

DIGIT_LETTER_RE: Final[re.Pattern[str]] = re.compile(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)")

VISIBLE_METRIC_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\$|\busd\s*)\d+(?:\.\d+)?\s*(?:m|million|b|billion)?\b|"
    r"\b\d+(?:\.\d+)?\s*(?:%|percent\b|percentage\b|x\b|times\b)|"
    r"\b\d+(?:\.\d+)?\+?\s*(?:countries|clients|customers|partners|teams|"
    r"workflows|platforms|products|programs|markets|regions|applications|systems)\b",
    re.I,
)

METRIC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(\d+(?:\.\d+)?%|\$[\d,.]+[MBK]?|\d+\s*(?:months?|weeks?|days?)|99\.9%|6 months to 3 weeks)",
    re.IGNORECASE,
)

MATERIAL_METRIC_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\b\d+(?:\.\d+)?%|\$[\d,]+(?:\.\d+)?[MBKmbk]?)\b",
    re.IGNORECASE,
)

HOLD_METRIC_TEXT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\b(?:by|of|to|at|up to|achieving|delivering|driving|with)\s+)?"
    r"(?:\$\s*(?:15|30)\s*M\b|\b(?:25|30|35|40)\s*%)",
    re.IGNORECASE,
)

IBM_FOREIGN_METRIC_SCRUB_RE: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b99\.9\s*%", re.IGNORECASE),
    re.compile(r"\b30\s*%", re.IGNORECASE),
    re.compile(r"\b25\s*%", re.IGNORECASE),
    re.compile(r"\b50\s*%", re.IGNORECASE),
    re.compile(r"\$15\s*m(?:illion)?\b", re.IGNORECASE),
    re.compile(r"\b40\s*%", re.IGNORECASE),
)

METRIC_EQUIVALENTS: Final[dict[str, str]] = {
    "percent": "pct",
    "percentage": "pct",
    "million": "m",
    "millions": "m",
    "billion": "b",
    "billions": "b",
    "dollars": "usd",
    "dollar": "usd",
}

EXACT_METRIC_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"(?:\$|\busd\s*)(\d+(?:\.\d+)?)\s*(m|million|b|billion|k)?\b", re.I), "USD"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*(%|percent\b|percentage\b)", re.I), "PERCENT"),
    (re.compile(r"(?:<\s*)?(\d+(?:\.\d+)?)\s*(ms|milliseconds?)\b", re.I), "LATENCY_MS"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*(tb|gb)\b", re.I), "DATA_VOLUME"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s*(x|times)\b", re.I), "MULTIPLIER"),
    (
        re.compile(
            r"\b(\d+(?:\.\d+)?)\+?\s*(countries|clients|customers|partners|teams|"
            r"workflows|platforms|products|programs|markets|regions|applications|systems|"
            r"controls|records|databases|workloads|carriers|engineers|leaders)\b",
            re.I,
        ),
        "COUNT",
    ),
)


def section_allows_hold_metric_scrub(section_id: str) -> bool:
    """Scope HOLD_METRIC_TEXT_RE strictly to IBM legacy holds; never scrub approved Unify/InsurTech/EY metrics."""
    return str(section_id or "").strip().lower() in {"ibm_bullets", "ibm_narrative"}

ENTAILMENT_NUMERIC_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<currency>\$\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:mm|million|billion|thousand|bn|k|m|b)\b)?)
    | (?P<percent>\d[\d,]*(?:\.\d+)?\s*(?:%|percent\b))
    | (?P<multiplier>\d+(?:\.\d+)?\s*x\b)
    | (?P<worded>\d[\d,]*(?:\.\d+)?\s+(?:million|billion|thousand)\b)
    | (?P<bare>\d[\d,]*(?:\.\d+)?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

ENTAILMENT_NORMALIZE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\$?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<suffix>mm|million|billion|thousand|bn|k|m|b|%|percent|x)?$",
    re.IGNORECASE,
)

ENTAILMENT_SCALE_SUFFIXES: Final[dict[str, float]] = {
    "k": 1_000.0,
    "thousand": 1_000.0,
    "m": 1_000_000.0,
    "mm": 1_000_000.0,
    "million": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
}

COVERAGE_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+")

STOPWORDS: Final[frozenset[str]] = (
    COMMON_LEXICAL_STOPWORDS
    - frozenset({"a", "an", "as", "at", "be", "by", "in", "is", "it", "of", "on", "or", "to", "who"})
) | frozenset({"role", "episode", "bundle", "claim", "unit", "section", "slot", "root"})

NARRATIVE_LEDGER_STOPWORDS: Final[frozenset[str]] = frozenset(
    {"and", "for", "into", "that", "the", "with", "without"}
)
CITATION_REPAIR_STOPWORDS: Final[frozenset[str]] = frozenset(
    {"and", "for", "from", "into", "that", "the", "through", "with", "while"}
)
SOURCE_FACT_TOKEN_STOPWORDS: Final[frozenset[str]] = frozenset(
    {"ai", "and", "aws", "by", "cloud", "fact", "for", "gtm", "ibm", "led", "metric", "reb", "skill", "the", "to", "unify"}
)
SEMANTIC_OVERLAP_STOPWORDS: Final[frozenset[str]] = frozenset(
    {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
)
METRIC_STEM_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
        "is", "it", "of", "on", "or", "that", "the", "their", "this", "to", "was",
        "were", "with", "within", "across", "over", "under", "through", "via", "per",
        "using", "used", "while", "where", "which", "who",
    }
)
PROOF_FACT_COMPOSITION_CONNECTIVES: Final[frozenset[str]] = frozenset({"and", "for", "of", "the", "to"})
MODEL_SURFACE_NON_ANCHOR_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on",
        "that", "the", "their", "to", "with", "across", "built", "created", "delivered",
        "designed", "directed", "drove", "implemented", "led", "managed", "owned", "scaled",
    }
)


def normalize_metric_signature(value: str) -> str:
    """Normalize semantically equivalent metric surfaces for zero-reuse checks."""
    text = str(value or "").casefold().strip()
    text = text.replace("$", " usd ").replace("%", " pct ").replace("×", " x ")
    text = DIGIT_LETTER_RE.sub(" ", text)
    tokens = [METRIC_EQUIVALENTS.get(token, token) for token in WORD_RE.findall(text)]
    return " ".join(tokens)


def extract_exact_metric_value_unit(value: str) -> tuple[str, str]:
    """Extract an explicit outcome value/unit; standards such as SOC 2 are not metrics."""
    text = str(value or "").strip()
    for pattern, base_unit in EXACT_METRIC_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        number = str(match.group(1))
        suffix = str(match.group(2) or "").casefold() if match.lastindex and match.lastindex >= 2 else ""
        if base_unit == "USD" and suffix:
            scale = "M" if suffix in {"m", "million"} else "B"
            return number, f"USD_{scale}"
        if base_unit == "COUNT" and suffix:
            return number, "COUNT_" + suffix.upper()
        return number, base_unit
    return "", ""


QUANTIFIED_METRIC_OUTCOME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\$|\busd\s*)\d[\d,]*(?:\.\d+)?\s*(?:k|m|mm|million|b|bn|billion)?\b|"
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:%|percent\b|percentage\b|x\b|times\b)|"
    r"\b(?:six|6)\s+months?\s+to\s+(?:just\s+)?(?:three|3)\s+weeks?\b|"
    r"\bweeks?\s+to\s+hours?\b|"
    r"\b\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|hours?|minutes?)\s+to\s+\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|hours?|minutes?)\b|"
    r"(?:<\s*)?\b\d+(?:\.\d+)?[-\s]+(?:hour|day|week|month|year|yr)s?\b|"
    r"\b\d+\s+to\s+\d+\b|"
    r"\b(?:zero|0)\s+(?:rollbacks?|red\s+escalations?|manual\s+gates?|defects?|outages?|breaches?|incidents?|downtime)\b|"
    r"(?<!bcbs\s)(?<!soc\s)(?<!iso\s)\b\d[\d,]*(?:\.\d+)?[kmb]?\+?\s+(?:[a-z0-9/&()-]+\s+){0,6}"
    r"(?:records?|signals?|workloads?|databases?|waves?|controls?|patterns?|blueprints?|"
    r"packages?|reviews?|pursuits?|architectures?|environments?|engineers?|entities?|"
    r"dependencies|violations?|accounts?|institutions?|rollbacks?|escalations?|defects?|"
    r"incidents?|findings?|views?|dashboards?|models?|pipelines?|services?|deployments?|"
    r"migrations?|members?|programs?|platforms?|products?|teams?|clients?|customers?|"
    r"partners?|countries|markets|regions|applications?|systems?|workflows?|standards?|"
    r"feeds?|sessions?|briefings?|objections?|runbooks?|tb|gb)\b",
    re.IGNORECASE,
)


def is_quantified_metric_outcome_text(value: str) -> bool:
    """True when ``value`` expresses a concrete quantified outcome rather than a qualitative surface."""
    text = str(value or "").strip()
    if not text:
        return False
    if extract_exact_metric_value_unit(text)[0]:
        return True
    return bool(QUANTIFIED_METRIC_OUTCOME_RE.search(text))


def canonicalize_unify_gate_metric_text(text: str) -> str:
    """Canonicalize Unify cycle-time compression phrasings to the gate-canonical string."""
    if not text:
        return text
    s = re.sub(
        r"\bsix\s+months\s+to\s+(?:just\s+)?three\s+weeks\b",
        "six months to three weeks",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"\b6\s+months\s+to\s+(?:just\s+)?3\s+weeks\b",
        "six months to three weeks",
        s,
        flags=re.IGNORECASE,
    )


def _load_default_unify_metric_nodes() -> dict[str, dict[str, Any]]:
    from apps_rg.runtime.sections.role_episode_metric_registry import metric_outcome_nodes_from_path
    from apps_rg.runtime.sections.unify_graph_role_episode_registry import BUNDLES_PATH as UNIFY_BUNDLES_PATH

    return metric_outcome_nodes_from_path(UNIFY_BUNDLES_PATH)


def metric_surface_tokens(
    metric_id: str,
    metric_nodes: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    metric_first: bool = False,
    limit: int | None = None,
) -> list[str]:
    """Collect deduplicated display/surface tokens for a metric outcome node."""
    nodes = metric_nodes if metric_nodes is not None else _load_default_unify_metric_nodes()
    node = nodes.get(str(metric_id)) or {}
    if metric_first:
        raw_values = [node.get("metric"), *(node.get("surface_tokens") or []), node.get("claim_text")]
    else:
        raw_values = [*(node.get("surface_tokens") or []), node.get("metric"), node.get("claim_text")]
    tokens: list[str] = []
    for raw in raw_values:
        token = str(raw or "").strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens[:limit] if limit is not None else tokens


def metric_token_visible_in_text(
    metric_id: str,
    text: str,
    *,
    metric_nodes: Mapping[str, Mapping[str, Any]] | None = None,
    surface_tokens: Sequence[str] | None = None,
    metric_first: bool = False,
    phrase_entailed_fn: Callable[[str, str], bool] | None = None,
) -> str | None:
    """Return the first matching surface token if ``metric_id`` is visible in ``text``."""
    low = str(text or "").lower()
    norm = surface_norm(text)
    tokens = (
        list(surface_tokens)
        if surface_tokens is not None
        else metric_surface_tokens(metric_id, metric_nodes, metric_first=metric_first)
    )
    for token in tokens:
        t_low = token.lower()
        if t_low and t_low in low:
            return token
        t_norm = surface_norm(token)
        if t_norm and t_norm in norm:
            return token
    if str(metric_id) == "metric_unify_team_scaled_8_to_28" and re.search(
        r"\b(?:engineering\s+)?team\b.{0,48}\b8\s*(?:to|-)\s*28\b", low
    ):
        return "engineering team from 8 to 28"
    if phrase_entailed_fn is None:
        from apps_rg.runtime.reasoning.bullet_fact_entailment import metric_phrase_entailed_in_text

        phrase_entailed_fn = metric_phrase_entailed_in_text
    for token in tokens:
        if len(token.split()) >= 2 and phrase_entailed_fn(token, text):
            return token
    return None


def unify_metric_raw_values(raw: Any) -> list[str]:
    """Normalize ``metric_raw`` strings or sequences into comparable lowercase metric tokens."""
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    if raw is None:
        return []
    text = str(raw).strip().lower()
    if not text:
        return []
    return [
        token.strip().strip("[]'\" ")
        for token in re.split(r"[,;]", text)
        if token.strip().strip("[]'\" ")
    ]


def stem_token(word: str) -> str:
    """Apply lightweight suffix stripping and 6-char truncation for FactAnchor stems."""
    token = word.lower().strip()
    for suffix in (
        "ization", "ational", "fulness", "ousness", "iveness",
        "ments", "ment", "ings", "ing", "edly", "ed", "ies", "es", "s",
    ):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token[:6] if len(token) > 6 else token


def extract_content_word_stems(text: str, *, max_stems: int = 32) -> list[str]:
    """Extract bounded unique content word stems from ``text`` using C0 stopwords."""
    stems: list[str] = []
    for match in WORD_TOKEN_RE.finditer(str(text or "").lower()):
        word = match.group(0)
        if word in STOPWORDS or word.isdigit():
            continue
        stem = stem_token(word)
        if len(stem) >= 3 and stem not in stems:
            stems.append(stem)
            if len(stems) >= max_stems:
                break
    return stems


def build_fact_anchor_lexical_tokens(text: str, *, max_stems: int = 32) -> dict[str, list[str]]:
    """Return FactAnchor ``numeric_tokens`` and ``content_word_stems`` for ``text``."""
    return {
        "numeric_tokens": extract_numeric_tokens(text),
        "content_word_stems": extract_content_word_stems(text, max_stems=max_stems),
    }


def citation_repair_tokens(text: str) -> set[str]:
    """Extract lowercase tokens > 2 chars excluding citation repair stopwords."""
    return {
        tok.lower()
        for tok in TOKEN_RE.findall(str(text or ""))
        if len(tok) > 2 and tok.lower() not in CITATION_REPAIR_STOPWORDS
    }


def narrative_ledger_tokens(text: str) -> set[str]:
    """Extract lowercase tokens > 2 chars excluding narrative ledger stopwords."""
    return set(tokenize_words(text, min_len=3, stopwords=NARRATIVE_LEDGER_STOPWORDS, lowercase=True))


def proof_fact_surface_tokens(fact: Mapping[str, Any]) -> set[str]:
    """Extract all alphanumeric surface tokens across a proof fact and its FactAnchor."""
    anchor = fact.get("fact_anchor") if isinstance(fact.get("fact_anchor"), Mapping) else {}
    values: list[Any] = [
        fact.get("claim_text"), fact.get("text"), fact.get("raw_chunk"),
        anchor.get("resolved_raw_chunk"), anchor.get("content_word_stems"),
        anchor.get("numeric_tokens"), anchor.get("partner_theme_tags"),
        fact.get("domain"), fact.get("role_episode_bundle_id"),
        fact.get("graph_skill_node_ids"), fact.get("allowed_graph_evidence_ids"),
    ]
    return set(WORD_RE.findall(" ".join(str(value or "") for value in values).casefold()))


def semantic_overlap_tokens(text: str) -> set[str]:
    """Extract casefolded content tokens for cross-bullet semantic overlap comparison."""
    return {
        token
        for token in WORD_RE.findall(str(text or "").casefold())
        if token not in SEMANTIC_OVERLAP_STOPWORDS
    }


def extract_entailment_numeric_tokens(text: str, *, min_bare_number: float = 10.0) -> list[str]:
    """Extract metric-bearing numeric tokens (currency, percent, multiplier, worded, bare >= 10)."""
    tokens: list[str] = []
    for match in ENTAILMENT_NUMERIC_TOKEN_RE.finditer(str(text or "")):
        raw = match.group(0).strip()
        if match.lastgroup == "bare":
            try:
                value = float(raw.replace(",", ""))
            except ValueError:
                continue
            if value < min_bare_number:
                continue
        tokens.append(raw)
    return tokens


def normalize_numeric_token(token: str) -> tuple[str, str] | None:
    """Normalize a numeric token to ``(magnitude, unit)`` (``usd``, ``pct``, ``x``, ``count``)."""
    s = str(token or "").strip().lower()
    if not s:
        return None
    is_usd = s.startswith("$")
    m = ENTAILMENT_NORMALIZE_RE.match(s)
    if m is None:
        return None
    try:
        value = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    suffix = (m.group("suffix") or "").lower()
    unit = "usd" if is_usd else "count"
    if suffix in ("%", "percent"):
        unit = "pct" if not is_usd else unit
    elif suffix == "x" and not is_usd:
        unit = "x"
    if suffix in ENTAILMENT_SCALE_SUFFIXES:
        value *= ENTAILMENT_SCALE_SUFFIXES[suffix]
    magnitude = str(int(value)) if value == int(value) else str(round(value, 6))
    return magnitude, unit


__all__ = [
    "CITATION_REPAIR_STOPWORDS", "COMMON_LEXICAL_STOPWORDS", "COVERAGE_WS_RE",
    "DIGIT_LETTER_RE", "ENTAILMENT_NORMALIZE_RE", "ENTAILMENT_NUMERIC_TOKEN_RE",
    "ENTAILMENT_SCALE_SUFFIXES", "EXACT_METRIC_PATTERNS", "HOLD_METRIC_TEXT_RE",
    "IBM_FOREIGN_METRIC_SCRUB_RE", "MATERIAL_METRIC_RE", "METRIC_DOLLAR_PAT",
    "METRIC_EQUIVALENTS", "METRIC_PATTERN", "METRIC_PERCENT_PAT", "METRIC_SCALE_PAT",
    "METRIC_STEM_STOPWORDS", "MODEL_SURFACE_NON_ANCHOR_TOKENS", "NARRATIVE_LEDGER_STOPWORDS",
    "NUMERIC_TOKEN_RE", "PROOF_FACT_COMPOSITION_CONNECTIVES", "QUANTIFIED_METRIC_OUTCOME_RE",
    "SEMANTIC_OVERLAP_STOPWORDS",
    "SOURCE_FACT_TOKEN_STOPWORDS", "STOPWORDS", "SURFACE_NORM_RE", "TOKEN_RE",
    "VISIBLE_METRIC_RE", "WORD_RE", "WORD_TOKEN_RE",
    "build_fact_anchor_lexical_tokens", "canonicalize_unify_gate_metric_text",
    "citation_repair_tokens", "extract_content_word_stems", "extract_entailment_numeric_tokens",
    "extract_exact_metric_value_unit", "extract_normalized_dollars", "extract_numeric_tokens",
    "is_quantified_metric_outcome_text",
    "metric_surface_tokens", "metric_token_visible_in_text", "narrative_ledger_tokens",
    "normalize_dollar_token", "normalize_metric_signature", "normalize_numeric_token",
    "proof_fact_surface_tokens", "semantic_overlap_tokens", "stem_token", "surface_norm",
    "tokenize_words", "unify_metric_raw_values",
]
