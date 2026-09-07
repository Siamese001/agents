"""Small application-owned compatibility surface for sibling app integrations.

This module keeps optional Apps Research and Apps Eval integrations importable
without reaching into a separate runtime checkout.  It intentionally provides
technical compatibility only; it does not grant execution, release, or state
write authority.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Callable, Mapping, TypeVar

from apps_rg.runtime.core_model_catalog import (
    BGE_M3_EMBEDDING_DIMENSION,
    BGE_M3_MODEL_ID,
)
from apps_rg.runtime.local_l6 import (
    L6PipelineState,
    build_apps_eval_alignment,
    build_future_run_proposals,
    build_l6_apps_eval_grain_parity,
    build_microstep_coverage,
    build_microstep_patterns,
    build_microstep_rca,
    run_6a,
    run_observer,
    write_span_artifacts,
)
from apps_rg.runtime.local_state import (
    CommitRequest,
    DurableWriteGateway,
    ReadSurfaceRefreshPlan,
    RollbackPlan,
    StateDiff,
    compute_deterministic_digest,
    compute_state_diffs_digest,
    get_default_gateway,
    stamp_digest,
)
from apps_rg.runtime.spine_contracts import (
    CompiledPromptArtifact,
    FinalEvidenceContract,
    L1PlanContract,
    RequestEnvelope,
    RouteContract,
    RuntimeCustomizationPackage,
    SealedL2Artifact,
    ValidatedRequest,
    X3Disposition,
)


_T = TypeVar("_T")


class _CompatMeta(type):
    def __getattr__(cls, name: str) -> str:
        value = name
        setattr(cls, name, value)
        return value


class CompatRecord(metaclass=_CompatMeta):
    """A permissive record for optional, non-authoritative integration seams."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, _name: str) -> "CompatRecord":
        return CompatRecord()

    def __call__(self, *args: Any, **kwargs: Any) -> "CompatRecord":
        return CompatRecord(*args, **kwargs)

    def __iter__(self):
        return iter(())

    def __bool__(self) -> bool:
        return False


class AppRuntimeCompatibilityError(RuntimeError):
    """Raised by an optional compatibility seam that lacks an app implementation."""


class EmbeddingMixin:
    """Marker retained for integrations that only require the local type surface."""


class SemanticCacheMixin:
    """Marker retained for integrations that only require the local type surface."""


class GraderError(AppRuntimeCompatibilityError):
    """Local grading integration error."""


class PackageDigestMismatchError(AppRuntimeCompatibilityError):
    """Local customization package digest mismatch."""


class UnknownPackageFieldError(AppRuntimeCompatibilityError):
    """Local customization package contains an unsupported field."""


def traces_execute(
    function: Callable[..., _T] | None = None, **_metadata: Any
) -> Callable[..., _T] | Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Return a no-op decorator for local telemetry-compatible call sites."""

    if function is not None and callable(function):
        return function

    def decorate(target: Callable[..., _T]) -> Callable[..., _T]:
        return target

    return decorate


def _emit_noop(*_args: Any, **_kwargs: Any) -> None:
    return None


def _resolve_device(*_args: Any, **_kwargs: Any) -> str:
    return "cpu"


class GraderClass(str, Enum):
    MODEL_BASED = "MODEL_BASED"
    DETERMINISTIC = "DETERMINISTIC"


@dataclass(frozen=True)
class Dimension:
    name: str
    grader_class: GraderClass
    threshold: float
    is_hard_gate: bool
    abstain_allowed: bool


@dataclass(frozen=True)
class JudgeResponse:
    score: float
    abstain: bool
    reasoning: str


@dataclass(frozen=True)
class _HttpRequest:
    url: str
    body: bytes
    method: str
    headers: Mapping[str, str]


class GoogleJudge:
    """Small local judge transport contract used by Apps Research tests."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        max_tokens: int = 4096,
        timeout: float = 30.0,
        **_kwargs: Any,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._timeout = timeout
        self.observed_model = ""
        self.provider_evidence: dict[str, Any] = {}

    def _build_request(self, system: str, user: str) -> _HttpRequest:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": self._max_tokens, "temperature": 0.0},
        }
        return _HttpRequest(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={"x-goog-api-key": self._api_key, "content-type": "application/json"},
        )

    def _extract_text(self, response_json: Any) -> str:
        try:
            parts = response_json["candidates"][0]["content"]["parts"]
            return "".join(str(part.get("text") or "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise GraderError("judge response had no text part") from exc

    def _parse_response(self, _dimension: Dimension, raw_text: str) -> JudgeResponse:
        try:
            # Gemini may wrap an otherwise valid requested JSON object in one
            # Markdown fence.  Accept only that unambiguous wrapper; arbitrary
            # prose around JSON remains a fail-closed contract violation.
            normalized = str(raw_text or "").strip()
            fenced = re.fullmatch(
                r"```(?:json)?\s*(\{.*\})\s*```",
                normalized,
                flags=re.DOTALL | re.IGNORECASE,
            )
            payload = json.loads(fenced.group(1) if fenced else normalized)
            if not isinstance(payload, dict):
                raise TypeError("judge response must be a JSON object")
            score = float(payload["score"])
            reasoning = str(payload.get("reasoning") or "")
            verdict = str(payload.get("verdict") or "").upper()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GraderError("judge JSON parse failed") from exc
        return JudgeResponse(score=score, abstain=verdict == "UNKNOWN", reasoning=reasoning)


class AuthorityLevel(str, Enum):
    INFO = "INFO"


@dataclass(frozen=True)
class AuthoritySlot:
    slot_type: str
    authority_level: AuthorityLevel
    content: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class SynthesisProvenance:
    producer: str
    source_trace_ids: tuple[str, ...]
    model: str
    synthesis_kind: str


def wrap_synthesis_output(
    *, text: str, provenance: SynthesisProvenance, source_layer: str
) -> AuthoritySlot:
    return AuthoritySlot(
        slot_type="C0",
        authority_level=AuthorityLevel.INFO,
        content=text,
        metadata={
            "synthesis_producer": provenance.producer,
            "synthesis_source_trace_ids": list(provenance.source_trace_ids),
            "synthesis_model": provenance.model,
            "synthesis_kind": provenance.synthesis_kind,
            "source_layer": source_layer,
        },
    )


def _digest(payload: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class GateVerdict:
    gate_id: str
    gate_family: str
    evaluated_stage: str
    evaluated_surface: str
    evaluated_packet_ref: str
    result: str
    severity: str
    reason_codes: tuple[str, ...] = ()
    score: float = 0.0
    threshold: float = 0.0
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    deterministic_digest: str = ""
    request_id: str = ""
    run_id: str = ""
    trace_root: str = ""
    evidence_digest: str = ""
    evaluator_version: str = ""
    evaluated_at: str = ""
    unknown_reason: str = ""
    created_at: str = ""

    @property
    def is_pass(self) -> bool:
        return self.result == "PASS"

    @property
    def is_hard_fail(self) -> bool:
        return self.result == "FAIL"

    @property
    def is_material_unknown(self) -> bool:
        return self.result == "UNKNOWN"

    @property
    def is_not_applicable(self) -> bool:
        return self.result == "NOT_APPLICABLE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "gate_family": self.gate_family,
            "evaluated_stage": self.evaluated_stage,
            "evaluated_surface": self.evaluated_surface,
            "evaluated_packet_ref": self.evaluated_packet_ref,
            "result": self.result,
            "severity": self.severity,
            "reason_codes": list(self.reason_codes),
            "score": self.score,
            "threshold": self.threshold,
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
            "deterministic_digest": self.deterministic_digest,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "trace_root": self.trace_root,
            "evidence_digest": self.evidence_digest,
            "evaluator_version": self.evaluator_version,
            "evaluated_at": self.evaluated_at,
            "unknown_reason": self.unknown_reason,
            "created_at": self.created_at,
            "schema_version": "apps_rg.local_gate_verdict.v1",
            "is_pass": self.is_pass,
            "is_hard_fail": self.is_hard_fail,
            "is_material_unknown": self.is_material_unknown,
            "is_not_applicable": self.is_not_applicable,
        }


@dataclass(frozen=True)
class GateMeshResult:
    request_id: str
    run_id: str
    trace_root: str
    route_id: str
    evaluated_surface: str
    evaluated_packet_ref: str
    required_gate_ids: tuple[str, ...]
    verdicts: tuple[GateVerdict, ...]
    completed_gate_ids: tuple[str, ...]
    missing_gate_ids: tuple[str, ...]
    hard_fail_present: bool
    unknown_material_present: bool
    warn_material_present: bool
    recommended_disposition_summary: str
    recommended_next_owner: str
    deterministic_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "trace_root": self.trace_root,
            "route_id": self.route_id,
            "evaluated_surface": self.evaluated_surface,
            "evaluated_packet_ref": self.evaluated_packet_ref,
            "required_gate_ids": list(self.required_gate_ids),
            "verdicts": [row.as_dict() for row in self.verdicts],
            "completed_gate_ids": list(self.completed_gate_ids),
            "missing_gate_ids": list(self.missing_gate_ids),
            "hard_fail_present": self.hard_fail_present,
            "unknown_material_present": self.unknown_material_present,
            "warn_material_present": self.warn_material_present,
            "recommended_disposition_summary": self.recommended_disposition_summary,
            "recommended_next_owner": self.recommended_next_owner,
            "gate_mesh_schema_version": "apps_rg.local_gate_mesh.v1",
            "deterministic_digest": self.deterministic_digest,
        }


def build_gate_mesh_result(**kwargs: Any) -> GateMeshResult:
    verdicts = tuple(kwargs.get("verdicts") or ())
    required_gate_ids = tuple(str(value) for value in kwargs.get("required_gate_ids") or ())
    completed_gate_ids = tuple(
        row.gate_id for row in verdicts if isinstance(row, GateVerdict)
    )
    completed_set = set(completed_gate_ids)
    missing_gate_ids = tuple(
        gate_id for gate_id in required_gate_ids if gate_id not in completed_set
    )
    results_by_id = {
        row.gate_id: row.result for row in verdicts if isinstance(row, GateVerdict)
    }
    hard_fail_present = any(
        results_by_id.get(gate_id) == "FAIL" for gate_id in required_gate_ids
    )
    unknown_material_present = any(
        results_by_id.get(gate_id) == "UNKNOWN" for gate_id in required_gate_ids
    )
    warn_material_present = any(
        results_by_id.get(gate_id) == "WARN" for gate_id in required_gate_ids
    )
    clean = not (
        missing_gate_ids
        or hard_fail_present
        or unknown_material_present
        or warn_material_present
    )
    recommended_disposition_summary = (
        "All required gates passed; finish is eligible"
        if clean
        else "One or more required gates are not eligible for finish"
    )
    recommended_next_owner = "exit::allow_finish" if clean else "exit::blocked"
    payload = {
        "request_id": str(kwargs.get("request_id") or ""),
        "run_id": str(kwargs.get("run_id") or ""),
        "trace_root": str(kwargs.get("trace_root") or ""),
        "route_id": str(kwargs.get("route_id") or ""),
        "evaluated_surface": str(kwargs.get("evaluated_surface") or ""),
        "evaluated_packet_ref": str(kwargs.get("evaluated_packet_ref") or ""),
        "required_gate_ids": list(required_gate_ids),
        "verdicts": [row.as_dict() for row in verdicts],
        "completed_gate_ids": list(completed_gate_ids),
        "missing_gate_ids": list(missing_gate_ids),
        "hard_fail_present": hard_fail_present,
        "unknown_material_present": unknown_material_present,
        "warn_material_present": warn_material_present,
        "recommended_disposition_summary": recommended_disposition_summary,
        "recommended_next_owner": recommended_next_owner,
    }
    return GateMeshResult(
        request_id=payload["request_id"],
        run_id=payload["run_id"],
        trace_root=payload["trace_root"],
        route_id=payload["route_id"],
        evaluated_surface=payload["evaluated_surface"],
        evaluated_packet_ref=payload["evaluated_packet_ref"],
        required_gate_ids=required_gate_ids,
        verdicts=verdicts,
        completed_gate_ids=completed_gate_ids,
        missing_gate_ids=missing_gate_ids,
        hard_fail_present=hard_fail_present,
        unknown_material_present=unknown_material_present,
        warn_material_present=warn_material_present,
        recommended_disposition_summary=recommended_disposition_summary,
        recommended_next_owner=recommended_next_owner,
        deterministic_digest=_digest(payload),
    )


@dataclass(frozen=True)
class SealedWorkflowPackage:
    package_id: str
    route_contract_ref: str
    workflow_ref: str
    workflow_id: str
    run_id: str
    app_context: str
    trace_root: str
    completed_at: str
    merged_content: str
    merged_content_digest: str
    merged_payload_digest: str
    runtime_gate_refs: tuple[str, ...] = ()
    terminal_class: str = ""
    decisive_reason: str = ""
    replay_manifest: str = ""
    schema_version: str = "apps_rg.local_sealed_workflow.v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "route_contract_ref": self.route_contract_ref,
            "workflow_ref": self.workflow_ref,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "app_context": self.app_context,
            "trace_root": self.trace_root,
            "completed_at": self.completed_at,
            "merged_content": self.merged_content,
            "merged_content_digest": self.merged_content_digest,
            "merged_payload_digest": self.merged_payload_digest,
            "runtime_gate_refs": list(self.runtime_gate_refs),
            "terminal_class": self.terminal_class,
            "decisive_reason": self.decisive_reason,
            "replay_manifest": self.replay_manifest,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class GateProfile:
    profile_id: str
    app_id: str
    task_class: str
    version: str
    required_exit_gates: tuple[str, ...]
    gate_definitions: Mapping[str, Any]


@dataclass(frozen=True)
class ExitPolicy:
    policy_id: str = "apps_rg.local_exit_policy.v1"


@dataclass(frozen=True)
class ExitInput:
    sealed_l2_artifact: SealedWorkflowPackage
    gate_mesh_result: Any
    evidence: Mapping[str, Any]


@dataclass(frozen=True)
class ExitReviewPacket:
    run_id: str
    request_id: str
    trace_root: str
    app_id: str
    task_class: str
    created_at: str
    gate_mesh_summary: Mapping[str, Any]
    x1_checkout_result: Mapping[str, Any]
    x2_aggregation_result: Mapping[str, Any]
    eligible: bool
    gate_results: tuple[Mapping[str, Any], ...] = ()
    input_type: str = "sealed_l2_artifact"
    schema_version: str = "apps_rg.local_exit_review.v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "trace_root": self.trace_root,
            "app_id": self.app_id,
            "task_class": self.task_class,
            "created_at": self.created_at,
            "gate_mesh_summary": dict(self.gate_mesh_summary),
            "x1_checkout_result": dict(self.x1_checkout_result),
            "x2_aggregation_result": dict(self.x2_aggregation_result),
            "gate_results": [dict(row) for row in self.gate_results],
            "eligible": self.eligible,
            "input_type": self.input_type,
            "schema_version": self.schema_version,
        }


X3D_ALLOW_FINISH = "X3D_ALLOW_FINISH"


@dataclass(frozen=True)
class ExitDispositionReceipt:
    request_id: str
    run_id: str
    trace_root: str
    x3_code: str
    app_id: str = "apps_research"
    exit_profile_ref: str = ""
    task_class: str = ""
    workflow_ref: str = ""
    sealed_workflow_package_ref: str = ""
    gate_mesh_result_ref: str = ""
    required_gates_passed: bool = False
    hard_fail_count: int = 0
    unknown_count: int = 0
    missing_gate_count: int = 0
    warn_count: int = 0
    decisive_reason: str = ""
    decisive_blocker_codes: tuple[str, ...] = ()
    decisive_blocker_gate_ids: tuple[str, ...] = ()
    policy_hash: str = ""
    commit_request_ref: str = ""
    uwg_path_evidence_ref: str = ""
    created_at: str = ""
    deterministic_digest: str = ""
    output_artifact_digest: str = ""
    schema_version: str = "apps_rg.local_exit_receipt.v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "trace_root": self.trace_root,
            "x3_code": self.x3_code,
            "app_id": self.app_id,
            "exit_profile_ref": self.exit_profile_ref,
            "task_class": self.task_class,
            "workflow_ref": self.workflow_ref,
            "sealed_workflow_package_ref": self.sealed_workflow_package_ref,
            "gate_mesh_result_ref": self.gate_mesh_result_ref,
            "required_gates_passed": self.required_gates_passed,
            "hard_fail_count": self.hard_fail_count,
            "unknown_count": self.unknown_count,
            "missing_gate_count": self.missing_gate_count,
            "warn_count": self.warn_count,
            "decisive_reason": self.decisive_reason,
            "decisive_blocker_codes": list(self.decisive_blocker_codes),
            "decisive_blocker_gate_ids": list(self.decisive_blocker_gate_ids),
            "policy_hash": self.policy_hash,
            "commit_request_ref": self.commit_request_ref,
            "uwg_path_evidence_ref": self.uwg_path_evidence_ref,
            "created_at": self.created_at,
            "deterministic_digest": self.deterministic_digest,
            "output_artifact_digest": self.output_artifact_digest,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class RuntimeExhaustBundle:
    run_id: str
    trace_root: str
    exit_disposition_ref: str = ""
    request_id: str = ""
    route_contract_ref: str = ""
    sealed_result_ref: str = ""
    gate_mesh_result_ref: str = ""
    created_after_exit: bool = False
    current_run_closed: bool = False
    learning_profile_ref: str = ""
    writeback_candidates: tuple[str, ...] = ()
    created_at: str = ""
    schema_version: str = "apps_rg.local_runtime_exhaust.v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "trace_root": self.trace_root,
            "exit_disposition_ref": self.exit_disposition_ref,
            "request_id": self.request_id,
            "route_contract_ref": self.route_contract_ref,
            "sealed_result_ref": self.sealed_result_ref,
            "gate_mesh_result_ref": self.gate_mesh_result_ref,
            "created_after_exit": self.created_after_exit,
            "current_run_closed": self.current_run_closed,
            "learning_profile_ref": self.learning_profile_ref,
            "writeback_candidates": list(self.writeback_candidates),
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }


def exit_bind_and_finalize_apps_research(
    *,
    gate_profile: GateProfile,
    exit_policy: ExitPolicy,
    exit_input: ExitInput,
    request_id: str,
    run_id: str,
    trace_root: str,
    route_id: str,
    commit_requested: bool,
) -> tuple[ExitReviewPacket, ExitDispositionReceipt, RuntimeExhaustBundle]:
    del route_id, commit_requested
    summary = dict(exit_input.gate_mesh_result.summarize())
    gate_rows = tuple(
        dict(row) for row in summary.get("verdicts") or () if isinstance(row, Mapping)
    )
    required = tuple(str(gate_id) for gate_id in gate_profile.required_exit_gates)
    by_id = {
        str(row.get("gate_id") or ""): str(row.get("result") or "")
        for row in gate_rows
    }
    missing_gate_ids = tuple(gate_id for gate_id in required if gate_id not in by_id)
    failed_gate_ids = tuple(gate_id for gate_id in required if by_id.get(gate_id) == "FAIL")
    unknown_gate_ids = tuple(
        gate_id for gate_id in required if by_id.get(gate_id) == "UNKNOWN"
    )
    warned_gate_ids = tuple(gate_id for gate_id in required if by_id.get(gate_id) == "WARN")
    eligible = not (missing_gate_ids or failed_gate_ids or unknown_gate_ids or warned_gate_ids) and all(
        by_id.get(gate_id) == "PASS" for gate_id in required
    )
    code = X3D_ALLOW_FINISH if eligible else "X3D_BLOCKED"
    created_at = datetime.now(timezone.utc).isoformat()
    gate_verdicts = {
        result: tuple(
            gate_id for gate_id in required if by_id.get(gate_id) == result
        )
        for result in ("PASS", "FAIL", "UNKNOWN", "WARN", "NOT_APPLICABLE")
    }
    blockers = tuple(
        f"required_gate_not_pass:{gate_id}"
        for gate_id in (*missing_gate_ids, *failed_gate_ids, *unknown_gate_ids, *warned_gate_ids)
    )
    review = ExitReviewPacket(
        run_id=run_id,
        request_id=request_id,
        trace_root=trace_root,
        app_id=gate_profile.app_id,
        task_class=gate_profile.task_class,
        created_at=created_at,
        gate_mesh_summary=summary,
        x1_checkout_result={
            "overall_pass": eligible,
            "blockers": list(blockers),
            "checks": {
                "X1_LOCAL_EXIT": {
                    "status": "PASS" if eligible else "FAIL",
                    "reason": "all required gates passed" if eligible else "required gate did not pass",
                }
            },
        },
        x2_aggregation_result={
            "gate_verdicts": {key: list(value) for key, value in gate_verdicts.items()},
            "x1_integration": {"overall_pass": eligible, "blockers": list(blockers)},
        },
        gate_results=gate_rows,
        eligible=eligible,
    )
    sealed = exit_input.sealed_l2_artifact
    decisive_blocker_ids = (*missing_gate_ids, *failed_gate_ids, *unknown_gate_ids, *warned_gate_ids)
    receipt = ExitDispositionReceipt(
        request_id=request_id,
        run_id=run_id,
        trace_root=trace_root,
        x3_code=code,
        app_id=gate_profile.app_id,
        exit_profile_ref=gate_profile.profile_id,
        task_class=gate_profile.task_class,
        workflow_ref=sealed.workflow_ref,
        sealed_workflow_package_ref=sealed.package_id,
        gate_mesh_result_ref=str(summary.get("deterministic_digest") or ""),
        required_gates_passed=eligible,
        hard_fail_count=len(failed_gate_ids),
        unknown_count=len(unknown_gate_ids),
        missing_gate_count=len(missing_gate_ids),
        warn_count=len(warned_gate_ids),
        decisive_reason=(
            "All required exit gates passed" if eligible else "One or more required exit gates did not pass"
        ),
        decisive_blocker_codes=tuple(
            str(by_id.get(gate_id) or "MISSING") for gate_id in decisive_blocker_ids
        ),
        decisive_blocker_gate_ids=decisive_blocker_ids,
        policy_hash=_digest({"policy_id": exit_policy.policy_id}),
        created_at=created_at,
        output_artifact_digest=sealed.merged_content_digest,
    )
    exhaust = RuntimeExhaustBundle(
        run_id=run_id,
        trace_root=trace_root,
        request_id=request_id,
        route_contract_ref=sealed.route_contract_ref,
        sealed_result_ref=sealed.package_id,
        gate_mesh_result_ref=str(summary.get("deterministic_digest") or ""),
        created_after_exit=True,
        current_run_closed=eligible,
        created_at=created_at,
    )
    return review, receipt, exhaust


def evaluate_and_emit(*_args: Any, **_kwargs: Any) -> CompatRecord:
    return CompatRecord()


def exit_finalize_apps_research(*_args: Any, **_kwargs: Any) -> CompatRecord:
    return CompatRecord()


def __getattr__(name: str) -> Any:
    """Supply optional local compatibility names without an external import."""

    if name.startswith("_emit_"):
        value: Any = _emit_noop
    elif name.isupper():
        value = name
    elif name.endswith(("Error", "MismatchError")):
        value = AppRuntimeCompatibilityError
    else:
        value = _CompatMeta(name, (CompatRecord,), {})
    globals()[name] = value
    return value


class LayerSegment(metaclass=_CompatMeta):
    pass


class _LifecycleTraceContract:
    LayerSegment = LayerSegment

    def __getattr__(self, _name: str) -> Callable[..., None]:
        return _emit_noop


lifecycle_trace_contract = _LifecycleTraceContract()


__all__ = [
    "AppRuntimeCompatibilityError",
    "BGE_M3_EMBEDDING_DIMENSION",
    "BGE_M3_MODEL_ID",
    "AuthorityLevel",
    "AuthoritySlot",
    "CommitRequest",
    "CompatRecord",
    "CompiledPromptArtifact",
    "DurableWriteGateway",
    "Dimension",
    "EmbeddingMixin",
    "FinalEvidenceContract",
    "ExitDispositionReceipt",
    "ExitInput",
    "ExitPolicy",
    "ExitReviewPacket",
    "GateMeshResult",
    "GateProfile",
    "GateVerdict",
    "GraderError",
    "GraderClass",
    "GoogleJudge",
    "JudgeResponse",
    "L1PlanContract",
    "L6PipelineState",
    "LayerSegment",
    "PackageDigestMismatchError",
    "ReadSurfaceRefreshPlan",
    "RequestEnvelope",
    "RollbackPlan",
    "RouteContract",
    "RuntimeCustomizationPackage",
    "RuntimeExhaustBundle",
    "SealedWorkflowPackage",
    "SealedL2Artifact",
    "SemanticCacheMixin",
    "SynthesisProvenance",
    "StateDiff",
    "UnknownPackageFieldError",
    "ValidatedRequest",
    "X3Disposition",
    "X3D_ALLOW_FINISH",
    "_resolve_device",
    "build_apps_eval_alignment",
    "build_future_run_proposals",
    "build_gate_mesh_result",
    "build_l6_apps_eval_grain_parity",
    "build_microstep_coverage",
    "build_microstep_patterns",
    "build_microstep_rca",
    "compute_deterministic_digest",
    "compute_state_diffs_digest",
    "evaluate_and_emit",
    "exit_bind_and_finalize_apps_research",
    "exit_finalize_apps_research",
    "get_default_gateway",
    "lifecycle_trace_contract",
    "run_6a",
    "run_observer",
    "stamp_digest",
    "traces_execute",
    "wrap_synthesis_output",
    "write_span_artifacts",
]
