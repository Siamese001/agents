"""Authoritative evaluation manifest contract."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .artifacts import HEX64, seal_record, validate_pinned_record

SCHEMA_VERSION = "apps_rg.authoritative_evaluation_manifest.v1"
SCORE_GROUPS = (
    "retrieval_quality",
    "binding_accuracy",
    "factual_grounding",
    "section_quality",
    "whole_resume_quality",
    "runtime_repeatability",
    "evaluator_validity",
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_FIELDS = {
    "schema_version",
    "evaluation_id",
    "source_commit",
    "corpus_digest",
    "graph_digest",
    "authority_receipt_file_sha256",
    "truth_bundle_digests",
    "threshold_policy_digests",
    "split_commitments",
    "score_groups",
    "release_authorizing",
    "record_digest",
}


def seal_evaluation_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    return seal_record({**value, "schema_version": SCHEMA_VERSION})


def validate_evaluation_manifest(value: Any, *, expected_digest: str) -> list[str]:
    reasons = validate_pinned_record(
        value,
        expected_digest=expected_digest,
        schema_version=SCHEMA_VERSION,
    )
    if not isinstance(value, Mapping):
        return reasons
    if set(value) != _FIELDS:
        reasons.append("EVALUATION_MANIFEST_FIELDS_INVALID")
    if not isinstance(value.get("evaluation_id"), str) or not value.get("evaluation_id"):
        reasons.append("EVALUATION_ID_INVALID")
    if not _COMMIT.fullmatch(str(value.get("source_commit") or "")):
        reasons.append("SOURCE_COMMIT_INVALID")
    for field in ("corpus_digest", "graph_digest", "authority_receipt_file_sha256"):
        if not HEX64.fullmatch(str(value.get(field) or "")):
            reasons.append(f"{field.upper()}_INVALID")
    for field in ("truth_bundle_digests", "threshold_policy_digests"):
        mapping = value.get(field)
        if not isinstance(mapping, Mapping) or set(mapping) != set(SCORE_GROUPS) or any(
            not isinstance(key, str)
            or not key
            or not HEX64.fullmatch(str(digest or ""))
            for key, digest in (mapping.items() if isinstance(mapping, Mapping) else [])
        ):
            reasons.append(f"{field.upper()}_INVALID")
    splits = value.get("split_commitments")
    if not isinstance(splits, Mapping) or set(splits) != {"calibration", "holdout"} or any(
        not HEX64.fullmatch(str(digest or ""))
        for digest in (splits.values() if isinstance(splits, Mapping) else [])
    ):
        reasons.append("SPLIT_COMMITMENTS_INVALID")
    if value.get("score_groups") != list(SCORE_GROUPS):
        reasons.append("SCORE_GROUP_SET_INVALID")
    if value.get("release_authorizing") is not False:
        reasons.append("MANIFEST_RELEASE_AUTHORITY_FORBIDDEN")
    return sorted(set(reasons))


__all__ = [
    "SCHEMA_VERSION",
    "SCORE_GROUPS",
    "seal_evaluation_manifest",
    "validate_evaluation_manifest",
]
