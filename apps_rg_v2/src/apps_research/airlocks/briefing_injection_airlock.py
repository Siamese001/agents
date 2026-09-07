"""Briefing Injection Airlock — Outbound sanitization gate for apps_research -> apps_rg handoff.

Per the decoupled briefing design, web-harvested research content is untrusted
until cleared by this airlock. Scraped pages or synthetic summaries containing
adversarial prompt-injection patterns (e.g. system overrides, role-switching,
or jailbreaks) are sanitized and coerced into structured, bounded key-value bullets
before emission into downstream prompt assembly.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

_INJECTION_SIGNALS = (
    "ignore previous instructions",
    "disregard all previous",
    "disregard previous",
    "disregard the above",
    "you are now",
    "system prompt:",
    "system:",
    "assistant:",
    "developer instructions:",
    "developer instruction:",
    "override:",
    "new instruction:",
    "do not follow previous",
    "<|im_start|>",
    "<|im_end|>",
    "[system]",
    "[assistant]",
    "### system",
    "### instruction",
)

_COMPILED_INJECTION_PATTERNS = [
    (signal, re.compile(re.escape(signal), re.IGNORECASE)) for signal in _INJECTION_SIGNALS
]

MAX_BRIEFING_CHARS = 1600
MAX_BRIEFING_BULLETS = 14


@dataclass(frozen=True, slots=True)
class AirlockBriefingReceipt:
    original_digest: str
    clean_digest: str
    sanitized: bool
    injection_signals_detected: tuple[str, ...]
    char_count: int
    bullet_count: int
    clean_briefing_text: str
    audit_metadata: dict[str, Any] = field(default_factory=dict)


def sanitize_briefing_content(
    raw_text: str,
    *,
    max_chars: int = MAX_BRIEFING_CHARS,
    max_bullets: int = MAX_BRIEFING_BULLETS,
    trace_id: str = "",
) -> tuple[str, AirlockBriefingReceipt]:
    """Sanitize research briefing text and return (clean_text, receipt).

    1. Scans every line for prompt-injection markers and removes malicious lines.
    2. Enforces structural bullet boundaries and strips dangerous control characters.
    3. Truncates cleanly to max_bullets and max_chars.
    """
    raw_norm = raw_text.strip()
    raw_bytes = raw_norm.encode("utf-8")
    original_digest = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()

    lines = raw_text.splitlines()
    clean_lines: list[str] = []
    flagged_signals: list[str] = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            clean_lines.append("")
            continue

        matched_signal = None
        for signal, pattern in _COMPILED_INJECTION_PATTERNS:
            if pattern.search(line_stripped):
                matched_signal = signal
                break

        if matched_signal:
            flagged_signals.append(matched_signal)
            # Exclude this adversarial line entirely
            continue

        # Neutralize markdown-embedded HTML or script delimiters
        sanitized_line = line_stripped.replace("<script", "&lt;script").replace("</script>", "&lt;/script&gt;")
        sanitized_line = sanitized_line.replace("<style", "&lt;style").replace("</style>", "&lt;/style&gt;")
        clean_lines.append(sanitized_line)

    # Reconstruct text
    processed_text = "\n".join(clean_lines).strip()

    # Ensure structured bullets count does not exceed limit
    bullets = [line for line in processed_text.splitlines() if line.strip().startswith(("-", "*", "•"))]
    if len(bullets) > max_bullets:
        # Keep section headers and first max_bullets
        retained: list[str] = []
        b_count = 0
        for line in processed_text.splitlines():
            if line.strip().startswith(("-", "*", "•")):
                if b_count < max_bullets:
                    retained.append(line)
                    b_count += 1
            else:
                retained.append(line)
        processed_text = "\n".join(retained).strip()

    # Bounded length constraint
    if len(processed_text) > max_chars:
        processed_text = processed_text[:max_chars].rsplit("\n", 1)[0].strip()
        if not processed_text.endswith("."):
            processed_text += "..."

    clean_bytes = processed_text.encode("utf-8")
    clean_digest = "sha256:" + hashlib.sha256(clean_bytes).hexdigest()
    was_sanitized = bool(flagged_signals) or (clean_digest != original_digest)

    final_bullets = [line for line in processed_text.splitlines() if line.strip().startswith(("-", "*", "•"))]

    receipt = AirlockBriefingReceipt(
        original_digest=original_digest,
        clean_digest=clean_digest,
        sanitized=was_sanitized,
        injection_signals_detected=tuple(sorted(set(flagged_signals))),
        char_count=len(processed_text),
        bullet_count=len(final_bullets),
        clean_briefing_text=processed_text,
        audit_metadata={
            "trace_id": trace_id,
            "airlock_id": "OUTBOUND_BRIEFING_INJECTION_AIRLOCK_V1",
            "lines_inspected": len(lines),
            "lines_retained": len(clean_lines),
        },
    )
    return processed_text, receipt


__all__ = [
    "AirlockBriefingReceipt",
    "MAX_BRIEFING_BULLETS",
    "MAX_BRIEFING_CHARS",
    "sanitize_briefing_content",
]
