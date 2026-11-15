"""Lexical, channel-length, question-ending, punctuation, and tone validators for apps_lic."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Final, List, Optional

from apps_lic.domain.models import ChannelType

LINKEDIN_CONNECTION_MAX_CHARS: Final[int] = 300
LINKEDIN_INMAIL_MAX_CHARS: Final[int] = 1900
EMAIL_MAX_CHARS: Final[int] = 1500
FOLLOW_UP_MAX_CHARS: Final[int] = 800

# Curated spam triggers fallback based on apps_lic/config/spam_trigger_phrases.py
_CRITICAL_SPAM_TRIGGERS: Final[List[re.Pattern[str]]] = [
    re.compile(p, re.IGNORECASE) for p in (
        r"\bact now\b", r"\burgent response needed\b", r"\blimited time opportunity\b",
        r"\bguaranteed interview\b", r"\bdon't miss out\b",
    )
]

_HIGH_SPAM_TRIGGERS: Final[List[re.Pattern[str]]] = [
    re.compile(p, re.IGNORECASE) for p in (
        r"\bonce in a lifetime\b", r"\bexclusive invitation\b",
        r"\bdouble your income\b", r"\bunbelievable offer\b",
    )
]

_GENERIC_OPENER_TRIGGERS: Final[List[re.Pattern[str]]] = [
    re.compile(p, re.IGNORECASE) for p in (
        r"\bI hope this email finds you well\b", r"\bI hope this message finds you well\b",
        r"\bI hope you are having a great week\b", r"\bI came across your profile and was impressed\b",
        r"\bAllow me to introduce myself\b",
    )
]

# Channel length ceilings
_CHANNEL_MAX_CHARS: Final[dict[ChannelType, int]] = {
    ChannelType.LINKEDIN_CONNECTION: LINKEDIN_CONNECTION_MAX_CHARS,
    ChannelType.LINKEDIN_INMAIL: LINKEDIN_INMAIL_MAX_CHARS,
    ChannelType.EMAIL: EMAIL_MAX_CHARS,
    ChannelType.FOLLOW_UP: FOLLOW_UP_MAX_CHARS,
}


def _load_canonical_spam_phrases() -> dict[str, list[re.Pattern[str]]]:
    """Load canonical spam triggers from config/spam_trigger_phrases.py without mutating sys.path."""
    try:
        config_file = Path(__file__).resolve().parents[4] / "config" / "spam_trigger_phrases.py"
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
    except (OSError, ValueError, KeyError, TypeError):
        pass

    return {
        "pushy_cta": _HIGH_SPAM_TRIGGERS + _CRITICAL_SPAM_TRIGGERS,
        "generic_opener": _GENERIC_OPENER_TRIGGERS,
    }


class SpamTriggerValidator:
    """Scans text for aggressive CTAs, false urgency, or generic cliches."""

    def __init__(self) -> None:
        self._categories = _load_canonical_spam_phrases()

    def validate(self, text: Optional[str]) -> tuple[bool, List[str], List[str]]:
        text_str = str(text or "")
        norm_text = re.sub(r"\s+", " ", text_str)
        violations: List[str] = []
        warnings: List[str] = []

        for pat in _CRITICAL_SPAM_TRIGGERS:
            if pat.search(text_str) or pat.search(norm_text):
                violations.append(f"Critical spam trigger matched: '{pat.pattern}'")

        for pat in _HIGH_SPAM_TRIGGERS:
            if pat.search(text_str) or pat.search(norm_text):
                violations.append(f"High-severity pushy CTA matched: '{pat.pattern}'")

        for pat in _GENERIC_OPENER_TRIGGERS:
            if pat.search(text_str) or pat.search(norm_text):
                warnings.append(f"Generic cliche opener matched: '{pat.pattern}'")

        pushy = self._categories.get("pushy_cta", [])
        for pat in pushy:
            if (pat.search(text_str) or pat.search(norm_text)) and not any(pat.pattern in v for v in violations):
                violations.append(f"Pushy sales CTA matched: '{pat.pattern}'")

        urgency = self._categories.get("false_urgency", [])
        for pat in urgency:
            if (pat.search(text_str) or pat.search(norm_text)) and not any(pat.pattern in v for v in violations):
                violations.append(f"False urgency phrase matched: '{pat.pattern}'")

        cliches = self._categories.get("corporate_cliche", [])
        for pat in cliches:
            if (pat.search(text_str) or pat.search(norm_text)) and not any(pat.pattern in w for w in warnings):
                warnings.append(f"Corporate cliche matched: '{pat.pattern}'")

        openers = self._categories.get("generic_opener", [])
        for pat in openers:
            if (pat.search(text_str) or pat.search(norm_text)) and not any(pat.pattern in w for w in warnings):
                warnings.append(f"Formulaic generic opener matched: '{pat.pattern}'")

        is_valid = len(violations) == 0
        return is_valid, violations, warnings


class ChannelLengthValidator:
    """Verifies message body does not exceed strict channel ceilings."""

    def validate(self, channel: ChannelType, body: Optional[str]) -> tuple[bool, Optional[str]]:
        body_str = str(body or "")
        ceiling = _CHANNEL_MAX_CHARS.get(channel, 2000)
        actual = len(body_str)
        if actual > ceiling:
            return False, f"Message length ({actual} chars) exceeds channel ceiling ({ceiling} chars) for {channel.value}."
        return True, None


class QuestionEndingValidator:
    """Verifies that the message concludes with a low-friction inquiry."""

    def validate(self, body: Optional[str]) -> tuple[bool, Optional[str]]:
        stripped = str(body or "").strip()
        if not stripped:
            return False, "Empty message body."

        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if lines[-1].endswith("?"):
            return True, None

        signature_tokens = (
            "linkedin.com", "github.com", "+1-", "+1 ", "@", "officer", "director", "partner", "vp",
            "chief", "lead", "architect", "engineer", "regards", "sincerely", "best,", "best regards",
            "--", "__", "tel:", "phone:", "email:",
        )
        for i, line in enumerate(lines):
            if line.endswith("?"):
                trailing = lines[i + 1:]
                if not trailing:
                    return True, None
                has_explicit_signoff = any(
                    any(tok in t.lower() for tok in ("regards", "best", "sincerely", "--", "—", "linkedin.com", "github.com", "+1", "@", "tel:", "phone:", "email:"))
                    for t in trailing
                )
                if not has_explicit_signoff:
                    continue
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

    def validate(self, body: Optional[str]) -> tuple[bool, Optional[str]]:
        body_str = str(body or "")
        if "—" in body_str or "\u2014" in body_str:
            return False, "Forbidden em dash detected; use standard punctuation or commas."
        return True, None


class MarkdownLinkValidator:
    """Verifies message body uses plain text links rather than markdown links."""

    _MD_LINK_PAT = re.compile(r"\[([^\]]+)\]\(\s*((?:https?://|www\.)[^\)\s]+)\s*\)", re.IGNORECASE)

    def validate(self, body: Optional[str]) -> tuple[bool, Optional[str]]:
        body_str = str(body or "")
        if self._MD_LINK_PAT.search(body_str):
            return False, "Forbidden markdown link syntax detected; use plain text URLs only."
        return True, None


class SubordinateToneValidator:
    """Detects deferential or desperate subordinate phrasing in executive outreach."""

    _SUBORDINATE_PATTERNS = [
        re.compile(p, re.IGNORECASE) for p in (
            r"\bwould love to learn more\b", r"\bthink I(?:'d| would) be a (?:great|perfect) fit\b",
            r"\bhoping for an? (?:opportunity|interview|chance)\b", r"\bgive me a (?:chance|shot)\b",
            r"\bplease consider my (?:application|resume|c\.?v\.?)\b", r"\bseeking a (?:role|job|position)\b",
            r"\bgrateful for any (?:role|job|position|opportunity)\b", r"\bhire me\b", r"\byou must hire\b",
        )
    ]

    def validate(self, body: Optional[str]) -> tuple[bool, List[str]]:
        body_str = str(body or "")
        norm_body = re.sub(r"\s+", " ", body_str)
        violations: List[str] = []
        for pat in self._SUBORDINATE_PATTERNS:
            if pat.search(body_str) or pat.search(norm_body):
                violations.append(f"Subordinate or deferential phrasing detected: '{pat.pattern}'")
        return len(violations) == 0, violations


__all__ = [
    "ChannelLengthValidator",
    "EMAIL_MAX_CHARS",
    "EmDashValidator",
    "FOLLOW_UP_MAX_CHARS",
    "LINKEDIN_CONNECTION_MAX_CHARS",
    "LINKEDIN_INMAIL_MAX_CHARS",
    "MarkdownLinkValidator",
    "QuestionEndingValidator",
    "SpamTriggerValidator",
    "SubordinateToneValidator",
    "_CHANNEL_MAX_CHARS",
    "_CRITICAL_SPAM_TRIGGERS",
    "_GENERIC_OPENER_TRIGGERS",
    "_HIGH_SPAM_TRIGGERS",
    "_load_canonical_spam_phrases",
]
