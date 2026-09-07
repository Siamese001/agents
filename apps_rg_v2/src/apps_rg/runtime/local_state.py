"""Apps RG-owned durable-state and fact write-back primitives.

The module deliberately exposes only the application seams that Apps RG uses:
deterministic records, a transactional in-process gateway, and fact-vector
write-back classification.  It is a local boundary, not a proxy to another
runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from apps_rg.runtime.spine_contracts import RuntimePosture


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, frozenset)):
        return [_json_ready(item) for item in value]
    return value


def compute_deterministic_digest(payload: Any) -> str:
    encoded = json.dumps(
        _json_ready(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def stamp_digest(record: Any) -> Any:
    """Return a dataclass record with its deterministic digest populated."""

    if not is_dataclass(record):
        raise TypeError("stamp_digest requires a dataclass record")
    if "deterministic_digest" not in getattr(record, "__dataclass_fields__", {}):
        return record
    payload = asdict(record)
    payload["deterministic_digest"] = ""
    return replace(record, deterministic_digest=compute_deterministic_digest(payload))


@dataclass(frozen=True, slots=True)
class CommitRequest:
    commit_request_id: str
    cleared_exit_review_packet_ref: str
    request_id: str
    run_id: str
    trace_root: str
    tenant_id: str
    policy_hash: str
    blueprint_hash: str
    route_contract_ref: str
    replay_key: str
    rollback_plan_ref: str
    blast_radius: str
    source_surface: str = "Exit"
    schema_version: str = "apps_rg_uwg.v1"
    deterministic_digest: str = ""
    state_diff_refs: tuple[str, ...] = field(default_factory=tuple)
    gate_verdict_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_ref: str = ""
    hitl_reclearance_refs: tuple[str, ...] = field(default_factory=tuple)
    affected_state_surfaces: tuple[str, ...] = field(default_factory=tuple)
    expected_read_surface_refreshes: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    otel_span_refs: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    posture: RuntimePosture = field(default_factory=RuntimePosture)
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    is_uwg_write_authority: bool = False
    is_future_run_only: bool = False
    sandbox_required: bool = False
    egress_policy_ref: str = ""
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    allowed_models: tuple[str, ...] = field(default_factory=tuple)
    allowed_networks: tuple[str, ...] = field(default_factory=tuple)
    allowed_file_roots: tuple[str, ...] = field(default_factory=tuple)
    registry_digest_set: tuple[str, ...] = field(default_factory=tuple)
    capability_token_ref: str = ""
    clearance_proof_id: str = ""
    validator_receipt_id: str = ""
    staged_diff_hash: str = ""
    commit_request_signature: str = ""


@dataclass(frozen=True, slots=True)
class ReadSurfaceRefreshPlan:
    refresh_plan_id: str
    source_commit_receipt_ref: str
    before_snapshot: str
    expected_after_snapshot: str
    stale_projection_policy: str
    retry_policy: str
    policy_hash: str
    blueprint_hash: str
    schema_version: str = "apps_rg_uwg.v1"
    deterministic_digest: str = ""
    affected_surfaces: tuple[str, ...] = field(default_factory=tuple)
    required_refreshes: tuple[str, ...] = field(default_factory=tuple)
    optional_refreshes: tuple[str, ...] = field(default_factory=tuple)
    refresh_order: tuple[str, ...] = field(default_factory=tuple)
    rollback_policy_ref: str | None = None
    audit_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    rollback_plan_id: str
    blast_radius: str
    schema_version: str = "apps_rg_uwg.v1"
    deterministic_digest: str = ""
    target_surfaces: tuple[str, ...] = field(default_factory=tuple)
    before_snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    rollback_operation_types: tuple[str, ...] = field(default_factory=tuple)
    safety_preconditions: tuple[str, ...] = field(default_factory=tuple)
    policy_refs: tuple[str, ...] = field(default_factory=tuple)
    schema_refs: tuple[str, ...] = field(default_factory=tuple)
    test_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class StateDiff:
    state_diff_id: str
    target_surface: str
    operation_type: str
    after_candidate: str
    schema_ref: str
    blast_radius: str
    rollback_plan_ref: str
    proposed_by_surface: str
    created_at: str
    schema_version: str = "apps_rg_uwg.v1"
    deterministic_digest: str = ""
    before_ref: str | None = None
    validation_rules: tuple[str, ...] = field(default_factory=tuple)
    policy_refs: tuple[str, ...] = field(default_factory=tuple)
    replay_refs: tuple[str, ...] = field(default_factory=tuple)
    audit_refs: tuple[str, ...] = field(default_factory=tuple)


def compute_state_diffs_digest(state_diffs: Sequence[Any]) -> str:
    return compute_deterministic_digest([_json_ready(item) for item in state_diffs])


@dataclass(frozen=True, slots=True)
class UwgValidationReceipt:
    uwg_validation_receipt_id: str
    validation_status: str
    failed_rules: tuple[str, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    deterministic_digest: str = ""


@dataclass(frozen=True, slots=True)
class UwgCommitReceipt:
    commit_receipt_id: str
    uwg_validation_receipt_ref: str
    commit_status: str = "COMMITTED"
    deterministic_digest: str = ""
    affected_state_surfaces: tuple[str, ...] = ("sqlite",)
    state_diff_refs: tuple[str, ...] = ()
    content_hash: str = ""
    l5_certification_ref: str = ""
    gate_verdict_refs: tuple[str, ...] = ()
    policy_hash: str = ""
    blueprint_hash: str = ""
    replay_key: str = ""
    clearance_proof_id: str = ""
    registry_digest_set: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BlockedCommitReceipt:
    blocked_commit_receipt_id: str
    blocked_reason_codes: tuple[str, ...]
    failed_rule_ids: tuple[str, ...]
    no_mutation_assertion: str = "NO_MUTATION_APPLIED"
    deterministic_digest: str = ""


@dataclass(frozen=True, slots=True)
class ReadSurfaceRefreshReceipt:
    refresh_receipt_id: str
    refresh_plan_id: str
    status: str = "COMPLETE"
    deterministic_digest: str = ""


@dataclass
class ProjectionTask:
    projection_id: str
    commit_receipt_id: str
    status: str
    payload_digest: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    observed_payload_digest: str = ""
    receipt_payload: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)


class SQLiteL4Backend:
    """Small transactional persistence surface used by Apps RG promotion paths."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._state_versions: dict[str, list[dict[str, Any]]] = {}
        self._projection_tasks: list[ProjectionTask] = []
        self._audit_records: list[dict[str, Any]] = []

    def atomic_commit(
        self,
        *,
        commit_receipt_id: str,
        payloads: Sequence[Mapping[str, Any]] = (),
        projection_context: Mapping[str, Any] | None = None,
    ) -> None:
        rows = self._state_versions.setdefault(commit_receipt_id, [])
        if not rows:
            rows.extend({"payload": dict(payload)} for payload in payloads)
            self.persist_audit_record({"event_type": "atomic_commit_applied", "commit_receipt_id": commit_receipt_id})
        if projection_context is not None:
            existing = [task for task in self._projection_tasks if task.commit_receipt_id == commit_receipt_id]
            if not existing:
                context_dict = dict(projection_context)
                payload_digest = compute_deterministic_digest(context_dict)
                proj_id = f"proj:{compute_deterministic_digest((commit_receipt_id, payload_digest))[:24]}"
                self._projection_tasks.append(
                    ProjectionTask(
                        projection_id=proj_id,
                        commit_receipt_id=commit_receipt_id,
                        status="PENDING",
                        payload_digest=payload_digest,
                        context=context_dict,
                    )
                )

    def get_state_versions(self, commit_receipt_id: str) -> list[dict[str, Any]]:
        return list(self._state_versions.get(commit_receipt_id, ()))

    def list_projection_tasks(
        self, *, commit_receipt_id: str = "", statuses: Sequence[str] | None = None
    ) -> list[ProjectionTask]:
        tasks = list(self._projection_tasks)
        if commit_receipt_id:
            tasks = [task for task in tasks if task.commit_receipt_id == commit_receipt_id]
        if statuses is not None:
            allowed = set(statuses)
            tasks = [task for task in tasks if task.status in allowed]
        return tasks

    def claim_projection(self, projection_id_or_commit_id: str) -> ProjectionTask | None:
        for task in self._projection_tasks:
            if (
                task.projection_id == projection_id_or_commit_id
                or task.commit_receipt_id == projection_id_or_commit_id
            ) and task.status == "PENDING":
                task.status = "IN_PROGRESS"
                return task
        return None

    def complete_projection(
        self,
        projection_id_or_commit_id: str,
        *,
        observed_payload_digest: str = "",
        receipt_payload: Mapping[str, Any] | None = None,
    ) -> None:
        for task in self._projection_tasks:
            if (
                task.projection_id == projection_id_or_commit_id
                or task.commit_receipt_id == projection_id_or_commit_id
            ):
                task.status = "COMPLETE"
                if observed_payload_digest:
                    task.observed_payload_digest = observed_payload_digest
                if receipt_payload:
                    task.receipt_payload = dict(receipt_payload)
        self.persist_audit_record(
            {
                "event_type": "read_surface_refresh_completed",
                "commit_receipt_id": projection_id_or_commit_id,
            }
        )

    def fail_projection(
        self, projection_id_or_commit_id: str, reason: str = ""
    ) -> None:
        for task in self._projection_tasks:
            if (
                task.projection_id == projection_id_or_commit_id
                or task.commit_receipt_id == projection_id_or_commit_id
            ):
                task.status = "FAILED"
                task.reason = reason

    def reconcile_commit(self, commit_receipt_id: str) -> dict[str, Any]:
        tasks = self.list_projection_tasks(commit_receipt_id=commit_receipt_id)
        return {
            "commit_receipt_id": commit_receipt_id,
            "state_version_count": len(self.get_state_versions(commit_receipt_id)),
            "projection_task_count": len(tasks),
            "consistent": bool(self.get_state_versions(commit_receipt_id)) and all(
                task.status == "COMPLETE" for task in tasks
            ),
        }

    def persist_audit_record(self, record: Mapping[str, Any]) -> None:
        self._audit_records.append(dict(record))

    def load_audit_records(self) -> list[dict[str, Any]]:
        return list(self._audit_records)

    def health_check(self) -> dict[str, Any]:
        return {"status": "PASS", "path": str(self.path or "")}



_DEFAULT_BACKEND: SQLiteL4Backend | None = None


def get_default_backend() -> SQLiteL4Backend:
    global _DEFAULT_BACKEND
    if _DEFAULT_BACKEND is None:
        _DEFAULT_BACKEND = SQLiteL4Backend()
    return _DEFAULT_BACKEND


class DurableWriteGateway:
    """Apps RG fail-closed admission surface for durable state changes."""

    def __init__(self, **_kwargs: Any) -> None:
        self._validations: dict[str, UwgValidationReceipt] = {}
        self._commits: dict[str, UwgCommitReceipt] = {}
        self._blocked: dict[str, BlockedCommitReceipt] = {}
        self._direct_blocks: list[BlockedCommitReceipt] = []

    @property
    def last_snapshot_id(self) -> str:
        """Return the deterministic pre-write snapshot expected by UWG clients.

        The in-process gateway does not persist a materialized state snapshot,
        but a write client still needs an auditable before-reference.  Bind it
        to the committed-request set so it changes only after an accepted
        commit and is stable across equivalent gateway state.
        """
        committed = tuple(sorted(self._commits))
        return "snapshot:uwg:" + compute_deterministic_digest(committed)[:24]

    def _validate(
        self,
        commit_request: CommitRequest,
        state_diffs: list[Any],
        rollback_plan: Any,
        refresh_plan: Any,
    ) -> UwgValidationReceipt:
        request_id = str(getattr(commit_request, "commit_request_id", "") or "")
        reasons: list[str] = []
        failures: list[str] = []
        if str(getattr(commit_request, "source_surface", "") or "") != "Exit":
            failures.append("exit_sourced_commit_required")
            reasons.append("source_surface_not_exit")
        if not state_diffs:
            failures.append("state_diff_required")
            reasons.append("state_diffs_missing")
        if not str(getattr(commit_request, "rollback_plan_ref", "") or ""):
            failures.append("rollback_plan_required")
            reasons.append("rollback_plan_missing")
        if not str(getattr(commit_request, "capability_token_ref", "") or ""):
            failures.append("capability_token_required")
            reasons.append("missing_or_placeholder_capability_token_ref")
        status = "PASS" if not failures else "FAIL"
        raw = UwgValidationReceipt(
            uwg_validation_receipt_id=f"uvr:{compute_deterministic_digest((request_id, state_diffs, reasons))[:24]}",
            validation_status=status,
            failed_rules=tuple(failures),
            reason_codes=tuple(reasons),
        )
        receipt = stamp_digest(raw)
        self._validations[receipt.uwg_validation_receipt_id] = receipt
        return receipt

    def commit(
        self,
        *,
        commit_request: CommitRequest,
        state_diffs: list[Any],
        rollback_plan: Any,
        refresh_plan: Any,
    ) -> tuple[UwgCommitReceipt | None, BlockedCommitReceipt | None, list[ReadSurfaceRefreshReceipt]]:
        validation = self._validate(commit_request, state_diffs, rollback_plan, refresh_plan)
        if validation.validation_status != "PASS":
            blocked = stamp_digest(
                BlockedCommitReceipt(
                    blocked_commit_receipt_id=f"bcr:{validation.uwg_validation_receipt_id}",
                    blocked_reason_codes=validation.reason_codes,
                    failed_rule_ids=validation.failed_rules,
                )
            )
            self._blocked[blocked.blocked_commit_receipt_id] = blocked
            return None, blocked, []
        existing = self._commits.get(commit_request.commit_request_id)
        if existing is not None:
            return existing, None, []
        receipt = stamp_digest(
            UwgCommitReceipt(
                commit_receipt_id=f"ucr:{compute_deterministic_digest((commit_request.commit_request_id, validation.deterministic_digest))[:24]}",
                uwg_validation_receipt_ref=validation.uwg_validation_receipt_id,
                affected_state_surfaces=tuple(
                    getattr(commit_request, "affected_state_surfaces", ("sqlite",))
                ),
                state_diff_refs=tuple(
                    getattr(diff, "state_diff_id", str(diff)) for diff in state_diffs
                ),
                content_hash=str(
                    getattr(commit_request, "content_hash", "")
                    or getattr(commit_request, "deterministic_digest", "")
                    or ""
                ),
                l5_certification_ref=str(
                    getattr(commit_request, "l5_certification_ref", "") or ""
                ),
                gate_verdict_refs=tuple(
                    getattr(commit_request, "gate_verdict_refs", ()) or ()
                ),
                policy_hash=str(getattr(commit_request, "policy_hash", "") or ""),
                blueprint_hash=str(
                    getattr(commit_request, "blueprint_hash", "") or ""
                ),
                replay_key=str(getattr(commit_request, "replay_key", "") or ""),
                clearance_proof_id=str(
                    getattr(commit_request, "clearance_proof_id", "") or ""
                ),
                registry_digest_set=tuple(
                    getattr(commit_request, "registry_digest_set", ()) or ()
                ),
            )
        )
        self._commits[commit_request.commit_request_id] = receipt
        refreshes = [
            stamp_digest(
                ReadSurfaceRefreshReceipt(
                    refresh_receipt_id=f"rr:{receipt.commit_receipt_id}",
                    refresh_plan_id=str(getattr(refresh_plan, "refresh_plan_id", "") or ""),
                )
            )
        ]
        return receipt, None, refreshes

    def reject_direct_write(
        self,
        *,
        attempting_surface: str,
        target_surface: str,
        reason: str,
        request_id: str | None = None,
        run_id: str | None = None,
    ) -> BlockedCommitReceipt:
        blocked = stamp_digest(
            BlockedCommitReceipt(
                blocked_commit_receipt_id=f"bcr:direct:{compute_deterministic_digest((attempting_surface, target_surface, reason, request_id, run_id))[:24]}",
                blocked_reason_codes=(str(reason),),
                failed_rule_ids=("UWG_AUTHORITY_REQUIRED",),
            )
        )
        self._direct_blocks.append(blocked)
        self._blocked[blocked.blocked_commit_receipt_id] = blocked
        return blocked

    def get_validation_receipt(self, receipt_id: str) -> UwgValidationReceipt | None:
        return self._validations.get(receipt_id)

    def get_commit_receipt(self, receipt_id: str) -> UwgCommitReceipt | None:
        return next((item for item in self._commits.values() if item.commit_receipt_id == receipt_id), None)

    def get_blocked_receipt(self, receipt_id: str) -> BlockedCommitReceipt | None:
        return self._blocked.get(receipt_id)

    def list_direct_write_blocks(self) -> list[BlockedCommitReceipt]:
        return list(self._direct_blocks)


class TransactionalDurableWriteGateway(DurableWriteGateway):
    def __init__(
        self,
        *,
        canonical_backend: SQLiteL4Backend | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.canonical_backend = canonical_backend or get_default_backend()
        self._staged_payloads: dict[str, list[Mapping[str, Any]]] = {}
        self._projection_contexts: dict[str, Mapping[str, Any]] = {}

    def stage_state_payload(
        self, *, commit_request_id: str, state_diff_id: str, payload: Mapping[str, Any]
    ) -> None:
        self._staged_payloads.setdefault(commit_request_id, []).append(
            {"state_diff_id": state_diff_id, "canonical_state": dict(payload)}
        )

    def stage_projection_context(
        self, *, commit_request_id: str, context: Mapping[str, Any]
    ) -> None:
        self._projection_contexts[commit_request_id] = dict(context)

    def commit(self, **kwargs: Any) -> tuple[UwgCommitReceipt | None, BlockedCommitReceipt | None, list[ReadSurfaceRefreshReceipt]]:
        request = kwargs.get("commit_request")
        if self.canonical_backend is not None and request is not None:
            self.canonical_backend.persist_audit_record(
                {
                    "event_type": "commit_request_received",
                    "commit_request_id": getattr(request, "commit_request_id", ""),
                }
            )
        commit, blocked, refreshes = super().commit(**kwargs)
        if commit is None:
            return commit, blocked, refreshes
        if request is not None and self.canonical_backend is not None:
            self.canonical_backend.atomic_commit(
                commit_receipt_id=commit.commit_receipt_id,
                payloads=self._staged_payloads.get(request.commit_request_id, ()),
                projection_context=self._projection_contexts.get(request.commit_request_id),
            )
        return commit, blocked, refreshes

    def complete_projection(
        self,
        projection_id_or_receipt: str,
        *,
        observed_payload_digest: str = "",
        receipt_payload: Mapping[str, Any] | None = None,
    ) -> None:
        if self.canonical_backend is not None:
            self.canonical_backend.complete_projection(
                projection_id_or_receipt,
                observed_payload_digest=observed_payload_digest,
                receipt_payload=receipt_payload,
            )

    def fail_projection(
        self,
        projection_id_or_receipt: str,
        reason: str = "",
        *,
        error: str = "",
    ) -> None:
        if self.canonical_backend is not None:
            self.canonical_backend.fail_projection(
                projection_id_or_receipt, reason=reason or error
            )

    def reconcile_commit(self, commit_receipt_id: str) -> dict[str, Any]:
        if self.canonical_backend is not None:
            return self.canonical_backend.reconcile_commit(commit_receipt_id)
        return {"commit_receipt_id": commit_receipt_id, "consistent": False}

    def projection_tasks(
        self, *, commit_receipt_id: str = "", statuses: Sequence[str] | None = None
    ) -> list[ProjectionTask]:
        if self.canonical_backend is not None:
            return self.canonical_backend.list_projection_tasks(
                commit_receipt_id=commit_receipt_id, statuses=statuses
            )
        return []


_DEFAULT_GATEWAY: DurableWriteGateway | None = None


def get_default_gateway() -> DurableWriteGateway:
    global _DEFAULT_GATEWAY
    if _DEFAULT_GATEWAY is None:
        _DEFAULT_GATEWAY = DurableWriteGateway()
    return _DEFAULT_GATEWAY


def reset_default_gateway() -> None:
    global _DEFAULT_GATEWAY
    _DEFAULT_GATEWAY = None


@dataclass(frozen=True, slots=True)
class ApprovedJudgeCalibrationBaseline:
    baseline_id: str
    app_id: str
    task_class: str
    status: str
    judge_id: str
    judge_version: str
    rubric_hash: str
    rubric_version: str
    provider_profile_ref: str
    dataset_id: str
    dataset_version: str
    n: int
    spearman_rho: float
    p_value: float
    threshold: float
    approved_use: str
    approved_at: str
    expires_at: str
    promotion_receipt_ref: str
    uwg_receipt_ref: str
    schema_version: str = "apps_rg_uwg.v1"
    deterministic_digest: str = ""
    source_app_config_ref: str = ""
    created_by_surface: str = "UWG"
    audit_refs: tuple[str, ...] = field(default_factory=tuple)
    lineage_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.created_by_surface != "UWG":
            raise AppDomainContractError(
                "judge calibration baselines must be created by the Apps RG durable-write gateway"
            )


class AppDomainContractError(ValueError):
    pass


class AppDomainLookupError(LookupError):
    pass


class InMemoryAppDomainStore:
    def __init__(self) -> None:
        self._values: dict[str, dict[tuple[str, ...], Any]] = {}

    def clear(self) -> None:
        self._values.clear()

    def _put(self, kind: str, *keys: str, value: Any) -> None:
        self._values.setdefault(kind, {})[tuple(keys)] = value

    def _get(self, kind: str, *keys: str) -> Any:
        try:
            return self._values[kind][tuple(keys)]
        except KeyError as exc:
            raise AppDomainLookupError(f"Apps RG domain item not found: {kind}/{keys}") from exc

    def put_judge_calibration_baseline(self, baseline: ApprovedJudgeCalibrationBaseline) -> None:
        self._put("judge_calibration", baseline.baseline_id, value=baseline)

    def get_judge_calibration_baseline(self, baseline_id: str) -> ApprovedJudgeCalibrationBaseline:
        baseline = self._get("judge_calibration", baseline_id)
        expected = stamp_digest(replace(baseline, deterministic_digest="")).deterministic_digest
        if baseline.deterministic_digest != expected:
            raise AppDomainLookupError("judge calibration baseline digest invalid")
        return baseline


_DEFAULT_APP_DOMAIN_STORE: InMemoryAppDomainStore | None = None


def get_default_app_domain_store() -> InMemoryAppDomainStore:
    global _DEFAULT_APP_DOMAIN_STORE
    if _DEFAULT_APP_DOMAIN_STORE is None:
        _DEFAULT_APP_DOMAIN_STORE = InMemoryAppDomainStore()
    return _DEFAULT_APP_DOMAIN_STORE


def norm(value: Any) -> str:
    return str(value or "").strip()


def scalarize_metadata(metadata: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    result: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if isinstance(value, bool | int | float | str):
            result[str(key)] = value
        elif value is None:
            result[str(key)] = ""
        else:
            result[str(key)] = json.dumps(_json_ready(value), sort_keys=True)
    return result


@dataclass(frozen=True, slots=True)
class FactWritebackProfile:
    stage_route: str
    semantic_cache_route: str
    reject_route: str
    default_operation: str
    generated_operation: str
    allowed_operations: tuple[str, ...]
    operation_key: str = "write_back_operation"
    source_type_key: str = "source_type"
    source_pointer_keys: tuple[str, ...] = ("source_span_ref", "source_ref")
    source_document_id_key: str = "source_document_id"
    digest_key: str = "chunk_digest"
    confidence_key: str = "confidence"
    proof_status_key: str = "proof_status"
    authority_key: str = "authority_class"
    tier_key: str = "tier"
    learned_tier_value: str = "learned"
    promoted_at_key: str = "promoted_at_utc"
    promotion_run_id_key: str = "promotion_run_id"
    promotion_score_key: str = "promotion_score"
    promotion_score_components_key: str = "promotion_score_components"
    hold_reason_key: str = "promotion_hold_reason"
    hold_at_key: str = "promotion_hold_at_utc"
    run_id_key: str = "run_id"
    x3_code_key: str = "x3_code"
    section_key: str = "section_type"
    staged_at_key: str = "staged_at_utc"
    x3_allow_code: str = "X3_ALLOW"
    generated_proof_statuses: tuple[str, ...] = field(default_factory=tuple)
    forbidden_source_types: tuple[str, ...] = field(default_factory=tuple)
    confidence_scores: Mapping[str, float] = field(default_factory=dict)
    proof_status_scores: Mapping[str, float] = field(default_factory=dict)
    authority_scores: Mapping[str, float] = field(default_factory=dict)
    default_confidence_score: float = 0.3
    default_proof_status_score: float = 0.5
    default_authority_score: float = 0.8
    promotion_receipt_schema_version: str = "fact_writeback_promotion_v1"
    staging_list_schema_version: str = "fact_writeback_staging_list_v1"
    staging_reject_schema_version: str = "fact_writeback_staging_reject_v1"
    staging_drain_schema_version: str = "fact_writeback_staging_drain_held_v1"


@dataclass(frozen=True, slots=True)
class StagedFactRow:
    row_id: str
    document: str
    embedding: Any
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PromotedFactRow:
    row_id: str
    document: str
    embedding: Any
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PromotionRequest:
    staging_collection: str
    live_collection: str
    promotion_run_id: str
    promotion_mode: str
    promoted_at_utc: str
    score_floor: float
    hitl_required: bool
    selected_ids: tuple[str, ...] = field(default_factory=tuple)
    run_id: str = ""
    x3_code: str = ""
    require_x3_allow: bool = False
    limit: int | None = None
    receipt_path: str = ""


@dataclass(frozen=True, slots=True)
class WriteBackDecision:
    route: str
    operation: str
    reason: str
    stage_route: str = ""

    @property
    def stage(self) -> str:
        return self.stage_route


class FactWritebackEngine:
    def __init__(self, profile: FactWritebackProfile) -> None:
        self.profile = profile

    def is_generated_source(self, atom: Mapping[str, Any]) -> tuple[bool, str]:
        source_type = norm(atom.get(self.profile.source_type_key)).lower()
        proof_status = norm(atom.get(self.profile.proof_status_key)).lower()
        operation = norm(atom.get(self.profile.operation_key)).lower()
        if source_type in {item.lower() for item in self.profile.forbidden_source_types}:
            return True, "forbidden_source_type"
        if proof_status in {item.lower() for item in self.profile.generated_proof_statuses}:
            return True, "generated_proof_status"
        if operation == self.profile.generated_operation.lower():
            return True, "generated_operation"
        return False, "grounded_source"

    def has_source_pointer(self, atom: Mapping[str, Any]) -> bool:
        return any(norm(atom.get(key)) for key in self.profile.source_pointer_keys)

    def source_grounding_ok(self, atom: Mapping[str, Any]) -> tuple[bool, str]:
        generated, generated_reason = self.is_generated_source(atom)
        if generated:
            return False, generated_reason
        if not self.has_source_pointer(atom):
            return False, "source_pointer_missing"
        return True, "source_grounded"

    def classify_write_back_operation(self, atom: Mapping[str, Any]) -> tuple[str, str]:
        generated, reason = self.is_generated_source(atom)
        if generated:
            return self.profile.generated_operation, reason
        requested = norm(atom.get(self.profile.operation_key)).lower()
        if requested in self.profile.allowed_operations:
            return requested, "declared_grounded_operation"
        return self.profile.default_operation, "default_grounded_operation"

    def decide_write_back(self, atom: Mapping[str, Any]) -> WriteBackDecision:
        operation, reason = self.classify_write_back_operation(atom)
        if operation == self.profile.generated_operation:
            return WriteBackDecision(self.profile.semantic_cache_route, operation, reason)
        grounded, grounding_reason = self.source_grounding_ok(atom)
        if not grounded:
            return WriteBackDecision(self.profile.reject_route, operation, grounding_reason)
        return WriteBackDecision(
            self.profile.stage_route,
            operation,
            "grounded_transform",
            self.profile.stage_route,
        )

    def promotion_score(self, metadata: Mapping[str, Any]) -> tuple[float, dict[str, float]]:
        confidence = self.profile.confidence_scores.get(
            norm(metadata.get(self.profile.confidence_key)).upper(), self.profile.default_confidence_score
        )
        proof = self.profile.proof_status_scores.get(
            norm(metadata.get(self.profile.proof_status_key)).lower(), self.profile.default_proof_status_score
        )
        authority = self.profile.authority_scores.get(
            norm(metadata.get(self.profile.authority_key)).upper(), self.profile.default_authority_score
        )
        components = {"confidence": confidence, "proof_status": proof, "authority": authority}
        return round((confidence + proof + authority) / 3.0, 6), components

    def staged_row_is_promotable(self, metadata: Mapping[str, Any]) -> tuple[bool, str]:
        operation = norm(metadata.get(self.profile.operation_key)).lower()
        if operation not in self.profile.allowed_operations:
            return False, "operation_not_promotable"
        if not norm(metadata.get(self.profile.source_document_id_key)):
            return False, "source_document_id_missing"
        generated, reason = self.is_generated_source(metadata)
        if generated:
            return False, reason
        return True, "promotable"

    def make_promotion_receipt(self, request: PromotionRequest) -> dict[str, Any]:
        return {
            "schema_version": self.profile.promotion_receipt_schema_version,
            "promotion_run_id": request.promotion_run_id,
            "staging_collection": request.staging_collection,
            "live_collection": request.live_collection,
            "status": "NOT_RUN",
            "reason": "",
            "staged_count": 0,
            "promoted_count": 0,
            "rejected_count": 0,
            "held_count": 0,
            "promoted": [],
            "rejected": [],
            "held": [],
        }

    def promote(
        self,
        store: Any,
        request: PromotionRequest,
        *,
        sparse_sync_callback: Callable[[Sequence[PromotedFactRow], int], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        receipt = self.make_promotion_receipt(request)
        rows = list(store.list_staged_rows(include_embeddings=True))
        if request.run_id:
            rows = [row for row in rows if norm(row.metadata.get(self.profile.run_id_key)) == request.run_id]
        if request.selected_ids:
            ids = set(request.selected_ids)
            rows = [row for row in rows if row.row_id in ids]
        if request.limit is not None:
            rows = rows[: max(0, request.limit)]
        receipt["staged_count"] = len(rows)
        to_promote: list[PromotedFactRow] = []
        hold_metadata: dict[str, dict[str, Any]] = {}
        for row in rows:
            allowed, reason = self.staged_row_is_promotable(row.metadata)
            if not allowed:
                receipt["rejected"].append({"id": row.row_id, "reason": reason})
                continue
            if request.require_x3_allow:
                row_x3 = norm(row.metadata.get(self.profile.x3_code_key))
                effective_x3 = row_x3 or request.x3_code
                if effective_x3 != self.profile.x3_allow_code:
                    reason = f"run_not_x3_allow:{effective_x3}" if effective_x3 else "x3_allow_required"
                    hold_metadata[row.row_id] = {**row.metadata, self.profile.hold_reason_key: reason}
                    receipt["held"].append({"id": row.row_id, "reason": reason})
                    continue
            if request.hitl_required:
                hold_metadata[row.row_id] = {**row.metadata, self.profile.hold_reason_key: "hitl_required"}
                receipt["held"].append({"id": row.row_id, "reason": "hitl_required"})
                continue
            score, components = self.promotion_score(row.metadata)
            if score < request.score_floor:
                reason = f"promotion_score_below_floor:{score:.6f}<{request.score_floor:.6f}"
                hold_metadata[row.row_id] = {**row.metadata, self.profile.hold_reason_key: reason}
                receipt["held"].append({"id": row.row_id, "reason": reason})
                continue
            digest = norm(row.metadata.get(self.profile.digest_key))
            duplicate = store.find_live_id_by_digest(digest) if digest else ""
            if duplicate:
                reason = f"duplicate_digest:{duplicate}"
                hold_metadata[row.row_id] = {**row.metadata, self.profile.hold_reason_key: reason}
                receipt["held"].append({"id": row.row_id, "reason": reason})
                continue
            metadata = {
                **row.metadata,
                self.profile.tier_key: self.profile.learned_tier_value,
                self.profile.promoted_at_key: request.promoted_at_utc,
                self.profile.promotion_run_id_key: request.promotion_run_id,
                self.profile.promotion_score_key: score,
                self.profile.promotion_score_components_key: components,
            }
            to_promote.append(PromotedFactRow(row.row_id, row.document, row.embedding, metadata))
        if hold_metadata:
            store.mark_staged_rows_held(hold_metadata)
        if to_promote:
            store.upsert_live_rows(to_promote)
            store.delete_staged_rows([row.row_id for row in to_promote])
            receipt["promoted"] = [{"id": row.row_id} for row in to_promote]
        receipt["promoted_count"] = len(to_promote)
        receipt["rejected_count"] = len(receipt["rejected"])
        receipt["held_count"] = len(receipt["held"])
        if request.hitl_required and receipt["held_count"]:
            receipt["status"] = "HELD_FOR_HITL"
        elif any(h.get("reason", "").startswith("run_not_x3_allow") or h.get("reason") == "x3_allow_required" for h in receipt["held"]):
            receipt["status"] = "HELD_FOR_X3"
        elif receipt["promoted_count"]:
            receipt["status"] = "PASS"
        elif receipt["staged_count"] == 0:
            receipt["status"] = "EMPTY"
        else:
            receipt["status"] = "NONE_PROMOTABLE"
        if sparse_sync_callback and to_promote:
            receipt.update(dict(sparse_sync_callback(to_promote, int(store.live_count()))))
        return receipt

    def make_staging_list_receipt(self, *, staging_collection: str, chroma_path: str) -> dict[str, Any]:
        return {"schema_version": self.profile.staging_list_schema_version, "staging_collection": staging_collection, "chroma_path": chroma_path, "status": "NOT_RUN", "rows": []}

    def list_staged(self, store: Any, *, staging_collection: str, chroma_path: str, limit: int | None = None) -> dict[str, Any]:
        rows = list(store.list_staged_rows(include_embeddings=False))
        if limit is not None:
            rows = rows[: max(0, limit)]
        return {"schema_version": self.profile.staging_list_schema_version, "staging_collection": staging_collection, "chroma_path": chroma_path, "status": "PASS", "rows": [{"id": row.row_id, "document": row.document, "metadata": row.metadata} for row in rows]}

    def make_staging_reject_receipt(self, *, staging_collection: str, chroma_path: str, selected_ids: tuple[str, ...], reason: str) -> dict[str, Any]:
        return {"schema_version": self.profile.staging_reject_schema_version, "staging_collection": staging_collection, "chroma_path": chroma_path, "selected_ids": list(selected_ids), "reason": reason, "status": "NOT_RUN"}

    def reject_staged(self, store: Any, *, staging_collection: str, chroma_path: str, ids: tuple[str, ...], reason: str) -> dict[str, Any]:
        store.delete_staged_rows(ids)
        return {"schema_version": self.profile.staging_reject_schema_version, "staging_collection": staging_collection, "chroma_path": chroma_path, "selected_ids": list(ids), "reason": reason, "status": "PASS", "rejected_count": len(ids)}

    def drain_held(self, store: Any, *, staging_collection: str, chroma_path: str, reason: str) -> dict[str, Any]:
        rows = list(store.list_staged_rows(include_embeddings=False))
        ids = [row.row_id for row in rows if norm(row.metadata.get(self.profile.hold_reason_key))]
        store.delete_staged_rows(ids)
        return {"schema_version": self.profile.staging_drain_schema_version, "staging_collection": staging_collection, "chroma_path": chroma_path, "drained_ids": ids, "status": "PASS" if ids else "EMPTY", "reason": reason if ids else "no_held_rows"}


__all__ = [
    "AppDomainContractError",
    "AppDomainLookupError",
    "ApprovedJudgeCalibrationBaseline",
    "BlockedCommitReceipt",
    "CommitRequest",
    "DurableWriteGateway",
    "FactWritebackEngine",
    "FactWritebackProfile",
    "InMemoryAppDomainStore",
    "PromotedFactRow",
    "PromotionRequest",
    "ReadSurfaceRefreshPlan",
    "RollbackPlan",
    "SQLiteL4Backend",
    "StagedFactRow",
    "StateDiff",
    "TransactionalDurableWriteGateway",
    "UwgCommitReceipt",
    "UwgValidationReceipt",
    "WriteBackDecision",
    "compute_deterministic_digest",
    "compute_state_diffs_digest",
    "get_default_app_domain_store",
    "get_default_backend",
    "get_default_gateway",
    "norm",
    "reset_default_gateway",
    "scalarize_metadata",
    "stamp_digest",
]
