"""Apps RG-local assignment for the L1 cognitive paired experiment.

The assignment is deliberately an ingress-validated, source-bound input.  It
does not select a route, invoke a model, change evidence, or promote an output.
Its sole purpose is to ensure that a v2 control run cannot accidentally carry
the v3 cognitive plan that differentiates the candidate arm.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final


L1_COGNITIVE_TREATMENT_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_treatment.v1"
)
L1_COGNITIVE_TREATMENT_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
L1_COGNITIVE_TREATMENT_AUTHORITY: Final[str] = "EXPERIMENT_ASSIGNMENT_ONLY"
L1_COGNITIVE_V2_CONTROL_ARM: Final[str] = "l1_v2_control"
L1_COGNITIVE_V3_CANDIDATE_ARM: Final[str] = "l1_cognitive_v3"
L1_COGNITIVE_TREATMENT_ARMS: Final[frozenset[str]] = frozenset(
    {L1_COGNITIVE_V2_CONTROL_ARM, L1_COGNITIVE_V3_CANDIDATE_ARM}
)
_VALID_ASSIGNMENT_ORIGINS: Final[frozenset[str]] = frozenset(
    {"U0_VALIDATED_INGRESS", "LEGACY_L1_DEFAULT"}
)


class L1CognitiveTreatmentError(ValueError):
    """Raised when the Apps RG cognitive experiment arm is malformed."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def l1_cognitive_treatment_digest(treatment: Mapping[str, Any]) -> str:
    """Return the stable treatment digest excluding its declared digest."""

    body = dict(treatment)
    body.pop("treatment_digest", None)
    return "sha256:" + hashlib.sha256(
        _canonical_json(body).encode("utf-8")
    ).hexdigest()


def build_l1_cognitive_treatment(
    arm: str | None,
    *,
    assignment_origin: str,
) -> dict[str, Any]:
    """Build one validated treatment assignment without retaining raw inputs."""

    # The cognitive path is an experiment.  Missing ingress assignment must
    # preserve the existing v2 behavior; candidate exposure requires an
    # explicit U0-bound assignment and can never be inferred from omission.
    normalized_arm = str(arm or L1_COGNITIVE_V2_CONTROL_ARM).strip()
    normalized_origin = str(assignment_origin or "").strip()
    if normalized_arm not in L1_COGNITIVE_TREATMENT_ARMS:
        raise L1CognitiveTreatmentError(
            "l1_cognitive_treatment_arm must be one of "
            f"{sorted(L1_COGNITIVE_TREATMENT_ARMS)!r}"
        )
    if normalized_origin not in _VALID_ASSIGNMENT_ORIGINS:
        raise L1CognitiveTreatmentError("l1 cognitive treatment origin is invalid")

    treatment: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_TREATMENT_SCHEMA_VERSION,
        "app_scope": L1_COGNITIVE_TREATMENT_APP_SCOPE,
        "authority_class": L1_COGNITIVE_TREATMENT_AUTHORITY,
        "assignment_origin": normalized_origin,
        "arm": normalized_arm,
        "v3_cognitive_plan_enabled": normalized_arm
        == L1_COGNITIVE_V3_CANDIDATE_ARM,
        "automatic_promotion": False,
        "treatment_digest": "",
    }
    treatment["treatment_digest"] = l1_cognitive_treatment_digest(treatment)
    return treatment


def validate_l1_cognitive_treatment(treatment: Mapping[str, Any]) -> None:
    """Fail closed unless the assignment declares exactly one safe experiment arm."""

    if not isinstance(treatment, Mapping):
        raise L1CognitiveTreatmentError("l1 cognitive treatment must be a mapping")
    if treatment.get("schema_version") != L1_COGNITIVE_TREATMENT_SCHEMA_VERSION:
        raise L1CognitiveTreatmentError("unsupported l1 cognitive treatment schema")
    if treatment.get("app_scope") != L1_COGNITIVE_TREATMENT_APP_SCOPE:
        raise L1CognitiveTreatmentError("l1 cognitive treatment is outside apps_rg_v2")
    if treatment.get("authority_class") != L1_COGNITIVE_TREATMENT_AUTHORITY:
        raise L1CognitiveTreatmentError("l1 cognitive treatment authority is invalid")
    arm = str(treatment.get("arm") or "").strip()
    origin = str(treatment.get("assignment_origin") or "").strip()
    if arm not in L1_COGNITIVE_TREATMENT_ARMS:
        raise L1CognitiveTreatmentError("l1 cognitive treatment arm is invalid")
    if origin not in _VALID_ASSIGNMENT_ORIGINS:
        raise L1CognitiveTreatmentError("l1 cognitive treatment origin is invalid")
    if treatment.get("v3_cognitive_plan_enabled") != (
        arm == L1_COGNITIVE_V3_CANDIDATE_ARM
    ):
        raise L1CognitiveTreatmentError(
            "l1 cognitive treatment plan-emission flag conflicts with arm"
        )
    if treatment.get("automatic_promotion") is not False:
        raise L1CognitiveTreatmentError(
            "l1 cognitive treatment cannot authorize promotion"
        )
    if treatment.get("treatment_digest") != l1_cognitive_treatment_digest(treatment):
        raise L1CognitiveTreatmentError("l1 cognitive treatment digest mismatch")


def treatment_from_task_spec(task_spec: Mapping[str, Any]) -> dict[str, Any]:
    """Read a U0 assignment, with a marked legacy control default for old callers."""

    raw = task_spec.get("l1_cognitive_treatment")
    if raw is None:
        return build_l1_cognitive_treatment(
            L1_COGNITIVE_V2_CONTROL_ARM,
            assignment_origin="LEGACY_L1_DEFAULT",
        )
    if not isinstance(raw, Mapping):
        raise L1CognitiveTreatmentError("l1_cognitive_treatment must be a mapping")
    treatment = dict(raw)
    validate_l1_cognitive_treatment(treatment)
    return treatment


__all__ = [
    "L1_COGNITIVE_TREATMENT_APP_SCOPE",
    "L1_COGNITIVE_TREATMENT_ARMS",
    "L1_COGNITIVE_TREATMENT_AUTHORITY",
    "L1_COGNITIVE_TREATMENT_SCHEMA_VERSION",
    "L1_COGNITIVE_V2_CONTROL_ARM",
    "L1_COGNITIVE_V3_CANDIDATE_ARM",
    "L1CognitiveTreatmentError",
    "build_l1_cognitive_treatment",
    "l1_cognitive_treatment_digest",
    "treatment_from_task_spec",
    "validate_l1_cognitive_treatment",
]
