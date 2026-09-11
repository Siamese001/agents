"""Domain validators for outreach drafts."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final, List, Optional

from apps_lic.domain.models import ChannelType, OutreachMessageDraft, ValidationResult

# Curated spam triggers fallback based on apps_lic/config/spam_trigger_phrases.py
_CRITICAL_SPAM_TRIGGERS: Final[List[re.Pattern[str]]] = [
    re.compile(r"\bact now\b", re.IGNORECASE),
    re.compile(r"\burgent response needed\b", re.IGNORECASE),
    re.compile(r"\blimited time opportunity\b", re.IGNORECASE),
    re.compile(r"\bguaranteed interview\b", re.IGNORECASE),
    re.compile(r"\bdon't miss out\b", re.IGNORECASE),
]

_HIGH_SPAM_TRIGGERS: Final[List[re.Pattern[str]]] = [
    re.compile(r"\bjump on a quick call today\b", re.IGNORECASE),
    re.compile(r"\blet's hop on a call right now\b", re.IGNORECASE),
    re.compile(r"\bcall me at your earliest convenience\b", re.IGNORECASE),
    re.compile(r"\bI am the perfect candidate\b", re.IGNORECASE),
    re.compile(r"\byou must hire me\b", re.IGNORECASE),
]

_GENERIC_OPENER_TRIGGERS: Final[List[re.Pattern[str]]] = [
    re.compile(r"\bI hope this message finds you well\b", re.IGNORECASE),
    re.compile(r"\bI hope you are having a great week\b", re.IGNORECASE),
    re.compile(r"\bI came across your profile and was impressed\b", re.IGNORECASE),
    re.compile(r"\bAllow me to introduce myself\b", re.IGNORECASE),
]

# Channel length ceilings
_CHANNEL_MAX_CHARS: Final[dict[ChannelType, int]] = {
    ChannelType.LINKEDIN_CONNECTION: 300,
    ChannelType.LINKEDIN_INMAIL: 1900,
    ChannelType.EMAIL: 1500,
    ChannelType.FOLLOW_UP: 800,
}


def _load_canonical_spam_phrases() -> dict[str, list[re.Pattern[str]]]:
    """Load canonical spam triggers from config/spam_trigger_phrases.py if available."""
    try:
        config_path = Path(__file__).resolve().parent.parent.parent.parent / "config"
        if str(config_path) not in sys.path:
            sys.path.insert(0, str(config_path))
        from spam_trigger_phrases import SPAM_TRIGGER_PHRASES

        compiled: dict[str, list[re.Pattern[str]]] = {}
        for cat, phrases in SPAM_TRIGGER_PHRASES.items():
            compiled[cat] = [
                re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE) for p in phrases
            ]
        return compiled
    except Exception:
        return {
            "pushy_cta": _HIGH_SPAM_TRIGGERS + _CRITICAL_SPAM_TRIGGERS,
            "generic_opener": _GENERIC_OPENER_TRIGGERS,
        }


class SpamTriggerValidator:
    """Scans text for aggressive CTAs, false urgency, or generic cliches."""

    def __init__(self) -> None:
        self._categories = _load_canonical_spam_phrases()

    def validate(self, text: str) -> tuple[bool, List[str], List[str]]:
        violations: List[str] = []
        warnings: List[str] = []

        # 1. Critical hardcoded patterns (for backward compatibility)
        for pat in _CRITICAL_SPAM_TRIGGERS:
            if pat.search(text):
                violations.append(f"Critical spam trigger matched: '{pat.pattern}'")

        for pat in _HIGH_SPAM_TRIGGERS:
            if pat.search(text):
                violations.append(f"High-severity pushy CTA matched: '{pat.pattern}'")

        for pat in _GENERIC_OPENER_TRIGGERS:
            if pat.search(text):
                warnings.append(f"Generic cliche opener matched: '{pat.pattern}'")

        # 2. Canonical categories from config
        pushy = self._categories.get("pushy_cta", [])
        for pat in pushy:
            if pat.search(text) and not any(pat.pattern in v for v in violations):
                violations.append(f"Pushy sales CTA matched: '{pat.pattern}'")

        urgency = self._categories.get("false_urgency", [])
        for pat in urgency:
            if pat.search(text) and not any(pat.pattern in v for v in violations):
                violations.append(f"False urgency phrase matched: '{pat.pattern}'")

        cliches = self._categories.get("corporate_cliche", [])
        for pat in cliches:
            if pat.search(text) and not any(pat.pattern in w for w in warnings):
                warnings.append(f"Corporate cliche matched: '{pat.pattern}'")

        openers = self._categories.get("generic_opener", [])
        for pat in openers:
            if pat.search(text) and not any(pat.pattern in w for w in warnings):
                warnings.append(f"Formulaic generic opener matched: '{pat.pattern}'")

        is_valid = len(violations) == 0
        return is_valid, violations, warnings


class ChannelLengthValidator:
    """Verifies message body does not exceed strict channel ceilings."""

    def validate(self, channel: ChannelType, body: str) -> tuple[bool, Optional[str]]:
        ceiling = _CHANNEL_MAX_CHARS.get(channel, 2000)
        actual = len(body)
        if actual > ceiling:
            return False, f"Message length ({actual} chars) exceeds channel ceiling ({ceiling} chars) for {channel.value}."
        return True, None


class QuestionEndingValidator:
    """Verifies that the message concludes with a low-friction inquiry."""

    def validate(self, body: str) -> tuple[bool, Optional[str]]:
        stripped = body.strip()
        if not stripped:
            return False, "Empty message body."

        # Check if last non-whitespace sentence ends with '?'
        if not stripped.endswith("?"):
            return False, "Message does not conclude with a low-friction question mark."
        return True, None


class GroundingValidator:
    """Ensures drafts do not fabricate claims outside allowed candidate facts."""

    def validate(
        self, draft_facts_used: List[str], allowed_fact_ids: set[str]
    ) -> tuple[bool, List[str]]:
        violations: List[str] = []
        for fid in draft_facts_used:
            if fid not in allowed_fact_ids:
                violations.append(f"Ungrounded fact referenced: '{fid}'")
        return len(violations) == 0, violations


__all__ = [
    "ChannelLengthValidator",
    "GroundingValidator",
    "QuestionEndingValidator",
    "SpamTriggerValidator",
]
