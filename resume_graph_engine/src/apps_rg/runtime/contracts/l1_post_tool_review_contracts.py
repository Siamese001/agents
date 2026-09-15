"""Data contracts and schemas for L1 post-tool execution review.

This module defines the typed contracts returned by the L1 review step
after L2 completes tool execution and seals its observation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Final, Literal, Mapping

L1_POST_TOOL_REVIEW_SCHEMA_VERSION: Final[str] = "apps_rg.l1_post_tool_review.v1"
L1_DETERMINISTIC_CHECK_SCHEMA_VERSION: Final[str] = "apps_rg.l1_deterministic_check.v1"
L1_SEMANTIC_REVIEW_SCHEMA_VERSION: Final[str] = "apps_rg.l1_semantic_review.v1"


class L1ReviewVerdict(str, Enum):
    """Authoritative disposition from L1 post-L2 review."""

    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT_RETRY = "INSUFFICIENT_RETRY"
    INSUFFICIENT_REPLAN = "INSUFFICIENT_REPLAN"
    TERMINAL_FAIL = "TERMINAL_FAIL"

    @property
    def is_sufficient(self) -> bool:
        return self == L1ReviewVerdict.SUFFICIENT

    @property
    def requires_replan(self) -> bool:
        return self == L1ReviewVerdict.INSUFFICIENT_REPLAN

    @property
    def requires_retry(self) -> bool:
        return self == L1ReviewVerdict.INSUFFICIENT_RETRY


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(value: Any) -> str:
    raw = _canonical_json(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class L1DeterministicCheckResult:
    """Outcome of objective, deterministic checks on the sealed L2 observation."""

    schema_version: str = L1_DETERMINISTIC_CHECK_SCHEMA_VERSION
    status: Literal["PASS", "FAIL"] = "PASS"
    tool_execution_success: bool = True
    schema_valid: bool = True
    required_fields_present: bool = True
    missing_fields: tuple[str, ...] = ()
    missing_evidence_ids: tuple[str, ...] = ()
    checked_assertions: Mapping[str, bool] = field(default_factory=dict)
    failure_reasons: tuple[str, ...] = ()
    check_digest: str = ""

    def __post_init__(self) -> None:
        if not self.check_digest:
            body = {
                "schema_version": self.schema_version,
                "status": self.status,
                "tool_execution_success": self.tool_execution_success,
                "schema_valid": self.schema_valid,
                "required_fields_present": self.required_fields_present,
                "missing_fields": self.missing_fields,
                "missing_evidence_ids": self.missing_evidence_ids,
                "checked_assertions": dict(self.checked_assertions),
                "failure_reasons": self.failure_reasons,
            }
            object.__setattr__(self, "check_digest", sha256_hex(body))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "tool_execution_success": self.tool_execution_success,
            "schema_valid": self.schema_valid,
            "required_fields_present": self.required_fields_present,
            "missing_fields": list(self.missing_fields),
            "missing_evidence_ids": list(self.missing_evidence_ids),
            "checked_assertions": dict(self.checked_assertions),
            "failure_reasons": list(self.failure_reasons),
            "check_digest": self.check_digest,
        }


@dataclass(frozen=True, slots=True)
class L1SemanticReviewResult:
    """Outcome of semantic reasoning over original intent, plan, and sealed observation."""

    schema_version: str = L1_SEMANTIC_REVIEW_SCHEMA_VERSION
    status: Literal["PASS", "INSUFFICIENT", "SKIPPED"] = "PASS"
    subgoal_accomplished: bool = True
    evidence_sufficient: bool = True
    plan_adaptation_required: bool = False
    critique: str = ""
    recommended_action: str = "PROCEED_TO_EXIT"
    suggested_strategy_delta: Mapping[str, Any] = field(default_factory=dict)
    review_digest: str = ""

    def __post_init__(self) -> None:
        if not self.review_digest:
            body = {
                "schema_version": self.schema_version,
                "status": self.status,
                "subgoal_accomplished": self.subgoal_accomplished,
                "evidence_sufficient": self.evidence_sufficient,
                "plan_adaptation_required": self.plan_adaptation_required,
                "critique": self.critique,
                "recommended_action": self.recommended_action,
                "suggested_strategy_delta": dict(self.suggested_strategy_delta),
            }
            object.__setattr__(self, "review_digest", sha256_hex(body))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class L1PostToolReviewContract:
    """Typed review contract emitted by L1 review before exit gating."""

    request_id: str
    run_id: str
    trace_id: str
    parent_l1_plan_ref: str
    sealed_l2_artifact_ref: str
    verdict: L1ReviewVerdict
    deterministic_checks: L1DeterministicCheckResult
    semantic_review: L1SemanticReviewResult
    review_cycle: int = 1
    review_timestamp: str = ""
    schema_version: str = L1_POST_TOOL_REVIEW_SCHEMA_VERSION
    review_contract_digest: str = ""

    def __post_init__(self) -> None:
        if not self.review_contract_digest:
            body = {
                "schema_version": self.schema_version,
                "request_id": self.request_id,
                "run_id": self.run_id,
                "trace_id": self.trace_id,
                "review_cycle": self.review_cycle,
                "parent_l1_plan_ref": self.parent_l1_plan_ref,
                "sealed_l2_artifact_ref": self.sealed_l2_artifact_ref,
                "verdict": self.verdict.value if isinstance(self.verdict, L1ReviewVerdict) else str(self.verdict),
                "deterministic_check_digest": self.deterministic_checks.check_digest,
                "semantic_review_digest": self.semantic_review.review_digest,
            }
            object.__setattr__(self, "review_contract_digest", sha256_hex(body))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "review_cycle": self.review_cycle,
            "parent_l1_plan_ref": self.parent_l1_plan_ref,
            "sealed_l2_artifact_ref": self.sealed_l2_artifact_ref,
            "verdict": self.verdict.value if isinstance(self.verdict, L1ReviewVerdict) else str(self.verdict),
            "deterministic_checks": self.deterministic_checks.as_dict(),
            "semantic_review": self.semantic_review.as_dict(),
            "review_timestamp": self.review_timestamp,
            "review_contract_digest": self.review_contract_digest,
        }


__all__ = [
    "L1_DETERMINISTIC_CHECK_SCHEMA_VERSION",
    "L1_POST_TOOL_REVIEW_SCHEMA_VERSION",
    "L1_SEMANTIC_REVIEW_SCHEMA_VERSION",
    "L1DeterministicCheckResult",
    "L1PostToolReviewContract",
    "L1ReviewVerdict",
    "L1SemanticReviewResult",
    "sha256_hex",
]
