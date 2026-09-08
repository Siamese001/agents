"""Controller-bound G5 evaluation for actual, independently observed executions."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping

from apps_rg.evals.repeatability.evaluation import evaluate_run_set
from apps_rg.evals.resume_graph.reporting import canonical_digest

from .artifacts import HEX64, seal_record, validate_pinned_record

CONTROLLER_RECEIPT_SCHEMA = "apps_rg.execution_controller_receipt.v1"
CONTROLLER_MANIFEST_SCHEMA = "apps_rg.execution_controller_manifest.v1"
STABILITY_POLICY_SCHEMA = "apps_rg.repeatability_stability_policy.v1"
RECEIPT_SCHEMA = "apps_rg.authoritative_repeatability_receipt.v1"
_SEMANTIC_FIELDS = (
    "retrieved_candidate_ids",
    "selected_evidence_ids",
    "selected_graph_path_ids",
    "material_claim_ids",
    "bindings",
    "section_decisions",
    "grounding_dispositions",
    "final_disposition",
    "output_quality_scores",
    "output_text_by_section",
)
_STABILITY_METRICS = (
    "retrieved_candidate_stability",
    "evidence_selection_stability",
    "material_claim_identity_stability",
    "binding_stability",
    "grounding_disposition_stability",
    "semantic_output_stability",
    "output_quality_score_stability",
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def semantic_run_digest(run: Mapping[str, Any]) -> str:
    return canonical_digest({field: run.get(field) for field in _SEMANTIC_FIELDS})


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return None


def _unknown(reasons: list[str]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": RECEIPT_SCHEMA,
            "gate_id": "G5",
            "score_groups": ["runtime_repeatability"],
            "status": "UNKNOWN",
            "source_receipt": {},
            "metrics": {},
            "failure_codes": [],
            "unknown_reasons": sorted(set(reasons)),
            "authority": {
                "measurement_scope": "CONTROLLER_BOUND_ACTUAL_EXECUTIONS",
                "runtime_execution_proven": False,
                "release_authorizing": False,
            },
        }
    )


def evaluate_controller_bound_repeatability(
    run_set: Any,
    *,
    controller_manifest: Any,
    expected_controller_manifest_digest: str,
    stability_policy: Any,
    expected_stability_policy_digest: str,
    expected_source_commit: str,
) -> dict[str, Any]:
    """Reject copied/self-attested runs unless a pinned controller observed each execution."""

    reasons = validate_pinned_record(
        controller_manifest,
        expected_digest=expected_controller_manifest_digest,
        schema_version=CONTROLLER_MANIFEST_SCHEMA,
    )
    reasons.extend(
        validate_pinned_record(
            stability_policy,
            expected_digest=expected_stability_policy_digest,
            schema_version=STABILITY_POLICY_SCHEMA,
        )
    )
    if not all(isinstance(value, Mapping) for value in (run_set, controller_manifest, stability_policy)):
        return _unknown(reasons)
    if controller_manifest.get("runtime_invoked") is not True:
        reasons.append("CONTROLLER_RUNTIME_INVOCATION_NOT_PROVEN")
    if controller_manifest.get("source_commit") != expected_source_commit:
        reasons.append("CONTROLLER_SOURCE_COMMIT_MISMATCH")
    source_tree = str(controller_manifest.get("source_tree") or "")
    if not _COMMIT.fullmatch(source_tree):
        reasons.append("CONTROLLER_SOURCE_TREE_INVALID")
    controller_id = str(controller_manifest.get("controller_id") or "")
    if not controller_id:
        reasons.append("CONTROLLER_ID_INVALID")
    if not HEX64.fullmatch(str(controller_manifest.get("controller_plan_digest") or "")):
        reasons.append("CONTROLLER_PLAN_DIGEST_INVALID")
    receipts = controller_manifest.get("execution_receipts")
    if not isinstance(receipts, list) or not receipts:
        reasons.append("CONTROLLER_EXECUTION_RECEIPTS_EMPTY")
        receipts = []
    receipt_index: dict[str, Mapping[str, Any]] = {}
    nonces: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            reasons.append("CONTROLLER_EXECUTION_RECEIPT_INVALID")
            continue
        execution_id = str(receipt.get("execution_id") or "")
        if not execution_id or execution_id in receipt_index:
            reasons.append("CONTROLLER_EXECUTION_ID_INVALID")
        receipt_index[execution_id] = receipt
        reasons.extend(
            validate_pinned_record(
                receipt,
                expected_digest=str(receipt.get("record_digest") or ""),
                schema_version=CONTROLLER_RECEIPT_SCHEMA,
            )
        )
        nonce = str(receipt.get("controller_nonce") or "")
        if not HEX64.fullmatch(nonce) or nonce in nonces:
            reasons.append("CONTROLLER_NONCE_NOT_UNIQUE")
        nonces.add(nonce)
        if receipt.get("runtime_invoked") is not True or receipt.get("exit_code") != 0:
            reasons.append("CONTROLLER_EXECUTION_NONPASS")
        if receipt.get("source_commit") != expected_source_commit:
            reasons.append("CONTROLLER_EXECUTION_SOURCE_COMMIT_MISMATCH")
        if receipt.get("source_tree") != source_tree:
            reasons.append("CONTROLLER_EXECUTION_SOURCE_TREE_MISMATCH")
        if not str(receipt.get("workdir") or ""):
            reasons.append("CONTROLLER_EXECUTION_WORKDIR_MISSING")
        if receipt.get("controller_id") != controller_id:
            reasons.append("CONTROLLER_EXECUTION_IDENTITY_MISMATCH")
        if any(
            not HEX64.fullmatch(str(receipt.get(field) or ""))
            for field in (
                "input_file_sha256",
                "command_digest",
                "stdout_sha256",
                "stderr_sha256",
                "semantic_output_digest",
            )
        ):
            reasons.append("CONTROLLER_EXECUTION_DIGEST_INVALID")
        started_at = _timestamp(receipt.get("started_at"))
        ended_at = _timestamp(receipt.get("ended_at"))
        if started_at is None or ended_at is None or ended_at < started_at:
            reasons.append("CONTROLLER_EXECUTION_TIME_INVALID")

    observed_execution_ids: set[str] = set()
    for scenario in run_set.get("scenarios") or []:
        if not isinstance(scenario, Mapping):
            continue
        scenario_id = str(scenario.get("scenario_id") or "")
        for run in scenario.get("runs") or []:
            if not isinstance(run, Mapping):
                continue
            execution_id = str(run.get("execution_id") or "")
            observed_execution_ids.add(execution_id)
            receipt = receipt_index.get(execution_id)
            if not isinstance(receipt, Mapping):
                reasons.append("RUN_CONTROLLER_RECEIPT_NOT_FOUND")
                continue
            if receipt.get("scenario_id") != scenario_id:
                reasons.append("RUN_CONTROLLER_SCENARIO_MISMATCH")
            if run.get("execution_receipt_digest") != receipt.get("record_digest"):
                reasons.append("RUN_CONTROLLER_RECEIPT_DIGEST_MISMATCH")
            if receipt.get("semantic_output_digest") != semantic_run_digest(run):
                reasons.append("RUN_CONTROLLER_OUTPUT_BINDING_MISMATCH")
    if observed_execution_ids != set(receipt_index):
        reasons.append("CONTROLLER_EXECUTION_COVERAGE_MISMATCH")
    if reasons:
        return _unknown(reasons)

    base = evaluate_run_set(run_set)
    if base["status"] == "UNKNOWN":
        return _unknown(list(base["unknown_reasons"]))
    thresholds = stability_policy.get("minimum_stability")
    if not isinstance(thresholds, Mapping) or set(thresholds) != set(_STABILITY_METRICS):
        return _unknown(["STABILITY_POLICY_THRESHOLDS_INVALID"])
    failures = list(base["failure_codes"])
    threshold_failures: list[str] = []
    for scenario in base["scenario_results"]:
        if scenario["status"] == "UNKNOWN":
            continue
        for metric in _STABILITY_METRICS:
            value = scenario["metrics"].get(metric)
            threshold = thresholds.get(metric)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isinstance(threshold, (int, float))
                or isinstance(threshold, bool)
                or not 0 <= float(threshold) <= 1
            ):
                return _unknown(["STABILITY_POLICY_OR_METRIC_INVALID"])
            if float(value) < float(threshold):
                threshold_failures.append(
                    f"STABILITY_BELOW_POLICY::{scenario['scenario_id']}::{metric}"
                )
    failures.extend(threshold_failures)
    status = "FAIL" if failures else base["status"]
    return seal_record(
        {
            "schema_version": RECEIPT_SCHEMA,
            "gate_id": "G5",
            "score_groups": ["runtime_repeatability"],
            "status": status,
            "source_receipt": base,
            "metrics": base["metrics"],
            "failure_codes": sorted(set(failures)),
            "unknown_reasons": [],
            "authority": {
                "measurement_scope": "CONTROLLER_BOUND_ACTUAL_EXECUTIONS",
                "controller_manifest_digest": controller_manifest.get("record_digest"),
                "stability_policy_digest": stability_policy.get("record_digest"),
                "runtime_execution_proven": True,
                "release_authorizing": False,
            },
        }
    )


__all__ = [
    "CONTROLLER_MANIFEST_SCHEMA",
    "CONTROLLER_RECEIPT_SCHEMA",
    "RECEIPT_SCHEMA",
    "STABILITY_POLICY_SCHEMA",
    "evaluate_controller_bound_repeatability",
    "semantic_run_digest",
]
