"""Derive CI score-group receipts from validated native evaluator receipts."""

from __future__ import annotations

from typing import Any, Mapping

from apps_rg.evals.c03_ci_ratchet import (
    GATE_RECEIPT_SCHEMA_VERSION,
    REQUIRED_SCORE_GROUPS,
    SCORE_GROUP_GATES,
    seal_gate_receipt,
)

from .artifacts import record_digest_matches
from .grounding import RECEIPT_SCHEMA as GROUNDING_RECEIPT_SCHEMA
from .repeatability import RECEIPT_SCHEMA as REPEATABILITY_RECEIPT_SCHEMA
from .retrieval import RECEIPT_SCHEMA as RETRIEVAL_RECEIPT_SCHEMA
from .reviews import (
    SECTION_RECEIPT_SCHEMA,
    WHOLE_RECEIPT_SCHEMA,
)
from .validity import RECEIPT_SCHEMA as VALIDITY_RECEIPT_SCHEMA

_EXPECTED_SCHEMAS = {
    "retrieval_quality": RETRIEVAL_RECEIPT_SCHEMA,
    "binding_accuracy": GROUNDING_RECEIPT_SCHEMA,
    "factual_grounding": GROUNDING_RECEIPT_SCHEMA,
    "section_quality": SECTION_RECEIPT_SCHEMA,
    "whole_resume_quality": WHOLE_RECEIPT_SCHEMA,
    "runtime_repeatability": REPEATABILITY_RECEIPT_SCHEMA,
    "evaluator_validity": VALIDITY_RECEIPT_SCHEMA,
}


def _selected_result(score_group: str, native: Mapping[str, Any]) -> Mapping[str, Any]:
    if score_group == "binding_accuracy":
        gate_results = native.get("gate_results")
        value = gate_results.get("G2") if isinstance(gate_results, Mapping) else None
        return value if isinstance(value, Mapping) else {}
    if score_group == "factual_grounding":
        gate_results = native.get("gate_results")
        value = gate_results.get("G3") if isinstance(gate_results, Mapping) else None
        return value if isinstance(value, Mapping) else {}
    if score_group in {"section_quality", "whole_resume_quality"}:
        value = native.get("source_report")
        return value if isinstance(value, Mapping) else {}
    return native


def _authority_valid(score_group: str, native: Mapping[str, Any]) -> bool:
    authority = native.get("authority")
    if not isinstance(authority, Mapping):
        return False
    if score_group in {"retrieval_quality", "binding_accuracy", "factual_grounding"}:
        return authority.get("human_authority_verified") is True
    if score_group in {"section_quality", "whole_resume_quality"}:
        return (
            authority.get("human_authority_verified") is True
            and authority.get("source_grounding_verified") is True
        )
    if score_group == "runtime_repeatability":
        return authority.get("runtime_execution_proven") is True
    if score_group == "evaluator_validity":
        return (
            authority.get("machine_critical_grader_validation_complete") is True
            and authority.get("human_agreement_pilot_complete") is True
        )
    return False


def _native_shape_valid(score_group: str, native: Mapping[str, Any]) -> bool:
    if native.get("schema_version") != _EXPECTED_SCHEMAS.get(score_group):
        return False
    if score_group == "retrieval_quality":
        return native.get("gate_id") == "G1"
    if score_group in {"binding_accuracy", "factual_grounding"}:
        selected = _selected_result(score_group, native)
        return selected.get("gate_id") == SCORE_GROUP_GATES[score_group]
    if score_group == "runtime_repeatability":
        return native.get("gate_id") == "G5"
    if score_group == "evaluator_validity":
        return native.get("gate_id") == "G6"
    return True


def normalize_native_receipt(
    score_group: str,
    native: Any,
    *,
    expected_source_digest: str,
    baseline_signature: str,
) -> dict[str, Any]:
    """Validate one native receipt and derive counters; callers cannot supply them."""

    valid_native = (
        isinstance(native, Mapping)
        and record_digest_matches(native)
        and native.get("record_digest") == expected_source_digest
        and _native_shape_valid(score_group, native)
    )
    source = _selected_result(score_group, native) if isinstance(native, Mapping) else {}
    status = str(source.get("status") or "UNKNOWN") if valid_native else "UNKNOWN"
    authority_valid = valid_native and _authority_valid(score_group, native)
    if not authority_valid:
        status = "UNKNOWN"
    failure_codes = source.get("failure_codes")
    if not isinstance(failure_codes, list):
        failure_codes = []
    metrics = source.get("metrics")
    if not isinstance(metrics, Mapping):
        metrics = {}
    unknown_count = 1 if status in {"UNKNOWN", "NOT_MEASURED"} else 0
    if isinstance(source.get("unknown_reasons"), list) and source.get("unknown_reasons"):
        unknown_count = max(unknown_count, len(source["unknown_reasons"]))
    unsupported = metrics.get("unsupported_material_claim_count", 0)
    mutation_failures = metrics.get("mutation_failure_count", 0)
    return seal_gate_receipt(
        {
            "schema_version": GATE_RECEIPT_SCHEMA_VERSION,
            "score_group": score_group,
            "gate_id": SCORE_GROUP_GATES[score_group],
            "source_receipt_digest": expected_source_digest,
            "status": status,
            "metrics": dict(metrics),
            "critical_failure_count": len(set(str(code) for code in failure_codes)),
            "required_unknown_count": int(unknown_count),
            "holdout_leakage_incidents": sum("LEAKAGE" in str(code) for code in failure_codes),
            "unsupported_material_claim_count": (
                int(unsupported)
                if isinstance(unsupported, int) and not isinstance(unsupported, bool) and unsupported >= 0
                else 1
            ),
            "mutation_failure_count": (
                int(mutation_failures)
                if isinstance(mutation_failures, int)
                and not isinstance(mutation_failures, bool)
                and mutation_failures >= 0
                else 1
            ),
            "baseline_signature": baseline_signature,
            "record_digest": "",
        }
    )


def normalize_native_receipt_bundle(
    native_receipts: Mapping[str, Any],
    *,
    expected_source_digests: Mapping[str, str],
    baseline_signatures: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    return {
        score_group: normalize_native_receipt(
            score_group,
            native_receipts.get(score_group),
            expected_source_digest=str(expected_source_digests.get(score_group) or ""),
            baseline_signature=str(baseline_signatures.get(score_group) or ""),
        )
        for score_group in REQUIRED_SCORE_GROUPS
    }


__all__ = ["normalize_native_receipt", "normalize_native_receipt_bundle"]
