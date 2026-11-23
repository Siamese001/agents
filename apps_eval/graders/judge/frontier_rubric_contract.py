"""2025-2026 Frontier Atomic Rubric Checks, Failure Taxonomy, Evidence Excerpts & Quarantine (DIE Parity).

Implements 2025-2026 Anthropic (Demystifying Evals for AI Agents), Google Cloud /
DeepMind (Adaptive Rubrics & grounding_v2), and OpenAI (HealthBench 2025)
human-calibration controls on top of `external_judge_rubric_v1`:
1. Six atomic binary checks (`ATOMIC_RUBRIC_CHECKS`) + mechanical `pass_rule` lock.
2. Six structured failure-mode tags (`FAILURE_TAXONOMY_TAGS`) + critique-before-FAIL gate.
3. Non-contaminating `QuarantineDisposition` (`ABSTAIN_INSUFFICIENT_EVIDENCE`, `DEFECTIVE_PROMPT`).
4. Sanitized source-evidence excerpt extraction and seeded order randomization.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence

ATOMIC_RUBRIC_CHECKS: tuple[dict[str, Any], ...] = (
    {
        "id": "unsupported_claim_absent",
        "pillar": "factual_faithfulness",
        "critical_for_pass": True,
        "label": "No unsupported claim or invented date/metric",
    },
    {
        "id": "source_contradiction_absent",
        "pillar": "factual_faithfulness",
        "critical_for_pass": True,
        "label": "Zero contradictions against retrieved source evidence",
    },
    {
        "id": "core_question_fully_answered",
        "pillar": "completeness_and_relevance",
        "critical_for_pass": False,
        "label": "Directly answers the core question asked",
    },
    {
        "id": "scope_constraints_covered",
        "pillar": "completeness_and_relevance",
        "critical_for_pass": False,
        "label": "Covers requested constraints, risks, or dependencies",
    },
    {
        "id": "cold_reader_jargon_free",
        "pillar": "cold_reader_clarity",
        "critical_for_pass": False,
        "label": "Clear to a cold reader without insider shorthand or AI filler",
    },
    {
        "id": "concrete_owner_and_next_step",
        "pillar": "actionability_and_proportion",
        "critical_for_pass": False,
        "label": "Actionable takeaway with clear ownership and channel proportion",
    },
)

ATOMIC_CHECK_IDS: frozenset[str] = frozenset(c["id"] for c in ATOMIC_RUBRIC_CHECKS)
CRITICAL_FAITHFULNESS_CHECKS: tuple[str, ...] = (
    "unsupported_claim_absent",
    "source_contradiction_absent",
)

FAILURE_TAXONOMY_TAGS: tuple[dict[str, str], ...] = (
    {"id": "HALLUCINATED_FACT", "label": "Hallucinated fact / invented date or metric"},
    {"id": "UNSUPPORTED_EXTRAPOLATION", "label": "Extrapolates tentative claim as confirmed"},
    {"id": "OMITTED_CONSTRAINT", "label": "Misses core question part or key constraint"},
    {"id": "OPAQUE_SHORTHAND", "label": "Opaque insider shorthand / unexplained acronym"},
    {"id": "AI_FILLER_VOICE", "label": "Robotic boilerplate or artificial AI voice"},
    {"id": "UNACTIONABLE_TAKEAWAY", "label": "Vague unowned next step or bloated density"},
)

VALID_FAILURE_TAG_IDS: frozenset[str] = frozenset(t["id"] for t in FAILURE_TAXONOMY_TAGS)
VALID_QUARANTINE_REASONS: frozenset[str] = frozenset(
    {"ABSTAIN_INSUFFICIENT_EVIDENCE", "DEFECTIVE_PROMPT"}
)


def validate_atomic_checks(raw: Mapping[str, Any] | None) -> dict[str, bool]:
    """Validate optional atomic binary checks mapping `{check_id: bool}`."""
    if not raw:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("atomic_checks must be a mapping of check_id -> bool.")
    out: dict[str, bool] = {}
    for key, val in raw.items():
        clean_k = str(key).strip()
        if clean_k not in ATOMIC_CHECK_IDS:
            raise ValueError(f"Unknown atomic check id {clean_k!r}; expected subset of {sorted(ATOMIC_CHECK_IDS)}.")
        if not isinstance(val, bool):
            raise ValueError(f"Atomic check '{clean_k}' value must be a boolean, got {val!r}.")
        out[clean_k] = val
    return out


def validate_failure_tags(raw: Sequence[str] | str | None) -> tuple[str, ...]:
    """Validate structured failure-mode taxonomy tags."""
    if not raw:
        return ()
    tokens = [t.strip().upper() for t in (raw.split(",") if isinstance(raw, str) else raw) if str(t).strip()]
    unique: list[str] = []
    for tok in tokens:
        if tok not in VALID_FAILURE_TAG_IDS:
            raise ValueError(f"Unknown failure tag {tok!r}; expected subset of {sorted(VALID_FAILURE_TAG_IDS)}.")
        if tok not in unique:
            unique.append(tok)
    return tuple(unique)


def _enforce_pass_rules(
    dimension_grades: Mapping[str, int],
    atomic_checks: Mapping[str, bool] | None,
) -> None:
    if int(dimension_grades.get("factual_faithfulness", 0)) < 4:
        raise ValueError("PASS requires factual_faithfulness >= 4 under external_judge_rubric_v1 pass_rule.")
    below_three = [k for k, v in dimension_grades.items() if int(v) < 3]
    if below_three:
        raise ValueError(f"PASS requires all dimensions >= 3; below floor: {sorted(below_three)}.")
    if atomic_checks:
        failed_crit = [k for k in CRITICAL_FAITHFULNESS_CHECKS if atomic_checks.get(k) is False]
        if failed_crit:
            raise ValueError(f"PASS blocked by failed critical faithfulness atomic check(s): {failed_crit}.")


def enforce_pass_rule_and_critique(
    dimension_grades: Mapping[str, int],
    human_verdict: str,
    *,
    atomic_checks: Mapping[str, bool] | None = None,
    failure_tags: Sequence[str] = (),
    critique_rationale: str = "",
    require_fail_critique: bool = False,
) -> None:
    """Mechanically enforce external rubric `pass_rule` and critique-before-FAIL provenance."""
    verdict = str(human_verdict or "").strip().upper()
    if verdict == "PASS":
        _enforce_pass_rules(dimension_grades, atomic_checks)
        return
    if verdict == "FAIL" and (require_fail_critique or bool(atomic_checks)):
        if len(failure_tags) < 1 and len(str(critique_rationale or "").strip()) < 8:
            raise ValueError(
                "FAIL requires >= 1 structured failure_tags entry or a critique_rationale (>= 8 chars)."
            )


@dataclass(frozen=True)
class QuarantineDisposition:
    """Non-contaminating quarantine record for abstained or defective blind pool items."""

    case_id: str
    judge_surface: str
    topic_family: str
    partition: str
    artifact_sha256: str
    reason: str
    annotator_id: str
    recorded_at_utc: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> QuarantineDisposition:
        from apps_eval.graders.judge.external_rubric_store import (
            VALID_JUDGE_SURFACES,
            VALID_PARTITIONS,
            _require_non_empty_field,
            _validate_membership,
            _validate_sha256_hex,
            validate_human_annotator_id,
        )

        if not isinstance(raw, Mapping):
            raise ValueError("Quarantine record must be a mapping.")
        case_id = _require_non_empty_field(raw, "case_id", 1)
        surface = _validate_membership(str(raw.get("judge_surface") or "").strip(), VALID_JUDGE_SURFACES, "judge_surface")
        topic = _require_non_empty_field(raw, "topic_family", 2).lower()
        partition = _validate_membership(str(raw.get("partition") or "").strip(), VALID_PARTITIONS, "partition")
        art_sha = _validate_sha256_hex(str(raw.get("artifact_sha256") or ""), "artifact_sha256")
        reason = _validate_membership(str(raw.get("reason") or "").strip().upper(), VALID_QUARANTINE_REASONS, "reason")
        annotator = validate_human_annotator_id(str(raw.get("annotator_id") or ""))
        recorded_at = _require_non_empty_field(raw, "recorded_at_utc", 10)
        return cls(
            case_id=case_id,
            judge_surface=surface,
            topic_family=topic,
            partition=partition,
            artifact_sha256=art_sha,
            reason=reason,
            annotator_id=annotator,
            recorded_at_utc=recorded_at,
            notes=str(raw.get("notes") or "").strip(),
        )


def extract_sanitized_evidence_excerpts(
    raw_excerpts: Any,
    sanitizer_fn: Callable[[str], str] | None = None,
    max_excerpts: int = 8,
) -> tuple[list[dict[str, str]], str]:
    """Normalize and sanitize source evidence excerpts plus compute SHA-256 digest."""
    if not isinstance(raw_excerpts, (list, tuple)):
        return [], ""
    clean_fn = sanitizer_fn if sanitizer_fn is not None else (lambda s: s)
    cleaned: list[dict[str, str]] = []
    for item in list(raw_excerpts)[:max_excerpts]:
        if isinstance(item, Mapping):
            src = clean_fn(str(item.get("source") or item.get("source_label") or "Graph Evidence")).strip()
            txt = clean_fn(str(item.get("excerpt") or item.get("text") or item.get("claim") or "")).strip()
            date_s = clean_fn(str(item.get("date") or "")).strip()
        else:
            raw_s = clean_fn(str(item or "")).strip()
            if ":" in raw_s and len(raw_s.split(":", 1)[0]) <= 64:
                head, tail = raw_s.split(":", 1)
                src, date_s, txt = head.strip(), "", tail.strip()
            else:
                src, date_s, txt = "Verified Source Fact", "", raw_s
        if txt:
            cleaned.append({"source": src[:140], "date": date_s[:32], "excerpt": txt[:480]})
    if not cleaned:
        return [], ""
    encoded = json.dumps(cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return cleaned, hashlib.sha256(encoded).hexdigest()


def shuffle_pool_items_seeded(items: Sequence[dict[str, Any]], seed: int | None) -> list[dict[str, Any]]:
    """Deterministically shuffle blind pool items when `seed` is supplied to neutralize order bias."""
    copied = [dict(it) for it in items]
    if seed is not None and len(copied) > 1:
        rng = random.Random(int(seed))
        rng.shuffle(copied)
    return copied


__all__ = [
    "ATOMIC_CHECK_IDS",
    "ATOMIC_RUBRIC_CHECKS",
    "CRITICAL_FAITHFULNESS_CHECKS",
    "FAILURE_TAXONOMY_TAGS",
    "QuarantineDisposition",
    "VALID_FAILURE_TAG_IDS",
    "VALID_QUARANTINE_REASONS",
    "enforce_pass_rule_and_critique",
    "extract_sanitized_evidence_excerpts",
    "shuffle_pool_items_seeded",
    "validate_atomic_checks",
    "validate_failure_tags",
]
