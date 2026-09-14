"""Section Generation Service.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Coordinates execution of discrete resume section lanes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True, slots=True)
class SectionOutput:
    """Output of a section generation lane execution."""

    section_id: str
    content: str
    is_success: bool
    metadata: Mapping[str, Any]


class SectionGenerationService:
    """Service governing generation of individual resume sections."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[Mapping[str, Any]], str]] = {}

    def register_handler(
        self,
        section_id: str,
        handler: Callable[[Mapping[str, Any]], str],
    ) -> None:
        """Register a handler for a section lane."""
        self._handlers[section_id] = handler

    def generate_section(
        self,
        section_id: str,
        inputs: Mapping[str, Any],
    ) -> SectionOutput:
        """Execute generation for a specific section lane."""
        handler = self._handlers.get(section_id)
        if not handler:
            # Default nominal section generator if no handler registered
            return SectionOutput(
                section_id=section_id,
                content=f"# {section_id.title()}\n\nContent for {section_id}.",
                is_success=True,
                metadata={"default_handler": True},
            )

        try:
            content = handler(inputs)
            return SectionOutput(
                section_id=section_id,
                content=content,
                is_success=True,
                metadata={"handler": handler.__name__ if hasattr(handler, "__name__") else "callable"},
            )
        except Exception as exc:
            return SectionOutput(
                section_id=section_id,
                content="",
                is_success=False,
                metadata={"error": str(exc)},
            )
