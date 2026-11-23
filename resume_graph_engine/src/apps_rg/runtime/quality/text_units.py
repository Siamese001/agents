"""Unified text tokenization, number-unit canonicalization, and n-gram extraction for apps_rg overlap checks."""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from infrastructure.types.metric_lexical_primitives import COMMON_LEXICAL_STOPWORDS

ENGLISH_GRAMMAR_STOPWORDS: Final[frozenset[str]] = COMMON_LEXICAL_STOPWORDS

_WORD_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# Matches numeric KPI figures with units ($10M, $10 million, 99.9%, 20 percent, 3x, 6 months to 3 weeks)
# so code numbers (like BCBS 239 or SOC 2) are captured as code bigrams rather than bare numbers.
_NUMBER_UNIT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"\b\d+\s*(?:months?|weeks?|days?|hours?)\s+to\s+\d+\s*(?:months?|weeks?|days?|hours?)\b"
    r"|(?:(?:\$|\busd\s*)\d+(?:,\d{3})*(?:\.\d+)?\s*(?:m|mm|b|bn|k|million|billion|thousand)?\b)"
    r"|(?:\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|percent\b|percentage\b|x\b|times\b|bps\b))"
    r"|(?:\b\d+(?:,\d{3})+\+?\s*(?:seats|users|engineers|clients|accounts|workflows|portfolios)?\b)"
    r")",
    re.IGNORECASE,
)


def tokenize_text(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric/hyphenated word tokens."""
    if not text:
        return []
    return _WORD_TOKEN_RE.findall(text.lower())


def content_stem(token: str) -> str:
    """Light inflectional stemmer for English content words (zero domain hardcoding)."""
    w = token.lower().strip("-")
    if len(w) <= 4:
        return w
    for suffix in ("izations", "ization", "ments", "ment", "ings", "ing", "tions", "tion", "ities", "ity", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)]
    return w


def extract_content_stems(text: str) -> list[str]:
    """Return ordered content-word stems (excluding grammar stopwords and 1-char tokens)."""
    stems: list[str] = []
    for tok in tokenize_text(text):
        if tok in ENGLISH_GRAMMAR_STOPWORDS or len(tok) < 2:
            continue
        stems.append(content_stem(tok))
    return stems


def normalize_number_unit(raw: str) -> str:
    """Canonicalize a KPI number+unit expression (e.g. '$10 million' -> '$10m', '99.9 percent' -> '99.9%')."""
    s = raw.strip().lower().replace(",", "")
    if " to " in s:
        return re.sub(r"\s+", " ", s)
    s = re.sub(r"^usd\s*", "$", s)
    s = re.sub(r"\s+", "", s)
    s = (
        s.replace("million", "m")
        .replace("mm", "m")
        .replace("billion", "b")
        .replace("bn", "b")
        .replace("thousand", "k")
        .replace("percentage", "%")
        .replace("percent", "%")
        .replace("times", "x")
    )
    # Strip trailing noun labels after 1,000+ counts (e.g., 5750+seats -> 5750+)
    m_plus = re.match(r"^(\d+\+?)[a-z]{3,}$", s)
    if m_plus:
        return m_plus.group(1)
    return s


def extract_normalized_number_units(text: str) -> list[str]:
    """Extract unique normalized KPI number+unit strings in appearance order."""
    if not text:
        return []
    seen: list[str] = []
    for m in _NUMBER_UNIT_RE.finditer(text):
        norm = normalize_number_unit(m.group(0))
        if norm and norm not in seen:
            seen.append(norm)
    return seen


def extract_word_ngrams(text: str, n: int = 3, *, content_only: bool = False) -> set[tuple[str, ...]]:
    """Extract n-gram tuples from text."""
    if n <= 0:
        return set()
    tokens = extract_content_stems(text) if content_only else tokenize_text(text)
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def compute_ngram_jaccard(left: str, right: str, n: int = 3, *, content_only: bool = True) -> float:
    """Jaccard overlap of n-grams between two strings."""
    a = extract_word_ngrams(left, n=n, content_only=content_only)
    b = extract_word_ngrams(right, n=n, content_only=content_only)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def compute_reference_ngram_recall(candidate_text: str, reference_text: str, n: int = 4) -> float:
    """Fraction of candidate n-grams that appear verbatim in a reference text (base resume / E0)."""
    cand = extract_word_ngrams(candidate_text, n=n, content_only=False)
    ref = extract_word_ngrams(reference_text, n=n, content_only=False)
    if not cand or not ref:
        return 0.0
    return len(cand & ref) / len(cand)
