"""Domain validators for outreach drafts."""

from __future__ import annotations

import re
from typing import Final, List, Optional

from apps_lic.domain.models import ChannelType, OutreachMessageDraft, ValidationResult

# Curated spam triggers based on apps_lic/config/spam_trigger_phrases.py
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


class SpamTriggerValidator:
    """Scans text for aggressive CTAs, false urgency, or generic cliches."""

    def validate(self, text: str) -> tuple[bool, List[str], List[str]]:
        violations: List[str] = []
        warnings: List[str] = []

        for pat in _CRITICAL_SPAM_TRIGGERS:
            if pat.search(text):
                violations.append(f"Critical spam trigger matched: '{pat.pattern}'")

        for pat in _HIGH_SPAM_TRIGGERS:
            if pat.search(text):
                violations.append(f"High-severity pushy CTA matched: '{pat.pattern}'")

        for pat in _GENERIC_OPENER_TRIGGERS:
            if pat.search(text):
                warnings.append(f"Generic cliche opener matched: '{pat.pattern}'")

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
