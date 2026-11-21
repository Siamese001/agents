"""Tier-1 deterministic zero-token pre-judge gate executed before any LLM judge dispatch."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

_AI_BUZZWORD_RE = re.compile(
    r"\b(delve|testament|tapestry|pivotal|foster|underscore|moreover|furthermore|synergy|holistic|paradigm|seamless)\b",
    re.IGNORECASE,
)
_EM_DASH_RE = re.compile(r"[\u2014\u2013]| -- ")


@dataclass(frozen=True)
class Tier1GateReceipt:
    """Explicitly tagged deterministic pre-judge receipt (never masquerades as an LLM judge)."""

    verdict: str  # "TIER_1_PASSED" | "TIER_1_BLOCKED"
    passed: bool
    failed_gates: list[str] = field(default_factory=list)
    gate_details: dict[str, Any] = field(default_factory=dict)
    tokens_spent: int = 0
    evaluator_kind: str = "deterministic_gate"
    llm_judge_executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_tier1_deterministic_pre_judge(
    candidate: Any,
    *,
    required_keys: Sequence[str] = (),
    required_grounding_ids: Sequence[str] = (),
    enforce_anti_ai_filter: bool = True,
    max_words: int | None = None,
) -> Tier1GateReceipt:
    """Run zero-token structural, schema, grounding, and anti-AI gates before Tier-2 LLM judging."""
    failed_gates: list[str] = []
    details: dict[str, Any] = {}

    if candidate is None:
        failed_gates.append("empty_candidate")
        return Tier1GateReceipt(
            verdict="TIER_1_BLOCKED",
            passed=False,
            failed_gates=failed_gates,
            gate_details={"reason": "candidate_is_none"},
        )

    parsed_obj: Mapping[str, Any] | None = None
    text_surface = ""

    if isinstance(candidate, str):
        text_surface = candidate.strip()
        if not text_surface:
            failed_gates.append("empty_text")
        if required_keys:
            try:
                loaded = json.loads(text_surface)
                if isinstance(loaded, Mapping):
                    parsed_obj = loaded
                else:
                    failed_gates.append("json_root_not_object")
            except json.JSONDecodeError as exc:
                failed_gates.append("invalid_json_syntax")
                details["json_error"] = str(exc)
    elif isinstance(candidate, Mapping):
        parsed_obj = candidate
        text_parts: list[str] = []
        for val in candidate.values():
            if isinstance(val, str):
                text_parts.append(val)
        text_surface = " ".join(text_parts).strip()
        if not candidate:
            failed_gates.append("empty_mapping")
    else:
        text_surface = str(candidate).strip()

    if required_keys and parsed_obj is not None:
        missing = [k for k in required_keys if k not in parsed_obj or parsed_obj[k] in (None, "")]
        if missing:
            failed_gates.append("missing_required_schema_keys")
            details["missing_keys"] = missing

    if required_grounding_ids:
        missing_ids = [gid for gid in required_grounding_ids if gid not in text_surface]
        if missing_ids:
            failed_gates.append("grounding_citation_floor_failed")
            details["missing_grounding_ids"] = missing_ids

    if enforce_anti_ai_filter and text_surface:
        buzz = sorted({m.group(0).lower() for m in _AI_BUZZWORD_RE.finditer(text_surface)})
        if buzz:
            failed_gates.append("anti_ai_buzzword_violation")
            details["buzzwords"] = buzz
        if _EM_DASH_RE.search(text_surface):
            failed_gates.append("anti_ai_dash_violation")

    if max_words is not None and text_surface:
        word_count = len(text_surface.split())
        details["word_count"] = word_count
        if word_count > max_words:
            failed_gates.append("word_budget_exceeded")

    passed = len(failed_gates) == 0
    return Tier1GateReceipt(
        verdict="TIER_1_PASSED" if passed else "TIER_1_BLOCKED",
        passed=passed,
        failed_gates=failed_gates,
        gate_details=details,
        tokens_spent=0,
        evaluator_kind="deterministic_gate",
        llm_judge_executed=False,
    )
