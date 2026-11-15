"""Deterministic whole-sequence C0 fact-slot allocator and plan generation.

Enforces INV-LIC-C0-DISJOINT-TOUCH-FACTS across multi-touch outreach sequences.
Never imports sqlite3 or os.environ directly (delegates to infrastructure.candidate_evidence).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from infrastructure.candidate_evidence.contracts import (
    CandidateFactChunk,
    CustodyCheckReport,
    HybridCandidatePool,
    extract_metric_tokens,
)
from infrastructure.types.metric_lexical_primitives import (
    normalize_dollar_token,
)

C0_ALLOCATION_PLAN_SCHEMA_VERSION = "apps_lic.c0_sequence_allocation.v1"
INV_LIC_C0_DISJOINT_TOUCH_FACTS = "INV-LIC-C0-DISJOINT-TOUCH-FACTS"


class SequenceAllocationError(ValueError):
    """Raised when sequence fact slot allocation fails closed."""


@dataclass(frozen=True, slots=True)
class TouchSlotSpec:
    """Specification of an outreach touch slot within a sequence."""

    touch_number: int
    channel: str = "email"
    objective: str = ""
    strategic_priority: str = ""
    preferred_angle: str = "strategic_value"
    metric_required: bool = True
    required_fact_id: str = ""
    max_facts: int = 1


@dataclass(frozen=True, slots=True)
class TouchAllocationAssignment:
    """Deterministic allocation assignment for a single touch in a sequence."""

    touch_number: int
    channel: str
    allocated_fact_ids: tuple[str, ...]
    allocated_facts: tuple[CandidateFactChunk, ...]
    allocated_metric_tokens: tuple[str, ...]
    strategic_priority: str
    touch_angle: str
    selection_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize touch allocation assignment to a JSON-compatible dictionary."""
        return {
            "touch_number": self.touch_number,
            "channel": self.channel,
            "allocated_fact_ids": list(self.allocated_fact_ids),
            "allocated_facts": [f.to_dict() for f in self.allocated_facts],
            "allocated_metric_tokens": list(self.allocated_metric_tokens),
            "strategic_priority": self.strategic_priority,
            "touch_angle": self.touch_angle,
            "selection_score": round(float(self.selection_score), 6),
        }


@dataclass(frozen=True, slots=True)
class OutreachSequenceAllocationPlan:
    """Canonical frozen sequence fact-slot allocation plan."""

    opportunity_id: str
    candidate_id: str
    candidate_graph_db_sha256: str
    allocation_scope: str
    assignments: tuple[TouchAllocationAssignment, ...]
    allocated_fact_ids_by_touch: Mapping[int, tuple[str, ...]]
    reserve_repair_pool_fact_ids: tuple[str, ...]
    reserve_repair_pool_facts: tuple[CandidateFactChunk, ...]
    touch_angle_assignments: Mapping[int, str]
    uniqueness_receipt: Mapping[str, Any]
    allocation_plan_digest: str = ""
    schema_version: str = C0_ALLOCATION_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.allocation_plan_digest:
            payload = {
                "schema_version": self.schema_version,
                "opportunity_id": self.opportunity_id,
                "candidate_id": self.candidate_id,
                "candidate_graph_db_sha256": self.candidate_graph_db_sha256,
                "allocation_scope": self.allocation_scope,
                "allocated_fact_ids_by_touch": {
                    str(k): list(v) for k, v in sorted(self.allocated_fact_ids_by_touch.items())
                },
                "reserve_repair_pool_fact_ids": list(self.reserve_repair_pool_fact_ids),
                "touch_angle_assignments": {
                    str(k): v for k, v in sorted(self.touch_angle_assignments.items())
                },
                "uniqueness_receipt": dict(self.uniqueness_receipt),
            }
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            object.__setattr__(self, "allocation_plan_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        """Serialize sequence allocation plan to a JSON-compatible dictionary."""
        return {
            "schema_version": self.schema_version,
            "opportunity_id": self.opportunity_id,
            "candidate_id": self.candidate_id,
            "candidate_graph_db_sha256": self.candidate_graph_db_sha256,
            "allocation_scope": self.allocation_scope,
            "allocation_plan_digest": self.allocation_plan_digest,
            "assignments": [a.to_dict() for a in self.assignments],
            "allocated_fact_ids_by_touch": {
                int(k): list(v) for k, v in self.allocated_fact_ids_by_touch.items()
            },
            "reserve_repair_pool_fact_ids": list(self.reserve_repair_pool_fact_ids),
            "reserve_repair_pool_facts": [f.to_dict() for f in self.reserve_repair_pool_facts],
            "touch_angle_assignments": {
                int(k): v for k, v in self.touch_angle_assignments.items()
            },
            "uniqueness_receipt": dict(self.uniqueness_receipt),
        }


def normalize_metric_token(raw_tok: str) -> str:
    """Normalize numeric/metric tokens to prevent false distinctness across formats."""
    norm = str(raw_tok or "").strip().lower()
    if norm.startswith("$") or "usd" in norm:
        return normalize_dollar_token(norm)
    return norm.replace(",", "").strip()


def validate_disjoint_allocation(
    assignments: Sequence[TouchAllocationAssignment],
    reserve_fact_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Verify zero duplicate fact_id or primary metric token across touches and reserve pool."""
    all_facts: list[str] = []
    all_metrics: list[str] = []
    touch_facts: dict[int, list[str]] = {}
    touch_metrics: dict[int, list[str]] = {}

    for a in assignments:
        touch_facts[a.touch_number] = list(a.allocated_fact_ids)
        touch_metrics[a.touch_number] = [normalize_metric_token(m) for m in a.allocated_metric_tokens if m]
        all_facts.extend(a.allocated_fact_ids)
        all_metrics.extend([normalize_metric_token(m) for m in a.allocated_metric_tokens if m])

    fact_counts = Counter(all_facts)
    repeated_facts = sorted(k for k, v in fact_counts.items() if v > 1)

    metric_counts = Counter(all_metrics)
    repeated_metrics = sorted(k for k, v in metric_counts.items() if v > 1)

    reserve_overlap = sorted(set(all_facts) & set(reserve_fact_ids))

    passed = not repeated_facts and not repeated_metrics and not reserve_overlap
    return {
        "schema_version": "apps_lic.uniqueness_receipt.v1",
        "passed": passed,
        "invariant": INV_LIC_C0_DISJOINT_TOUCH_FACTS,
        "touch_count": len(assignments),
        "repeated_fact_ids": repeated_facts,
        "repeated_metric_tokens": repeated_metrics,
        "reserve_pool_overlap": reserve_overlap,
    }


def compute_allocation_plan_digest(plan_dict: Mapping[str, Any]) -> str:
    """Compute canonical SHA-256 digest over sorted sequence allocation data."""
    payload = {
        "schema_version": str(plan_dict.get("schema_version") or C0_ALLOCATION_PLAN_SCHEMA_VERSION),
        "opportunity_id": str(plan_dict.get("opportunity_id") or ""),
        "candidate_id": str(plan_dict.get("candidate_id") or ""),
        "candidate_graph_db_sha256": str(plan_dict.get("candidate_graph_db_sha256") or ""),
        "allocation_scope": str(plan_dict.get("allocation_scope") or ""),
        "allocated_fact_ids_by_touch": {
            str(k): list(v) for k, v in sorted(dict(plan_dict.get("allocated_fact_ids_by_touch") or {}).items())
        },
        "reserve_repair_pool_fact_ids": sorted(str(x) for x in (plan_dict.get("reserve_repair_pool_fact_ids") or ())),
        "touch_angle_assignments": {
            str(k): str(v) for k, v in sorted(dict(plan_dict.get("touch_angle_assignments") or {}).items())
        },
        "uniqueness_receipt": dict(plan_dict.get("uniqueness_receipt") or {}),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def solve_sequence_allocation(
    candidate_pool: HybridCandidatePool | Sequence[CandidateFactChunk],
    touch_specs: Sequence[TouchSlotSpec],
    *,
    opportunity_id: str = "opp_default",
    candidate_id: str = "cand_default",
    candidate_graph_db_sha256: str = "",
    min_reserve_count: int = 1,
) -> OutreachSequenceAllocationPlan:
    """Deterministically solve mutually disjoint fact_id and metric slots across Touch 1..N.

    Fails closed if insufficient facts are available or collisions occur.
    """
    if isinstance(candidate_pool, HybridCandidatePool):
        pool_sha256 = candidate_pool.candidate_graph_db_sha256
        chunks = list(candidate_pool.chunks)
    else:
        pool_sha256 = candidate_graph_db_sha256 or "sha256:hermetic_test_fixture"
        chunks = list(candidate_pool)

    # Sort candidates deterministically: highest final score, then fact_id
    chunks.sort(key=lambda c: (-float(c.final_score), c.fact_id))

    needed_slots = len(touch_specs)
    total_needed = needed_slots + min_reserve_count
    if len(chunks) < total_needed:
        raise SequenceAllocationError(
            f"Insufficient candidate facts ({len(chunks)}) to satisfy {needed_slots} touches "
            f"plus {min_reserve_count} reserve facts under {INV_LIC_C0_DISJOINT_TOUCH_FACTS}."
        )

    used_fact_ids: set[str] = set()
    used_metric_tokens: set[str] = set()
    assignments: list[TouchAllocationAssignment] = []
    angle_assignments: dict[int, str] = {}
    facts_by_touch: dict[int, tuple[str, ...]] = {}

    default_angles = [
        "strategic_value_hook",
        "specific_proof_momentum",
        "low_friction_reciprocity",
        "quarterly_checkin_optionality",
    ]

    for idx, spec in enumerate(touch_specs):
        chosen_chunk: CandidateFactChunk | None = None
        for chunk in chunks:
            if chunk.fact_id in used_fact_ids:
                continue
            chunk_metrics = {
                normalize_metric_token(m) for m in chunk.metric_tokens if m
            }
            if chunk_metrics & used_metric_tokens:
                continue
            if spec.required_fact_id and chunk.fact_id != spec.required_fact_id:
                continue
            if spec.metric_required and not chunk.metric_tokens:
                continue

            chosen_chunk = chunk
            break

        if chosen_chunk is None:
            # Fallback search if metric wasn't strictly mandatory or relaxed
            for chunk in chunks:
                if chunk.fact_id in used_fact_ids:
                    continue
                chunk_metrics = {
                    normalize_metric_token(m) for m in chunk.metric_tokens if m
                }
                if chunk_metrics & used_metric_tokens:
                    continue
                chosen_chunk = chunk
                break

        if chosen_chunk is None:
            raise SequenceAllocationError(
                f"Failed to allocate disjoint candidate fact for touch {spec.touch_number} "
                f"under {INV_LIC_C0_DISJOINT_TOUCH_FACTS}."
            )

        used_fact_ids.add(chosen_chunk.fact_id)
        for m in chosen_chunk.metric_tokens:
            if m:
                used_metric_tokens.add(normalize_metric_token(m))

        touch_angle = spec.preferred_angle or (
            default_angles[idx] if idx < len(default_angles) else f"touch_{spec.touch_number}_angle"
        )
        angle_assignments[spec.touch_number] = touch_angle
        facts_by_touch[spec.touch_number] = (chosen_chunk.fact_id,)

        assignments.append(
            TouchAllocationAssignment(
                touch_number=spec.touch_number,
                channel=spec.channel,
                allocated_fact_ids=(chosen_chunk.fact_id,),
                allocated_facts=(chosen_chunk,),
                allocated_metric_tokens=chosen_chunk.metric_tokens,
                strategic_priority=spec.strategic_priority,
                touch_angle=touch_angle,
                selection_score=float(chosen_chunk.final_score),
            )
        )

    # Reserve repair pool for inline X1C / X3A repairs
    reserve_chunks: list[CandidateFactChunk] = []
    reserve_ids: list[str] = []
    for chunk in chunks:
        if chunk.fact_id not in used_fact_ids:
            chunk_metrics = {
                normalize_metric_token(m) for m in chunk.metric_tokens if m
            }
            if not (chunk_metrics & used_metric_tokens):
                reserve_chunks.append(chunk)
                reserve_ids.append(chunk.fact_id)
                used_fact_ids.add(chunk.fact_id)
                for m in chunk.metric_tokens:
                    if m:
                        used_metric_tokens.add(normalize_metric_token(m))

    uniqueness_receipt = validate_disjoint_allocation(assignments, reserve_ids)
    if not uniqueness_receipt["passed"]:
        raise SequenceAllocationError(
            f"Allocation uniqueness validation failed: {uniqueness_receipt}"
        )

    return OutreachSequenceAllocationPlan(
        opportunity_id=opportunity_id,
        candidate_id=candidate_id,
        candidate_graph_db_sha256=pool_sha256,
        allocation_scope="MULTI_TOUCH_SEQUENCE",
        assignments=tuple(assignments),
        allocated_fact_ids_by_touch=facts_by_touch,
        reserve_repair_pool_fact_ids=tuple(reserve_ids),
        reserve_repair_pool_facts=tuple(reserve_chunks),
        touch_angle_assignments=angle_assignments,
        uniqueness_receipt=uniqueness_receipt,
    )
