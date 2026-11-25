"""Greenfield subtraction-first executive_summary_v2 engine (<=1,100 LOC, zero post-LLM prose mutators)."""
from __future__ import annotations

import importlib
from typing import Any

_EXPORT_MODULES: dict[str, str] = {
    "EXEC_SUMMARY_PASS_FLOOR": ".blind_judge_and_loop", "MAX_V2_ATTEMPTS": ".blind_judge_and_loop",
    "LoopExecutionOutcome": ".blind_judge_and_loop", "evaluate_blind_dual_judges": ".blind_judge_and_loop",
    "format_blind_judge_feedback": ".blind_judge_and_loop", "format_x2_failure_feedback": ".blind_judge_and_loop",
    "judge_row_passes_4_7_human_bar": ".blind_judge_and_loop", "run_bounded_v2_generation_and_judge_loop": ".blind_judge_and_loop",
    "run_executive_summary_v2": ".contract_emitter",
    "VerifiedExecutiveSummaryContext": ".evidence_firewall", "load_verified_executive_summary_context": ".evidence_firewall",
    "verify_and_compact_fact_slice": ".evidence_firewall",
    "EXEC_SUMMARY_TEMP_DEFAULT": ".prompt_and_generate", "EXEC_SUMMARY_TEMP_RANGE": ".prompt_and_generate",
    "GenerationTurnOutput": ".prompt_and_generate", "build_v2_prompt_messages": ".prompt_and_generate",
    "generate_executive_summary_v2_turn": ".prompt_and_generate", "load_v2_prompt_template": ".prompt_and_generate",
    "parse_strict_json_without_mutation": ".prompt_and_generate",
    "EXEC_SUMMARY_V2_CORE_GATE_IDS": ".x2_invariants", "MAX_CHARS": ".x2_invariants",
    "MAX_CHARS_PER_SENTENCE": ".x2_invariants", "MAX_SENTENCES": ".x2_invariants", "MAX_WORDS": ".x2_invariants",
    "MIN_CHARS": ".x2_invariants", "MIN_SENTENCES": ".x2_invariants",
    "evaluate_executive_summary_v2_x2": ".x2_invariants", "split_sentences": ".x2_invariants",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    mod_rel = _EXPORT_MODULES.get(name)
    if mod_rel is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    val = getattr(importlib.import_module(mod_rel, __name__), name)
    globals()[name] = val
    return val
