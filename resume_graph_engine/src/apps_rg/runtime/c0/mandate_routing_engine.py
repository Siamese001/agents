"""Unified Mandate Routing Engine (SSOT) for senior leadership resume graph traversal.

Eliminates the quadruple split-brain routing across track_weighted_graph_expansion,
graph_role_episode_selector, jd_fit_bundle_selection, and c0_perf_sync_helpers.

Purely domain-signal and role-level driven (zero company-name overfitting).
All JD/briefing texts act strictly as targeting inputs, never as proof authority.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from apps_rg.repository_layout import repository_root, resolve_apps_rg_path

ROOT = repository_root(Path(__file__))

TRACK_IDS: tuple[str, ...] = (
    "track_actuarial_risk_derivatives",
    "track_data_tech_cloud_ml",
    "track_genai_agentic",
)

ALL_EMPLOYER_LANES: tuple[str, ...] = (
    "slalom",
    "unify",
    "ibm",
    "insurtech",
    "ey",
    "early_career",
)

# Complete 20-family taxonomy -> canonical projection role SSOT (zero unmapped IDs).
CANONICAL_TAXONOMY_TO_PROJECTION: dict[str, str] = {
    "ENGINEERING_PLATFORM": "SVP_ENGINEERING_AI_PLATFORM",
    "AI_SOLUTIONS_ARCHITECTURE": "FIELD_CTO",
    "FIELD_SOLUTIONS_ARCHITECTURE": "FIELD_CTO",
    "PARTNERSHIPS_GTM": "ANTHROPIC_PARTNERSHIPS_APPLIED_AI",
    "SALES_STRATEGIC_ACCOUNTS": "CHIEF_REVENUE_OFFICER_COMPOSITE",
    "REVENUE_OPERATIONS": "CHIEF_REVENUE_OFFICER_COMPOSITE",
    "CUSTOMER_SUCCESS": "CHIEF_REVENUE_OFFICER_COMPOSITE",
    "PRODUCT_TECHNICAL_STRATEGY": "SVP_ENGINEERING_AI_PLATFORM",
    "AI_GOVERNANCE_RISK": "GOVERNANCE_RISK",
    "DATA_ANALYTICS_LEADERSHIP": "DATA_ANALYTICS_LEADERSHIP",
    "STRATEGIC_FINANCE": "STRATEGIC_FINANCE",
    "QUANT_TRADING_HPC": "QUANT_TRADING",
    "CONSULTING_DELIVERY_LEADERSHIP": "CONSULTING_DELIVERY_LEADERSHIP",
    "EXECUTIVE_LEADERSHIP": "CHIEF_AI_OFFICER",
    "INSURANCE_CARRIER_TRANSFORMATION": "INSURANCE_CARRIER_TRANSFORMATION",
    "INSURER_IT_AI_ENABLEMENT": "INSURER_IT_AI_ENABLEMENT",
    "INSURANCE_BROKERAGE_IT_INNOVATION": "INSURANCE_BROKERAGE_IT_INNOVATION",
    "BANKING_PLATFORM_AI": "BANKING_PLATFORM_AI",
    "REGULATED_AI_GOVERNANCE": "REGULATED_AI_GOVERNANCE",
    "PARTNER_APPLIED_AI_ARCHITECTURE": "PARTNER_APPLIED_AI_ARCHITECTURE",
    "HYPERSCALER_MARKETPLACE_GTM": "HYPERSCALER_MARKETPLACE_GTM",
}

PROJECTION_TRACK_WEIGHTS: dict[str, dict[str, float]] = {
    "SVP_ENGINEERING_AI_PLATFORM": {
        "track_actuarial_risk_derivatives": 0.12,
        "track_data_tech_cloud_ml": 0.28,
        "track_genai_agentic": 0.60,
    },
    "CHIEF_AI_OFFICER": {
        "track_actuarial_risk_derivatives": 0.18,
        "track_data_tech_cloud_ml": 0.27,
        "track_genai_agentic": 0.55,
    },
    "FIELD_CTO": {
        "track_actuarial_risk_derivatives": 0.10,
        "track_data_tech_cloud_ml": 0.42,
        "track_genai_agentic": 0.48,
    },
    "GOVERNANCE_RISK": {
        "track_actuarial_risk_derivatives": 0.40,
        "track_data_tech_cloud_ml": 0.25,
        "track_genai_agentic": 0.35,
    },
    "QUANT_TRADING": {
        "track_actuarial_risk_derivatives": 0.55,
        "track_data_tech_cloud_ml": 0.35,
        "track_genai_agentic": 0.10,
    },
    "ANTHROPIC_PARTNERSHIPS_APPLIED_AI": {
        "track_actuarial_risk_derivatives": 0.10,
        "track_data_tech_cloud_ml": 0.55,
        "track_genai_agentic": 0.35,
    },
    "INSURANCE_CARRIER_TRANSFORMATION": {
        "track_actuarial_risk_derivatives": 0.35,
        "track_data_tech_cloud_ml": 0.25,
        "track_genai_agentic": 0.40,
    },
    "INSURER_IT_AI_ENABLEMENT": {
        "track_actuarial_risk_derivatives": 0.25,
        "track_data_tech_cloud_ml": 0.40,
        "track_genai_agentic": 0.35,
    },
    "INSURANCE_BROKERAGE_IT_INNOVATION": {
        "track_actuarial_risk_derivatives": 0.18,
        "track_data_tech_cloud_ml": 0.47,
        "track_genai_agentic": 0.35,
    },
    "BANKING_PLATFORM_AI": {
        "track_actuarial_risk_derivatives": 0.35,
        "track_data_tech_cloud_ml": 0.25,
        "track_genai_agentic": 0.40,
    },
    "REGULATED_AI_GOVERNANCE": {
        "track_actuarial_risk_derivatives": 0.40,
        "track_data_tech_cloud_ml": 0.25,
        "track_genai_agentic": 0.35,
    },
    "PARTNER_APPLIED_AI_ARCHITECTURE": {
        "track_actuarial_risk_derivatives": 0.10,
        "track_data_tech_cloud_ml": 0.55,
        "track_genai_agentic": 0.35,
    },
    "HYPERSCALER_MARKETPLACE_GTM": {
        "track_actuarial_risk_derivatives": 0.10,
        "track_data_tech_cloud_ml": 0.60,
        "track_genai_agentic": 0.30,
    },
    "CONSULTING_DELIVERY_LEADERSHIP": {
        "track_actuarial_risk_derivatives": 0.18,
        "track_data_tech_cloud_ml": 0.47,
        "track_genai_agentic": 0.35,
    },
    "DATA_ANALYTICS_LEADERSHIP": {
        "track_actuarial_risk_derivatives": 0.28,
        "track_data_tech_cloud_ml": 0.37,
        "track_genai_agentic": 0.35,
    },
    "STRATEGIC_FINANCE": {
        "track_actuarial_risk_derivatives": 0.35,
        "track_data_tech_cloud_ml": 0.40,
        "track_genai_agentic": 0.25,
    },
    "HEALTHCARE_PAYER_DATA_AI": {
        "track_actuarial_risk_derivatives": 0.35,
        "track_data_tech_cloud_ml": 0.30,
        "track_genai_agentic": 0.35,
    },
    "PE_OPERATING_PARTNER_TRANSFORMATION": {
        "track_actuarial_risk_derivatives": 0.20,
        "track_data_tech_cloud_ml": 0.45,
        "track_genai_agentic": 0.35,
    },
    "AI_FINANCIAL_SERVICES": {
        "track_actuarial_risk_derivatives": 0.35,
        "track_data_tech_cloud_ml": 0.28,
        "track_genai_agentic": 0.37,
    },
    "CHIEF_REVENUE_OFFICER_COMPOSITE": {
        "track_actuarial_risk_derivatives": 0.10,
        "track_data_tech_cloud_ml": 0.60,
        "track_genai_agentic": 0.30,
    },
    "THREE_PHASE_GENERALIST": {
        "track_actuarial_risk_derivatives": 0.27,
        "track_data_tech_cloud_ml": 0.38,
        "track_genai_agentic": 0.35,
    },
}

# Employer weights across ALL 6 career lanes (slalom, unify, ibm, insurtech, ey, early_career).
SELECTOR_EMPLOYER_WEIGHTS: dict[str, dict[str, float]] = {
    "insurance_agentic_ai": {
        "slalom": 1.00,
        "unify": 0.95,
        "insurtech": 0.95,
        "ey": 0.80,
        "early_career": 0.85,
        "ibm": 0.65,
    },
    "insurance_it_strategy": {
        "insurtech": 1.00,
        "unify": 0.85,
        "ey": 0.80,
        "early_career": 0.80,
        "slalom": 0.75,
        "ibm": 0.65,
    },
    "banking_model_risk_ai": {
        "slalom": 1.00,
        "unify": 0.95,
        "ey": 0.90,
        "early_career": 0.85,
        "ibm": 0.75,
        "insurtech": 0.55,
    },
    "healthcare_payer_data_ai": {
        "slalom": 0.95,
        "unify": 0.95,
        "early_career": 0.90,
        "ey": 0.75,
        "insurtech": 0.70,
        "ibm": 0.70,
    },
    "executive_agentic_transformation": {
        "slalom": 1.00,
        "unify": 1.00,
        "ibm": 0.95,
        "ey": 0.90,
        "insurtech": 0.65,
        "early_career": 0.55,
    },
    "ai_partnerships_gtm": {
        "slalom": 1.00,
        "unify": 1.00,
        "ibm": 0.95,
        "insurtech": 0.45,
        "ey": 0.35,
        "early_career": 0.30,
    },
    "svp_agentic_engineering": {
        "slalom": 1.00,
        "unify": 0.95,
        "ibm": 0.75,
        "insurtech": 0.50,
        "ey": 0.35,
        "early_career": 0.35,
    },
    "quant_risk_hpc": {
        "early_career": 1.00,
        "ey": 0.90,
        "unify": 0.85,
        "slalom": 0.80,
        "ibm": 0.70,
        "insurtech": 0.65,
    },
    "balanced_enterprise_ai": {
        "slalom": 0.95,
        "unify": 0.90,
        "ibm": 0.80,
        "insurtech": 0.65,
        "ey": 0.60,
        "early_career": 0.55,
    },
}

# Dynamic two-page per-employer bullet budgets (total 18-20 bullets fitting 2 pages cleanly).
SLOT_BUDGET_BY_PROFILE: dict[str, dict[str, int]] = {
    "insurance_agentic_ai": {
        "slalom_bullets": 4,
        "unify_bullets": 5,
        "ibm_bullets": 3,
        "insurtech_bullets": 3,
        "ey_bullets": 2,
        "early_career_bullets": 2,
    },
    "insurance_it_strategy": {
        "slalom_bullets": 3,
        "unify_bullets": 5,
        "ibm_bullets": 3,
        "insurtech_bullets": 3,
        "ey_bullets": 2,
        "early_career_bullets": 2,
    },
    "banking_model_risk_ai": {
        "slalom_bullets": 4,
        "unify_bullets": 5,
        "ibm_bullets": 3,
        "insurtech_bullets": 2,
        "ey_bullets": 3,
        "early_career_bullets": 2,
    },
    "healthcare_payer_data_ai": {
        "slalom_bullets": 4,
        "unify_bullets": 5,
        "ibm_bullets": 3,
        "insurtech_bullets": 2,
        "ey_bullets": 2,
        "early_career_bullets": 3,
    },
    "executive_agentic_transformation": {
        "slalom_bullets": 4,
        "unify_bullets": 5,
        "ibm_bullets": 4,
        "insurtech_bullets": 2,
        "ey_bullets": 3,
        "early_career_bullets": 1,
    },
    "ai_partnerships_gtm": {
        "slalom_bullets": 4,
        "unify_bullets": 6,
        "ibm_bullets": 5,
        "insurtech_bullets": 2,
        "ey_bullets": 1,
        "early_career_bullets": 1,
    },
    "svp_agentic_engineering": {
        "slalom_bullets": 4,
        "unify_bullets": 6,
        "ibm_bullets": 5,
        "insurtech_bullets": 2,
        "ey_bullets": 1,
        "early_career_bullets": 1,
    },
    "quant_risk_hpc": {
        "slalom_bullets": 3,
        "unify_bullets": 4,
        "ibm_bullets": 3,
        "insurtech_bullets": 2,
        "ey_bullets": 3,
        "early_career_bullets": 3,
    },
    "balanced_enterprise_ai": {
        "slalom_bullets": 4,
        "unify_bullets": 5,
        "ibm_bullets": 4,
        "insurtech_bullets": 2,
        "ey_bullets": 2,
        "early_career_bullets": 1,
    },
}

_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _compile_word_pattern(term: str) -> re.Pattern[str]:
    cached = _PATTERN_CACHE.get(term)
    if cached is not None:
        return cached
    escaped = re.escape(term.strip().lower()).replace(r"\ ", r"[\s\-/]+")
    pat = re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)
    _PATTERN_CACHE[term] = pat
    return pat


def has_word_signal(text: str, term: str) -> bool:
    """Match a term using strict alphanumeric word boundaries (blocks 'ai' inside 'claims')."""
    if not text or not term:
        return False
    return bool(_compile_word_pattern(term).search(text))


def count_word_signals(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if has_word_signal(text, term))


def _normalize_track_weights(
    weights: Mapping[str, float],
    *,
    enforce_three_era_floor: bool = True,
) -> dict[str, float]:
    floor = 0.08 if enforce_three_era_floor else 0.0
    clipped = {k: max(floor, float(weights.get(k, 0.0))) for k in TRACK_IDS}
    total = sum(clipped.values())
    if total <= 0:
        return dict(PROJECTION_TRACK_WEIGHTS["SVP_ENGINEERING_AI_PLATFORM"])
    return {k: round(v / total, 4) for k, v in clipped.items()}


@dataclass(frozen=True)
class MandateRouteDecision:
    """Single SSOT routing output consumed by expansion, selector, allocator, and synthesis."""

    canonical_projection_role: str
    taxonomy_role_family: str
    selector_profile: str
    track_weights: dict[str, float]
    employer_weights: dict[str, float]
    slot_budget_profile: dict[str, int]
    credential_elevation_ids: tuple[str, ...]
    fde_context: bool
    requires_commercial_pairing: bool
    detected_domain_signals: tuple[str, ...] = field(default_factory=tuple)
    mandate_rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_projection_role": self.canonical_projection_role,
            "taxonomy_role_family": self.taxonomy_role_family,
            "selector_profile": self.selector_profile,
            "track_weights": dict(self.track_weights),
            "employer_weights": dict(self.employer_weights),
            "slot_budget_profile": dict(self.slot_budget_profile),
            "credential_elevation_ids": list(self.credential_elevation_ids),
            "fde_context": self.fde_context,
            "requires_commercial_pairing": self.requires_commercial_pairing,
            "detected_domain_signals": list(self.detected_domain_signals),
            "mandate_rationale": self.mandate_rationale,
        }


_INSURANCE_SIGNALS: tuple[str, ...] = (
    "insurance",
    "insurer",
    "insurtech",
    "carrier",
    "underwriting",
    "claims",
    "policy administration",
    "guidewire",
    "actuarial",
    "actuary",
    "fsa",
    "annuity",
    "life insurance",
    "reserving",
    "solvency ii",
    "ifrs 17",
    "brokerage",
    "policyholder",
)

_BANKING_MODEL_RISK_SIGNALS: tuple[str, ...] = (
    "banking",
    "global bank",
    "institutional bank",
    "capital markets",
    "sr 11-7",
    "sr 11 7",
    "bcbs 239",
    "ccar",
    "basel",
    "model risk",
    "mrm",
    "stress testing",
    "finra",
    "occ",
    "federal reserve",
    "regulatory reporting",
)

_HEALTHCARE_PAYER_SIGNALS: tuple[str, ...] = (
    "healthcare",
    "health plan",
    "payer",
    "health insurer",
    "medical loss ratio",
    "mlr",
    "hipaa",
    "clinical",
    "biostatistics",
    "provider network",
    "medicare",
    "medicaid",
    "population health",
    "value-based care",
    "heor",
)

_PE_TRANSFORMATION_SIGNALS: tuple[str, ...] = (
    "private equity",
    "operating partner",
    "portfolio company",
    "portfolio companies",
    "ebitda",
    "value creation",
    "due diligence",
    "m&a",
    "management consulting",
    "operating model redesign",
    "c-suite advisory",
    "board-level",
    "steering committee",
    "agentic transformation",
)

_PARTNER_GTM_SIGNALS: tuple[str, ...] = (
    "partnerships",
    "partner ecosystem",
    "channel partner",
    "partner-led",
    "partner engineering",
    "applied ai partnerships",
    "hyperscaler",
    "co-sell",
    "cosell",
    "joint gtm",
    "go-to-market",
    "gtm",
    "systems integrator",
    "gsi",
    "isv",
    "marketplace",
    "alliances",
)

_QUANT_HPC_SIGNALS: tuple[str, ...] = (
    "quantitative",
    "quant",
    "derivatives",
    "greeks",
    "exotic options",
    "stochastic",
    "monte carlo",
    "hpc",
    "high-performance computing",
    "trading",
    "hedging",
    "economic capital",
)

_AGENTIC_PLATFORM_SIGNALS: tuple[str, ...] = (
    "agentic",
    "multi-agent",
    "graphrag",
    "llm",
    "ai platform",
    "control plane",
    "orchestration",
    "cto",
    "chief technology officer",
    "svp engineering",
    "vp engineering",
    "lead engineer",
    "distributed systems",
    "microservices",
    "platform engineering",
    "cloud platform",
)

_FDE_EXPLICIT_SIGNALS: tuple[str, ...] = (
    "forward deployed",
    "forward-deployed",
    "forward deployment",
    "deployed engineering",
)

_EXECUTIVE_COMMERCIAL_SIGNALS: tuple[str, ...] = (
    "cto",
    "chief",
    "svp",
    "evp",
    "vp",
    "head of",
    "partner",
    "managing director",
    "director",
    "lead engineer",
    "p&l",
    "revenue",
    "margin",
    "commercial",
    "board",
)


def _read_if_file_path(value: str) -> str:
    text = str(value or "")
    if text and ("\n" not in text) and len(text) < 500:
        try:
            cand = Path(text)
            if cand.is_file():
                return cand.read_text(encoding="utf-8")
        except (OSError, ValueError):
            pass
    return text


def resolve_mandate_route(
    *,
    target_role: str = "",
    jd_text: str = "",
    briefing_text: str = "",
    taxonomy: Mapping[str, Any] | None = None,
) -> MandateRouteDecision:
    """Deterministically resolve unified mandate routing across all layers."""
    jd_clean = _read_if_file_path(jd_text)
    brief_clean = _read_if_file_path(briefing_text)
    role_clean = str(target_role or "").strip()
    blob = f"{role_clean}\n{jd_clean}\n{brief_clean}"

    ins_hits = count_word_signals(blob, _INSURANCE_SIGNALS)
    bank_hits = count_word_signals(blob, _BANKING_MODEL_RISK_SIGNALS)
    health_hits = count_word_signals(blob, _HEALTHCARE_PAYER_SIGNALS)
    pe_hits = count_word_signals(blob, _PE_TRANSFORMATION_SIGNALS)
    partner_hits = count_word_signals(blob, _PARTNER_GTM_SIGNALS)
    quant_hits = count_word_signals(blob, _QUANT_HPC_SIGNALS)
    agentic_hits = count_word_signals(blob, _AGENTIC_PLATFORM_SIGNALS)

    role_has_partner = any(
        has_word_signal(role_clean, tok)
        for tok in ("partner", "partnerships", "alliance", "alliances", "gtm", "co-sell", "cosell", "cro", "revenue")
    )
    role_has_pe_partner = has_word_signal(role_clean, "operating partner") or (
        has_word_signal(role_clean, "partner") and pe_hits >= 2
    )
    role_has_health = any(
        has_word_signal(role_clean, tok)
        for tok in ("healthcare", "health", "payer", "clinical", "biostatistics")
    )
    role_has_cdao = any(
        has_word_signal(role_clean, tok)
        for tok in ("cdao", "chief data", "data & ai", "data and ai", "analytics")
    )
    role_has_ins = any(
        has_word_signal(role_clean, tok)
        for tok in ("insurance", "insurer", "insurtech", "carrier", "actuarial", "underwriting", "brokerage")
    )
    role_has_bank_risk = any(
        has_word_signal(role_clean, tok)
        for tok in ("model risk", "mrm", "chief ai", "risk officer", "banking", "governance")
    )
    role_has_tech_exec = any(
        has_word_signal(role_clean, tok)
        for tok in ("cto", "chief technology", "lead engineer", "svp engineering", "vp engineering", "ai", "agentic")
    )

    # FDE context strictly requires explicit forward-deployed signals (NEVER SR 11-7 / model risk!).
    fde_context = count_word_signals(blob, _FDE_EXPLICIT_SIGNALS) > 0 and not role_has_partner and not role_has_pe_partner

    # Commercial outcomes pairing is ON for all executive / engineering leadership roles.
    requires_commercial_pairing = (
        count_word_signals(role_clean, _EXECUTIVE_COMMERCIAL_SIGNALS) > 0
        or count_word_signals(blob, _EXECUTIVE_COMMERCIAL_SIGNALS) >= 2
    )

    detected: list[str] = []
    if ins_hits:
        detected.append(f"insurance:{ins_hits}")
    if bank_hits:
        detected.append(f"banking_mrm:{bank_hits}")
    if health_hits:
        detected.append(f"healthcare_payer:{health_hits}")
    if pe_hits:
        detected.append(f"pe_transformation:{pe_hits}")
    if partner_hits:
        detected.append(f"partnerships_gtm:{partner_hits}")
    if quant_hits:
        detected.append(f"quant_hpc:{quant_hits}")
    if agentic_hits:
        detected.append(f"agentic_platform:{agentic_hits}")

    # Determine primary domain archetype cleanly without brittle single-word traps.
    single_track_quant_only = (
        quant_hits >= 3
        and agentic_hits == 0
        and partner_hits == 0
        and ("no agentic" in blob.lower() or "no partner" in blob.lower())
    )

    if single_track_quant_only:
        proj = "QUANT_TRADING"
        tax_id = "QUANT_TRADING_HPC"
        sel_prof = "quant_risk_hpc"
        rationale = "Pure quantitative risk/derivatives/HPC mandate."
    elif fde_context:
        proj = "SVP_ENGINEERING_AI_PLATFORM"
        tax_id = "ENGINEERING_PLATFORM"
        sel_prof = "svp_agentic_engineering"
        rationale = "Forward-deployed AI platform engineering leadership mandate."
    elif (health_hits >= 2 or role_has_health) and (health_hits >= ins_hits or role_has_cdao or "mlr" in blob.lower() or "hipaa" in blob.lower()):
        proj = "HEALTHCARE_PAYER_DATA_AI"
        tax_id = "DATA_ANALYTICS_LEADERSHIP"
        sel_prof = "healthcare_payer_data_ai"
        rationale = "Healthcare payer/provider data, biostatistics, and AI executive mandate."
    elif (ins_hits >= 2 or role_has_ins) and ins_hits >= bank_hits:
        has_brokerage = has_word_signal(blob, "brokerage") or has_word_signal(blob, "distribution technology")
        has_it_strategy = has_word_signal(blob, "it strategy") or has_word_signal(blob, "enterprise architecture")
        if has_brokerage:
            proj = "INSURANCE_BROKERAGE_IT_INNOVATION"
            tax_id = "INSURANCE_BROKERAGE_IT_INNOVATION"
            sel_prof = "insurance_it_strategy"
            rationale = "Insurance brokerage IT innovation and distribution architecture mandate."
        elif role_has_tech_exec or agentic_hits >= 2 or not has_it_strategy:
            proj = "INSURANCE_CARRIER_TRANSFORMATION"
            tax_id = "INSURANCE_CARRIER_TRANSFORMATION"
            sel_prof = "insurance_agentic_ai"
            rationale = "Insurance carrier / digital insurer engineering, CTO, and AI transformation mandate."
        else:
            proj = "INSURER_IT_AI_ENABLEMENT"
            tax_id = "INSURER_IT_AI_ENABLEMENT"
            sel_prof = "insurance_it_strategy"
            rationale = "Insurer IT strategy and enterprise architecture enablement mandate."
    elif bank_hits >= 2 or (role_has_bank_risk and bank_hits >= 1):
        if has_word_signal(blob, "model risk") or has_word_signal(blob, "sr 11-7") or has_word_signal(blob, "sr 11 7") or has_word_signal(blob, "ccar") or has_word_signal(blob, "basel"):
            proj = "REGULATED_AI_GOVERNANCE" if bank_hits <= 2 and not has_word_signal(blob, "banking") else "BANKING_PLATFORM_AI"
            tax_id = proj
            sel_prof = "banking_model_risk_ai"
            rationale = "Regulated banking AI platform and model risk governance mandate."
        else:
            proj = "BANKING_PLATFORM_AI"
            tax_id = "BANKING_PLATFORM_AI"
            sel_prof = "banking_model_risk_ai"
            rationale = "Banking AI platform leadership mandate."
    elif role_has_pe_partner or (pe_hits >= 3 and not role_has_partner):
        proj = "PE_OPERATING_PARTNER_TRANSFORMATION"
        tax_id = "CONSULTING_DELIVERY_LEADERSHIP"
        sel_prof = "executive_agentic_transformation"
        rationale = "Private equity operating partner / enterprise AI transformation mandate."
    elif (role_has_partner and not role_has_pe_partner) or (partner_hits >= 3 and partner_hits >= agentic_hits):
        if has_word_signal(blob, "applied ai") or has_word_signal(blob, "reference architecture") or has_word_signal(blob, "partner engineering") or has_word_signal(blob, "deployment engineering"):
            proj = "PARTNER_APPLIED_AI_ARCHITECTURE"
            tax_id = "PARTNER_APPLIED_AI_ARCHITECTURE"
        elif has_word_signal(blob, "marketplace") or has_word_signal(blob, "hyperscaler"):
            proj = "HYPERSCALER_MARKETPLACE_GTM"
            tax_id = "HYPERSCALER_MARKETPLACE_GTM"
        else:
            proj = "ANTHROPIC_PARTNERSHIPS_APPLIED_AI"
            tax_id = "PARTNERSHIPS_GTM"
        sel_prof = "ai_partnerships_gtm"
        rationale = "Frontier AI / hyperscaler partner architecture and commercial GTM mandate."
    elif role_has_cdao and not agentic_hits >= 4:
        proj = "DATA_ANALYTICS_LEADERSHIP"
        tax_id = "DATA_ANALYTICS_LEADERSHIP"
        sel_prof = "balanced_enterprise_ai"
        rationale = "Enterprise data, analytics, and governed AI leadership mandate."
    elif has_word_signal(blob, "cfo") or has_word_signal(blob, "strategic finance") or has_word_signal(blob, "synergy"):
        proj = "STRATEGIC_FINANCE"
        tax_id = "STRATEGIC_FINANCE"
        sel_prof = "executive_agentic_transformation"
        rationale = "Strategic finance, M&A analytics, and commercial value mandate."
    elif quant_hits >= 3:
        proj = "QUANT_TRADING"
        tax_id = "QUANT_TRADING_HPC"
        sel_prof = "quant_risk_hpc"
        rationale = "Quantitative modeling, derivatives, and HPC leadership mandate."
    elif fde_context or agentic_hits >= 2:
        proj = "SVP_ENGINEERING_AI_PLATFORM"
        tax_id = "ENGINEERING_PLATFORM"
        sel_prof = "svp_agentic_engineering"
        rationale = "SVP Engineering / CTO agentic AI platform and cloud engineering mandate."
    else:
        # Check taxonomy fallback if provided or load canonical taxonomy.
        proj = "THREE_PHASE_GENERALIST" if (ins_hits + bank_hits + quant_hits > 0 and partner_hits > 0 and agentic_hits > 0) else "CHIEF_AI_OFFICER"
        tax_id = "EXECUTIVE_LEADERSHIP"
        sel_prof = "balanced_enterprise_ai"
        rationale = "Generalist executive AI and enterprise technology leadership mandate."

    # Refine track weights with domain-aware bumps while keeping 3-era representation intact.
    base_tracks = dict(PROJECTION_TRACK_WEIGHTS.get(proj) or PROJECTION_TRACK_WEIGHTS["SVP_ENGINEERING_AI_PLATFORM"])
    if ins_hits >= 2 or bank_hits >= 2 or health_hits >= 2 or quant_hits >= 2:
        base_tracks["track_actuarial_risk_derivatives"] += 0.05
    if partner_hits >= 2 or pe_hits >= 2 or has_word_signal(blob, "aws") or has_word_signal(blob, "cloud"):
        base_tracks["track_data_tech_cloud_ml"] += 0.04
    if agentic_hits >= 2:
        base_tracks["track_genai_agentic"] += 0.04
    track_weights = _normalize_track_weights(
        base_tracks,
        enforce_three_era_floor=not single_track_quant_only,
    )

    employer_weights = dict(
        SELECTOR_EMPLOYER_WEIGHTS.get(sel_prof) or SELECTOR_EMPLOYER_WEIGHTS["balanced_enterprise_ai"]
    )
    slot_budgets = dict(
        SLOT_BUDGET_BY_PROFILE.get(sel_prof) or SLOT_BUDGET_BY_PROFILE["balanced_enterprise_ai"]
    )

    # Credential elevation policy (Operator Q2): elevate FSA / Columbia MS Biostatistics / AWS SAP
    # whenever differentiating for the target mandate.
    creds: list[str] = []
    if ins_hits >= 1 or bank_hits >= 1 or health_hits >= 1 or quant_hits >= 1 or pe_hits >= 2:
        creds.append("cert_fsa_001")
    if health_hits >= 1 or role_has_cdao or quant_hits >= 1 or bank_hits >= 1 or ins_hits >= 2:
        creds.append("edu_columbia_ms_biostat_001")
    if agentic_hits >= 1 or partner_hits >= 1 or has_word_signal(blob, "aws") or has_word_signal(blob, "cloud"):
        creds.append("cert_aws_sap_001")
    if not creds:
        creds.extend(["cert_fsa_001", "cert_aws_sap_001"])

    return MandateRouteDecision(
        canonical_projection_role=proj,
        taxonomy_role_family=tax_id,
        selector_profile=sel_prof,
        track_weights=track_weights,
        employer_weights=employer_weights,
        slot_budget_profile=slot_budgets,
        credential_elevation_ids=tuple(dict.fromkeys(creds)),
        fde_context=fde_context,
        requires_commercial_pairing=requires_commercial_pairing,
        detected_domain_signals=tuple(detected),
        mandate_rationale=rationale,
    )


class MandateRoutingEngine:
    """Stateful facade caching taxonomy lookups for repeatable mandate routing."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or ROOT
        self._taxonomy_cache: dict[str, Any] | None = None

    def load_taxonomy(self) -> dict[str, Any]:
        if self._taxonomy_cache is not None:
            return self._taxonomy_cache
        tax_path = resolve_apps_rg_path(
            self.repo_root,
            "config",
            "domain_contract",
            "master_role_family_taxonomy.yaml",
        )
        import yaml  # type: ignore[import-untyped]

        loaded = yaml.safe_load(tax_path.read_text(encoding="utf-8")) or {}
        self._taxonomy_cache = dict(loaded) if isinstance(loaded, dict) else {}
        return self._taxonomy_cache

    def route(
        self,
        *,
        target_role: str = "",
        jd_text: str = "",
        briefing_text: str = "",
    ) -> MandateRouteDecision:
        return resolve_mandate_route(
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=briefing_text,
            taxonomy=self.load_taxonomy(),
        )


__all__ = [
    "ALL_EMPLOYER_LANES",
    "CANONICAL_TAXONOMY_TO_PROJECTION",
    "MandateRouteDecision",
    "MandateRoutingEngine",
    "PROJECTION_TRACK_WEIGHTS",
    "SELECTOR_EMPLOYER_WEIGHTS",
    "SLOT_BUDGET_BY_PROFILE",
    "TRACK_IDS",
    "count_word_signals",
    "has_word_signal",
    "resolve_mandate_route",
]
