"""Sequence-wide X2 cross-touch validator for multi-touch outreach sequences."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from apps_lic.domain.validators_pkg.grounding_and_claims import (
    METRIC_LAUNDERED_FROM_OPPORTUNITY,
    PCTCertificate,
    UNGROUNDED_CANDIDATE_METRIC,
    verify_candidate_metric_grounding,
)
from infrastructure.types.metric_lexical_primitives import (
    COMMON_LEXICAL_STOPWORDS,
    METRIC_DOLLAR_PAT,
    METRIC_PERCENT_PAT,
    METRIC_SCALE_PAT,
    normalize_dollar_token,
)

MAX_PAIRWISE_TOUCH_COSINE: Final[float] = 0.32
MAX_EXEMPLAR_4GRAM_OVERLAP: Final[float] = 0.20
ZERO_DUPLICATE_OPENERS_AND_CTAS: Final[str] = "ZERO_DUPLICATE_OPENERS_AND_CTAS"
INV_LIC_C0_DISJOINT_TOUCH_FACTS: Final[str] = "INV-LIC-C0-DISJOINT-TOUCH-FACTS"
INV_RESUME_NO_UNDEFINED_ACRONYMS: Final[str] = "INV-RESUME-NO-UNDEFINED-ACRONYMS"
PAIRWISE_COSINE_EXCEEDED: Final[str] = "PAIRWISE_COSINE_EXCEEDED"
EXEMPLAR_4GRAM_OVERLAP_EXCEEDED: Final[str] = "EXEMPLAR_4GRAM_OVERLAP_EXCEEDED"

_MGA_ACRONYM_PAT: Final[re.Pattern[str]] = re.compile(r"\bMGAs?\b")
_MGA_EXPANDED_PAT: Final[re.Pattern[str]] = re.compile(r"\bmanaging\s+general\s+agents?\b", re.IGNORECASE)
_SALUTATION_PREFIX_PAT: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:hi|hello|dear|good\s+(?:morning|afternoon|evening))\b[^\n,]*,\s*", re.IGNORECASE
)
_FACT_TAG_PAT: Final[re.Pattern[str]] = re.compile(r"\[fact_id:([A-Za-z0-9_.\-:]+)\]")
_COSINE_STOPWORDS: Final[frozenset[str]] = COMMON_LEXICAL_STOPWORDS | frozenset(
    {
        "hi", "hello", "dear", "regards", "best", "sincerely", "thanks", "thank",
        "would", "open", "next", "week", "brief", "conversation", "connecting",
        "connect", "touch", "note", "message", "email", "following", "given",
    }
)


@dataclass(frozen=True)
class TouchX2Violation:
    """Single cross-touch or sequence-level X2 gate violation."""

    violation_code: str
    touch_numbers: tuple[int, ...] = ()
    message: str = ""
    observed: Any = None
    threshold: Any = None
    touch_number: int = 0
    rule_id: str = ""

    def __post_init__(self) -> None:
        if not self.touch_numbers and self.touch_number > 0:
            object.__setattr__(self, "touch_numbers", (int(self.touch_number),))
        elif self.touch_numbers and self.touch_number == 0:
            object.__setattr__(self, "touch_number", int(self.touch_numbers[0]))
        if not self.rule_id:
            object.__setattr__(self, "rule_id", self.violation_code)

    @property
    def code(self) -> str:
        return self.violation_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_code": self.violation_code, "rule_id": self.rule_id,
            "touch_number": self.touch_number, "touch_numbers": list(self.touch_numbers),
            "message": self.message, "observed": self.observed, "threshold": self.threshold,
        }


@dataclass(frozen=True)
class SequenceX2Report:
    """Consolidated report from sequence-wide X2 validation across Touch 1..N."""

    passed: bool
    violations: tuple[TouchX2Violation, ...] = ()
    max_pairwise_cosine: float = 0.0
    pairwise_cosines: dict[str, float] = field(default_factory=dict)
    duplicate_openers: tuple[str, ...] = ()
    duplicate_ctas: tuple[str, ...] = ()
    max_exemplar_4gram_overlap: float = 0.0
    disjoint_facts_passed: bool = True
    undefined_acronyms_found: tuple[str, ...] = ()
    pct_certificates: tuple[PCTCertificate, ...] = ()
    metric_grounding_passed: bool = True

    @property
    def is_valid(self) -> bool:
        return self.passed

    @property
    def violation_codes(self) -> tuple[str, ...]:
        return tuple(v.violation_code for v in self.violations)

    @property
    def violation_messages(self) -> list[str]:
        return [f"{v.violation_code}: {v.message}" for v in self.violations]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed, "is_valid": self.passed,
            "max_pairwise_cosine": round(float(self.max_pairwise_cosine), 6),
            "pairwise_cosines": {k: round(float(v), 6) for k, v in self.pairwise_cosines.items()},
            "duplicate_openers": list(self.duplicate_openers), "duplicate_ctas": list(self.duplicate_ctas),
            "max_exemplar_4gram_overlap": round(float(self.max_exemplar_4gram_overlap), 6),
            "disjoint_facts_passed": self.disjoint_facts_passed,
            "undefined_acronyms_found": list(self.undefined_acronyms_found),
            "metric_grounding_passed": self.metric_grounding_passed,
            "pct_certificates": [c.to_dict() for c in self.pct_certificates],
            "violations": [v.to_dict() for v in self.violations],
        }


def check_undefined_mga_acronym(text: str | None) -> tuple[bool, list[str]]:
    """Enforce INV-RESUME-NO-UNDEFINED-ACRONYMS: reject standalone MGA/MGAs unless expanded."""
    raw = str(text or "")
    hits = [m.group(0) for m in _MGA_ACRONYM_PAT.finditer(raw)]
    if not hits or _MGA_EXPANDED_PAT.search(raw):
        return True, []
    unique_hits = sorted(set(hits))
    return False, [
        f"{INV_RESUME_NO_UNDEFINED_ACRONYMS}: Undefined acronym {', '.join(unique_hits)} detected; "
        "must be expanded as 'Managing General Agent (MGA)' or 'Managing General Agents (MGAs)'."
    ]


class UndefinedAcronymValidator:
    """Validator rejecting standalone MGA/MGAs acronyms without full expansion."""

    def validate(self, body: str | None) -> tuple[bool, list[str]]:
        return check_undefined_mga_acronym(body)


def _strip_salutation_and_signature(body: str) -> str:
    cleaned = _SALUTATION_PREFIX_PAT.sub("", str(body or "").strip())
    sig_starts = ("regards", "best,", "sincerely", "best regards", "--", "__", "cheers")
    kept_lines: list[str] = []
    for line in cleaned.splitlines():
        if any(line.strip().lower().startswith(tok) for tok in sig_starts):
            break
        kept_lines.append(line)
    return "\n".join(kept_lines).strip()


def extract_touch_opener(body: str) -> str:
    """Extract normalized opening sentence of a touch body (after any salutation)."""
    core = _strip_salutation_and_signature(body)
    if not core:
        return ""
    first_para = next((p.strip() for p in core.split("\n\n") if p.strip()), core)
    sentences = re.split(r"(?<=[.!?])\s+|\n+", first_para)
    opener = sentences[0] if sentences else first_para
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", opener.lower())).strip()


def extract_touch_cta(body: str) -> str:
    """Extract normalized closing call-to-action (CTA) sentence from a touch body."""
    core = _strip_salutation_and_signature(body)
    if not core:
        return ""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", core) if s.strip()]
    if not sentences:
        return ""
    questions = [s for s in sentences if s.endswith("?")]
    cta = questions[-1] if questions else sentences[-1]
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", cta.lower())).strip()


def compute_touch_cosine_similarity(text_a: str, text_b: str) -> float:
    """Compute TF cosine similarity between two touch bodies over content words."""
    core_a, core_b = _strip_salutation_and_signature(text_a).lower(), _strip_salutation_and_signature(text_b).lower()
    toks_a = [w for w in re.findall(r"\b[a-z0-9$%]{3,}\b", core_a) if w not in _COSINE_STOPWORDS]
    toks_b = [w for w in re.findall(r"\b[a-z0-9$%]{3,}\b", core_b) if w not in _COSINE_STOPWORDS]
    if not toks_a or not toks_b:
        return 0.0
    counts_a, counts_b = Counter(toks_a), Counter(toks_b)
    shared = set(counts_a.keys()) & set(counts_b.keys())
    if not shared:
        return 0.0
    dot = sum(counts_a[w] * counts_b[w] for w in shared)
    norm_a = math.sqrt(sum(v * v for v in counts_a.values()))
    norm_b = math.sqrt(sum(v * v for v in counts_b.values()))
    return 0.0 if (norm_a == 0.0 or norm_b == 0.0) else round(dot / (norm_a * norm_b), 6)


def compute_exemplar_4gram_overlap(touch_body: str, exemplars: Sequence[str] | str | None) -> float:
    """Compute maximum 4-gram overlap ratio between touch_body and E0 style exemplars."""
    if not exemplars:
        return 0.0
    ex_list = [exemplars] if isinstance(exemplars, str) else [str(x) for x in exemplars if str(x).strip()]
    words = re.findall(r"\b[a-z0-9]+\b", str(touch_body or "").lower())
    if not ex_list or len(words) < 4:
        return 0.0
    touch_4grams = {tuple(words[i : i + 4]) for i in range(len(words) - 3)}
    if not touch_4grams:
        return 0.0
    max_overlap = 0.0
    for ex in ex_list:
        ex_words = re.findall(r"\b[a-z0-9]+\b", ex.lower())
        if len(ex_words) >= 4:
            ex_4grams = {tuple(ex_words[i : i + 4]) for i in range(len(ex_words) - 3)}
            max_overlap = max(max_overlap, len(touch_4grams & ex_4grams) / float(len(touch_4grams)))
    return round(max_overlap, 6)


def _normalize_sequence_touches(touches_or_sequence: Any) -> list[dict[str, Any]]:
    raw_items = getattr(touches_or_sequence, "touches", touches_or_sequence)
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        raw_items = [raw_items]
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_items, start=1):
        t_num, draft_obj = idx, item
        if hasattr(item, "draft"):
            t_num = int(getattr(item, "touch_number", idx) or idx)
            draft_obj = getattr(item, "draft")
        if isinstance(draft_obj, str):
            body, subject, fids, meta = draft_obj, "", _FACT_TAG_PAT.findall(draft_obj), {}
        elif isinstance(draft_obj, Mapping):
            t_num = int(draft_obj.get("touch_number", t_num) or t_num)
            body, subject = str(draft_obj.get("body") or ""), str(draft_obj.get("subject") or "")
            raw_fids = draft_obj.get("grounded_facts_used") or draft_obj.get("cited_fact_ids") or draft_obj.get("fact_ids") or ()
            fids = [str(x) for x in raw_fids if str(x).strip()] or _FACT_TAG_PAT.findall(body)
            meta = dict(draft_obj.get("metadata") or {})
            if draft_obj.get("repaired_from_reserve_pool"):
                meta["repaired_from_reserve_pool"] = True
        else:
            t_num = int(getattr(draft_obj, "touch_number", t_num) or t_num)
            body, subject = str(getattr(draft_obj, "body", "") or ""), str(getattr(draft_obj, "subject", "") or "")
            raw_fids = getattr(draft_obj, "grounded_facts_used", None) or getattr(draft_obj, "cited_fact_ids", None) or ()
            fids = [str(x) for x in raw_fids if str(x).strip()] or _FACT_TAG_PAT.findall(body)
            meta = dict(getattr(draft_obj, "metadata", None) or {})
        normalized.append({"touch_number": t_num, "subject": subject, "body": body, "fact_ids": fids, "metadata": meta, "raw": item})
    return normalized


def _extract_canonical_metrics(text: str) -> set[str]:
    tokens = {normalize_dollar_token(m.group(0)) for m in METRIC_DOLLAR_PAT.finditer(text)}
    tokens |= {m.group(0).strip().lower() for m in METRIC_PERCENT_PAT.finditer(text)}
    tokens |= {m.group(0).strip().lower() for m in METRIC_SCALE_PAT.finditer(text)}
    return tokens


def validate_sequence_x2(
    touches_or_sequence: Any,
    allocation_plan: Any | None = None,
    e0_exemplars: Sequence[str] | str | None = None,
    *,
    exemplars: Sequence[str] | str | None = None,
    candidate_facts: Sequence[Any] | Any | None = None,
    opportunity_context: str | Any | None = None,
    max_pairwise_cosine: float = MAX_PAIRWISE_TOUCH_COSINE,
    max_exemplar_4gram_overlap: float = MAX_EXEMPLAR_4GRAM_OVERLAP,
    enforce_metric_grounding: bool = True,
) -> SequenceX2Report:
    """Run sequence-wide X2 validation across all touches in an outreach sequence."""
    touches = _normalize_sequence_touches(touches_or_sequence)
    eff_exemplars = e0_exemplars if e0_exemplars is not None else exemplars
    violations: list[TouchX2Violation] = []

    pairwise_cosines: dict[str, float] = {}
    max_cos = 0.0
    for i in range(len(touches)):
        for j in range(i + 1, len(touches)):
            ti, tj = touches[i], touches[j]
            sim = compute_touch_cosine_similarity(ti["body"], tj["body"])
            pairwise_cosines[f"touch_{ti['touch_number']}_vs_touch_{tj['touch_number']}"] = sim
            max_cos = max(max_cos, sim)
            if sim > max_pairwise_cosine:
                violations.append(
                    TouchX2Violation(
                        violation_code=PAIRWISE_COSINE_EXCEEDED,
                        touch_numbers=(ti["touch_number"], tj["touch_number"]),
                        message=f"Pairwise cosine similarity {sim:.3f} between touch {ti['touch_number']} and touch {tj['touch_number']} exceeds ceiling {max_pairwise_cosine}.",
                        observed=sim, threshold=max_pairwise_cosine,
                    )
                )

    opener_map: dict[str, list[int]] = {}
    cta_map: dict[str, list[int]] = {}
    for t in touches:
        if op := extract_touch_opener(t["body"]):
            opener_map.setdefault(op, []).append(t["touch_number"])
        if cta := extract_touch_cta(t["body"]):
            cta_map.setdefault(cta, []).append(t["touch_number"])

    dup_openers = tuple(sorted(op for op, tnums in opener_map.items() if len(tnums) > 1))
    dup_ctas = tuple(sorted(cta for cta, tnums in cta_map.items() if len(tnums) > 1))
    for op in dup_openers:
        tnums = tuple(opener_map[op])
        violations.append(TouchX2Violation(ZERO_DUPLICATE_OPENERS_AND_CTAS, tnums, f"Duplicate opener across touches {tnums}: '{op}'.", op, "unique_opener_per_touch"))
    for cta in dup_ctas:
        tnums = tuple(cta_map[cta])
        violations.append(TouchX2Violation(ZERO_DUPLICATE_OPENERS_AND_CTAS, tnums, f"Duplicate CTA across touches {tnums}: '{cta}'.", cta, "unique_cta_per_touch"))

    max_4gram = 0.0
    if eff_exemplars:
        for t in touches:
            ov = compute_exemplar_4gram_overlap(t["body"], eff_exemplars)
            max_4gram = max(max_4gram, ov)
            if ov > max_exemplar_4gram_overlap:
                violations.append(
                    TouchX2Violation(
                        EXEMPLAR_4GRAM_OVERLAP_EXCEEDED, (t["touch_number"],),
                        f"Touch {t['touch_number']} E0 exemplar 4-gram overlap {ov:.3f} exceeds ceiling {max_exemplar_4gram_overlap}.",
                        ov, max_exemplar_4gram_overlap,
                    )
                )

    disjoint_passed = True
    fact_to_touches: dict[str, list[int]] = {}
    metric_to_touches: dict[str, list[int]] = {}
    for t in touches:
        for fid in set(t["fact_ids"]):
            fact_to_touches.setdefault(fid, []).append(t["touch_number"])
        for m_tok in _extract_canonical_metrics(t["body"]):
            metric_to_touches.setdefault(m_tok, []).append(t["touch_number"])

    for fid, tnums in sorted(fact_to_touches.items()):
        if len(tnums) > 1:
            disjoint_passed = False
            violations.append(TouchX2Violation(INV_LIC_C0_DISJOINT_TOUCH_FACTS, tuple(tnums), f"Fact ID '{fid}' is reused across touches {tuple(tnums)}; violates {INV_LIC_C0_DISJOINT_TOUCH_FACTS}.", fid, "disjoint_fact_ids"))
    for m_tok, tnums in sorted(metric_to_touches.items()):
        if len(tnums) > 1:
            disjoint_passed = False
            violations.append(TouchX2Violation(INV_LIC_C0_DISJOINT_TOUCH_FACTS, tuple(tnums), f"Metric '{m_tok}' is repeated across touches {tuple(tnums)}; violates {INV_LIC_C0_DISJOINT_TOUCH_FACTS}.", m_tok, "disjoint_metrics"))

    if allocation_plan is not None:
        by_touch = getattr(allocation_plan, "allocated_fact_ids_by_touch", None) or (
            allocation_plan.get("allocated_fact_ids_by_touch") if isinstance(allocation_plan, Mapping) else None
        )
        res_ids = {str(x) for x in (getattr(allocation_plan, "reserve_repair_pool_fact_ids", None) or (allocation_plan.get("reserve_repair_pool_fact_ids") if isinstance(allocation_plan, Mapping) else ()) or ())}
        if isinstance(by_touch, Mapping):
            for t in touches:
                t_num = t["touch_number"]
                alloc_set = {str(x) for x in (by_touch.get(t_num) or by_touch.get(str(t_num)) or ()) if str(x).strip()}
                if t["metadata"].get("repaired_from_reserve_pool"):
                    alloc_set |= res_ids
                for fid in t["fact_ids"]:
                    if alloc_set and fid not in alloc_set:
                        disjoint_passed = False
                        violations.append(TouchX2Violation(INV_LIC_C0_DISJOINT_TOUCH_FACTS, (t_num,), f"Touch {t_num} cites unallocated fact_id '{fid}' (expected {sorted(alloc_set)}).", fid, sorted(alloc_set)))

    undef_acronyms: list[str] = []
    for t in touches:
        combined = f"{t['subject']} {t['body']}".strip()
        mga_ok, mga_errs = check_undefined_mga_acronym(combined)
        if not mga_ok:
            for hit in _MGA_ACRONYM_PAT.findall(combined):
                if hit not in undef_acronyms:
                    undef_acronyms.append(hit)
            violations.append(TouchX2Violation(INV_RESUME_NO_UNDEFINED_ACRONYMS, (t["touch_number"],), mga_errs[0], undef_acronyms, "expanded_Managing_General_Agents_(MGAs)"))

    all_certs: list[PCTCertificate] = []
    metric_grounding_ok = True
    if enforce_metric_grounding and (candidate_facts is not None or opportunity_context is not None or allocation_plan is not None):
        for t in touches:
            res = verify_candidate_metric_grounding(
                t["raw"], candidate_facts=candidate_facts or (), opportunity_context=opportunity_context,
                allocation_plan=allocation_plan, touch_number=t["touch_number"],
                declared_fact_ids=t["fact_ids"] if t["fact_ids"] else None,
            )
            all_certs.extend(res.certificates)
            if not res.passed:
                metric_grounding_ok = False
                for v_msg in res.violations:
                    v_code = METRIC_LAUNDERED_FROM_OPPORTUNITY if METRIC_LAUNDERED_FROM_OPPORTUNITY in v_msg else UNGROUNDED_CANDIDATE_METRIC
                    violations.append(TouchX2Violation(v_code, (t["touch_number"],), v_msg))

    return SequenceX2Report(
        passed=len(violations) == 0, violations=tuple(violations),
        max_pairwise_cosine=max_cos, pairwise_cosines=pairwise_cosines,
        duplicate_openers=dup_openers, duplicate_ctas=dup_ctas,
        max_exemplar_4gram_overlap=max_4gram, disjoint_facts_passed=disjoint_passed,
        undefined_acronyms_found=tuple(undef_acronyms), pct_certificates=tuple(all_certs),
        metric_grounding_passed=metric_grounding_ok,
    )


__all__ = [
    "EXEMPLAR_4GRAM_OVERLAP_EXCEEDED", "INV_LIC_C0_DISJOINT_TOUCH_FACTS",
    "INV_RESUME_NO_UNDEFINED_ACRONYMS", "MAX_EXEMPLAR_4GRAM_OVERLAP",
    "MAX_PAIRWISE_TOUCH_COSINE", "PAIRWISE_COSINE_EXCEEDED",
    "SequenceX2Report", "TouchX2Violation", "UndefinedAcronymValidator",
    "ZERO_DUPLICATE_OPENERS_AND_CTAS", "check_undefined_mga_acronym",
    "compute_exemplar_4gram_overlap", "compute_touch_cosine_similarity",
    "extract_touch_cta", "extract_touch_opener", "validate_sequence_x2",
]
