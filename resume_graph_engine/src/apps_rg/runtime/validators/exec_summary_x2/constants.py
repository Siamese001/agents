"""Constants, patterns, and gate result model for executive summary X2 validators."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from apps_rg.runtime.section_judge_policy import REQUIRED_JUDGE_PROVIDER_KEYS
from apps_rg.runtime.section_model_limits import resolve_section_generation_model
from apps_rg.runtime.validators.executive_summary_sentence_utils import split_sentences

EXPECTED_PROMPT_TEMPLATE_REF = "apps_rg/prompt_assembly/templates/executive_summary.generate_scratch_v1.yaml"
EXPECTED_PROMPT_ID = "executive_summary.generate_scratch_v1"
EXPECTED_PA_SHELL_TEMPLATE_ID = "strategic_tailor_v1"

FIRST_PERSON_PATTERN = re.compile(r"\b(I|me|my|mine|we|our|ours)\b", re.IGNORECASE)
EM_DASH = "—"
INLINE_SOURCE_PATTERN = re.compile(r"\[(source|fact|citation)\s*:[^\]]+\]", re.IGNORECASE)
GENERIC_FILLER = [
    "proven track record",
    "seasoned executive",
    "dynamic leader",
    "visionary leader",
    "results-driven",
    "cutting-edge technologies",
    "market position",
    "strategic leader",
    "passionate",
    "transformative",
]

EXEC_SUMMARY_FORBIDDEN_META_PHRASES = [
    "across the scope described in selected facts",
    "with active-voice delivery and governance discipline",
    "active-voice delivery",
    "governance discipline",
    "same fact plan",
    "canonical facts used as proof",
]

EXEC_SUMMARY_FORBIDDEN_META_PHRASES_LOOSE = [
    "selected facts",
    "this summary",
    "the candidate",
    "this individual",
    "this executive",
    "this leadership profile",
    "leadership profile",
    "can translate into",
    "additionally, their",
    "furthermore, their",
    "additionally,",
    "furthermore,",
    "an experienced engineering executive with a strong background",
    "an experienced leader in regulated",
    "with extensive experience in",
    "with extensive experience",
    "former cto", "former chief technology officer", "former svp", "former senior vice president",
    "big-4 principal", "past principal", "past cto", "former partner",
]

EXEC_SUMMARY_INTERNAL_PLUMBING_BANNED_SUBSTRINGS: tuple[str, ...] = (
    "119-package",
    "119 modular subpackages",
    "32 readiness gates",
    "thirty-two readiness gates",
    "32 fail-closed",
    "six mcp servers",
    "6 custom mcp servers",
    "6 mcp servers",
    "sqlite wal",
    "fts5",
    "1024-d",
    "bge-m3",
    "dirichlet-laplace",
    "merkle-cached",
    "merkle subgraph",
    "universal write gateway",
    "8-surface system learning",
    "8 closed-loop system learning",
    "dual-track live executive copilot",
    "pcm audio spooler",
    "mlx whisper",
)

EXEC_SUMMARY_STUTTERED_STEM_PATTERNS: tuple[str, ...] = (
    "regulated enterprise regulatory findings",
    "regulated enterprises regulatory findings",
    "regulated enterprise regulatory",
    "regulated enterprises regulatory",
)

EXEC_SUMMARY_WEAK_S1_SUBJECT_OPENERS: tuple[str, ...] = (
    "executive leadership architects",
    "executive leadership identity",
    "the candidate ",
    "this leader ",
    "this executive ",
    "this individual ",
)


# Finite-verb pattern: matches common present/past tense verbs and auxiliary constructions.
# A sentence is a fragment if it has NO finite verb — it's a noun phrase or participial phrase.
# We use a conservative heuristic: look for at least one token that is a finite verb form.
_FINITE_VERB_RE = re.compile(
    r"\b("
    r"is|are|was|were|has|have|had|does|do|did|"
    r"can|could|will|would|shall|should|may|might|must|"
    r"[a-z]{3,}s\b|"  # third-person singular (e.g. "enables", "improves")
    r"[a-z]{3,}ed\b|"  # past tense / past participle (e.g. "reduced", "scaled")
    r"[a-z]{3,}es\b"   # third-person plural form (e.g. "establishes")
    r")",
    re.IGNORECASE,
)

# Noun-phrase-only starters that signal a fragment sentence when the rest is participial.
# Pattern: "NOUN_PHRASE, <participial_phrase>." with no finite verb.
_PARTICIPIAL_OPENER_RE = re.compile(
    r"^[A-Z][^.!?]*,\s+(built|established|formed|developed|grounded|rooted|"
    r"founded|centered|driven|designed|shaped|created)\s+through\b",
    re.IGNORECASE,
)

_SUBJECTLESS_VERB_OPENER_RE = re.compile(r"^(?:positions|can\s+translate|translates\s+into|brings)\b", re.IGNORECASE)



ACTION_VERB_OPENERS = (
    "designed", "strengthened", "generated", "reduced", "architected",
    "built", "implemented", "delivered", "created", "led", "scaled",
    "productized", "standardized", "operationalized", "spearheaded",
    "drove", "driven", "managed", "oversaw", "directed",
)

# Executive-summary mechanical chains (prompt + X1D); includes leading fillers.
EXEC_SUMMARY_MECHANICAL_OPENERS = (
    "led",
    "successfully",
    "also",
    "built",
    "delivered",
    "designed",
    "implemented",
    "architected",
    "productized",
    "scaled",
)

# Judge-visible robotic transitions. These are not forbidden individually; they
# fail only when stacked through the S2-S5 body cadence.
EXEC_SUMMARY_ROBOTIC_TRANSITION_PREFIXES = (
    "through that",
    "that operating foundation",
    "that migration discipline",
    "building on that",
    "with that governance",
    "from that",
    "against that",
    "complementing that",
)

# Phrases that must have direct source support
SOURCE_SENSITIVE_PHRASES = [
    "regulated enterprise workflows",
    "regulated environments",
    "compliance",
    "audit",
    "governance framework",
]

# Bridge claim phrases that are forbidden without direct support
INFERRED_BRIDGE_PHRASES = [
    "regulated enterprise workflows",
    "compliance",
    "market position",
    "enterprise-wide transformation",
    "strategic leader",
    "proven track record",
    "industry-leading",
    "mission-critical",
    "scalable and resilient infrastructure",
]

# Industry/domain claims that need direct support
INDUSTRY_DOMAIN_CLAIMS = [
    "regulated industries",
    "financial services",
    "healthcare",
    "insurance",
    "banking",
    "public sector",
    "compliance domain",
]

# Allowed top-level fields in model output
ALLOWED_TOP_LEVEL_FIELDS = {
    "executive_strategy_thesis",
    "resume_display_text",
    "executive_summary_text",
    "selected_fact_plan",
    "claim_ledger",
    "jd_alignment",
    "gap_notes",
    "change_log",
    "self_check",
    "sentence_map",
    "brushstroke_map",
    "graph_skill_refs",
    "executive_summary_composition_plan",
    "text_claim_coverage",
    "source_sensitive_phrase_ledger",
    "input_payload_hash",
    "output_payload_hash",
    "claim_ledger_hash",
    "allowed_fact_ids_hash",
    "c0_graph_diagnostics",
    "allowed_fact_utilization_receipt",
}

# Required runtime artifacts.
#
# The X2 gate runs before the lane writes the final L2/result receipts below.  Keep those
# post-X2 receipts in the full inventory for runtime-exhaust checks, but do not require
# placeholder versions during the pre-X2 deterministic gate.  Placeholder writes caused the
# parent run's write gateway to flag the final receipts as write amplification.
REQUIRED_ARTIFACTS = [
    "provider_request.json",
    "real_l2_generation_result.json",
    "runtime_payload.json",
    "prompt_selection_trace.json",
    "claim_ledger.json",
    "canonical_claim_ledger_v2.json",
    "text_claim_coverage.json",
    "fact_check_result.json",
    "x2_gate_outputs.json",
    "x3_disposition.json",
    "section_metric_receipt.json",
]
POST_X2_REQUIRED_ARTIFACTS = {
    "fact_check_result.json",
    "real_l2_generation_result.json",
    "section_metric_receipt.json",
    "x3_disposition.json",
}
PRE_X2_REQUIRED_ARTIFACTS = [
    artifact for artifact in REQUIRED_ARTIFACTS if artifact not in POST_X2_REQUIRED_ARTIFACTS
]

# Allowed generation model names for executive summary proof.
EXECUTIVE_SUMMARY_SECTION_ID = "executive_summary"
ALLOWED_MODELS = [
    resolve_section_generation_model(EXECUTIVE_SUMMARY_SECTION_ID),
]

# Required X1D judge providers
REQUIRED_JUDGE_PROVIDERS = list(REQUIRED_JUDGE_PROVIDER_KEYS)


@dataclass
class X2GateResult:
    gate_id: str
    gate_type: str
    pass_: bool
    observed_value: Any
    threshold: Any
    failure_reason: str | None
    evidence_ref: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pass"] = data.pop("pass_")
        return data


MECHANICAL_PROOF_OPENERS = frozenset({"productized", "designed", "strengthened", "standardized"})


POST_X2_X1D_WIRING_GATE_IDS: frozenset[str] = frozenset(
    {
        "x2_x1d_required_judges_present",
        "x2_x1d_raw_responses_written",
        "x2_x1d_schema_valid",
        "x2_x1d_judge_packet_hash_uniform",
    }
)


NORTH_STAR_SIGNATURE_PHRASES = (
    "fellow of the society of actuaries",
    "$22m",
    "$22 m",
    "reclaimed $14m",
    "reclaimed $14 m",
    "reclaimed $14",
    "productized ai revenue",
    "gross margins",
    "gross margin expansion",
    "expanding gross margins",
)


_GRAPH_EVIDENCE_PERCENT_CAPTURE_RE = re.compile(r"\b(\d+)\s*%")


_CROSS_SENTENCE_DEDUP_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:scaled|scaling)\s+(?:the\s+)?ml engineering organization from 8 to 28\b", re.I), "team_8_to_28"),
    (re.compile(r"\b8\s+to\s+28\s+specialists\b", re.I), "team_8_to_28_specialists"),
)


EVIDENCE_UTIL_MIN_POOL_FOR_LEDGER_DEPTH = 6
EVIDENCE_UTIL_MIN_LEDGER_ROWS_WHEN_POOL_LARGE = 5
EVIDENCE_UTIL_MIN_POOL_FOR_THIN_SENTENCE = 5
EVIDENCE_UTIL_MIN_WORDS_PER_SENTENCE_WHEN_FOUR = 12


# Vendor/cloud cert labels — inventory-style (e.g. AWS Associate). Not C0.3 phase-1 FSA rigor.
VENDOR_NAMED_CERT_LABELS: tuple[str, ...] = (
    "aws certified",
    "databricks",
    "certified solutions architect",
    "lakehouse fundamentals",
)

# FSA (Fellow of the Society of Actuaries): C0.3 skills-graph phase-1 rigor signal — not a vendor cert.
FSA_RIGOR_MARKERS: tuple[str, ...] = (
    "fellow of the society of actuaries",
    "society of actuaries",
    "fsa credential",
    "fsa designation",
)
FSA_WORD_RE = re.compile(r"\bfsa\b", re.IGNORECASE)

CREDENTIAL_CONTEXT_MARKERS: tuple[str, ...] = (
    *VENDOR_NAMED_CERT_LABELS,
    *FSA_RIGOR_MARKERS,
    "basel iii",
    "ccar",
)



_GRAPH_EVIDENCE_S1_CONNECTOR_PHRASES = (
    "to improve",
    "to reduce",
    "to streamline",
)
_GRAPH_EVIDENCE_S1_CONNECTOR_WORDS = (
    "integrating",
    "combining",
    "through",
    "while",
)
_GRAPH_EVIDENCE_S1_MECHANISM_TERMS = (
    "microservices",
    "hpc",
    "vector services",
    "routing",
    "orchestration",
    "retrieval",
    "pipelines",
)

