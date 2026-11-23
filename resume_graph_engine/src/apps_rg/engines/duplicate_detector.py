"""Pairwise bullet duplicate detector delegating to apps_rg.runtime.quality."""

from __future__ import annotations

from typing import Any

from apps_rg.runtime.quality.overlap_engine import compute_idf_cosine_similarity
from apps_rg.runtime.quality.rare_term_lexicon import RareTermLexicon


class DuplicateDetector:
    """Structural duplicate finder for bullets + cross-section summaries."""

    def __init__(self, default_threshold: float = 0.9) -> None:
        self.default_threshold = default_threshold

    @staticmethod
    def _bullet_text(record: dict[str, Any]) -> str:
        return str(record.get("bullet_text") or "").strip()

    def find_duplicates(
        self, bullets: list[dict[str, Any]], threshold: float | None = None
    ) -> list[tuple[int, int, float]]:
        thr = self.default_threshold if threshold is None else threshold
        lex = RareTermLexicon.from_default_fact_inventory()
        texts = [self._bullet_text(rec) for rec in bullets]
        out: list[tuple[int, int, float]] = []
        n = len(texts)
        for i in range(n):
            for j in range(i + 1, n):
                sim, _ = compute_idf_cosine_similarity(texts[i], texts[j], lex)
                if sim >= thr:
                    out.append((i, j, sim))
        return out

    def compute_similarity_matrix(
        self, sections: dict[str, list[Any]] | None
    ) -> dict[str, Any]:
        if not sections:
            return {
                "pairwise_checks": [],
                "total_comparisons": 0,
                "duplicates_found": [],
                "max_similarity": 0.0,
                "sections_analyzed": [],
            }

        lex = RareTermLexicon.from_default_fact_inventory()
        section_names = list(sections.keys())
        pairwise_checks: list[dict[str, Any]] = []
        duplicates_found: list[dict[str, Any]] = []
        max_similarity = 0.0
        bullets_meta: list[tuple[str, int, str]] = []

        for sec in section_names:
            raw_items = sections.get(sec, []) or []
            for idx, raw in enumerate(raw_items):
                if isinstance(raw, str) and raw.strip():
                    bullets_meta.append((sec, idx, raw.strip()))

        for i in range(len(bullets_meta)):
            for j in range(i + 1, len(bullets_meta)):
                si, _, ti = bullets_meta[i]
                sj, _, tj = bullets_meta[j]
                sim, _ = compute_idf_cosine_similarity(ti, tj, lex)
                max_similarity = max(max_similarity, sim)
                cross_section = si != sj
                pairwise_checks.append(
                    {"i": i, "j": j, "similarity": sim, "cross_section": cross_section}
                )
                if sim >= self.default_threshold:
                    duplicates_found.append(
                        {"i": i, "j": j, "similarity": sim, "cross_section": cross_section}
                    )

        return {
            "pairwise_checks": pairwise_checks,
            "total_comparisons": len(pairwise_checks),
            "duplicates_found": duplicates_found,
            "max_similarity": float(max_similarity),
            "sections_analyzed": section_names,
        }
