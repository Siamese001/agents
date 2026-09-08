"""W0, apps_rg_v2-only baseline capture for L1 reasoning changes.

The baseline is observational. It snapshots verified L1 planning semantics and
already-produced stage artifacts; it never routes, retrieves, composes a prompt,
executes a model, writes a product output, or authorizes an exit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_planning_capsule import (
    PlanningCapsuleIntegrityError,
    verify_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.contracts.failure_aware_replan import (
    FailureAwareReplanError,
    validate_failure_aware_replan,
)
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    PlanExecutionReconciliationError,
    validate_plan_execution_reconciliation,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_REASONING_BASELINE_SCHEMA_VERSION: Final[str] = "apps_rg.l1_reasoning_baseline.v1"
L1_REASONING_BASELINE_AUTHORITY: Final[str] = "OBSERVATION_ONLY_W0"
L1_REASONING_BASELINE_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_STAGE_NAMES: Final[tuple[str, ...]] = ("l0", "c0", "pa", "l2", "w1", "w2")


class L1ReasoningBaselineError(ValueError):
    """Raised when a W0 baseline is malformed or not tied to its L1 plan."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def baseline_digest(snapshot: Mapping[str, Any]) -> str:
    """Return the stable digest of a baseline, excluding its own digest field."""

    body = dict(snapshot)
    body.pop("baseline_digest", None)
    return "sha256:" + hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    return json.loads(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _value(source: Any, field: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(field, default)
    return getattr(source, field, default)


def _required_string(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1ReasoningBaselineError(f"{field} is required")
    return normalized


def _strings(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise L1ReasoningBaselineError(f"{field} must be a sequence")
    rows = [str(item or "").strip() for item in value]
    if any(not item for item in rows) or len(set(rows)) != len(rows):
        raise L1ReasoningBaselineError(f"{field} must contain unique non-empty values")
    return rows


def _relative_ref(value: Any, *, field: str, required: bool = False) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        if required:
            raise L1ReasoningBaselineError(f"{field} is required")
        return ""
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise L1ReasoningBaselineError(f"{field} must be a relative artifact reference")
    return path.as_posix()


def _identity_from_capsule(capsule: Mapping[str, Any]) -> dict[str, str]:
    return {
        "request_id": _required_string(capsule.get("request_id"), field="request_id"),
        "run_id": _required_string(capsule.get("run_id"), field="run_id"),
        "trace_id": _required_string(capsule.get("trace_id"), field="trace_id"),
    }


def _assert_stage_identity(
    stage: Any,
    *,
    identity: Mapping[str, str],
    stage_name: str,
) -> None:
    for field, expected in identity.items():
        actual = str(_value(stage, field, "") or "").strip()
        if actual and actual != expected:
            raise L1ReasoningBaselineError(
                f"{stage_name}.{field} does not match the L1 planning capsule"
            )


def _require_mapping(value: Any, *, field: str) -> dict[str, Any]:
    out = _mapping(value)
    if not out:
        raise L1ReasoningBaselineError(f"{field} must be a non-empty mapping")
    return out


def _planning_projection(capsule: Mapping[str, Any]) -> dict[str, Any]:
    """Return a comparison-safe plan projection without raw JD or resume text."""

    try:
        verified = verify_apps_rg_l1_planning_capsule(capsule)
    except PlanningCapsuleIntegrityError as exc:
        raise L1ReasoningBaselineError(f"invalid L1 planning capsule: {exc}") from exc

    prior_refs = capsule.get("planning_prior_refs")
    if not isinstance(prior_refs, Sequence) or isinstance(prior_refs, (str, bytes)):
        raise L1ReasoningBaselineError("L1 planning prior binding is missing")
    prior = _require_mapping(
        prior_refs[0] if prior_refs else None,
        field="planning_prior",
    )
    intent = _require_mapping(capsule.get("intent_frame"), field="intent_frame")
    obligation_plan = _require_mapping(
        capsule.get("jd_obligation_plan"),
        field="jd_obligation_plan",
    )
    obligations = obligation_plan.get("obligations")
    if not isinstance(obligations, Sequence) or isinstance(obligations, (str, bytes)):
        raise L1ReasoningBaselineError("jd_obligation_plan.obligations is invalid")

    sanitized_obligations: list[dict[str, Any]] = []
    for raw in obligations:
        row = _require_mapping(raw, field="jd_obligation_plan.obligation")
        text = _required_string(
            row.get("obligation_text"),
            field="jd_obligation_plan.obligation_text",
        )
        sanitized_obligations.append(
            {
                "obligation_id": _required_string(
                    row.get("obligation_id"),
                    field="jd_obligation_plan.obligation_id",
                ),
                "obligation_text_digest": "sha256:"
                + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "source_kind": str(row.get("source_kind") or ""),
                "criticality": str(row.get("criticality") or ""),
                "mapped_unit_ids": _strings(
                    row.get("mapped_unit_ids"),
                    field="jd_obligation_plan.mapped_unit_ids",
                ),
                "coverage_status": str(row.get("coverage_status") or ""),
                "escalation_reason": str(row.get("escalation_reason") or ""),
            }
        )

    source_binding = _require_mapping(
        obligation_plan.get("source_binding"),
        field="jd_obligation_plan.source_binding",
    )
    return {
        "capsule_digest": _required_string(
            verified.get("capsule_digest"),
            field="capsule_digest",
        ),
        "planning_profile": {
            "ref": _required_string(prior.get("ref"), field="planning_profile.ref"),
            "digest": _required_string(
                prior.get("digest"),
                field="planning_profile.digest",
            ),
        },
        "planning_status": _required_string(
            verified.get("planning_status"),
            field="planning_status",
        ),
        "intent": {
            "generation_mode": str(intent.get("generation_mode") or ""),
            "deliverable": str(intent.get("deliverable") or ""),
            "assumptions": _strings(
                intent.get("assumptions"),
                field="intent_frame.assumptions",
            ),
            "intent_digest": "sha256:"
            + hashlib.sha256(
                _canonical_json(_plain(intent)).encode("utf-8")
            ).hexdigest(),
        },
        "ambiguity_register": _plain(capsule.get("ambiguity_register")),
        "work_units": _plain(capsule.get("work_units")),
        "dependency_sketch": _plain(capsule.get("dependency_sketch")),
        "completion_criteria": _plain(capsule.get("completion_criteria")),
        "jd_obligation_plan": {
            "schema_version": str(obligation_plan.get("schema_version") or ""),
            "source_binding": {
                "source_class": str(source_binding.get("source_class") or ""),
                "jd_hash": str(source_binding.get("jd_hash") or ""),
                "inline_text_digest": str(
                    source_binding.get("inline_text_digest") or ""
                ),
            },
            "extraction_status": str(obligation_plan.get("extraction_status") or ""),
            "obligation_plan_digest": str(
                obligation_plan.get("obligation_plan_digest") or ""
            ),
            "obligations": sanitized_obligations,
            "coverage": _plain(obligation_plan.get("coverage")),
        },
        "evidence_plan": _plain(capsule.get("evidence_plan")),
        "prompt_plan": _plain(capsule.get("prompt_plan")),
        "cognition_plan": _plain(capsule.get("cognition_plan")),
        "route_feature_hints": _plain(capsule.get("route_feature_hints")),
    }


def _route_projection(route: Any, *, identity: Mapping[str, str]) -> dict[str, Any]:
    if route is None:
        return {}
    _assert_stage_identity(route, identity=identity, stage_name="l0")
    gates = _value(route, "route_gate_receipts", ()) or ()
    if not isinstance(gates, Sequence) or isinstance(gates, (str, bytes)):
        raise L1ReasoningBaselineError("l0.route_gate_receipts must be a sequence")
    gate_rows = [
        {
            "gate_id": str(_value(gate, "gate_id", "") or ""),
            "verdict": str(_value(gate, "verdict", "") or ""),
            "score": _value(gate, "score", None),
        }
        for gate in gates
    ]
    return {
        "route_id": str(_value(route, "route_id", "") or ""),
        "route_family": str(_value(route, "route_family", "") or ""),
        "execution_form": str(_value(route, "execution_form", "") or ""),
        "route_digest": str(_value(route, "route_digest", "") or ""),
        "route_gate_digest": "sha256:"
        + hashlib.sha256(_canonical_json(gate_rows).encode("utf-8")).hexdigest(),
        "gate_ids": [row["gate_id"] for row in gate_rows],
    }


def _c0_projection(fec: Any, *, identity: Mapping[str, str]) -> dict[str, Any]:
    if fec is None:
        return {}
    _assert_stage_identity(fec, identity=identity, stage_name="c0")
    audit_refs = _strings(_value(fec, "audit_refs", ()), field="c0.audit_refs")
    evidence_items = _value(fec, "evidence_items", ()) or ()
    if not isinstance(evidence_items, Sequence) or isinstance(
        evidence_items, (str, bytes)
    ):
        raise L1ReasoningBaselineError("c0.evidence_items must be a sequence")
    return {
        "support_status": str(_value(fec, "support_status", "") or ""),
        "support_target_met": bool(_value(fec, "support_target_met", False)),
        "final_evidence_digest": str(_value(fec, "final_evidence_digest", "") or ""),
        "retrieval_plan_ref": str(_value(fec, "retrieval_plan_ref", "") or ""),
        "audit_refs": sorted(audit_refs),
        "evidence_item_count": len(evidence_items),
    }


def _pa_projection(artifact: Any, *, identity: Mapping[str, str]) -> dict[str, Any]:
    if artifact is None:
        return {}
    _assert_stage_identity(artifact, identity=identity, stage_name="pa")
    hashes = _mapping(_value(artifact, "component_hash_map", {}))
    lineage = _mapping(_value(artifact, "slot_lineage_map", {}))
    return {
        "component_hash_map": {
            str(key): str(value)
            for key, value in sorted(hashes.items(), key=lambda item: str(item[0]))
        },
        "slot_lineage_digest": "sha256:"
        + hashlib.sha256(_canonical_json(_plain(lineage)).encode("utf-8")).hexdigest(),
        "compiled_prompt_digest": str(
            _value(artifact, "compiled_prompt_digest", "")
            or _value(artifact, "prompt_digest", "")
            or ""
        ),
    }


def _l2_projection(rows: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise L1ReasoningBaselineError("l2 receipts must be a sequence")
    out: list[dict[str, Any]] = []
    observed_lanes: set[str] = set()
    for raw in rows:
        row = _require_mapping(raw, field="l2 receipt")
        lane_id = _required_string(
            row.get("lane_id") or row.get("section_id"),
            field="l2.lane_id",
        )
        if lane_id in observed_lanes:
            raise L1ReasoningBaselineError(f"duplicate l2.lane_id: {lane_id}")
        observed_lanes.add(lane_id)
        control_receipt = row.get("reasoning_execution_receipt")
        control_digest = ""
        if control_receipt is not None:
            control_digest = (
                "sha256:"
                + hashlib.sha256(
                    _canonical_json(_plain(control_receipt)).encode("utf-8")
                ).hexdigest()
            )
        out.append(
            {
                "lane_id": lane_id,
                "status": str(row.get("status") or ""),
                "artifact_ref": _relative_ref(
                    row.get("artifact_ref") or row.get("output_ref"),
                    field="l2.artifact_ref",
                ),
                "reasoning_execution_receipt_ref": _relative_ref(
                    row.get("reasoning_execution_receipt_ref"),
                    field="l2.reasoning_execution_receipt_ref",
                ),
                "reasoning_execution_receipt_digest": control_digest,
            }
        )
    return sorted(out, key=lambda row: row["lane_id"])


def _w1_projection(
    receipt: Mapping[str, Any] | None,
    *,
    capsule: Mapping[str, Any],
    identity: Mapping[str, str],
) -> dict[str, Any]:
    if receipt is None:
        return {}
    try:
        validate_plan_execution_reconciliation(receipt)
    except (PlanExecutionReconciliationError, ValueError) as exc:
        raise L1ReasoningBaselineError(f"invalid W1 receipt: {exc}") from exc
    _assert_stage_identity(receipt, identity=identity, stage_name="w1")
    plan = _require_mapping(receipt.get("plan"), field="w1.plan")
    capsule_digest = str(capsule.get("capsule_digest") or "")
    if plan.get("capsule_digest") != capsule_digest:
        raise L1ReasoningBaselineError("W1 receipt is bound to a different capsule")
    return {
        "receipt_digest": _required_string(
            receipt.get("receipt_digest"),
            field="w1.receipt_digest",
        ),
        "summary": _plain(receipt.get("summary")),
        "unit_outcomes": _plain(receipt.get("unit_outcomes")),
    }


def _w2_projection(
    decision: Mapping[str, Any] | None,
    *,
    capsule: Mapping[str, Any],
    w1_receipt: Mapping[str, Any] | None,
    identity: Mapping[str, str],
) -> dict[str, Any]:
    if decision is None:
        return {}
    if w1_receipt is None:
        raise L1ReasoningBaselineError("W2 baseline capture requires its W1 receipt")
    try:
        validate_failure_aware_replan(
            decision,
            plan_capsule=capsule,
            plan_execution_receipt=w1_receipt,
        )
    except (FailureAwareReplanError, ValueError) as exc:
        raise L1ReasoningBaselineError(f"invalid W2 replan decision: {exc}") from exc
    _assert_stage_identity(decision, identity=identity, stage_name="w2")
    return {
        "decision_digest": _required_string(
            decision.get("decision_digest"),
            field="w2.decision_digest",
        ),
        "replan_status": str(decision.get("replan_status") or ""),
        "failure_classifications": _plain(decision.get("failure_classifications")),
        "replan_actions": _plain(decision.get("replan_actions")),
        "replan_revision": _plain(decision.get("replan_revision")),
    }


def build_l1_reasoning_baseline(
    *,
    baseline_id: str,
    capsule: Mapping[str, Any],
    route: Any = None,
    final_evidence_contract: Any = None,
    prompt_artifact: Any = None,
    l2_receipts: Sequence[Mapping[str, Any]] | None = None,
    plan_execution_receipt: Mapping[str, Any] | None = None,
    replan_decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a privacy-safe, digest-bound W0 baseline from observed artifacts."""

    baseline_name = _required_string(baseline_id, field="baseline_id")
    source_capsule = _mapping(capsule)
    if not source_capsule:
        raise L1ReasoningBaselineError("capsule must be a non-empty mapping")
    identity = _identity_from_capsule(source_capsule)
    plan = _planning_projection(source_capsule)
    stages = {
        "l0": _route_projection(route, identity=identity),
        "c0": _c0_projection(final_evidence_contract, identity=identity),
        "pa": _pa_projection(prompt_artifact, identity=identity),
        "l2": _l2_projection(l2_receipts),
        "w1": _w1_projection(
            plan_execution_receipt,
            capsule=source_capsule,
            identity=identity,
        ),
        "w2": _w2_projection(
            replan_decision,
            capsule=source_capsule,
            w1_receipt=plan_execution_receipt,
            identity=identity,
        ),
    }
    snapshot: dict[str, Any] = {
        "schema_version": L1_REASONING_BASELINE_SCHEMA_VERSION,
        "authority_class": L1_REASONING_BASELINE_AUTHORITY,
        "app_scope": L1_REASONING_BASELINE_APP_SCOPE,
        "baseline_id": baseline_name,
        "identity": identity,
        "plan": plan,
        "stage_presence": {name: bool(stages[name]) for name in _STAGE_NAMES},
        "stage_observations": stages,
        "execution_authority_assertions": {
            "does_not_route": True,
            "does_not_retrieve": True,
            "does_not_assemble_prompt": True,
            "does_not_execute_model": True,
            "does_not_authorize_exit": True,
        },
    }
    snapshot["baseline_digest"] = baseline_digest(snapshot)
    validate_l1_reasoning_baseline(snapshot)
    return snapshot


def validate_l1_reasoning_baseline(snapshot: Mapping[str, Any]) -> None:
    """Validate an emitted baseline without re-running any pipeline stage."""

    if not isinstance(snapshot, Mapping):
        raise L1ReasoningBaselineError("baseline must be a mapping")
    if snapshot.get("schema_version") != L1_REASONING_BASELINE_SCHEMA_VERSION:
        raise L1ReasoningBaselineError("unsupported L1 reasoning baseline schema")
    if snapshot.get("authority_class") != L1_REASONING_BASELINE_AUTHORITY:
        raise L1ReasoningBaselineError("invalid L1 reasoning baseline authority")
    if snapshot.get("app_scope") != L1_REASONING_BASELINE_APP_SCOPE:
        raise L1ReasoningBaselineError("baseline is outside apps_rg_v2 scope")
    _required_string(snapshot.get("baseline_id"), field="baseline_id")
    identity = _mapping(snapshot.get("identity"))
    for field in ("request_id", "run_id", "trace_id"):
        _required_string(identity.get(field), field=f"identity.{field}")
    plan = _require_mapping(snapshot.get("plan"), field="plan")
    for field in ("capsule_digest", "planning_profile", "planning_status"):
        if field not in plan:
            raise L1ReasoningBaselineError(f"plan.{field} is required")
    presence = _mapping(snapshot.get("stage_presence"))
    observations = _mapping(snapshot.get("stage_observations"))
    if set(presence) != set(_STAGE_NAMES) or set(observations) != set(_STAGE_NAMES):
        raise L1ReasoningBaselineError("baseline stage coverage is incomplete")
    for name in _STAGE_NAMES:
        if not isinstance(presence[name], bool):
            raise L1ReasoningBaselineError(f"stage_presence.{name} must be boolean")
        if not isinstance(observations[name], Mapping) and name != "l2":
            raise L1ReasoningBaselineError(
                f"stage_observations.{name} must be a mapping"
            )
        if name == "l2" and not isinstance(observations[name], Sequence):
            raise L1ReasoningBaselineError("stage_observations.l2 must be a sequence")
        if presence[name] != bool(observations[name]):
            raise L1ReasoningBaselineError(
                f"stage_presence.{name} conflicts with observed data"
            )
    assertions = _mapping(snapshot.get("execution_authority_assertions"))
    expected_assertions = {
        "does_not_route",
        "does_not_retrieve",
        "does_not_assemble_prompt",
        "does_not_execute_model",
        "does_not_authorize_exit",
    }
    if any(assertions.get(name) is not True for name in expected_assertions):
        raise L1ReasoningBaselineError(
            "baseline execution authority assertions are incomplete"
        )
    if snapshot.get("baseline_digest") != baseline_digest(snapshot):
        raise L1ReasoningBaselineError("baseline digest mismatch")


def compare_l1_reasoning_baseline(
    snapshot: Mapping[str, Any],
    *,
    capsule: Mapping[str, Any],
) -> None:
    """Fail closed when a current capsule differs from a frozen W0 baseline."""

    validate_l1_reasoning_baseline(snapshot)
    source_capsule = _mapping(capsule)
    if not source_capsule:
        raise L1ReasoningBaselineError("capsule must be a non-empty mapping")
    expected_identity = _identity_from_capsule(source_capsule)
    if snapshot.get("identity") != expected_identity:
        raise L1ReasoningBaselineError(
            "baseline identity does not match the current L1 capsule"
        )
    expected_plan = _planning_projection(source_capsule)
    if snapshot.get("plan") != expected_plan:
        raise L1ReasoningBaselineError(
            "current L1 planning semantics differ from the frozen baseline"
        )


def write_l1_reasoning_baseline(
    *,
    output_path: Path,
    baseline: Mapping[str, Any],
) -> Path:
    """Validate and write a baseline artifact at an explicit path."""

    validate_l1_reasoning_baseline(baseline)
    path = Path(output_path)
    sr.write_stage_receipt(path, baseline)
    return path


def emit_l1_reasoning_baseline(
    *,
    artifact_dir: Path,
    baseline: Mapping[str, Any],
) -> Path:
    """Write the canonical W0 baseline filename beneath one run artifact root."""

    return write_l1_reasoning_baseline(
        output_path=Path(artifact_dir) / sr.FILENAME_L1_REASONING_BASELINE,
        baseline=baseline,
    )


__all__ = [
    "L1_REASONING_BASELINE_APP_SCOPE",
    "L1_REASONING_BASELINE_AUTHORITY",
    "L1_REASONING_BASELINE_SCHEMA_VERSION",
    "L1ReasoningBaselineError",
    "baseline_digest",
    "build_l1_reasoning_baseline",
    "compare_l1_reasoning_baseline",
    "emit_l1_reasoning_baseline",
    "validate_l1_reasoning_baseline",
    "write_l1_reasoning_baseline",
]
