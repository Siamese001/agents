"""Voice repair constants, patterns, and canonical slot/override text."""
from __future__ import annotations

import re

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    MATERIAL_METRIC_RE as _MATERIAL_METRIC_RE,
)

_EXTENSIVE_EXPERIENCE_RE = re.compile(r"\bwith extensive experience in\b", re.IGNORECASE)
_EXTENSIVE_EXPERIENCE_EXEC_RE = re.compile(r"\ban engineering executive with extensive experience\b", re.IGNORECASE)

_S5_CREDENTIAL_DUMP_RE = re.compile(
    r"\b(?:built|established)\s+advanced\s+quantitative\s+foundation\b"
    r".*\b(?:derivatives\s+pricing|multi-greek)\b"
    r".*\b(?:capital\s+modeling|fsa)\b",
    re.IGNORECASE | re.DOTALL,
)
_S6_THIN_RECAP_RE = re.compile(r"\bextend\s+that\s+arc\s+toward\b", re.IGNORECASE)
_FORCED_LINEAGE_BRIDGE_RE = re.compile(
    r"\bthat\s+regulatory\s+lineage\s+work\s+extended\s+to\b",
    re.IGNORECASE,
)
# Retired judge-fail strings — kept only for regression guards in tests.
_JUDGE_FAIL_S5_SUBSTRING = "capital-markets rigor informs which platform investments"
_JUDGE_FAIL_S6_LOOKING_AHEAD = re.compile(r"^Looking ahead,\s*", re.IGNORECASE)

_FORMULAIC_S2_RE = re.compile(
    r"^Building on that platform foundation,\s*",
    re.IGNORECASE,
)
_S5_STRESS_ECHO_RE = re.compile(r"\bstress-testing\b", re.IGNORECASE)
_S4_PARTICIPIAL_AFTER_COMPLEMENT_RE = re.compile(
    r"(Complementing that regulatory foundation,)\s+re-architecting\b",
    re.IGNORECASE,
)
_S5_META_COMMENTARY_RE = re.compile(
    r"\s+rather than listing credential labels\.?",
    re.IGNORECASE,
)
_UNIFY_HELD_METRIC_PATTERNS: tuple[re.Pattern[str], ...] = ()
_GENERIC_S1_RE = re.compile(
    r"^Technology strategy executive who aligns enterprise IT direction,?\s+"
    r"governed AI platform delivery,?\s+and innovation programs for regulated enterprise scale\.?\s*",
    re.IGNORECASE,
)
_S1_DISTINCTIVE_REPLACEMENT = (
    "Enterprise technology leader who unifies governed AI platforms, regulatory lineage, and digital innovation programs "
    "into one IT strategy and innovation agenda for decentralized regulated enterprises. "
)
_FORMULAIC_S3_RE = re.compile(
    r"^Through that operating model,\s*",
    re.IGNORECASE,
)
_AI_PARTNERSHIP_META_S6_RE = re.compile(
    r"\b(?:this\s+)?leadership\s+profile\b|\bcan\s+translate\s+into\b|"
    r"\bcan\s+guide\s+future\b|\bguide\s+future\s+partner\b",
    re.IGNORECASE,
)
_AI_PARTNERSHIP_S4_REPEAT_RE = re.compile(
    r"\bregulated\s+cloud\s+modernization\s+architecture\b.*\bfinancial-services\s+workloads\b",
    re.IGNORECASE,
)
_AI_PARTNERSHIP_S4_SENTENCE = (
    "Governed agentic platform architecture translated distributed cloud/data engineering "
    "into regulated AI delivery patterns with traceable controls and standards-aware adoption."
)
_AI_PARTNERSHIP_S6_SENTENCE = (
    "That partner channel foundation converted applied-AI architectures and alliance co-sell "
    "execution into repeatable adoption across cloud-vendor and enterprise partner ecosystems."
)
_AI_PARTNERSHIP_PAST_TENSE_S1 = (
    "Technology executive who led IBM-AWS alliance co-sell motions and now applies that "
    "partner discipline to secure platform productization and IP-led revenue growth."
)
_AI_PARTNERSHIP_DISTINCT_S2 = (
    "At IBM, financial-services modernization opportunities were shaped through partner "
    "collaboration and solution-architecture feasibility."
)
_AI_PARTNERSHIP_DEVSECOPS_S5 = (
    "Regulated DevSecOps release governance strengthened modernization delivery with "
    "controlled deployment discipline."
)
_AI_PARTNERSHIP_PLATFORM_CONTROL_S2 = (
    "From that foundation, the leader architects an agentic AI platform control plane "
    "with explicit decision rules."
)
_AI_PARTNERSHIP_EVIDENCE_LED_S6 = (
    "Together, partner solution architecture, regulated delivery, and commercialized "
    "platform IP established a repeatable enterprise adoption model."
)
_AI_PARTNERSHIP_COHERENCE_COMPACTION: tuple[str, ...] = (
    "Engineering executive who embedded release automation and security scanning, including automated release pipelines and DevSecOps scanning, in regulated modernization delivery, strengthening the foundation for secure enterprise-scale platform architecture.",
    "On that foundation, architected an agentic AI platform control plane with explicit decision rules for governed deployment across complex enterprise environments.",
    "Established architecture governance and automated release controls to modernize complex systems while maintaining continuous deployment resilience.",
    "Established clear human review and escalation paths for policy-gated AI deployments, keeping intervention and accountability visible at critical decision points.",
    "Expanded enterprise AI adoption through reusable platform solutions, carrying that combined technical and commercial discipline into partner ecosystems.",
    "Generated $22M in IP-led revenue growth through platform productization, converting reusable technical capability into commercialized enterprise solutions.",
)

_FILLER_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\ban engineering executive with a proven track record in delivering\b", re.IGNORECASE), "Engineering executive delivering"),
    (re.compile(r"\bwith a proven track record in\b", re.IGNORECASE), " leading"),
    (re.compile(r"\bwith a proven track record of\b", re.IGNORECASE), " with a record of"),
    (re.compile(r"\bproven track record\b", re.IGNORECASE), ""),
    (re.compile(r"\bresults-driven\b", re.IGNORECASE), "outcomes-focused"),
    (re.compile(r"\bseasoned executive\b", re.IGNORECASE), "engineering executive"),
)

_META_PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("with active-voice delivery and governance discipline", "with regulated platform delivery"),
    ("governance discipline", "regulatory foundation"),
    ("active-voice delivery", "platform delivery"),
    ("across the scope described in selected facts", ""),
    ("canonical facts used as proof", ""),
    ("same fact plan", ""),
    ("this leadership profile", "That combined technical and commercial foundation"),
    ("leadership profile", "combined technical and commercial foundation"),
    ("this summary", "That combined delivery foundation"),
    ("the candidate", "That executive background"),
    ("this individual", "That executive background"),
    ("this executive", "That executive background"),
    ("this leader directed ", "directed "),
    ("this leader led ", "led "),
    ("this leader built ", "built "),
    ("this leader drove ", "drove "),
    ("this leader engineered ", "engineered "),
    ("this leader architected ", "architected "),
    ("this leader steered ", "steered "),
    ("cosell", "co-sell"),
    ("can translate into", "translates into"),
    ("additionally, their", "In parallel, that"),
    ("furthermore, their", "In parallel, that"),
    ("additionally,", "In parallel,"),
    ("furthermore,", "In parallel,"),
    ("an experienced engineering executive with a strong background", "Engineering executive with a background"),
    ("an experienced leader in regulated", "Technology leader in regulated"),
    ("with extensive experience in", "experienced in"),
    ("with extensive experience", "with deep experience"),
)
_BARE_SUBJECTLESS_OPENER_RE = re.compile(r"^(?:positions|can\s+translate|translates\s+into|brings)\b", re.IGNORECASE)

_GOV_POOL_UTILIZATION_SENTENCE = (
    "Applied across enterprise programs, Basel III and CCAR data lineage and "
    "automated validation frameworks cut regulatory reporting errors by 40%."
)

_INSURTECH_POOL_UTILIZATION_SENTENCE = (
    "In parallel, regulated cloud modernization architecture for financial-services workloads "
    "established reference architecture reuse across migration waves, grounding partner-led AI "
    "solutions in validated delivery patterns while addressing insurance regulatory cloud "
    "adoption standards."
)

_UNIFY_PLATFORM_COMMERCIALIZATION_UTILIZATION_SENTENCE = (
    "Platform commercialization, IP-led revenue, margin expansion, and team scale now position "
    "partner-led AI solution architecture and alliance GTM motion."
)

_GRAPH_OVERRIDE_ANCHOR = "dependency graph intelligence enables accelerated"

_STOCK_BRIDGE_OPENERS: tuple[str, ...] = (
    "building on", "through that", "that operating foundation",
    "complementing", "with that governance", "against that", "from that",
)
_STOCK_BRIDGE_PREFIX_RE = re.compile(
    r"^(?:Building on that [^,]{0,80},\s*|Through that [^,]{0,80},\s*|That operating foundation also\s+|"
    r"That operating foundation\s*,\s*|Complementing [^,]{0,80},\s*|With that governance,\s*|"
    r"Against that [^,]{0,80},\s*|From that [^,]{0,80},\s*)",
    re.IGNORECASE,
)

_CANONICAL_DISPLAY_SENTENCES: dict[str, str] = {
    "fact_governance_003": (
        "Applied across enterprise programs, Basel III and CCAR data lineage and "
        "automated validation frameworks cut regulatory reporting errors by 40%."
    ),
    "fact_quant_hpc_003": (
        "That regulatory foundation is grounded in quantitative rigor established through "
        "FSA-chartered actuarial work in capital modeling and portfolio stress analytics, "
        "informing data governance and AI strategy at scale."
    ),
    "fact_consulting_001": (
        "Against that delivery foundation, directed large-scale regulatory IT "
        "transformations and legacy-modernization programs for major financial "
        "institutions across enterprise risk, data, and cloud domains."
    ),
    "fact_exec_002": (
        "In parallel, the ML engineering organization scaled from 8 to 28 specialists, "
        "advancing governed agentic AI delivery and enterprise innovation programs."
    ),
}

_CANONICAL_FACT_SLOT: dict[str, int] = {
    "fact_governance_003": 1,
    "fact_quant_hpc_003": 3,
    "fact_consulting_001": 4,
    "fact_exec_002": 5,
}
