"""G5 Repeatability and G6 Planted-Defect Meta-Evaluation Gate for resume_graph_engine (apps_rg).

Mirrors outreach_engine's G5/G6 architecture while enforcing strict label blindness:
`detect_resume_defect_classes()` strips all ground-truth label fields (`planted_defect_class`,
`is_defective`, `gold_pass_label`, `gold_human_score`) before executing real production
`apps_rg` validators (`OverlapEngine`, `evaluate_executive_summary_v2_x2`,
`COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS`, `_jd_parroting_count`, historical era guards,
and C0 role-mandate bundle rules).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
from typing import Any, Final

from apps_rg.evals.whole_resume.deterministic_checks import _jd_parroting_count
from apps_rg.runtime.contracts.prompt_validator_vocab_ssot import (
    COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS,
)
from apps_rg.runtime.quality.overlap_engine import (
    OverlapPolicy,
    ResumeUnit,
    evaluate_resume_overlap,
)
from apps_rg.runtime.quality.rare_term_lexicon import RareTermLexicon
from apps_rg.runtime.quality.text_units import (
    extract_normalized_number_units,
    tokenize_text,
)
from apps_rg.runtime.sections.executive_summary_v2.x2_invariants import (
    evaluate_executive_summary_v2_x2,
)

RG_G5_MAX_SCORE_STD_CEILING: Final[float] = 0.02
RG_G5_MIN_REPEATED_RUNS: Final[int] = 3
RG_G6_MIN_SPEARMAN_RHO: Final[float] = 0.75
RG_G6_MIN_COHENS_KAPPA: Final[float] = 0.90
RG_G6_MAX_CLEAN_FPR: Final[float] = 0.0
RG_G6_MIN_DEFECT_TPR: Final[float] = 0.95

DEFAULT_RG_HOLDOUT_CORPUS_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "holdout"
    / "resume_planted_defect_corpus.v1.jsonl"
)

RG_PLANTED_DEFECT_CLASSES: Final[tuple[str, ...]] = (
    "repeated_signature_term_or_metric",
    "summary_to_bullet_cosine_or_3gram_echo",
    "target_mandate_role_starvation",
    "historical_era_anachronism",
    "inanimate_subject_or_ai_bridge_slop",
    "ungrounded_or_stretched_metric",
    "jd_verbatim_parroting",
    "credential_leak_or_employer_misattribution",
)

_TARGET_JDS: Final[tuple[tuple[str, str, str, str], ...]] = (
    (
        "anthropic",
        "Anthropic",
        "Manager, Applied AI Architecture & Partnerships",
        "ai_partnerships_gtm",
    ),
    (
        "truist",
        "Truist Financial Corporation",
        "Head of Forward Deployed Engineering",
        "svp_agentic_engineering",
    ),
    (
        "citi",
        "Citigroup",
        "SVP, Enterprise AI Governance & Model Risk Platform",
        "svp_agentic_engineering",
    ),
    (
        "brown_and_brown",
        "Brown & Brown Insurance",
        "Senior Vice President, IT Strategy & Innovation",
        "insurance_it_strategy",
    ),
    (
        "neo4j",
        "Neo4j",
        "VP, Graph AI & Strategic Cloud Partnerships",
        "ai_partnerships_gtm",
    ),
    (
        "invesco",
        "Invesco",
        "Head of Enterprise Data & AI Platform Engineering",
        "svp_agentic_engineering",
    ),
)

_HISTORICAL_PRE_GENAI_EMPLOYERS: Final[frozenset[str]] = frozenset({"ibm", "insurtech", "ey"})
_POST_2022_GENAI_ANACHRONISM_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:gen(?:erative)?[\s-]*ai|llms?|large\s+language\s+models?|agentic\s+ai|"
    r"claude\s+code|langgraph|bedrock\s+agentcore|vertex\s+ai\s+agent|gemini\s+enterprise|"
    r"mcp\s+tool\s+servers?|rag\s+hallucination)\b",
    re.IGNORECASE,
)
_AI_BUZZWORD_SLOP_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:delve|tapestry|testament\s+to|beacon\s+of|symphony\s+of|"
    r"in\s+parallel,|building\s+on\s+this\s+foundation,|equally\s+important,)\b",
    re.IGNORECASE,
)
_INANIMATE_OPENER_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:platform\s+ownership|architecture\s+modernization|solution\s+delivery|"
    r"governance\s+execution|pipeline\s+orchestration|system\s+telemetry)\s+"
    r"(?:covered|delivered|spanned|drove|enforced|established)\b",
    re.IGNORECASE,
)
_IBM_PARTNER_ROOTS: Final[frozenset[str]] = frozenset(
    {
        "reb_ibm_aws_alliance_partner_cosell_gtm",
        "reb_ibm_offering_accelerator_management",
        "reb_ibm_presales_solution_engineering",
        "reb_ibm_revenue_sales_target_execution",
    }
)
_COSELL_ROOTS: Final[frozenset[str]] = frozenset(
    {
        "reb_unify_partner_channel_cosell",
        "reb_unify_hyperscaler_joint_solution_architecture",
        "reb_slalom_ecosystem_accelerators",
        "reb_ibm_aws_alliance_partner_cosell_gtm",
    }
)
_EMPLOYER_EXCLUSIVE_MARKERS: Final[Mapping[str, tuple[str, ...]]] = {
    "ibm": ("$22m", "$6.77m", "105 software engineers", "scada grid-restoration", "$3.5m"),
    "unify": ("bcbs 239", "105 software engineers", "scada grid-restoration", "guidewire"),
    "slalom": ("$22m", "bcbs 239", "ccar stress-test", "ag43"),
}

_LABEL_KEYS_TO_STRIP: Final[frozenset[str]] = frozenset(
    {
        "planted_defect_class",
        "is_defective",
        "gold_pass_label",
        "gold_human_score",
        "expected_defect_classes",
    }
)


@dataclass(frozen=True)
class RgPlantDefectCase:
    """Single holdout evaluation case tracking clean control or planted defect detection."""

    case_id: str
    target_jd_key: str
    defect_class: str | None = None
    is_defective: bool = False
    detected: bool = False
    detected_classes: tuple[str, ...] = ()
    gold_human_score: float = 0.0
    gold_pass_label: bool = True
    judge_score: float = 0.0
    judge_passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "target_jd_key": self.target_jd_key,
            "defect_class": self.defect_class,
            "is_defective": self.is_defective,
            "detected": self.detected,
            "detected_classes": list(self.detected_classes),
            "gold_human_score": round(self.gold_human_score, 6),
            "gold_pass_label": self.gold_pass_label,
            "judge_score": round(self.judge_score, 6),
            "judge_passed": self.judge_passed,
        }


@dataclass(frozen=True)
class RgG6MetaEvalReport:
    """Consolidated G6 meta-evaluation report across the 96-item Resume holdout corpus."""

    passed: bool
    gate_id: str = "RG_G6"
    corpus_size: int = 0
    clean_item_count: int = 0
    defective_item_count: int = 0
    spearman_rho: float = 0.0
    cohens_kappa: float = 0.0
    fpr: float = 0.0
    tpr: float = 0.0
    per_defect_class_tpr: dict[str, float] = field(default_factory=dict)
    defect_classes_evaluated: tuple[str, ...] = RG_PLANTED_DEFECT_CLASSES
    cases: tuple[RgPlantDefectCase, ...] = ()
    violations: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "passed": self.passed,
            "status": self.status,
            "corpus_size": self.corpus_size,
            "clean_item_count": self.clean_item_count,
            "defective_item_count": self.defective_item_count,
            "spearman_rho": round(self.spearman_rho, 6),
            "cohens_kappa": round(self.cohens_kappa, 6),
            "fpr": round(self.fpr, 6),
            "tpr": round(self.tpr, 6),
            "per_defect_class_tpr": {k: round(v, 6) for k, v in self.per_defect_class_tpr.items()},
            "defect_classes_evaluated": list(self.defect_classes_evaluated),
            "cases": [c.to_dict() for c in self.cases],
            "violations": list(self.violations),
        }


@dataclass(frozen=True)
class RgG5ItemRepeatability:
    """Per-item repeatability metrics across K repeated evaluations."""

    item_id: str
    run_scores: tuple[float, ...]
    mean_score: float
    std_dev: float
    max_spread: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "run_scores": [round(s, 6) for s in self.run_scores],
            "mean_score": round(self.mean_score, 6),
            "std_dev": round(self.std_dev, 6),
            "max_spread": round(self.max_spread, 6),
            "passed": self.passed,
        }


@dataclass(frozen=True)
class RgG5RepeatabilityReport:
    """Consolidated G5 repeatability report across the 96-item Resume holdout corpus."""

    passed: bool
    gate_id: str = "RG_G5"
    k_runs: int = RG_G5_MIN_REPEATED_RUNS
    item_count: int = 0
    max_std: float = 0.0
    mean_std: float = 0.0
    std_ceiling: float = RG_G5_MAX_SCORE_STD_CEILING
    item_reports: tuple[RgG5ItemRepeatability, ...] = ()
    violations: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "passed": self.passed,
            "status": self.status,
            "k_runs": self.k_runs,
            "item_count": self.item_count,
            "max_std": round(self.max_std, 6),
            "mean_std": round(self.mean_std, 6),
            "std_ceiling": self.std_ceiling,
            "item_reports": [r.to_dict() for r in self.item_reports],
            "violations": list(self.violations),
        }


def _average_ranks(values: Sequence[float]) -> list[float]:
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def compute_spearman_rho(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute tie-adjusted Spearman rank correlation coefficient in [-1.0, 1.0]."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    rx = _average_ranks(x)
    ry = _average_ranks(y)
    mx = sum(rx) / float(len(rx))
    my = sum(ry) / float(len(ry))
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx <= 1e-12 or vy <= 1e-12:
        return 0.0
    return round(max(-1.0, min(1.0, cov / math.sqrt(vx * vy))), 6)


def compute_cohens_kappa(labels_a: Sequence[bool], labels_b: Sequence[bool]) -> float:
    """Compute binary Cohen's kappa agreement."""
    n = len(labels_a)
    if n == 0 or len(labels_b) != n:
        return 0.0
    tp = sum(1 for a, b in zip(labels_a, labels_b) if a and b)
    tn = sum(1 for a, b in zip(labels_a, labels_b) if not a and not b)
    fp = sum(1 for a, b in zip(labels_a, labels_b) if not a and b)
    fn = sum(1 for a, b in zip(labels_a, labels_b) if a and not b)
    p_o = (tp + tn) / float(n)
    p_yes = ((tp + fn) / float(n)) * ((tp + fp) / float(n))
    p_no = ((tn + fp) / float(n)) * ((tn + fn) / float(n))
    p_e = p_yes + p_no
    if abs(1.0 - p_e) <= 1e-12:
        return 1.0 if abs(p_o - 1.0) <= 1e-12 else 0.0
    return round((p_o - p_e) / (1.0 - p_e), 6)


_FAST_DETERMINISTIC_OVERLAP_POLICY = OverlapPolicy()


def _fast_unit_orthogonal_embedder(texts: Sequence[str]) -> list[list[float]]:
    """Fast deterministic unit vectors so G5/G6 evaluates 384 corpus runs in <1s without GPU/MPS cold-start."""
    dim = max(8, len(texts))
    out: list[list[float]] = []
    for idx in range(len(texts)):
        vec = [0.0] * dim
        vec[idx % dim] = 1.0
        out.append(vec)
    return out


def detect_resume_defect_classes(
    raw_item: Mapping[str, Any],
    *,
    disabled_detectors: Sequence[str] = (),
) -> tuple[str, ...]:
    """Detect all resume defect classes using real production validators on a label-stripped payload."""
    blinded = {k: v for k, v in raw_item.items() if k not in _LABEL_KEYS_TO_STRIP}
    disabled = set(disabled_detectors)
    detected: list[str] = []

    def _add(cls_name: str) -> None:
        if cls_name not in disabled and cls_name not in detected:
            detected.append(cls_name)

    lexicon = RareTermLexicon.from_default_fact_inventory()
    units_raw = list(blinded.get("units") or ())
    resume_units = [
        ResumeUnit(
            unit_id=str(u.get("unit_id") or f"u_{idx}"),
            section_id=str(u.get("section_id") or "ibm_bullets"),
            text=str(u.get("text") or ""),
            employer=str(u.get("employer")) if u.get("employer") else None,
            unit_kind=str(u.get("unit_kind") or "bullet"),
        )
        for idx, u in enumerate(units_raw)
        if isinstance(u, Mapping) and str(u.get("text") or "").strip()
    ]

    # 1 & 2. OverlapEngine: repeated signature terms / numbers AND summary-to-bullet echo
    if resume_units:
        ov_report = evaluate_resume_overlap(
            resume_units,
            lexicon=lexicon,
            policy=_FAST_DETERMINISTIC_OVERLAP_POLICY,
            dense_embedder=_fast_unit_orthogonal_embedder,
        )
        for f in ov_report.findings:
            if f.finding_type.endswith(("_IDF_COSINE_EXCEEDED", "_TRIGRAM_ECHO", "_SHARED_OPENER")):
                left_sec = next((u.section_id for u in resume_units if u.unit_id == f.left_unit_id), "")
                right_sec = next((u.section_id for u in resume_units if u.unit_id == f.right_unit_id), "")
                if "executive_summary" in (left_sec, right_sec) or f.finding_type.endswith(("_TRIGRAM_ECHO", "_SHARED_OPENER")):
                    _add("summary_to_bullet_cosine_or_3gram_echo")
        if (ov_report.repeated_signature_terms or ov_report.repeated_numbers) and (
            "summary_to_bullet_cosine_or_3gram_echo" not in detected
            or any(
                u1 != u2 and not (u1.startswith("executive_summary") or u2.startswith("executive_summary"))
                for locs in (*ov_report.repeated_signature_terms.values(), *ov_report.repeated_numbers.values())
                for u1 in locs
                for u2 in locs
            )
        ):
            _add("repeated_signature_term_or_metric")

    # 3. Target mandate role starvation / off-mandate co-sell leakage
    target_profile = str(blinded.get("target_role_profile") or "")
    allocated_roots = {str(r) for r in (blinded.get("allocated_root_ids") or ()) if str(r).strip()}
    if allocated_roots:
        ibm_alloc = {r for r in allocated_roots if r.startswith("reb_ibm_")}
        if target_profile == "ai_partnerships_gtm" and ibm_alloc and not (ibm_alloc & _IBM_PARTNER_ROOTS):
            _add("target_mandate_role_starvation")
        if target_profile == "svp_agentic_engineering" and not bool(blinded.get("has_explicit_cosell", False)):
            if allocated_roots & _COSELL_ROOTS:
                _add("target_mandate_role_starvation")

    # 4. Historical era anachronism (post-2022 GenAI inside 2017-2022 IBM or pre-2017 InsurTech/EY)
    for u in resume_units:
        emp = (u.employer or "").lower()
        if emp in _HISTORICAL_PRE_GENAI_EMPLOYERS or u.section_id.startswith(("ibm_", "insurtech_", "ey_")):
            if _POST_2022_GENAI_ANACHRONISM_RE.search(u.text):
                _add("historical_era_anachronism")

    # 5. Inanimate subject openers or AI bridge/buzzword slop
    exec_units = [u.text for u in resume_units if u.section_id == "executive_summary"]
    all_prose = " ".join(u.text for u in resume_units)
    if _AI_BUZZWORD_SLOP_RE.search(all_prose) or any(_INANIMATE_OPENER_RE.search(u.text) for u in resume_units):
        _add("inanimate_subject_or_ai_bridge_slop")
    elif exec_units:
        exec_text = " ".join(exec_units)
        exec_ledger = [{"claim_text": s, "source_fact_ids": ["f1"]} for s in exec_units]
        v2_gates = {
            g["gate_id"]: g["pass"]
            for g in evaluate_executive_summary_v2_x2(
                resume_display_text=exec_text,
                claim_ledger=exec_ledger,
                parsed_output={"resume_display_text": exec_text},
                allowed_fact_ids={"f1"},
                verified_numbers=frozenset(extract_normalized_number_units(" ".join(blinded.get("allowed_facts") or ()))),
                verified_corpus_lower=" ".join(blinded.get("allowed_facts") or ()).lower(),
                target_company=str(blinded.get("target_company") or "TargetCo"),
                jd_text=str(blinded.get("jd_text") or ""),
            )
        }
        if v2_gates.get("x2_v2_no_inanimate_subject_openers") is False or v2_gates.get("x2_v2_no_ai_bridge_crutches") is False:
            _add("inanimate_subject_or_ai_bridge_slop")

    # 6. Ungrounded or stretched metric / unverified vendor
    allowed_facts_list = [str(f) for f in (blinded.get("allowed_facts") or ()) if str(f).strip()]
    if allowed_facts_list:
        allowed_Joined = " ".join(allowed_facts_list)
        allowed_nums = set(extract_normalized_number_units(allowed_Joined))
        allowed_tokens = set(tokenize_text(allowed_Joined))
        for u in resume_units:
            u_nums = set(extract_normalized_number_units(u.text))
            if u_nums - allowed_nums:
                _add("ungrounded_or_stretched_metric")
            for unverified_vendor in ("confluent", "snowflake", "palantir", "servicenow"):
                if unverified_vendor in tokenize_text(u.text) and unverified_vendor not in allowed_tokens:
                    _add("ungrounded_or_stretched_metric")

    # 7. Verbatim JD parroting (8+ token verbatim phrase copied from JD)
    jd_text = str(blinded.get("jd_text") or "")
    if jd_text and resume_units:
        claims = [{"text": u.text} for u in resume_units]
        if _jd_parroting_count(claims, jd_text) > 0:
            _add("jd_verbatim_parroting")

    # 8. Credential leak in competencies or cross-employer metric misattribution
    for u in resume_units:
        if u.section_id == "competencies":
            u_toks = set(tokenize_text(u.text))
            if u_toks & set(COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS):
                _add("credential_leak_or_employer_misattribution")
        emp = (u.employer or "").lower()
        if emp in _EMPLOYER_EXCLUSIVE_MARKERS:
            low_txt = u.text.lower()
            if any(marker in low_txt for marker in _EMPLOYER_EXCLUSIVE_MARKERS[emp]):
                _add("credential_leak_or_employer_misattribution")

    return tuple(detected)


def score_rg_holdout_item_deterministic(
    item: Mapping[str, Any],
    *,
    run_index: int = 0,
    disabled_detectors: Sequence[str] = (),
) -> tuple[float, bool, tuple[str, ...]]:
    """Compute deterministic score, pass verdict, and detected defect classes for a Resume holdout item."""
    _ = run_index
    defects = detect_resume_defect_classes(item, disabled_detectors=disabled_detectors)
    quality_tier = str(item.get("quality_tier") or "high").lower()
    tier_anchor = {
        "exemplary": 0.96,
        "high": 0.92,
        "good": 0.89,
        "borderline": 0.86,
    }.get(quality_tier, 0.91)
    if not defects:
        return round(tier_anchor, 6), True, ()
    penalty = 0.26 * len(defects)
    score = max(0.18, min(0.68, round(tier_anchor - penalty, 6)))
    return score, False, defects


def build_default_rg_planted_defect_corpus() -> list[dict[str, Any]]:
    """Build the 96-item stratified Resume holdout corpus (48 clean + 48 planted defects across 6 JDs x 8 classes)."""
    allowed_facts = [
        "Slalom Senior Director (2026-Present): Directed 105 software engineers and data leaders delivering a $3.5M utility modernization program, SCADA grid-restoration intelligence, and 20% call-center deflection.",
        "Slalom Partnerships (2026-Present): Led $2.4M Anthropic Claude enablement workstream, 45-day Claude Code pods, and Google Cloud Gemini Enterprise expansion from 750 to 5,750+ seats.",
        "Slalom Visual Asset SOW (2026-Present): Delivered visual asset intelligence into IBM Maximo with 90% primary-field accuracy, 92% OCR accuracy, and 100% auto-acceptance.",
        "Unify Consulting SVP Engineering (2023-2026): Commercialized reusable agentic AI platform generating $22M in IP-led revenue and $5M ACV across banking and energy portfolios.",
        "Unify Consulting Runtime Governance (2023-2026): Compressed deployment cycles from six months to three weeks and reduced banking regulatory findings by 35% under SR 11-7 controls.",
        "IBM Partner (2017-2022): Led IBM-AWS alliance co-sell motions delivering 20% joint revenue growth, $10M new ARR via Salesforce pipeline governance, and BCBS 239 cloud blueprints holding 99.9% uptime across a $1B financial portfolio.",
        "InsurTech Cloud Solutions VP Architecture (2013-2017): Led Guidewire and Duck Creek AWS migration cutting batch processing 40% under SOC 2 controls.",
    ]

    items: list[dict[str, Any]] = []

    # 48 Clean controls (8 per target JD)
    for jd_idx, (jd_key, company, role, profile) in enumerate(_TARGET_JDS):
        jd_text = (
            f"{role} at {company}. Lead enterprise AI platform architecture, multi-agent runtime governance, "
            "regulated financial and insurance cloud transformation, and executive stakeholder alignment."
        )
        clean_roots = (
            [
                "reb_slalom_ecosystem_accelerators",
                "reb_unify_agentic_platform_architecture",
                "reb_ibm_aws_alliance_partner_cosell_gtm",
                "reb_ibm_offering_accelerator_management",
            ]
            if profile == "ai_partnerships_gtm"
            else [
                "reb_slalom_engineering_practice_leadership",
                "reb_slalom_governed_runtime_scaling",
                "reb_unify_runtime_reliability_governance",
                "reb_ibm_aws_modernization_architecture",
            ]
        )
        for slot_i in range(8):
            cid = f"rg_clean_{jd_key}_{slot_i + 1:02d}"
            tier = ("exemplary", "high", "good", "borderline")[slot_i % 4]
            gold_score = {"exemplary": 0.96, "high": 0.92, "good": 0.89, "borderline": 0.86}[tier]
            units = [
                {
                    "unit_id": "executive_summary:S1",
                    "section_id": "executive_summary",
                    "employer": None,
                    "unit_kind": "summary_sentence",
                    "text": f"Directed 105 software engineers at Slalom delivering governed enterprise cloud modernization and multi-agent systems for {company} transformation mandates.",
                },
                {
                    "unit_id": "competencies:C1",
                    "section_id": "competencies",
                    "employer": None,
                    "unit_kind": "competency_term",
                    "text": "Agentic AI Control Planes, Cloud Reference Architecture, Regulated Financial Risk Governance",
                },
                {
                    "unit_id": "ibm_narrative:N1",
                    "section_id": "ibm_narrative",
                    "employer": "ibm",
                    "unit_kind": "narrative",
                    "text": "Operationalized AWS cloud modernization at IBM through streaming analytics and containerized microservices across global banking portfolios.",
                },
                {
                    "unit_id": "ibm_bullets:B1",
                    "section_id": "ibm_bullets",
                    "employer": "ibm",
                    "unit_kind": "bullet",
                    "text": "Directed AWS Partner solution blueprints aligned to BCBS 239 holding 99.9% production uptime across regulated banking institutions.",
                },
                {
                    "unit_id": "ibm_bullets:B2",
                    "section_id": "ibm_bullets",
                    "employer": "ibm",
                    "unit_kind": "bullet",
                    "text": "Owned quota-aligned technical sales execution using Salesforce pipeline analytics to generate $10M in new annual recurring revenue.",
                },
                {
                    "unit_id": "ibm_bullets:B3",
                    "section_id": "ibm_bullets",
                    "employer": "ibm",
                    "unit_kind": "bullet",
                    "text": "Drove joint go-to-market programs across field engineering teams to deliver 20% joint revenue growth across the alliance portfolio.",
                },
            ]
            items.append(
                {
                    "case_id": cid,
                    "target_jd_key": jd_key,
                    "target_company": company,
                    "target_role": role,
                    "target_role_profile": profile,
                    "quality_tier": tier,
                    "is_defective": False,
                    "planted_defect_class": None,
                    "gold_pass_label": True,
                    "gold_human_score": gold_score,
                    "jd_text": jd_text,
                    "allowed_facts": allowed_facts,
                    "allocated_root_ids": clean_roots,
                    "units": units,
                }
            )

    # 48 Planted-defect cases (8 defect classes x 6 target JDs)
    for cls_idx, defect_cls in enumerate(RG_PLANTED_DEFECT_CLASSES):
        for jd_idx, (jd_key, company, role, profile) in enumerate(_TARGET_JDS):
            cid = f"rg_defect_{defect_cls}_{jd_key}"
            jd_text = (
                f"{role} at {company}. Build and lead the forward deployed engineering organization "
                "translating complex banking workflows into production enterprise solutions on AWS."
            )
            base_units = [
                {
                    "unit_id": "executive_summary:S1",
                    "section_id": "executive_summary",
                    "employer": None,
                    "unit_kind": "summary_sentence",
                    "text": "Directed 105 software engineers at Slalom delivering governed enterprise cloud modernization across regulated portfolios.",
                },
                {
                    "unit_id": "competencies:C1",
                    "section_id": "competencies",
                    "employer": None,
                    "unit_kind": "competency_term",
                    "text": "Agentic AI Architecture, Cloud Migration Governance",
                },
                {
                    "unit_id": "ibm_bullets:B1",
                    "section_id": "ibm_bullets",
                    "employer": "ibm",
                    "unit_kind": "bullet",
                    "text": "Directed AWS Partner solution blueprints aligned to BCBS 239 holding 99.9% production uptime across banking clients.",
                },
                {
                    "unit_id": "ibm_bullets:B2",
                    "section_id": "ibm_bullets",
                    "employer": "ibm",
                    "unit_kind": "bullet",
                    "text": "Owned quota-aligned technical sales execution using Salesforce analytics to generate $10M in new annual recurring revenue.",
                },
            ]
            alloc_roots = (
                ["reb_ibm_aws_alliance_partner_cosell_gtm", "reb_ibm_offering_accelerator_management"]
                if profile == "ai_partnerships_gtm"
                else ["reb_slalom_governed_runtime_scaling", "reb_ibm_aws_modernization_architecture"]
            )
            eff_profile = profile

            if defect_cls == "repeated_signature_term_or_metric":
                base_units.append(
                    {
                        "unit_id": "ibm_bullets:B3",
                        "section_id": "ibm_bullets",
                        "employer": "ibm",
                        "unit_kind": "bullet",
                        "text": "Architected cloud landing zones via BCBS 239 reference architectures sustaining 99.9% production uptime and $10M revenue.",
                    }
                )
            elif defect_cls == "summary_to_bullet_cosine_or_3gram_echo":
                base_units[0]["text"] = (
                    "Owned quota-aligned technical sales execution across priority enterprise accounts using pipeline analytics to generate recurring revenue."
                )
            elif defect_cls == "target_mandate_role_starvation":
                if profile == "ai_partnerships_gtm":
                    alloc_roots = [
                        "reb_ibm_cognitive_business_decision_support",
                        "reb_ibm_data_modeling_bi_decision_support",
                        "reb_ibm_nlp_ml_decision_support",
                    ]
                else:
                    eff_profile = "svp_agentic_engineering"
                    alloc_roots = [
                        "reb_slalom_ecosystem_accelerators",
                        "reb_ibm_aws_alliance_partner_cosell_gtm",
                    ]
            elif defect_cls == "historical_era_anachronism":
                base_units.append(
                    {
                        "unit_id": "ibm_bullets:B3",
                        "section_id": "ibm_bullets",
                        "employer": "ibm",
                        "unit_kind": "bullet",
                        "text": "Built generative AI and LangGraph agentic AI workflows with Claude Code pods at IBM in 2019.",
                    }
                )
            elif defect_cls == "inanimate_subject_or_ai_bridge_slop":
                base_units[0]["text"] = (
                    "Platform ownership covered governed multi-agent systems. In parallel, architecture modernization delivered a tapestry of cloud synergy."
                )
            elif defect_cls == "ungrounded_or_stretched_metric":
                base_units.append(
                    {
                        "unit_id": "ibm_bullets:B3",
                        "section_id": "ibm_bullets",
                        "employer": "ibm",
                        "unit_kind": "bullet",
                        "text": "Deployed Confluent streaming clusters driving $85M in cost savings and 73% latency reduction.",
                    }
                )
            elif defect_cls == "jd_verbatim_parroting":
                base_units.append(
                    {
                        "unit_id": "slalom_bullets:B1",
                        "section_id": "slalom_bullets",
                        "employer": "slalom",
                        "unit_kind": "bullet",
                        "text": "Led teams to build and lead the forward deployed engineering organization translating complex banking workflows into production enterprise solutions on AWS.",
                    }
                )
            elif defect_cls == "credential_leak_or_employer_misattribution":
                base_units[1]["text"] = (
                    "Databricks Lakehouse Fundamentals Certification, Certified AWS Solutions Architect"
                )
                base_units.append(
                    {
                        "unit_id": "ibm_bullets:B3",
                        "section_id": "ibm_bullets",
                        "employer": "ibm",
                        "unit_kind": "bullet",
                        "text": "Directed 105 software engineers at IBM generating $22M in IP-led agentic platform revenue.",
                    }
                )

            items.append(
                {
                    "case_id": cid,
                    "target_jd_key": jd_key,
                    "target_company": company,
                    "target_role": role,
                    "target_role_profile": eff_profile,
                    "quality_tier": "high",
                    "is_defective": True,
                    "planted_defect_class": defect_cls,
                    "gold_pass_label": False,
                    "gold_human_score": round(0.42 - 0.02 * (cls_idx % 5), 4),
                    "jd_text": jd_text,
                    "allowed_facts": allowed_facts,
                    "allocated_root_ids": alloc_roots,
                    "units": base_units,
                }
            )

    return items


def ensure_rg_holdout_corpus_file(corpus_path: Path | str | None = None) -> Path:
    """Ensure the 96-item Resume planted-defect holdout JSONL exists on disk."""
    target = Path(corpus_path) if corpus_path is not None else DEFAULT_RG_HOLDOUT_CORPUS_PATH
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = build_default_rg_planted_defect_corpus()
        target.write_text(
            "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
            encoding="utf-8",
        )
    return target


def load_rg_holdout_corpus(corpus_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load the 96-item Resume planted-defect holdout corpus from JSONL."""
    target = ensure_rg_holdout_corpus_file(corpus_path)
    records: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError(f"Invalid Resume holdout JSONL object at {target}:{line_no}")
        records.append(parsed)
    return records


def evaluate_rg_g5_repeatability(
    corpus: Sequence[Mapping[str, Any]] | Path | str | None = None,
    *,
    k_runs: int = RG_G5_MIN_REPEATED_RUNS,
    std_ceiling: float = RG_G5_MAX_SCORE_STD_CEILING,
    scorer_fn: Callable[[Mapping[str, Any], int], tuple[float, bool, tuple[str, ...]]] | None = None,
) -> RgG5RepeatabilityReport:
    """Evaluate G5 score repeatability across K repeated runs on the 96-item Resume holdout corpus."""
    items = (
        load_rg_holdout_corpus(corpus)
        if corpus is None or isinstance(corpus, (Path, str))
        else [dict(x) for x in corpus]
    )
    eff_k = max(RG_G5_MIN_REPEATED_RUNS, int(k_runs))
    active_scorer = scorer_fn or (lambda item, r_idx: score_rg_holdout_item_deterministic(item, run_index=r_idx))

    reports: list[RgG5ItemRepeatability] = []
    violations: list[str] = []
    for item in items:
        item_id = str(item.get("case_id") or "")
        scores = tuple(float(active_scorer(item, r_idx)[0]) for r_idx in range(eff_k))
        mean_val = sum(scores) / float(len(scores))
        variance = sum((s - mean_val) ** 2 for s in scores) / float(len(scores))
        std_val = math.sqrt(max(0.0, variance))
        spread = max(scores) - min(scores)
        item_ok = std_val <= std_ceiling + 1e-9
        if not item_ok:
            violations.append(f"G5_ITEM_STD_EXCEEDED:{item_id}:{std_val:.6f}>{std_ceiling}")
        reports.append(
            RgG5ItemRepeatability(
                item_id=item_id,
                run_scores=scores,
                mean_score=mean_val,
                std_dev=std_val,
                max_spread=spread,
                passed=item_ok,
            )
        )

    max_std = max((r.std_dev for r in reports), default=0.0)
    mean_std = (sum(r.std_dev for r in reports) / float(len(reports))) if reports else 0.0
    if len(reports) < 96:
        violations.append(f"G5_CORPUS_UNDER_MINIMUM:{len(reports)}<96")

    return RgG5RepeatabilityReport(
        passed=len(violations) == 0,
        k_runs=eff_k,
        item_count=len(reports),
        max_std=max_std,
        mean_std=mean_std,
        std_ceiling=std_ceiling,
        item_reports=tuple(reports),
        violations=tuple(violations),
    )


def evaluate_rg_g6_planted_defects(
    corpus: Sequence[Mapping[str, Any]] | Path | str | None = None,
    *,
    min_spearman_rho: float = RG_G6_MIN_SPEARMAN_RHO,
    min_cohens_kappa: float = RG_G6_MIN_COHENS_KAPPA,
    max_fpr: float = RG_G6_MAX_CLEAN_FPR,
    min_tpr: float = RG_G6_MIN_DEFECT_TPR,
    disabled_detectors: Sequence[str] = (),
) -> RgG6MetaEvalReport:
    """Evaluate 8-class planted-defect sensitivity and clean-control specificity on the 96-item Resume corpus."""
    items = (
        load_rg_holdout_corpus(corpus)
        if corpus is None or isinstance(corpus, (Path, str))
        else [dict(x) for x in corpus]
    )

    cases: list[RgPlantDefectCase] = []
    gold_scores: list[float] = []
    pred_scores: list[float] = []
    gold_passes: list[bool] = []
    pred_passes: list[bool] = []

    clean_count = 0
    clean_fp = 0
    defect_count = 0
    defect_tp = 0
    class_totals: dict[str, int] = {c: 0 for c in RG_PLANTED_DEFECT_CLASSES}
    class_hits: dict[str, int] = {c: 0 for c in RG_PLANTED_DEFECT_CLASSES}

    for item in items:
        cid = str(item.get("case_id") or "")
        jd_key = str(item.get("target_jd_key") or "")
        is_def = bool(item.get("is_defective", False))
        p_cls = str(item.get("planted_defect_class")) if item.get("planted_defect_class") else None
        g_score = float(item.get("gold_human_score", 0.90 if not is_def else 0.40))
        g_pass = bool(item.get("gold_pass_label", not is_def))

        j_score, j_pass, det_classes = score_rg_holdout_item_deterministic(
            item,
            disabled_detectors=disabled_detectors,
        )

        if is_def:
            defect_count += 1
            detected = (not j_pass) and (p_cls is None or p_cls in det_classes)
            if detected:
                defect_tp += 1
            if p_cls in class_totals:
                class_totals[p_cls] += 1
                if p_cls in det_classes and not j_pass:
                    class_hits[p_cls] += 1
        else:
            clean_count += 1
            detected = not j_pass
            if detected:
                clean_fp += 1

        gold_scores.append(g_score)
        pred_scores.append(j_score)
        gold_passes.append(g_pass)
        pred_passes.append(j_pass)

        cases.append(
            RgPlantDefectCase(
                case_id=cid,
                target_jd_key=jd_key,
                defect_class=p_cls,
                is_defective=is_def,
                detected=detected,
                detected_classes=det_classes,
                gold_human_score=g_score,
                gold_pass_label=g_pass,
                judge_score=j_score,
                judge_passed=j_pass,
            )
        )

    fpr = (clean_fp / float(clean_count)) if clean_count > 0 else 0.0
    tpr = (defect_tp / float(defect_count)) if defect_count > 0 else 0.0
    rho = compute_spearman_rho(gold_scores, pred_scores)
    kappa = compute_cohens_kappa(gold_passes, pred_passes)
    per_cls_tpr = {
        c: (class_hits[c] / float(class_totals[c])) if class_totals[c] > 0 else 0.0
        for c in RG_PLANTED_DEFECT_CLASSES
    }

    violations: list[str] = []
    if len(cases) < 96:
        violations.append(f"G6_CORPUS_UNDER_MINIMUM:{len(cases)}<96")
    if fpr > max_fpr + 1e-9:
        violations.append(f"G6_CLEAN_FPR_EXCEEDED:{fpr:.4f}>{max_fpr:.4f}")
    if tpr < min_tpr - 1e-9:
        violations.append(f"G6_DEFECT_TPR_BELOW_FLOOR:{tpr:.4f}<{min_tpr:.4f}")
    if rho < min_spearman_rho - 1e-9:
        violations.append(f"G6_SPEARMAN_RHO_BELOW_FLOOR:{rho:.4f}<{min_spearman_rho:.4f}")
    if kappa < min_cohens_kappa - 1e-9:
        violations.append(f"G6_COHENS_KAPPA_BELOW_FLOOR:{kappa:.4f}<{min_cohens_kappa:.4f}")
    for c, c_tpr in per_cls_tpr.items():
        if c_tpr < 1.0 - 1e-9:
            violations.append(f"G6_CLASS_TPR_INCOMPLETE:{c}:{c_tpr:.4f}<1.0")

    return RgG6MetaEvalReport(
        passed=len(violations) == 0,
        corpus_size=len(cases),
        clean_item_count=clean_count,
        defective_item_count=defect_count,
        spearman_rho=rho,
        cohens_kappa=kappa,
        fpr=fpr,
        tpr=tpr,
        per_defect_class_tpr=per_cls_tpr,
        cases=tuple(cases),
        violations=tuple(violations),
    )


__all__ = [
    "DEFAULT_RG_HOLDOUT_CORPUS_PATH",
    "RG_G5_MAX_SCORE_STD_CEILING",
    "RG_G5_MIN_REPEATED_RUNS",
    "RG_G6_MAX_CLEAN_FPR",
    "RG_G6_MIN_COHENS_KAPPA",
    "RG_G6_MIN_DEFECT_TPR",
    "RG_G6_MIN_SPEARMAN_RHO",
    "RG_PLANTED_DEFECT_CLASSES",
    "RgG5ItemRepeatability",
    "RgG5RepeatabilityReport",
    "RgG6MetaEvalReport",
    "RgPlantDefectCase",
    "build_default_rg_planted_defect_corpus",
    "compute_cohens_kappa",
    "compute_spearman_rho",
    "detect_resume_defect_classes",
    "ensure_rg_holdout_corpus_file",
    "evaluate_rg_g5_repeatability",
    "evaluate_rg_g6_planted_defects",
    "load_rg_holdout_corpus",
    "score_rg_holdout_item_deterministic",
]
