"""Strict length and execution-evidence checks for newly authored wave plans."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence


def _resolve_max_plan_words() -> int:
    """Resolve INV-WAVE-PLAN-MAX-WORDS dynamically from config/governance/policy_registry.yaml."""
    reg_path = Path(__file__).resolve().parents[2] / "config" / "governance" / "policy_registry.yaml"
    if reg_path.is_file():
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
            for entry in raw.get("policies", []):
                if isinstance(entry, dict) and entry.get("id") == "INV-WAVE-PLAN-MAX-WORDS":
                    val = entry.get("threshold")
                    if isinstance(val, int) and val > 0:
                        return val
        except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):  # guardian: allow-silent-swallow -- safe fallback when yaml parser unavailable
            pass
    return 1000


MAX_PLAN_WORDS: int = _resolve_max_plan_words()
_GATE_HEADING = re.compile(
    r"^#{3,4}\s+.*(?:receipt|completion\s+gate|exit\s+gate|verification).*",
    re.IGNORECASE,
)
_FIELD_PATTERNS = {
    "Run": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Run(?:\*\*)?\s*:", re.IGNORECASE),
    "Input": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Input(?:\*\*)?\s*:", re.IGNORECASE),
    "Expected": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Expected(?:\*\*)?\s*:", re.IGNORECASE),
    "Verify independently": re.compile(
        r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?(?:Verify independently|Independent check)(?:\*\*)?\s*:",
        re.IGNORECASE,
    ),
    "Fail if": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Fail if(?:\*\*)?\s*:", re.IGNORECASE),
    "Record": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Record(?:\*\*)?\s*:", re.IGNORECASE),
}

# INV-HOLISTIC-PIPELINE-PLANNING patterns
_SECTION_BULLET_DELIVERABLE_RE = re.compile(
    r"(?:runtime/sections/(?:role_episode_lane|ibm_bullets_lane|unify_bullets_lane|"
    r"exec_summary_perf_sync_helpers|executive_summary_voice_repair|section_authority_repairs|"
    r"ibm_bullets_pa|unify_bullets_pa|executive_summary_pa)|"
    r"\b(?:role_episode_lane|ibm_bullets_lane|unify_bullets_lane|section_authority_repairs|"
    r"exec_summary_perf_sync_helpers|executive_summary_voice_repair|"
    r"employment_bullet_pool|bullet_pool_claude_selector|employment_bullet_judge_rubric)\.py\b)",
    re.IGNORECASE,
)
_UPSTREAM_PRODUCER_RE = re.compile(
    r"(?:runtime/c0/|resume_graph_allocation|c0_fact_anchor|c0_perf_sync_helpers|"
    r"quad_graph_retriever|graph_role_episode_selector|fact_anchor|FactAnchor|"
    r"what\s+stays\s+unchanged|upstream\s+(?:c0|allocation|retrieval|producer))",
    re.IGNORECASE,
)
_DOWNSTREAM_VALIDATOR_RE = re.compile(
    r"(?:cross_section_x2|bullet_quality_floor_x2|bullet_line_discipline_x2|"
    r"narrative_quality_x2|executive_summary_x2|bullet_fact_entailment|"
    r"runtime/(?:validators|aggregation)/|\bx2\s+(?:gate|validator|deduplication|floor))",
    re.IGNORECASE,
)
_NEGATED_STAGE_DISMISSAL_RE = re.compile(
    r"\b(?:without\s+(?:checking|modifying|touching|updating|verifying|realigning|addressing)|"
    r"skip(?:ping)?|ignore|ignoring|omit(?:ting)?|do\s+not\s+(?:check|modify|touch|verify|realign))\b",
    re.IGNORECASE,
)
_DEFENSE_HEADING_RE = re.compile(
    r"^#{2,4}\s+.*(?:architectural\s+defense|what\s+stays\s+unchanged|"
    r"what\s+must\s+be\s+realigned|holistic|spine\s+trace|pipeline\s+contract).*",
    re.IGNORECASE,
)


def _extract_defense_lines(content: str) -> list[str]:
    lines = content.splitlines()
    active = False
    active_level = 0
    extracted: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _DEFENSE_HEADING_RE.match(stripped):
            active = True
            active_level = len(stripped) - len(stripped.lstrip("#"))
            extracted.append(stripped)
            continue
        if active and stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if level <= active_level and not _DEFENSE_HEADING_RE.match(stripped):
                active = False
                continue
        if active and stripped:
            extracted.append(stripped)
    return extracted


def _has_affirmative_stage_coverage(
    pattern: re.Pattern[str], candidate_lines: Sequence[str]
) -> bool:
    for line in candidate_lines:
        if pattern.search(line) and not _NEGATED_STAGE_DISMISSAL_RE.search(line):
            return True
    return False


def validate_holistic_pipeline_alignment(
    content: str, waves: Sequence[object], filename: str
) -> list[str]:
    """Enforce INV-HOLISTIC-PIPELINE-PLANNING on domain section/bullet generation plans.

    When a plan modifies intermediate section/bullet generation or authority-repair lanes
    (e.g., role_episode_lane.py, ibm_bullets_lane.py, unify_bullets_lane.py,
    section_authority_repairs.py), it must also verify or realign both:
      1. Upstream Producer / Allocation (Stage-1 Retrieval / Stage-2 C0.3 Graph Allocation & FactAnchor), and
      2. Downstream Cross-Section / Quality-Floor Validation (Stage-4 X2 validators / entailment gates).

    References that only appear inside negated dismissal clauses (e.g., 'without checking C0
    allocation', 'skip resume_graph_allocation.py') are rejected; stage coverage must appear
    affirmatively in wave Milestones & Deliverables, Acceptance Criteria, or an explicit
    Architectural Defense / Spine Trace section.
    """
    deliverable_lines = [
        item
        for wave in waves
        for item in getattr(wave, "deliverable_items", [])
    ]
    deliverable_text = "\n".join(deliverable_lines)
    if not _SECTION_BULLET_DELIVERABLE_RE.search(deliverable_text):
        return []

    defense_lines = _extract_defense_lines(content)
    authoritative_lines = list(deliverable_lines) + defense_lines

    errors: list[str] = []
    has_upstream = _has_affirmative_stage_coverage(_UPSTREAM_PRODUCER_RE, authoritative_lines)
    has_downstream = _has_affirmative_stage_coverage(_DOWNSTREAM_VALIDATOR_RE, authoritative_lines)

    missing_stages: list[str] = []
    if not has_upstream:
        missing_stages.append(
            "Upstream Producer/Allocation stage (e.g., Stage-1 retrieval / Stage-2 C0.3 "
            "resume_graph_allocation.py / FactAnchor contract in Milestones & Deliverables "
            "or explicit Architectural Defense)"
        )
    if not has_downstream:
        missing_stages.append(
            "Downstream Cross-Section/X2 Validation stage (e.g., Stage-4 cross_section_x2.py / "
            "bullet_quality_floor_x2.py / narrative_quality_x2.py / bullet_fact_entailment.py "
            "in Milestones & Deliverables or explicit Architectural Defense)"
        )

    if missing_stages:
        errors.append(
            f"{filename}: [INV-HOLISTIC-PIPELINE-PLANNING] Plan modifies intermediate section/bullet "
            "generation or repair lanes without addressing coupled pipeline stages: "
            f"{'; '.join(missing_stages)}. Trace the full Producer -> Consumer -> Validator spine."
        )
    return errors


def _gate_lines(wave: object) -> list[str]:
    lines = getattr(wave, "lines", [])
    active = False
    result: list[str] = []
    for _line_number, line in lines:
        if _GATE_HEADING.search(line.strip()):
            active = True
            continue
        if active and re.match(r"^\s*#{2,4}\s+", line):
            break
        if active:
            result.append(line)
    return result


def validate_execution_evidence(content: str, waves: Sequence[object], filename: str) -> list[str]:
    """Require bounded plans and explicit run/evidence fields in each wave gate."""
    errors: list[str] = []
    word_count = len(content.split())
    if word_count > MAX_PLAN_WORDS:
        errors.append(
            f"{filename}: Plan has {word_count} words; newly authored wave plans are capped at "
            f"{MAX_PLAN_WORDS} words (target 500–800)."
        )

    for wave in waves:
        gate_lines = _gate_lines(wave)
        if not gate_lines:
            continue  # The structural validator reports the missing gate heading.
        present = {
            label for label, pattern in _FIELD_PATTERNS.items()
            if any(pattern.search(line) for line in gate_lines)
        }
        missing = [label for label in _FIELD_PATTERNS if label not in present]
        if missing:
            number = getattr(wave, "number", "?")
            errors.append(
                f"{filename}: Wave {number} completion gate must specify: {', '.join(missing)}. "
                "Receipts document runs; independently observed behavior determines completion."
            )
    errors.extend(validate_holistic_pipeline_alignment(content, waves, filename))
    return errors
