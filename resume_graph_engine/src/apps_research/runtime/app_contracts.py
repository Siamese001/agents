"""Application-owned contracts for the Apps Research ingress profile."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Callable


POSTURE_READ_ONLY = "read_only"


class TaskClass(str, Enum):
    COMPANY_BRIEF = "company_brief"
    RESEARCH_SUBSTRATE = "research_substrate"
    UPLOADED_BRIEFING_NORMALIZATION = "uploaded_briefing_normalization"


class UnknownPackageFieldError(ValueError):
    def __init__(self, *, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


class PackageDigestMismatchError(ValueError):
    def __init__(self, *, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"runtime customization package digest mismatch: expected={expected} actual={actual}")


@dataclass
class RuntimeCustomizationPackage:
    package_id: str
    package_version: str = "1.0.0"
    app_id: str = "apps_research"
    task_class: TaskClass | str = TaskClass.COMPANY_BRIEF
    spine_profile_ref: str = ""
    route_profile_ref: str = ""
    retrieval_profile_ref: str = ""
    cache_profile_ref: str = ""
    source_mix_policy_ref: str = ""
    freshness_policy_ref: str = ""
    runtime_gate_profile_ref: str = ""
    exit_profile_ref: str = ""
    judge_profile_ref: str = ""
    grader_roster_ref: str = ""
    eval_rubric_ref: str = ""
    threshold_profile_ref: str = ""
    rubric_output_map_ref: str = ""
    negative_controls_ref: str = ""
    prompt_profile_ref: str = ""
    prompt_bom_ref: str = ""
    output_schema_ref: str = ""
    research_substrate_schema_ref: str = ""
    learning_profile_ref: str = ""
    meta_feedback_profile_ref: str = ""
    briefing_normalization_policy_ref: str = ""
    entity_resolution_policy_ref: str = ""
    capability_profile_ref: str = ""
    provider_profile_ref: str = ""
    write_policy: str = POSTURE_READ_ONLY
    required_runtime_gates: list[str] = field(default_factory=list)
    required_exit_gates: list[str] = field(default_factory=list)
    conditional_exit_gates: list[str] = field(default_factory=list)
    judge_execution_policy: str = "local_only"
    eval_execution_policy: str = "local_only"
    meta_feedback_policy: str = "l6_only"
    l6_learning_policy: str = "future_run_only"
    semantic_cache_policy: str = "research_substrate_only"
    cross_app_reuse_policy: str = "delegated_only"
    package_digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.task_class, TaskClass):
            self.task_class = TaskClass(str(self.task_class))
        if not self.package_digest:
            self.package_digest = self._compute_digest()

    def _compute_digest(self) -> str:
        payload = self.to_dict(include_digest=False)
        return sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def verify_digest(self) -> bool:
        return bool(self.package_digest) and self.package_digest == self._compute_digest()

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["task_class"] = self.task_class.value
        if not include_digest:
            payload.pop("package_digest", None)
        return payload


@dataclass(frozen=True)
class PackageValidationReceipt:
    package_id: str
    package_version: str
    task_class: str
    validation_passed: bool
    unknown_fields_found: list[str]
    digest_verified: bool
    timestamp_iso: str


@dataclass(frozen=True)
class AuthorityValidationReceipt:
    allowed: bool
    passed: bool
    forbidden_fields_detected: tuple[str, ...]
    timestamp_iso: str


@dataclass
class AppsRgIngressPayload:
    target_company: str = ""
    target_role: str = ""
    target_level: str = ""
    app_id: str = "apps_research"
    task_class: str = TaskClass.COMPANY_BRIEF.value
    user_constraints: dict[str, Any] = field(default_factory=dict)
    output_preferences: dict[str, Any] = field(default_factory=dict)
    manual_brief_path: str | None = None
    auto_research_internal: bool = False
    auto_research_tavily: bool = False
    idempotency_key: str | None = None
    payload_digest: str = ""
    app_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestEnvelope:
    payload: AppsRgIngressPayload
    request_id: str = ""
    run_id: str = ""
    trace_id: str = ""
    tenant_id: str = ""
    submitted_at: str = ""


@dataclass
class ValidatedRequest:
    request_id: str
    run_id: str
    app_id: str
    task_class: str
    payload_digest: str
    authority_validation_receipt: AuthorityValidationReceipt
    trace_id: str
    tenant_id: str
    target_level: str = ""
    schema_version: str = ""
    posture: str = POSTURE_READ_ONLY
    l5_certification_ref: str = ""
    app_payload: dict[str, Any] = field(default_factory=dict)
    reflection_receipt: Any = None


@dataclass(frozen=True)
class AppRuntimeProfile:
    app_id: str
    required_fields: tuple[str, ...]
    parse: Callable[..., Any]
    u0: Callable[..., Any]
    l1: Callable[..., Any]
    l0: Callable[..., Any]
    c0: Callable[..., Any]
    pa: Callable[..., Any]
    l2: Callable[..., Any]
    exit: Callable[..., Any]
    profile_version: str


__all__ = [
    "AppRuntimeProfile",
    "AppsRgIngressPayload",
    "AuthorityValidationReceipt",
    "POSTURE_READ_ONLY",
    "PackageDigestMismatchError",
    "PackageValidationReceipt",
    "RequestEnvelope",
    "RuntimeCustomizationPackage",
    "TaskClass",
    "UnknownPackageFieldError",
    "ValidatedRequest",
]
