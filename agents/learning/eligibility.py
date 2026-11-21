"""Learning eligibility firewall, anti-synthetic approval checks, and effort hysteresis guard."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence

_TEST_MARKERS = (
    "pytest",
    "test_",
    "mock_",
    "synthetic_",
    "dummy_",
    "fixture_",
    "fake_",
)

_SYNTHETIC_APPROVAL_MARKERS = (
    "auto-approved",
    "auto_approved",
    "autonomous_policy_supervisor",
    "stop-hook",
    "stop_hook",
    "synthetic_approval",
    "bypass_hitl",
    "self_approved",
    "system_auto_override",
)

EffortLevel = Literal["LOW", "MEDIUM", "HIGH", "XHIGH"]
_EFFORT_ORDER: tuple[EffortLevel, ...] = ("LOW", "MEDIUM", "HIGH", "XHIGH")


def is_test_record(record: Mapping[str, Any]) -> bool:
    """Return True if record originates from tests, mocks, or synthetic fixtures."""
    if record.get("is_test") is True or record.get("synthetic") is True:
        return True
    for field in ("run_id", "session_id", "trace_id", "actor", "source_surface"):
        val = str(record.get(field) or "").strip().lower()
        if any(val.startswith(m) or f":{m}" in val for m in _TEST_MARKERS):
            return True
    return False


def record_learning_weight(record: Mapping[str, Any]) -> float:
    """Compute learning eligibility weight (0.0 for test records or unverified autonomous decisions)."""
    if is_test_record(record):
        return 0.0
    origin = str(record.get("decision_origin") or record.get("approval_origin") or "").upper()
    has_independent_outcome = bool(record.get("independent_outcome_verified", False))
    if origin in {"AUTONOMOUS", "AUTONOMOUS_AUDIT_ONLY"} and not has_independent_outcome:
        return 0.0
    if origin in {"HUMAN_HITL_APPROVED", "HUMAN_OPERATOR", "OPERATOR_CORRECTION"}:
        return 1.0
    return 0.5 if has_independent_outcome else 0.0


def filter_frozen_priors(
    historical_records: Sequence[Mapping[str, Any]],
    *,
    current_decision_id: str,
    lineage_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Freeze priors by excluding the active decision, its retries, its lineage, and zero-weight rows."""
    excluded = {current_decision_id, *(str(x) for x in lineage_ids if x)}
    seen_idem: set[str] = set()
    eligible: list[dict[str, Any]] = []
    for rec in historical_records:
        did = str(rec.get("decision_id") or "")
        parent_id = str(rec.get("parent_decision_id") or "")
        if did in excluded or parent_id in excluded:
            continue
        if record_learning_weight(rec) <= 0.0:
            continue
        idem = str(rec.get("idempotency_key") or f"{did}:{rec.get('selected_key', '')}")
        if idem in seen_idem:
            continue
        seen_idem.add(idem)
        eligible.append(dict(rec))
    return eligible


def validate_learning_approval_origin(approval_receipt: Mapping[str, Any]) -> tuple[bool, str]:
    """Reject synthetic, self-authored, or stop-hook approval receipts fail-closed."""
    origin = str(approval_receipt.get("approval_origin") or "").strip().lower()
    approver = str(approval_receipt.get("approved_by") or "").strip().lower()
    rationale = str(approval_receipt.get("rationale") or "").strip().lower()
    combined = f"{origin} {approver} {rationale}"

    for marker in _SYNTHETIC_APPROVAL_MARKERS:
        if marker in combined:
            return False, f"SYNTHETIC_APPROVAL_ORIGIN_REJECTED:{marker}"

    if origin not in {"human_hitl_approved", "pr_governance_merged", "policy_tier_a_auto"}:
        return False, f"UNRECOGNIZED_APPROVAL_ORIGIN:{origin or 'empty'}"
    if origin == "human_hitl_approved" and not approver:
        return False, "MISSING_HUMAN_APPROVER_ID"
    return True, "approval_origin_verified"


def evaluate_effort_hysteresis(
    *,
    current_effort: EffortLevel,
    recent_runs: Sequence[Mapping[str, Any]],
    required_clean_runs: int = 3,
    min_margin: float = 0.20,
) -> tuple[EffortLevel, str]:
    """Immediately escalate effort on failure/stagnation; require N clean high-margin runs to step down."""
    idx = _EFFORT_ORDER.index(current_effort)
    if not recent_runs:
        return current_effort, "no_recent_runs"

    latest = recent_runs[-1]
    latest_status = str(latest.get("status") or "").upper()
    latest_steps = int(latest.get("steps", 1))
    if latest_status in {"FAILED", "STAGNATED", "BUDGET_EXHAUSTED", "BLOCKED"} or latest_steps >= 3:
        if idx < len(_EFFORT_ORDER) - 1:
            return _EFFORT_ORDER[idx + 1], f"escalated_on_{latest_status.lower() or 'steps'}"
        return current_effort, "at_max_effort"

    if len(recent_runs) >= required_clean_runs and idx > 0:
        tail = recent_runs[-required_clean_runs:]
        all_clean = all(
            str(r.get("status") or "").upper() in {"COMPLETED", "PASS"}
            and int(r.get("steps", 1)) <= 1
            and float(r.get("confidence_margin", 0.0)) > min_margin
            for r in tail
        )
        if all_clean:
            return _EFFORT_ORDER[idx - 1], f"stepped_down_after_{required_clean_runs}_clean_runs"

    return current_effort, "hysteresis_hold"
