"""Shared quality and overlap engine package for apps_rg."""
from __future__ import annotations

from apps_rg.runtime.quality.overlap_engine import (
    OverlapFinding,
    OverlapPolicy,
    OverlapReport,
    ResumeUnit,
    SHARED_OVERLAP_DECISIVE_FAILURE_CLAUSE,
    compute_idf_cosine_similarity,
    evaluate_bullets_section_overlap,
    evaluate_competencies_section_overlap,
    evaluate_exec_summary_section_overlap,
    evaluate_headline_section_overlap,
    evaluate_narrative_section_overlap,
    evaluate_resume_overlap,
    load_default_overlap_policy,
)
from apps_rg.runtime.quality.rare_term_lexicon import RareTermLexicon
from apps_rg.runtime.quality.text_units import (
    ENGLISH_GRAMMAR_STOPWORDS,
    compute_ngram_jaccard,
    compute_reference_ngram_recall,
    content_stem,
    extract_content_stems,
    extract_normalized_number_units,
    extract_word_ngrams,
    normalize_number_unit,
    tokenize_text,
)

__all__ = [
    "ENGLISH_GRAMMAR_STOPWORDS",
    "OverlapFinding",
    "OverlapPolicy",
    "OverlapReport",
    "RareTermLexicon",
    "ResumeUnit",
    "SHARED_OVERLAP_DECISIVE_FAILURE_CLAUSE",
    "compute_idf_cosine_similarity",
    "compute_ngram_jaccard",
    "compute_reference_ngram_recall",
    "content_stem",
    "evaluate_bullets_section_overlap",
    "evaluate_competencies_section_overlap",
    "evaluate_exec_summary_section_overlap",
    "evaluate_headline_section_overlap",
    "evaluate_narrative_section_overlap",
    "evaluate_resume_overlap",
    "extract_content_stems",
    "extract_normalized_number_units",
    "extract_word_ngrams",
    "load_default_overlap_policy",
    "normalize_number_unit",
    "tokenize_text",
]
