"""Source-bound W3 authority and pipeline evaluation for cluster retrieval."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from apps_rg.evals.resume_graph.reporting import canonical_digest

from .artifacts import HEX64, seal_record, validate_pinned_record
from .cluster_retrieval import LOGICAL_RETRIEVAL_UNIT
from .grounding import RECEIPT_SCHEMA as GROUNDING_RECEIPT_SCHEMA

CLUSTER_GRAPH_SNAPSHOT_SCHEMA = "apps_rg.cluster_authority_graph_snapshot.v1"
CLUSTER_REGISTRY_SCHEMA = "apps_rg.cluster_authority_registry.v1"
CLUSTER_REHYDRATION_TRACE_SCHEMA = "apps_rg.cluster_rehydration_trace.v1"
CLUSTER_ALLOCATION_TRACE_SCHEMA = "apps_rg.cluster_allocation_trace.v1"
CLUSTER_AUTHORITY_POLICY_SCHEMA = "apps_rg.cluster_authority_policy.v1"
CLUSTER_AUTHORITY_RECEIPT_SCHEMA = "apps_rg.cluster_authority_receipt.v1"
QUALIFICATION_SCOPE = "EVAL_W3_NON_RELEASE_AUTHORIZING"

_COUNTERS = frozenset(
    {
        "stale_cluster_count",
        "orphan_cluster_count",
        "missing_member_node_count",
        "missing_member_edge_count",
        "missing_fact_count",
        "missing_metric_count",
        "lifecycle_leak_count",
        "section_policy_leak_count",
        "external_policy_leak_count",
        "authority_bypass_count",
        "duplicate_cluster_output_count",
        "facet_collapse_mismatch_count",
        "unsupported_claim_count",
        "allocation_binding_mismatch_count",
    }
)
_GRAPH_FIELDS = frozenset(
    {"schema_version", "nodes", "edges", "facts", "metrics", "record_digest"}
)
_NODE_FIELDS = frozenset(
    {"node_id", "activation_status", "external_claim_policy"}
)
_EDGE_FIELDS = frozenset(
    {
        "edge_id",
        "source_node_id",
        "target_node_id",
        "activation_status",
        "external_claim_policy",
    }
)
_FACT_FIELDS = frozenset(
    {"fact_id", "activation_status", "external_claim_policy"}
)
_METRIC_FIELDS = frozenset(
    {"metric_id", "activation_status", "external_claim_policy"}
)
_REGISTRY_FIELDS = frozenset(
    {"schema_version", "graph_digest", "clusters", "record_digest"}
)
_CLUSTER_FIELDS = frozenset(
    {
        "cluster_id",
        "cluster_kind",
        "canonical_embedding_text",
        "member_node_ids",
        "member_edge_ids",
        "linked_fact_ids",
        "linked_metric_ids",
        "allowed_sections",
        "activation_status",
        "external_claim_policy",
        "authority_envelope_sha256",
    }
)
_REHYDRATED_FIELDS = _CLUSTER_FIELDS - {"canonical_embedding_text"}
_TRACE_FIELDS = frozenset(
    {
        "schema_version",
        "graph_digest",
        "cluster_registry_digest",
        "activation_manifest_sha256",
        "runtime_config_sha256",
        "runtime_top_k",
        "queries",
        "record_digest",
    }
)
_QUERY_FIELDS = frozenset(
    {"query_id", "section", "raw_hits", "rehydrated_clusters"}
)
_HIT_FIELDS = frozenset({"facet_id", "cluster_id", "rank", "score"})
_ALLOCATION_FIELDS = frozenset(
    {
        "schema_version",
        "graph_digest",
        "cluster_registry_digest",
        "rehydration_trace_digest",
        "grounding_receipt_digest",
        "activation_manifest_sha256",
        "allocations",
        "record_digest",
    }
)
_GROUNDING_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "gate_results",
        "input_digests",
        "claim_records",
        "failure_codes",
        "unknown_reasons",
        "authority",
        "record_digest",
    }
)
_ALLOCATION_ROW_FIELDS = frozenset(
    {"query_id", "section", "selected_cluster_ids", "claims"}
)
_CLAIM_FIELDS = frozenset(
    {
        "claim_id",
        "cluster_id",
        "member_node_ids",
        "fact_ids",
        "metric_ids",
        "graph_path",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "logical_retrieval_unit",
        "retrievable_lifecycle_states",
        "allowed_external_claim_policies",
        "violation_maxima",
        "record_digest",
    }
)
_CLUSTER_KINDS = frozenset({"role_episode", "capability_evidence"})


def seal_cluster_authority_envelope(
    cluster: Mapping[str, Any], *, graph_digest: str
) -> str:
    """Bind cluster membership and policy fields to one graph snapshot."""

    payload = dict(cluster)
    payload.pop("authority_envelope_sha256", None)
    payload["graph_digest"] = graph_digest
    return canonical_digest(payload)


def _valid_text_list(value: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item) for item in value)
        and len(value) == len(set(value))
    )


def _index_rows(
    value: object,
    *,
    key: str,
    fields: frozenset[str],
    label: str,
    reasons: list[str],
    allow_empty: bool = False,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or (not allow_empty and not value):
        reasons.append(f"{label}_ROWS_INVALID")
        return {}
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in value:
        if not isinstance(row, Mapping) or set(row) != fields:
            reasons.append(f"{label}_ROW_SCHEMA_INVALID")
            continue
        identity = str(row.get(key) or "")
        if not identity or identity in indexed:
            reasons.append(f"{label}_IDENTITY_INVALID")
            continue
        indexed[identity] = row
    return indexed


def _validate_policy(
    value: object, *, expected_digest: str
) -> tuple[dict[str, Any], list[str]]:
    reasons = validate_pinned_record(
        value,
        expected_digest=expected_digest,
        schema_version=CLUSTER_AUTHORITY_POLICY_SCHEMA,
    )
    if not isinstance(value, Mapping):
        return {}, reasons
    policy = dict(value)
    if set(policy) != _POLICY_FIELDS:
        reasons.append("CLUSTER_AUTHORITY_POLICY_SCHEMA_INVALID")
    if policy.get("logical_retrieval_unit") != LOGICAL_RETRIEVAL_UNIT:
        reasons.append("CLUSTER_AUTHORITY_POLICY_UNIT_INVALID")
    for field in (
        "retrievable_lifecycle_states",
        "allowed_external_claim_policies",
    ):
        if not _valid_text_list(policy.get(field)):
            reasons.append(f"CLUSTER_AUTHORITY_POLICY_{field.upper()}_INVALID")
    maxima = policy.get("violation_maxima")
    if not isinstance(maxima, Mapping) or set(maxima) != _COUNTERS:
        reasons.append("CLUSTER_AUTHORITY_POLICY_MAXIMA_INVALID")
    elif any(value != 0 for value in maxima.values()):
        reasons.append("CLUSTER_AUTHORITY_POLICY_NOT_ZERO_TOLERANCE")
    return policy, sorted(set(reasons))


def _unknown(reasons: Sequence[str]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_AUTHORITY_RECEIPT_SCHEMA,
            "gate_id": "W3_AUTHORITY_PIPELINE",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": QUALIFICATION_SCOPE,
            "status": "UNKNOWN",
            "query_count": 0,
            "retrieved_cluster_count": 0,
            "claim_count": 0,
            "violation_counts": dict.fromkeys(sorted(_COUNTERS), 0),
            "violation_maxima": dict.fromkeys(sorted(_COUNTERS), 0),
            "checks": {},
            "input_digests": {},
            "failure_codes": [],
            "unknown_reasons": sorted(set(reasons)),
            "authority": {
                "measurement_scope": "SOURCE_BOUND_CLUSTER_AUTHORITY_PIPELINE",
                "release_authorizing": False,
            },
        }
    )


def evaluate_cluster_authority_pipeline(
    *,
    graph_snapshot: Mapping[str, Any],
    expected_graph_digest: str,
    cluster_registry: Mapping[str, Any],
    expected_cluster_registry_digest: str,
    rehydration_trace: Mapping[str, Any],
    expected_rehydration_trace_digest: str,
    allocation_trace: Mapping[str, Any],
    expected_allocation_trace_digest: str,
    grounding_receipt: Mapping[str, Any],
    expected_grounding_receipt_digest: str,
    safety_policy: Mapping[str, Any],
    expected_safety_policy_digest: str,
) -> dict[str, Any]:
    """Compare runtime cluster outputs with current graph and allocation authority."""

    reasons: list[str] = []
    for value, expected, schema in (
        (graph_snapshot, expected_graph_digest, CLUSTER_GRAPH_SNAPSHOT_SCHEMA),
        (
            cluster_registry,
            expected_cluster_registry_digest,
            CLUSTER_REGISTRY_SCHEMA,
        ),
        (
            rehydration_trace,
            expected_rehydration_trace_digest,
            CLUSTER_REHYDRATION_TRACE_SCHEMA,
        ),
        (
            allocation_trace,
            expected_allocation_trace_digest,
            CLUSTER_ALLOCATION_TRACE_SCHEMA,
        ),
        (
            grounding_receipt,
            expected_grounding_receipt_digest,
            GROUNDING_RECEIPT_SCHEMA,
        ),
    ):
        reasons.extend(
            validate_pinned_record(
                value,
                expected_digest=expected,
                schema_version=schema,
            )
        )
    policy, policy_reasons = _validate_policy(
        safety_policy,
        expected_digest=expected_safety_policy_digest,
    )
    reasons.extend(policy_reasons)
    if not all(
        isinstance(value, Mapping)
        for value in (
            graph_snapshot,
            cluster_registry,
            rehydration_trace,
            allocation_trace,
            grounding_receipt,
            safety_policy,
        )
    ):
        return _unknown(reasons + ["CLUSTER_AUTHORITY_INPUT_NOT_OBJECT"])
    if set(graph_snapshot) != _GRAPH_FIELDS:
        reasons.append("CLUSTER_AUTHORITY_GRAPH_SCHEMA_INVALID")
    if set(cluster_registry) != _REGISTRY_FIELDS:
        reasons.append("CLUSTER_AUTHORITY_REGISTRY_SCHEMA_INVALID")
    if set(rehydration_trace) != _TRACE_FIELDS:
        reasons.append("CLUSTER_AUTHORITY_TRACE_SCHEMA_INVALID")
    if set(allocation_trace) != _ALLOCATION_FIELDS:
        reasons.append("CLUSTER_AUTHORITY_ALLOCATION_SCHEMA_INVALID")
    if (
        set(grounding_receipt) != _GROUNDING_RECEIPT_FIELDS
        or not isinstance(grounding_receipt.get("claim_records"), list)
        or not isinstance(grounding_receipt.get("authority"), Mapping)
    ):
        reasons.append("CLUSTER_AUTHORITY_GROUNDING_RECEIPT_SCHEMA_INVALID")

    nodes = _index_rows(
        graph_snapshot.get("nodes"),
        key="node_id",
        fields=_NODE_FIELDS,
        label="CLUSTER_GRAPH_NODE",
        reasons=reasons,
    )
    edges = _index_rows(
        graph_snapshot.get("edges"),
        key="edge_id",
        fields=_EDGE_FIELDS,
        label="CLUSTER_GRAPH_EDGE",
        reasons=reasons,
        allow_empty=True,
    )
    facts = _index_rows(
        graph_snapshot.get("facts"),
        key="fact_id",
        fields=_FACT_FIELDS,
        label="CLUSTER_GRAPH_FACT",
        reasons=reasons,
    )
    metrics = _index_rows(
        graph_snapshot.get("metrics"),
        key="metric_id",
        fields=_METRIC_FIELDS,
        label="CLUSTER_GRAPH_METRIC",
        reasons=reasons,
        allow_empty=True,
    )
    clusters = _index_rows(
        cluster_registry.get("clusters"),
        key="cluster_id",
        fields=_CLUSTER_FIELDS,
        label="CLUSTER_REGISTRY",
        reasons=reasons,
    )
    graph_digest = str(graph_snapshot.get("record_digest") or "")
    registry_digest = str(cluster_registry.get("record_digest") or "")
    trace_digest = str(rehydration_trace.get("record_digest") or "")
    activation_digest = str(rehydration_trace.get("activation_manifest_sha256") or "")
    if not (
        cluster_registry.get("graph_digest") == graph_digest
        and rehydration_trace.get("graph_digest") == graph_digest
        and rehydration_trace.get("cluster_registry_digest") == registry_digest
        and allocation_trace.get("graph_digest") == graph_digest
        and allocation_trace.get("cluster_registry_digest") == registry_digest
        and allocation_trace.get("rehydration_trace_digest") == trace_digest
        and allocation_trace.get("grounding_receipt_digest")
        == grounding_receipt.get("record_digest")
        and allocation_trace.get("activation_manifest_sha256") == activation_digest
    ):
        reasons.append("CLUSTER_AUTHORITY_INPUT_BINDING_MISMATCH")
    for value in (
        graph_digest,
        registry_digest,
        trace_digest,
        activation_digest,
        str(rehydration_trace.get("runtime_config_sha256") or ""),
    ):
        if not HEX64.fullmatch(value):
            reasons.append("CLUSTER_AUTHORITY_DIGEST_INVALID")
    runtime_top_k = rehydration_trace.get("runtime_top_k")
    if (
        not isinstance(runtime_top_k, int)
        or isinstance(runtime_top_k, bool)
        or runtime_top_k < 1
        or runtime_top_k >= len(clusters)
    ):
        reasons.append("CLUSTER_AUTHORITY_TOP_K_NOT_BOUNDED")

    query_rows = _index_rows(
        rehydration_trace.get("queries"),
        key="query_id",
        fields=_QUERY_FIELDS,
        label="CLUSTER_REHYDRATION_QUERY",
        reasons=reasons,
    )
    allocation_rows = _index_rows(
        allocation_trace.get("allocations"),
        key="query_id",
        fields=_ALLOCATION_ROW_FIELDS,
        label="CLUSTER_ALLOCATION_QUERY",
        reasons=reasons,
    )
    if reasons:
        return _unknown(reasons)

    retrievable_states = set(policy["retrievable_lifecycle_states"])
    allowed_policies = set(policy["allowed_external_claim_policies"])
    violations: dict[str, set[str]] = {name: set() for name in _COUNTERS}

    def add(counter: str, identity: str) -> None:
        violations[counter].add(identity)

    for cluster_id, cluster in clusters.items():
        if cluster.get("cluster_kind") not in _CLUSTER_KINDS:
            add("stale_cluster_count", cluster_id)
        if not isinstance(cluster.get("canonical_embedding_text"), str) or not str(
            cluster.get("canonical_embedding_text")
        ).strip():
            add("stale_cluster_count", cluster_id)
        for field, allow_empty in (
            ("member_node_ids", False),
            ("member_edge_ids", True),
            ("linked_fact_ids", True),
            ("linked_metric_ids", True),
            ("allowed_sections", False),
        ):
            if not _valid_text_list(cluster.get(field), allow_empty=allow_empty):
                add("stale_cluster_count", cluster_id)
        expected_envelope = seal_cluster_authority_envelope(
            cluster, graph_digest=graph_digest
        )
        if cluster.get("authority_envelope_sha256") != expected_envelope:
            add("stale_cluster_count", cluster_id)
        references = (
            ("member_node_ids", nodes, "missing_member_node_count"),
            ("member_edge_ids", edges, "missing_member_edge_count"),
            ("linked_fact_ids", facts, "missing_fact_count"),
            ("linked_metric_ids", metrics, "missing_metric_count"),
        )
        if not cluster.get("linked_fact_ids"):
            add("missing_fact_count", f"{cluster_id}:NO_LINKED_FACT")
        if cluster.get("activation_status") not in retrievable_states:
            add("lifecycle_leak_count", f"cluster:{cluster_id}")
        if cluster.get("external_claim_policy") not in allowed_policies:
            add("external_policy_leak_count", f"cluster:{cluster_id}")
        for field, index, counter in references:
            for reference in cluster.get(field) or []:
                identity = str(reference)
                authority_row = index.get(identity)
                if authority_row is None:
                    add(counter, identity)
                    continue
                if authority_row.get("activation_status") not in retrievable_states:
                    add("lifecycle_leak_count", f"{field}:{identity}")
                if authority_row.get("external_claim_policy") not in allowed_policies:
                    add("external_policy_leak_count", f"{field}:{identity}")

    output_by_query: dict[str, list[str]] = {}
    retrieved_total = 0
    for query_id, query in query_rows.items():
        section = str(query.get("section") or "")
        raw_hits = query.get("raw_hits")
        hydrated = query.get("rehydrated_clusters")
        if not isinstance(raw_hits, list) or not isinstance(hydrated, list):
            return _unknown(["CLUSTER_AUTHORITY_QUERY_PAYLOAD_INVALID"])
        raw_ids: list[str] = []
        for index, hit in enumerate(raw_hits, start=1):
            if not isinstance(hit, Mapping) or set(hit) != _HIT_FIELDS:
                return _unknown(["CLUSTER_AUTHORITY_HIT_SCHEMA_INVALID"])
            score = hit.get("score")
            if (
                hit.get("rank") != index
                or not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isfinite(float(score))
            ):
                return _unknown(["CLUSTER_AUTHORITY_HIT_RANK_OR_SCORE_INVALID"])
            cluster_id = str(hit.get("cluster_id") or "")
            if not cluster_id:
                return _unknown(["CLUSTER_AUTHORITY_HIT_IDENTITY_INVALID"])
            raw_ids.append(cluster_id)
            if cluster_id not in clusters:
                add("orphan_cluster_count", f"raw:{query_id}:{cluster_id}")
        expected_collapsed = list(dict.fromkeys(raw_ids))[: int(runtime_top_k)]
        hydrated_ids: list[str] = []
        for index, row in enumerate(hydrated):
            if not isinstance(row, Mapping) or set(row) != _REHYDRATED_FIELDS:
                return _unknown(["CLUSTER_AUTHORITY_REHYDRATED_SCHEMA_INVALID"])
            cluster_id = str(row.get("cluster_id") or "")
            hydrated_ids.append(cluster_id)
            registry_row = clusters.get(cluster_id)
            if registry_row is None:
                add("orphan_cluster_count", f"hydrated:{query_id}:{cluster_id}")
                continue
            expected_row = {
                key: registry_row[key] for key in sorted(_REHYDRATED_FIELDS)
            }
            if dict(row) != expected_row:
                add("stale_cluster_count", f"hydrated:{query_id}:{cluster_id}")
            if section not in registry_row.get("allowed_sections", []):
                add("section_policy_leak_count", f"{query_id}:{cluster_id}")
            if registry_row.get("activation_status") not in retrievable_states:
                add("lifecycle_leak_count", f"output:{query_id}:{cluster_id}")
            if registry_row.get("external_claim_policy") not in allowed_policies:
                add("external_policy_leak_count", f"output:{query_id}:{cluster_id}")
            if cluster_id not in raw_ids:
                add("authority_bypass_count", f"{query_id}:{cluster_id}:{index}")
        duplicate_ids = {
            cluster_id for cluster_id in hydrated_ids if hydrated_ids.count(cluster_id) > 1
        }
        for cluster_id in duplicate_ids:
            add("duplicate_cluster_output_count", f"{query_id}:{cluster_id}")
        if hydrated_ids != expected_collapsed:
            add("facet_collapse_mismatch_count", query_id)
        if len(hydrated_ids) > int(runtime_top_k):
            add("authority_bypass_count", f"{query_id}:TOP_K_EXCEEDED")
        output_by_query[query_id] = hydrated_ids
        retrieved_total += len(hydrated_ids)

    if set(allocation_rows) != set(query_rows):
        add("allocation_binding_mismatch_count", "QUERY_SET")
    grounding_authority = grounding_receipt.get("authority")
    if not (
        grounding_receipt.get("status") == "PASS"
        and isinstance(grounding_authority, Mapping)
        and grounding_authority.get("human_authority_verified") is True
        and grounding_authority.get("release_authorizing") is False
    ):
        add("allocation_binding_mismatch_count", "GROUNDING_RECEIPT_NOT_PASSING")
    grounding_claims: dict[str, Mapping[str, Any]] = {}
    for record in grounding_receipt.get("claim_records") or []:
        if not isinstance(record, Mapping):
            add("allocation_binding_mismatch_count", "GROUNDING_RECORD_SCHEMA")
            continue
        claim_id = str(record.get("claim_id") or "")
        if (
            not claim_id
            or claim_id in grounding_claims
            or record.get("support_disposition") != "SUPPORTED"
            or record.get("path_binding") != "EXACT"
            or not _valid_text_list(record.get("graph_path"))
        ):
            add(
                "allocation_binding_mismatch_count",
                f"GROUNDING_RECORD:{claim_id or 'MISSING'}",
            )
        grounding_claims[claim_id] = record
    claim_count = 0
    graph_path_authority = set(nodes) | set(edges)
    for query_id, allocation in allocation_rows.items():
        selected = allocation.get("selected_cluster_ids")
        claims = allocation.get("claims")
        if not _valid_text_list(selected, allow_empty=True) or not isinstance(claims, list):
            return _unknown(["CLUSTER_AUTHORITY_ALLOCATION_PAYLOAD_INVALID"])
        if allocation.get("section") != query_rows.get(query_id, {}).get("section"):
            add("allocation_binding_mismatch_count", f"{query_id}:SECTION")
        output_ids = output_by_query.get(query_id, [])
        for cluster_id in selected:
            if cluster_id not in output_ids:
                add("allocation_binding_mismatch_count", f"{query_id}:{cluster_id}")
        seen_claims: set[str] = set()
        for claim in claims:
            claim_count += 1
            if not isinstance(claim, Mapping) or set(claim) != _CLAIM_FIELDS:
                return _unknown(["CLUSTER_AUTHORITY_CLAIM_SCHEMA_INVALID"])
            claim_id = str(claim.get("claim_id") or "")
            if not claim_id or claim_id in seen_claims:
                return _unknown(["CLUSTER_AUTHORITY_CLAIM_IDENTITY_INVALID"])
            seen_claims.add(claim_id)
            grounding_record = grounding_claims.get(claim_id)
            if grounding_record is None:
                add(
                    "allocation_binding_mismatch_count",
                    f"GROUNDING_CLAIM:{claim_id}",
                )
            cluster_id = str(claim.get("cluster_id") or "")
            cluster = clusters.get(cluster_id)
            if cluster_id not in selected or cluster is None:
                add("authority_bypass_count", f"claim:{query_id}:{claim_id}")
                continue
            claim_nodes = claim.get("member_node_ids")
            claim_facts = claim.get("fact_ids")
            claim_metrics = claim.get("metric_ids")
            graph_path = claim.get("graph_path")
            if not all(
                (
                    _valid_text_list(claim_nodes),
                    _valid_text_list(claim_facts),
                    _valid_text_list(claim_metrics, allow_empty=True),
                    _valid_text_list(graph_path),
                )
            ):
                add("unsupported_claim_count", f"{query_id}:{claim_id}:SHAPE")
                continue
            if not set(claim_nodes).issubset(cluster["member_node_ids"]):
                add("unsupported_claim_count", f"{query_id}:{claim_id}:NODE")
            if grounding_record is not None and not set(claim_nodes).issubset(
                grounding_record.get("graph_path") or []
            ):
                add(
                    "allocation_binding_mismatch_count",
                    f"GROUNDING_PATH:{claim_id}",
                )
            if not set(claim_facts).issubset(cluster["linked_fact_ids"]):
                add("unsupported_claim_count", f"{query_id}:{claim_id}:FACT")
            if not set(claim_metrics).issubset(cluster["linked_metric_ids"]):
                add("unsupported_claim_count", f"{query_id}:{claim_id}:METRIC")
            if not set(graph_path).issubset(graph_path_authority):
                add("unsupported_claim_count", f"{query_id}:{claim_id}:PATH")

    counts = {name: len(violations[name]) for name in sorted(_COUNTERS)}
    maxima = {name: int(policy["violation_maxima"][name]) for name in sorted(_COUNTERS)}
    failures = [
        f"CLUSTER_W3_{name.removesuffix('_count').upper()}"
        for name, count in counts.items()
        if count > maxima[name]
    ]
    checks = {
        "exact_rehydration": counts["stale_cluster_count"] == 0,
        "no_orphan_or_missing_authority": sum(
            counts[name]
            for name in (
                "orphan_cluster_count",
                "missing_member_node_count",
                "missing_member_edge_count",
                "missing_fact_count",
                "missing_metric_count",
            )
        )
        == 0,
        "lifecycle_and_policy_safe": sum(
            counts[name]
            for name in (
                "lifecycle_leak_count",
                "section_policy_leak_count",
                "external_policy_leak_count",
            )
        )
        == 0,
        "facets_collapsed_to_unique_clusters": sum(
            counts[name]
            for name in (
                "duplicate_cluster_output_count",
                "facet_collapse_mismatch_count",
            )
        )
        == 0,
        "claims_graph_and_fact_backed": counts["unsupported_claim_count"] == 0,
        "unknown_is_pass": False,
    }
    return seal_record(
        {
            "schema_version": CLUSTER_AUTHORITY_RECEIPT_SCHEMA,
            "gate_id": "W3_AUTHORITY_PIPELINE",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "qualification_scope": QUALIFICATION_SCOPE,
            "status": "PASS" if not failures else "FAIL",
            "query_count": len(query_rows),
            "retrieved_cluster_count": retrieved_total,
            "claim_count": claim_count,
            "violation_counts": counts,
            "violation_maxima": maxima,
            "checks": checks,
            "input_digests": {
                "graph_snapshot": graph_digest,
                "cluster_registry": registry_digest,
                "rehydration_trace": trace_digest,
                "allocation_trace": allocation_trace["record_digest"],
                "grounding_receipt": grounding_receipt["record_digest"],
                "safety_policy": policy["record_digest"],
                "activation_manifest": activation_digest,
            },
            "failure_codes": failures,
            "unknown_reasons": [],
            "authority": {
                "measurement_scope": "SOURCE_BOUND_CLUSTER_AUTHORITY_PIPELINE",
                "release_authorizing": False,
            },
        }
    )


__all__ = [
    "CLUSTER_ALLOCATION_TRACE_SCHEMA",
    "CLUSTER_AUTHORITY_POLICY_SCHEMA",
    "CLUSTER_AUTHORITY_RECEIPT_SCHEMA",
    "CLUSTER_GRAPH_SNAPSHOT_SCHEMA",
    "CLUSTER_REGISTRY_SCHEMA",
    "CLUSTER_REHYDRATION_TRACE_SCHEMA",
    "QUALIFICATION_SCOPE",
    "evaluate_cluster_authority_pipeline",
    "seal_cluster_authority_envelope",
]
