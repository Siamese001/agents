"""Prompt-reception shared AgentSpec fields."""
from __future__ import annotations

from typing import Optional
from pydantic import Field


class PromptReceptionSpec:
    adapter_version: str = Field(
        default="v2",
        description="Prompt adapter version to use for this app",
    )
    exemplar_task_class: Optional[str] = Field(
        default=None,
        description="Task class name for exemplar retrieval (E0), or None if ineligible",
    )


__all__ = ["PromptReceptionSpec"]
