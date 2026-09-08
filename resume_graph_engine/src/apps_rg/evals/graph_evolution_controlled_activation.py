"""GE-W8 controlled release planning and post-activation shadow guardrails.

GE-W8 deliberately does not mutate the active retrieval pointer.  A caller
must pass the returned, digest-bound plan to an explicitly authorized UWG
operation before any traffic can be switched.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.evals.graph_evolution_candidate_comparison import GE_W7_COMPLETION_MARKER


GE_W8_CONTRACT_RELATIVE_PATH = Path("src/apps_rg/evals/graph_evolution_controlled_activation_contract.v1.json")
GE_W8_CONTRACT_SCHEMA_VERSION = "apps_rg.graph_evolution_controlled_activation_contract.v1"
GE_W8_COMPLETION_MARKER = "GE_W8_CONTROLLED_ACTIVATION_PLANNED"


class GraphEvolutionControlledActivationError(ValueError):
    """Raised when the frozen GE-W8 contract cannot be loaded."""


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphEvolutionControlledActivationError(f"GE-W8 JSON unavailable: {path}") from exc
    if not isinstance(payload, dict):
        raise GraphEvolutionControlledActivationError("GE-W8 JSON must be an object")
    return payload


def load_ge_w8_controlled_activation_contract(repo_root: Path | str) -> dict[str, Any]:
    return _read_json(Path(repo_root).resolve() / GE_W8_CONTRACT_RELATIVE_PATH)


def validate_ge_w8_controlled_activation_contract(contract: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if contract.get("schema_version") != GE_W8_CONTRACT_SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if contract.get("contract_id") != "APPS_RG_GRAPH_EVOLUTION_CONTROLLED_ACTIVATION":
        issues.append("CONTRACT_ID")
    if contract.get("wave") != "GE_W8" or contract.get("status") != "FROZEN":
        issues.append("WAVE_OR_STATUS")
    entry = contract.get("entry_requirements")
    if not isinstance(entry, Mapping) or any(entry.get(key) is not True for key in ("ge_w7_qualified_comparison_receipt_required", "candidate_registry_projection_digest_binding_required", "explicit_external_release_authority_required", "uwg_required_for_any_active_pointer_change")):
        issues.append("ENTRY_REQUIREMENTS")
    canary = contract.get("canary")
    if not isinstance(canary, Mapping) or not 0.0 < float(canary.get("maximum_candidate_traffic_fraction", 0.0)) <= 0.05 or int(canary.get("minimum_shadow_request_count", 0)) < 1 or int(canary.get("minimum_shadow_window_seconds", 0)) < 1 or any(canary.get(key) is not True for key in ("candidate_and_baseline_comparison_required", "activation_is_reversible")):
        issues.append("CANARY")
    rollback = contract.get("rollback")
    if not isinstance(rollback, Mapping) or any(rollback.get(key) is not True for key in ("automatic_on_guardrail_breach", "restore_prior_active_registry_required", "candidate_retained_for_audit", "rollback_requires_uwg")):
        issues.append("ROLLBACK")
    exit_gate = contract.get("ge_w8_exit")
    if not isinstance(exit_gate, Mapping) or exit_gate.get("plan_ready_state") != "CANARY_PLAN_READY" or exit_gate.get("rollback_state") != "ROLLBACK_REQUIRED" or exit_gate.get("full_promotion_created") is not False:
        issues.append("GE_W8_EXIT")
    return issues


def _validate_qualified_comparison(receipt: Mapping[str, Any], registry: Mapping[str, Any], projection: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if receipt.get("completion_marker") != GE_W7_COMPLETION_MARKER:
        issues.append("GE_W7_MARKER")
    if receipt.get("status") != "QUALIFIED" or receipt.get("candidate_state") != "CANDIDATE_COMPARISON_EVALUATED":
        issues.append("GE_W7_NOT_QUALIFIED")
    if receipt.get("candidate_registry_sha256") != registry.get("registry_sha256"):
        issues.append("GE_W7_REGISTRY_BINDING")
    if receipt.get("candidate_projection_sha256") != projection.get("projection_sha256"):
        issues.append("GE_W7_PROJECTION_BINDING")
    if not _is_sha256(receipt.get("receipt_sha256")):
        issues.append("GE_W7_RECEIPT_DIGEST")
    return issues


def _validate_release_authorization(authorization: Mapping[str, Any], comparison_receipt: Mapping[str, Any], registry: Mapping[str, Any], projection: Mapping[str, Any], maximum_fraction: float) -> list[str]:
    issues: list[str] = []
    if authorization.get("schema_version") != "apps_rg.graph_evolution_release_authorization.v1":
        issues.append("RELEASE_AUTHORIZATION_SCHEMA")
    if authorization.get("status") != "EXPLICIT_RELEASE_AUTHORIZED":
        issues.append("RELEASE_AUTHORIZATION_STATUS")
    if authorization.get("candidate_registry_sha256") != registry.get("registry_sha256") or authorization.get("candidate_projection_sha256") != projection.get("projection_sha256") or authorization.get("qualified_comparison_receipt_sha256") != comparison_receipt.get("receipt_sha256"):
        issues.append("RELEASE_AUTHORIZATION_BINDING")
    if not str(authorization.get("authorized_by") or "").startswith("human-release-authority://"):
        issues.append("RELEASE_AUTHORIZATION_ACTOR")
    if not _is_sha256(authorization.get("release_authority_receipt_sha256")):
        issues.append("RELEASE_AUTHORITY_RECEIPT")
    fraction = authorization.get("candidate_traffic_fraction")
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or not 0.0 < float(fraction) <= maximum_fraction:
        issues.append("RELEASE_CANARY_FRACTION")
    return issues


def prepare_controlled_canary_plan(candidate_registry: Mapping[str, Any], candidate_projection: Mapping[str, Any], qualified_comparison_receipt: Mapping[str, Any], release_authorization: Mapping[str, Any] | None, *, repo_root: Path | str, prior_active_registry_sha256: str) -> dict[str, Any]:
    """Return a reversible GE-W8 canary plan; never switch runtime traffic."""
    contract = load_ge_w8_controlled_activation_contract(repo_root)
    contract_issues = validate_ge_w8_controlled_activation_contract(contract)
    if contract_issues:
        raise GraphEvolutionControlledActivationError(f"GE-W8 contract invalid: {', '.join(contract_issues)}")
    comparison_issues = _validate_qualified_comparison(qualified_comparison_receipt, candidate_registry, candidate_projection)
    if comparison_issues:
        return {"status": "BLOCKED", "reason": "GE_W8_QUALIFIED_COMPARISON_REQUIRED", "failures": comparison_issues, "activation_created": False}
    if not _is_sha256(prior_active_registry_sha256) or prior_active_registry_sha256 == candidate_registry.get("registry_sha256"):
        return {"status": "BLOCKED", "reason": "GE_W8_PRIOR_ACTIVE_REGISTRY_REQUIRED", "failures": [], "activation_created": False}
    if release_authorization is None:
        return {"status": "BLOCKED_RELEASE_AUTHORITY", "reason": "GE_W8_EXPLICIT_RELEASE_AUTHORIZATION_REQUIRED", "failures": [], "activation_created": False}
    authorization_issues = _validate_release_authorization(release_authorization, qualified_comparison_receipt, candidate_registry, candidate_projection, float(contract["canary"]["maximum_candidate_traffic_fraction"]))
    if authorization_issues:
        return {"status": "BLOCKED_RELEASE_AUTHORITY", "reason": "GE_W8_RELEASE_AUTHORIZATION_INVALID", "failures": authorization_issues, "activation_created": False}
    plan: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_controlled_canary_plan.v1",
        "completion_marker": GE_W8_COMPLETION_MARKER,
        "status": "CANARY_PLAN_READY",
        "candidate_registry_sha256": candidate_registry["registry_sha256"],
        "candidate_projection_sha256": candidate_projection["projection_sha256"],
        "prior_active_registry_sha256": prior_active_registry_sha256,
        "qualified_comparison_receipt_sha256": qualified_comparison_receipt["receipt_sha256"],
        "release_authority_receipt_sha256": release_authorization["release_authority_receipt_sha256"],
        "canary": {
            "candidate_traffic_fraction": float(release_authorization["candidate_traffic_fraction"]),
            "minimum_shadow_request_count": contract["canary"]["minimum_shadow_request_count"],
            "minimum_shadow_window_seconds": contract["canary"]["minimum_shadow_window_seconds"],
            "baseline_comparison_required": True,
        },
        "rollback": {
            "trigger": "ANY_SHADOW_GUARDRAIL_BREACH",
            "restore_registry_sha256": prior_active_registry_sha256,
            "operation": "UWG_POINTER_RESTORE",
            "candidate_retained_for_audit": True,
        },
        "active_runtime_pointer_changed": False,
        "activation_created": False,
        "full_promotion_created": False,
        "next_gate": "EXPLICIT_UWG_CANARY_ACTIVATION",
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return {"status": "CANARY_PLAN_READY", "reason": GE_W8_COMPLETION_MARKER, "plan": plan, "activation_created": False}


def evaluate_canary_shadow(plan: Mapping[str, Any], observation: Mapping[str, Any], *, repo_root: Path | str) -> dict[str, Any]:
    """Turn a bound post-runtime shadow observation into continue or rollback."""
    contract = load_ge_w8_controlled_activation_contract(repo_root)
    contract_issues = validate_ge_w8_controlled_activation_contract(contract)
    if contract_issues:
        raise GraphEvolutionControlledActivationError(f"GE-W8 contract invalid: {', '.join(contract_issues)}")
    if plan.get("status") != "CANARY_PLAN_READY" or not _is_sha256(plan.get("plan_sha256")):
        return {"status": "BLOCKED", "reason": "GE_W8_CANARY_PLAN_REQUIRED", "failures": []}
    if observation.get("plan_sha256") != plan.get("plan_sha256"):
        return {"status": "BLOCKED", "reason": "GE_W8_SHADOW_PLAN_BINDING", "failures": []}
    required = ("request_count", "elapsed_window_seconds", "candidate_error_rate", "baseline_error_rate", "candidate_p95_latency_ms", "baseline_p95_latency_ms", "evidence_authority_bypass_count", "section_policy_leak_count", "projection_issue_count")
    missing = [key for key in required if key not in observation]
    if missing:
        return {"status": "BLOCKED", "reason": "GE_W8_SHADOW_OBSERVATION_INCOMPLETE", "failures": [f"MISSING:{key}" for key in missing]}
    canary = plan["canary"]
    if int(observation["request_count"]) < int(canary["minimum_shadow_request_count"]) or float(observation["elapsed_window_seconds"]) < float(canary["minimum_shadow_window_seconds"]):
        return {"status": "OBSERVATION_INCOMPLETE", "reason": "GE_W8_SHADOW_WINDOW_INCOMPLETE", "failures": []}
    guardrails = contract["shadow_guardrails"]
    latency_ratio = float(observation["candidate_p95_latency_ms"]) / float(observation["baseline_p95_latency_ms"]) if float(observation["baseline_p95_latency_ms"]) > 0.0 else float("inf")
    failures: list[str] = []
    if float(observation["candidate_error_rate"]) - float(observation["baseline_error_rate"]) > float(guardrails["candidate_error_rate_delta_max"]):
        failures.append("ERROR_RATE_DELTA")
    if latency_ratio > float(guardrails["candidate_p95_latency_ratio_max"]):
        failures.append("P95_LATENCY_RATIO")
    for metric, maximum in (("evidence_authority_bypass_count", guardrails["evidence_authority_bypass_count_max"]), ("section_policy_leak_count", guardrails["section_policy_leak_count_max"]), ("projection_issue_count", guardrails["projection_issue_count_max"])):
        if float(observation[metric]) > float(maximum):
            failures.append(metric.upper())
    status = "ROLLBACK_REQUIRED" if failures else "CONTINUE_CANARY"
    receipt: dict[str, Any] = {
        "schema_version": "apps_rg.graph_evolution_canary_shadow_receipt.v1",
        "status": status,
        "plan_sha256": plan["plan_sha256"],
        "candidate_registry_sha256": plan["candidate_registry_sha256"],
        "prior_active_registry_sha256": plan["prior_active_registry_sha256"],
        "latency_ratio": latency_ratio,
        "guardrail_failures": failures,
        "rollback_required": status == "ROLLBACK_REQUIRED",
        "rollback_operation": plan["rollback"]["operation"] if failures else None,
        "active_runtime_pointer_changed": False,
        "full_promotion_created": False,
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return {"status": status, "reason": "GE_W8_SHADOW_GUARDRAILS", "failures": failures, "receipt": receipt}


__all__ = ["GE_W8_COMPLETION_MARKER", "GE_W8_CONTRACT_RELATIVE_PATH", "GE_W8_CONTRACT_SCHEMA_VERSION", "GraphEvolutionControlledActivationError", "evaluate_canary_shadow", "load_ge_w8_controlled_activation_contract", "prepare_controlled_canary_plan", "validate_ge_w8_controlled_activation_contract"]
