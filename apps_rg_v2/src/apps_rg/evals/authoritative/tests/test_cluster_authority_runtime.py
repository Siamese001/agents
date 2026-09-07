from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from apps_rg.evals.authoritative.artifacts import seal_record
from apps_rg.evals.authoritative.cluster_authority import (
    CLUSTER_ALLOCATION_TRACE_SCHEMA,
    CLUSTER_AUTHORITY_POLICY_SCHEMA,
    CLUSTER_GRAPH_SNAPSHOT_SCHEMA,
    CLUSTER_REGISTRY_SCHEMA,
    CLUSTER_REHYDRATION_TRACE_SCHEMA,
    evaluate_cluster_authority_pipeline,
    seal_cluster_authority_envelope,
)
from apps_rg.evals.authoritative.cluster_retrieval import LOGICAL_RETRIEVAL_UNIT
from apps_rg.evals.authoritative.cluster_runtime import (
    CLUSTER_RUNTIME_POLICY_SCHEMA,
    CLUSTER_RUNTIME_RUN_SET_SCHEMA,
    evaluate_cluster_runtime_quality,
)
from apps_rg.evals.authoritative.grounding import RECEIPT_SCHEMA as GROUNDING_SCHEMA

_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"


def _validate_receipt_schema(filename: str, receipt: dict[str, Any]) -> None:
    schema = json.loads((_SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(receipt)


def _authority_case() -> dict[str, dict[str, Any]]:
    graph = seal_record(
        {
            "schema_version": CLUSTER_GRAPH_SNAPSHOT_SCHEMA,
            "nodes": [
                {
                    "node_id": f"node-{index}",
                    "activation_status": "ACTIVE_CONFIRMED",
                    "external_claim_policy": "source_bound_only",
                }
                for index in (1, 2, 3)
            ],
            "edges": [
                {
                    "edge_id": "edge-1",
                    "source_node_id": "node-1",
                    "target_node_id": "node-2",
                    "activation_status": "ACTIVE_CONFIRMED",
                    "external_claim_policy": "source_bound_only",
                }
            ],
            "facts": [
                {
                    "fact_id": f"fact-{index}",
                    "activation_status": "ACTIVE_CONFIRMED",
                    "external_claim_policy": "source_bound_only",
                }
                for index in (1, 2, 3)
            ],
            "metrics": [
                {
                    "metric_id": "metric-1",
                    "activation_status": "ACTIVE_CONFIRMED",
                    "external_claim_policy": "source_bound_only",
                }
            ],
        }
    )
    clusters = []
    for index in (1, 2, 3):
        cluster = {
            "cluster_id": f"cluster-{index}",
            "cluster_kind": (
                "role_episode" if index < 3 else "capability_evidence"
            ),
            "canonical_embedding_text": (
                f"Led evidence-backed operating improvement {index}."
            ),
            "member_node_ids": [f"node-{index}"],
            "member_edge_ids": ["edge-1"],
            "linked_fact_ids": [f"fact-{index}"],
            "linked_metric_ids": ["metric-1"] if index == 1 else [],
            "allowed_sections": ["experience"],
            "activation_status": "ACTIVE_CONFIRMED",
            "external_claim_policy": "source_bound_only",
        }
        cluster["authority_envelope_sha256"] = seal_cluster_authority_envelope(
            cluster,
            graph_digest=graph["record_digest"],
        )
        clusters.append(cluster)
    registry = seal_record(
        {
            "schema_version": CLUSTER_REGISTRY_SCHEMA,
            "graph_digest": graph["record_digest"],
            "clusters": clusters,
        }
    )

    def hydrated(cluster: dict[str, Any]) -> dict[str, Any]:
        return {
            key: deepcopy(value)
            for key, value in cluster.items()
            if key != "canonical_embedding_text"
        }

    trace = seal_record(
        {
            "schema_version": CLUSTER_REHYDRATION_TRACE_SCHEMA,
            "graph_digest": graph["record_digest"],
            "cluster_registry_digest": registry["record_digest"],
            "activation_manifest_sha256": "a" * 64,
            "runtime_config_sha256": "b" * 64,
            "runtime_top_k": 2,
            "queries": [
                {
                    "query_id": "query-1",
                    "section": "experience",
                    "raw_hits": [
                        {
                            "facet_id": "facet-cluster-1-claim",
                            "cluster_id": "cluster-1",
                            "rank": 1,
                            "score": 0.99,
                        },
                        {
                            "facet_id": "facet-cluster-1-evidence",
                            "cluster_id": "cluster-1",
                            "rank": 2,
                            "score": 0.98,
                        },
                        {
                            "facet_id": None,
                            "cluster_id": "cluster-2",
                            "rank": 3,
                            "score": 0.90,
                        },
                    ],
                    "rehydrated_clusters": [
                        hydrated(clusters[0]),
                        hydrated(clusters[1]),
                    ],
                }
            ],
        }
    )
    grounding = seal_record(
        {
            "schema_version": GROUNDING_SCHEMA,
            "status": "PASS",
            "gate_results": {},
            "input_digests": {},
            "claim_records": [
                {
                    "claim_id": "claim-1",
                    "support_disposition": "SUPPORTED",
                    "path_binding": "EXACT",
                    "graph_path": ["node-1"],
                }
            ],
            "failure_codes": [],
            "unknown_reasons": [],
            "authority": {
                "human_authority_verified": True,
                "release_authorizing": False,
            },
        }
    )
    allocation = seal_record(
        {
            "schema_version": CLUSTER_ALLOCATION_TRACE_SCHEMA,
            "graph_digest": graph["record_digest"],
            "cluster_registry_digest": registry["record_digest"],
            "rehydration_trace_digest": trace["record_digest"],
            "grounding_receipt_digest": grounding["record_digest"],
            "activation_manifest_sha256": trace["activation_manifest_sha256"],
            "allocations": [
                {
                    "query_id": "query-1",
                    "section": "experience",
                    "selected_cluster_ids": ["cluster-1"],
                    "claims": [
                        {
                            "claim_id": "claim-1",
                            "cluster_id": "cluster-1",
                            "member_node_ids": ["node-1"],
                            "fact_ids": ["fact-1"],
                            "metric_ids": ["metric-1"],
                            "graph_path": ["node-1", "edge-1"],
                        }
                    ],
                }
            ],
        }
    )
    policy = seal_record(
        {
            "schema_version": CLUSTER_AUTHORITY_POLICY_SCHEMA,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "retrievable_lifecycle_states": ["ACTIVE", "ACTIVE_CONFIRMED"],
            "allowed_external_claim_policies": ["source_bound_only"],
            "violation_maxima": {
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
            },
        }
    )
    return {
        "graph": graph,
        "registry": registry,
        "trace": trace,
        "allocation": allocation,
        "grounding": grounding,
        "policy": policy,
    }


def _reseal_authority_chain(case: dict[str, dict[str, Any]]) -> None:
    case["graph"] = seal_record(case["graph"])
    case["registry"]["graph_digest"] = case["graph"]["record_digest"]
    case["registry"] = seal_record(case["registry"])
    case["trace"]["graph_digest"] = case["graph"]["record_digest"]
    case["trace"]["cluster_registry_digest"] = case["registry"]["record_digest"]
    case["trace"] = seal_record(case["trace"])
    case["allocation"]["graph_digest"] = case["graph"]["record_digest"]
    case["allocation"]["cluster_registry_digest"] = case["registry"][
        "record_digest"
    ]
    case["allocation"]["rehydration_trace_digest"] = case["trace"][
        "record_digest"
    ]
    case["allocation"] = seal_record(case["allocation"])


def _evaluate_authority(case: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return evaluate_cluster_authority_pipeline(
        graph_snapshot=case["graph"],
        expected_graph_digest=case["graph"]["record_digest"],
        cluster_registry=case["registry"],
        expected_cluster_registry_digest=case["registry"]["record_digest"],
        rehydration_trace=case["trace"],
        expected_rehydration_trace_digest=case["trace"]["record_digest"],
        allocation_trace=case["allocation"],
        expected_allocation_trace_digest=case["allocation"]["record_digest"],
        grounding_receipt=case["grounding"],
        expected_grounding_receipt_digest=case["grounding"]["record_digest"],
        safety_policy=case["policy"],
        expected_safety_policy_digest=case["policy"]["record_digest"],
    )


def test_cluster_authority_pipeline_passes_exact_rehydration_and_facet_collapse() -> None:
    receipt = _evaluate_authority(_authority_case())

    assert receipt["status"] == "PASS"
    assert receipt["retrieved_cluster_count"] == 2
    assert receipt["claim_count"] == 1
    assert set(receipt["violation_counts"].values()) == {0}
    assert receipt["checks"]["exact_rehydration"] is True
    assert receipt["checks"]["facets_collapsed_to_unique_clusters"] is True
    assert receipt["checks"]["claims_graph_and_fact_backed"] is True
    assert receipt["authority"]["release_authorizing"] is False
    _validate_receipt_schema("cluster_authority_receipt.v1.schema.json", receipt)


def test_cluster_authority_policy_cannot_relax_zero_tolerance() -> None:
    case = _authority_case()
    case["policy"]["violation_maxima"]["stale_cluster_count"] = 1
    case["policy"] = seal_record(case["policy"])

    receipt = _evaluate_authority(case)

    assert receipt["status"] == "UNKNOWN"
    assert "CLUSTER_AUTHORITY_POLICY_NOT_ZERO_TOLERANCE" in receipt[
        "unknown_reasons"
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_counter"),
    [
        ("stale", "stale_cluster_count"),
        ("orphan", "orphan_cluster_count"),
        ("missing_member", "missing_member_node_count"),
        ("held", "lifecycle_leak_count"),
        ("section", "section_policy_leak_count"),
        ("policy", "external_policy_leak_count"),
        ("duplicate", "duplicate_cluster_output_count"),
        ("unsupported_claim", "unsupported_claim_count"),
        ("grounding", "allocation_binding_mismatch_count"),
        ("authority_bypass", "authority_bypass_count"),
    ],
)
def test_cluster_authority_mutations_fail_closed(
    mutation: str,
    expected_counter: str,
) -> None:
    case = _authority_case()
    registry_cluster = case["registry"]["clusters"][0]
    hydrated = case["trace"]["queries"][0]["rehydrated_clusters"]
    if mutation == "stale":
        registry_cluster["canonical_embedding_text"] = "tampered semantic text"
    elif mutation == "orphan":
        case["trace"]["queries"][0]["raw_hits"].append(
            {
                "facet_id": None,
                "cluster_id": "cluster-orphan",
                "rank": 4,
                "score": 0.1,
            }
        )
    elif mutation == "missing_member":
        case["graph"]["nodes"] = case["graph"]["nodes"][1:]
    elif mutation == "held":
        registry_cluster["activation_status"] = "HELD"
        registry_cluster["authority_envelope_sha256"] = (
            seal_cluster_authority_envelope(
                registry_cluster,
                graph_digest=case["graph"]["record_digest"],
            )
        )
        hydrated[0]["activation_status"] = "HELD"
        hydrated[0]["authority_envelope_sha256"] = registry_cluster[
            "authority_envelope_sha256"
        ]
    elif mutation == "section":
        case["trace"]["queries"][0]["section"] = "summary"
        case["allocation"]["allocations"][0]["section"] = "summary"
    elif mutation == "policy":
        registry_cluster["external_claim_policy"] = "internal_only"
        registry_cluster["authority_envelope_sha256"] = (
            seal_cluster_authority_envelope(
                registry_cluster,
                graph_digest=case["graph"]["record_digest"],
            )
        )
        hydrated[0]["external_claim_policy"] = "internal_only"
        hydrated[0]["authority_envelope_sha256"] = registry_cluster[
            "authority_envelope_sha256"
        ]
    elif mutation == "duplicate":
        hydrated.append(deepcopy(hydrated[0]))
    elif mutation == "unsupported_claim":
        case["allocation"]["allocations"][0]["claims"][0]["fact_ids"] = [
            "fact-2"
        ]
    elif mutation == "grounding":
        case["grounding"]["claim_records"][0]["support_disposition"] = "UNSUPPORTED"
        case["grounding"] = seal_record(case["grounding"])
        case["allocation"]["grounding_receipt_digest"] = case["grounding"][
            "record_digest"
        ]
    elif mutation == "authority_bypass":
        hydrated[1] = {
            key: deepcopy(value)
            for key, value in case["registry"]["clusters"][2].items()
            if key != "canonical_embedding_text"
        }
    _reseal_authority_chain(case)

    receipt = _evaluate_authority(case)

    assert receipt["status"] == "FAIL"
    assert receipt["violation_counts"][expected_counter] > 0
    assert receipt["authority"]["release_authorizing"] is False


def _runtime_case() -> dict[str, dict[str, Any]]:
    bindings = {
        "activation_manifest_sha256": "a" * 64,
        "projection_sha256": "b" * 64,
        "runtime_config_sha256": "c" * 64,
        "hardware_profile_sha256": "e" * 64,
        "cluster_count": 3,
        "runtime_top_k": 2,
    }
    policy = seal_record(
        {
            "schema_version": CLUSTER_RUNTIME_POLICY_SCHEMA,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            **bindings,
            "minimum_cold_runs": 3,
            "minimum_warm_runs": 3,
            "retrieval_cold_p95_ms_maximum": 50.0,
            "retrieval_warm_p95_ms_maximum": 20.0,
            "end_to_end_cold_p95_ms_maximum": 100.0,
            "end_to_end_warm_p95_ms_maximum": 40.0,
            "required_failure_probes": ["MANIFEST_MISSING", "MANIFEST_INVALID"],
        }
    )
    runs = []
    for phase, retrieval_base, e2e_base in (
        ("COLD", 20.0, 40.0),
        ("WARM", 5.0, 10.0),
    ):
        for repetition in (1, 2, 3):
            runs.append(
                {
                    "run_id": f"{phase.lower()}-{repetition}",
                    "phase": phase,
                    "repetition": repetition,
                    "status": "PASS",
                    **bindings,
                    "query_results": [
                        {
                            "query_id": "query-1",
                            "ranked_cluster_ids": ["cluster-1", "cluster-2"],
                            "rehydrated_output_sha256": "d" * 64,
                            "retrieval_latency_ms": retrieval_base + repetition,
                            "end_to_end_latency_ms": e2e_base + repetition,
                        }
                    ],
                }
            )
    run_set = seal_record(
        {
            "schema_version": CLUSTER_RUNTIME_RUN_SET_SCHEMA,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            **bindings,
            "runs": runs,
            "failure_probes": [
                {
                    "probe_id": "missing-manifest",
                    "failure_kind": "MANIFEST_MISSING",
                    "status": "FAIL_CLOSED",
                    "error_code": "ACTIVATION_MANIFEST_MISSING",
                    "emitted_cluster_ids": [],
                },
                {
                    "probe_id": "invalid-manifest",
                    "failure_kind": "MANIFEST_INVALID",
                    "status": "FAIL_CLOSED",
                    "error_code": "ACTIVATION_MANIFEST_INVALID",
                    "emitted_cluster_ids": [],
                },
            ],
        }
    )
    return {"policy": policy, "run_set": run_set}


def _evaluate_runtime(case: dict[str, dict[str, Any]]) -> dict[str, Any]:
    case["run_set"] = seal_record(case["run_set"])
    return evaluate_cluster_runtime_quality(
        run_set=case["run_set"],
        expected_run_set_digest=case["run_set"]["record_digest"],
        runtime_policy=case["policy"],
        expected_runtime_policy_digest=case["policy"]["record_digest"],
    )


def test_cluster_runtime_quality_passes_repeated_cold_warm_runs() -> None:
    receipt = _evaluate_runtime(_runtime_case())

    assert receipt["status"] == "PASS"
    assert receipt["cluster_count"] == 3
    assert receipt["phase_metrics"]["cold"]["run_count"] == 3
    assert receipt["phase_metrics"]["warm"]["run_count"] == 3
    assert receipt["phase_metrics"]["cold"]["retrieval_p95_ms"] == 23.0
    assert receipt["phase_metrics"]["warm"]["end_to_end_p95_ms"] == 13.0
    assert set(receipt["violation_counts"].values()) == {0}
    assert receipt["checks"]["invalid_manifest_fails_closed"] is True
    assert receipt["authority"]["release_authorizing"] is False
    _validate_receipt_schema("cluster_runtime_receipt.v1.schema.json", receipt)


def test_cluster_runtime_policy_requires_three_runs_and_bounded_top_k() -> None:
    case = _runtime_case()
    case["policy"]["minimum_cold_runs"] = 2
    case["policy"]["runtime_top_k"] = 3
    case["policy"] = seal_record(case["policy"])

    receipt = _evaluate_runtime(case)

    assert receipt["status"] == "UNKNOWN"
    assert "CLUSTER_RUNTIME_POLICY_MINIMUM_COLD_RUNS_INVALID" in receipt[
        "unknown_reasons"
    ]
    assert "CLUSTER_RUNTIME_POLICY_TOP_K_NOT_BOUNDED" in receipt[
        "unknown_reasons"
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_counter"),
    [
        ("ranking", "ranking_nondeterminism_count"),
        ("rehydration", "rehydration_nondeterminism_count"),
        ("top_k", "bounded_k_violation_count"),
        ("latency", "latency_threshold_violation_count"),
        ("binding", "runtime_binding_mismatch_count"),
        ("failure_probe", "failure_probe_violation_count"),
        ("missing_probe", "missing_failure_probe_count"),
    ],
)
def test_cluster_runtime_mutations_are_detected(
    mutation: str,
    expected_counter: str,
) -> None:
    case = _runtime_case()
    run = case["run_set"]["runs"][0]
    query = run["query_results"][0]
    if mutation == "ranking":
        query["ranked_cluster_ids"] = ["cluster-2", "cluster-1"]
    elif mutation == "rehydration":
        query["rehydrated_output_sha256"] = "e" * 64
    elif mutation == "top_k":
        query["ranked_cluster_ids"].append("cluster-3")
    elif mutation == "latency":
        query["retrieval_latency_ms"] = 500.0
        query["end_to_end_latency_ms"] = 600.0
    elif mutation == "binding":
        run["projection_sha256"] = "f" * 64
    elif mutation == "failure_probe":
        case["run_set"]["failure_probes"][0]["emitted_cluster_ids"] = [
            "cluster-1"
        ]
    elif mutation == "missing_probe":
        case["run_set"]["failure_probes"].pop()

    receipt = _evaluate_runtime(case)

    assert receipt["status"] == "FAIL"
    assert receipt["violation_counts"][expected_counter] > 0
    assert receipt["authority"]["release_authorizing"] is False
