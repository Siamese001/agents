"""Unified fail-closed Overlap Engine for apps_rg across all sections, narratives, summaries, competencies, and bullets."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
import math
from pathlib import Path
from typing import Any

from apps_rg.runtime.quality.rare_term_lexicon import RareTermLexicon
from apps_rg.runtime.quality.text_units import (
    compute_ngram_jaccard,
    compute_reference_ngram_recall,
    extract_content_stems,
    extract_normalized_number_units,
)


@dataclass(frozen=True)
class ResumeUnit:
    """One atomic unit of resume text (headline segment, summary sentence, competency term, narrative, or bullet)."""

    unit_id: str
    section_id: str
    text: str
    employer: str | None = None
    unit_kind: str = "bullet"


@dataclass(frozen=True)
class OverlapPolicy:
    """Numeric threshold policy loaded from config/quality/overlap_policy.yaml (zero domain vocabulary)."""

    max_signature_term_occurrences_per_resume: int = 1
    max_number_unit_occurrences_per_resume: int = 1
    max_number_unit_occurrences_per_section: int = 1
    max_signature_df_ratio: float = 0.016
    min_capitalization_ratio: float = 0.85
    idf_signature_percentile: float = 0.90
    max_within_section_idf_cosine: float = 0.34
    max_narrative_to_bullet_idf_cosine: float = 0.34
    max_cross_section_idf_cosine: float = 0.35
    max_within_section_dense_cosine: float = 0.82
    max_cross_section_dense_cosine: float = 0.84
    max_content_trigram_jaccard: float = 0.18
    max_base_reference_4gram_jaccard: float = 0.25


@dataclass(frozen=True)
class OverlapFinding:
    """One concrete fail-closed overlap violation with exact offending units and shared terms."""

    finding_type: str
    verdict: str
    left_unit_id: str
    right_unit_id: str
    observed_value: float
    threshold: float
    shared_terms: tuple[str, ...]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_type": self.finding_type,
            "verdict": self.verdict,
            "left_unit_id": self.left_unit_id,
            "right_unit_id": self.right_unit_id,
            "observed_value": round(self.observed_value, 4),
            "threshold": round(self.threshold, 4),
            "shared_terms": list(self.shared_terms),
            "message": self.message,
        }


@dataclass(frozen=True)
class OverlapReport:
    """Aggregated fail-closed overlap evaluation result (PASS | FAIL | UNKNOWN; never WARN)."""

    verdict: str
    passed: bool
    repeated_signature_terms: Mapping[str, tuple[str, ...]]
    repeated_numbers: Mapping[str, tuple[str, ...]]
    findings: tuple[OverlapFinding, ...]
    max_within_section_idf_cosine: float = 0.0
    max_narrative_to_bullet_idf_cosine: float = 0.0
    max_cross_section_idf_cosine: float = 0.0
    max_dense_cosine: float = 0.0
    max_trigram_jaccard: float = 0.0
    evaluated_unit_count: int = 0
    lexicon_digest: str = ""

    def diagnostic_summary(self, *, section_id: str | None = None, max_items: int = 6) -> str:
        """Compact writer/judge diagnostic listing exact offending units and repeated terms/numbers."""
        relevant = [
            f
            for f in self.findings
            if section_id is None
            or f.left_unit_id.startswith(section_id)
            or f.right_unit_id.startswith(section_id)
        ]
        if not relevant and self.passed:
            return "OVERLAP_ENGINE_PASS: zero repeated signature terms, zero repeated figures, all pairwise similarities within bounds."
        target_findings = relevant or list(self.findings)
        parts = [f.message for f in target_findings[:max_items]]
        return f"OVERLAP_ENGINE_{self.verdict} ({len(target_findings)} finding(s)): " + "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "pass": self.passed,
            "evaluated_unit_count": self.evaluated_unit_count,
            "lexicon_digest": self.lexicon_digest,
            "repeated_signature_terms": {k: list(v) for k, v in self.repeated_signature_terms.items()},
            "repeated_numbers": {k: list(v) for k, v in self.repeated_numbers.items()},
            "max_within_section_idf_cosine": round(self.max_within_section_idf_cosine, 4),
            "max_narrative_to_bullet_idf_cosine": round(self.max_narrative_to_bullet_idf_cosine, 4),
            "max_cross_section_idf_cosine": round(self.max_cross_section_idf_cosine, 4),
            "max_dense_cosine": round(self.max_dense_cosine, 4),
            "max_trigram_jaccard": round(self.max_trigram_jaccard, 4),
            "findings": [f.to_dict() for f in self.findings],
            "diagnostic_summary": self.diagnostic_summary(),
        }

    def to_x2_gate_dict(self, gate_id: str = "x2_overlap_engine", *, section_id: str | None = None) -> dict[str, Any]:
        return {
            "gate_id": gate_id,
            "pass": self.passed,
            "verdict": self.verdict,
            "observed_value": {
                "verdict": self.verdict,
                "finding_count": len(self.findings),
                "repeated_signature_terms": {k: list(v) for k, v in self.repeated_signature_terms.items()},
                "repeated_numbers": {k: list(v) for k, v in self.repeated_numbers.items()},
                "max_within_section_idf_cosine": round(self.max_within_section_idf_cosine, 4),
                "max_narrative_to_bullet_idf_cosine": round(self.max_narrative_to_bullet_idf_cosine, 4),
                "max_cross_section_idf_cosine": round(self.max_cross_section_idf_cosine, 4),
                "max_dense_cosine": round(self.max_dense_cosine, 4),
                "max_trigram_jaccard": round(self.max_trigram_jaccard, 4),
                "findings": [f.to_dict() for f in self.findings[:10]],
            },
            "threshold": {
                "max_signature_term_occurrences_per_resume": 1,
                "max_number_unit_occurrences_per_resume": 1,
            },
            "failure_reason": None if self.passed else self.diagnostic_summary(section_id=section_id),
            "details": self.diagnostic_summary(section_id=section_id),
        }


def load_default_overlap_policy(policy_path: Path | None = None) -> OverlapPolicy:
    """Load OverlapPolicy from resume_graph_engine/config/quality/overlap_policy.yaml."""
    default_path = Path(__file__).resolve().parents[4] / "config" / "quality" / "overlap_policy.yaml"
    path = policy_path or default_path
    if not path.is_file():
        return OverlapPolicy()
    raw_text = path.read_text(encoding="utf-8")
    kv: dict[str, Any] = {}
    for ln in raw_text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, v = s.split(":", 1)
        key = k.strip()
        val_str = v.split("#", 1)[0].strip().strip("\"'")
        if key in OverlapPolicy.__dataclass_fields__:
            f_type = OverlapPolicy.__dataclass_fields__[key].type
            if "int" in str(f_type):
                kv[key] = int(float(val_str))
            elif "float" in str(f_type):
                kv[key] = float(val_str)
    return OverlapPolicy(**kv)


def compute_idf_cosine_similarity(
    left_text: str,
    right_text: str,
    lexicon: RareTermLexicon,
) -> tuple[float, tuple[str, ...]]:
    """Compute IDF-weighted cosine similarity and return highest-IDF shared terms."""
    left_stems = extract_content_stems(left_text)
    right_stems = extract_content_stems(right_text)
    if not left_stems or not right_stems:
        return 0.0, ()

    left_counts: Counter[str] = Counter(left_stems)
    right_counts: Counter[str] = Counter(right_stems)

    # Boost rare signature terms and normalized numbers so shared rare features weigh heavily in cosine
    for sig in lexicon.extract_signature_terms(left_text):
        left_counts[f"sig:{sig}"] += 2
    for sig in lexicon.extract_signature_terms(right_text):
        right_counts[f"sig:{sig}"] += 2
    for num in extract_normalized_number_units(left_text):
        left_counts[f"num:{num}"] += 2
    for num in extract_normalized_number_units(right_text):
        right_counts[f"num:{num}"] += 2

    def _weight(feature: str, count: int) -> float:
        if feature.startswith(("sig:", "num:")):
            base_idf = lexicon.default_unseen_idf * 1.4
        else:
            base_idf = lexicon.term_idf(feature)
        return (1.0 + math.log(count)) * (base_idf ** 1.25)

    left_vec = {k: _weight(k, c) for k, c in left_counts.items()}
    right_vec = {k: _weight(k, c) for k, c in right_counts.items()}

    shared_keys = set(left_vec) & set(right_vec)
    if not shared_keys:
        return 0.0, ()

    dot = sum(left_vec[k] * right_vec[k] for k in shared_keys)
    norm_l = math.sqrt(sum(v * v for v in left_vec.values()))
    norm_r = math.sqrt(sum(v * v for v in right_vec.values()))
    if norm_l <= 0.0 or norm_r <= 0.0:
        return 0.0, ()

    ranked_shared = sorted(
        shared_keys,
        key=lambda k: -(left_vec[k] * right_vec[k]),
    )
    clean_shared = tuple(k.split(":", 1)[-1] for k in ranked_shared[:8])
    return round(dot / (norm_l * norm_r), 4), clean_shared


def _default_dense_embedder(texts: Sequence[str]) -> list[list[float]]:
    """Compute dense vectors using apps_rg BGE multi-head projection."""
    from apps_rg.runtime.bge_multi_head import project_text_multi_head

    vectors: list[list[float]] = []
    for t in texts:
        mh = project_text_multi_head(t)
        vec = list(mh.dense_vector)
        if not vec:
            raise ValueError("Empty dense_vector returned from project_text_multi_head")
        vectors.append(vec)
    return vectors


def _vector_cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return round(dot / (na * nb), 4)


def _is_companion_narrative_and_bullet(u1: ResumeUnit, u2: ResumeUnit) -> bool:
    kinds = {u1.unit_kind, u2.unit_kind}
    if kinds != {"narrative", "bullet"}:
        return False
    if u1.employer and u2.employer:
        return u1.employer == u2.employer
    p1 = u1.section_id.split("_", 1)[0]
    p2 = u2.section_id.split("_", 1)[0]
    return p1 == p2


def evaluate_resume_overlap(
    units: Sequence[ResumeUnit],
    *,
    lexicon: RareTermLexicon | None = None,
    policy: OverlapPolicy | None = None,
    dense_embedder: Callable[[Sequence[str]], list[list[float]]] | None = None,
    reference_texts: Mapping[str, Sequence[str]] | None = None,
) -> OverlapReport:
    """Evaluate all units of a resume or section slice for signature repeats, figure repeats, and semantic/lexical echo."""
    active_policy = policy or load_default_overlap_policy()
    active_lexicon = lexicon or RareTermLexicon.from_default_fact_inventory(
        max_signature_df_ratio=active_policy.max_signature_df_ratio,
        min_capitalization_ratio=active_policy.min_capitalization_ratio,
    )
    clean_units = [u for u in units if u.text and u.text.strip()]
    if not clean_units:
        return OverlapReport(
            verdict="PASS",
            passed=True,
            repeated_signature_terms={},
            repeated_numbers={},
            findings=(),
            evaluated_unit_count=0,
            lexicon_digest=active_lexicon.corpus_digest,
        )

    findings: list[OverlapFinding] = []

    # 1. Signature term repetition:
    #    - Globally across all prose units (Executive Summary + all Narratives + all Bullets)
    #    - Within Competencies (no duplicate signature terms across competency items)
    #    - Within Headline segments
    #    Number+unit repetition is checked globally across the entire resume.
    prose_sig_locations: dict[str, list[str]] = {}
    comp_sig_locations: dict[str, list[str]] = {}
    head_sig_locations: dict[str, list[str]] = {}
    num_locations: dict[str, list[str]] = {}

    for u in clean_units:
        target_sig_map = (
            comp_sig_locations
            if u.unit_kind == "competency_term"
            else head_sig_locations
            if u.unit_kind == "headline_segment"
            else prose_sig_locations
        )
        for sig in active_lexicon.extract_signature_terms(u.text):
            locs = target_sig_map.setdefault(sig, [])
            if u.unit_id not in locs:
                locs.append(u.unit_id)
        for num in extract_normalized_number_units(u.text):
            locs = num_locations.setdefault(num, [])
            if u.unit_id not in locs:
                locs.append(u.unit_id)

    repeated_sigs: dict[str, tuple[str, ...]] = {}
    for sig_pool in (prose_sig_locations, comp_sig_locations, head_sig_locations):
        for sig, locs in sorted(sig_pool.items()):
            if len(locs) > active_policy.max_signature_term_occurrences_per_resume:
                repeated_sigs[sig] = tuple(locs)
                findings.append(
                    OverlapFinding(
                        finding_type="REPEATED_SIGNATURE_TERM",
                        verdict="FAIL",
                        left_unit_id=locs[0],
                        right_unit_id=locs[1],
                        observed_value=float(len(locs)),
                        threshold=float(active_policy.max_signature_term_occurrences_per_resume),
                        shared_terms=(sig,),
                        message=(
                            f"Signature term '{sig}' repeated {len(locs)} times across {locs} "
                            f"(cap={active_policy.max_signature_term_occurrences_per_resume}); "
                            f"keep '{sig}' in at most one unit."
                        ),
                    )
                )

    repeated_nums: dict[str, tuple[str, ...]] = {}
    for num, locs in sorted(num_locations.items()):
        if len(locs) > active_policy.max_number_unit_occurrences_per_resume:
            repeated_nums[num] = tuple(locs)
            findings.append(
                OverlapFinding(
                    finding_type="REPEATED_NUMBER_UNIT",
                    verdict="FAIL",
                    left_unit_id=locs[0],
                    right_unit_id=locs[1],
                    observed_value=float(len(locs)),
                    threshold=float(active_policy.max_number_unit_occurrences_per_resume),
                    shared_terms=(num,),
                    message=(
                        f"Numeric figure '{num}' repeated {len(locs)} times across {locs} "
                        f"(cap={active_policy.max_number_unit_occurrences_per_resume}); "
                        f"allocate distinct outcome figures."
                    ),
                )
            )

    # 2. Dense embeddings (fail-closed to UNKNOWN if embedder fails)
    prose_units = [
        u for u in clean_units if u.unit_kind in ("summary_sentence", "narrative", "bullet")
    ]
    embed_fn = dense_embedder or _default_dense_embedder
    dense_vecs: list[list[float]] = []
    if len(prose_units) >= 2:
        try:
            dense_vecs = embed_fn([u.text for u in prose_units])
            if len(dense_vecs) != len(prose_units) or any(not v for v in dense_vecs):
                raise ValueError("Dense embedder returned mismatched or empty vector list")
        except Exception as exc:
            unknown_finding = OverlapFinding(
                finding_type="DENSE_EMBEDDING_UNAVAILABLE",
                verdict="UNKNOWN",
                left_unit_id=prose_units[0].unit_id,
                right_unit_id=prose_units[1].unit_id,
                observed_value=0.0,
                threshold=active_policy.max_within_section_dense_cosine,
                shared_terms=(),
                message=f"Dense embedding evaluation failed closed (UNKNOWN): {exc}",
            )
            return OverlapReport(
                verdict="UNKNOWN",
                passed=False,
                repeated_signature_terms=repeated_sigs,
                repeated_numbers=repeated_nums,
                findings=tuple([*findings, unknown_finding]),
                evaluated_unit_count=len(clean_units),
                lexicon_digest=active_lexicon.corpus_digest,
            )

    # 3. All-pairs IDF cosine, dense cosine, and content 3-gram Jaccard over prose units
    max_within_idf = 0.0
    max_narr_bullet_idf = 0.0
    max_cross_idf = 0.0
    max_dense = 0.0
    max_trigram = 0.0

    for i in range(len(prose_units)):
        u1 = prose_units[i]
        for j in range(i + 1, len(prose_units)):
            u2 = prose_units[j]
            same_section = u1.section_id == u2.section_id
            companion_nb = _is_companion_narrative_and_bullet(u1, u2)

            idf_cos, shared = compute_idf_cosine_similarity(u1.text, u2.text, active_lexicon)
            trigram_j = round(compute_ngram_jaccard(u1.text, u2.text, n=3, content_only=True), 4)
            dense_cos = _vector_cosine(dense_vecs[i], dense_vecs[j]) if dense_vecs else 0.0

            max_dense = max(max_dense, dense_cos)
            max_trigram = max(max_trigram, trigram_j)

            if same_section:
                max_within_idf = max(max_within_idf, idf_cos)
                idf_limit = active_policy.max_within_section_idf_cosine
                dense_limit = active_policy.max_within_section_dense_cosine
                pair_kind = "WITHIN_SECTION"
            elif companion_nb:
                max_narr_bullet_idf = max(max_narr_bullet_idf, idf_cos)
                idf_limit = active_policy.max_narrative_to_bullet_idf_cosine
                dense_limit = active_policy.max_within_section_dense_cosine
                pair_kind = "NARRATIVE_TO_BULLET"
            else:
                max_cross_idf = max(max_cross_idf, idf_cos)
                idf_limit = active_policy.max_cross_section_idf_cosine
                dense_limit = active_policy.max_cross_section_dense_cosine
                pair_kind = "CROSS_SECTION"

            if idf_cos > idf_limit:
                findings.append(
                    OverlapFinding(
                        finding_type=f"{pair_kind}_IDF_COSINE_EXCEEDED",
                        verdict="FAIL",
                        left_unit_id=u1.unit_id,
                        right_unit_id=u2.unit_id,
                        observed_value=idf_cos,
                        threshold=idf_limit,
                        shared_terms=shared,
                        message=(
                            f"{pair_kind} IDF cosine {idf_cos:.4f} > {idf_limit:.4f} between "
                            f"{u1.unit_id} and {u2.unit_id}; replace shared terms {list(shared[:5])}."
                        ),
                    )
                )

            if dense_cos > dense_limit:
                findings.append(
                    OverlapFinding(
                        finding_type=f"{pair_kind}_DENSE_COSINE_EXCEEDED",
                        verdict="FAIL",
                        left_unit_id=u1.unit_id,
                        right_unit_id=u2.unit_id,
                        observed_value=dense_cos,
                        threshold=dense_limit,
                        shared_terms=shared,
                        message=(
                            f"{pair_kind} semantic dense cosine {dense_cos:.4f} > {dense_limit:.4f} between "
                            f"{u1.unit_id} and {u2.unit_id}; differentiate claim mechanism and outcome."
                        ),
                    )
                )

            if trigram_j > active_policy.max_content_trigram_jaccard:
                findings.append(
                    OverlapFinding(
                        finding_type=f"{pair_kind}_TRIGRAM_ECHO",
                        verdict="FAIL",
                        left_unit_id=u1.unit_id,
                        right_unit_id=u2.unit_id,
                        observed_value=trigram_j,
                        threshold=active_policy.max_content_trigram_jaccard,
                        shared_terms=shared,
                        message=(
                            f"{pair_kind} 3-gram phrase overlap {trigram_j:.4f} > "
                            f"{active_policy.max_content_trigram_jaccard:.4f} between {u1.unit_id} and {u2.unit_id}."
                        ),
                    )
                )

            if companion_nb:
                w1 = (u1.text.strip().split() or [""])[0].lower().strip(",.:;-")
                w2 = (u2.text.strip().split() or [""])[0].lower().strip(",.:;-")
                if w1 and w1 == w2:
                    findings.append(
                        OverlapFinding(
                            finding_type="NARRATIVE_TO_BULLET_SHARED_OPENER",
                            verdict="FAIL",
                            left_unit_id=u1.unit_id,
                            right_unit_id=u2.unit_id,
                            observed_value=1.0,
                            threshold=0.0,
                            shared_terms=(w1,),
                            message=(
                                f"Narrative {u1.unit_id} shares opening action verb '{w1}' with companion bullet {u2.unit_id}; "
                                "use a distinct executive verb."
                            ),
                        )
                    )

    # 4. Optional reference n-gram recall checks (base resume / E0 example anti-copying)
    if reference_texts:
        for u in clean_units:
            for ref_label, refs in reference_texts.items():
                for r_idx, ref_str in enumerate(refs, start=1):
                    recall = round(compute_reference_ngram_recall(u.text, ref_str, n=4), 4)
                    if recall > active_policy.max_base_reference_4gram_jaccard:
                        findings.append(
                            OverlapFinding(
                                finding_type="REFERENCE_4GRAM_COPYING",
                                verdict="FAIL",
                                left_unit_id=u.unit_id,
                                right_unit_id=f"{ref_label}:R{r_idx}",
                                observed_value=recall,
                                threshold=active_policy.max_base_reference_4gram_jaccard,
                                shared_terms=(),
                                message=(
                                    f"Unit {u.unit_id} copies 4-grams from {ref_label}:R{r_idx} "
                                    f"({recall:.4f} > {active_policy.max_base_reference_4gram_jaccard:.4f})."
                                ),
                            )
                        )

    verdict = "PASS" if not findings else "FAIL"
    return OverlapReport(
        verdict=verdict,
        passed=(verdict == "PASS"),
        repeated_signature_terms=repeated_sigs,
        repeated_numbers=repeated_nums,
        findings=tuple(findings),
        max_within_section_idf_cosine=max_within_idf,
        max_narrative_to_bullet_idf_cosine=max_narr_bullet_idf,
        max_cross_section_idf_cosine=max_cross_idf,
        max_dense_cosine=max_dense,
        max_trigram_jaccard=max_trigram,
        evaluated_unit_count=len(clean_units),
        lexicon_digest=active_lexicon.corpus_digest,
    )


_SENT_SPLIT_RE = __import__("re").compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_BULLET_PREFIX_RE = __import__("re").compile(r"^(?:[-•*]\s*)?(?:bul_[a-z0-9_]+\s*:\s*)?", __import__("re").IGNORECASE)


def _clean_bullet_strings(bullets: Sequence[Mapping[str, Any] | str] | str) -> list[str]:
    if isinstance(bullets, str):
        raw_lines = [ln.strip() for ln in bullets.splitlines() if ln.strip()]
    else:
        raw_lines = []
        for item in bullets or ():
            if isinstance(item, Mapping):
                txt = str(item.get("bullet_text") or item.get("text") or "").strip()
            else:
                txt = str(item or "").strip()
            if txt:
                raw_lines.append(txt)
    return [cleaned for ln in raw_lines if (cleaned := _BULLET_PREFIX_RE.sub("", ln).strip())]


def evaluate_bullets_section_overlap(
    bullets: Sequence[Mapping[str, Any] | str] | str,
    *,
    section_id: str,
    employer: str | None = None,
    reference_texts: Mapping[str, Sequence[str]] | None = None,
) -> OverlapReport:
    """Evaluate a bullet lane's bullets for signature repeats, number repeats, IDF/dense cosine, and n-grams."""
    emp = employer or section_id.split("_", 1)[0]
    b_strs = _clean_bullet_strings(bullets)
    units = [
        ResumeUnit(
            unit_id=f"{section_id}:B{idx}",
            section_id=section_id,
            text=txt,
            employer=emp,
            unit_kind="bullet",
        )
        for idx, txt in enumerate(b_strs, start=1)
    ]
    return evaluate_resume_overlap(units, reference_texts=reference_texts)


SHARED_OVERLAP_DECISIVE_FAILURE_CLAUSE: str = (
    "- Repeated rare signature term (any named regulatory standard, compliance code, or client system such as "
    "BCBS 239, SOC 2, SR 11-7, CCAR, Basel III, Solvency II, AG43, SCADA, MEDDPICC, Salesforce, Guidewire, Maximo) "
    "or repeated numeric KPI figure (such as 99.9%, $10M, 20%) across bullets, sentences, or sections, or echoed "
    "clause structure: MUST set decisive_failure=true and pass=false (never excuse a repeated standard or figure as "
    "'minor' even when each occurrence matches an allowed fact or allocated bundle metric)."
)



def evaluate_narrative_section_overlap(
    narrative_sentence: str,
    companion_bullets: Sequence[Mapping[str, Any] | str] | str = (),
    *,
    section_id: str = "role_narrative",
    employer: str | None = None,
    reference_texts: Mapping[str, Sequence[str]] | None = None,
) -> OverlapReport:
    """Evaluate a role narrative against its companion bullets (without re-failing internal bullet-vs-bullet pairs)."""
    emp = employer or section_id.split("_", 1)[0]
    bullet_sec_id = f"{emp}_bullets"
    narr = str(narrative_sentence or "").strip()
    b_strs = _clean_bullet_strings(companion_bullets)
    if not narr:
        return evaluate_resume_overlap(())
    if not b_strs:
        return evaluate_resume_overlap(
            [ResumeUnit(unit_id=f"{section_id}:N1", section_id=section_id, text=narr, employer=emp, unit_kind="narrative")],
            reference_texts=reference_texts,
        )
    # Evaluate narrative against each companion bullet and filters findings involving the narrative unit
    narr_unit = ResumeUnit(unit_id=f"{section_id}:N1", section_id=section_id, text=narr, employer=emp, unit_kind="narrative")
    b_units = [
        ResumeUnit(unit_id=f"{bullet_sec_id}:B{idx}", section_id=bullet_sec_id, text=txt, employer=emp, unit_kind="bullet")
        for idx, txt in enumerate(b_strs, start=1)
    ]
    full_rep = evaluate_resume_overlap([narr_unit, *b_units], reference_texts=reference_texts)
    if full_rep.verdict == "UNKNOWN":
        return full_rep
    narr_findings = tuple(
        f for f in full_rep.findings
        if f.left_unit_id == narr_unit.unit_id or f.right_unit_id == narr_unit.unit_id
    )
    narr_sigs = {
        k: v for k, v in full_rep.repeated_signature_terms.items() if narr_unit.unit_id in v
    }
    narr_nums = {
        k: v for k, v in full_rep.repeated_numbers.items() if narr_unit.unit_id in v
    }
    verdict = "PASS" if not narr_findings else "FAIL"
    return OverlapReport(
        verdict=verdict,
        passed=(verdict == "PASS"),
        repeated_signature_terms=narr_sigs,
        repeated_numbers=narr_nums,
        findings=narr_findings,
        max_within_section_idf_cosine=0.0,
        max_narrative_to_bullet_idf_cosine=full_rep.max_narrative_to_bullet_idf_cosine,
        max_cross_section_idf_cosine=full_rep.max_cross_section_idf_cosine,
        max_dense_cosine=full_rep.max_dense_cosine,
        max_trigram_jaccard=full_rep.max_trigram_jaccard,
        evaluated_unit_count=1 + len(b_units),
        lexicon_digest=full_rep.lexicon_digest,
    )


def evaluate_exec_summary_section_overlap(
    resume_display_text: str,
    companion_bullets: Sequence[Mapping[str, Any] | str] | str = (),
) -> OverlapReport:
    """Evaluate Executive Summary sentences internally and against any provided companion bullets."""
    sents = [s.strip() for s in _SENT_SPLIT_RE.split(str(resume_display_text or "").strip()) if s.strip()]
    units = [
        ResumeUnit(
            unit_id=f"executive_summary:S{idx}",
            section_id="executive_summary",
            text=s,
            employer=None,
            unit_kind="summary_sentence",
        )
        for idx, s in enumerate(sents, start=1)
    ]
    for idx, b_txt in enumerate(_clean_bullet_strings(companion_bullets), start=1):
        units.append(
            ResumeUnit(
                unit_id=f"companion_bullets:B{idx}",
                section_id="companion_bullets",
                text=b_txt,
                employer=None,
                unit_kind="bullet",
            )
        )
    return evaluate_resume_overlap(units)


def evaluate_competencies_section_overlap(
    competencies: Sequence[Mapping[str, Any]],
    *,
    reference_texts: Mapping[str, Sequence[str]] | None = None,
) -> OverlapReport:
    """Evaluate competency items for duplicate signature terms, numbers, and reference n-gram copying."""
    units: list[ResumeUnit] = []
    for c_idx, cat in enumerate(competencies or (), start=1):
        if not isinstance(cat, Mapping):
            continue
        for t_idx, raw in enumerate(cat.get("terms") or (), start=1):
            if isinstance(raw, Mapping):
                phrase = str(raw.get("term") or raw.get("phrase") or raw.get("label") or "").strip()
            else:
                phrase = str(raw or "").strip()
            if phrase:
                units.append(
                    ResumeUnit(
                        unit_id=f"competencies:C{c_idx}:T{t_idx}",
                        section_id="competencies",
                        text=phrase,
                        employer=None,
                        unit_kind="competency_term",
                    )
                )
    return evaluate_resume_overlap(units, reference_texts=reference_texts)


SHARED_OVERLAP_DECISIVE_FAILURE_CLAUSE: str = (
    "- Repeated rare signature term (any named regulatory standard, compliance code, or client system such as "
    "BCBS 239, SOC 2, SR 11-7, CCAR, Basel III, Solvency II, AG43, SCADA, MEDDPICC, Salesforce, Guidewire, Maximo) "
    "or repeated numeric KPI figure (such as 99.9%, $10M, 20%) across bullets, sentences, or sections, or echoed "
    "clause structure: MUST set decisive_failure=true and pass=false (never excuse a repeated standard or figure as "
    "'minor' even when each occurrence matches an allowed fact or allocated bundle metric)."
)



def evaluate_headline_section_overlap(
    headline_line: str,
    *,
    reference_texts: Mapping[str, Sequence[str]] | None = None,
) -> OverlapReport:
    """Evaluate headline segments for duplicate signature terms and reference n-gram copying."""
    segs = [s.strip() for s in str(headline_line or "").split("|") if s.strip()]
    units = [
        ResumeUnit(
            unit_id=f"headline:seg_{idx}",
            section_id="headline",
            text=seg,
            employer=None,
            unit_kind="headline_segment",
        )
        for idx, seg in enumerate(segs, start=1)
    ]
    return evaluate_resume_overlap(units, reference_texts=reference_texts)


SHARED_OVERLAP_DECISIVE_FAILURE_CLAUSE: str = (
    "- Repeated rare signature term (any named regulatory standard, compliance code, or client system such as "
    "BCBS 239, SOC 2, SR 11-7, CCAR, Basel III, Solvency II, AG43, SCADA, MEDDPICC, Salesforce, Guidewire, Maximo) "
    "or repeated numeric KPI figure (such as 99.9%, $10M, 20%) across bullets, sentences, or sections, or echoed "
    "clause structure: MUST set decisive_failure=true and pass=false (never excuse a repeated standard or figure as "
    "'minor' even when each occurrence matches an allowed fact or allocated bundle metric)."
)


