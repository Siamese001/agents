"""Externally pinned artifact and human-authority verification helpers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.evals.resume_graph.reporting import canonical_digest

HEX64 = re.compile(r"^[0-9a-f]{64}$")
HUMAN_AUTHORITY_SCHEMA = "apps_rg.c03_human_eval.human_review_authority_receipt.v1"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_has_symlink_component(path: Path) -> bool:
    absolute = Path(path).absolute()
    return any(component.is_symlink() for component in (absolute, *absolute.parents))


def seal_record(value: Mapping[str, Any], *, digest_field: str = "record_digest") -> dict[str, Any]:
    """Seal integrity only; callers still need an independently supplied pin."""

    sealed = dict(value)
    sealed.pop(digest_field, None)
    sealed[digest_field] = canonical_digest(sealed)
    return sealed


def record_digest_matches(value: Mapping[str, Any], *, digest_field: str = "record_digest") -> bool:
    digest = value.get(digest_field)
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        return False
    payload = dict(value)
    payload.pop(digest_field, None)
    return digest == canonical_digest(payload)


def validate_pinned_record(
    value: Any,
    *,
    expected_digest: str,
    schema_version: str,
    digest_field: str = "record_digest",
) -> list[str]:
    reasons: list[str] = []
    if not isinstance(value, Mapping):
        return ["PINNED_RECORD_NOT_OBJECT"]
    if value.get("schema_version") != schema_version:
        reasons.append("PINNED_RECORD_SCHEMA_INVALID")
    if not HEX64.fullmatch(str(expected_digest or "")):
        reasons.append("EXPECTED_RECORD_DIGEST_REQUIRED")
    if not record_digest_matches(value, digest_field=digest_field):
        reasons.append("PINNED_RECORD_DIGEST_INVALID")
    elif value.get(digest_field) != expected_digest:
        reasons.append("PINNED_RECORD_DIFFERS_FROM_EXTERNAL_DIGEST")
    return sorted(set(reasons))


def load_pinned_json(
    path: Path,
    *,
    expected_file_sha256: str,
    schema_version: str,
    digest_field: str = "record_digest",
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    if path.is_symlink():
        reasons.append("PINNED_FILE_SYMLINK_FORBIDDEN")
    if not HEX64.fullmatch(str(expected_file_sha256 or "")):
        reasons.append("EXPECTED_FILE_SHA256_REQUIRED")
    try:
        observed_file_sha256 = file_sha256(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, sorted(set(reasons + ["PINNED_FILE_UNREADABLE"]))
    if observed_file_sha256 != expected_file_sha256:
        reasons.append("PINNED_FILE_DIFFERS_FROM_EXTERNAL_SHA256")
    if not isinstance(raw, Mapping):
        return {}, sorted(set(reasons + ["PINNED_RECORD_NOT_OBJECT"]))
    record = dict(raw)
    reasons.extend(
        validate_pinned_record(
            record,
            expected_digest=str(record.get(digest_field) or ""),
            schema_version=schema_version,
            digest_field=digest_field,
        )
    )
    return record, sorted(set(reasons))


def load_human_authority_receipt(
    path: Path,
    *,
    expected_file_sha256: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    """Validate the existing C0.3 out-of-band roster receipt as a trust root."""

    receipt, reasons = load_pinned_json(
        path,
        expected_file_sha256=expected_file_sha256,
        schema_version=HUMAN_AUTHORITY_SCHEMA,
        digest_field="receipt_digest",
    )
    if not receipt:
        return {}, {}, reasons
    if receipt.get("authority_mode") != "TRUSTED_HUMAN_ROSTER_APPROVAL":
        reasons.append("HUMAN_AUTHORITY_MODE_NOT_TRUSTED")
    if receipt.get("official_authority_eligible") is not True:
        reasons.append("HUMAN_AUTHORITY_NOT_OFFICIAL")
    if receipt.get("unknown_is_pass") is not False:
        reasons.append("HUMAN_AUTHORITY_UNKNOWN_POLICY_INVALID")
    if not str(receipt.get("issuer_ref") or "").startswith("authority-issuer://"):
        reasons.append("HUMAN_AUTHORITY_ISSUER_INVALID")
    if not str(receipt.get("approval_ref") or "").startswith("approval://"):
        reasons.append("HUMAN_AUTHORITY_APPROVAL_INVALID")

    participants = receipt.get("authorized_participants")
    if not isinstance(participants, list) or not participants:
        reasons.append("HUMAN_AUTHORITY_ROSTER_EMPTY")
        participants = []
    roster: dict[str, dict[str, Any]] = {}
    cohorts_by_hash: dict[str, str] = {}
    for participant in participants:
        if not isinstance(participant, Mapping):
            reasons.append("HUMAN_AUTHORITY_PARTICIPANT_INVALID")
            continue
        identity_ref = str(participant.get("identity_ref") or "")
        identity_hash = str(participant.get("identity_hash") or "")
        cohort = str(participant.get("cohort") or "")
        roles = participant.get("roles")
        qualification = str(participant.get("qualification_ref") or "")
        if not identity_ref.startswith("human-reviewer://"):
            reasons.append("HUMAN_AUTHORITY_IDENTITY_INVALID")
        if identity_hash != hashlib.sha256(identity_ref.encode("utf-8")).hexdigest():
            reasons.append("HUMAN_AUTHORITY_IDENTITY_HASH_INVALID")
        if cohort not in {"proof", "retrieval", "w9"}:
            reasons.append("HUMAN_AUTHORITY_COHORT_INVALID")
        if not isinstance(roles, list) or not roles or not set(roles).issubset(
            {"primary", "adjudicator"}
        ):
            reasons.append("HUMAN_AUTHORITY_ROLES_INVALID")
        if not qualification:
            reasons.append("HUMAN_AUTHORITY_QUALIFICATION_INVALID")
        if identity_ref in roster:
            reasons.append("HUMAN_AUTHORITY_IDENTITY_DUPLICATE")
        prior_cohort = cohorts_by_hash.setdefault(identity_hash, cohort)
        if prior_cohort != cohort:
            reasons.append("HUMAN_AUTHORITY_CROSS_COHORT_IDENTITY")
        roster[identity_ref] = dict(participant)
    return receipt, roster, sorted(set(reasons))


def validate_authorized_reviewer(
    *,
    identity_ref: str,
    qualification_ref: str | None,
    cohort: str,
    role: str,
    roster: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    participant = roster.get(identity_ref)
    if not isinstance(participant, Mapping):
        return ["REVIEWER_NOT_IN_AUTHORIZED_ROSTER"]
    reasons: list[str] = []
    if participant.get("cohort") != cohort:
        reasons.append("REVIEWER_COHORT_NOT_AUTHORIZED")
    roles = participant.get("roles")
    if not isinstance(roles, list) or role not in roles:
        reasons.append("REVIEWER_ROLE_NOT_AUTHORIZED")
    expected_qualification = str(participant.get("qualification_ref") or "")
    if qualification_ref is not None and qualification_ref != expected_qualification:
        reasons.append("REVIEWER_QUALIFICATION_MISMATCH")
    return reasons


def validate_label_review_coverage(
    row: Mapping[str, Any],
    *,
    reviewer_identity_refs: Sequence[str],
    adjudicator_identity_ref: str,
) -> list[str]:
    """Require every truth row to bind the declared reviewers and adjudicator."""

    observed_reviewers = row.get("reviewer_identity_refs")
    if (
        not isinstance(observed_reviewers, list)
        or any(not isinstance(identity, str) or not identity for identity in observed_reviewers)
        or any(not isinstance(identity, str) or not identity for identity in reviewer_identity_refs)
        or len(observed_reviewers) != len(set(observed_reviewers))
        or set(observed_reviewers) != set(reviewer_identity_refs)
    ):
        return ["LABEL_REVIEWER_COVERAGE_INVALID"]
    reasons: list[str] = []
    if row.get("adjudication_status") != "ADJUDICATED":
        reasons.append("LABEL_ADJUDICATION_INCOMPLETE")
    if row.get("adjudicator_identity_ref") != adjudicator_identity_ref:
        reasons.append("LABEL_ADJUDICATOR_BINDING_INVALID")
    return reasons


__all__ = [
    "HEX64",
    "HUMAN_AUTHORITY_SCHEMA",
    "file_sha256",
    "load_human_authority_receipt",
    "load_pinned_json",
    "path_has_symlink_component",
    "record_digest_matches",
    "seal_record",
    "validate_authorized_reviewer",
    "validate_label_review_coverage",
    "validate_pinned_record",
]
