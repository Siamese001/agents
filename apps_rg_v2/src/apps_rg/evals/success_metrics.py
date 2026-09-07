"""W0 success-metric contract and non-mutating readiness receipt builder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml


CONTRACT_VERSION = "apps_rg.success_metric_contract.v1"
RECEIPT_VERSION = "apps_rg.success_metric_receipt.v1"
APPS_RESEARCH_HANDOFF_RECEIPT_VERSION = (
    "apps_rg.apps_research_handoff_validation_receipt.v2"
)
CONTRACT_PATH = Path(__file__).with_name("contracts") / "success_metric_contract.v1.yaml"
OUTCOME_METRICS = {
    "P1": "blind_finished_resume_utility_delta",
    "P2": "grounded_decision_ready_completion_rate",
}
DIAGNOSTIC_GATE_IDS = ("G1", "G2", "G3", "G4", "G5", "G6")
_OUTCOME_REASON = "W0_OUTCOME_MEASUREMENT_NOT_IMPLEMENTED"
_GUARDRAIL_REASON = "W0_GUARDRAIL_MEASUREMENT_NOT_IMPLEMENTED"


def canonical_digest(value: Any) -> str:
    """Return the canonical SHA-256 digest used by W0 receipts."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load_success_metric_contract() -> dict[str, Any]:
    """Load the versioned, declarative W0 success-metric contract."""
    value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("W0 success-metric contract must be a mapping")
    if value.get("schema_version") != CONTRACT_VERSION:
        raise ValueError("unexpected W0 success-metric contract schema")
    return value


def evaluate_apps_research_u0_prerequisite(
    handoff_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate an already-produced Apps Research handoff validation receipt.

    This evaluator intentionally does not locate, validate, or persist a
    handoff itself. Runtime owns that validation before U0; W0 only records
    its result in the end-to-end measurement boundary.
    """
    if not isinstance(handoff_receipt, Mapping):
        return {
            "status": "UNKNOWN",
            "observed": False,
            "valid": False,
            "reason_codes": ["APPS_RESEARCH_HANDOFF_RECEIPT_MISSING"],
        }
    if handoff_receipt.get("schema_version") != APPS_RESEARCH_HANDOFF_RECEIPT_VERSION:
        return {
            "status": "UNKNOWN",
            "observed": False,
            "valid": False,
            "reason_codes": ["APPS_RESEARCH_HANDOFF_RECEIPT_SCHEMA_INVALID"],
        }
    observed = handoff_receipt.get("observed")
    valid = handoff_receipt.get("valid")
    status = handoff_receipt.get("status")
    if observed is not True:
        return {
            "status": "UNKNOWN",
            "observed": False,
            "valid": False,
            "reason_codes": ["APPS_RESEARCH_HANDOFF_NOT_OBSERVED"],
        }
    if valid is not True or status not in (None, "PASS"):
        return {
            "status": "FAIL",
            "observed": True,
            "valid": False,
            "reason_codes": ["APPS_RESEARCH_HANDOFF_VALIDATION_FAILED"],
        }
    return {
        "status": "PASS",
        "observed": True,
        "valid": True,
        "reason_codes": [],
    }


def build_w0_success_metric_receipt(
    *,
    evaluation_id: str,
    apps_research_handoff_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a technical-only W0 receipt without measuring P1, P2, or release.

    A passing Apps Research prerequisite only admits an attempt to the U0
    denominator. It does not turn either primary outcome into a PASS.
    """
    if not isinstance(evaluation_id, str) or not evaluation_id.strip():
        raise ValueError("evaluation_id must be a non-empty string")
    contract = load_success_metric_contract()
    prerequisite = evaluate_apps_research_u0_prerequisite(
        apps_research_handoff_receipt
    )
    blocking_reasons = {
        "HUMAN_QUALIFICATION_NOT_COMPLETE",
        "P1_NOT_MEASURED",
        "P2_NOT_MEASURED",
        "RELEASE_AUTHORITY_NOT_GRANTED",
    }
    if prerequisite["status"] != "PASS":
        blocking_reasons.add("APPS_RESEARCH_TO_U0_PREREQUISITE_NOT_PASS")

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "contract_digest": canonical_digest(contract),
        "evaluation_id": evaluation_id,
        "authority": {
            "tier": "technical_validation",
            "technical_validation": True,
            "human_qualified": False,
            "release_authorized": False,
            "production_authorized": False,
            "release_authorizing": False,
        },
        "hard_prerequisites": {"apps_research_to_u0": prerequisite},
        "outcomes": {
            outcome_id: {
                "metric_id": metric_id,
                "status": "NOT_MEASURED",
                "reason_codes": [_OUTCOME_REASON],
            }
            for outcome_id, metric_id in OUTCOME_METRICS.items()
        },
        "guardrails": {
            name: {"status": "NOT_MEASURED", "reason_codes": [_GUARDRAIL_REASON]}
            for name in (
                "unsupported_material_claim_count",
                "critical_binding_error_count",
                "critical_run_divergence_count",
            )
        },
        "diagnostic_gates": {
            gate_id: {"status": "NOT_MEASURED", "authority": "diagnostic_only"}
            for gate_id in DIAGNOSTIC_GATE_IDS
        },
        "promotion_eligible": False,
        "blocking_reasons": sorted(blocking_reasons),
    }
    receipt["record_digest"] = canonical_digest(receipt)
    return receipt


__all__ = [
    "APPS_RESEARCH_HANDOFF_RECEIPT_VERSION",
    "CONTRACT_PATH",
    "CONTRACT_VERSION",
    "DIAGNOSTIC_GATE_IDS",
    "OUTCOME_METRICS",
    "RECEIPT_VERSION",
    "build_w0_success_metric_receipt",
    "canonical_digest",
    "evaluate_apps_research_u0_prerequisite",
    "load_success_metric_contract",
]
