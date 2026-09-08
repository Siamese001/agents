from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from apps_rg.evals.authoritative.artifacts import seal_record
from apps_rg.evals.authoritative.cluster_authority import (
    CLUSTER_AUTHORITY_RECEIPT_SCHEMA,
)
from apps_rg.evals.authoritative.cluster_qrel_review import (
    CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA,
)
from apps_rg.evals.authoritative.cluster_release import (
    CLUSTER_DEPLOYMENT_BINDINGS_SCHEMA,
    CLUSTER_HOLDOUT_CONTROLLER_SCHEMA,
    RELEASE_COMPLETION_MARKER,
    THRESHOLD_FREEZE_MARKER,
    freeze_cluster_calibration_thresholds,
    qualify_cluster_embedding_release,
)
from apps_rg.evals.authoritative.cluster_retrieval import (
    CLUSTER_RECEIPT_SCHEMA,
    CLUSTER_THRESHOLD_POLICY_SCHEMA,
    LOGICAL_RETRIEVAL_UNIT,
    seal_cluster_authority_bindings,
)
from apps_rg.evals.authoritative.cluster_runtime import (
    CLUSTER_RUNTIME_RECEIPT_SCHEMA,
)
from apps_rg.evals.authoritative.grounding import (
    RECEIPT_SCHEMA as GROUNDING_SCHEMA,
)
from apps_rg.evals.authoritative.repeatability import (
    RECEIPT_SCHEMA as REPEATABILITY_SCHEMA,
)
from apps_rg.evals.authoritative.validity import RECEIPT_SCHEMA as VALIDITY_SCHEMA

_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
_SOURCE_COMMIT = "a" * 40


def _validate_schema(filename: str, value: dict[str, Any]) -> None:
    schema = json.loads((_SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)


def _deployment() -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_DEPLOYMENT_BINDINGS_SCHEMA,
            "source_commit": _SOURCE_COMMIT,
            "graph_sha256": "1" * 64,
            "cluster_registry_sha256": "2" * 64,
            "corpus_sha256": "3" * 64,
            "model_artifact_sha256": "4" * 64,
            "projection_sha256": "5" * 64,
            "runtime_config_sha256": "6" * 64,
            "hardware_profile_sha256": "7" * 64,
            "candidate_activation_manifest_sha256": "8" * 64,
            "cluster_count": 3,
            "runtime_top_k": 2,
            "dimension": 1024,
            "normalization": "l2",
        }
    )


def _threshold_policy(deployment: dict[str, Any]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_THRESHOLD_POLICY_SCHEMA,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "runtime_top_k": deployment["runtime_top_k"],
            "positive_relevance_floor": 2.0,
            "metric_thresholds": {
                "recall_at_runtime_k_minimum": 0.9,
                "ndcg_at_runtime_k_minimum": 0.85,
                "mrr_minimum": 0.8,
                "hard_negative_rejection_rate_minimum": 1.0,
                "top_k_redundancy_rate_maximum": 0.0,
            },
            "authority_bindings": seal_cluster_authority_bindings(
                {
                    "graph_sha256": deployment["graph_sha256"],
                    "cluster_registry_sha256": deployment[
                        "cluster_registry_sha256"
                    ],
                    "corpus_sha256": deployment["corpus_sha256"],
                    "model_artifact_sha256": deployment[
                        "model_artifact_sha256"
                    ],
                    "projection_sha256": deployment["projection_sha256"],
                    "runtime_config_sha256": deployment[
                        "runtime_config_sha256"
                    ],
                }
            ),
        }
    )


def _qrel_review() -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA,
            "status": "PASS",
            "completion_marker": "CLUSTER_QREL_HUMAN_REVIEWS_COMPLETE",
            "item_count": 4,
            "review_count": 8,
            "adjudication_count": 4,
            "two_human_reviews_per_item": True,
            "adjudication_per_item": True,
            "zero_unresolved_judgments": True,
            "human_authority_verified": True,
            "qrels_ready": True,
            "release_authorizing": False,
            "input_digests": {
                "reviewer_packet": "9" * 64,
                "blinding_manifest": "a" * 64,
                "rubric": "b" * 64,
                "split_policy": "c" * 64,
                "review_bundle": "d" * 64,
                "adjudication_bundle": "e" * 64,
                "human_authority_file_sha256": "f" * 64,
            },
            "unknown_reasons": [],
        }
    )


def _retrieval(
    *,
    split: str,
    threshold_policy: dict[str, Any],
    query_id: str,
) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_RECEIPT_SCHEMA,
            "gate_id": "G1",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": "EVAL_W1_CONTRACT_ONLY",
            "status": "PASS",
            "runtime_top_k": threshold_policy["runtime_top_k"],
            "metrics": {"recall_at_2": 1.0, "ndcg_at_2": 1.0},
            "query_results": [
                {
                    "query_id": query_id,
                    "status": "PASS",
                    "slice_attributes": {"split": [split]},
                }
            ],
            "slices": {},
            "input_digests": {},
            "threshold_policy_digest": threshold_policy["record_digest"],
            "generic_receipt_digest": "1" * 64,
            "failure_codes": [],
            "unknown_reasons": [],
            "authority": {
                "human_authority_verified": True,
                "release_authorizing": False,
            },
        }
    )


def _freeze_inputs() -> dict[str, dict[str, Any]]:
    deployment = _deployment()
    policy = _threshold_policy(deployment)
    return {
        "deployment": deployment,
        "threshold_policy": policy,
        "qrel_review": _qrel_review(),
        "calibration_retrieval": _retrieval(
            split="CALIBRATION",
            threshold_policy=policy,
            query_id="query-calibration",
        ),
    }


def _freeze(case: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return freeze_cluster_calibration_thresholds(
        calibration_retrieval_receipt=case["calibration_retrieval"],
        expected_calibration_retrieval_digest=case["calibration_retrieval"][
            "record_digest"
        ],
        threshold_policy=case["threshold_policy"],
        expected_threshold_policy_digest=case["threshold_policy"]["record_digest"],
        completed_qrel_review_receipt=case["qrel_review"],
        expected_completed_qrel_review_digest=case["qrel_review"]["record_digest"],
        deployment_bindings=case["deployment"],
        expected_deployment_bindings_digest=case["deployment"]["record_digest"],
        source_commit=_SOURCE_COMMIT,
    )


def test_threshold_freeze_accepts_calibration_only() -> None:
    case = _freeze_inputs()
    receipt = _freeze(case)

    assert receipt["status"] == "PASS"
    assert receipt["completion_marker"] == THRESHOLD_FREEZE_MARKER
    assert receipt["calibration_query_ids"] == ["query-calibration"]
    assert receipt["release_authorizing"] is False
    _validate_schema("cluster_deployment_bindings.v1.schema.json", case["deployment"])
    _validate_schema("cluster_threshold_freeze_receipt.v1.schema.json", receipt)


def test_threshold_freeze_rejects_holdout_measurement() -> None:
    case = _freeze_inputs()
    case["calibration_retrieval"]["query_results"][0]["slice_attributes"][
        "split"
    ] = ["HOLDOUT"]
    case["calibration_retrieval"] = seal_record(case["calibration_retrieval"])

    receipt = _freeze(case)

    assert receipt["status"] == "UNKNOWN"
    assert "CLUSTER_THRESHOLD_FREEZE_NON_CALIBRATION_INPUT" in receipt[
        "unknown_reasons"
    ]
    assert receipt["release_authorizing"] is False
    _validate_schema("cluster_threshold_freeze_receipt.v1.schema.json", receipt)


def test_threshold_freeze_rejects_incomplete_metric_policy() -> None:
    case = _freeze_inputs()
    del case["threshold_policy"]["metric_thresholds"]["mrr_minimum"]
    case["threshold_policy"] = seal_record(case["threshold_policy"])
    case["calibration_retrieval"]["threshold_policy_digest"] = case[
        "threshold_policy"
    ]["record_digest"]
    case["calibration_retrieval"] = seal_record(case["calibration_retrieval"])

    receipt = _freeze(case)

    assert receipt["status"] == "UNKNOWN"
    assert "CLUSTER_THRESHOLD_FREEZE_METRICS_INVALID" in receipt["unknown_reasons"]
    assert receipt["release_authorizing"] is False


def _release_case() -> dict[str, dict[str, Any]]:
    base = _freeze_inputs()
    freeze = _freeze(base)
    deployment = base["deployment"]
    grounding = seal_record(
        {
            "schema_version": GROUNDING_SCHEMA,
            "status": "PASS",
            "gate_results": {},
            "input_digests": {},
            "claim_records": [],
            "failure_codes": [],
            "unknown_reasons": [],
            "authority": {
                "human_authority_verified": True,
                "release_authorizing": False,
            },
        }
    )
    holdout = _retrieval(
        split="HOLDOUT",
        threshold_policy=base["threshold_policy"],
        query_id="query-holdout",
    )
    authority_counts = {
        "stale_cluster_count": 0,
        "orphan_cluster_count": 0,
        "missing_member_node_count": 0,
        "missing_member_edge_count": 0,
        "missing_fact_count": 0,
        "missing_metric_count": 0,
        "lifecycle_leak_count": 0,
        "section_policy_leak_count": 0,
        "external_policy_leak_count": 0,
        "authority_bypass_count": 0,
        "duplicate_cluster_output_count": 0,
        "facet_collapse_mismatch_count": 0,
        "unsupported_claim_count": 0,
        "allocation_binding_mismatch_count": 0,
    }
    authority = seal_record(
        {
            "schema_version": CLUSTER_AUTHORITY_RECEIPT_SCHEMA,
            "status": "PASS",
            "violation_counts": authority_counts,
            "input_digests": {
                "graph_snapshot": deployment["graph_sha256"],
                "cluster_registry": deployment["cluster_registry_sha256"],
                "grounding_receipt": grounding["record_digest"],
                "activation_manifest": deployment[
                    "candidate_activation_manifest_sha256"
                ],
            },
            "authority": {"release_authorizing": False},
        }
    )
    runtime_counts = {
        "run_count_shortfall_count": 0,
        "runtime_binding_mismatch_count": 0,
        "bounded_k_violation_count": 0,
        "ranking_nondeterminism_count": 0,
        "rehydration_nondeterminism_count": 0,
        "latency_threshold_violation_count": 0,
        "missing_failure_probe_count": 0,
        "failure_probe_violation_count": 0,
    }
    runtime = seal_record(
        {
            "schema_version": CLUSTER_RUNTIME_RECEIPT_SCHEMA,
            "status": "PASS",
            "cluster_count": deployment["cluster_count"],
            "runtime_top_k": deployment["runtime_top_k"],
            "violation_counts": runtime_counts,
            "input_digests": {
                "projection": deployment["projection_sha256"],
                "runtime_config": deployment["runtime_config_sha256"],
                "hardware_profile": deployment["hardware_profile_sha256"],
                "activation_manifest": deployment[
                    "candidate_activation_manifest_sha256"
                ],
            },
            "authority": {"release_authorizing": False},
        }
    )
    repeatability = seal_record(
        {
            "schema_version": REPEATABILITY_SCHEMA,
            "status": "PASS",
            "authority": {
                "runtime_execution_proven": True,
                "controller_manifest_digest": "1" * 64,
                "release_authorizing": False,
            },
        }
    )
    validity = seal_record(
        {
            "schema_version": VALIDITY_SCHEMA,
            "status": "PASS",
            "authority": {
                "machine_critical_grader_validation_complete": True,
                "human_agreement_pilot_complete": True,
                "release_authorizing": False,
            },
        }
    )
    controller = seal_record(
        {
            "schema_version": CLUSTER_HOLDOUT_CONTROLLER_SCHEMA,
            "status": "PASS",
            "split": "HOLDOUT",
            "controller_id": "cluster-release-controller",
            "controller_nonce": "2" * 64,
            "execution_id": "cluster-holdout-once",
            "source_commit": _SOURCE_COMMIT,
            "controller_plan_digest": "3" * 64,
            "input_bundle_sha256": "4" * 64,
            "threshold_freeze_digest": freeze["record_digest"],
            "holdout_retrieval_receipt_digest": holdout["record_digest"],
            "started_at": "2026-08-02T18:00:00Z",
            "ended_at": "2026-08-02T18:01:00Z",
            "runtime_invoked": True,
            "exit_code": 0,
        }
    )
    return {
        "deployment": deployment,
        "threshold_freeze": freeze,
        "qrel_review": base["qrel_review"],
        "holdout_retrieval": holdout,
        "authority_pipeline": authority,
        "runtime_quality": runtime,
        "grounding": grounding,
        "repeatability": repeatability,
        "evaluator_validity": validity,
        "holdout_controller": controller,
    }


def _qualify(case: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return qualify_cluster_embedding_release(
        deployment_bindings=case["deployment"],
        expected_deployment_bindings_digest=case["deployment"]["record_digest"],
        threshold_freeze_receipt=case["threshold_freeze"],
        expected_threshold_freeze_digest=case["threshold_freeze"]["record_digest"],
        completed_qrel_review_receipt=case["qrel_review"],
        expected_completed_qrel_review_digest=case["qrel_review"]["record_digest"],
        holdout_retrieval_receipt=case["holdout_retrieval"],
        expected_holdout_retrieval_digest=case["holdout_retrieval"]["record_digest"],
        authority_pipeline_receipt=case["authority_pipeline"],
        expected_authority_pipeline_digest=case["authority_pipeline"]["record_digest"],
        runtime_quality_receipt=case["runtime_quality"],
        expected_runtime_quality_digest=case["runtime_quality"]["record_digest"],
        grounding_receipt=case["grounding"],
        expected_grounding_digest=case["grounding"]["record_digest"],
        repeatability_receipt=case["repeatability"],
        expected_repeatability_digest=case["repeatability"]["record_digest"],
        evaluator_validity_receipt=case["evaluator_validity"],
        expected_evaluator_validity_digest=case["evaluator_validity"][
            "record_digest"
        ],
        holdout_controller_receipt=case["holdout_controller"],
        expected_holdout_controller_digest=case["holdout_controller"][
            "record_digest"
        ],
    )


def test_release_qualification_aggregates_exact_holdout_chain() -> None:
    case = _release_case()
    receipt = _qualify(case)

    assert receipt["status"] == "PASS"
    assert receipt["completion_marker"] == RELEASE_COMPLETION_MARKER
    assert receipt["release_authorizing"] is True
    assert receipt["legacy_regression_only_accepted"] is False
    assert all(receipt["checks"].values())
    _validate_schema(
        "cluster_holdout_controller_receipt.v1.schema.json",
        case["holdout_controller"],
    )
    _validate_schema("cluster_release_qualification_receipt.v1.schema.json", receipt)


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        ("holdout_split", "untouched_holdout_retrieval_passed"),
        ("holdout_overlap", "untouched_holdout_retrieval_passed"),
        ("freeze_semantics", "calibration_thresholds_frozen"),
        ("authority", "authority_pipeline_zero_violations"),
        ("runtime", "runtime_quality_passed"),
        ("qrels", "human_qrels_complete"),
        ("grounding", "grounding_passed"),
        ("repeatability", "controller_repeatability_passed"),
        ("validity", "evaluator_validity_passed"),
        ("controller", "holdout_controller_bound"),
    ],
)
def test_release_qualification_mutations_cannot_authorize(
    mutation: str,
    failed_check: str,
) -> None:
    case = _release_case()
    if mutation == "holdout_split":
        case["holdout_retrieval"]["query_results"][0]["slice_attributes"][
            "split"
        ] = ["CALIBRATION"]
        case["holdout_retrieval"] = seal_record(case["holdout_retrieval"])
    elif mutation == "holdout_overlap":
        case["holdout_retrieval"]["query_results"][0]["query_id"] = (
            "query-calibration"
        )
        case["holdout_retrieval"] = seal_record(case["holdout_retrieval"])
    elif mutation == "freeze_semantics":
        case["threshold_freeze"]["frozen_thresholds"] = {}
        case["threshold_freeze"] = seal_record(case["threshold_freeze"])
    elif mutation == "authority":
        case["authority_pipeline"]["violation_counts"]["stale_cluster_count"] = 1
        case["authority_pipeline"] = seal_record(case["authority_pipeline"])
    elif mutation == "runtime":
        case["runtime_quality"]["input_digests"]["projection"] = "f" * 64
        case["runtime_quality"] = seal_record(case["runtime_quality"])
    elif mutation == "qrels":
        case["qrel_review"]["zero_unresolved_judgments"] = False
        case["qrel_review"] = seal_record(case["qrel_review"])
    elif mutation == "grounding":
        case["grounding"]["status"] = "FAIL"
        case["grounding"] = seal_record(case["grounding"])
    elif mutation == "repeatability":
        case["repeatability"]["status"] = "FAIL"
        case["repeatability"] = seal_record(case["repeatability"])
    elif mutation == "validity":
        case["evaluator_validity"]["status"] = "FAIL"
        case["evaluator_validity"] = seal_record(case["evaluator_validity"])
    elif mutation == "controller":
        case["holdout_controller"]["runtime_invoked"] = False
        case["holdout_controller"] = seal_record(case["holdout_controller"])

    receipt = _qualify(case)

    assert receipt["status"] == "FAIL"
    assert receipt["checks"][failed_check] is False
    assert receipt["release_authorizing"] is False


def test_legacy_regression_receipt_cannot_replace_w4_freeze() -> None:
    case = _release_case()
    legacy = seal_record(
        {
            "schema_version": "apps_rg.graph_embedding_qualification_report.v1",
            "status": "PASS",
            "qualification_scope": "REGRESSION_ONLY",
            "release_authorizing": False,
        }
    )
    case["threshold_freeze"] = legacy

    receipt = _qualify(case)

    assert receipt["status"] == "UNKNOWN"
    assert receipt["release_authorizing"] is False
    assert receipt["legacy_regression_only_accepted"] is False
    _validate_schema("cluster_release_qualification_receipt.v1.schema.json", receipt)
