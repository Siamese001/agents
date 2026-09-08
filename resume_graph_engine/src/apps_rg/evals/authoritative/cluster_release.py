"""W4 calibration freeze and release qualification for cluster embeddings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import math
from typing import Any

from .artifacts import HEX64, seal_record, validate_pinned_record
from .cluster_authority import CLUSTER_AUTHORITY_RECEIPT_SCHEMA
from .cluster_qrel_review import CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA
from .cluster_retrieval import (
    CLUSTER_RECEIPT_SCHEMA,
    CLUSTER_THRESHOLD_POLICY_SCHEMA,
    LOGICAL_RETRIEVAL_UNIT,
    seal_cluster_authority_bindings,
)
from .cluster_runtime import CLUSTER_RUNTIME_RECEIPT_SCHEMA
from .grounding import RECEIPT_SCHEMA as GROUNDING_RECEIPT_SCHEMA
from .repeatability import RECEIPT_SCHEMA as REPEATABILITY_RECEIPT_SCHEMA
from .validity import RECEIPT_SCHEMA as VALIDITY_RECEIPT_SCHEMA

CLUSTER_DEPLOYMENT_BINDINGS_SCHEMA = "apps_rg.cluster_deployment_bindings.v1"
CLUSTER_THRESHOLD_FREEZE_SCHEMA = "apps_rg.cluster_threshold_freeze_receipt.v1"
CLUSTER_HOLDOUT_CONTROLLER_SCHEMA = "apps_rg.cluster_holdout_controller_receipt.v1"
CLUSTER_RELEASE_QUALIFICATION_SCHEMA = (
    "apps_rg.cluster_release_qualification_receipt.v1"
)
THRESHOLD_FREEZE_MARKER = "CLUSTER_CALIBRATION_THRESHOLDS_FROZEN"
RELEASE_COMPLETION_MARKER = "GRAPH_EVIDENCE_CLUSTER_EMBEDDINGS_QUALIFIED"
QUALIFICATION_SCOPE = "EVAL_W4_RELEASE_HOLDOUT"

_DEPLOYMENT_FIELDS = frozenset(
    {
        "schema_version",
        "source_commit",
        "graph_sha256",
        "cluster_registry_sha256",
        "corpus_sha256",
        "model_artifact_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
        "candidate_activation_manifest_sha256",
        "cluster_count",
        "runtime_top_k",
        "dimension",
        "normalization",
        "record_digest",
    }
)
_DEPLOYMENT_DIGEST_FIELDS = frozenset(
    {
        "graph_sha256",
        "cluster_registry_sha256",
        "corpus_sha256",
        "model_artifact_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
        "candidate_activation_manifest_sha256",
    }
)
_THRESHOLD_STATIC_BINDINGS = {
    "graph_sha256": "graph_sha256",
    "cluster_registry_sha256": "cluster_registry_sha256",
    "corpus_sha256": "corpus_sha256",
    "model_artifact_sha256": "model_artifact_sha256",
    "projection_sha256": "projection_sha256",
    "runtime_config_sha256": "runtime_config_sha256",
}
_THRESHOLD_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "logical_retrieval_unit",
        "runtime_top_k",
        "positive_relevance_floor",
        "metric_thresholds",
        "authority_bindings",
        "record_digest",
    }
)
_THRESHOLD_BINDING_FIELDS = frozenset(
    {*_THRESHOLD_STATIC_BINDINGS, "authority_envelope_sha256"}
)
_REQUIRED_METRIC_THRESHOLDS = frozenset(
    {
        "recall_at_runtime_k_minimum",
        "ndcg_at_runtime_k_minimum",
        "mrr_minimum",
        "hard_negative_rejection_rate_minimum",
        "top_k_redundancy_rate_maximum",
    }
)
_FREEZE_INPUTS = frozenset(
    {
        "calibration_retrieval",
        "threshold_policy",
        "completed_qrel_review",
        "split_policy",
    }
)
_FREEZE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "completion_marker",
        "logical_retrieval_unit",
        "source_commit",
        "calibration_query_ids",
        "frozen_thresholds",
        "runtime_top_k",
        "positive_relevance_floor",
        "deployment_bindings_digest",
        "input_digests",
        "release_authorizing",
        "unknown_reasons",
        "record_digest",
    }
)
_HOLDOUT_CONTROLLER_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "split",
        "controller_id",
        "controller_nonce",
        "execution_id",
        "source_commit",
        "controller_plan_digest",
        "input_bundle_sha256",
        "threshold_freeze_digest",
        "holdout_retrieval_receipt_digest",
        "started_at",
        "ended_at",
        "runtime_invoked",
        "exit_code",
        "record_digest",
    }
)
_QUALIFICATION_INPUT_SCHEMAS = {
    "threshold_freeze": CLUSTER_THRESHOLD_FREEZE_SCHEMA,
    "qrel_review": CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA,
    "holdout_retrieval": CLUSTER_RECEIPT_SCHEMA,
    "authority_pipeline": CLUSTER_AUTHORITY_RECEIPT_SCHEMA,
    "runtime_quality": CLUSTER_RUNTIME_RECEIPT_SCHEMA,
    "grounding": GROUNDING_RECEIPT_SCHEMA,
    "repeatability": REPEATABILITY_RECEIPT_SCHEMA,
    "evaluator_validity": VALIDITY_RECEIPT_SCHEMA,
    "holdout_controller": CLUSTER_HOLDOUT_CONTROLLER_SCHEMA,
}


def _valid_source_commit(value: object) -> bool:
    text = str(value or "")
    return len(text) == 40 and all(character in "0123456789abcdef" for character in text)


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return None


def _query_split(result: object) -> str | None:
    if not isinstance(result, Mapping):
        return None
    attributes = result.get("slice_attributes")
    if not isinstance(attributes, Mapping):
        return None
    split = attributes.get("split")
    if not isinstance(split, list) or len(split) != 1:
        return None
    return str(split[0])


def _valid_metric_thresholds(value: object) -> bool:
    return bool(
        isinstance(value, Mapping)
        and set(value) == _REQUIRED_METRIC_THRESHOLDS
        and all(
            isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and math.isfinite(float(threshold))
            and 0.0 <= float(threshold) <= 1.0
            for threshold in value.values()
        )
    )


def _valid_positive_relevance_floor(value: object) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 < float(value) <= 3.0
    )


def _validate_deployment_bindings(
    value: object, *, expected_digest: str
) -> tuple[dict[str, Any], list[str]]:
    reasons = validate_pinned_record(
        value,
        expected_digest=expected_digest,
        schema_version=CLUSTER_DEPLOYMENT_BINDINGS_SCHEMA,
    )
    if not isinstance(value, Mapping):
        return {}, reasons
    bindings = dict(value)
    if set(bindings) != _DEPLOYMENT_FIELDS:
        reasons.append("CLUSTER_DEPLOYMENT_BINDINGS_SCHEMA_INVALID")
    if not _valid_source_commit(bindings.get("source_commit")):
        reasons.append("CLUSTER_DEPLOYMENT_SOURCE_COMMIT_INVALID")
    if any(
        not HEX64.fullmatch(str(bindings.get(field) or ""))
        for field in _DEPLOYMENT_DIGEST_FIELDS
    ):
        reasons.append("CLUSTER_DEPLOYMENT_DIGEST_INVALID")
    cluster_count = bindings.get("cluster_count")
    runtime_top_k = bindings.get("runtime_top_k")
    if (
        not isinstance(cluster_count, int)
        or isinstance(cluster_count, bool)
        or cluster_count < 2
        or not isinstance(runtime_top_k, int)
        or isinstance(runtime_top_k, bool)
        or runtime_top_k < 1
        or runtime_top_k >= cluster_count
    ):
        reasons.append("CLUSTER_DEPLOYMENT_TOP_K_NOT_BOUNDED")
    if bindings.get("dimension") != 1024 or bindings.get("normalization") != "l2":
        reasons.append("CLUSTER_DEPLOYMENT_VECTOR_SHAPE_INVALID")
    return bindings, sorted(set(reasons))


def _freeze_unknown(reasons: Sequence[str]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_THRESHOLD_FREEZE_SCHEMA,
            "status": "UNKNOWN",
            "completion_marker": None,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "source_commit": None,
            "calibration_query_ids": [],
            "frozen_thresholds": {},
            "runtime_top_k": None,
            "positive_relevance_floor": None,
            "deployment_bindings_digest": None,
            "input_digests": {},
            "release_authorizing": False,
            "unknown_reasons": sorted(set(reasons)),
        }
    )


def freeze_cluster_calibration_thresholds(
    *,
    calibration_retrieval_receipt: Mapping[str, Any],
    expected_calibration_retrieval_digest: str,
    threshold_policy: Mapping[str, Any],
    expected_threshold_policy_digest: str,
    completed_qrel_review_receipt: Mapping[str, Any],
    expected_completed_qrel_review_digest: str,
    deployment_bindings: Mapping[str, Any],
    expected_deployment_bindings_digest: str,
    source_commit: str,
) -> dict[str, Any]:
    """Freeze thresholds only from a source-pinned calibration evaluation."""

    reasons: list[str] = []
    for value, expected, schema in (
        (
            calibration_retrieval_receipt,
            expected_calibration_retrieval_digest,
            CLUSTER_RECEIPT_SCHEMA,
        ),
        (
            threshold_policy,
            expected_threshold_policy_digest,
            CLUSTER_THRESHOLD_POLICY_SCHEMA,
        ),
        (
            completed_qrel_review_receipt,
            expected_completed_qrel_review_digest,
            CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA,
        ),
    ):
        reasons.extend(
            validate_pinned_record(
                value,
                expected_digest=expected,
                schema_version=schema,
            )
        )
    deployment, deployment_reasons = _validate_deployment_bindings(
        deployment_bindings,
        expected_digest=expected_deployment_bindings_digest,
    )
    reasons.extend(deployment_reasons)
    if not all(
        isinstance(value, Mapping)
        for value in (
            calibration_retrieval_receipt,
            threshold_policy,
            completed_qrel_review_receipt,
            deployment_bindings,
        )
    ):
        return _freeze_unknown(reasons + ["CLUSTER_THRESHOLD_FREEZE_INPUT_NOT_OBJECT"])
    if set(threshold_policy) != _THRESHOLD_POLICY_FIELDS:
        reasons.append("CLUSTER_THRESHOLD_FREEZE_POLICY_SCHEMA_INVALID")
    if threshold_policy.get("logical_retrieval_unit") != LOGICAL_RETRIEVAL_UNIT:
        reasons.append("CLUSTER_THRESHOLD_FREEZE_LOGICAL_UNIT_INVALID")
    query_results = calibration_retrieval_receipt.get("query_results")
    if not isinstance(query_results, list) or not query_results:
        reasons.append("CLUSTER_CALIBRATION_QUERY_RESULTS_EMPTY")
        query_results = []
    query_ids: list[str] = []
    for result in query_results:
        query_id = str(result.get("query_id") or "") if isinstance(result, Mapping) else ""
        if not query_id or query_id in query_ids:
            reasons.append("CLUSTER_CALIBRATION_QUERY_IDENTITY_INVALID")
        query_ids.append(query_id)
        if _query_split(result) != "CALIBRATION":
            reasons.append("CLUSTER_THRESHOLD_FREEZE_NON_CALIBRATION_INPUT")
    authority = calibration_retrieval_receipt.get("authority")
    qrel_inputs = completed_qrel_review_receipt.get("input_digests")
    if not (
        calibration_retrieval_receipt.get("status") == "PASS"
        and calibration_retrieval_receipt.get("logical_retrieval_unit")
        == LOGICAL_RETRIEVAL_UNIT
        and isinstance(authority, Mapping)
        and authority.get("human_authority_verified") is True
        and authority.get("release_authorizing") is False
    ):
        reasons.append("CLUSTER_CALIBRATION_RETRIEVAL_NOT_QUALIFIED")
    if not (
        completed_qrel_review_receipt.get("status") == "PASS"
        and completed_qrel_review_receipt.get("qrels_ready") is True
        and completed_qrel_review_receipt.get("zero_unresolved_judgments") is True
        and completed_qrel_review_receipt.get("human_authority_verified") is True
        and completed_qrel_review_receipt.get("release_authorizing") is False
        and isinstance(qrel_inputs, Mapping)
        and HEX64.fullmatch(str(qrel_inputs.get("split_policy") or ""))
    ):
        reasons.append("CLUSTER_THRESHOLD_FREEZE_QRELS_NOT_COMPLETE")
    if calibration_retrieval_receipt.get("threshold_policy_digest") != threshold_policy.get(
        "record_digest"
    ):
        reasons.append("CLUSTER_THRESHOLD_FREEZE_POLICY_BINDING_MISMATCH")
    if source_commit != deployment.get("source_commit") or not _valid_source_commit(
        source_commit
    ):
        reasons.append("CLUSTER_THRESHOLD_FREEZE_SOURCE_COMMIT_MISMATCH")
    threshold_bindings = threshold_policy.get("authority_bindings")
    if (
        not isinstance(threshold_bindings, Mapping)
        or set(threshold_bindings) != _THRESHOLD_BINDING_FIELDS
    ):
        reasons.append("CLUSTER_THRESHOLD_FREEZE_AUTHORITY_BINDINGS_INVALID")
    else:
        for threshold_field, deployment_field in _THRESHOLD_STATIC_BINDINGS.items():
            if threshold_bindings.get(threshold_field) != deployment.get(deployment_field):
                reasons.append("CLUSTER_THRESHOLD_FREEZE_DEPLOYMENT_BINDING_MISMATCH")
        if dict(threshold_bindings) != seal_cluster_authority_bindings(
            dict(threshold_bindings)
        ):
            reasons.append("CLUSTER_THRESHOLD_FREEZE_AUTHORITY_ENVELOPE_INVALID")
    if threshold_policy.get("runtime_top_k") != deployment.get("runtime_top_k"):
        reasons.append("CLUSTER_THRESHOLD_FREEZE_TOP_K_MISMATCH")
    thresholds = threshold_policy.get("metric_thresholds")
    if not _valid_metric_thresholds(thresholds):
        reasons.append("CLUSTER_THRESHOLD_FREEZE_METRICS_INVALID")
    if not _valid_positive_relevance_floor(
        threshold_policy.get("positive_relevance_floor")
    ):
        reasons.append("CLUSTER_THRESHOLD_FREEZE_POSITIVE_FLOOR_INVALID")
    if reasons:
        return _freeze_unknown(reasons)
    return seal_record(
        {
            "schema_version": CLUSTER_THRESHOLD_FREEZE_SCHEMA,
            "status": "PASS",
            "completion_marker": THRESHOLD_FREEZE_MARKER,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "source_commit": source_commit,
            "calibration_query_ids": sorted(query_ids),
            "frozen_thresholds": dict(sorted(thresholds.items())),
            "runtime_top_k": threshold_policy["runtime_top_k"],
            "positive_relevance_floor": threshold_policy[
                "positive_relevance_floor"
            ],
            "deployment_bindings_digest": deployment["record_digest"],
            "input_digests": {
                "calibration_retrieval": calibration_retrieval_receipt[
                    "record_digest"
                ],
                "threshold_policy": threshold_policy["record_digest"],
                "completed_qrel_review": completed_qrel_review_receipt[
                    "record_digest"
                ],
                "split_policy": qrel_inputs["split_policy"],
            },
            "release_authorizing": False,
            "unknown_reasons": [],
        }
    )


def _qualification_unknown(
    reasons: Sequence[str], *, deployment: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    embedded_deployment = (
        {
            key: deployment[key]
            for key in sorted(
                _DEPLOYMENT_FIELDS - {"schema_version", "record_digest"}
            )
        }
        if deployment and set(deployment) == _DEPLOYMENT_FIELDS
        else {}
    )
    return seal_record(
        {
            "schema_version": CLUSTER_RELEASE_QUALIFICATION_SCHEMA,
            "status": "UNKNOWN",
            "completion_marker": None,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": QUALIFICATION_SCOPE,
            "source_commit": deployment.get("source_commit") if deployment else None,
            "deployment_bindings": embedded_deployment,
            "input_receipt_digests": {},
            "checks": {},
            "failure_codes": [],
            "unknown_reasons": sorted(set(reasons)),
            "legacy_regression_only_accepted": False,
            "release_authorizing": False,
        }
    )


def qualify_cluster_embedding_release(
    *,
    deployment_bindings: Mapping[str, Any],
    expected_deployment_bindings_digest: str,
    threshold_freeze_receipt: Mapping[str, Any],
    expected_threshold_freeze_digest: str,
    completed_qrel_review_receipt: Mapping[str, Any],
    expected_completed_qrel_review_digest: str,
    holdout_retrieval_receipt: Mapping[str, Any],
    expected_holdout_retrieval_digest: str,
    authority_pipeline_receipt: Mapping[str, Any],
    expected_authority_pipeline_digest: str,
    runtime_quality_receipt: Mapping[str, Any],
    expected_runtime_quality_digest: str,
    grounding_receipt: Mapping[str, Any],
    expected_grounding_digest: str,
    repeatability_receipt: Mapping[str, Any],
    expected_repeatability_digest: str,
    evaluator_validity_receipt: Mapping[str, Any],
    expected_evaluator_validity_digest: str,
    holdout_controller_receipt: Mapping[str, Any],
    expected_holdout_controller_digest: str,
) -> dict[str, Any]:
    """Aggregate externally pinned holdout evidence into release authority."""

    deployment, reasons = _validate_deployment_bindings(
        deployment_bindings,
        expected_digest=expected_deployment_bindings_digest,
    )
    receipts = {
        "threshold_freeze": (
            threshold_freeze_receipt,
            expected_threshold_freeze_digest,
        ),
        "qrel_review": (
            completed_qrel_review_receipt,
            expected_completed_qrel_review_digest,
        ),
        "holdout_retrieval": (
            holdout_retrieval_receipt,
            expected_holdout_retrieval_digest,
        ),
        "authority_pipeline": (
            authority_pipeline_receipt,
            expected_authority_pipeline_digest,
        ),
        "runtime_quality": (
            runtime_quality_receipt,
            expected_runtime_quality_digest,
        ),
        "grounding": (grounding_receipt, expected_grounding_digest),
        "repeatability": (repeatability_receipt, expected_repeatability_digest),
        "evaluator_validity": (
            evaluator_validity_receipt,
            expected_evaluator_validity_digest,
        ),
        "holdout_controller": (
            holdout_controller_receipt,
            expected_holdout_controller_digest,
        ),
    }
    for name, (value, expected) in receipts.items():
        reasons.extend(
            f"{name.upper()}::{reason}"
            for reason in validate_pinned_record(
                value,
                expected_digest=expected,
                schema_version=_QUALIFICATION_INPUT_SCHEMAS[name],
            )
        )
    if not isinstance(deployment_bindings, Mapping) or not all(
        isinstance(value, Mapping) for value, _expected in receipts.values()
    ):
        return _qualification_unknown(
            reasons + ["CLUSTER_RELEASE_INPUT_NOT_OBJECT"], deployment=deployment
        )
    if set(threshold_freeze_receipt) != _FREEZE_FIELDS:
        reasons.append("CLUSTER_RELEASE_THRESHOLD_FREEZE_SCHEMA_INVALID")
    if set(holdout_controller_receipt) != _HOLDOUT_CONTROLLER_FIELDS:
        reasons.append("CLUSTER_RELEASE_HOLDOUT_CONTROLLER_SCHEMA_INVALID")
    if reasons:
        return _qualification_unknown(reasons, deployment=deployment)

    failures: list[str] = []
    checks: dict[str, bool] = {}
    freeze_inputs = threshold_freeze_receipt.get("input_digests")
    checks["calibration_thresholds_frozen"] = bool(
        threshold_freeze_receipt.get("status") == "PASS"
        and threshold_freeze_receipt.get("completion_marker") == THRESHOLD_FREEZE_MARKER
        and threshold_freeze_receipt.get("logical_retrieval_unit")
        == LOGICAL_RETRIEVAL_UNIT
        and threshold_freeze_receipt.get("release_authorizing") is False
        and threshold_freeze_receipt.get("unknown_reasons") == []
        and isinstance(threshold_freeze_receipt.get("calibration_query_ids"), list)
        and bool(threshold_freeze_receipt.get("calibration_query_ids"))
        and len(threshold_freeze_receipt["calibration_query_ids"])
        == len(set(threshold_freeze_receipt["calibration_query_ids"]))
        and _valid_metric_thresholds(
            threshold_freeze_receipt.get("frozen_thresholds")
        )
        and threshold_freeze_receipt.get("runtime_top_k")
        == deployment.get("runtime_top_k")
        and _valid_positive_relevance_floor(
            threshold_freeze_receipt.get("positive_relevance_floor")
        )
        and threshold_freeze_receipt.get("deployment_bindings_digest")
        == deployment.get("record_digest")
        and threshold_freeze_receipt.get("source_commit")
        == deployment.get("source_commit")
        and isinstance(freeze_inputs, Mapping)
        and set(freeze_inputs) == _FREEZE_INPUTS
        and all(HEX64.fullmatch(str(value or "")) for value in freeze_inputs.values())
        and freeze_inputs.get("completed_qrel_review")
        == completed_qrel_review_receipt.get("record_digest")
    )
    qrel_inputs = completed_qrel_review_receipt.get("input_digests")
    checks["human_qrels_complete"] = bool(
        completed_qrel_review_receipt.get("status") == "PASS"
        and completed_qrel_review_receipt.get("qrels_ready") is True
        and completed_qrel_review_receipt.get("zero_unresolved_judgments") is True
        and completed_qrel_review_receipt.get("human_authority_verified") is True
        and completed_qrel_review_receipt.get("release_authorizing") is False
        and isinstance(qrel_inputs, Mapping)
        and isinstance(freeze_inputs, Mapping)
        and qrel_inputs.get("split_policy") == freeze_inputs.get("split_policy")
    )
    holdout_results = holdout_retrieval_receipt.get("query_results")
    holdout_rows = holdout_results if isinstance(holdout_results, list) else []
    holdout_query_ids = [
        str(result.get("query_id") or "")
        for result in holdout_rows
        if isinstance(result, Mapping)
    ]
    calibration_query_ids = threshold_freeze_receipt.get("calibration_query_ids")
    holdout_identities_valid = bool(
        isinstance(holdout_results, list)
        and len(holdout_query_ids) == len(holdout_results)
        and all(holdout_query_ids)
        and len(holdout_query_ids) == len(set(holdout_query_ids))
        and isinstance(calibration_query_ids, list)
        and set(holdout_query_ids).isdisjoint(calibration_query_ids)
    )
    holdout_only = bool(
        isinstance(holdout_results, list)
        and holdout_results
        and all(_query_split(result) == "HOLDOUT" for result in holdout_results)
    )
    retrieval_authority = holdout_retrieval_receipt.get("authority")
    checks["untouched_holdout_retrieval_passed"] = bool(
        holdout_only
        and holdout_identities_valid
        and holdout_retrieval_receipt.get("status") == "PASS"
        and holdout_retrieval_receipt.get("logical_retrieval_unit")
        == LOGICAL_RETRIEVAL_UNIT
        and holdout_retrieval_receipt.get("runtime_top_k")
        == deployment.get("runtime_top_k")
        and isinstance(freeze_inputs, Mapping)
        and holdout_retrieval_receipt.get("threshold_policy_digest")
        == freeze_inputs.get("threshold_policy")
        and isinstance(retrieval_authority, Mapping)
        and retrieval_authority.get("human_authority_verified") is True
        and retrieval_authority.get("release_authorizing") is False
    )
    authority_inputs = authority_pipeline_receipt.get("input_digests")
    authority_counts = authority_pipeline_receipt.get("violation_counts")
    checks["authority_pipeline_zero_violations"] = bool(
        authority_pipeline_receipt.get("status") == "PASS"
        and isinstance(authority_counts, Mapping)
        and authority_counts
        and all(value == 0 for value in authority_counts.values())
        and isinstance(authority_inputs, Mapping)
        and authority_inputs.get("graph_snapshot") == deployment.get("graph_sha256")
        and authority_inputs.get("cluster_registry")
        == deployment.get("cluster_registry_sha256")
        and authority_inputs.get("grounding_receipt")
        == grounding_receipt.get("record_digest")
        and authority_inputs.get("activation_manifest")
        == deployment.get("candidate_activation_manifest_sha256")
    )
    runtime_inputs = runtime_quality_receipt.get("input_digests")
    runtime_counts = runtime_quality_receipt.get("violation_counts")
    checks["runtime_quality_passed"] = bool(
        runtime_quality_receipt.get("status") == "PASS"
        and runtime_quality_receipt.get("cluster_count")
        == deployment.get("cluster_count")
        and runtime_quality_receipt.get("runtime_top_k")
        == deployment.get("runtime_top_k")
        and isinstance(runtime_counts, Mapping)
        and runtime_counts
        and all(value == 0 for value in runtime_counts.values())
        and isinstance(runtime_inputs, Mapping)
        and runtime_inputs.get("projection") == deployment.get("projection_sha256")
        and runtime_inputs.get("runtime_config")
        == deployment.get("runtime_config_sha256")
        and runtime_inputs.get("hardware_profile")
        == deployment.get("hardware_profile_sha256")
        and runtime_inputs.get("activation_manifest")
        == deployment.get("candidate_activation_manifest_sha256")
    )
    grounding_authority = grounding_receipt.get("authority")
    checks["grounding_passed"] = bool(
        grounding_receipt.get("status") == "PASS"
        and isinstance(grounding_authority, Mapping)
        and grounding_authority.get("human_authority_verified") is True
        and grounding_authority.get("release_authorizing") is False
    )
    repeatability_authority = repeatability_receipt.get("authority")
    checks["controller_repeatability_passed"] = bool(
        repeatability_receipt.get("status") == "PASS"
        and isinstance(repeatability_authority, Mapping)
        and repeatability_authority.get("runtime_execution_proven") is True
        and repeatability_authority.get("release_authorizing") is False
        and HEX64.fullmatch(
            str(repeatability_authority.get("controller_manifest_digest") or "")
        )
    )
    validity_authority = evaluator_validity_receipt.get("authority")
    checks["evaluator_validity_passed"] = bool(
        evaluator_validity_receipt.get("status") == "PASS"
        and isinstance(validity_authority, Mapping)
        and validity_authority.get("machine_critical_grader_validation_complete")
        is True
        and validity_authority.get("human_agreement_pilot_complete") is True
        and validity_authority.get("release_authorizing") is False
    )
    started_at = _timestamp(holdout_controller_receipt.get("started_at"))
    ended_at = _timestamp(holdout_controller_receipt.get("ended_at"))
    checks["holdout_controller_bound"] = bool(
        holdout_controller_receipt.get("status") == "PASS"
        and holdout_controller_receipt.get("split") == "HOLDOUT"
        and holdout_controller_receipt.get("source_commit")
        == deployment.get("source_commit")
        and holdout_controller_receipt.get("threshold_freeze_digest")
        == threshold_freeze_receipt.get("record_digest")
        and holdout_controller_receipt.get("holdout_retrieval_receipt_digest")
        == holdout_retrieval_receipt.get("record_digest")
        and holdout_controller_receipt.get("runtime_invoked") is True
        and holdout_controller_receipt.get("exit_code") == 0
        and HEX64.fullmatch(
            str(holdout_controller_receipt.get("controller_nonce") or "")
        )
        and HEX64.fullmatch(
            str(holdout_controller_receipt.get("controller_plan_digest") or "")
        )
        and HEX64.fullmatch(
            str(holdout_controller_receipt.get("input_bundle_sha256") or "")
        )
        and started_at is not None
        and ended_at is not None
        and ended_at >= started_at
    )
    for name, passed in checks.items():
        if not passed:
            failures.append(f"CLUSTER_RELEASE_{name.upper()}_FAILED")
    status = "PASS" if not failures else "FAIL"
    input_digests = {
        name: str(value.get("record_digest") or "")
        for name, (value, _expected) in receipts.items()
    }
    return seal_record(
        {
            "schema_version": CLUSTER_RELEASE_QUALIFICATION_SCHEMA,
            "status": status,
            "completion_marker": RELEASE_COMPLETION_MARKER if status == "PASS" else None,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": QUALIFICATION_SCOPE,
            "source_commit": deployment["source_commit"],
            "deployment_bindings": {
                key: deployment[key]
                for key in sorted(_DEPLOYMENT_FIELDS - {"schema_version", "record_digest"})
            },
            "input_receipt_digests": input_digests,
            "checks": checks,
            "failure_codes": sorted(failures),
            "unknown_reasons": [],
            "legacy_regression_only_accepted": False,
            "release_authorizing": status == "PASS",
        }
    )


__all__ = [
    "CLUSTER_DEPLOYMENT_BINDINGS_SCHEMA",
    "CLUSTER_HOLDOUT_CONTROLLER_SCHEMA",
    "CLUSTER_RELEASE_QUALIFICATION_SCHEMA",
    "CLUSTER_THRESHOLD_FREEZE_SCHEMA",
    "QUALIFICATION_SCOPE",
    "RELEASE_COMPLETION_MARKER",
    "THRESHOLD_FREEZE_MARKER",
    "freeze_cluster_calibration_thresholds",
    "qualify_cluster_embedding_release",
]
