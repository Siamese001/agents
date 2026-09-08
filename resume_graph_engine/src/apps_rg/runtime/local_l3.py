"""Apps RG-owned L3 scheduling records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WorkflowNodeType(str, Enum):
    L2_MODEL_STEP = "L2_MODEL_STEP"


@dataclass(frozen=True, slots=True)
class StepInputs:
    query_refs: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    graph_refs: tuple[str, ...] = field(default_factory=tuple)
    prompt_artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    prior_artifact_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class L3StepContract:
    step_contract_id: str
    workflow_id: str
    node_id: str
    attempt_id: str
    parent_route_id: str
    route_digest: str
    policy_hash: str
    blueprint_hash: str
    snapshot_id: str
    replay_key: str
    idempotency_key: str
    node_type: WorkflowNodeType
    current_work_order: str
    inputs: StepInputs
    expected_output_contract: str
    capability_token_requirement: str
    sandbox_envelope_requirement: str
    timeout_ms: int
    retry_policy: str
    fallback_permission: str
    telemetry_keys: tuple[str, ...] = field(default_factory=tuple)
    expected_receipts: tuple[str, ...] = field(default_factory=tuple)
    step_contract_hash: str = ""
    no_durable_commit_authority: bool = True
    l5_certification_ref: str = ""


@dataclass(frozen=True, slots=True)
class L3ContextBus:
    workflow_id: str
    bus_hash: str
    carried_query_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_graph_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_prompt_artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_l2_artifact_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_human_review_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_policy_receipt_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_error_refs: tuple[str, ...] = field(default_factory=tuple)
    contradiction_flags: tuple[str, ...] = field(default_factory=tuple)
    unresolved_gaps: tuple[str, ...] = field(default_factory=tuple)
    lineage_manifest: str = ""


__all__ = ["L3ContextBus", "L3StepContract", "StepInputs", "WorkflowNodeType"]
