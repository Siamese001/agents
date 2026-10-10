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
    except Exception:  # guardian: allow-silent-swallow -- fallback to default in-memory spam trigger lists
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


class ForbiddenClaimsValidator:
    """Hard assertion gate rejecting ungrounded compensation, unverifiable tenure claims, and policy-forbidden phrasing."""

    _COMPENSATION_PATTERNS: Final[List[re.Pattern[str]]] = [
        re.compile(r"\b(?:salary|compensation|base\s+pay|annual\s+pay|equity\s+grant|stock\s+options|signing\s+bonus|hourly\s+rate|expected\s+rate|pay\s+rate|target\s+comp|ote)\b", re.IGNORECASE),
        re.compile(r"\$\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*(?:k|m|million|thousand|/yr|/year|per\s+year|ote)?\b", re.IGNORECASE),
        re.compile(r"\b\d{2,3}\s*k\s*(?:ote|salary|base|comp)\b", re.IGNORECASE),
    ]

    _TENURE_PATTERNS: Final[List[re.Pattern[str]]] = [
        re.compile(r"\b(?:over\s+)?(\d+|ten|fifteen|twenty|twenty-five|thirty)\+?\s+years?\s+(?:of\s+)?(?:experience|leading|leadership|in|track\s+record)\b", re.IGNORECASE),
        re.compile(r"\b((?:two|three|four)\s+decades?)\s+(?:of\s+)?(?:experience|leadership|in)\b", re.IGNORECASE),
        re.compile(r"\b(\d+)\s*(?:\+|-)\s*year\s+(?:veteran|career|leader)\b", re.IGNORECASE),
    ]

    _POLICY_FORBIDDEN_PATTERNS: Final[List[re.Pattern[str]]] = [
        re.compile(r"\b(?:visa\s+sponsorship|require\s+sponsorship|sponsorship\s+required|h-?1b|opt\s+stem|green\s*card\s+sponsorship)\b", re.IGNORECASE),
        re.compile(r"\b(?:relocation\s+(?:package|assistance|allowance|bonus)|paid\s+relocation)\b", re.IGNORECASE),
        re.compile(r"\b(?:status\s+of\s+my\s+application|following\s+up\s+on\s+my\s+(?:job\s+)?application|submitted\s+my\s+resume|check\s+on\s+my\s+interview\s+status|pending\s+application)\b", re.IGNORECASE),
    ]

    def validate(
        self,
        body: str,
        verified_facts: Optional[List[Any]] = None,
    ) -> tuple[bool, List[str]]:
        violations: List[str] = []

        # 1. Compensation claims
        for pat in self._COMPENSATION_PATTERNS:
            for match in pat.finditer(body):
                matched_str = match.group(0)
                # If this dollar amount is part of a verified business fact/metric, do not flag
                if verified_facts:
                    v_match = False
                    for f in verified_facts:
                        stmt = str(getattr(f, "statement", "") or "")
                        met = str(getattr(f, "metric", "") or "")
                        if matched_str.lower() in stmt.lower() or matched_str.lower() in met.lower():
                            v_match = True
                            break
                    if v_match:
                        continue
                # Also check context around the match for business metrics (ARR, revenue, volume, etc.)
                start = max(0, match.start() - 30)
                end = min(len(body), match.end() + 30)
                surrounding = body[start:end].lower()
                if any(w in surrounding for w in ("arr", "revenue", "volume", "budget", "valuation", "pipeline", "spend", "deal", "portfolio", "gmv", "assets", "sales")):
                    continue
                violations.append(
                    f"Forbidden compensation claim detected: '{matched_str}'. Compensation discussions are strictly prohibited in cold outreach before first reply."
                )

        # 2. Policy-forbidden claims (visa, relocation, unearned interview status)
        for pat in self._POLICY_FORBIDDEN_PATTERNS:
            match = pat.search(body)
            if match:
                violations.append(
                    f"Policy-forbidden claim detected: '{match.group(0)}'."
                )

        # 3. Unverifiable tenure claims
        verified_text = ""
        if verified_facts:
            verified_text = " ".join(
                str(getattr(f, "statement", f)) + " " + str(getattr(f, "metric", ""))
                for f in verified_facts
            ).lower()

        for pat in self._TENURE_PATTERNS:
            match = pat.search(body)
            if match:
                claimed_tenure = match.group(0).lower()
                tenure_term = match.group(1).lower()
                if tenure_term not in verified_text:
                    violations.append(
                        f"Unverifiable tenure claim detected: '{claimed_tenure}'. Claimed duration '{tenure_term}' is not backed by candidate verified facts."
                    )

        return len(violations) == 0, violations


__all__ = [
    "ChannelLengthValidator",
    "EmDashValidator",
    "ForbiddenClaimsValidator",
    "GroundingValidator",
    "MarkdownLinkValidator",
    "QuestionEndingValidator",
    "SpamTriggerValidator",
    "SubordinateToneValidator",
]
