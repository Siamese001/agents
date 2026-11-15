"""Constants, lexical primitives, and gate result model for IBM bullets X2 gates."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    COVERAGE_WS_RE as _COVERAGE_WS_RE,
    SEMANTIC_OVERLAP_STOPWORDS as _SEMANTIC_OVERLAP_STOPWORDS,
    WORD_RE as _SEMANTIC_OVERLAP_TOKEN_RE,
    semantic_overlap_tokens,
)

IBM_BULLET_IDS = (
    "bul_ibm_001",
    "bul_ibm_002",
    "bul_ibm_003",
    "bul_ibm_004",
    "bul_ibm_005",
)
TEXT_COVERAGE_INTEGRITY_GATE_ID = "x2_text_claim_coverage_integrity"
IBM_BULLET_GRAPH_SKILL_NODE_IDS_GATE_ID = "x2_ibm_bullet_graph_skill_node_ids_required"
IBM_BULLET_METRIC_SOURCE_GATE_ID = "x2_ibm_metric_source_required"

# Category-style prefix at start of resume bullet (themes belong in bullet_theme / metadata only).
TAXONOMY_LABEL_PREFIX_PATTERN = re.compile(r"^[A-Z][A-Za-z /,&-]{3,60}:\s+")

UNIFY_RUNTIME_TERM_PATTERNS = (
    r"\bagentic\s+ai\b",
    r"\bagentic\s+runtime\b",
    r"\bgraphrag\b",
    r"\bmulti[- ]?agent\s+orchestration\b",
    r"\bdeterministic\s+routing\b",
    r"\bsandboxed\s+execution\b",
    r"\breplayable\s+traces\b",
    r"\bgoverned\s+ai\s+runtime\b",
    r"\bprompt\s+assembly\b",
    r"\bjudge\s+mesh\b",
    r"\bgoverned\s+spine\b",
    r"\bc0\b",
    r"\bl2\b",
    r"\bexit\b",
    r"\buwg\b",
)

REQUIRED_TOP_LEVEL = {
    "bullets",
    "selected_fact_plan",
    "claim_ledger",
    "jd_alignment",
    "gap_notes",
    "change_log",
    "self_check",
}

CORE_METRIC_TOKENS = ("20%", "weeks to hours")

# Metric ownership: REQUIRED_ANCHOR — metric must appear on assigned canonical bullet text.
IBM_METRIC_ANCHOR_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("20%", "20 %"), "bul_ibm_004"),
)


@dataclass
class X2GateResult:
    """Deterministic X2 gate outcome row."""

    gate_id: str
    gate_type: str
    pass_: bool
    observed_value: Any
    threshold: Any
    failure_reason: str | None
    evidence_ref: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize gate outcome using JSON key ``pass``."""
        data = asdict(self)
        data["pass"] = data.pop("pass_")
        return data


__all__ = [
    "CORE_METRIC_TOKENS",
    "IBM_BULLET_GRAPH_SKILL_NODE_IDS_GATE_ID",
    "IBM_BULLET_IDS",
    "IBM_BULLET_METRIC_SOURCE_GATE_ID",
    "IBM_METRIC_ANCHOR_RULES",
    "REQUIRED_TOP_LEVEL",
    "TAXONOMY_LABEL_PREFIX_PATTERN",
    "TEXT_COVERAGE_INTEGRITY_GATE_ID",
    "UNIFY_RUNTIME_TERM_PATTERNS",
    "X2GateResult",
    "_COVERAGE_WS_RE",
    "_SEMANTIC_OVERLAP_STOPWORDS",
    "_SEMANTIC_OVERLAP_TOKEN_RE",
    "semantic_overlap_tokens",
]
