"""Narrative claim-ledger tokenization, binding patterns, and targeting strip helpers."""
from __future__ import annotations

import re
from typing import Any, Mapping

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    NARRATIVE_LEDGER_STOPWORDS,
    narrative_ledger_tokens,
)
from .lane_config import (
    _bullet_sentence,
    _compact_text,
    _facts_from_plan,
    _normalize_source_ids,
    _sentence,
)

_NARRATIVE_LEDGER_STOPWORDS = NARRATIVE_LEDGER_STOPWORDS
_narrative_ledger_tokens = narrative_ledger_tokens

def _valid_source_ids_without_fallback(raw: Any, allowed: list[str]) -> list[str]:
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    out: list[str] = []
    for value in raw if isinstance(raw, list) else ([raw] if raw else []):
        fid = str(value or "").strip()
        if fid and fid in allowed_set and fid not in out:
            out.append(fid)
    return out


def _parsed_claim_ledger_source_ids_for_narrative(
    *,
    parsed: dict[str, Any],
    narrative: str,
    allowed: list[str],
) -> list[str]:
    """Preserve valid parsed ledger IDs whose claim text appears in the narrative."""
    rows = parsed.get("claim_ledger") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return []
    narrative_text = str(narrative or "")
    narrative_l = narrative_text.lower()
    narrative_tokens = _narrative_ledger_tokens(narrative_text)
    source_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        claim_text = str(row.get("claim_text") or row.get("claim") or "").strip()
        claim_l = claim_text.lower()
        if claim_text and claim_l not in narrative_l:
            claim_tokens = _narrative_ledger_tokens(claim_text)
            required_overlap = 2 if len(claim_tokens) <= 5 else 3
            if len(narrative_tokens & claim_tokens) < required_overlap:
                continue
        for fid in _valid_source_ids_without_fallback(row.get("source_fact_ids"), allowed):
            if fid not in source_ids:
                source_ids.append(fid)
    return source_ids


_NARRATIVE_SOURCE_BINDING_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "reb_ey_regulatory_analytics_modernization": (
        re.compile(r"\bregulatory\s+analytics\b", re.IGNORECASE),
        re.compile(r"\blineage[-\s]+backed\s+regulatory\b", re.IGNORECASE),
        re.compile(r"\bpredictive\s+risk\s+analytics\b", re.IGNORECASE),
    ),
    "reb_ey_capital_optimization_solvency": (
        re.compile(r"\bcapital\b", re.IGNORECASE),
        re.compile(r"\bsolvency\b", re.IGNORECASE),
        re.compile(r"\bhedg(?:e|ing)\b", re.IGNORECASE),
        re.compile(r"\bliability\s+greeks\b", re.IGNORECASE),
    ),
    "reb_ey_ccar_capital_liquidity_stress_testing": (
        re.compile(r"\bccar\b", re.IGNORECASE),
        re.compile(r"\bstress\s+testing\b", re.IGNORECASE),
        re.compile(r"\bmodel[-\s]?risk\b", re.IGNORECASE),
        re.compile(r"\bgovernance\s+evidence\b", re.IGNORECASE),
    ),
    "reb_ey_insurance_core_modernization": (
        re.compile(r"\binsurance\s+operations\b", re.IGNORECASE),
        re.compile(r"\bpolicy\s+(?:and\s+claims\s+)?operations\b", re.IGNORECASE),
        re.compile(r"\bclaims\s+(?:operations|workflow)\b", re.IGNORECASE),
        re.compile(r"\bpolicy\s+administration\b", re.IGNORECASE),
        re.compile(r"\bbilling/rating/underwriting\b", re.IGNORECASE),
        re.compile(r"\bBI[-\s]+ready\s+data\s+outputs\b", re.IGNORECASE),
    ),
    "reb_ey_erm_risk_governance": (
        re.compile(r"\bauditable\b", re.IGNORECASE),
        re.compile(r"\btraceable\s+controls?\b", re.IGNORECASE),
        re.compile(r"\brisk[-\s]+data\b", re.IGNORECASE),
        re.compile(r"\bthree[-\s]+lines(?:[-\s]+of[-\s]+defense)?\b", re.IGNORECASE),
        re.compile(r"\brisk\s+metrics?\b", re.IGNORECASE),
    ),
    "reb_insurtech_founder_led_gtm_revenue": (
        re.compile(r"\bgtm\b", re.IGNORECASE),
        re.compile(r"\bgo[-\s]?to[-\s]?market\b", re.IGNORECASE),
    ),
    "reb_insurtech_lean_delivery_operating_model": (
        re.compile(r"\bcontrol\s+discipline\b", re.IGNORECASE),
        re.compile(r"\baudit/control\s+discipline\b", re.IGNORECASE),
        re.compile(r"\blean\s+execution\b", re.IGNORECASE),
        re.compile(r"\blean\s+(?:delivery|operating)\s+model\b", re.IGNORECASE),
    ),
    "reb_insurtech_aws_cloud_economics": (
        re.compile(r"\beconomics(?:[-\s]+driven)?\b", re.IGNORECASE),
        re.compile(r"\bcost\s+controls?\b", re.IGNORECASE),
    ),
    "reb_insurtech_aws_migration_execution": (
        re.compile(r"\blegacy\s+platforms?\b", re.IGNORECASE),
        re.compile(r"\benterprise\s+workloads?\b", re.IGNORECASE),
        re.compile(r"\bcomplex\s+workloads?\b", re.IGNORECASE),
        re.compile(r"\bworkloads?\s+deployable\b", re.IGNORECASE),
        re.compile(r"\bproduction\b", re.IGNORECASE),
    ),
    "reb_insurtech_aws_shared_responsibility_operating_model": (
        re.compile(r"\bcontrol\s+discipline\b", re.IGNORECASE),
        re.compile(r"\bsafety[-\s]first\s+control\b", re.IGNORECASE),
        re.compile(r"\binsurer-owned\s+controls?\b", re.IGNORECASE),
    ),
    "reb_insurtech_regulated_aws_control_implementation": (
        re.compile(r"\bregulated\s+AWS\b", re.IGNORECASE),
        re.compile(r"\bcontrol\s+discipline\b", re.IGNORECASE),
        re.compile(r"\bcontrol\s+design\b", re.IGNORECASE),
        re.compile(r"\bsafety[-\s]first\s+control\b", re.IGNORECASE),
    ),
    "reb_insurtech_founder_led_market_creation": (
        re.compile(r"\bfounder[-\s]led\b", re.IGNORECASE),
        re.compile(r"\bmarket\s+creation\b", re.IGNORECASE),
        re.compile(r"\bcarrier\s+traction\b", re.IGNORECASE),
    ),
    "reb_insurtech_public_vs_private_cloud_strategy": (
        re.compile(r"\bpublic[-\s]cloud\b", re.IGNORECASE),
        re.compile(r"\bprivate\s+on[-\s]?prem\b", re.IGNORECASE),
        re.compile(r"\bcloud\s+fit\b", re.IGNORECASE),
    ),
    "reb_insurtech_insurance_regulatory_cloud_adoption_standards": (
        re.compile(r"\bregulatory\s+cloud\b", re.IGNORECASE),
        re.compile(r"\binsurance\s+regulatory\b", re.IGNORECASE),
        re.compile(r"\bcompliance\s+artifacts?\b", re.IGNORECASE),
    ),
    "reb_insurtech_aws_guidewire_core_modernization": (
        re.compile(r"\bguidewire\b", re.IGNORECASE),
        re.compile(r"\bpolicy\s+administration\b", re.IGNORECASE),
        re.compile(r"\bcore\s+insurance\b", re.IGNORECASE),
    ),
    "reb_insurtech_insurance_data_bi_decisioning": (
        re.compile(r"\breporting\s+latency\b", re.IGNORECASE),
        re.compile(r"\bunderwriting\s+analytics\b", re.IGNORECASE),
        re.compile(r"\bpricing\s+decisions?\b", re.IGNORECASE),
    ),
    "reb_insurtech_resilient_core_operations": (
        re.compile(r"\bhigh\s+availability\b", re.IGNORECASE),
        re.compile(r"\brto/rpo\b", re.IGNORECASE),
        re.compile(r"\bincident\s+runbooks?\b", re.IGNORECASE),
    ),
}


def _narrative_source_ids_for_claim(
    *,
    narrative: str,
    raw_source_ids: Any,
    allowed: list[str],
    selected_fact_plan: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Bind narrative material phrases to selected role-episode bundle facts."""
    source_ids = _normalize_source_ids(raw_source_ids, allowed, 0)
    fact_ids = {
        str(row.get("fact_id") or row.get("role_episode_bundle_id") or "").strip()
        for row in _facts_from_plan(selected_fact_plan)
    }
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    added: list[str] = []
    for fid in allowed:
        if fid in source_ids or fid not in fact_ids:
            continue
        patterns = _NARRATIVE_SOURCE_BINDING_PATTERNS.get(fid, ())
        if not patterns or not any(pattern.search(narrative) for pattern in patterns):
            continue
        if fid not in allowed_set:
            continue
        source_ids.append(fid)
        added.append(fid)
    return source_ids, added


_TARGETING_ONLY_TAIL_REPAIRS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r",?\s+(?:mirroring|positioning|aligning|framing|mapping|translating)\b"
        r"[^.?!]*(?:frontier\s+AI|partner-led\s+deployments?|target\s+role|"
        r"target\s+company|Anthropic|applied\s+AI\s+architecture|ecosystem\s+revenue)"
        r"[^.?!]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+(?:required|needed)\s+to\s+enable\s+partner-led\s+deployments?"
        r"\s+of\s+frontier\s+AI(?:\s+at\s+scale)?",
        re.IGNORECASE,
    ),
    re.compile(
        r",?\s+for\s+(?:Anthropic|the\s+target\s+role|the\s+target\s+company|"
        r"target\s+role|target\s+company)\b[^.?!]*",
        re.IGNORECASE,
    ),
)

_TARGETING_ONLY_EXPERIENCE_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("target_company_name", re.compile(r"\b(?:for|at|to)\s+Anthropic\b", re.IGNORECASE)),
    ("frontier_ai_as_experience", re.compile(r"\bfrontier\s+AI\b", re.IGNORECASE)),
    (
        "partner_led_deployment_as_experience",
        re.compile(r"\bpartner-led\s+deployments?\b", re.IGNORECASE),
    ),
    ("target_role_as_experience", re.compile(r"\btarget\s+(?:role|company)\b", re.IGNORECASE)),
)


def _targeting_only_experience_hits(text: str, *, target_company: str = "") -> list[str]:
    s = str(text or "")
    hits = [
        label
        for label, pattern in _TARGETING_ONLY_EXPERIENCE_MARKERS
        if pattern.search(s)
    ]
    tc = str(target_company or "").strip()
    if tc and len(tc) >= 3 and "target_company_name" not in hits:
        tc_head = tc.split()[0].strip(",.")
        for cand in {tc, tc_head}:
            if len(cand) >= 3 and re.search(rf"\b(?:for|at|to)\s+{re.escape(cand)}\b", s, re.IGNORECASE):
                hits.append("target_company_name")
                break
    return hits


def _strip_targeting_only_experience_claims(
    text: str,
    *,
    target_company: str = "",
    allow_prose_mutation: bool = False,
) -> tuple[str, list[str]]:
    """Remove JD/briefing-only tail claims when allow_prose_mutation=True; detect-only by default (role_narrative_v2)."""
    original = str(text or "")
    if not allow_prose_mutation:
        return original, _targeting_only_experience_hits(original, target_company=target_company)
    cleaned = original
    for pattern in _TARGETING_ONLY_TAIL_REPAIRS:
        cleaned = pattern.sub("", cleaned)
    if re.search(r"\bfrontier\s+AI\b", cleaned, re.IGNORECASE):
        replacement = "enterprise AI" if re.search(r"next-gen", cleaned, re.IGNORECASE) else "next-generation AI"
        cleaned = re.sub(r"\bfrontier\s+AI\b", replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bpartner-led\s+deployments\b", "client deployments", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bpartner-led\s+deployment\b", "client deployment", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned).strip(" ,;:")
    if cleaned != original and cleaned:
        cleaned = _bullet_sentence(cleaned)
    return (cleaned or original), _targeting_only_experience_hits(cleaned or original, target_company=target_company)


def _narrative_from_parsed(parsed: dict[str, Any], *, allow_prose_mutation: bool = False) -> str:
    text = parsed.get("narrative_sentence") if isinstance(parsed, dict) else None
    cleaned, _hits = _strip_targeting_only_experience_claims(
        str(text or ""),
        allow_prose_mutation=allow_prose_mutation,
    )
    return _sentence(cleaned)

