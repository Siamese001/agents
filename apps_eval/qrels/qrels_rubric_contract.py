"""External QRELS Rubric Contract, Core/Boilerplate Splitter & Consistency Locks (DIE Parity).

Implements the universal Anthropic/Google TREC Depth-10 QRELS standards:
1. Behavior-anchored 4-point relevance scale (3, 2, 1, 0) verified by SHA-256.
2. Five atomic binary checks + mechanical grade-cap & critique-before-Grade-0 locks.
3. Core statement vs. repeated boilerplate/scope footer separation + MM/DD/YYYY date normalization.
4. Non-contaminating quarantine dispositions (ABSTAIN_INSUFFICIENT_EVIDENCE, DEFECTIVE_QUERY).
5. Seeded presentation shuffling with zero channel/rank metadata leakage.

Zero concrete storage imports (`sqlite3` forbidden in `apps_eval`).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

EXTERNAL_QRELS_RUBRIC_ID = "external_qrels_rubric_v1"
DEFAULT_EXTERNAL_QRELS_RUBRIC_REL_PATH = Path("config/governance/external_qrels_rubric_v1.json")
ALLOWED_QRELS_GRADES: frozenset[int] = frozenset({0, 1, 2, 3})

QRELS_GRADE_ANCHORS: dict[str, dict[str, str]] = {
    "3": {
        "short_label": "Authoritative / Perfect",
        "meaning": (
            "Core statement directly and completely answers the query with concrete facts, "
            "metrics, owners, or boundaries actionable for the target surface."
        ),
    },
    "2": {
        "short_label": "Supporting / Acceptable",
        "meaning": (
            "Core statement gives specific supporting evidence relevant to the query, "
            "but misses a secondary condition, metric, or detail."
        ),
    },
    "1": {
        "short_label": "Marginal / Background Stub",
        "meaning": (
            "Core statement gives only high-level topical background, an org label, "
            "role bio, or generic boilerplate without directly answering the query."
        ),
    },
    "0": {
        "short_label": "Irrelevant / Confounder",
        "meaning": (
            "Wrong employer, wrong system/domain, policy-ineligible record, or "
            "off-topic lexical keyword trap."
        ),
    },
}

QRELS_ATOMIC_CHECKS: tuple[dict[str, Any], ...] = (
    {
        "id": "core_answers_query",
        "caps_grade_at_1_when_false": True,
        "label": "Core statement directly addresses the query (ignoring boilerplate footer)",
    },
    {
        "id": "exact_entity_or_metric_grounded",
        "caps_grade_at_1_when_false": False,
        "label": "Concrete facts, entities, or metrics match the query need",
    },
    {
        "id": "section_and_role_fit",
        "caps_grade_at_1_when_false": True,
        "label": "Fits the target resume/outreach/research surface and employer boundary",
    },
    {
        "id": "not_boilerplate_stub",
        "caps_grade_at_1_when_false": True,
        "label": "Substantive evidence (not a bare org label, bio, or boilerplate stub)",
    },
    {
        "id": "policy_and_clearance_eligible",
        "caps_grade_at_1_when_false": True,
        "label": "Permitted for external/target use with zero policy or clearance conflict",
    },
)

QRELS_ATOMIC_CHECK_IDS: frozenset[str] = frozenset(c["id"] for c in QRELS_ATOMIC_CHECKS)
QRELS_CAP_AT_1_CHECKS: tuple[str, ...] = tuple(
    c["id"] for c in QRELS_ATOMIC_CHECKS if c.get("caps_grade_at_1_when_false")
)

QRELS_REJECTION_TAGS: tuple[dict[str, str], ...] = (
    {"id": "WRONG_EMPLOYER", "label": "Wrong employer, engagement, or career band"},
    {"id": "SECTION_MISMATCH", "label": "Wrong target section or retrieval surface"},
    {"id": "LEXICAL_CONFOUNDER_TRAP", "label": "Superficial keyword match in unrelated context"},
    {"id": "BOILERPLATE_STUB", "label": "Bare org/role stub or repeated boilerplate shell"},
    {"id": "INSUFFICIENT_EVIDENCE", "label": "Lacks concrete facts or verifiable grounding"},
    {"id": "POLICY_RESTRICTED", "label": "Restricted, held, or policy-ineligible record"},
)

VALID_QRELS_REJECTION_TAG_IDS: frozenset[str] = frozenset(t["id"] for t in QRELS_REJECTION_TAGS)
VALID_QRELS_QUARANTINE_REASONS: frozenset[str] = frozenset(
    {"ABSTAIN_INSUFFICIENT_EVIDENCE", "DEFECTIVE_QUERY"}
)

BLIND_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "dense_rank",
        "dense_score",
        "sparse_rank",
        "sparse_score",
        "colbert_rank",
        "colbert_score",
        "bm25_rank",
        "bm25_score",
        "graph_rank",
        "graph_1hop",
        "fused_rank",
        "fused_score",
        "rrf_score",
        "final_score",
        "similarity",
        "original_rank",
        "selected",
        "channel_origin",
        "split",
        "partition_hidden",
    }
)

_FOOTER_SPLIT_RE = re.compile(
    r"\s*(?:"
    r"\[MECE Hierarchy\s*/\s*Scope\]|"
    r"\[Hierarchy\s*/\s*Scope\]|"
    r"(?:Operating context:|Scope:|Capabilities:|\[Scope\]:)"
    r")",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DOT_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")


def canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    """Compute deterministic SHA-256 over canonical sorted JSON."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalize_display_dates(text: str) -> str:
    """Normalize YYYY-MM-DD and MM.DD.YYYY dates into MM/DD/YYYY display dates."""
    value = str(text or "")
    value = _ISO_DATE_RE.sub(lambda m: f"{m.group(2)}/{m.group(3)}/{m.group(1)}", value)
    value = _DOT_DATE_RE.sub(lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}", value)
    return value


def split_core_and_boilerplate(raw_passage: str) -> tuple[str, str]:
    """Separate prominent core candidate statement from repeated scope/hierarchy/unit boilerplate."""
    normalized = normalize_display_dates(str(raw_passage or "").strip())
    if not normalized:
        return "", ""
    # Handle pipe-delimited semantic_unit payloads: keep [Claim]/[Outcomes]/[Evidence] in core,
    # route [Unit]/[Capabilities]/[Domain]/[Confidence]/[Scope] into dimmed boilerplate footer.
    if "[Unit]" in normalized and "[Claim]" in normalized:
        segments = [seg.strip() for seg in normalized.split("|") if seg.strip()]
        core_parts: list[str] = []
        ref_parts: list[str] = []
        for seg in segments:
            if seg.startswith(("[Unit]", "[Capabilities]", "[Domain]", "[Confidence]", "[Scope]", "[Lineage]")):
                ref_parts.append(seg)
            else:
                core_parts.append(seg)
        if core_parts:
            return " | ".join(core_parts), " | ".join(ref_parts)
    match = _FOOTER_SPLIT_RE.search(normalized)
    if not match:
        return normalized, ""
    core = normalized[: match.start()].strip()
    footer = normalized[match.start() :].strip()
    if not core:
        return normalized, ""
    return core, footer


def build_canonical_qrels_rubric_payload() -> dict[str, Any]:
    """Build the authoritative external_qrels_rubric_v1 payload with sealed rubric_sha256."""
    unsigned: dict[str, Any] = {
        "schema_version": "1.0.0",
        "rubric_id": EXTERNAL_QRELS_RUBRIC_ID,
        "scale_range": [0, 3],
        "grade_values": [0, 1, 2, 3],
        "relevant_grade_floor": 2,
        "grades": QRELS_GRADE_ANCHORS,
        "atomic_checks": list(QRELS_ATOMIC_CHECKS),
        "rejection_tags": list(QRELS_REJECTION_TAGS),
        "quarantine_reasons": sorted(VALID_QRELS_QUARANTINE_REASONS),
        "consistency_rules": [
            "core_statement_only_grading_required",
            "failed_cap_atomic_check_caps_grade_at_1",
            "grade_0_requires_rejection_tag_or_8_char_rationale",
            "quarantined_items_excluded_from_scored_denominators",
        ],
        "standard_lineage": [
            "Anthropic-Contextual-Retrieval-2025",
            "Anthropic-Demystifying-Evals-2026",
            "Google-TREC-Depth-10-Pooling",
            "DIE-External-Rubric-Calibration-v1",
        ],
    }
    return {**unsigned, "rubric_sha256": canonical_json_sha256(unsigned)}


def load_and_verify_qrels_rubric(rubric_path: Path | None = None) -> dict[str, Any]:
    """Load and cryptographically verify `config/governance/external_qrels_rubric_v1.json`."""
    resolved = (
        Path(rubric_path).resolve()
        if rubric_path is not None
        else (Path(__file__).resolve().parents[2] / DEFAULT_EXTERNAL_QRELS_RUBRIC_REL_PATH)
    )
    if not resolved.is_file():
        raise FileNotFoundError(f"External QRELS rubric not found: '{resolved}'.")
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("External QRELS rubric must be a JSON object.")
    if raw.get("rubric_id") != EXTERNAL_QRELS_RUBRIC_ID:
        raise ValueError(f"Unexpected QRELS rubric_id: {raw.get('rubric_id')!r}.")
    supplied = str(raw.get("rubric_sha256") or "")
    unsigned = {k: v for k, v in raw.items() if k != "rubric_sha256"}
    expected = canonical_json_sha256(unsigned)
    if supplied != expected:
        raise ValueError(
            f"External QRELS rubric SHA-256 mismatch: expected '{expected}', observed '{supplied}'."
        )
    if set(raw.get("grade_values") or []) != ALLOWED_QRELS_GRADES:
        raise ValueError("External QRELS rubric must declare exact grade_values [0, 1, 2, 3].")
    return raw


def validate_qrels_atomic_checks(raw: Mapping[str, Any] | None) -> dict[str, bool]:
    """Validate optional QRELS atomic binary checks mapping `{check_id: bool}`."""
    if not raw:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("atomic_checks must be a mapping of check_id -> bool.")
    out: dict[str, bool] = {}
    for key, val in raw.items():
        clean = str(key).strip()
        if clean not in QRELS_ATOMIC_CHECK_IDS:
            raise ValueError(
                f"Unknown QRELS atomic check {clean!r}; expected subset of {sorted(QRELS_ATOMIC_CHECK_IDS)}."
            )
        if not isinstance(val, bool):
            raise ValueError(f"QRELS atomic check '{clean}' must be bool, got {val!r}.")
        out[clean] = val
    return out


def validate_qrels_rejection_tags(raw: Sequence[str] | str | None) -> tuple[str, ...]:
    """Validate structured QRELS rejection taxonomy tags."""
    if not raw:
        return ()
    tokens = [
        t.strip().upper()
        for t in (raw.split(",") if isinstance(raw, str) else raw)
        if str(t).strip()
    ]
    unique: list[str] = []
    for tok in tokens:
        if tok not in VALID_QRELS_REJECTION_TAG_IDS:
            raise ValueError(
                f"Unknown QRELS rejection tag {tok!r}; expected subset of {sorted(VALID_QRELS_REJECTION_TAG_IDS)}."
            )
        if tok not in unique:
            unique.append(tok)
    return tuple(unique)


def enforce_qrels_grade_consistency(
    relevance_grade: int,
    *,
    atomic_checks: Mapping[str, bool] | None = None,
    rejection_tags: Sequence[str] = (),
    critique_rationale: str = "",
    require_grade0_rationale: bool = True,
) -> None:
    """Mechanically enforce QRELS grade-cap and Grade-0 rationale consistency rules."""
    if not isinstance(relevance_grade, int) or isinstance(relevance_grade, bool):
        raise ValueError(f"relevance_grade must be an integer in 0..3, got {relevance_grade!r}.")
    if relevance_grade not in ALLOWED_QRELS_GRADES:
        raise ValueError(f"relevance_grade must be in 0..3, got {relevance_grade}.")
    clean_checks = validate_qrels_atomic_checks(atomic_checks)
    clean_tags = validate_qrels_rejection_tags(rejection_tags)
    if relevance_grade >= 2:
        failed_caps = [cid for cid in QRELS_CAP_AT_1_CHECKS if clean_checks.get(cid) is False]
        if failed_caps:
            raise ValueError(
                f"Grade {relevance_grade} blocked by failed consistency check(s): {failed_caps}. "
                "Maximum permitted grade is 1."
            )
    if relevance_grade == 0 and require_grade0_rationale:
        if len(clean_tags) < 1 and len(str(critique_rationale or "").strip()) < 8:
            raise ValueError(
                "Grade 0 requires at least 1 rejection tag or a critique rationale (>= 8 chars)."
            )


def strip_blind_forbidden_fields(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow-sanitized copy with all rank, score, and channel provenance removed."""
    return {k: v for k, v in item.items() if k not in BLIND_FORBIDDEN_FIELDS}


def shuffle_qrels_pool_seeded(items: Sequence[Mapping[str, Any]], seed: int | None) -> list[dict[str, Any]]:
    """Deterministically shuffle blind QRELS items when a seed is provided."""
    ordered = [dict(it) for it in items]
    if seed is None:
        return ordered
    rng = random.Random(int(seed))
    rng.shuffle(ordered)
    return ordered


@dataclass(frozen=True)
class QrelsQuarantineDisposition:
    """Non-contaminating quarantine record for unanswerable/defective QRELS items."""

    pair_id: str
    query_id: str
    record_id: str
    surface: str
    topic_family: str
    partition: str
    artifact_sha256: str
    reason: str
    annotator_id: str
    recorded_at_utc: str
    notes: str = ""

    def __post_init__(self) -> None:
        if self.reason not in VALID_QRELS_QUARANTINE_REASONS:
            raise ValueError(
                f"Invalid quarantine reason {self.reason!r}; expected one of {sorted(VALID_QRELS_QUARANTINE_REASONS)}."
            )
        if not str(self.pair_id).strip() or not str(self.query_id).strip() or not str(self.record_id).strip():
            raise ValueError("pair_id, query_id, and record_id must be non-empty.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "ALLOWED_QRELS_GRADES",
    "BLIND_FORBIDDEN_FIELDS",
    "DEFAULT_EXTERNAL_QRELS_RUBRIC_REL_PATH",
    "EXTERNAL_QRELS_RUBRIC_ID",
    "QRELS_ATOMIC_CHECKS",
    "QRELS_ATOMIC_CHECK_IDS",
    "QRELS_CAP_AT_1_CHECKS",
    "QRELS_GRADE_ANCHORS",
    "QRELS_REJECTION_TAGS",
    "QrelsQuarantineDisposition",
    "VALID_QRELS_QUARANTINE_REASONS",
    "VALID_QRELS_REJECTION_TAG_IDS",
    "build_canonical_qrels_rubric_payload",
    "canonical_json_sha256",
    "enforce_qrels_grade_consistency",
    "load_and_verify_qrels_rubric",
    "normalize_display_dates",
    "shuffle_qrels_pool_seeded",
    "split_core_and_boilerplate",
    "strip_blind_forbidden_fields",
    "validate_qrels_atomic_checks",
    "validate_qrels_rejection_tags",
]
