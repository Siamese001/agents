"""Cross-subsystem pure-stdlib metric parsing and lexical tokenization primitives.

Zero upward imports: never import ``apps_rg``, ``outreach_engine``, ``resume_engine``,
or ``apps_research`` from this module.
"""

from __future__ import annotations

import re
from collections.abc import Set as AbstractSet
from typing import Final

METRIC_DOLLAR_PAT: Final[re.Pattern[str]] = re.compile(
    r"(?:[\$€£]|(?:USD|EUR|GBP)\s*)\s*\d+(?:,\d{3})*(?:\.\d+)?\s*(?:[kKmMbBtT]|billion|million|thousand)?(?:\s*[-–—]\s*(?:[\$€£]|(?:USD|EUR|GBP)\s*)?\s*\d+(?:,\d{3})*(?:\.\d+)?\s*(?:[kKmMbBtT]|billion|million|thousand)?)?\b",
    re.IGNORECASE,
)

METRIC_PERCENT_PAT: Final[re.Pattern[str]] = re.compile(r"\b\d+(?:\.\d+)?%")

METRIC_SCALE_PAT: Final[re.Pattern[str]] = re.compile(
    r"\b\d+\s*\+\s*(?:engineers?|professionals?|people|team|members?|clients?|customers?)\b|"
    r"\b\d+(?:\.\d+)?\s*(?:[mMbBkK])\s+(?:DAU|MAU|users?|requests?|events?|queries|qps)\b",
    re.IGNORECASE,
)

NUMERIC_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\$\d+(?:\.\d+)?[BMKbmk]?|\b\d+(?:\.\d+)?(?:\+|%|x|bps|ms|s|m|b|k)?\b)",
    re.IGNORECASE,
)

WORD_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9]{2,}")
WORD_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+", re.IGNORECASE)
SURFACE_NORM_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9%$]+")

COMMON_LEXICAL_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "about",
        "across",
        "after",
        "all",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "before",
        "being",
        "between",
        "both",
        "by",
        "could",
        "each",
        "for",
        "from",
        "had",
        "has",
        "have",
        "in",
        "into",
        "is",
        "it",
        "more",
        "most",
        "of",
        "on",
        "or",
        "other",
        "over",
        "per",
        "should",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "used",
        "using",
        "very",
        "via",
        "was",
        "were",
        "when",
        "where",
        "which",
        "while",
        "who",
        "will",
        "with",
        "within",
        "without",
        "would",
    }
)

_DOLLAR_MULT: Final[dict[str, float]] = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "million": 1e6,
    "b": 1e9,
    "billion": 1e9,
    "t": 1e12,
}


def normalize_dollar_token(raw: str) -> str:
    """Normalize currency token to a canonical dollar amount string."""
    cleaned = re.sub(r"(?i)[\$€£]|usd|eur|gbp", "", raw).replace(",", "").strip()
    if any(sep in cleaned for sep in ("-", "–", "—")):
        parts = [p.strip() for p in re.split(r"[-–—]", cleaned) if p.strip()]
        if len(parts) == 2:
            m1 = re.match(
                r"^(\d+(?:\.\d+)?)\s*(k|thousand|m|million|b|billion|t)?$",
                parts[0],
                re.IGNORECASE,
            )
            m2 = re.match(
                r"^(\d+(?:\.\d+)?)\s*(k|thousand|m|million|b|billion|t)?$",
                parts[1],
                re.IGNORECASE,
            )
            if m1 and m2:
                s2 = m2.group(2) or ""
                n1 = normalize_dollar_token(f"${m1.group(1)}{m1.group(2) or s2}")
                n2 = normalize_dollar_token(f"${m2.group(1)}{s2}")
                return f"{n1}-{n2}"
    m = re.match(
        r"^(\d+(?:\.\d+)?)\s*(k|thousand|m|million|b|billion|t)?$",
        cleaned,
        re.IGNORECASE,
    )
    if not m:
        return raw.lower().strip()
    num_str = m.group(1)
    if len(num_str.split(".")[0]) > 20:
        return f"${num_str}"
    try:
        val = float(num_str) * _DOLLAR_MULT.get((m.group(2) or "").lower(), 1.0)
        return f"${int(round(val))}"
    except (OverflowError, ValueError):
        return f"${num_str}"


def extract_normalized_dollars(text: str) -> set[str]:
    """Extract normalized dollar amounts and range endpoints from ``text``."""
    tokens: set[str] = set()
    if not text:
        return tokens
    for m in METRIC_DOLLAR_PAT.finditer(text):
        try:
            norm = normalize_dollar_token(m.group(0))
            tokens.add(norm)
            tokens.update(s for s in norm.split("-") if "-" in norm and s.startswith("$"))
        except (OverflowError, ValueError):
            pass
    return tokens


def surface_norm(text: str) -> str:
    """Lowercase and collapse non-alphanumeric/currency/percent characters to single spaces."""
    return SURFACE_NORM_RE.sub(" ", str(text or "").lower()).strip()


def tokenize_words(
    text: str,
    *,
    min_len: int = 1,
    stopwords: AbstractSet[str] = frozenset(),
    lowercase: bool = True,
) -> list[str]:
    """Tokenize alphanumeric words with optional minimum length and stopword filtering."""
    raw = str(text or "")
    if lowercase:
        raw = raw.lower()
        matches = WORD_RE.findall(raw)
    else:
        matches = TOKEN_RE.findall(raw)
    return [tok for tok in matches if len(tok) >= min_len and tok not in stopwords]


def extract_numeric_tokens(text: str) -> list[str]:
    """Extract unique numeric/metric tokens from ``text`` in first-appearance order."""
    seen: list[str] = []
    for match in NUMERIC_TOKEN_RE.finditer(str(text or "")):
        tok = match.group(0).strip()
        if tok and tok not in seen:
            seen.append(tok)
    return seen


__all__ = [
    "COMMON_LEXICAL_STOPWORDS",
    "METRIC_DOLLAR_PAT",
    "METRIC_PERCENT_PAT",
    "METRIC_SCALE_PAT",
    "NUMERIC_TOKEN_RE",
    "SURFACE_NORM_RE",
    "TOKEN_RE",
    "WORD_RE",
    "WORD_TOKEN_RE",
    "extract_normalized_dollars",
    "extract_numeric_tokens",
    "normalize_dollar_token",
    "surface_norm",
    "tokenize_words",
]
