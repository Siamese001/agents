"""Corpus-learned rare-term lexicon and IDF weighting for apps_rg overlap checks (zero typed domain lists)."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Final

from apps_rg.runtime.quality.text_units import (
    ENGLISH_GRAMMAR_STOPWORDS,
    content_stem,
    extract_normalized_number_units,
    tokenize_text,
)

# Structural pattern recognizers (orthographic shapes only; zero domain words):
# 1. All-caps acronym + number/Roman numeral, or Capitalized noun + Roman numeral (e.g., BCBS 239, SOC 2, SR 11-7, Solvency II, Basel III)
_STRUCTURAL_CODE_BIGRAM_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:[A-Z]{2,8}\s+(?:\d{1,5}(?:-\d{1,5})?|II|III|IV)|[A-Z][a-z]{3,14}\s+(?:II|III|IV))\b"
)
# 2. Alphanumeric standard code (e.g., AG43)
_STRUCTURAL_ALNUM_CODE_RE: Final[re.Pattern[str]] = re.compile(r"\b[A-Z]{2,6}\d{1,5}\b")
# 3. All-caps acronym (len 4..10; 3-letter acronyms without digits are general domain acronyms weighted via IDF)
_STRUCTURAL_ACRONYM_RE: Final[re.Pattern[str]] = re.compile(r"\b[A-Z]{4,10}\b")
# 4. Mid-sentence capitalized proper noun (preceded by a lowercase word and space, len 5..16)
_MID_SENTENCE_PROPER_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[a-z,;:]\s)[A-Z][a-zA-Z]{4,15}\b")

_ROMAN_NUMERALS: Final[frozenset[str]] = frozenset({"ii", "iii", "iv", "vi", "vii", "viii"})

_METADATA_SKIP_KEYS: Final[frozenset[str]] = frozenset({
    "id",
    "bundle_id",
    "fact_id",
    "metric_id",
    "schema",
    "version",
    "source_fact_ids",
    "source_skill_ids",
    "bundle_title",
    "category_label",
    "resume_display_label",
    "title",
    "label",
    "role_title",
    "employer",
    "company",
    "location",
    "dates",
})

_ROLE_HEADER_KEYS: Final[frozenset[str]] = frozenset({
    "role_title",
    "employer",
    "company",
    "employer_name",
    "company_name",
    "organization",
    "location",
    "geography",
    "regions",
})

_LEXICON_CACHE: dict[str, "RareTermLexicon"] = {}
_FINGERPRINT_CACHE: dict[tuple[str, str], frozenset[str]] = {}


def _default_fact_inventory_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "fact_inventory"


_GEO_ENUM_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:across|spanning)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?),\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?),\s*and\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b"
)


def _collect_corpus_units_and_header_tokens(fact_dir: Path) -> tuple[list[str], set[str], str]:
    """Extract prose units and structural role-header metadata words from fact inventory JSONs."""
    units: list[str] = []
    header_tokens: set[str] = set()
    hasher = hashlib.sha256()

    paths = sorted(fact_dir.glob("*role_episode_bundles.json"))
    for extra_name in ("unify_graph_gap_fill.json", "competency_capability_bundles.json"):
        extra = fact_dir / extra_name
        if extra.is_file() and extra not in paths:
            paths.append(extra)

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            s = obj.strip()
            for gm in _GEO_ENUM_RE.finditer(s):
                for grp in gm.groups():
                    for gtok in tokenize_text(grp):
                        header_tokens.add(gtok)
            if (
                len(s) >= 20
                and " " in s
                and not s.startswith(("urn:", "http", "fact_", "reb_", "metric_", "sk_", "ccb_", "hpb_"))
            ):
                units.append(s)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if k in _ROLE_HEADER_KEYS and isinstance(v, str):
                    for tok in tokenize_text(v):
                        if len(tok) >= 2:
                            header_tokens.add(tok)
                if k not in _METADATA_SKIP_KEYS:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for p in paths:
        raw_bytes = p.read_bytes()
        hasher.update(p.name.encode("utf-8"))
        hasher.update(raw_bytes)
        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        _walk(data)

    return units, header_tokens, hasher.hexdigest()[:16]


@dataclass(frozen=True)
class RareTermLexicon:
    """Corpus-derived IDF table and rare signature term inventory."""

    corpus_size: int
    corpus_digest: str
    idf: Mapping[str, float]
    doc_freq: Mapping[str, int]
    signature_terms: frozenset[str]
    role_header_tokens: frozenset[str]
    max_signature_df_ratio: float
    default_unseen_idf: float

    @classmethod
    def from_fact_inventory(
        cls,
        units: Sequence[str],
        *,
        role_header_tokens: Sequence[str] = (),
        max_signature_df_ratio: float = 0.016,
        min_capitalization_ratio: float = 0.85,
        idf_signature_percentile: float = 0.90,
        corpus_digest: str = "custom",
    ) -> "RareTermLexicon":
        n_docs = max(1, len(units))
        header_set = frozenset(t.lower() for t in role_header_tokens if t)

        stem_df: dict[str, int] = {}
        cap_df: dict[str, int] = {}
        lower_df: dict[str, int] = {}

        for text in units:
            # 1. Content stem unigram + bigram DF for IDF cosine
            stems = [content_stem(t) for t in tokenize_text(text) if t not in ENGLISH_GRAMMAR_STOPWORDS and len(t) >= 2]
            seen_stems = set(stems)
            for i in range(len(stems) - 1):
                seen_stems.add(f"{stems[i]} {stems[i + 1]}")
            for st in seen_stems:
                stem_df[st] = stem_df.get(st, 0) + 1

            # 2. Lowercase word occurrences in original text
            for w in set(re.findall(r"\b[a-z]{2,16}\b", text)):
                lower_df[w] = lower_df.get(w, 0) + 1

            # 3. Structural code / acronym / mid-sentence proper noun occurrences
            found_caps: set[str] = set()
            for m in _STRUCTURAL_CODE_BIGRAM_RE.finditer(text):
                found_caps.add(re.sub(r"\s+", " ", m.group(0).strip().lower()))
            for m in _STRUCTURAL_ALNUM_CODE_RE.finditer(text):
                found_caps.add(m.group(0).lower())
            for m in _STRUCTURAL_ACRONYM_RE.finditer(text):
                found_caps.add(m.group(0).lower())
            for m in _MID_SENTENCE_PROPER_RE.finditer(text):
                found_caps.add(m.group(0).lower())
            for item in found_caps:
                cap_df[item] = cap_df.get(item, 0) + 1

        idf_map: dict[str, float] = {}
        for term, df_val in stem_df.items():
            idf_map[term] = round(math.log((n_docs + 1.0) / (df_val + 1.0)) + 1.0, 4)

        default_unseen_idf = round(math.log(n_docs + 1.0) + 1.5, 4)
        sorted_idfs = sorted(idf_map.values())
        p_idx = min(len(sorted_idfs) - 1, max(0, int(len(sorted_idfs) * idf_signature_percentile))) if sorted_idfs else 0
        idf_floor = sorted_idfs[p_idx] if sorted_idfs else 1.0

        learned_signatures: set[str] = set()
        for term, c_cnt in cap_df.items():
            if term in ENGLISH_GRAMMAR_STOPWORDS or term in _ROMAN_NUMERALS or term in header_set:
                continue
            tokens = term.split()
            if any(t in header_set for t in tokens):
                continue
            l_cnt = lower_df.get(term, 0)
            total_cnt = c_cnt + l_cnt
            cap_ratio = c_cnt / max(1, total_cnt)
            df_ratio = total_cnt / n_docs
            term_idf = idf_map.get(content_stem(term), default_unseen_idf)
            is_code_or_alnum = bool(" " in term or any(ch.isdigit() for ch in term))
            if (
                cap_ratio >= min_capitalization_ratio
                and df_ratio <= max_signature_df_ratio
                and (is_code_or_alnum or term_idf >= idf_floor or df_ratio <= max_signature_df_ratio)
            ):
                learned_signatures.add(term)
                idf_map.setdefault(term, round(math.log((n_docs + 1.0) / (total_cnt + 1.0)) + 1.5, 4))

        return cls(
            corpus_size=n_docs,
            corpus_digest=corpus_digest,
            idf=idf_map,
            doc_freq={**stem_df, **cap_df},
            signature_terms=frozenset(learned_signatures),
            role_header_tokens=header_set,
            max_signature_df_ratio=max_signature_df_ratio,
            default_unseen_idf=default_unseen_idf,
        )

    @classmethod
    def from_default_fact_inventory(
        cls,
        fact_dir: Path | None = None,
        *,
        max_signature_df_ratio: float = 0.016,
        min_capitalization_ratio: float = 0.85,
    ) -> "RareTermLexicon":
        fdir = fact_dir or _default_fact_inventory_dir()
        fast_key = f"path:{fdir}:{max_signature_df_ratio}:{min_capitalization_ratio}"
        fast_cached = _LEXICON_CACHE.get(fast_key)
        if fast_cached is not None:
            return fast_cached
        units, header_tokens, digest = _collect_corpus_units_and_header_tokens(fdir)
        cache_key = f"{digest}:{max_signature_df_ratio}:{min_capitalization_ratio}"
        cached = _LEXICON_CACHE.get(cache_key)
        if cached is not None:
            _LEXICON_CACHE[fast_key] = cached
            return cached
        lex = cls.from_fact_inventory(
            units,
            role_header_tokens=tuple(sorted(header_tokens)),
            max_signature_df_ratio=max_signature_df_ratio,
            min_capitalization_ratio=min_capitalization_ratio,
            corpus_digest=digest,
        )
        _LEXICON_CACHE[cache_key] = lex
        _LEXICON_CACHE[fast_key] = lex
        return lex

    def term_idf(self, token_or_stem: str) -> float:
        """Return corpus IDF weight for a token or stem (unseen rare tokens get default_unseen_idf)."""
        key = token_or_stem.lower()
        if key in self.idf:
            return self.idf[key]
        st = content_stem(key)
        return self.idf.get(st, self.default_unseen_idf)

    def extract_signature_terms(self, text: str) -> list[str]:
        """Extract rare signature terms from text, longest-first without double-counting sub-tokens."""
        if not text:
            return []
        lower_text = re.sub(r"\s+", " ", text.lower())
        candidates: set[str] = set()

        # 1. Structural code bigrams and alphanumeric codes directly in text (catches brand-new unseen standards too)
        for m in _STRUCTURAL_CODE_BIGRAM_RE.finditer(text):
            norm = re.sub(r"\s+", " ", m.group(0).strip().lower())
            df_ratio = self.doc_freq.get(norm, 0) / max(1, self.corpus_size)
            if df_ratio <= self.max_signature_df_ratio and not any(t in self.role_header_tokens for t in norm.split()):
                candidates.add(norm)

        for m in _STRUCTURAL_ALNUM_CODE_RE.finditer(text):
            norm = m.group(0).lower()
            df_ratio = self.doc_freq.get(norm, 0) / max(1, self.corpus_size)
            if df_ratio <= self.max_signature_df_ratio and norm not in self.role_header_tokens:
                candidates.add(norm)

        # 2. Corpus-learned rare signature terms present as whole words/phrases
        for sig in self.signature_terms:
            if sig in lower_text and re.search(r"\b" + re.escape(sig) + r"\b", lower_text):
                candidates.add(sig)

        # Longest-first pruning so 'bcbs 239' suppresses 'bcbs' and 'soc 2' suppresses 'soc'
        ordered = sorted(candidates, key=lambda s: (-len(s.split()), -len(s), s))
        kept: list[str] = []
        for cand in ordered:
            if any(cand != existing and re.search(r"\b" + re.escape(cand) + r"\b", existing) for existing in kept):
                continue
            kept.append(cand)
        return sorted(kept)

    def extract_metric_fingerprint(self, text: str) -> frozenset[str]:
        """Return the collision fingerprint (rare signature terms + normalized number+unit tokens) for a metric/unit."""
        if not text:
            return frozenset()
        fp_key = (self.corpus_digest, text)
        cached_fp = _FINGERPRINT_CACHE.get(fp_key)
        if cached_fp is not None:
            return cached_fp
        sigs = [f"sig:{s}" for s in self.extract_signature_terms(text)]
        nums = [f"num:{n}" for n in extract_normalized_number_units(text)]
        res = frozenset([*sigs, *nums])
        _FINGERPRINT_CACHE[fp_key] = res
        return res
