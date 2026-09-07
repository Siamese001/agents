"""Resolved active model pins for behavior tests.

Behavior tests import these values instead of duplicating production model IDs.
Exact literals remain confined to SSOT and capability-contract tests.
"""

from apps_research.config.model_pins import (
    apps_rg_handoff_judge_pin,
    company_brief_generation_pin,
)
from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
from apps_rg.runtime.section_model_limits import (
    resolve_section_generation_model,
    resolve_selector_provider_model,
    resolve_selector_reasoning_effort,
)


CLAUDE_GENERATOR_MODEL = resolve_section_generation_model("competencies")
OPENAI_GENERATOR_MODEL = resolve_section_generation_model("unify_narrative")
_GEMINI_PROOF_JUDGE = resolve_section_proof_judge_model(
    "executive_summary", "gemini_pro"
)
GEMINI_PROOF_JUDGE_MODEL = _GEMINI_PROOF_JUDGE.model_requested
GEMINI_PROOF_JUDGE_REASONING_EFFORT = _GEMINI_PROOF_JUDGE.reasoning_effort
OPENAI_PROOF_JUDGE_MODEL = resolve_section_proof_judge_model(
    "executive_summary", "openai_chatgpt"
).model_requested
COMPETENCIES_SELECTOR_MODEL = resolve_selector_provider_model(
    "competencies_graph_pool_selector"
)[1]
COMPETENCIES_SELECTOR_REASONING_EFFORT = resolve_selector_reasoning_effort(
    "competencies_graph_pool_selector"
)
CLAUDE_SELECTOR_MODEL = resolve_selector_provider_model(
    "employment_bullet_pool_selector"
)[1]
RESEARCH_GENERATOR_MODEL = company_brief_generation_pin().model
RESEARCH_GENERATOR_REASONING_EFFORT = company_brief_generation_pin().reasoning_effort
RESEARCH_JUDGE_MODEL = apps_rg_handoff_judge_pin().model
RESEARCH_JUDGE_REASONING_EFFORT = apps_rg_handoff_judge_pin().reasoning_effort


__all__ = [
    "CLAUDE_GENERATOR_MODEL",
    "CLAUDE_SELECTOR_MODEL",
    "COMPETENCIES_SELECTOR_MODEL",
    "COMPETENCIES_SELECTOR_REASONING_EFFORT",
    "GEMINI_PROOF_JUDGE_MODEL",
    "GEMINI_PROOF_JUDGE_REASONING_EFFORT",
    "OPENAI_GENERATOR_MODEL",
    "OPENAI_PROOF_JUDGE_MODEL",
    "RESEARCH_GENERATOR_MODEL",
    "RESEARCH_GENERATOR_REASONING_EFFORT",
    "RESEARCH_JUDGE_MODEL",
    "RESEARCH_JUDGE_REASONING_EFFORT",
]
