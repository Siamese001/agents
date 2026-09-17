"""Domain validators for outreach drafts."""

from __future__ import annotations

import importlib.util
import re
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
    re.compile(r"\bonce in a lifetime\b", re.IGNORECASE),
    re.compile(r"\bexclusive invitation\b", re.IGNORECASE),
    re.compile(r"\bdouble your income\b", re.IGNORECASE),
    re.compile(r"\bunbelievable offer\b", re.IGNORECASE),
]

_GENERIC_OPENER_TRIGGERS: Final[List[re.Pattern[str]]] = [
    re.compile(r"\bI hope this email finds you well\b", re.IGNORECASE),
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
    """Load canonical spam triggers from config/spam_trigger_phrases.py without mutating sys.path."""
    try:
        config_file = Path(__file__).resolve().parent.parent.parent.parent / "config" / "spam_trigger_phrases.py"
        if config_file.is_file():
            spec = importlib.util.spec_from_file_location("outreach_spam_triggers", str(config_file))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                spam_dict = getattr(mod, "SPAM_TRIGGER_PHRASES", {})
                compiled: dict[str, list[re.Pattern[str]]] = {}
                for cat, phrases in spam_dict.items():
                    compiled[cat] = [
                        re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE) for p in phrases
                    ]
                if compiled:
                    return compiled
    except Exception:
        pass

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
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if lines[-1].endswith("?"):
            return True, None

        # Check if the line before a signature block ends with '?'
        signature_tokens = (
            "linkedin.com",
            "github.com",
            "+1-",
            "+1 ",
            "@",
            "officer",
            "director",
            "partner",
            "vp",
            "chief",
            "lead",
            "architect",
            "engineer",
            "regards",
            "sincerely",
            "best,",
            "best regards",
            "--",
            "__",
            "tel:",
            "phone:",
            "email:",
        )
        # Check if an inquiry ends with '?' and all trailing lines form a signature block
        for i, line in enumerate(lines):
            if line.endswith("?"):
                trailing = lines[i + 1:]
                if not trailing:
                    return True, None
                is_signature = True
                for t in trailing:
                    t_lower = t.lower().strip()
                    has_sig_token = any(tok in t_lower for tok in signature_tokens)
                    is_short_name = (
                        len(t.split()) <= 4
                        and len(t) <= 40
                        and not t.endswith((".", "!", ";", "?"))
                    )
                    if not (has_sig_token or is_short_name or t.startswith(("--", "—", "-"))):
                        is_signature = False
                        break
                if is_signature:
                    return True, None

        return False, "Message does not conclude with a low-friction question mark."


class EmDashValidator:
    """Verifies message body contains no em dashes (rule: no_em_dash)."""

    def validate(self, body: str) -> tuple[bool, Optional[str]]:
        if "—" in body or "\u2014" in body:
            return False, "Forbidden em dash detected; use standard punctuation or commas."
        return True, None


class MarkdownLinkValidator:
    """Verifies message body uses plain text links rather than markdown links."""

    _MD_LINK_PAT = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")

    def validate(self, body: str) -> tuple[bool, Optional[str]]:
        if self._MD_LINK_PAT.search(body):
            return False, "Forbidden markdown link syntax detected; use plain text URLs only."
        return True, None


class SubordinateToneValidator:
    """Detects deferential or desperate subordinate phrasing in executive outreach."""

    _SUBORDINATE_PATTERNS = [
        re.compile(r"\bwould love to learn more\b", re.IGNORECASE),
        re.compile(r"\bthink I(?:'d| would) be a (?:great|perfect) fit\b", re.IGNORECASE),
        re.compile(r"\bhoping for an? (?:opportunity|interview|chance)\b", re.IGNORECASE),
        re.compile(r"\bgive me a (?:chance|shot)\b", re.IGNORECASE),
        re.compile(r"\bplease consider my (?:application|resume|c\.?v\.?)\b", re.IGNORECASE),
        re.compile(r"\bseeking a (?:role|job|position)\b", re.IGNORECASE),
        re.compile(r"\bgrateful for any (?:role|job|position|opportunity)\b", re.IGNORECASE),
        re.compile(r"\bhire me\b", re.IGNORECASE),
        re.compile(r"\byou must hire\b", re.IGNORECASE),
    ]

    def validate(self, body: str) -> tuple[bool, List[str]]:
        violations: List[str] = []
        for pat in self._SUBORDINATE_PATTERNS:
            if pat.search(body):
                violations.append(f"Subordinate or deferential phrasing detected: '{pat.pattern}'")
        return len(violations) == 0, violations


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
    "EmDashValidator",
    "GroundingValidator",
    "MarkdownLinkValidator",
    "QuestionEndingValidator",
    "SpamTriggerValidator",
    "SubordinateToneValidator",
]
