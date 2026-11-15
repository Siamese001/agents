"""Prompt compiler and context assembler with strict guardrails."""

from __future__ import annotations

from apps_lic.pipeline.compiler_pkg.draft_composer import PromptCompiler
from apps_lic.pipeline.compiler_pkg.signatures_and_context import (
    PromptContextAssembler,
    _load_cached_yaml_template,
    get_executive_signature_block,
    get_recruiter_signature_block,
)

__all__ = [
    "PromptCompiler",
    "PromptContextAssembler",
    "_load_cached_yaml_template",
    "get_executive_signature_block",
    "get_recruiter_signature_block",
]
