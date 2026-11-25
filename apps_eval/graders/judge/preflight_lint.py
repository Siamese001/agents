"""Stage A Zero-Token Deterministic Preflight Lint (`<= 200L`).

Executes structural, length, citation, markdown-link, prompt-injection, and
anti-AI-voice checks BEFORE Stage B blind LLM judging. Never masquerades as an
LLM judge: always emits `evaluator_kind="deterministic_gate"`,
`llm_judge_executed=False`, and `normalized_unit_score=None`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any, Mapping, Sequence

from apps_eval.graders.judge._core_governance_bridge import get_judge_v3_rigor_engine

_rigor = get_judge_v3_rigor_engine()

_AI_BUZZWORD_RE = re.compile(
    r"\b(delve|testament|tapestry|pivotal|foster|underscore|moreover|furthermore|synergy|holistic|paradigm|seamless|symphony|multifaceted|game-changer|cutting-edge)\b",
    re.IGNORECASE,
)
_EM_DASH_RE = re.compile(r"[\u2014\u2013]| -- ")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)")
_PROMPT_INJECTION_RE = re.compile(
    r"\b(?:ignore\s+all\s+previous\s+instructions|bypass\s+the\s+safety\s+gate|disregard\s+system\s+prompt)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class PreflightLintReceipt:
    """Explicitly tagged Stage A deterministic preflight receipt."""

    verdict: str  # "TIER_1_PASSED" | "TIER_1_BLOCKED"
    passed: bool
    failed_gates: list[str] = field(default_factory=list)
    gate_details: dict[str, Any] = field(default_factory=dict)
    tokens_spent: int = 0
    evaluator_kind: str = "deterministic_gate"
    llm_judge_executed: bool = False
    normalized_unit_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Tier1GateReceipt = PreflightLintReceipt


def run_preflight_lint(
    candidate: Any,
    *,
    required_keys: Sequence[str] = (),
    required_grounding_ids: Sequence[str] = (),
    enforce_anti_ai_filter: bool = True,
    forbid_markdown_links: bool = False,
    forbid_prompt_injection: bool = True,
    min_words: int | None = None,
    max_words: int | None = None,
    max_chars: int | None = None,
    min_sentences: int | None = None,
    max_sentences: int | None = None,
) -> PreflightLintReceipt:
    """Run Stage A zero-token structural and hygiene gates before Stage B LLM judging."""
    failed_gates: list[str] = []
    details: dict[str, Any] = {}

    if candidate is None:
        return PreflightLintReceipt(
            verdict="TIER_1_BLOCKED",
            passed=False,
            failed_gates=["empty_candidate"],
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
        text_surface = " ".join(str(v) for v in candidate.values() if isinstance(v, str)).strip()
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

    if forbid_markdown_links and text_surface and _MARKDOWN_LINK_RE.search(text_surface):
        failed_gates.append("markdown_link_forbidden")

    if forbid_prompt_injection and text_surface:
        central_stage_a = _rigor.run_stage_a_preflight(
            candidate if isinstance(candidate, (str, Mapping)) else text_surface,
            min_words=0,
            enforce_anti_ai_filter=False,
            forbid_prompt_injection=True,
        )
        if _PROMPT_INJECTION_RE.search(text_surface) or "STAGE_A_PROMPT_INJECTION_DETECTED" in central_stage_a.failed_gates:
            failed_gates.append("prompt_injection_directive_detected")

    if text_surface:
        words = text_surface.split()
        details["word_count"] = len(words)
        details["char_count"] = len(text_surface)
        if min_words is not None and len(words) < min_words:
            failed_gates.append("word_floor_underrun")
        if max_words is not None and len(words) > max_words:
            failed_gates.append("word_budget_exceeded")
        if max_chars is not None and len(text_surface) > max_chars:
            failed_gates.append("char_budget_exceeded")
        if min_sentences is not None or max_sentences is not None:
            sents = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text_surface) if s.strip()]
            details["sentence_count"] = len(sents)
            if min_sentences is not None and len(sents) < min_sentences:
                failed_gates.append("sentence_floor_underrun")
            if max_sentences is not None and len(sents) > max_sentences:
                failed_gates.append("sentence_ceiling_exceeded")

    passed = len(failed_gates) == 0
    return PreflightLintReceipt(
        verdict="TIER_1_PASSED" if passed else "TIER_1_BLOCKED",
        passed=passed,
        failed_gates=failed_gates,
        gate_details=details,
    )


run_tier1_deterministic_pre_judge = run_preflight_lint


def screen_handoff_payload_deterministic(*, body: bytes) -> PreflightLintReceipt:
    """Deterministic handoff injection screen (zero fake scores, zero fake token counts)."""
    try:
        decoded = body.decode("utf-8") if body else ""
    except UnicodeDecodeError:
        decoded = ""
    return run_preflight_lint(
        decoded or "{}",
        enforce_anti_ai_filter=False,
        forbid_prompt_injection=True,
    )


__all__ = [
    "PreflightLintReceipt",
    "Tier1GateReceipt",
    "run_preflight_lint",
    "run_tier1_deterministic_pre_judge",
    "screen_handoff_payload_deterministic",
]
