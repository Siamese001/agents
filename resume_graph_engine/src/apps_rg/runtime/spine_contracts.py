"""App-owned contracts for the Apps RG execution spine.

These records are deliberately small, immutable boundary values.  Keeping the
types here makes the application self-contained: every stage can exchange the
same auditable payloads without resolving a package outside this repository.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping, Optional


ALLOWED_PROMPT_SLOT_C0_EVIDENCE_DATA_ONLY = "C0_EVIDENCE_DATA_ONLY"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
SUPPORT_STATUS_EMPTY = "EMPTY"
SUPPORT_STATUS_BLOCKED = "BLOCKED"
SUPPORT_STATUS_CONFLICTED = "CONFLICTED"
SUPPORT_STATUS_WEAK = "WEAK"
SUPPORT_STATUS_WEAK_WITH_CAVEATS = "WEAK_WITH_CAVEATS"
SUPPORT_STATUS_PASS = "PASS"
SUPPORT_STATUS_PARTIAL = "PARTIAL"
SUPPORT_STATUS_PASSING_VALUES = frozenset({SUPPORT_STATUS_PASS})
L3_RUNTIME_RECEIPT_SCHEMA_VERSION = "1.0"


class FrozenContractDict(dict[str, Any]):
    """A recursively frozen ``dict`` that remains readable as a normal mapping."""

    @staticmethod
    def _blocked(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("contract mapping is immutable")

    __setitem__ = _blocked
    __delitem__ = _blocked
    clear = _blocked
    pop = _blocked
    popitem = _blocked
    setdefault = _blocked
    update = _blocked
    __ior__ = _blocked


class FrozenContractList(list[Any]):
    """A recursively frozen ``list`` retained for backwards-compatible reads."""

    @staticmethod
    def _blocked(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("contract list is immutable")

    __setitem__ = _blocked
    __delitem__ = _blocked
    __iadd__ = _blocked
    __imul__ = _blocked
    append = _blocked
    clear = _blocked
    extend = _blocked
    insert = _blocked
    pop = _blocked
    remove = _blocked
    reverse = _blocked
    sort = _blocked


def _freeze_contract_value(value: Any) -> Any:
    if isinstance(value, FrozenContractDict | FrozenContractList):
        return value
    if isinstance(value, Mapping):
        return FrozenContractDict(
            {str(key): _freeze_contract_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return FrozenContractList(_freeze_contract_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_contract_value(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_freeze_contract_value(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class RuntimePosture:
    read_only: bool = True
    external_call: bool = False
    write_intent: bool = False
    hitl_required: bool = False
    posture_class: str = "read_only"


class Origin(str, Enum):
    USER_INTENT = "USER_INTENT"
    RETRIEVED_DATA = "RETRIEVED_DATA"
    TOOL_OUTPUT = "TOOL_OUTPUT"
    MODEL_GENERATION = "MODEL_GENERATION"
    HUMAN_REVIEW_DATA = "HUMAN_REVIEW_DATA"
    SYSTEM_INTERNAL = "SYSTEM_INTERNAL"


@dataclass(frozen=True, slots=True)
class AppsRgIngressPayload:
    app_id: str = "apps_rg"
    task_class: str = "resume_generation"
    target_company: Optional[str] = None
    target_role: Optional[str] = None
    target_level: Optional[str] = None
    source_resume_ref: Optional[str] = None
    source_resume_text: Optional[str] = None
    job_description_ref: Optional[str] = None
    job_description_text: Optional[str] = None
    candidate_profile_path: Optional[str] = None
    project_fact_refs: tuple[str, ...] = field(default_factory=tuple)
    briefing_artifact_ref: Optional[str] = None
    manual_brief_path: Optional[str] = None
    auto_research_internal: bool = False
    auto_research_tavily: bool = False
    research_via: Optional[str] = None
    user_constraints: Mapping[str, Any] = field(default_factory=dict)
    output_preferences: Mapping[str, Any] = field(default_factory=dict)
    profile_refs: Any = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    payload_digest: str = ""
    l5_certification_ref: Optional[str] = None


@dataclass(frozen=True, slots=True)
class RequestEnvelope:
    payload: AppsRgIngressPayload
    request_id: str = ""
    run_id: str = ""
    tenant_id: str = ""
    trace_id: str = ""
    submitted_at: str = ""
    replay_key: str = ""


@dataclass(frozen=True, slots=True)
class ValidatedRequest:
    request_id: str
    run_id: str
    app_id: str
    task_class: str
    payload_digest: str
    authority_validation_receipt: Any
    trace_id: str
    tenant_id: str = ""
    target_level: str = ""
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = "W6.0"
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_key: str = ""
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_ref: Optional[str] = None
    app_payload: Mapping[str, Any] = field(default_factory=dict)
    reflection_receipt: Any = None
    session_id: str = ""
    trace_root: str = ""
    caller_scope_baseline: str = ""


@dataclass(frozen=True, slots=True)
class PromptBlock:
    role: str
    content: str
    block_index: int = 0
    origin: Origin = Origin.SYSTEM_INTERNAL


@dataclass(frozen=True, slots=True)
class CompiledPromptArtifact:
    request_id: str
    run_id: str
    app_id: str
    trace_id: str
    prompt_blocks: tuple[PromptBlock, ...] = field(default_factory=tuple)
    system_preamble: str = ""
    user_instruction: str = ""
    assembly_timestamp: str = ""
    schema_version: str = "W6.0"
    target_model: str = ""
    target_provider: str = ""
    evidence_digest: str = ""
    compilation_hash: str = ""
    slot_lineage_map: Mapping[str, str] = field(default_factory=dict)
    component_hash_map: Mapping[str, str] = field(default_factory=dict)
    replay_manifest_ref: str = ""
    per_input_hash_map: Mapping[str, str] = field(default_factory=dict)
    tenant_id: str = ""
    sandbox_required: bool = False
    egress_policy_ref: str = ""
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    allowed_models: tuple[str, ...] = field(default_factory=tuple)
    allowed_networks: tuple[str, ...] = field(default_factory=tuple)
    allowed_file_roots: tuple[str, ...] = field(default_factory=tuple)
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_key: str = ""
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_ref: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    source: str
    content: str
    content_type: str = "text"
    retrieval_timestamp: str = ""
    confidence_score: float = 0.0
    origin: Origin = Origin.RETRIEVED_DATA
    evidence_id: str = ""
    source_id: str = ""
    source_type: str = ""
    source_version: str = ""
    source_uri_or_ref: str = ""
    source_owner_or_authority: str = ""
    retrieved_span: str = ""
    citation_anchor: str = ""
    chunk_digest: str = ""
    fact_vec_ref: str = ""
    dense_score: float = 0.0
    bm25_score: float = 0.0
    metadata_score: float = 0.0
    query_vec_ref: str = ""
    freshness_status: str = STATUS_UNKNOWN
    acl_status: str = STATUS_UNKNOWN
    origin_trust_label: str = ""
    authority_class: str = STATUS_UNKNOWN
    contradiction_status: str = STATUS_UNKNOWN
    stratum: str = ""
    allowed_prompt_slot: str = ALLOWED_PROMPT_SLOT_C0_EVIDENCE_DATA_ONLY
    support_score: float = 0.0
    support_status: str = STATUS_UNKNOWN
    retrieval_method: str = ""
    retrieval_run_ref: str = ""
    graph_ref: str = ""
    evidence_digest: str = ""
    unknown_reason: str = ""
    not_applicable_reason: str = ""


@dataclass(frozen=True, slots=True)
class FinalEvidenceContract:
    request_id: str
    run_id: str
    app_id: str
    trace_id: str
    evidence_items: tuple[EvidenceItem, ...] = field(default_factory=tuple)
    retrieval_sources: tuple[str, ...] = field(default_factory=tuple)
    support_target_met: bool = False
    support_target_partial: bool = False
    evidence_sufficiency_score: float = 0.0
    tenant_id: str = ""
    evidence_collection_timestamp: str = ""
    schema_version: str = "W6.0"
    compilation_hash: str = ""
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_key: str = ""
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_ref: str = ""
    route_contract_ref: str = ""
    retrieval_plan_ref: str = ""
    query_vec_ref: str = ""
    dense_search_refs: tuple[str, ...] = field(default_factory=tuple)
    sparse_search_refs: tuple[str, ...] = field(default_factory=tuple)
    metadata_filter_refs: tuple[str, ...] = field(default_factory=tuple)
    graph_expansion_refs: tuple[str, ...] = field(default_factory=tuple)
    evidence_strata: tuple[tuple[str, tuple[str, ...]], ...] = field(default_factory=tuple)
    citation_map: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    source_lineage_map: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    source_version_map: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    acl_verification_receipts: tuple[str, ...] = field(default_factory=tuple)
    freshness_receipts: tuple[str, ...] = field(default_factory=tuple)
    contradiction_report: str = ""
    support_status: str = STATUS_UNKNOWN
    support_score_profile: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    excluded_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    blocked_source_refs: tuple[str, ...] = field(default_factory=tuple)
    weak_support_refinement_attempts: tuple[str, ...] = field(default_factory=tuple)
    final_evidence_digest: str = ""
    unknown_reason: str = ""
    not_applicable_reason: str = ""

    @property
    def has_blocked_sources(self) -> bool:
        return bool(self.blocked_source_refs)

    @property
    def has_contradictions(self) -> bool:
        return bool(self.contradiction_report)

    @property
    def support_status_is_passing(self) -> bool:
        return self.support_status in SUPPORT_STATUS_PASSING_VALUES


@dataclass(frozen=True, slots=True)
class RouteGateReceipt:
    gate_id: str
    verdict: str
    score: float
    facts_present: bool
    adapter_kind: str = "TEMPORARY_THIN_ADAPTER"
    reason: str = ""

    def to_runtime_gate_ref(self) -> str:
        return f"{self.gate_id}:{self.verdict}:{self.score:.6f}"


@dataclass(frozen=True, slots=True)
class GraphTraversePolicy:
    graph_expansion_allowed: bool = False
    max_hops: int = 0
    max_nodes: int = 0
    max_edges: int = 0
    allowed_relation_types: tuple[str, ...] = field(default_factory=tuple)
    contradiction_scan_enabled: bool = False
    supersession_scan_enabled: bool = False
    graph_adapter_ref: str = ""
    live_wiring_deferred: bool = True
    wiring_gate: str = ""

    @property
    def is_active(self) -> bool:
        return self.graph_expansion_allowed and self.max_hops > 0 and self.max_nodes > 0


@dataclass(frozen=True, slots=True)
class RouteContract:
    request_id: str
    run_id: str
    app_id: str
    trace_id: str
    route_id: str
    l3_required: bool
    grounding_required: bool
    model_generation_required: bool
    write_authority_present: bool
    tenant_id: str = ""
    sandbox_required: bool = False
    egress_policy_ref: str = ""
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    allowed_models: tuple[str, ...] = field(default_factory=tuple)
    allowed_networks: tuple[str, ...] = field(default_factory=tuple)
    allowed_file_roots: tuple[str, ...] = field(default_factory=tuple)
    route_family: str = ""
    execution_form: str = ""
    cache_eligibility: Mapping[str, bool] = field(default_factory=dict)
    action_required: bool = False
    workflow_ref: str = ""
    workflow_manifest_ref: str = ""
    workflow_registry_ref: str = ""
    registry_resolution_receipt_ref: str = ""
    route_gate_refs: tuple[str, ...] = field(default_factory=tuple)
    route_gate_receipts: tuple[RouteGateReceipt, ...] = field(default_factory=tuple)
    allowed_next_stage: frozenset[str] = field(default_factory=frozenset)
    provider_model_requirement_ref: str = ""
    personalization_required: bool = False
    work_shape: str = ""
    task_shape: str = ""
    route_profile_ref: str = ""
    route_policy_ref: str = ""
    route_digest: str = ""
    hmac_sig: str = ""
    cache_lookup_r1a_receipt: str = ""
    cache_lookup_r1b_receipt: str = ""
    cache_lookup_r5_receipt: str = ""
    r1a_lookup_receipt_ref: str = ""
    r1b_lookup_receipt_ref: str = ""
    r5_fallback_receipt_ref: str = ""
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    routing_timestamp: str = ""
    schema_version: str = "W6.0"
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_key: str = ""
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_ref: str = ""
    graph_traverse_policy: Optional[GraphTraversePolicy] = None
    apps_research_call_required: bool = False

    @property
    def route_version(self) -> str:
        return self.schema_version


@dataclass(frozen=True, slots=True)
class L1PlanContract:
    request_id: str
    run_id: str
    app_id: str
    trace_id: str
    task_plan: tuple[str, ...] = field(default_factory=tuple)
    required_capabilities: tuple[str, ...] = field(default_factory=tuple)
    grounding_required: bool = False
    apps_research_call_required: bool = False
    model_generation_required: bool = False
    write_authority_present: bool = False
    tenant_id: str = ""
    profile_manifest_digest: str = ""
    target_level: str = ""
    task_spec: Mapping[str, Any] = field(default_factory=dict)
    query_spec: Mapping[str, Any] = field(default_factory=dict)
    support_expectation: Mapping[str, Any] = field(default_factory=dict)
    output_expectation: Mapping[str, Any] = field(default_factory=dict)
    policy_refs: Mapping[str, str] = field(default_factory=dict)
    multiple_work_units_hint: bool = False
    merge_required_hint: bool = False
    per_unit_quality_selection_hint: bool = False
    candidate_generation_expected_hint: bool = False
    planning_timestamp: str = ""
    schema_version: str = "W6.0"
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_key: str = ""
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_ref: str = ""
    non_authority_assertion: Mapping[str, bool] = field(default_factory=dict)
    planning_prior_refs: tuple[str, ...] = field(default_factory=tuple)
    route_hints: Mapping[str, str] = field(default_factory=dict)
    work_shape: str = ""
    task_shape: str = ""
    route_profile_ref: str = ""
    prompt_bom_refs: tuple[str, ...] = field(default_factory=tuple)
    judge_eval_expectation_refs: tuple[str, ...] = field(default_factory=tuple)
    validation_receipt_id: str = ""
    ambiguity_register: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "task_spec",
            "query_spec",
            "support_expectation",
            "output_expectation",
            "policy_refs",
            "non_authority_assertion",
            "route_hints",
            "ambiguity_register",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_contract_value(getattr(self, field_name)),
            )

        task_spec = self.task_spec
        capsule = task_spec.get("apps_rg_planning_capsule")
        if capsule is not None:
            from apps_rg.runtime.bindings.l1_planning_capsule import (
                verify_apps_rg_l1_planning_capsule,
            )

            verify_apps_rg_l1_planning_capsule(
                capsule,
                expected_capsule_digest=str(
                    task_spec.get("apps_rg_planning_capsule_ref") or ""
                ),
            )


@dataclass(frozen=True)
class L3StepContractRef:
    step_id: str
    node_id: str
    run_id: str
    status: str
    handed_to_l2_at_utc: str = ""
    skipped_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class L3RuntimeOrchestrationReceipt:
    run_id: str
    request_id: str
    trace_root: str
    route_contract_id: str
    route_id: str
    dag_id: str
    dag_sha256: str
    selected_node_ids: tuple[str, ...]
    step_contracts: tuple[L3StepContractRef, ...]
    l3_required: bool = True
    l3_no_execute_assertion: bool = True
    l3_no_retrieve_assertion: bool = True
    l3_no_prompt_assembly_assertion: bool = True
    l3_no_l4_write_assertion: bool = True
    schema_version: str = L3_RUNTIME_RECEIPT_SCHEMA_VERSION
    deterministic_digest: str = ""
    static_dag_ref: str = ""
    tenant_id: str = ""
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_key: str = ""
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [_json_ready(item) for item in value]
    return value


def compute_l3_runtime_digest(payload: Mapping[str, Any] | L3RuntimeOrchestrationReceipt) -> str:
    """Return a stable digest for an application-owned L3 receipt."""

    serializable = payload.to_dict() if isinstance(payload, L3RuntimeOrchestrationReceipt) else _json_ready(payload)
    encoded = json.dumps(serializable, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class L3ToL2StepContract:
    contract_id: str = ""
    route_contract_ref: str = ""
    workflow_ref: str = ""
    workflow_manifest_ref: str = ""
    workflow_id: str = ""
    node_id: str = ""
    node_type: str = ""
    node_attempt: int = 1
    parent_node_refs: tuple[str, ...] = field(default_factory=tuple)
    dependency_refs: tuple[str, ...] = field(default_factory=tuple)
    branch_join_state: str = ""
    checkpoint_ref: str = ""
    workflow_ledger_ref: str = ""
    step_input_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    carried_prompt_refs: tuple[str, ...] = field(default_factory=tuple)
    capability_token: str = ""
    sandbox_envelope: str = ""
    side_effect_class: str = "none"
    allowed_execution_lane: str = "ENSEMBLE_MODEL"
    tool_allowlist: tuple[str, ...] = field(default_factory=tuple)
    model_allowlist: tuple[str, ...] = field(default_factory=tuple)
    provider_allowlist: tuple[str, ...] = field(default_factory=tuple)
    filesystem_scope: str = ""
    network_scope: str = ""
    credential_scope: str = ""
    budget: str = ""
    retry_policy: str = ""
    heal_policy_ref: str = ""
    exit_condition: str = ""
    replay_key: str = ""
    run_id: str = ""
    trace_root: str = ""
    step_handoff_receipt: str = ""
    provider_profile_ref: str = ""
    candidate_count: int = 3
    prompt_profile_ref: str = ""
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    output_schema_ref: str = ""
    prompt_artifact_ref: str = ""
    prompt_artifact_digest: str = ""
    prompt_bom_ref: str = ""
    prompt_registry_ref: str = ""
    section_prompt_ref: str = ""
    authority_order: tuple[str, ...] = field(default_factory=tuple)
    pa_is_valid: bool = True
    pa_failure_reason: str = ""
    runtime_gate_refs: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = "W7.a3f7e2"

    def as_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    AUTO_INJECTED = "auto_injected"
    EXPLICIT = "explicit"


@dataclass(frozen=True)
class RuntimeCustomizationPackage:
    package_id: str
    package_version: str = "1.0.0"
    app_id: str = ""
    task_class: str = ""
    package_ref: str = ""
    package_digest: str = ""
    profile_refs: dict[str, str] = field(default_factory=dict)
    policy_hash: str = ""
    blueprint_hash: str = ""
    registry_digest_set: list[str] = field(default_factory=list)
    package_origin: str = "unknown"
    auto_injected_runtime_package: bool = False
    auto_injection_reason: str = ""
    auto_injection_receipt_ref: str = ""
    validation_status: str = STATUS_UNKNOWN.lower()
    validation_errors: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.package_digest:
            object.__setattr__(self, "package_digest", self._compute_digest())

    def _compute_digest(self) -> str:
        payload = {
            "package_id": self.package_id,
            "package_version": self.package_version,
            "app_id": self.app_id,
            "task_class": self.task_class,
            "package_ref": self.package_ref,
            "profile_refs": self.profile_refs,
            "policy_hash": self.policy_hash,
            "blueprint_hash": self.blueprint_hash,
            "extra": self.extra,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return sha256(encoded.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuntimeCustomizationPackage":
        known = {field_name for field_name in cls.__dataclass_fields__}
        payload = {key: item for key, item in value.items() if key in known}
        unknown = sorted(set(value) - known)
        if unknown:
            payload["extra"] = {**dict(payload.get("extra", {})), **{key: value[key] for key in unknown}}
        return cls(**payload)

    def validate_schema(
        self, schema: Mapping[str, Any] | None = None
    ) -> tuple[bool, list[str]]:
        errors = list(self.validation_errors)
        if not self.package_id:
            errors.append("package_id is required")
        if not self.app_id:
            errors.append("app_id is required")
        if not self.task_class:
            errors.append("task_class is required")
        if schema:
            allowed_fields = set(schema.get("allowed_fields") or ())
            required_fields = set(schema.get("required_fields") or ())
            errors.extend(
                f"Unknown field in extra: {field_name}"
                for field_name in self.extra
                if field_name not in allowed_fields
            )
            errors.extend(
                f"Required field missing in extra: {field_name}"
                for field_name in required_fields
                if field_name not in self.extra
            )
        return not errors, errors


@dataclass(frozen=True)
class PackageValidationReceipt:
    package_id: str
    package_version: str
    task_class: str
    validation_passed: bool
    unknown_fields_found: list[str]
    digest_verified: bool
    timestamp_iso: str
    schema_version: str = "AG9.U0.PKG.1"


@dataclass(frozen=True, slots=True)
class SealedL2Artifact:
    request_id: str
    run_id: str
    app_id: str
    trace_id: str
    execution_status: str
    generated_content: str = ""
    generated_content_origin: Origin = Origin.MODEL_GENERATION
    proposed_state_diff: Mapping[str, Any] = field(default_factory=dict)
    state_diff_authorized: bool = False
    execution_timestamp: str = ""
    execution_duration_ms: int = 0
    sovereign_execution_receipt: str = ""
    tenant_id: str = ""
    sandbox_required: bool = False
    egress_policy_ref: str = ""
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    allowed_models: tuple[str, ...] = field(default_factory=tuple)
    allowed_networks: tuple[str, ...] = field(default_factory=tuple)
    allowed_file_roots: tuple[str, ...] = field(default_factory=tuple)
    prompt_artifact_digest: str = ""
    schema_version: str = "W6.0"
    compilation_hash: str = ""
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_key: str = ""
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    is_uwg_write_authority: bool = False
    is_future_run_only: bool = False
    l5_certification_ref: str = ""
    l5_certification_packet_ref: str = ""
    l5_certification_packet_digest: str = ""
    l5_certification_status: str = ""
    l5_certification_packet: Any | None = None
    l5_runtime_binding_digest: str = ""
    l5_prompt_artifact_digest: str = ""
    l5_evidence_contract_digest: str = ""
    l5_certification_verified: bool = False
    l5_certification_verification_digest: str = ""
    l5_egress_receipt_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_egress_receipt_digests: tuple[str, ...] = field(default_factory=tuple)
    l5_egress_receipts: tuple[Any, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    prompt_refs: tuple[str, ...] = field(default_factory=tuple)
    tool_call_refs: tuple[str, ...] = field(default_factory=tuple)
    model_call_refs: tuple[str, ...] = field(default_factory=tuple)
    provider_receipts: tuple[str, ...] = field(default_factory=tuple)
    replay_manifest: str = ""
    audit_manifest_ref: str = ""


@dataclass(frozen=True, slots=True)
class X3Disposition:
    request_id: str
    run_id: str
    app_id: str
    trace_id: str
    exit_status: str
    outcome_authorized: bool = False
    final_output: Mapping[str, Any] = field(default_factory=dict)
    output_artifact_path: Optional[str] = None
    eval_score: Optional[float] = None
    eval_threshold_met: bool = False
    hitl_required: bool = False
    tenant_id: str = ""
    exit_timestamp: str = ""
    schema_version: str = "W6.0"
    sealed_l2_digest: str = ""
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_key: str = ""
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    is_uwg_write_authority: bool = False
    is_future_run_only: bool = False
    l5_certification_ref: str = ""


class _TraceNamespace:
    def __getattr__(self, name: str) -> str:
        return name


class _LifecycleTraceContract:
    """Minimal local trace namespace retained for validator compatibility."""

    LayerSegment = _TraceNamespace()

    def __getattr__(self, _name: str) -> Any:
        return lambda *args, **kwargs: None


lifecycle_trace_contract = _LifecycleTraceContract()


__all__ = [
    "ALLOWED_PROMPT_SLOT_C0_EVIDENCE_DATA_ONLY",
    "AppsRgIngressPayload",
    "CompiledPromptArtifact",
    "EvidenceItem",
    "FinalEvidenceContract",
    "GraphTraversePolicy",
    "L1PlanContract",
    "L3_RUNTIME_RECEIPT_SCHEMA_VERSION",
    "L3RuntimeOrchestrationReceipt",
    "L3StepContractRef",
    "L3ToL2StepContract",
    "Origin",
    "PackageValidationReceipt",
    "PromptBlock",
    "RequestEnvelope",
    "RouteContract",
    "RouteGateReceipt",
    "RuntimeCustomizationPackage",
    "RuntimePosture",
    "STATUS_NOT_APPLICABLE",
    "STATUS_UNKNOWN",
    "SUPPORT_STATUS_BLOCKED",
    "SUPPORT_STATUS_CONFLICTED",
    "SUPPORT_STATUS_EMPTY",
    "SUPPORT_STATUS_PARTIAL",
    "SUPPORT_STATUS_PASS",
    "SUPPORT_STATUS_PASSING_VALUES",
    "SUPPORT_STATUS_WEAK",
    "SUPPORT_STATUS_WEAK_WITH_CAVEATS",
    "SealedL2Artifact",
    "ValidatedRequest",
    "X3Disposition",
    "compute_l3_runtime_digest",
    "lifecycle_trace_contract",
]
