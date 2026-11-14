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
    r"exec_summary_perf_sync_helpers|executive_summary_voice_repair)\.py\b)",
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


def validate_holistic_pipeline_alignment(
    content: str, waves: Sequence[object], filename: str
) -> list[str]:
    """Enforce INV-HOLISTIC-PIPELINE-PLANNING on domain section/bullet generation plans.

    When a plan modifies intermediate section/bullet generation or authority-repair lanes
    (e.g., role_episode_lane.py, ibm_bullets_lane.py, unify_bullets_lane.py,
    section_authority_repairs.py), it must also verify or realign both:
      1. Upstream Producer / Allocation (Stage-1 Retrieval / Stage-2 C0.3 Graph Allocation & FactAnchor), and
      2. Downstream Cross-Section / Quality-Floor Validation (Stage-4 X2 validators / entailment gates).
    """
    deliverable_text = "\n".join(
        item
        for wave in waves
        for item in getattr(wave, "deliverable_items", [])
    )
    if not _SECTION_BULLET_DELIVERABLE_RE.search(deliverable_text):
        return []

    errors: list[str] = []
    has_upstream = bool(_UPSTREAM_PRODUCER_RE.search(content))
    has_downstream = bool(_DOWNSTREAM_VALIDATOR_RE.search(content))

    missing_stages: list[str] = []
    if not has_upstream:
        missing_stages.append(
            "Upstream Producer/Allocation stage (e.g., Stage-1 retrieval / Stage-2 C0.3 "
            "resume_graph_allocation.py / FactAnchor contract or explicit upstream defense)"
        )
    if not has_downstream:
        missing_stages.append(
            "Downstream Cross-Section/X2 Validation stage (e.g., Stage-4 cross_section_x2.py / "
            "bullet_quality_floor_x2.py / narrative_quality_x2.py / bullet_fact_entailment.py)"
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
