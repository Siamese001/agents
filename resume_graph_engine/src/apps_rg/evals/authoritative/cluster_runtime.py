"""Source-bound W3 determinism, latency, and failure-policy evaluation."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from .artifacts import HEX64, seal_record, validate_pinned_record
from .cluster_retrieval import LOGICAL_RETRIEVAL_UNIT

CLUSTER_RUNTIME_POLICY_SCHEMA = "apps_rg.cluster_runtime_policy.v1"
CLUSTER_RUNTIME_RUN_SET_SCHEMA = "apps_rg.cluster_runtime_run_set.v1"
CLUSTER_RUNTIME_RECEIPT_SCHEMA = "apps_rg.cluster_runtime_receipt.v1"
QUALIFICATION_SCOPE = "EVAL_W3_NON_RELEASE_AUTHORIZING"

_PHASES = ("COLD", "WARM")
_FAILURE_KINDS = frozenset({"MANIFEST_MISSING", "MANIFEST_INVALID"})
_COUNTERS = frozenset(
    {
        "run_count_shortfall_count",
        "runtime_binding_mismatch_count",
        "bounded_k_violation_count",
        "ranking_nondeterminism_count",
        "rehydration_nondeterminism_count",
        "latency_threshold_violation_count",
        "missing_failure_probe_count",
        "failure_probe_violation_count",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "logical_retrieval_unit",
        "activation_manifest_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
        "cluster_count",
        "runtime_top_k",
        "minimum_cold_runs",
        "minimum_warm_runs",
        "retrieval_cold_p95_ms_maximum",
        "retrieval_warm_p95_ms_maximum",
        "end_to_end_cold_p95_ms_maximum",
        "end_to_end_warm_p95_ms_maximum",
        "required_failure_probes",
        "record_digest",
    }
)
_RUN_SET_FIELDS = frozenset(
    {
        "schema_version",
        "logical_retrieval_unit",
        "activation_manifest_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
        "cluster_count",
        "runtime_top_k",
        "runs",
        "failure_probes",
        "record_digest",
    }
)
_RUN_FIELDS = frozenset(
    {
        "run_id",
        "phase",
        "repetition",
        "status",
        "activation_manifest_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
        "cluster_count",
        "runtime_top_k",
        "query_results",
    }
)
_QUERY_FIELDS = frozenset(
    {
        "query_id",
        "ranked_cluster_ids",
        "rehydrated_output_sha256",
        "retrieval_latency_ms",
        "end_to_end_latency_ms",
    }
)
_PROBE_FIELDS = frozenset(
    {"probe_id", "failure_kind", "status", "error_code", "emitted_cluster_ids"}
)


def _finite_nonnegative(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _empty_phase_metrics() -> dict[str, dict[str, float | int | None]]:
    return {
        phase.lower(): {
            "run_count": 0,
            "query_observation_count": 0,
            "retrieval_p50_ms": None,
            "retrieval_p95_ms": None,
            "end_to_end_p50_ms": None,
            "end_to_end_p95_ms": None,
        }
        for phase in _PHASES
    }


def _unknown(reasons: Sequence[str]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_RUNTIME_RECEIPT_SCHEMA,
            "gate_id": "W3_RUNTIME_QUALITY",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": QUALIFICATION_SCOPE,
            "status": "UNKNOWN",
            "cluster_count": None,
            "runtime_top_k": None,
            "phase_metrics": _empty_phase_metrics(),
            "violation_counts": dict.fromkeys(sorted(_COUNTERS), 0),
            "checks": {},
            "input_digests": {},
            "failure_codes": [],
            "unknown_reasons": sorted(set(reasons)),
            "authority": {
                "measurement_scope": "SOURCE_BOUND_CLUSTER_RUNTIME_QUALITY",
                "release_authorizing": False,
            },
        }
    )


def _validate_policy(
    value: object, *, expected_digest: str
) -> tuple[dict[str, Any], list[str]]:
    reasons = validate_pinned_record(
        value,
        expected_digest=expected_digest,
        schema_version=CLUSTER_RUNTIME_POLICY_SCHEMA,
    )
    if not isinstance(value, Mapping):
        return {}, reasons
    policy = dict(value)
    if set(policy) != _POLICY_FIELDS:
        reasons.append("CLUSTER_RUNTIME_POLICY_SCHEMA_INVALID")
    if policy.get("logical_retrieval_unit") != LOGICAL_RETRIEVAL_UNIT:
        reasons.append("CLUSTER_RUNTIME_POLICY_UNIT_INVALID")
    for field in (
        "activation_manifest_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
    ):
        if not HEX64.fullmatch(str(policy.get(field) or "")):
            reasons.append("CLUSTER_RUNTIME_POLICY_BINDING_INVALID")
    for field in ("runtime_top_k", "minimum_cold_runs", "minimum_warm_runs"):
        item = policy.get(field)
        minimum = 1 if field == "runtime_top_k" else 3
        if not isinstance(item, int) or isinstance(item, bool) or item < minimum:
            reasons.append(f"CLUSTER_RUNTIME_POLICY_{field.upper()}_INVALID")
    cluster_count = policy.get("cluster_count")
    if (
        not isinstance(cluster_count, int)
        or isinstance(cluster_count, bool)
        or cluster_count < 2
        or not isinstance(policy.get("runtime_top_k"), int)
        or policy["runtime_top_k"] >= cluster_count
    ):
        reasons.append("CLUSTER_RUNTIME_POLICY_TOP_K_NOT_BOUNDED")
    for field in (
        "retrieval_cold_p95_ms_maximum",
        "retrieval_warm_p95_ms_maximum",
        "end_to_end_cold_p95_ms_maximum",
        "end_to_end_warm_p95_ms_maximum",
    ):
        if not _finite_nonnegative(policy.get(field)):
            reasons.append("CLUSTER_RUNTIME_POLICY_LATENCY_THRESHOLD_INVALID")
    probes = policy.get("required_failure_probes")
    if (
        not isinstance(probes, list)
        or set(probes) != _FAILURE_KINDS
        or len(probes) != len(set(probes))
    ):
        reasons.append("CLUSTER_RUNTIME_POLICY_FAILURE_PROBES_INVALID")
    return policy, sorted(set(reasons))


def evaluate_cluster_runtime_quality(
    *,
    run_set: Mapping[str, Any],
    expected_run_set_digest: str,
    runtime_policy: Mapping[str, Any],
    expected_runtime_policy_digest: str,
) -> dict[str, Any]:
    """Evaluate repeated real-runtime observations against a pinned policy."""

    reasons = validate_pinned_record(
        run_set,
        expected_digest=expected_run_set_digest,
        schema_version=CLUSTER_RUNTIME_RUN_SET_SCHEMA,
    )
    policy, policy_reasons = _validate_policy(
        runtime_policy,
        expected_digest=expected_runtime_policy_digest,
    )
    reasons.extend(policy_reasons)
    if not isinstance(run_set, Mapping) or not isinstance(runtime_policy, Mapping):
        return _unknown(reasons + ["CLUSTER_RUNTIME_INPUT_NOT_OBJECT"])
    if set(run_set) != _RUN_SET_FIELDS:
        reasons.append("CLUSTER_RUNTIME_RUN_SET_SCHEMA_INVALID")
    if run_set.get("logical_retrieval_unit") != LOGICAL_RETRIEVAL_UNIT:
        reasons.append("CLUSTER_RUNTIME_RUN_SET_UNIT_INVALID")
    for field in (
        "activation_manifest_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
    ):
        if not HEX64.fullmatch(str(run_set.get(field) or "")):
            reasons.append("CLUSTER_RUNTIME_RUN_SET_BINDING_INVALID")
    runtime_top_k = run_set.get("runtime_top_k")
    cluster_count = run_set.get("cluster_count")
    if (
        not isinstance(runtime_top_k, int)
        or isinstance(runtime_top_k, bool)
        or runtime_top_k < 1
        or not isinstance(cluster_count, int)
        or isinstance(cluster_count, bool)
        or cluster_count < 2
        or runtime_top_k >= cluster_count
    ):
        reasons.append("CLUSTER_RUNTIME_TOP_K_INVALID")
    runs = run_set.get("runs")
    probes = run_set.get("failure_probes")
    if not isinstance(runs, list) or not runs:
        reasons.append("CLUSTER_RUNTIME_RUNS_EMPTY")
        runs = []
    if not isinstance(probes, list):
        reasons.append("CLUSTER_RUNTIME_FAILURE_PROBES_INVALID")
        probes = []
    if reasons:
        return _unknown(reasons)

    violations: dict[str, set[str]] = {name: set() for name in _COUNTERS}

    def add(counter: str, identity: str) -> None:
        violations[counter].add(identity)

    binding_fields = (
        "activation_manifest_sha256",
        "projection_sha256",
        "runtime_config_sha256",
        "hardware_profile_sha256",
        "cluster_count",
        "runtime_top_k",
    )
    if any(run_set[field] != policy[field] for field in binding_fields):
        add("runtime_binding_mismatch_count", "RUN_SET_POLICY")

    runs_by_phase: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    run_ids: set[str] = set()
    repetitions: set[tuple[str, int]] = set()
    ranking_observations: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    rehydration_observations: dict[str, list[str]] = defaultdict(list)
    retrieval_latencies: dict[str, list[float]] = defaultdict(list)
    end_to_end_latencies: dict[str, list[float]] = defaultdict(list)
    expected_query_ids: set[str] | None = None
    for run in runs:
        if not isinstance(run, Mapping) or set(run) != _RUN_FIELDS:
            return _unknown(["CLUSTER_RUNTIME_RUN_SCHEMA_INVALID"])
        run_id = str(run.get("run_id") or "")
        phase = str(run.get("phase") or "")
        repetition = run.get("repetition")
        if (
            not run_id
            or run_id in run_ids
            or phase not in _PHASES
            or not isinstance(repetition, int)
            or isinstance(repetition, bool)
            or repetition < 1
            or (phase, repetition) in repetitions
            or run.get("status") != "PASS"
        ):
            return _unknown(["CLUSTER_RUNTIME_RUN_IDENTITY_OR_STATUS_INVALID"])
        run_ids.add(run_id)
        repetitions.add((phase, repetition))
        runs_by_phase[phase].append(run)
        if any(run.get(field) != policy.get(field) for field in binding_fields):
            add("runtime_binding_mismatch_count", run_id)
        query_results = run.get("query_results")
        if not isinstance(query_results, list) or not query_results:
            return _unknown(["CLUSTER_RUNTIME_QUERY_RESULTS_EMPTY"])
        query_ids: set[str] = set()
        for query in query_results:
            if not isinstance(query, Mapping) or set(query) != _QUERY_FIELDS:
                return _unknown(["CLUSTER_RUNTIME_QUERY_RESULT_SCHEMA_INVALID"])
            query_id = str(query.get("query_id") or "")
            ranked = query.get("ranked_cluster_ids")
            digest = str(query.get("rehydrated_output_sha256") or "")
            retrieval_ms = query.get("retrieval_latency_ms")
            end_to_end_ms = query.get("end_to_end_latency_ms")
            if (
                not query_id
                or query_id in query_ids
                or not isinstance(ranked, list)
                or any(not isinstance(item, str) or not item for item in ranked)
                or len(ranked) != len(set(ranked))
                or not HEX64.fullmatch(digest)
                or not _finite_nonnegative(retrieval_ms)
                or not _finite_nonnegative(end_to_end_ms)
                or float(end_to_end_ms) < float(retrieval_ms)
            ):
                return _unknown(["CLUSTER_RUNTIME_QUERY_RESULT_INVALID"])
            query_ids.add(query_id)
            if len(ranked) > int(policy["runtime_top_k"]):
                add("bounded_k_violation_count", f"{run_id}:{query_id}")
            ranking_observations[query_id].append(tuple(ranked))
            rehydration_observations[query_id].append(digest)
            retrieval_latencies[phase].append(float(retrieval_ms))
            end_to_end_latencies[phase].append(float(end_to_end_ms))
        if expected_query_ids is None:
            expected_query_ids = query_ids
        elif query_ids != expected_query_ids:
            return _unknown(["CLUSTER_RUNTIME_QUERY_SET_DRIFT"])

    for phase, minimum_field in (
        ("COLD", "minimum_cold_runs"),
        ("WARM", "minimum_warm_runs"),
    ):
        if len(runs_by_phase[phase]) < int(policy[minimum_field]):
            add("run_count_shortfall_count", phase)
    for query_id, observations in ranking_observations.items():
        if len(set(observations)) != 1:
            add("ranking_nondeterminism_count", query_id)
    for query_id, observations in rehydration_observations.items():
        if len(set(observations)) != 1:
            add("rehydration_nondeterminism_count", query_id)

    phase_metrics = _empty_phase_metrics()
    for phase in _PHASES:
        retrieval = retrieval_latencies[phase]
        end_to_end = end_to_end_latencies[phase]
        metrics = phase_metrics[phase.lower()]
        metrics["run_count"] = len(runs_by_phase[phase])
        metrics["query_observation_count"] = len(retrieval)
        if retrieval:
            metrics["retrieval_p50_ms"] = median(retrieval)
            metrics["retrieval_p95_ms"] = _nearest_rank_percentile(retrieval, 0.95)
            metrics["end_to_end_p50_ms"] = median(end_to_end)
            metrics["end_to_end_p95_ms"] = _nearest_rank_percentile(
                end_to_end, 0.95
            )
            for metric_name, policy_name in (
                (
                    "retrieval_p95_ms",
                    f"retrieval_{phase.lower()}_p95_ms_maximum",
                ),
                (
                    "end_to_end_p95_ms",
                    f"end_to_end_{phase.lower()}_p95_ms_maximum",
                ),
            ):
                if float(metrics[metric_name]) > float(policy[policy_name]):
                    add(
                        "latency_threshold_violation_count",
                        f"{phase}:{metric_name}",
                    )

    observed_probe_kinds: set[str] = set()
    probe_ids: set[str] = set()
    for probe in probes:
        if not isinstance(probe, Mapping) or set(probe) != _PROBE_FIELDS:
            return _unknown(["CLUSTER_RUNTIME_FAILURE_PROBE_SCHEMA_INVALID"])
        probe_id = str(probe.get("probe_id") or "")
        failure_kind = str(probe.get("failure_kind") or "")
        emitted = probe.get("emitted_cluster_ids")
        if (
            not probe_id
            or probe_id in probe_ids
            or failure_kind not in _FAILURE_KINDS
            or failure_kind in observed_probe_kinds
            or not isinstance(emitted, list)
            or any(not isinstance(item, str) or not item for item in emitted)
        ):
            return _unknown(["CLUSTER_RUNTIME_FAILURE_PROBE_INVALID"])
        probe_ids.add(probe_id)
        observed_probe_kinds.add(failure_kind)
        if (
            probe.get("status") != "FAIL_CLOSED"
            or not str(probe.get("error_code") or "")
            or emitted
        ):
            add("failure_probe_violation_count", failure_kind)
    for failure_kind in policy["required_failure_probes"]:
        if failure_kind not in observed_probe_kinds:
            add("missing_failure_probe_count", failure_kind)

    counts = {name: len(violations[name]) for name in sorted(_COUNTERS)}
    failures = [
        f"CLUSTER_W3_RUNTIME_{name.removesuffix('_count').upper()}"
        for name, count in counts.items()
        if count
    ]
    checks = {
        "bounded_top_k": counts["bounded_k_violation_count"] == 0,
        "ranking_deterministic": counts["ranking_nondeterminism_count"] == 0,
        "rehydration_deterministic": (
            counts["rehydration_nondeterminism_count"] == 0
        ),
        "latency_within_policy": (
            counts["latency_threshold_violation_count"] == 0
        ),
        "invalid_manifest_fails_closed": sum(
            counts[name]
            for name in (
                "missing_failure_probe_count",
                "failure_probe_violation_count",
            )
        )
        == 0,
        "unknown_is_pass": False,
    }
    return seal_record(
        {
            "schema_version": CLUSTER_RUNTIME_RECEIPT_SCHEMA,
            "gate_id": "W3_RUNTIME_QUALITY",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": QUALIFICATION_SCOPE,
            "status": "PASS" if not failures else "FAIL",
            "cluster_count": int(policy["cluster_count"]),
            "runtime_top_k": int(policy["runtime_top_k"]),
            "phase_metrics": phase_metrics,
            "violation_counts": counts,
            "checks": checks,
            "input_digests": {
                "run_set": run_set["record_digest"],
                "runtime_policy": policy["record_digest"],
                "activation_manifest": policy["activation_manifest_sha256"],
                "projection": policy["projection_sha256"],
                "runtime_config": policy["runtime_config_sha256"],
                "hardware_profile": policy["hardware_profile_sha256"],
            },
            "failure_codes": failures,
            "unknown_reasons": [],
            "authority": {
                "measurement_scope": "SOURCE_BOUND_CLUSTER_RUNTIME_QUALITY",
                "release_authorizing": False,
            },
        }
    )


__all__ = [
    "CLUSTER_RUNTIME_POLICY_SCHEMA",
    "CLUSTER_RUNTIME_RECEIPT_SCHEMA",
    "CLUSTER_RUNTIME_RUN_SET_SCHEMA",
    "QUALIFICATION_SCOPE",
    "evaluate_cluster_runtime_quality",
]
