"""Shared cross-engine research handoff contracts and canonical brief matching utilities.

Consolidates common data structures (`EvidenceItem`), company/role token normalization,
stem matching, and SHA-256 digest verification shared across `resume_graph_engine`
(`apps_rg`) and `outreach_engine` (`apps_lic`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Sequence

_STOP_TOKENS = frozenset({"of", "the", "and", "for", "in", "at", "to"})


@dataclass(frozen=True)
class EvidenceItem:
    """Canonical provenance evidence item shared across research handoff bridges."""

    source_id: str
    label: str
    uri: str
    source_type: str
    field_ref: str
    confidence: float = 0.0


def normalize_company_role_tokens(
    company_name: str,
    job_title: str = "",
) -> tuple[str, str, list[str], list[str]]:
    """Return (company_norm, role_norm, company_tokens, role_tokens) for targeting brief resolution."""
    company_norm = re.sub(r"[^a-z0-9]+", "_", company_name.lower()).strip("_")
    role_norm = re.sub(r"[^a-z0-9]+", "_", job_title.lower()).strip("_")
    company_tokens = [
        tok
        for tok in re.findall(r"[a-z]+|\d+", company_name.lower())
        if len(tok) >= 3 and not tok.isdigit()
    ]
    role_tokens = [tok for tok in role_norm.split("_") if len(tok) > 3 and tok not in _STOP_TOKENS]
    return company_norm, role_norm, company_tokens, role_tokens


def matches_company_stem(
    stem: str,
    company_norm: str,
    company_tokens: Sequence[str],
) -> bool:
    """Return True if a candidate briefing filename stem matches the normalized company identity."""
    stem_low = stem.lower()
    if company_norm and company_norm in stem_low:
        return True
    return any(tok in stem_low or stem_low.startswith(tok) for tok in company_tokens)


def verify_handoff_digest(content: str | bytes, expected_sha256: str) -> bool:
    """Verify SHA-256 digest of a handoff brief or manifest payload."""
    if not expected_sha256:
        return False
    raw = content.encode("utf-8") if isinstance(content, str) else content
    actual = hashlib.sha256(raw).hexdigest()
    return actual == expected_sha256.strip().lower()
