"""Allocation contracts, invariants, plan validation, and usage-ledger builders."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from apps_rg.runtime.c0.c03_resume_graph_contracts import (
    ALLOCATION_PLAN_SCHEMA_VERSION,
    USAGE_LEDGER_SCHEMA_VERSION,
    stable_digest,
)
from apps_rg.runtime.contracts.metric_lexical_primitives import (
    DIGIT_LETTER_RE as _DIGIT_LETTER_RE,
    EXACT_METRIC_PATTERNS as _EXACT_METRIC_PATTERNS,
    METRIC_EQUIVALENTS as _METRIC_EQUIVALENTS,
    WORD_RE as _WORD_RE,
    extract_exact_metric_value_unit,
    normalize_metric_signature,
)

WHOLE_RESUME_SCOPE = "WHOLE_RESUME"
SECTION_ONLY_SCOPE = "SECTION_ONLY"
ALLOCATION_SCOPES = frozenset({WHOLE_RESUME_SCOPE, SECTION_ONLY_SCOPE})
ALLOCATION_PLAN_ENV = "APPS_RG_RESUME_GRAPH_ALLOCATION_PLAN"
ALLOCATION_USAGE_LEDGER_ENV = "APPS_RG_RESUME_GRAPH_USAGE_LEDGER"
SECTION_EVIDENCE_CONTRACTS_ENV = "APPS_RG_SECTION_FINAL_GRAPH_EVIDENCE_CONTRACTS"
# Exact C0.3 source plans frozen before lane execution. A whole-resume lane
# consumes this snapshot; it never reruns graph selection after allocation.
SECTION_SOURCE_PLANS_ENV = "APPS_RG_SECTION_GRAPH_SOURCE_PLANS"
DEFAULT_MAX_CANDIDATES_PER_SLOT = 256

_ALLOCATION_DIGEST_EXCLUDED_KEYS = frozenset(
    {
        "allocation_plan_id",
        "allocation_plan_digest",
        "prior_seal",
        "prior_seals",
        "downstream_receipt",
        "downstream_receipts",
    }
)

CANONICAL_BULLET_CLAIM_UNITS: Mapping[str, tuple[str, ...]] = {
    "slalom_bullets": tuple(f"bul_slalom_{index:03d}" for index in range(1, 5)),
    "unify_bullets": tuple(f"bul_unify_{index:03d}" for index in range(1, 7)),
    "ibm_bullets": tuple(f"bul_ibm_{index:03d}" for index in range(1, 6)),
    "insurtech_bullets": ("bul_insurtech_001", "bul_insurtech_002", "bul_insurtech_003"),
    "ey_bullets": ("bul_ey_001", "bul_ey_002", "bul_ey_003"),
    "early_career_bullets": ("bul_early_career_001", "bul_early_career_002", "bul_early_career_003"),
}
EMPLOYER_LANE_BY_SECTION: Mapping[str, str] = {
    "slalom_bullets": "slalom",
    "unify_bullets": "unify",
    "ibm_bullets": "ibm",
    "insurtech_bullets": "insurtech",
    "ey_bullets": "ey",
    "early_career_bullets": "early_career",
}
NARRATIVE_DERIVATION_POLICY: Mapping[str, str] = {
    "slalom_narrative": "slalom_bullets",
    "unify_narrative": "unify_bullets",
    "ibm_narrative": "ibm_bullets",
    "insurtech_narrative": "insurtech_bullets",
    "ey_narrative": "ey_bullets",
    "early_career_narrative": "early_career_bullets",
}
CANONICAL_VISIBLE_SECTIONS: tuple[str, ...] = (
    "competencies",
    "slalom_bullets",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "ey_bullets",
    "early_career_bullets",
    "executive_summary",
    "headline",
)
LEGACY_CLAIM_BEARING_SECTIONS: tuple[str, ...] = (
    "competencies",
    "slalom_bullets",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "ey_bullets",
    "slalom_narrative",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
    "ey_narrative",
    "executive_summary",
    "headline",
)
ALL_CLAIM_BEARING_SECTIONS: tuple[str, ...] = (
    "competencies",
    "slalom_bullets",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "ey_bullets",
    "early_career_bullets",
    "slalom_narrative",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
    "ey_narrative",
    "early_career_narrative",
    "executive_summary",
    "headline",
)


class ResumeGraphAllocationError(RuntimeError):
    """Fail-closed allocation error with a machine-readable constraint receipt."""

    def __init__(self, message: str, *, receipt: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.receipt = dict(receipt)


@dataclass(frozen=True, slots=True)
class _Slot:
    slot_id: str
    section_id: str
    metric_required: bool
    metric_outcome_required: bool
    employer_lane: str
    required_root_id: str
    counts_toward_global_uniqueness: bool
    allowed_employer_lanes: tuple[str, ...] = ()


def stable_edge_id(source: str, edge_type: str, target: str) -> str:
    """Return deterministic edge identifier from source, edge_type, and target."""
    payload = {"source": str(source), "edge_type": str(edge_type), "target": str(target)}
    return f"edge:{stable_digest(payload)[:24]}"


def _strings(values: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _slot_from_row(row: Mapping[str, Any]) -> _Slot:
    slot_id = str(row.get("slot_id") or row.get("claim_unit_id") or "").strip()
    section_id = str(row.get("section_id") or "").strip()
    if not slot_id or not section_id:
        raise ValueError("every allocation slot requires slot_id and section_id")
    allowed_lanes = tuple(_strings(row.get("allowed_employer_lanes")))
    return _Slot(
        slot_id=slot_id,
        section_id=section_id,
        metric_required=bool(row.get("metric_required")),
        metric_outcome_required=bool(row.get("metric_outcome_required")),
        employer_lane=str(row.get("employer_lane") or "").strip(),
        required_root_id=str(row.get("required_root_id") or "").strip(),
        counts_toward_global_uniqueness=bool(
            row.get("counts_toward_global_uniqueness", True)
        ),
        allowed_employer_lanes=allowed_lanes,
    )


def _candidate_identity(row: Mapping[str, Any], *, slot: _Slot) -> str:
    explicit = str(row.get("candidate_id") or "").strip()
    if explicit:
        return explicit
    return "cand:" + stable_digest(
        {
            "slot_id": slot.slot_id,
            "skill_id": row.get("skill_id"),
            "fact_id": row.get("fact_id"),
            "metric_outcome_id": row.get("metric_outcome_id"),
            "graph_path_ids": row.get("graph_path_ids"),
        }
    )[:24]


def _constraint_receipt(
    *,
    slots: Sequence[_Slot],
    eligible_by_slot: Mapping[str, Sequence[Mapping[str, Any]]],
    reason: str,
) -> dict[str, Any]:
    empty = [slot.slot_id for slot in slots if not eligible_by_slot.get(slot.slot_id)]
    return {
        "schema_version": "resume_graph_allocation_failure_v1",
        "reason": reason,
        "unsatisfied_constraints": [
            "authority_and_complete_path_candidate_per_slot" if empty else "global_uniqueness",
            *(["empty_eligible_slots:" + ",".join(empty)] if empty else []),
        ],
        "slot_count": len(slots),
        "eligible_candidate_count_by_slot": {
            slot.slot_id: len(eligible_by_slot.get(slot.slot_id) or ()) for slot in slots
        },
    }


def _validate_assignment_uniqueness(assignments: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    visible = [row for row in assignments if row.get("counts_toward_global_uniqueness") is True]
    skill_counts = Counter(str(row.get("skill_id") or "") for row in visible)
    metric_counts = Counter(
        str(row.get("metric_outcome_id") or "")
        for row in visible
        if str(row.get("metric_outcome_id") or "")
    )
    signature_counts = Counter(
        str(row.get("normalized_metric_signature") or "")
        for row in visible
        if str(row.get("normalized_metric_signature") or "")
    )
    fingerprint_counts = Counter(
        str(tok)
        for row in visible
        for tok in (row.get("metric_fingerprint_tokens") or ())
        if str(tok).strip()
    )
    repeated_skills = sorted(key for key, count in skill_counts.items() if key and count > 1)
    repeated_metrics = sorted(key for key, count in metric_counts.items() if count > 1)
    repeated_signatures = sorted(key for key, count in signature_counts.items() if count > 1)
    repeated_fingerprints = sorted(key for key, count in fingerprint_counts.items() if count > 1)
    return {
        "schema_version": "resume_graph_uniqueness_receipt_v1",
        "visible_assignment_count": len(visible),
        "repeated_skill_ids": repeated_skills,
        "repeated_metric_outcome_ids": repeated_metrics,
        "repeated_normalized_metric_signatures": repeated_signatures,
        "repeated_metric_fingerprint_tokens": repeated_fingerprints,
        "pass": (
            not repeated_skills
            and not repeated_metrics
            and not repeated_signatures
            and not repeated_fingerprints
        ),
    }


def _allocation_digest_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _allocation_digest_value(item)
            for key, item in value.items()
            if key not in _ALLOCATION_DIGEST_EXCLUDED_KEYS
            and not (
                key.startswith("prior_")
                and key.endswith(("_seal", "_digest", "_receipt"))
            )
            and not (
                key.startswith("downstream_")
                and key.endswith(("_seal", "_digest", "_receipt"))
            )
        }
    if isinstance(value, (list, tuple)):
        return [_allocation_digest_value(item) for item in value]
    return value


def _plan_digest_payload(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the one canonical allocation digest domain.

    Prior seals and downstream receipts may be nested by later consumers. They
    are evidence about the allocation, not allocation inputs, so they cannot
    change the immutable plan identity.
    """
    return _allocation_digest_value(plan)


def canonical_allocation_digest(plan: Mapping[str, Any]) -> str:
    """Compute canonical SHA-256 digest over allocation plan inputs."""
    return stable_digest(_plan_digest_payload(plan))


def validate_resume_graph_allocation_plan(plan: Mapping[str, Any]) -> list[str]:
    """Validate structural invariants, uniqueness, and digest seal on an allocation plan."""
    failures: list[str] = []
    if str(plan.get("schema_version") or "") != ALLOCATION_PLAN_SCHEMA_VERSION:
        failures.append("schema_version")
    if str(plan.get("allocation_scope") or "") not in ALLOCATION_SCOPES:
        failures.append("allocation_scope")
    assignments = plan.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        failures.append("assignments")
        assignments = []
    if len({str(row.get("claim_unit_id") or "") for row in assignments if isinstance(row, Mapping)}) != len(assignments):
        failures.append("claim_unit_assignment_uniqueness")
    uniqueness = _validate_assignment_uniqueness(
        [row for row in assignments if isinstance(row, Mapping)]
    )
    if uniqueness["pass"] is not True:
        failures.append("resource_uniqueness")
    if plan.get("uniqueness_receipt") != uniqueness:
        failures.append("uniqueness_receipt")
    expected_digest = canonical_allocation_digest(plan)
    if str(plan.get("allocation_plan_digest") or "") != expected_digest:
        failures.append("allocation_plan_digest")
    if str(plan.get("allocation_scope")) == SECTION_ONLY_SCOPE and plan.get(
        "global_uniqueness_claimed"
    ) is not False:
        failures.append("section_only_global_uniqueness_claim")
    return failures


def finalize_resume_graph_allocation_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute derived receipts and seal one immutable allocation digest."""
    out = dict(plan)
    out.pop("allocation_plan_id", None)
    out.pop("allocation_plan_digest", None)
    assignments = [
        dict(row) for row in out.get("assignments") or [] if isinstance(row, Mapping)
    ]
    assignments.sort(
        key=lambda row: (
            str(row.get("section_id") or ""),
            str(row.get("claim_unit_id") or ""),
            str(row.get("candidate_id") or ""),
        )
    )
    out["assignments"] = assignments
    out["uniqueness_receipt"] = _validate_assignment_uniqueness(assignments)
    digest = canonical_allocation_digest(out)
    out["allocation_plan_digest"] = digest
    out["allocation_plan_id"] = f"resume_graph_allocation:{digest[:20]}"
    failures = validate_resume_graph_allocation_plan(out)
    if failures:
        raise ValueError("invalid allocation plan: " + ", ".join(failures))
    return out


def build_resume_graph_usage_ledger(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Construct immutable current-run usage ledger from a sealed allocation plan."""
    failures = validate_resume_graph_allocation_plan(plan)
    if failures:
        raise ValueError("cannot build usage ledger from invalid allocation plan: " + ", ".join(failures))
    reservations: list[dict[str, Any]] = []
    for assignment in plan.get("assignments") or []:
        if not isinstance(assignment, Mapping):
            continue
        base = {
            "section_id": str(assignment.get("section_id") or ""),
            "claim_unit_id": str(assignment.get("claim_unit_id") or ""),
            "counts_toward_global_uniqueness": bool(
                assignment.get("counts_toward_global_uniqueness")
            ),
        }
        for resource_type, key in (
            ("skill_id", "skill_id"),
            ("fact_id", "fact_id"),
            ("source_family", "source_family"),
            ("metric_outcome_id", "metric_outcome_id"),
            ("normalized_metric_signature", "normalized_metric_signature"),
        ):
            resource_id = str(assignment.get(key) or "").strip()
            if resource_id:
                reservations.append(
                    {**base, "resource_type": resource_type, "resource_id": resource_id}
                )
    reservations.sort(
        key=lambda row: (
            row["resource_type"],
            row["resource_id"],
            row["section_id"],
            row["claim_unit_id"],
        )
    )
    ledger: dict[str, Any] = {
        "schema_version": USAGE_LEDGER_SCHEMA_VERSION,
        "allocation_plan_digest": str(plan.get("allocation_plan_digest") or ""),
        "allocation_scope": str(plan.get("allocation_scope") or ""),
        "current_run_only": True,
        "durable_graph_state_mutated": False,
        "reservations": reservations,
        "reservation_count": len(reservations),
    }
    ledger["usage_ledger_digest"] = stable_digest(ledger)
    return ledger


def load_resume_graph_allocation_plan(path: Path) -> dict[str, Any]:
    """Load and validate an allocation plan JSON artifact from disk."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResumeGraphAllocationError(
            "allocation plan is missing or invalid",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["allocation_plan_load"],
                "path": str(path),
            },
        ) from exc
    if not isinstance(raw, dict):
        raise ResumeGraphAllocationError(
            "allocation plan must be a JSON object",
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["allocation_plan_shape"],
                "path": str(path),
            },
        )
    failures = validate_resume_graph_allocation_plan(raw)
    if failures:
        raise ResumeGraphAllocationError(
            "allocation plan validation failed: " + ", ".join(failures),
            receipt={
                "schema_version": "resume_graph_allocation_failure_v1",
                "unsatisfied_constraints": ["allocation_plan_validation"],
                "validation_failures": failures,
                "path": str(path),
            },
        )
    return raw
