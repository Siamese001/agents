"""Text Parsing and Normalization for Executive Summary Section.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
"""

from __future__ import annotations

import re


def tokenize_sentences(text: str) -> list[str]:
    """Split text into sentences cleanly."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def extract_bullets(text: str) -> list[str]:
    """Extract individual bullet points from markdown text."""
    bullets: list[str] = []
    for line in text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith(("-", "*", "•")):
            bullets.append(re.sub(r"^[-*•]\s*", "", trimmed))
    return bullets


def count_words(text: str) -> int:
    """Accurately count word tokens."""
    return len(re.findall(r"\b\w+\b", text))
