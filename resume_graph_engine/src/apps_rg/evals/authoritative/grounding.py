"""G2/G3 measurement over source bytes, graph paths, system claims, and human truth."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from apps_rg.evals.resume_graph.metrics.binding import BINDING_FIELDS
from apps_rg.evals.resume_graph.metrics.grounding import (
    evaluate_binding_gate,
    evaluate_grounding_gate,
    seal_claim_evidence_record,
)

from .artifacts import (
    load_human_authority_receipt,
    seal_record,
    validate_authorized_reviewer,
    validate_label_review_coverage,
    validate_pinned_record,
)

SOURCE_SCHEMA = "apps_rg.authoritative_source_bundle.v1"
GRAPH_SCHEMA = "apps_rg.authoritative_graph_snapshot.v1"
SYSTEM_SCHEMA = "apps_rg.authoritative_system_claims.v1"
TRUTH_SCHEMA = "apps_rg.authoritative_claim_truth.v1"
RECEIPT_SCHEMA = "apps_rg.authoritative_grounding_receipt.v1"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _index(rows: Any, key: str, label: str, reasons: list[str]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(rows, list) or not rows:
        reasons.append(f"{label}_EMPTY")
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            reasons.append(f"{label}_ROW_INVALID")
            continue
        identity = str(row.get(key) or "")
        if not identity or identity in result:
            reasons.append(f"{label}_IDENTITY_INVALID")
            continue
        result[identity] = row
    return result


def _unknown(reasons: Sequence[str], input_digests: Mapping[str, str]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": RECEIPT_SCHEMA,
            "status": "UNKNOWN",
            "gate_results": {
                "G2": {"status": "UNKNOWN", "metrics": {}, "failure_codes": []},
                "G3": {"status": "UNKNOWN", "metrics": {}, "failure_codes": []},
            },
            "input_digests": dict(input_digests),
            "claim_records": [],
            "failure_codes": [],
            "unknown_reasons": sorted(set(reasons)),
            "authority": {
                "measurement_scope": "SOURCE_AND_GRAPH_VERIFIED_SYSTEM_VS_HUMAN_TRUTH",
                "human_authority_verified": False,
                "release_authorizing": False,
            },
        }
    )


def evaluate_authoritative_grounding(
    *,
    source_bundle: Any,
    expected_source_digest: str,
    graph_snapshot: Any,
    expected_graph_digest: str,
    system_claims: Any,
    expected_system_digest: str,
    truth_bundle: Any,
    expected_truth_digest: str,
    authority_receipt_path: Any,
    expected_authority_file_sha256: str,
) -> dict[str, Any]:
    """Reconstruct claim-evidence records from independent source and truth artifacts."""

    reasons: list[str] = []
    for value, expected, schema in (
        (source_bundle, expected_source_digest, SOURCE_SCHEMA),
        (graph_snapshot, expected_graph_digest, GRAPH_SCHEMA),
        (system_claims, expected_system_digest, SYSTEM_SCHEMA),
        (truth_bundle, expected_truth_digest, TRUTH_SCHEMA),
    ):
        reasons.extend(
            validate_pinned_record(value, expected_digest=expected, schema_version=schema)
        )
    input_digests = {
        "source_bundle": expected_source_digest,
        "graph_snapshot": expected_graph_digest,
        "system_claims": expected_system_digest,
        "truth_bundle": expected_truth_digest,
    }
    authority, roster, authority_reasons = load_human_authority_receipt(
        authority_receipt_path,
        expected_file_sha256=expected_authority_file_sha256,
    )
    reasons.extend(authority_reasons)
    if not all(
        isinstance(value, Mapping)
        for value in (source_bundle, graph_snapshot, system_claims, truth_bundle)
    ):
        return _unknown(reasons, input_digests)
    if truth_bundle.get("authority_receipt_file_sha256") != expected_authority_file_sha256:
        reasons.append("CLAIM_TRUTH_AUTHORITY_BINDING_MISMATCH")
    reviewers = truth_bundle.get("reviewer_identity_refs")
    if (
        not isinstance(reviewers, list)
        or any(not isinstance(reviewer, str) or not reviewer for reviewer in reviewers)
        or len(set(reviewers)) < 2
    ):
        reasons.append("CLAIM_TRUTH_TWO_REVIEWERS_REQUIRED")
        reviewers = []
    for reviewer in reviewers:
        reasons.extend(
            validate_authorized_reviewer(
                identity_ref=str(reviewer),
                qualification_ref=None,
                cohort="proof",
                role="primary",
                roster=roster,
            )
        )
    adjudicator = str(truth_bundle.get("adjudicator_identity_ref") or "")
    reasons.extend(
        validate_authorized_reviewer(
            identity_ref=adjudicator,
            qualification_ref=None,
            cohort="proof",
            role="adjudicator",
            roster=roster,
        )
    )

    sources = _index(source_bundle.get("sources"), "source_id", "SOURCE", reasons)
    paths = _index(graph_snapshot.get("paths"), "path_id", "GRAPH_PATH", reasons)
    claims = _index(system_claims.get("claims"), "claim_id", "SYSTEM_CLAIM", reasons)
    truths = _index(truth_bundle.get("labels"), "claim_id", "CLAIM_TRUTH", reasons)
    for truth in truths.values():
        reasons.extend(
            validate_label_review_coverage(
                truth,
                reviewer_identity_refs=[str(reviewer) for reviewer in reviewers],
                adjudicator_identity_ref=adjudicator,
            )
        )
    if set(claims) != set(truths):
        reasons.append("MATERIAL_CLAIM_DENOMINATOR_MISMATCH")

    records: list[dict[str, Any]] = []
    for claim_id in sorted(set(claims) & set(truths)):
        claim = claims[claim_id]
        truth = truths[claim_id]
        claim_text = str(claim.get("claim_text") or "")
        if truth.get("claim_text_digest") != _sha256_text(claim_text):
            reasons.append(f"claim[{claim_id}]::CLAIM_TEXT_TRUTH_BINDING_MISMATCH")
        source_id = str(claim.get("source_id") or "")
        source = sources.get(source_id)
        locator = claim.get("locator")
        excerpt = ""
        if not isinstance(source, Mapping):
            reasons.append(f"claim[{claim_id}]::SOURCE_NOT_FOUND")
        elif source.get("content_sha256") != _sha256_text(str(source.get("text") or "")):
            reasons.append(f"claim[{claim_id}]::SOURCE_CONTENT_DIGEST_INVALID")
        if not isinstance(locator, Mapping):
            reasons.append(f"claim[{claim_id}]::SOURCE_LOCATOR_INVALID")
            start = end = 0
        else:
            start, end = locator.get("start"), locator.get("end")
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start < 0
                or end < start
                or not isinstance(source, Mapping)
                or end > len(str(source.get("text") or ""))
            ):
                reasons.append(f"claim[{claim_id}]::SOURCE_LOCATOR_INVALID")
                start = end = 0
            elif isinstance(source, Mapping):
                excerpt = str(source.get("text") or "")[start:end]
        excerpt_digest = _sha256_text(excerpt)
        if truth.get("source_excerpt_digest") != excerpt_digest:
            reasons.append(f"claim[{claim_id}]::SOURCE_EXCERPT_TRUTH_MISMATCH")

        path_id = str(claim.get("graph_path_id") or "")
        graph = paths.get(path_id)
        expected_nodes = truth.get("expected_graph_path")
        observed_nodes = graph.get("nodes") if isinstance(graph, Mapping) else None
        path_exact = (
            isinstance(graph, Mapping)
            and graph.get("source_id") == source_id
            and observed_nodes == expected_nodes
        )
        if not isinstance(graph, Mapping):
            reasons.append(f"claim[{claim_id}]::GRAPH_PATH_NOT_FOUND")

        expected_bindings = truth.get("expected_bindings")
        observed_bindings = claim.get("predicted_bindings")
        raw_inflation_fields = truth.get("inflation_fields")
        if not isinstance(raw_inflation_fields, list) or any(
            not isinstance(field, str) for field in raw_inflation_fields
        ):
            reasons.append(f"claim[{claim_id}]::TRUTH_INFLATION_FIELDS_INVALID")
            raw_inflation_fields = []
        inflation_fields = set(raw_inflation_fields)
        if not isinstance(expected_bindings, Mapping) or set(expected_bindings) != set(BINDING_FIELDS):
            reasons.append(f"claim[{claim_id}]::TRUTH_BINDINGS_INCOMPLETE")
            expected_bindings = {}
        if not isinstance(observed_bindings, Mapping) or set(observed_bindings) != set(BINDING_FIELDS):
            reasons.append(f"claim[{claim_id}]::SYSTEM_BINDINGS_INCOMPLETE")
            observed_bindings = {}
        bindings: dict[str, dict[str, Any]] = {}
        for field in BINDING_FIELDS:
            expected = expected_bindings.get(field)
            observed = observed_bindings.get(field)
            status = (
                "NOT_APPLICABLE"
                if expected is None and observed is None
                else "EXACT"
                if expected == observed
                else "MISMATCH"
            )
            bindings[field] = {
                "status": status,
                "expected": expected,
                "observed": observed,
                "inflation": field in inflation_fields,
            }
        record = seal_claim_evidence_record(
            {
                "schema_version": "apps_rg.claim_evidence_record.v1",
                "claim_id": claim_id,
                "claim_text": claim_text,
                "materiality": truth.get("materiality"),
                "source_id": source_id,
                "exact_evidence_locator": {
                    "artifact_ref": f"artifact://source/{source_id}",
                    "start": start,
                    "end": end,
                },
                "locator_failure_reason": None,
                "source_excerpt_digest": excerpt_digest,
                "graph_path": observed_nodes or [],
                "path_binding": "EXACT" if path_exact else "MISMATCH",
                "bindings": bindings,
                "entailment_grade": truth.get("entailment_grade"),
                "support_disposition": claim.get("predicted_support_disposition"),
                "components": truth.get("components", []),
                "record_digest": "",
            }
        )
        records.append(record)
    if reasons:
        return _unknown(reasons, input_digests)
    binding = evaluate_binding_gate(records)
    grounding = evaluate_grounding_gate(records)
    statuses = {binding["status"], grounding["status"]}
    status = "UNKNOWN" if "UNKNOWN" in statuses else "FAIL" if "FAIL" in statuses else "PASS"
    return seal_record(
        {
            "schema_version": RECEIPT_SCHEMA,
            "status": status,
            "gate_results": {"G2": binding, "G3": grounding},
            "input_digests": input_digests,
            "claim_records": records,
            "failure_codes": sorted(set(binding["failure_codes"] + grounding["failure_codes"])),
            "unknown_reasons": sorted(
                set(binding["unknown_reasons"] + grounding["unknown_reasons"])
            ),
            "authority": {
                "measurement_scope": "SOURCE_AND_GRAPH_VERIFIED_SYSTEM_VS_HUMAN_TRUTH",
                "authority_receipt_digest": authority.get("receipt_digest"),
                "authority_receipt_file_sha256": expected_authority_file_sha256,
                "human_authority_verified": True,
                "release_authorizing": False,
            },
        }
    )


__all__ = [
    "GRAPH_SCHEMA",
    "RECEIPT_SCHEMA",
    "SOURCE_SCHEMA",
    "SYSTEM_SCHEMA",
    "TRUTH_SCHEMA",
    "evaluate_authoritative_grounding",
]
