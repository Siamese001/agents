"""Blinded human-review contracts for graph-evidence cluster QRELs."""

from __future__ import annotations

import hashlib
import hmac
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from apps_rg.evals.resume_graph.reporting import canonical_digest

from .artifacts import (
    HEX64,
    load_human_authority_receipt,
    record_digest_matches,
    seal_record,
    validate_authorized_reviewer,
    validate_pinned_record,
)
from .cluster_retrieval import CLUSTER_UNIVERSE_SCHEMA, LOGICAL_RETRIEVAL_UNIT

CLUSTER_REVIEW_SOURCE_SCHEMA = "apps_rg.cluster_qrel_review_source.v1"
CLUSTER_SPLIT_POLICY_SCHEMA = "apps_rg.cluster_qrel_split_policy.v1"
CLUSTER_RUBRIC_SCHEMA = "apps_rg.cluster_qrel_rubric.v1"
CLUSTER_REVIEWER_PACKET_SCHEMA = "apps_rg.cluster_qrel_reviewer_packet.v1"
CLUSTER_BLINDING_MANIFEST_SCHEMA = "apps_rg.cluster_qrel_blinding_manifest.v1"
CLUSTER_PRELABEL_RECEIPT_SCHEMA = "apps_rg.cluster_qrel_prelabel_receipt.v1"
CLUSTER_PRELABEL_VALIDATION_RECEIPT_SCHEMA = (
    "apps_rg.cluster_qrel_prelabel_validation_receipt.v1"
)
CLUSTER_REVIEW_BUNDLE_SCHEMA = "apps_rg.cluster_qrel_review_bundle.v1"
CLUSTER_ADJUDICATION_BUNDLE_SCHEMA = "apps_rg.cluster_qrel_adjudication_bundle.v1"
CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA = (
    "apps_rg.cluster_qrel_completed_review_receipt.v1"
)

_SPLITS = ("CALIBRATION", "HOLDOUT")
_CLUSTER_KINDS = ("role_episode", "capability_evidence")
REQUIRED_CLUSTER_COVERAGE_TAGS = frozenset(
    {
        "ROLE_EPISODE",
        "CAPABILITY_EVIDENCE",
        "AMBIGUOUS_CAPABILITY",
        "SHARED_EVIDENCE_ANCHOR",
        "FACTLESS_OR_HELD",
        "POLICY_RESTRICTED",
        "SINGLETON_EXCEPTION",
        "CROSS_EMPLOYER_NEAR_NEIGHBOR",
    }
)
_RELEVANCE_GRADES = (0, 1, 2, 3)
_EVIDENCE_SUFFICIENCY = ("SUFFICIENT", "PARTIAL", "INSUFFICIENT")
_SECTION_FITNESS = ("FIT", "CONDITIONAL", "NOT_FIT")
_AMBIGUITY = ("UNAMBIGUOUS", "AMBIGUOUS", "CONFLICTING")
_REJECTION_REASONS = (
    "NONE",
    "IRRELEVANT",
    "INSUFFICIENT_EVIDENCE",
    "SECTION_MISMATCH",
    "POLICY_RESTRICTED",
    "LIFECYCLE_INELIGIBLE",
    "WRONG_EMPLOYER",
    "WRONG_ROLE",
    "DUPLICATE",
)
_RUBRIC_RULES = (
    "relevance_grade_gte_2_requires_nonrejected_sufficient_or_partial_evidence",
    "relevance_grade_0_requires_rejection_reason",
    "insufficient_evidence_caps_relevance_at_1",
    "not_fit_caps_relevance_at_1",
    "conflicting_ambiguity_caps_relevance_at_1",
)
_LABEL_FIELDS = frozenset(
    {
        "relevance_grade",
        "evidence_sufficiency",
        "section_fitness",
        "ambiguity",
        "rejection_reason",
    }
)
_REVIEWER_FORBIDDEN_KEYS = frozenset(
    {
        "query_id",
        "cluster_id",
        "split",
        "rank",
        "score",
        "similarity",
        "evidence_anchor_ids",
        "authority_bindings",
        "universe_digest",
        "review_source_digest",
        "activation_status",
        "allowed_sections",
        "member_node_ids",
        "linked_fact_ids",
    }
)


class ClusterQrelReviewError(RuntimeError):
    """Raised when a prelabel cluster-review packet cannot be frozen safely."""


def _valid_text_list(value: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item) for item in value)
        and len(value) == len(set(value))
    )


def _blind_id(
    *,
    nonce: str,
    purpose: str,
    payload: Mapping[str, Any],
    prefix: str,
) -> str:
    digest = hmac.new(
        nonce.encode("utf-8"),
        f"{purpose}:{canonical_digest(payload)}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{prefix}-{digest[:24]}"


def _unsafe_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        found = set(value) & _REVIEWER_FORBIDDEN_KEYS
        for child in value.values():
            found.update(_unsafe_keys(child))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for child in value:
            found.update(_unsafe_keys(child))
        return found
    return set()


def _validate_rubric(
    value: object,
    *,
    expected_digest: str,
) -> tuple[dict[str, Any], list[str]]:
    reasons = validate_pinned_record(
        value,
        expected_digest=expected_digest,
        schema_version=CLUSTER_RUBRIC_SCHEMA,
    )
    if not isinstance(value, Mapping):
        return {}, sorted(set(reasons))
    rubric = dict(value)
    if set(rubric) != {
        "schema_version",
        "rubric_id",
        "reviewer_policy",
        "dimensions",
        "consistency_rules",
        "record_digest",
    }:
        reasons.append("CLUSTER_RUBRIC_SCHEMA_INVALID")
    if not str(rubric.get("rubric_id") or ""):
        reasons.append("CLUSTER_RUBRIC_ID_INVALID")
    if rubric.get("reviewer_policy") != {
        "independent_primary_reviewers": 2,
        "human_only": True,
        "unknown_is_pass": False,
        "rank_visible": False,
        "score_visible": False,
        "split_visible": False,
        "authority_ids_visible": False,
    }:
        reasons.append("CLUSTER_RUBRIC_REVIEWER_POLICY_INVALID")
    if rubric.get("dimensions") != {
        "relevance_grade": list(_RELEVANCE_GRADES),
        "evidence_sufficiency": list(_EVIDENCE_SUFFICIENCY),
        "section_fitness": list(_SECTION_FITNESS),
        "ambiguity": list(_AMBIGUITY),
        "rejection_reason": list(_REJECTION_REASONS),
    }:
        reasons.append("CLUSTER_RUBRIC_DIMENSIONS_INVALID")
    if rubric.get("consistency_rules") != list(_RUBRIC_RULES):
        reasons.append("CLUSTER_RUBRIC_CONSISTENCY_RULES_INVALID")
    return rubric, sorted(set(reasons))


def _validate_split_policy(
    value: object,
    *,
    expected_digest: str,
) -> tuple[dict[str, Any], list[str]]:
    reasons = validate_pinned_record(
        value,
        expected_digest=expected_digest,
        schema_version=CLUSTER_SPLIT_POLICY_SCHEMA,
    )
    if not isinstance(value, Mapping):
        return {}, sorted(set(reasons))
    policy = dict(value)
    if set(policy) != {
        "schema_version",
        "policy_id",
        "splits",
        "required_target_profiles",
        "required_sections",
        "required_employers",
        "required_cluster_kinds",
        "required_coverage_tags",
        "record_digest",
    }:
        reasons.append("CLUSTER_SPLIT_POLICY_SCHEMA_INVALID")
    if not str(policy.get("policy_id") or ""):
        reasons.append("CLUSTER_SPLIT_POLICY_ID_INVALID")
    if policy.get("splits") != list(_SPLITS):
        reasons.append("CLUSTER_SPLIT_SET_INVALID")
    for field in (
        "required_target_profiles",
        "required_sections",
        "required_employers",
    ):
        if not _valid_text_list(policy.get(field)):
            reasons.append(f"CLUSTER_SPLIT_{field.upper()}_INVALID")
    if policy.get("required_cluster_kinds") != list(_CLUSTER_KINDS):
        reasons.append("CLUSTER_SPLIT_CLUSTER_KINDS_INVALID")
    if set(policy.get("required_coverage_tags") or []) != (
        REQUIRED_CLUSTER_COVERAGE_TAGS
    ):
        reasons.append("CLUSTER_SPLIT_COVERAGE_TAGS_INCOMPLETE")
    return policy, sorted(set(reasons))


def _validate_review_source(
    value: object,
    *,
    expected_digest: str,
    universe: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    reasons = validate_pinned_record(
        value,
        expected_digest=expected_digest,
        schema_version=CLUSTER_REVIEW_SOURCE_SCHEMA,
    )
    if not isinstance(value, Mapping):
        return {}, sorted(set(reasons))
    if set(value) != {
        "schema_version",
        "query_id",
        "universe_digest",
        "clusters",
        "record_digest",
    }:
        reasons.append("CLUSTER_REVIEW_SOURCE_SCHEMA_INVALID")
    if not (
        value.get("query_id") == universe.get("query_id")
        and value.get("universe_digest") == universe.get("record_digest")
    ):
        reasons.append("CLUSTER_REVIEW_SOURCE_BINDING_MISMATCH")
    raw_rows = value.get("clusters")
    if not isinstance(raw_rows, list) or not raw_rows:
        return {}, sorted(set(reasons + ["CLUSTER_REVIEW_SOURCE_EMPTY"]))
    rows: dict[str, Mapping[str, Any]] = {}
    expected_fields = {
        "cluster_id",
        "cluster_kind",
        "cluster_authority_envelope_sha256",
        "claim_summary",
        "operating_context",
        "capability_summaries",
        "approved_evidence_summaries",
        "evidence_anchor_ids",
        "coverage_tags",
    }
    for row in raw_rows:
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            reasons.append("CLUSTER_REVIEW_SOURCE_ROW_SCHEMA_INVALID")
            continue
        cluster_id = str(row.get("cluster_id") or "")
        if not cluster_id or cluster_id in rows:
            reasons.append("CLUSTER_REVIEW_SOURCE_IDENTITY_INVALID")
            continue
        rows[cluster_id] = row
        if row.get("cluster_kind") not in _CLUSTER_KINDS:
            reasons.append("CLUSTER_REVIEW_SOURCE_KIND_INVALID")
        if not HEX64.fullmatch(
            str(row.get("cluster_authority_envelope_sha256") or "")
        ):
            reasons.append("CLUSTER_REVIEW_SOURCE_AUTHORITY_INVALID")
        if not all(
            isinstance(row.get(field), str) and row[field]
            for field in ("claim_summary", "operating_context")
        ):
            reasons.append("CLUSTER_REVIEW_SOURCE_TEXT_INVALID")
        for field in (
            "capability_summaries",
            "approved_evidence_summaries",
            "evidence_anchor_ids",
            "coverage_tags",
        ):
            if not _valid_text_list(row.get(field)):
                reasons.append(f"CLUSTER_REVIEW_SOURCE_{field.upper()}_INVALID")
        if not set(row.get("coverage_tags") or []).issubset(
            REQUIRED_CLUSTER_COVERAGE_TAGS
        ):
            reasons.append("CLUSTER_REVIEW_SOURCE_COVERAGE_TAG_UNKNOWN")
        expected_kind_tag = str(row.get("cluster_kind") or "").upper()
        if expected_kind_tag not in set(row.get("coverage_tags") or []):
            reasons.append("CLUSTER_REVIEW_SOURCE_KIND_TAG_MISSING")
    universe_rows = {
        str(row.get("cluster_id") or ""): row
        for row in universe.get("clusters") or []
        if isinstance(row, Mapping)
    }
    if set(rows) != set(universe_rows):
        reasons.append("CLUSTER_REVIEW_SOURCE_UNIVERSE_MISMATCH")
    for cluster_id, row in rows.items():
        universe_row = universe_rows.get(cluster_id) or {}
        if (
            row.get("cluster_kind") != universe_row.get("cluster_kind")
            or row.get("cluster_authority_envelope_sha256")
            != universe_row.get("cluster_authority_envelope_sha256")
        ):
            reasons.append("CLUSTER_REVIEW_SOURCE_CLUSTER_BINDING_MISMATCH")
    return rows, sorted(set(reasons))


def _validate_source_case(
    case: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    if set(case) != {
        "universe",
        "expected_universe_digest",
        "split",
        "review_source",
        "expected_review_source_digest",
    }:
        reasons.append("CLUSTER_REVIEW_CASE_SCHEMA_INVALID")
    universe = case.get("universe")
    reasons.extend(
        validate_pinned_record(
            universe,
            expected_digest=str(case.get("expected_universe_digest") or ""),
            schema_version=CLUSTER_UNIVERSE_SCHEMA,
        )
    )
    if not isinstance(universe, Mapping):
        return None, sorted(set(reasons))
    if universe.get("logical_retrieval_unit") != LOGICAL_RETRIEVAL_UNIT:
        reasons.append("CLUSTER_REVIEW_LOGICAL_UNIT_INVALID")
    split = case.get("split")
    if split not in _SPLITS:
        reasons.append("CLUSTER_REVIEW_SPLIT_INVALID")
    rows, source_reasons = _validate_review_source(
        case.get("review_source"),
        expected_digest=str(case.get("expected_review_source_digest") or ""),
        universe=universe,
    )
    reasons.extend(source_reasons)
    if reasons:
        return None, sorted(set(reasons))
    return {
        "universe": universe,
        "split": split,
        "review_source": case["review_source"],
        "review_rows": rows,
    }, []


def _validate_coverage(
    cases: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    query_ids: set[str] = set()
    cluster_ids_by_split: dict[str, set[str]] = defaultdict(set)
    anchors_by_split: dict[str, set[str]] = defaultdict(set)
    profiles_by_split: dict[str, set[str]] = defaultdict(set)
    sections_by_split: dict[str, set[str]] = defaultdict(set)
    employers_by_split: dict[str, set[str]] = defaultdict(set)
    kinds_by_split: dict[str, set[str]] = defaultdict(set)
    tags: set[str] = set()
    for case in cases:
        universe = case["universe"]
        split = str(case["split"])
        query_id = str(universe["query_id"])
        if query_id in query_ids:
            reasons.append("CLUSTER_REVIEW_QUERY_ID_DUPLICATE")
        query_ids.add(query_id)
        profiles_by_split[split].add(str(universe["target_profile"]))
        sections_by_split[split].add(str(universe["section"]))
        employers_by_split[split].add(str(universe["employer"]))
        for cluster_id, row in case["review_rows"].items():
            cluster_ids_by_split[split].add(cluster_id)
            kinds_by_split[split].add(str(row["cluster_kind"]))
            anchors_by_split[split].update(str(value) for value in row["evidence_anchor_ids"])
            tags.update(str(value) for value in row["coverage_tags"])
    if cluster_ids_by_split["CALIBRATION"] & cluster_ids_by_split["HOLDOUT"]:
        reasons.append("CLUSTER_REVIEW_CLUSTER_SPLIT_LEAKAGE")
    if anchors_by_split["CALIBRATION"] & anchors_by_split["HOLDOUT"]:
        reasons.append("CLUSTER_REVIEW_EVIDENCE_ANCHOR_SPLIT_LEAKAGE")
    requirements = {
        "target_profiles": set(policy.get("required_target_profiles") or []),
        "sections": set(policy.get("required_sections") or []),
        "employers": set(policy.get("required_employers") or []),
        "cluster_kinds": set(policy.get("required_cluster_kinds") or []),
    }
    observed = {
        "target_profiles": profiles_by_split,
        "sections": sections_by_split,
        "employers": employers_by_split,
        "cluster_kinds": kinds_by_split,
    }
    for split in _SPLITS:
        if not cluster_ids_by_split[split]:
            reasons.append(f"CLUSTER_REVIEW_{split}_EMPTY")
        for label, required in requirements.items():
            if not required.issubset(observed[label][split]):
                reasons.append(f"CLUSTER_REVIEW_{split}_{label.upper()}_INCOMPLETE")
    if not REQUIRED_CLUSTER_COVERAGE_TAGS.issubset(tags):
        reasons.append("CLUSTER_REVIEW_REQUIRED_COVERAGE_TAGS_INCOMPLETE")
    summary = {
        "query_count": len(query_ids),
        "coverage_tags": sorted(tags),
        "splits": {
            split: {
                "cluster_count": len(cluster_ids_by_split[split]),
                "evidence_anchor_count": len(anchors_by_split[split]),
                "target_profiles": sorted(profiles_by_split[split]),
                "sections": sorted(sections_by_split[split]),
                "employers": sorted(employers_by_split[split]),
                "cluster_kinds": sorted(kinds_by_split[split]),
            }
            for split in _SPLITS
        },
        "cluster_split_overlap_count": len(
            cluster_ids_by_split["CALIBRATION"]
            & cluster_ids_by_split["HOLDOUT"]
        ),
        "evidence_anchor_split_overlap_count": len(
            anchors_by_split["CALIBRATION"] & anchors_by_split["HOLDOUT"]
        ),
    }
    return summary, sorted(set(reasons))


def build_cluster_qrel_prelabel_packet(
    cases: Sequence[Mapping[str, Any]],
    *,
    packet_id: str,
    blinding_nonce: str,
    rubric: Mapping[str, Any],
    expected_rubric_digest: str,
    split_policy: Mapping[str, Any],
    expected_split_policy_digest: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build reviewer and sealed mapping artifacts without creating labels."""

    if not packet_id.strip():
        raise ClusterQrelReviewError("cluster QREL packet_id is required")
    if len(blinding_nonce) < 32:
        raise ClusterQrelReviewError("cluster QREL blinding nonce must be at least 32 characters")
    validated_rubric, reasons = _validate_rubric(
        rubric,
        expected_digest=expected_rubric_digest,
    )
    validated_policy, policy_reasons = _validate_split_policy(
        split_policy,
        expected_digest=expected_split_policy_digest,
    )
    reasons.extend(policy_reasons)
    normalized_cases: list[dict[str, Any]] = []
    if not cases:
        reasons.append("CLUSTER_REVIEW_CASES_EMPTY")
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            reasons.append(f"case[{index}]::CLUSTER_REVIEW_CASE_NOT_OBJECT")
            continue
        normalized, case_reasons = _validate_source_case(case)
        reasons.extend(f"case[{index}]::{reason}" for reason in case_reasons)
        if normalized is not None:
            normalized_cases.append(normalized)
    coverage, coverage_reasons = _validate_coverage(
        normalized_cases,
        policy=validated_policy,
    )
    reasons.extend(coverage_reasons)
    if reasons:
        raise ClusterQrelReviewError("; ".join(sorted(set(reasons))))

    reviewer_queries: list[dict[str, Any]] = []
    internal_mappings: list[dict[str, Any]] = []
    raw_identity_values: set[str] = set()
    for case in normalized_cases:
        universe = case["universe"]
        query_id = str(universe["query_id"])
        raw_identity_values.add(query_id)
        query_blind_id = _blind_id(
            nonce=blinding_nonce,
            purpose="cluster-query-id",
            payload={"packet_id": packet_id, "query_id": query_id},
            prefix="query",
        )
        candidates: list[dict[str, Any]] = []
        candidate_mappings: list[dict[str, Any]] = []
        for cluster_id, row in sorted(case["review_rows"].items()):
            raw_identity_values.add(cluster_id)
            raw_identity_values.update(str(value) for value in row["evidence_anchor_ids"])
            candidate_blind_id = _blind_id(
                nonce=blinding_nonce,
                purpose="cluster-candidate-id",
                payload={
                    "packet_id": packet_id,
                    "query_blind_id": query_blind_id,
                    "cluster_id": cluster_id,
                },
                prefix="candidate",
            )
            candidates.append(
                {
                    "candidate_blind_id": candidate_blind_id,
                    "cluster_kind": row["cluster_kind"],
                    "claim_summary": row["claim_summary"],
                    "operating_context": row["operating_context"],
                    "capability_summaries": list(row["capability_summaries"]),
                    "approved_evidence_summaries": list(
                        row["approved_evidence_summaries"]
                    ),
                }
            )
            candidate_mappings.append(
                {
                    "candidate_blind_id": candidate_blind_id,
                    "cluster_id": cluster_id,
                    "cluster_kind": row["cluster_kind"],
                    "cluster_authority_envelope_sha256": row[
                        "cluster_authority_envelope_sha256"
                    ],
                    "evidence_anchor_ids": list(row["evidence_anchor_ids"]),
                    "coverage_tags": list(row["coverage_tags"]),
                }
            )
        candidates.sort(
            key=lambda row: _blind_id(
                nonce=blinding_nonce,
                purpose="cluster-candidate-order",
                payload={
                    "query_blind_id": query_blind_id,
                    "candidate_blind_id": row["candidate_blind_id"],
                },
                prefix="order",
            )
        )
        reviewer_queries.append(
            {
                "query_blind_id": query_blind_id,
                "query_text": universe["query_text"],
                "target_profile": universe["target_profile"],
                "section": universe["section"],
                "employer_context": universe["employer"],
                "review_target": (
                    "Judge each evidence cluster for target relevance, evidence "
                    "sufficiency, section fit, ambiguity, and rejection reason."
                ),
                "candidate_count": len(candidates),
                "candidates": candidates,
            }
        )
        internal_mappings.append(
            {
                "query_blind_id": query_blind_id,
                "query_id": query_id,
                "split": case["split"],
                "universe_digest": universe["record_digest"],
                "review_source_digest": case["review_source"]["record_digest"],
                "authority_envelope_sha256": universe["authority_bindings"][
                    "authority_envelope_sha256"
                ],
                "target_profile": universe["target_profile"],
                "section": universe["section"],
                "employer": universe["employer"],
                "candidates": sorted(
                    candidate_mappings,
                    key=lambda row: row["candidate_blind_id"],
                ),
            }
        )
    reviewer_queries.sort(key=lambda row: row["query_blind_id"])
    reviewer_packet = seal_record(
        {
            "schema_version": CLUSTER_REVIEWER_PACKET_SCHEMA,
            "packet_id": packet_id,
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "rubric_id": validated_rubric["rubric_id"],
            "rubric_digest": validated_rubric["record_digest"],
            "candidate_order": "BLINDED_DETERMINISTIC_SHUFFLE",
            "query_count": len(reviewer_queries),
            "queries": reviewer_queries,
        }
    )
    unsafe_keys = _unsafe_keys(reviewer_packet)
    encoded_packet = str(reviewer_packet)
    exposed_identities = sorted(
        value for value in raw_identity_values if value and value in encoded_packet
    )
    if unsafe_keys or exposed_identities:
        raise ClusterQrelReviewError(
            "reviewer packet exposes protected fields or identities: "
            f"keys={sorted(unsafe_keys)}, identities={exposed_identities}"
        )
    internal_manifest = seal_record(
        {
            "schema_version": CLUSTER_BLINDING_MANIFEST_SCHEMA,
            "packet_id": packet_id,
            "reviewer_packet_digest": reviewer_packet["record_digest"],
            "rubric_digest": validated_rubric["record_digest"],
            "split_policy_digest": validated_policy["record_digest"],
            "blinding_nonce_sha256": hashlib.sha256(
                blinding_nonce.encode("utf-8")
            ).hexdigest(),
            "coverage": coverage,
            "mappings": sorted(
                internal_mappings,
                key=lambda row: row["query_blind_id"],
            ),
        }
    )
    validation = validate_cluster_qrel_prelabel_packet(
        reviewer_packet=reviewer_packet,
        expected_reviewer_packet_digest=reviewer_packet["record_digest"],
        blinding_manifest=internal_manifest,
        expected_blinding_manifest_digest=internal_manifest["record_digest"],
        rubric=validated_rubric,
        expected_rubric_digest=validated_rubric["record_digest"],
        split_policy=validated_policy,
        expected_split_policy_digest=validated_policy["record_digest"],
    )
    if validation["status"] != "PASS":
        raise ClusterQrelReviewError(
            "generated prelabel packet failed validation: "
            + "; ".join(validation["unknown_reasons"])
        )
    receipt = seal_record(
        {
            "schema_version": CLUSTER_PRELABEL_RECEIPT_SCHEMA,
            "status": "PASS",
            "completion_marker": "CLUSTER_QREL_PRELABEL_PACKET_VALID",
            "packet_id": packet_id,
            "reviewer_packet_digest": reviewer_packet["record_digest"],
            "blinding_manifest_digest": internal_manifest["record_digest"],
            "prelabel_validation_digest": validation["record_digest"],
            "rubric_digest": validated_rubric["record_digest"],
            "split_policy_digest": validated_policy["record_digest"],
            "coverage": coverage,
            "reviewer_payload_blinded": True,
            "rank_visible": False,
            "score_visible": False,
            "split_visible": False,
            "authority_ids_visible": False,
            "labels_created": False,
            "qrels_created": False,
            "evaluation_executed": False,
            "release_authorizing": False,
        }
    )
    return reviewer_packet, internal_manifest, receipt


def _prelabel_validation_receipt(
    *,
    status: str,
    reviewer_packet: Mapping[str, Any],
    blinding_manifest: Mapping[str, Any],
    rubric: Mapping[str, Any],
    split_policy: Mapping[str, Any],
    reasons: Sequence[str],
    checks: Mapping[str, Any],
    labels_present: bool,
) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_PRELABEL_VALIDATION_RECEIPT_SCHEMA,
            "status": status,
            "completion_marker": (
                "CLUSTER_QREL_PRELABEL_PACKET_VALID" if status == "PASS" else None
            ),
            "input_digests": {
                "reviewer_packet": reviewer_packet.get("record_digest"),
                "blinding_manifest": blinding_manifest.get("record_digest"),
                "rubric": rubric.get("record_digest"),
                "split_policy": split_policy.get("record_digest"),
            },
            "checks": dict(checks),
            "labels_present": labels_present,
            "release_authorizing": False,
            "unknown_reasons": sorted(set(reasons)),
        }
    )


def validate_cluster_qrel_prelabel_packet(
    *,
    reviewer_packet: Mapping[str, Any],
    expected_reviewer_packet_digest: str,
    blinding_manifest: Mapping[str, Any],
    expected_blinding_manifest_digest: str,
    rubric: Mapping[str, Any],
    expected_rubric_digest: str,
    split_policy: Mapping[str, Any],
    expected_split_policy_digest: str,
) -> dict[str, Any]:
    """Revalidate a stored packet and its sealed identity/split mapping."""

    reasons: list[str] = []
    reasons.extend(
        validate_pinned_record(
            reviewer_packet,
            expected_digest=expected_reviewer_packet_digest,
            schema_version=CLUSTER_REVIEWER_PACKET_SCHEMA,
        )
    )
    reasons.extend(
        validate_pinned_record(
            blinding_manifest,
            expected_digest=expected_blinding_manifest_digest,
            schema_version=CLUSTER_BLINDING_MANIFEST_SCHEMA,
        )
    )
    validated_rubric, rubric_reasons = _validate_rubric(
        rubric,
        expected_digest=expected_rubric_digest,
    )
    validated_policy, policy_reasons = _validate_split_policy(
        split_policy,
        expected_digest=expected_split_policy_digest,
    )
    reasons.extend(rubric_reasons)
    reasons.extend(policy_reasons)
    packet_fields = {
        "schema_version",
        "packet_id",
        "logical_retrieval_unit",
        "rubric_id",
        "rubric_digest",
        "candidate_order",
        "query_count",
        "queries",
        "record_digest",
    }
    manifest_fields = {
        "schema_version",
        "packet_id",
        "reviewer_packet_digest",
        "rubric_digest",
        "split_policy_digest",
        "blinding_nonce_sha256",
        "coverage",
        "mappings",
        "record_digest",
    }
    if set(reviewer_packet) != packet_fields:
        reasons.append("CLUSTER_PRELABEL_REVIEWER_PACKET_SCHEMA_INVALID")
    if set(blinding_manifest) != manifest_fields:
        reasons.append("CLUSTER_PRELABEL_BLINDING_MANIFEST_SCHEMA_INVALID")
    if not (
        reviewer_packet.get("packet_id") == blinding_manifest.get("packet_id")
        and reviewer_packet.get("logical_retrieval_unit")
        == LOGICAL_RETRIEVAL_UNIT
        and reviewer_packet.get("rubric_id") == validated_rubric.get("rubric_id")
        and reviewer_packet.get("rubric_digest")
        == validated_rubric.get("record_digest")
        and blinding_manifest.get("reviewer_packet_digest")
        == reviewer_packet.get("record_digest")
        and blinding_manifest.get("rubric_digest")
        == validated_rubric.get("record_digest")
        and blinding_manifest.get("split_policy_digest")
        == validated_policy.get("record_digest")
    ):
        reasons.append("CLUSTER_PRELABEL_ARTIFACT_BINDING_MISMATCH")
    if reviewer_packet.get("candidate_order") != "BLINDED_DETERMINISTIC_SHUFFLE":
        reasons.append("CLUSTER_PRELABEL_CANDIDATE_ORDER_INVALID")
    if not HEX64.fullmatch(
        str(blinding_manifest.get("blinding_nonce_sha256") or "")
    ):
        reasons.append("CLUSTER_PRELABEL_NONCE_BINDING_INVALID")
    unsafe_keys = _unsafe_keys(reviewer_packet)
    labels_present = "labels" in _walk_mapping_keys(reviewer_packet)
    if unsafe_keys or labels_present:
        reasons.append("CLUSTER_PRELABEL_REVIEWER_PAYLOAD_NOT_BLINDED")

    packet_query_fields = {
        "query_blind_id",
        "query_text",
        "target_profile",
        "section",
        "employer_context",
        "review_target",
        "candidate_count",
        "candidates",
    }
    packet_candidate_fields = {
        "candidate_blind_id",
        "cluster_kind",
        "claim_summary",
        "operating_context",
        "capability_summaries",
        "approved_evidence_summaries",
    }
    packet_items: dict[str, set[str]] = {}
    queries = reviewer_packet.get("queries")
    if not isinstance(queries, list) or not queries:
        reasons.append("CLUSTER_PRELABEL_QUERY_SET_EMPTY")
        queries = []
    for query in queries:
        if not isinstance(query, Mapping) or set(query) != packet_query_fields:
            reasons.append("CLUSTER_PRELABEL_QUERY_SCHEMA_INVALID")
            continue
        query_blind_id = str(query.get("query_blind_id") or "")
        if not query_blind_id or query_blind_id in packet_items:
            reasons.append("CLUSTER_PRELABEL_QUERY_IDENTITY_INVALID")
            continue
        candidate_ids: set[str] = set()
        candidates = query.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            reasons.append("CLUSTER_PRELABEL_CANDIDATE_SET_EMPTY")
            candidates = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping) or set(candidate) != (
                packet_candidate_fields
            ):
                reasons.append("CLUSTER_PRELABEL_CANDIDATE_SCHEMA_INVALID")
                continue
            candidate_id = str(candidate.get("candidate_blind_id") or "")
            if not candidate_id or candidate_id in candidate_ids:
                reasons.append("CLUSTER_PRELABEL_CANDIDATE_IDENTITY_INVALID")
            candidate_ids.add(candidate_id)
            if candidate.get("cluster_kind") not in _CLUSTER_KINDS:
                reasons.append("CLUSTER_PRELABEL_CANDIDATE_KIND_INVALID")
            if not all(
                isinstance(candidate.get(field), str) and candidate[field]
                for field in ("claim_summary", "operating_context")
            ):
                reasons.append("CLUSTER_PRELABEL_CANDIDATE_TEXT_INVALID")
            for field in (
                "capability_summaries",
                "approved_evidence_summaries",
            ):
                if not _valid_text_list(candidate.get(field)):
                    reasons.append(f"CLUSTER_PRELABEL_{field.upper()}_INVALID")
        if query.get("candidate_count") != len(candidate_ids):
            reasons.append("CLUSTER_PRELABEL_CANDIDATE_COUNT_MISMATCH")
        packet_items[query_blind_id] = candidate_ids
    if reviewer_packet.get("query_count") != len(packet_items):
        reasons.append("CLUSTER_PRELABEL_QUERY_COUNT_MISMATCH")

    mapping_fields = {
        "query_blind_id",
        "query_id",
        "split",
        "universe_digest",
        "review_source_digest",
        "authority_envelope_sha256",
        "target_profile",
        "section",
        "employer",
        "candidates",
    }
    mapping_candidate_fields = {
        "candidate_blind_id",
        "cluster_id",
        "cluster_kind",
        "cluster_authority_envelope_sha256",
        "evidence_anchor_ids",
        "coverage_tags",
    }
    manifest_items: dict[str, set[str]] = {}
    raw_identity_values: set[str] = set()
    cluster_ids_by_split: dict[str, set[str]] = defaultdict(set)
    anchors_by_split: dict[str, set[str]] = defaultdict(set)
    profiles_by_split: dict[str, set[str]] = defaultdict(set)
    sections_by_split: dict[str, set[str]] = defaultdict(set)
    employers_by_split: dict[str, set[str]] = defaultdict(set)
    kinds_by_split: dict[str, set[str]] = defaultdict(set)
    coverage_tags: set[str] = set()
    mappings = blinding_manifest.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        reasons.append("CLUSTER_PRELABEL_MAPPING_SET_EMPTY")
        mappings = []
    for mapping in mappings:
        if not isinstance(mapping, Mapping) or set(mapping) != mapping_fields:
            reasons.append("CLUSTER_PRELABEL_MAPPING_SCHEMA_INVALID")
            continue
        query_blind_id = str(mapping.get("query_blind_id") or "")
        if not query_blind_id or query_blind_id in manifest_items:
            reasons.append("CLUSTER_PRELABEL_MAPPING_IDENTITY_INVALID")
            continue
        split = str(mapping.get("split") or "")
        if split not in _SPLITS:
            reasons.append("CLUSTER_PRELABEL_MAPPING_SPLIT_INVALID")
        for field in (
            "universe_digest",
            "review_source_digest",
            "authority_envelope_sha256",
        ):
            if not HEX64.fullmatch(str(mapping.get(field) or "")):
                reasons.append("CLUSTER_PRELABEL_MAPPING_DIGEST_INVALID")
        raw_identity_values.add(str(mapping.get("query_id") or ""))
        profiles_by_split[split].add(str(mapping.get("target_profile") or ""))
        sections_by_split[split].add(str(mapping.get("section") or ""))
        employers_by_split[split].add(str(mapping.get("employer") or ""))
        candidate_ids: set[str] = set()
        for candidate in mapping.get("candidates") or []:
            if not isinstance(candidate, Mapping) or set(candidate) != (
                mapping_candidate_fields
            ):
                reasons.append("CLUSTER_PRELABEL_MAPPING_CANDIDATE_SCHEMA_INVALID")
                continue
            blind_id = str(candidate.get("candidate_blind_id") or "")
            cluster_id = str(candidate.get("cluster_id") or "")
            if not blind_id or blind_id in candidate_ids or not cluster_id:
                reasons.append("CLUSTER_PRELABEL_MAPPING_CANDIDATE_IDENTITY_INVALID")
            candidate_ids.add(blind_id)
            raw_identity_values.add(cluster_id)
            cluster_ids_by_split[split].add(cluster_id)
            kinds_by_split[split].add(str(candidate.get("cluster_kind") or ""))
            anchors = candidate.get("evidence_anchor_ids")
            tags = candidate.get("coverage_tags")
            if not _valid_text_list(anchors) or not _valid_text_list(tags):
                reasons.append("CLUSTER_PRELABEL_MAPPING_COVERAGE_INVALID")
                continue
            anchors_by_split[split].update(str(value) for value in anchors)
            raw_identity_values.update(str(value) for value in anchors)
            coverage_tags.update(str(value) for value in tags)
        manifest_items[query_blind_id] = candidate_ids
    if packet_items != manifest_items:
        reasons.append("CLUSTER_PRELABEL_PACKET_MAPPING_CONSERVATION_FAILED")
    encoded_packet = str(reviewer_packet)
    if any(value and value in encoded_packet for value in raw_identity_values):
        reasons.append("CLUSTER_PRELABEL_RAW_IDENTITY_EXPOSED")
    cluster_overlap = (
        cluster_ids_by_split["CALIBRATION"] & cluster_ids_by_split["HOLDOUT"]
    )
    anchor_overlap = anchors_by_split["CALIBRATION"] & anchors_by_split["HOLDOUT"]
    if cluster_overlap:
        reasons.append("CLUSTER_PRELABEL_CLUSTER_SPLIT_LEAKAGE")
    if anchor_overlap:
        reasons.append("CLUSTER_PRELABEL_EVIDENCE_ANCHOR_SPLIT_LEAKAGE")
    required_by_dimension = {
        "target_profiles": set(validated_policy.get("required_target_profiles") or []),
        "sections": set(validated_policy.get("required_sections") or []),
        "employers": set(validated_policy.get("required_employers") or []),
        "cluster_kinds": set(validated_policy.get("required_cluster_kinds") or []),
    }
    observed_by_dimension = {
        "target_profiles": profiles_by_split,
        "sections": sections_by_split,
        "employers": employers_by_split,
        "cluster_kinds": kinds_by_split,
    }
    for split in _SPLITS:
        for label, required in required_by_dimension.items():
            if not required.issubset(observed_by_dimension[label][split]):
                reasons.append(f"CLUSTER_PRELABEL_{split}_{label.upper()}_INCOMPLETE")
    if not REQUIRED_CLUSTER_COVERAGE_TAGS.issubset(coverage_tags):
        reasons.append("CLUSTER_PRELABEL_COVERAGE_TAGS_INCOMPLETE")
    recomputed_coverage = {
        "query_count": len(manifest_items),
        "coverage_tags": sorted(coverage_tags),
        "splits": {
            split: {
                "cluster_count": len(cluster_ids_by_split[split]),
                "evidence_anchor_count": len(anchors_by_split[split]),
                "target_profiles": sorted(profiles_by_split[split]),
                "sections": sorted(sections_by_split[split]),
                "employers": sorted(employers_by_split[split]),
                "cluster_kinds": sorted(kinds_by_split[split]),
            }
            for split in _SPLITS
        },
        "cluster_split_overlap_count": len(cluster_overlap),
        "evidence_anchor_split_overlap_count": len(anchor_overlap),
    }
    if blinding_manifest.get("coverage") != recomputed_coverage:
        reasons.append("CLUSTER_PRELABEL_COVERAGE_RECEIPT_MISMATCH")
    checks = {
        "reviewer_payload_blinded": not unsafe_keys,
        "packet_mapping_conservation": packet_items == manifest_items,
        "cluster_split_disjoint": not cluster_overlap,
        "evidence_anchor_split_disjoint": not anchor_overlap,
        "required_coverage_complete": REQUIRED_CLUSTER_COVERAGE_TAGS.issubset(
            coverage_tags
        ),
        "unknown_is_pass": False,
    }
    return _prelabel_validation_receipt(
        status="PASS" if not reasons else "UNKNOWN",
        reviewer_packet=reviewer_packet,
        blinding_manifest=blinding_manifest,
        rubric=validated_rubric,
        split_policy=validated_policy,
        reasons=reasons,
        checks=checks,
        labels_present=labels_present,
    )


def _walk_mapping_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        keys = set(value)
        for child in value.values():
            keys.update(_walk_mapping_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(_walk_mapping_keys(child))
        return keys
    return set()


def _validate_labels(value: object) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != _LABEL_FIELDS:
        return ["CLUSTER_REVIEW_LABEL_SCHEMA_INVALID"]
    reasons: list[str] = []
    grade = value.get("relevance_grade")
    sufficiency = value.get("evidence_sufficiency")
    fitness = value.get("section_fitness")
    ambiguity = value.get("ambiguity")
    rejection = value.get("rejection_reason")
    if grade not in _RELEVANCE_GRADES:
        reasons.append("CLUSTER_REVIEW_RELEVANCE_INVALID")
    if sufficiency not in _EVIDENCE_SUFFICIENCY:
        reasons.append("CLUSTER_REVIEW_EVIDENCE_SUFFICIENCY_INVALID")
    if fitness not in _SECTION_FITNESS:
        reasons.append("CLUSTER_REVIEW_SECTION_FITNESS_INVALID")
    if ambiguity not in _AMBIGUITY:
        reasons.append("CLUSTER_REVIEW_AMBIGUITY_INVALID")
    if rejection not in _REJECTION_REASONS:
        reasons.append("CLUSTER_REVIEW_REJECTION_REASON_INVALID")
    if grade in {2, 3} and (
        sufficiency == "INSUFFICIENT"
        or fitness == "NOT_FIT"
        or rejection != "NONE"
    ):
        reasons.append("CLUSTER_REVIEW_POSITIVE_LABEL_CONFLICT")
    if grade == 0 and rejection == "NONE":
        reasons.append("CLUSTER_REVIEW_ZERO_GRADE_REJECTION_REQUIRED")
    if sufficiency == "INSUFFICIENT" and grade not in {0, 1}:
        reasons.append("CLUSTER_REVIEW_INSUFFICIENT_EVIDENCE_GRADE_CONFLICT")
    if fitness == "NOT_FIT" and grade not in {0, 1}:
        reasons.append("CLUSTER_REVIEW_SECTION_FITNESS_GRADE_CONFLICT")
    if ambiguity == "CONFLICTING" and grade not in {0, 1}:
        reasons.append("CLUSTER_REVIEW_AMBIGUITY_GRADE_CONFLICT")
    return sorted(set(reasons))


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError:
        return None


def _review_item_index(packet: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    items: dict[tuple[str, str], str] = {}
    for query in packet.get("queries") or []:
        if not isinstance(query, Mapping):
            continue
        query_id = str(query.get("query_blind_id") or "")
        for candidate in query.get("candidates") or []:
            if not isinstance(candidate, Mapping):
                continue
            candidate_id = str(candidate.get("candidate_blind_id") or "")
            if query_id and candidate_id:
                items[(query_id, candidate_id)] = canonical_digest(candidate)
    return items


def _completed_unknown(reasons: Sequence[str]) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA,
            "status": "UNKNOWN",
            "completion_marker": None,
            "item_count": 0,
            "review_count": 0,
            "adjudication_count": 0,
            "two_human_reviews_per_item": False,
            "adjudication_per_item": False,
            "zero_unresolved_judgments": False,
            "human_authority_verified": False,
            "qrels_ready": False,
            "release_authorizing": False,
            "input_digests": {},
            "unknown_reasons": sorted(set(reasons)),
        }
    )


def validate_completed_cluster_qrel_reviews(
    *,
    reviewer_packet: Mapping[str, Any],
    expected_reviewer_packet_digest: str,
    blinding_manifest: Mapping[str, Any],
    expected_blinding_manifest_digest: str,
    rubric: Mapping[str, Any],
    expected_rubric_digest: str,
    split_policy: Mapping[str, Any],
    expected_split_policy_digest: str,
    review_bundle: Mapping[str, Any],
    expected_review_bundle_digest: str,
    adjudication_bundle: Mapping[str, Any],
    expected_adjudication_bundle_digest: str,
    authority_receipt_path: Any,
    expected_authority_file_sha256: str,
) -> dict[str, Any]:
    """Validate supplied human judgments; never generate or infer labels."""

    reasons: list[str] = []
    for value, expected, schema in (
        (
            reviewer_packet,
            expected_reviewer_packet_digest,
            CLUSTER_REVIEWER_PACKET_SCHEMA,
        ),
        (
            blinding_manifest,
            expected_blinding_manifest_digest,
            CLUSTER_BLINDING_MANIFEST_SCHEMA,
        ),
        (review_bundle, expected_review_bundle_digest, CLUSTER_REVIEW_BUNDLE_SCHEMA),
        (
            adjudication_bundle,
            expected_adjudication_bundle_digest,
            CLUSTER_ADJUDICATION_BUNDLE_SCHEMA,
        ),
    ):
        reasons.extend(
            validate_pinned_record(
                value,
                expected_digest=expected,
                schema_version=schema,
            )
        )
    validated_rubric, rubric_reasons = _validate_rubric(
        rubric,
        expected_digest=expected_rubric_digest,
    )
    validated_policy, policy_reasons = _validate_split_policy(
        split_policy,
        expected_digest=expected_split_policy_digest,
    )
    reasons.extend(rubric_reasons)
    reasons.extend(policy_reasons)
    prelabel_validation = validate_cluster_qrel_prelabel_packet(
        reviewer_packet=reviewer_packet,
        expected_reviewer_packet_digest=expected_reviewer_packet_digest,
        blinding_manifest=blinding_manifest,
        expected_blinding_manifest_digest=expected_blinding_manifest_digest,
        rubric=rubric,
        expected_rubric_digest=expected_rubric_digest,
        split_policy=split_policy,
        expected_split_policy_digest=expected_split_policy_digest,
    )
    if prelabel_validation["status"] != "PASS":
        reasons.extend(
            f"PRELABEL::{reason}"
            for reason in prelabel_validation["unknown_reasons"]
        )
    authority, roster, authority_reasons = load_human_authority_receipt(
        authority_receipt_path,
        expected_file_sha256=expected_authority_file_sha256,
    )
    reasons.extend(authority_reasons)
    if not all(
        isinstance(value, Mapping)
        for value in (
            reviewer_packet,
            blinding_manifest,
            review_bundle,
            adjudication_bundle,
        )
    ):
        return _completed_unknown(reasons)
    if set(reviewer_packet) != {
        "schema_version",
        "packet_id",
        "logical_retrieval_unit",
        "rubric_id",
        "rubric_digest",
        "candidate_order",
        "query_count",
        "queries",
        "record_digest",
    }:
        reasons.append("CLUSTER_COMPLETED_REVIEWER_PACKET_SCHEMA_INVALID")
    if set(blinding_manifest) != {
        "schema_version",
        "packet_id",
        "reviewer_packet_digest",
        "rubric_digest",
        "split_policy_digest",
        "blinding_nonce_sha256",
        "coverage",
        "mappings",
        "record_digest",
    }:
        reasons.append("CLUSTER_COMPLETED_BLINDING_MANIFEST_SCHEMA_INVALID")
    if set(review_bundle) != {
        "schema_version",
        "packet_digest",
        "rubric_digest",
        "authority_receipt_file_sha256",
        "reviews",
        "record_digest",
    }:
        reasons.append("CLUSTER_REVIEW_BUNDLE_SCHEMA_INVALID")
    if set(adjudication_bundle) != {
        "schema_version",
        "packet_digest",
        "review_bundle_digest",
        "rubric_digest",
        "authority_receipt_file_sha256",
        "adjudications",
        "record_digest",
    }:
        reasons.append("CLUSTER_ADJUDICATION_BUNDLE_SCHEMA_INVALID")
    if not (
        blinding_manifest.get("reviewer_packet_digest")
        == reviewer_packet.get("record_digest")
        and blinding_manifest.get("rubric_digest")
        == validated_rubric.get("record_digest")
        and blinding_manifest.get("split_policy_digest")
        == validated_policy.get("record_digest")
        and reviewer_packet.get("rubric_digest")
        == validated_rubric.get("record_digest")
    ):
        reasons.append("CLUSTER_COMPLETED_PRELABEL_BINDING_MISMATCH")
    for bundle in (review_bundle, adjudication_bundle):
        if bundle.get("packet_digest") != reviewer_packet.get("record_digest"):
            reasons.append("CLUSTER_COMPLETED_PACKET_BINDING_MISMATCH")
        if bundle.get("rubric_digest") != validated_rubric.get("record_digest"):
            reasons.append("CLUSTER_COMPLETED_RUBRIC_BINDING_MISMATCH")
        if bundle.get("authority_receipt_file_sha256") != (
            expected_authority_file_sha256
        ):
            reasons.append("CLUSTER_COMPLETED_AUTHORITY_BINDING_MISMATCH")
    if adjudication_bundle.get("review_bundle_digest") != review_bundle.get(
        "record_digest"
    ):
        reasons.append("CLUSTER_ADJUDICATION_REVIEW_BUNDLE_MISMATCH")

    item_index = _review_item_index(reviewer_packet)
    if not item_index:
        reasons.append("CLUSTER_COMPLETED_ITEM_UNIVERSE_EMPTY")
    authority_issued_at = _parse_utc(authority.get("issued_at"))
    if authority_issued_at is None:
        reasons.append("CLUSTER_COMPLETED_AUTHORITY_TIMESTAMP_INVALID")
    review_fields = {
        "review_id",
        "query_blind_id",
        "candidate_blind_id",
        "candidate_content_digest",
        "reviewer_type",
        "reviewer_identity_ref",
        "reviewer_identity_hash",
        "qualification_ref",
        "label_batch_id",
        "human_attestation",
        "labeled_at",
        "labels",
        "record_digest",
    }
    reviews_by_item: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    review_by_id: dict[str, Mapping[str, Any]] = {}
    reviews = review_bundle.get("reviews")
    if not isinstance(reviews, list):
        reviews = []
        reasons.append("CLUSTER_REVIEW_BUNDLE_ROWS_INVALID")
    for review in reviews:
        if not isinstance(review, Mapping) or set(review) != review_fields:
            reasons.append("CLUSTER_REVIEW_ROW_SCHEMA_INVALID")
            continue
        review_id = str(review.get("review_id") or "")
        key = (
            str(review.get("query_blind_id") or ""),
            str(review.get("candidate_blind_id") or ""),
        )
        if not review_id or review_id in review_by_id:
            reasons.append("CLUSTER_REVIEW_IDENTITY_INVALID")
        review_by_id[review_id] = review
        if key not in item_index:
            reasons.append("CLUSTER_REVIEW_ITEM_UNKNOWN")
            continue
        if review.get("candidate_content_digest") != item_index[key]:
            reasons.append("CLUSTER_REVIEW_CONTENT_BINDING_INVALID")
        if not record_digest_matches(review):
            reasons.append("CLUSTER_REVIEW_RECORD_DIGEST_INVALID")
        identity_ref = str(review.get("reviewer_identity_ref") or "")
        if (
            review.get("reviewer_type") != "human"
            or review.get("human_attestation") is not True
            or review.get("reviewer_identity_hash")
            != hashlib.sha256(identity_ref.encode("utf-8")).hexdigest()
        ):
            reasons.append("CLUSTER_REVIEW_HUMAN_IDENTITY_INVALID")
        reasons.extend(
            validate_authorized_reviewer(
                identity_ref=identity_ref,
                qualification_ref=str(review.get("qualification_ref") or ""),
                cohort="retrieval",
                role="primary",
                roster=roster,
            )
        )
        labeled_at = _parse_utc(review.get("labeled_at"))
        if labeled_at is None or (
            authority_issued_at is not None and labeled_at <= authority_issued_at
        ):
            reasons.append("CLUSTER_REVIEW_TIMESTAMP_INVALID")
        reasons.extend(_validate_labels(review.get("labels")))
        reviews_by_item[key].append(review)
    for key in item_index:
        item_reviews = reviews_by_item.get(key, [])
        if len(item_reviews) != 2:
            reasons.append("CLUSTER_REVIEW_EXACTLY_TWO_PRIMARY_REQUIRED")
            continue
        if len(
            {str(review.get("reviewer_identity_ref") or "") for review in item_reviews}
        ) != 2:
            reasons.append("CLUSTER_REVIEW_PRIMARY_IDENTITIES_NOT_DISTINCT")
        if len(
            {str(review.get("label_batch_id") or "") for review in item_reviews}
        ) != 2:
            reasons.append("CLUSTER_REVIEW_BATCHES_NOT_INDEPENDENT")

    adjudication_fields = {
        "adjudication_id",
        "query_blind_id",
        "candidate_blind_id",
        "review_ids",
        "review_digests",
        "status",
        "adjudicator_type",
        "adjudicator_identity_ref",
        "adjudicator_identity_hash",
        "qualification_ref",
        "human_attestation",
        "adjudicated_at",
        "final_labels",
        "record_digest",
    }
    adjudications_by_item: dict[tuple[str, str], Mapping[str, Any]] = {}
    adjudications = adjudication_bundle.get("adjudications")
    if not isinstance(adjudications, list):
        adjudications = []
        reasons.append("CLUSTER_ADJUDICATION_BUNDLE_ROWS_INVALID")
    for adjudication in adjudications:
        if not isinstance(adjudication, Mapping) or set(adjudication) != (
            adjudication_fields
        ):
            reasons.append("CLUSTER_ADJUDICATION_ROW_SCHEMA_INVALID")
            continue
        key = (
            str(adjudication.get("query_blind_id") or ""),
            str(adjudication.get("candidate_blind_id") or ""),
        )
        if key not in item_index or key in adjudications_by_item:
            reasons.append("CLUSTER_ADJUDICATION_ITEM_INVALID")
            continue
        adjudications_by_item[key] = adjudication
        if not record_digest_matches(adjudication):
            reasons.append("CLUSTER_ADJUDICATION_RECORD_DIGEST_INVALID")
        primary = reviews_by_item.get(key, [])
        if set(adjudication.get("review_ids") or []) != {
            str(review.get("review_id") or "") for review in primary
        }:
            reasons.append("CLUSTER_ADJUDICATION_REVIEW_IDS_INVALID")
        if set(adjudication.get("review_digests") or []) != {
            str(review.get("record_digest") or "") for review in primary
        }:
            reasons.append("CLUSTER_ADJUDICATION_REVIEW_DIGESTS_INVALID")
        identity_ref = str(adjudication.get("adjudicator_identity_ref") or "")
        if (
            adjudication.get("status") != "ADJUDICATED"
            or adjudication.get("adjudicator_type") != "human"
            or adjudication.get("human_attestation") is not True
            or adjudication.get("adjudicator_identity_hash")
            != hashlib.sha256(identity_ref.encode("utf-8")).hexdigest()
        ):
            reasons.append("CLUSTER_ADJUDICATION_HUMAN_IDENTITY_INVALID")
        reasons.extend(
            validate_authorized_reviewer(
                identity_ref=identity_ref,
                qualification_ref=str(adjudication.get("qualification_ref") or ""),
                cohort="retrieval",
                role="adjudicator",
                roster=roster,
            )
        )
        primary_refs = {
            str(review.get("reviewer_identity_ref") or "") for review in primary
        }
        if identity_ref in primary_refs:
            reasons.append("CLUSTER_ADJUDICATOR_NOT_INDEPENDENT")
        adjudicated_at = _parse_utc(adjudication.get("adjudicated_at"))
        if adjudicated_at is None or (
            authority_issued_at is not None and adjudicated_at <= authority_issued_at
        ):
            reasons.append("CLUSTER_ADJUDICATION_TIMESTAMP_INVALID")
        reasons.extend(_validate_labels(adjudication.get("final_labels")))
    if set(adjudications_by_item) != set(item_index):
        reasons.append("CLUSTER_ADJUDICATION_COVERAGE_INCOMPLETE")
    if set(reviews_by_item) - set(item_index):
        reasons.append("CLUSTER_REVIEW_EXTRA_ITEMS")
    if reasons:
        return _completed_unknown(reasons)
    return seal_record(
        {
            "schema_version": CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA,
            "status": "PASS",
            "completion_marker": "CLUSTER_QREL_HUMAN_REVIEWS_COMPLETE",
            "item_count": len(item_index),
            "review_count": len(reviews),
            "adjudication_count": len(adjudications),
            "two_human_reviews_per_item": True,
            "adjudication_per_item": True,
            "zero_unresolved_judgments": True,
            "human_authority_verified": True,
            "qrels_ready": True,
            "release_authorizing": False,
            "input_digests": {
                "reviewer_packet": reviewer_packet["record_digest"],
                "blinding_manifest": blinding_manifest["record_digest"],
                "rubric": validated_rubric["record_digest"],
                "split_policy": validated_policy["record_digest"],
                "review_bundle": review_bundle["record_digest"],
                "adjudication_bundle": adjudication_bundle["record_digest"],
                "human_authority_file_sha256": expected_authority_file_sha256,
            },
            "unknown_reasons": [],
        }
    )


__all__ = [
    "CLUSTER_ADJUDICATION_BUNDLE_SCHEMA",
    "CLUSTER_BLINDING_MANIFEST_SCHEMA",
    "CLUSTER_COMPLETED_REVIEW_RECEIPT_SCHEMA",
    "CLUSTER_PRELABEL_RECEIPT_SCHEMA",
    "CLUSTER_PRELABEL_VALIDATION_RECEIPT_SCHEMA",
    "CLUSTER_REVIEW_BUNDLE_SCHEMA",
    "CLUSTER_REVIEW_SOURCE_SCHEMA",
    "CLUSTER_REVIEWER_PACKET_SCHEMA",
    "CLUSTER_RUBRIC_SCHEMA",
    "CLUSTER_SPLIT_POLICY_SCHEMA",
    "ClusterQrelReviewError",
    "REQUIRED_CLUSTER_COVERAGE_TAGS",
    "build_cluster_qrel_prelabel_packet",
    "validate_cluster_qrel_prelabel_packet",
    "validate_completed_cluster_qrel_reviews",
]
