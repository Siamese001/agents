"""Closed-schema canonical contracts for the automated eval harness, flywheel, and auto-apply loop.

Zero sqlite3 imports are permitted in apps_eval. All contracts are pure frozen dataclasses
with closed-key deserialization and RFC-8259 canonical SHA-256 digests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping

from apps_eval.contracts.digests import canonical_sha256, stable_id, verify_canonical_digest

EXTENDED_EVAL_APPS: frozenset[str] = frozenset(
    {"apps_rg", "apps_lic", "apps_research", "agents_core", "agents_cli", "antigravity_turn"}
)

GroundingTier = Literal[
    "LIVE_CORPUS_GROUNDED",
    "OFFLINE_BENCHMARK_GROUNDED",
    "SYNTHETIC_SANDBOX_SMOKE_ONLY",
]
ExecutionModeV2 = Literal["snapshot", "cassette_replay", "live_authorized"]
EvalSplit = Literal["development", "holdout", "pinned_regression"]
TrackName = Literal["TRACK_1_CALIBRATION", "TRACK_2_CODE_FIX"]
PriorityLevel = Literal["P0", "P1", "P2"]
FindingStatus = Literal[
    "OPEN",
    "APPROVED",
    "IN_PROGRESS",
    "VERIFIED",
    "REJECTED",
    "SNOOZED",
    "ARCHIVED",
]
AutonomyTier = Literal["TIER_A_AUTO_APPLY", "TIER_B_HITL_GATED", "TIER_C_PR_ONLY"]
RiskLaneName = Literal["LANE_0", "LANE_1", "LANE_2"]
ArtifactClass = Literal[
    "repair_hint",
    "trajectory_exemplar",
    "bounded_threshold",
    "routing_weight",
    "prompt_prior",
    "regression_case_pin",
    "prompt_template",
    "validator_or_code",
    "governance_or_schema",
]

CONTRACT_RUN_TRACE = "urn:agents:eval:run-trace:1.0.0"
CONTRACT_EVAL_CASE = "urn:agents:eval:eval-case:1.0.0"
CONTRACT_EVAL_RECEIPT = "urn:agents:eval:eval-receipt:1.0.0"
CONTRACT_EVAL_COMPARISON = "urn:agents:eval:eval-comparison:1.0.0"
CONTRACT_STRESS_RESULT = "urn:agents:eval:stress-result:1.0.0"
CONTRACT_FINDING_RECORD = "urn:agents:learning:finding-record:1.0.0"
CONTRACT_FAILURE_CLUSTER = "urn:agents:learning:failure-cluster:1.0.0"
CONTRACT_IMPROVEMENT_PROPOSAL = "urn:agents:learning:improvement-proposal:1.0.0"
CONTRACT_HOLDOUT_VERDICT = "urn:agents:learning:holdout-replay-verdict:1.0.0"
CONTRACT_APPLIED_CHANGE = "urn:agents:learning:applied-change-receipt:1.0.0"


def utc_now_iso() -> str:
    """Return canonical ISO-8601 UTC timestamp with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_extra_keys(data: Mapping[str, Any], allowed: set[str], cls_name: str) -> None:
    extra = sorted(set(data.keys()) - allowed)
    if extra:
        raise ValueError(f"{cls_name} rejects unknown schema keys (additionalProperties=false): {extra}")


@dataclass(frozen=True)
class RunTrace:
    """Canonical post-runtime trace emitted by any agent or domain pipeline exit seam."""

    trace_id: str
    app_id: str
    run_id: str
    session_id: str
    git_sha: str
    config_digest: str
    started_at_utc: str
    finished_at_utc: str
    terminal_status: Literal["PASS", "FAIL", "BLOCKED", "TIMEOUT", "ERROR"]
    input_redacted: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    trajectory_steps: list[dict[str, Any]] = field(default_factory=list)
    gate_outcomes: dict[str, Any] = field(default_factory=dict)
    telemetry: dict[str, Any] = field(default_factory=dict)
    user_feedback: dict[str, Any] = field(default_factory=dict)
    contract_id: str = CONTRACT_RUN_TRACE
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if self.app_id not in EXTENDED_EVAL_APPS:
            raise ValueError(f"Unsupported app_id in RunTrace: {self.app_id}")
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def verify_digest(self) -> bool:
        return verify_canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RunTrace:
        allowed = set(cls.__dataclass_fields__.keys())
        _reject_extra_keys(data, allowed, cls.__name__)
        return cls(**dict(data))


@dataclass(frozen=True)
class EvalCase:
    """Canonical evaluation case with strict label-isolation unlabeled_view."""

    case_id: str
    suite_id: str
    app_id: str
    split: EvalSplit
    execution_mode: ExecutionModeV2
    source_kind: Literal[
        "curated",
        "online_eval_failure",
        "hitl_override",
        "operator_correction",
        "bug_fix_pin",
    ]
    grounding_tier: GroundingTier
    unlabeled_input: dict[str, Any]
    expected_contract: dict[str, Any]
    locked_split: bool = False
    source_trace_id: str | None = None
    watch_prefixes: list[str] = field(default_factory=list)
    created_at_utc: str = field(default_factory=utc_now_iso)
    contract_id: str = CONTRACT_EVAL_CASE
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if self.app_id not in EXTENDED_EVAL_APPS:
            raise ValueError(f"Unsupported app_id in EvalCase: {self.app_id}")
        if not self.case_id:
            cid = stable_id(
                "case",
                self.source_kind,
                self.app_id,
                self.suite_id,
                self.unlabeled_input,
                length=20,
            )
            object.__setattr__(self, "case_id", cid)
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    @property
    def unlabeled_view(self) -> dict[str, Any]:
        """Expose strictly unlabeled inputs to prevent ground-truth label leakage."""
        return {
            "case_id": self.case_id,
            "suite_id": self.suite_id,
            "app_id": self.app_id,
            "execution_mode": self.execution_mode,
            "unlabeled_input": dict(self.unlabeled_input),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def verify_digest(self) -> bool:
        return verify_canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvalCase:
        allowed = set(cls.__dataclass_fields__.keys())
        _reject_extra_keys(data, allowed, cls.__name__)
        return cls(**dict(data))


@dataclass(frozen=True)
class EvalReceipt:
    """Sealed evaluation receipt binding deterministic Tier-1 and blind Tier-2 results."""

    receipt_id: str
    suite_id: str
    suite_digest: str
    rubric_version: str
    pipeline_version: str
    git_sha: str
    execution_mode: ExecutionModeV2
    grounding_tier: GroundingTier
    deterministic_tier1: dict[str, Any]
    blind_judge_tier2: dict[str, Any]
    case_results: list[dict[str, Any]]
    pareto_point: dict[str, Any]
    non_compensating_regressions: list[str]
    verdict: Literal["PASS", "FAIL", "BLOCKED", "HITL_ESCALATE"]
    evaluated_at_utc: str = field(default_factory=utc_now_iso)
    contract_id: str = CONTRACT_EVAL_RECEIPT
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def verify_digest(self) -> bool:
        return verify_canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvalReceipt:
        allowed = set(cls.__dataclass_fields__.keys())
        _reject_extra_keys(data, allowed, cls.__name__)
        return cls(**dict(data))


@dataclass(frozen=True)
class EvalComparison:
    """Non-compensating comparison between baseline and candidate EvalReceipts."""

    suite_id: str
    baseline_receipt_id: str
    candidate_receipt_id: str
    comparable: bool
    incomparability_reasons: list[str]
    case_regressions: list[str]
    case_improvements: list[str]
    pass_rate_delta: float
    latency_delta_ms: float
    cost_delta_usd: float
    verdict: Literal["PASS", "FAIL", "NOT_COMPARABLE"]
    compared_at_utc: str = field(default_factory=utc_now_iso)
    contract_id: str = CONTRACT_EVAL_COMPARISON
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StressResult:
    """Multi-trial repeatability stress receipt checking behavior signature stability."""

    suite_id: str
    repetitions: int
    unique_behavior_signatures: list[str]
    pass_rate_by_trial: list[float]
    all_workspaces_cleaned: bool
    seed_state_unchanged: bool
    verdict: Literal["PASS", "FAIL"]
    failure_reasons: list[str]
    evaluated_at_utc: str = field(default_factory=utc_now_iso)
    contract_id: str = CONTRACT_STRESS_RESULT
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FindingRecord:
    """Normalized, fingerprinted remediation finding in the canonical findings queue."""

    finding_id: str
    fingerprint_sha256: str
    source_surface: str
    app_id: str
    failed_gate_signature: str
    root_cause_bucket: str
    owner_subsystem: str
    track: TrackName
    priority: PriorityLevel
    status: FindingStatus
    title: str
    summary: str
    recommended_action: str
    occurrence_count: int
    impact_score: float
    target_files: list[str] = field(default_factory=list)
    sample_trace_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    first_seen_utc: str = field(default_factory=utc_now_iso)
    last_seen_utc: str = field(default_factory=utc_now_iso)
    snoozed_until_utc: str | None = None
    hitl_decision_id: str | None = None
    contract_id: str = CONTRACT_FINDING_RECORD
    finding_digest: str = ""

    def __post_init__(self) -> None:
        if not self.finding_digest:
            core = {
                "finding_id": self.finding_id,
                "fingerprint_sha256": self.fingerprint_sha256,
                "source_surface": self.source_surface,
                "failed_gate_signature": self.failed_gate_signature,
                "root_cause_bucket": self.root_cause_bucket,
                "track": self.track,
                "priority": self.priority,
                "title": self.title,
                "recommended_action": self.recommended_action,
                "target_files": sorted(set(self.target_files)),
            }
            object.__setattr__(self, "finding_digest", canonical_sha256(core))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FailureCluster:
    """Aggregated root-cause failure cluster feeding golden promotion and proposals."""

    cluster_id: str
    root_cause_bucket: str
    owner_subsystem: str
    member_finding_ids: list[str]
    unique_run_ids: list[str]
    unique_session_count: int
    max_priority: PriorityLevel
    aggregate_impact_score: float
    conflict_detected: bool
    eligible_for_golden_promotion: bool
    eligible_for_proposal_synthesis: bool
    recommended_track: TrackName
    computed_at_utc: str = field(default_factory=utc_now_iso)
    contract_id: str = CONTRACT_FAILURE_CLUSTER
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImprovementProposal:
    """Governed candidate improvement synthesized from a FailureCluster."""

    proposal_id: str
    cluster_id: str
    artifact_class: ArtifactClass
    autonomy_tier: AutonomyTier
    risk_lane: RiskLaneName
    target_path: str
    target_key: str | None
    expected_current_value: Any
    proposed_value_or_patch: Any
    step_delta_magnitude: float
    evidence_trace_ids: list[str]
    source_receipt_digests: list[str]
    provenance_digest: str
    evaluation_plan: list[str]
    status: Literal[
        "PROPOSED",
        "SIMULATED_PASS",
        "SIMULATED_FAIL",
        "APPROVED",
        "APPLIED",
        "ROLLED_BACK",
        "REJECTED",
    ]
    expires_at_utc: str
    created_at_utc: str = field(default_factory=utc_now_iso)
    contract_id: str = CONTRACT_IMPROVEMENT_PROPOSAL
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_trace_ids:
            raise ValueError("ImprovementProposal requires at least one evidence_trace_id")
        if not self.evaluation_plan:
            raise ValueError("ImprovementProposal requires a non-empty evaluation_plan")
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def verify_digest(self) -> bool:
        return verify_canonical_digest(self.to_dict())


@dataclass(frozen=True)
class HoldoutReplayVerdict:
    """Zero-mutation shadow and locked holdout replay verdict for a candidate proposal."""

    verdict_id: str
    proposal_id: str
    proposal_digest: str
    dataset_digest: str
    zero_mutation_verified: bool
    unlabeled_view_enforced: bool
    target_cluster_cases: int
    target_metric_before: float
    target_metric_after: float
    holdout_cases_evaluated: int
    holdout_accuracy_before: float
    holdout_accuracy_after: float
    holdout_accuracy_delta: float
    pinned_regressions_passed: bool
    veto_regressions_count: int
    pareto_regression: bool
    latency_delta_pct: float
    cost_delta_pct: float
    verdict: Literal["PASS", "REJECT", "VETOED"]
    rejection_reasons: list[str] = field(default_factory=list)
    evaluated_at_utc: str = field(default_factory=utc_now_iso)
    contract_id: str = CONTRACT_HOLDOUT_VERDICT
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def verify_digest(self) -> bool:
        return verify_canonical_digest(self.to_dict())


@dataclass(frozen=True)
class AppliedChangeReceipt:
    """Durable cryptographic receipt for an applied post-runtime improvement with rollback handle."""

    commit_id: str
    proposal_id: str
    proposal_digest: str
    holdout_verdict_digest: str
    autonomy_tier: AutonomyTier
    approval_receipt_id: str | None
    approval_origin: Literal["POLICY_TIER_A_AUTO", "HUMAN_HITL_APPROVED", "PR_GOVERNANCE_MERGED"]
    target_path: str
    previous_state_snapshot: dict[str, Any]
    absent_keys: list[str]
    applied_state: dict[str, Any]
    pre_apply_file_sha256: str
    post_apply_file_sha256: str
    rollback_handle_path: str
    canary_status: Literal["PENDING", "PASSED", "ROLLED_BACK"]
    merkle_seal_root: str
    stages_sealed: list[str]
    status: Literal["APPLIED", "ROLLED_BACK"]
    applied_at_utc: str = field(default_factory=utc_now_iso)
    contract_id: str = CONTRACT_APPLIED_CHANGE
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_digest:
            digest = canonical_sha256(asdict(self), exclude_keys=("canonical_digest",))
            object.__setattr__(self, "canonical_digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def verify_digest(self) -> bool:
        return verify_canonical_digest(self.to_dict())
