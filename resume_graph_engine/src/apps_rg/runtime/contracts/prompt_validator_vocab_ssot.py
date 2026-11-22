"""Canonical shared vocabulary SSOT between apps_rg prompt producers and X2 validators.

Enforces INV-PROMPT-VALIDATOR-VOCAB-SYMMETRY: prompt assembly templates, voice-repair
prompts, and deterministic X2 gates MUST import executive abstraction nouns, seniority
prefixes, credential blocklists, word-count floors/caps, and action-verb / authority
lexicons from this single module so prompts never instruct the model to emit tokens
that downstream X2 validators reject.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Headline shared vocabulary (headline_pa, ExecutiveVoiceRepairAgent, headline_x2)
# ---------------------------------------------------------------------------

APPROVED_HEADLINE_SENIORITY_PREFIXES: tuple[str, ...] = (
    "SVP Engineering",
    "SVP Enterprise Architecture",
    "SVP AI Strategy",
    "SVP IT Strategy",
    "SVP Agentic Transformation",
    "SVP Transformation",
    "SVP Enterprise AI",
    "SVP Technology Strategy",
    "SVP Agentic AI Platforms",
    "Partner",
    "Executive Director",
    "Managing Director",
)

HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS: tuple[str, ...] = (
    "Platforms",
    "Architecture",
    "Governance",
    "Systems",
    "Ecosystems",
    "Solutions",
    "Partnerships",
    "Alliances",
    "Delivery",
    "Orchestration",
    "Modernization",
    "Transformation",
    "Commercialization",
    "Regulated",
    "Enterprise",
)

HEADLINE_EXECUTIVE_ABSTRACTION_RE: re.Pattern[str] = re.compile(
    r"(?:\bplatforms?\b|\barchitecture\b|\barchitectures\b|\bgovernance\b|\bgoverned\b|"
    r"\bmodernization\b|\bmodernizations?\b|\btransformations?\b|\bvalue\s+creation\b|"
    r"\becosystems?\b|\bcommercialization\b|\bregulated\b|\bsystems?\b|"
    r"\badoption\b|\boperating\s+model\b|\bco-?sell\b|\bmotions?\b|"
    r"\bpartners?\b|\bpartnerships?\b|\balliances?\b|\benterprise\b|\bruntime\b|\binfrastructure\b|"
    r"\bproductization\b|\bcontrols?\b|\bcloud\s+data\b|\baccelerators?\b|\badvisory\b|"
    r"\bresilience\b|\breliability\b|\bdevsecops\b|\bdelivery\b|\bsolutions?\b|\benablement\b|"
    r"\broadmaps?\b|\bstrategy\b|\bstrategies\b|\borchestration\b|\bdeployments?\b)",
    re.IGNORECASE,
)

HEADLINE_FORBIDDEN_PLUMBING_LABELS: tuple[str, ...] = (
    "Three Lines Governance",
    "Client Adoption Systems",
    "SCADA Systems",
    "Telemetry AI Platform",
    "Portal Agentic Platform",
    "Compliance AI Governance",
)

HEADLINE_SIGNAL_FLOOR_PLATFORM_TOKENS: tuple[str, ...] = (
    "Platforms",
    "Platform",
    "Architecture",
    "Runtime",
)

HEADLINE_SIGNAL_FLOOR_GOVERNANCE_TOKENS: tuple[str, ...] = (
    "Governance",
    "Governed",
    "Regulated",
)

# ---------------------------------------------------------------------------
# Competencies shared vocabulary (competencies_pa, ExecutiveVoiceRepairAgent, competencies_x2)
# ---------------------------------------------------------------------------

COMPETENCIES_TERM_MIN_WORDS: int = 3
COMPETENCIES_TERM_MAX_WORDS: int = 7

COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS: tuple[str, ...] = (
    "fundamentals",
    "accreditation",
    "practitioner",
    "certified",
    "certificate",
    "certification",
)

_SKILL_ID_PREFIX_STRIPS: tuple[str, ...] = (
    "sr w12 ",
    "p2 gtm ",
    "p2 tech ",
)

_FORBIDDEN_CREDENTIAL_TOKEN_SET: frozenset[str] = frozenset(
    tok.lower() for tok in COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS
)


def sanitize_allocated_skill_concept_hint(skill_id: str) -> str:
    """Derive a clean capability concept hint from a graph skill_id with zero credential leakage."""
    raw = str(skill_id or "").strip()
    if raw.lower().startswith("skill:"):
        raw = raw[6:]
    elif raw.lower().startswith("skill_"):
        raw = raw[6:]
    normalized = raw.replace(":", " ").replace("_", " ").strip()
    lowered = " ".join(normalized.split()).lower()
    for prefix in _SKILL_ID_PREFIX_STRIPS:
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix) :].strip()
    kept_tokens = [
        tok for tok in lowered.split() if tok and tok not in _FORBIDDEN_CREDENTIAL_TOKEN_SET
    ]
    return " ".join(kept_tokens) if kept_tokens else "enterprise architecture"


# ---------------------------------------------------------------------------
# Experience bullet & narrative shared lexicons (bullet_quality_floor_x2, narrative_quality_x2)
# ---------------------------------------------------------------------------

EXPERIENCE_STRONG_ACTION_VERBS: frozenset[str] = frozenset({
    "architected", "architect", "engineered", "engineer", "operationalized", "operationalize",
    "directed", "direct", "structured", "converted", "convert", "deployed", "designed",
    "established", "establish", "led", "lead", "built", "build", "launched", "launch",
    "modernized", "modernize", "forged", "forge", "drove", "drive", "productized",
    "productize", "standardized", "standardize", "unified", "unify", "accelerated",
    "accelerate", "cut", "scaled", "scale", "transformed", "transform", "generated",
    "generate", "delivered", "deliver", "created", "create", "implemented", "implement",
    "developed", "develop", "oversaw", "oversee", "managed", "manage", "steered", "steer",
    "instituted", "institute", "commercialized", "commercialize", "pioneered", "pioneer",
    "defined", "define", "spearheaded", "spearhead", "owned", "own", "headed", "head",
    "championed", "champion", "governed", "govern",
    "embedded", "embed", "ran", "run", "set",
    "aligned", "align", "advised", "advise", "translated", "translate",
    "partnered", "partner", "served", "serve",
    "achieved", "achieve", "unlocked", "unlock", "secured", "secure",
    "captured", "capture", "realized", "realize", "expanded", "expand",
    "grew", "grow", "increased", "increase", "reduced", "reduce",
    "compressed", "compress", "sustained", "sustain", "orchestrated", "orchestrate",
    "anchored", "anchor", "strengthened", "strengthen",
    "eliminated", "eliminate", "enabled", "enable", "prevented", "prevent",
    "mitigated", "mitigate", "protected", "protect", "safeguarded", "safeguard",
    "enforced", "enforce", "remediated", "remediate", "hardened", "harden",
    "improved", "improve", "lowered", "lower", "de-risked", "derisked",
    "automated", "automate", "streamlined", "streamline", "consolidated", "consolidate",
    "resolved", "resolve", "closed", "close",
    "shortened", "shorten", "tightened", "tighten", "halved", "halve",
    "trimmed", "trim", "curtailed", "curtail", "shaped", "shape", "codified", "codify",
    "re-architected", "rearchitected", "re-engineered", "reengineered",
    "re-platformed", "replatformed",
})

EXPERIENCE_WEAK_ACTION_VERBS: frozenset[str] = frozenset({
    "supported", "helped", "assisted", "worked on", "participated", "contributed",
    "involved in", "part of", "utilized",
})

NARRATIVE_WEAK_VERBS: frozenset[str] = frozenset({
    "supported", "helped", "assisted", "contributed", "participated",
    "worked", "involved", "utilized", "leveraged",
})

NARRATIVE_CONSULTING_PHRASES: frozenset[str] = frozenset({
    "drive strategic value", "ensure alignment", "leveraged best practices",
    "worked closely with", "partnered with stakeholders", "aligned with the business",
    "facilitating collaboration", "drove alignment", "drove strategic alignment",
    "enabling the business", "providing thought leadership", "thought leadership",
    "best practices",
})

NARRATIVE_STRONG_VERBS: frozenset[str] = frozenset({
    "owned", "drove", "scaled", "championed", "productized", "operationalized",
    "established", "anchored", "stewarded", "originated", "architected",
    "engineered", "directed", "structured", "converted", "deployed", "designed",
    "launched", "modernized", "forged", "built", "standardized", "unified",
    "accelerated", "transformed", "generated", "delivered", "implemented",
    "oversaw", "managed", "steered", "pioneered", "defined", "spearheaded",
    "led", "created", "advised", "guided",
})

NARRATIVE_AUTHORITY_SIGNALS: frozenset[str] = frozenset({
    "platform", "platforms", "enterprise", "enterprises", "mandate", "mandates",
    "roadmap", "roadmaps", "infrastructure", "organization", "organizations",
    "architecture", "architectures", "governance", "production", "regulated",
    "commercialization", "productization", "strategy", "operating", "model",
    "c-suite", "board", "executive", "portfolio", "portfolios", "diligence",
    "transformation", "transformations", "advisory", "systems", "programs", "leadership",
})

__all__ = [
    "APPROVED_HEADLINE_SENIORITY_PREFIXES",
    "COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS",
    "COMPETENCIES_TERM_MAX_WORDS",
    "COMPETENCIES_TERM_MIN_WORDS",
    "EXPERIENCE_STRONG_ACTION_VERBS",
    "EXPERIENCE_WEAK_ACTION_VERBS",
    "HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS",
    "HEADLINE_EXECUTIVE_ABSTRACTION_RE",
    "HEADLINE_FORBIDDEN_PLUMBING_LABELS",
    "HEADLINE_SIGNAL_FLOOR_GOVERNANCE_TOKENS",
    "HEADLINE_SIGNAL_FLOOR_PLATFORM_TOKENS",
    "NARRATIVE_AUTHORITY_SIGNALS",
    "NARRATIVE_CONSULTING_PHRASES",
    "NARRATIVE_STRONG_VERBS",
    "NARRATIVE_WEAK_VERBS",
    "sanitize_allocated_skill_concept_hint",
]
