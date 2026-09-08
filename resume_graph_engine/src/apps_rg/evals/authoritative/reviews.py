"""Authority-bound section and whole-resume evaluation wrappers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

from apps_rg.evals.section_quality_benchmark.evaluation import evaluate_section_benchmark
from apps_rg.evals.whole_resume.evaluation import evaluate_whole_resume

from .artifacts import (
    HEX64,
    load_human_authority_receipt,
    seal_record,
    validate_authorized_reviewer,
    validate_pinned_record,
)

SECTION_ADJUDICATION_SCHEMA = "apps_rg.authoritative_section_adjudications.v1"
SECTION_GROUNDING_INDEX_SCHEMA = "apps_rg.authoritative_section_grounding_index.v1"
SECTION_RECEIPT_SCHEMA = "apps_rg.authoritative_section_quality_receipt.v1"
GROUNDING_INDEX_SCHEMA = "apps_rg.authoritative_whole_resume_grounding_index.v1"
WHOLE_RECEIPT_SCHEMA = "apps_rg.authoritative_whole_resume_receipt.v1"


def _wrap_unknown(
    *, schema_version: str, source_report: Mapping[str, Any], reasons: list[str]
) -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": schema_version,
            "status": "UNKNOWN",
            "source_report": dict(source_report),
            "unknown_reasons": sorted(set(reasons)),
            "authority": {
                "human_authority_verified": False,
                "source_grounding_verified": False,
                "release_authorizing": False,
            },
        }
    )


def evaluate_authoritative_sections(
    input_bundle: Any,
    review_bundle: Any,
    *,
    adjudication_bundle: Any,
    expected_adjudication_digest: str,
    grounding_index: Any,
    expected_grounding_index_digest: str,
    authority_receipt_path: Any,
    expected_authority_file_sha256: str,
) -> dict[str, Any]:
    """Require two rostered human reviews and one rostered adjudicator per section case."""

    source_report = evaluate_section_benchmark(input_bundle, review_bundle)
    reasons = validate_pinned_record(
        adjudication_bundle,
        expected_digest=expected_adjudication_digest,
        schema_version=SECTION_ADJUDICATION_SCHEMA,
    )
    reasons.extend(
        validate_pinned_record(
            grounding_index,
            expected_digest=expected_grounding_index_digest,
            schema_version=SECTION_GROUNDING_INDEX_SCHEMA,
        )
    )
    authority, roster, authority_reasons = load_human_authority_receipt(
        authority_receipt_path,
        expected_file_sha256=expected_authority_file_sha256,
    )
    reasons.extend(authority_reasons)
    if not all(
        isinstance(value, Mapping)
        for value in (input_bundle, review_bundle, adjudication_bundle, grounding_index)
    ):
        return _wrap_unknown(
            schema_version=SECTION_RECEIPT_SCHEMA,
            source_report=source_report,
            reasons=reasons,
        )
    if adjudication_bundle.get("authority_receipt_file_sha256") != expected_authority_file_sha256:
        reasons.append("SECTION_ADJUDICATION_AUTHORITY_BINDING_MISMATCH")
    if adjudication_bundle.get("input_bundle_digest") != input_bundle.get("bundle_digest"):
        reasons.append("SECTION_ADJUDICATION_INPUT_BINDING_MISMATCH")
    if adjudication_bundle.get("review_bundle_digest") != review_bundle.get("bundle_digest"):
        reasons.append("SECTION_ADJUDICATION_REVIEW_BINDING_MISMATCH")
    if grounding_index.get("authority_receipt_file_sha256") != expected_authority_file_sha256:
        reasons.append("SECTION_GROUNDING_AUTHORITY_BINDING_MISMATCH")
    grounded_artifacts = grounding_index.get("artifacts")
    if not isinstance(grounded_artifacts, Mapping):
        reasons.append("SECTION_GROUNDING_INDEX_INVALID")
        grounded_artifacts = {}
    expected_artifacts: set[str] = set()
    for case in input_bundle.get("lane_cases") or []:
        if not isinstance(case, Mapping):
            continue
        for label in ("candidate", "baseline"):
            artifact = case.get(label)
            if not isinstance(artifact, Mapping):
                continue
            artifact_id = str(artifact.get("artifact_id") or "")
            if artifact_id:
                expected_artifacts.add(artifact_id)
            ground = grounded_artifacts.get(artifact_id)
            if (
                not isinstance(ground, Mapping)
                or ground.get("gate_id") != "G3"
                or ground.get("status") != "PASS"
                or not HEX64.fullmatch(str(ground.get("source_receipt_digest") or ""))
            ):
                reasons.append("SECTION_ARTIFACT_G3_BINDING_NONPASS")
    if set(grounded_artifacts) != expected_artifacts:
        reasons.append("SECTION_GROUNDING_DENOMINATOR_MISMATCH")

    reviews_by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    reviews_by_id: dict[str, Mapping[str, Any]] = {}
    for review in review_bundle.get("reviews") or []:
        if not isinstance(review, Mapping) or review.get("reviewer_class") != "HUMAN":
            continue
        reviews_by_case[str(review.get("case_id") or "")].append(review)
        reviews_by_id[str(review.get("review_id") or "")] = review
        reasons.extend(
            validate_authorized_reviewer(
                identity_ref=str(review.get("reviewer_identity_ref") or ""),
                qualification_ref=None,
                cohort="w9",
                role="primary",
                roster=roster,
            )
        )
    adjudications = adjudication_bundle.get("adjudications")
    if not isinstance(adjudications, list):
        reasons.append("SECTION_ADJUDICATION_SET_INVALID")
        adjudications = []
    adjudication_by_case: dict[str, Mapping[str, Any]] = {}
    for row in adjudications:
        if not isinstance(row, Mapping):
            reasons.append("SECTION_ADJUDICATION_ROW_INVALID")
            continue
        case_id = str(row.get("case_id") or "")
        if not case_id or case_id in adjudication_by_case:
            reasons.append("SECTION_ADJUDICATION_CASE_ID_INVALID")
            continue
        adjudication_by_case[case_id] = row
        reasons.extend(
            validate_authorized_reviewer(
                identity_ref=str(row.get("adjudicator_identity_ref") or ""),
                qualification_ref=str(row.get("qualification_ref") or ""),
                cohort="w9",
                role="adjudicator",
                roster=roster,
            )
        )
        case_reviews = reviews_by_case.get(case_id, [])
        identities = {str(review.get("reviewer_identity_ref") or "") for review in case_reviews}
        if len(case_reviews) < 2 or len(identities) < 2:
            reasons.append("SECTION_TWO_INDEPENDENT_REVIEWS_REQUIRED")
        expected_review_ids = {str(review.get("review_id") or "") for review in case_reviews}
        raw_review_ids = row.get("review_ids")
        if not isinstance(raw_review_ids, list) or any(
            not isinstance(review_id, str) for review_id in raw_review_ids
        ):
            reasons.append("SECTION_ADJUDICATION_REVIEW_REFS_INVALID")
            raw_review_ids = []
        if set(raw_review_ids) != expected_review_ids:
            reasons.append("SECTION_ADJUDICATION_REVIEW_REFS_INVALID")
        if any(review_id not in reviews_by_id for review_id in raw_review_ids):
            reasons.append("SECTION_ADJUDICATION_REVIEW_NOT_FOUND")
    supplied_case_ids = {
        str(case.get("case_id") or "")
        for case in input_bundle.get("lane_cases") or []
        if isinstance(case, Mapping)
    }
    if set(adjudication_by_case) != supplied_case_ids:
        reasons.append("SECTION_ADJUDICATION_COVERAGE_INCOMPLETE")
    if source_report.get("authority", {}).get("classification") != "HUMAN_REVIEW":
        reasons.append("SECTION_HUMAN_MEASUREMENT_INCOMPLETE")
    if reasons:
        return _wrap_unknown(
            schema_version=SECTION_RECEIPT_SCHEMA,
            source_report=source_report,
            reasons=reasons,
        )
    return seal_record(
        {
            "schema_version": SECTION_RECEIPT_SCHEMA,
            "status": source_report["status"],
            "source_report": source_report,
            "unknown_reasons": [],
            "authority": {
                "authority_receipt_digest": authority.get("receipt_digest"),
                "authority_receipt_file_sha256": expected_authority_file_sha256,
                "adjudication_bundle_digest": adjudication_bundle.get("record_digest"),
                "human_authority_verified": True,
                "source_grounding_verified": True,
                "release_authorizing": False,
            },
        }
    )


def evaluate_authoritative_whole_resume(
    bundle: Any,
    *,
    expected_bundle_digest: str,
    grounding_index: Any,
    expected_grounding_index_digest: str,
    authority_receipt_path: Any,
    expected_authority_file_sha256: str,
) -> dict[str, Any]:
    """Bind W9 reviewers and every candidate material claim to verified G3 receipts."""

    source_report = evaluate_whole_resume(bundle)
    reasons = validate_pinned_record(
        grounding_index,
        expected_digest=expected_grounding_index_digest,
        schema_version=GROUNDING_INDEX_SCHEMA,
    )
    authority, roster, authority_reasons = load_human_authority_receipt(
        authority_receipt_path,
        expected_file_sha256=expected_authority_file_sha256,
    )
    reasons.extend(authority_reasons)
    if not isinstance(bundle, Mapping) or not isinstance(grounding_index, Mapping):
        return _wrap_unknown(
            schema_version=WHOLE_RECEIPT_SCHEMA,
            source_report=source_report,
            reasons=reasons,
        )
    if not HEX64.fullmatch(str(expected_bundle_digest or "")):
        reasons.append("EXPECTED_WHOLE_RESUME_BUNDLE_DIGEST_REQUIRED")
    if bundle.get("bundle_digest") != expected_bundle_digest:
        reasons.append("WHOLE_RESUME_BUNDLE_DIFFERS_FROM_EXTERNAL_DIGEST")
    if source_report.get("input_bundle_digest") != expected_bundle_digest:
        reasons.append("WHOLE_RESUME_BUNDLE_DIGEST_INVALID")
    evidence = bundle.get("human_review_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("authority_receipt_digest") != authority.get(
        "receipt_digest"
    ):
        reasons.append("WHOLE_RESUME_AUTHORITY_RECEIPT_BINDING_MISMATCH")
    if grounding_index.get("authority_receipt_file_sha256") != expected_authority_file_sha256:
        reasons.append("WHOLE_RESUME_GROUNDING_AUTHORITY_BINDING_MISMATCH")
    grounded_claims = grounding_index.get("claims")
    if not isinstance(grounded_claims, Mapping):
        reasons.append("WHOLE_RESUME_GROUNDING_INDEX_INVALID")
        grounded_claims = {}
    expected_candidate_claims: set[str] = set()
    for pair in bundle.get("pairs") or []:
        if not isinstance(pair, Mapping):
            continue
        candidate_key = "resume_a" if pair.get("candidate_variant") == "A" else "resume_b"
        candidate = pair.get(candidate_key)
        if isinstance(candidate, Mapping):
            for section in candidate.get("sections") or []:
                if not isinstance(section, Mapping):
                    continue
                for claim in section.get("claims") or []:
                    if isinstance(claim, Mapping) and claim.get("material") is True:
                        claim_id = str(claim.get("claim_id") or "")
                        expected_candidate_claims.add(claim_id)
                        ground = grounded_claims.get(claim_id)
                        if (
                            not isinstance(ground, Mapping)
                            or ground.get("status") != "PASS"
                            or ground.get("gate_id") != "G3"
                            or not HEX64.fullmatch(
                                str(ground.get("source_receipt_digest") or "")
                            )
                        ):
                            reasons.append("WHOLE_RESUME_CLAIM_G3_BINDING_NONPASS")
        for review in pair.get("reviews") or []:
            if not isinstance(review, Mapping):
                continue
            reasons.extend(
                validate_authorized_reviewer(
                    identity_ref=str(review.get("reviewer_identity_ref") or ""),
                    qualification_ref=str(review.get("qualification_ref") or ""),
                    cohort="w9",
                    role="primary",
                    roster=roster,
                )
            )
        adjudication = pair.get("adjudication")
        if isinstance(adjudication, Mapping) and adjudication.get("status") == "ADJUDICATED":
            reasons.extend(
                validate_authorized_reviewer(
                    identity_ref=str(adjudication.get("adjudicator_identity_ref") or ""),
                    qualification_ref=str(adjudication.get("qualification_ref") or ""),
                    cohort="w9",
                    role="adjudicator",
                    roster=roster,
                )
            )
    if set(grounded_claims) != expected_candidate_claims:
        reasons.append("WHOLE_RESUME_GROUNDING_DENOMINATOR_MISMATCH")
    if reasons:
        return _wrap_unknown(
            schema_version=WHOLE_RECEIPT_SCHEMA,
            source_report=source_report,
            reasons=reasons,
        )
    return seal_record(
        {
            "schema_version": WHOLE_RECEIPT_SCHEMA,
            "status": source_report["status"],
            "source_report": source_report,
            "unknown_reasons": [],
            "authority": {
                "authority_receipt_digest": authority.get("receipt_digest"),
                "authority_receipt_file_sha256": expected_authority_file_sha256,
                "grounding_index_digest": grounding_index.get("record_digest"),
                "human_authority_verified": True,
                "source_grounding_verified": True,
                "release_authorizing": False,
            },
        }
    )


__all__ = [
    "GROUNDING_INDEX_SCHEMA",
    "SECTION_ADJUDICATION_SCHEMA",
    "SECTION_GROUNDING_INDEX_SCHEMA",
    "SECTION_RECEIPT_SCHEMA",
    "WHOLE_RECEIPT_SCHEMA",
    "evaluate_authoritative_sections",
    "evaluate_authoritative_whole_resume",
]
