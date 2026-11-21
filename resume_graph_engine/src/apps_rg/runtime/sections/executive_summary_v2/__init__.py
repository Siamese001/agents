"""Greenfield subtraction-first executive_summary_v2 engine (~850 LOC, zero post-LLM prose mutators)."""

from __future__ import annotations

from .blind_judge_and_loop import (
    EXEC_SUMMARY_PASS_FLOOR,
    MAX_V2_ATTEMPTS,
    LoopExecutionOutcome,
    evaluate_blind_dual_judges,
    format_blind_judge_feedback,
    format_x2_failure_feedback,
    judge_row_passes_4_7_human_bar,
    run_bounded_v2_generation_and_judge_loop,
)
from .contract_emitter import run_executive_summary_v2
from .evidence_firewall import (
    VerifiedExecutiveSummaryContext,
    load_verified_executive_summary_context,
    verify_and_compact_fact_slice,
)
from .prompt_and_generate import (
    EXEC_SUMMARY_TEMP_DEFAULT,
    EXEC_SUMMARY_TEMP_RANGE,
    GenerationTurnOutput,
    build_v2_prompt_messages,
    generate_executive_summary_v2_turn,
    load_v2_prompt_template,
    parse_strict_json_without_mutation,
)
from .x2_invariants import (
    EXEC_SUMMARY_V2_CORE_GATE_IDS,
    MAX_CHARS,
    MAX_CHARS_PER_SENTENCE,
    MAX_SENTENCES,
    MAX_WORDS,
    MIN_CHARS,
    MIN_SENTENCES,
    evaluate_executive_summary_v2_x2,
    split_sentences,
)

__all__ = [
    "EXEC_SUMMARY_PASS_FLOOR",
    "EXEC_SUMMARY_TEMP_DEFAULT",
    "EXEC_SUMMARY_TEMP_RANGE",
    "EXEC_SUMMARY_V2_CORE_GATE_IDS",
    "GenerationTurnOutput",
    "LoopExecutionOutcome",
    "MAX_CHARS",
    "MAX_CHARS_PER_SENTENCE",
    "MAX_SENTENCES",
    "MAX_V2_ATTEMPTS",
    "MAX_WORDS",
    "MIN_CHARS",
    "MIN_SENTENCES",
    "VerifiedExecutiveSummaryContext",
    "build_v2_prompt_messages",
    "evaluate_blind_dual_judges",
    "evaluate_executive_summary_v2_x2",
    "format_blind_judge_feedback",
    "format_x2_failure_feedback",
    "generate_executive_summary_v2_turn",
    "judge_row_passes_4_7_human_bar",
    "load_v2_prompt_template",
    "load_verified_executive_summary_context",
    "parse_strict_json_without_mutation",
    "run_bounded_v2_generation_and_judge_loop",
    "run_executive_summary_v2",
    "split_sentences",
    "verify_and_compact_fact_slice",
]
