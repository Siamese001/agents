"""W9 human-review intake and adjudicated QREL finalization for C0.3 clusters."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

CONTRACT_PATH = Path(
    "src/apps_rg/evals/c03_graph_evidence_cluster_human_intake_contract.v1.json"
)
AUTHORITY_TRUST_CONTRACT_PATH = Path(
    "config/contracts/c03_w9_human_authority_trust.v1.json"
)
ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_evidence_cluster_embeddings")
W9_RECEIPT_PATH = ARTIFACT_DIR / "wave9_human_review_intake_receipt.json"

CONTRACT_SCHEMA_VERSION = (
    "apps_rg.c03_graph_evidence_cluster_human_intake_contract.v1"
)
HUMAN_AUTHORITY_SCHEMA_VERSION = (
    "apps_rg.c03_graph_evidence_cluster_human_authority.v1"
)
REVIEW_RETURN_MANIFEST_SCHEMA_VERSION = (
    "apps_rg.c03_graph_evidence_cluster_review_return_manifest.v1"
)
ADJUDICATION_MANIFEST_SCHEMA_VERSION = (
    "apps_rg.c03_graph_evidence_cluster_adjudication_manifest.v1"
)
QREL_SCHEMA_VERSION = "apps_rg.c03_graph_evidence_cluster_qrels.v1"
RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w9_receipt.v1"
W9_COMPLETION_MARKER = (
    "C03_CLUSTER_EMBEDDING_W9_INTAKE_READY_HUMAN_INPUTS_BLOCKED"
)
AUTHORITY_TRUST_SCHEMA_VERSION = "apps_rg.c03_w9_human_authority_trust.v1"

COHORTS = ("reviewer_a", "reviewer_b")
NON_HUMAN_TOKENS = {
    "agent",
    "ai",
    "assistant",
    "auto",
    "automated",
    "automation",
    "bot",
    "claude",
    "codex",
    "gpt",
    "judge",
    "llm",
    "machine",
    "model",
    "openai",
    "pipeline",
    "robot",
    "synthetic",
}


class ClusterHumanIntakeError(ValueError):
    """Raised when W9 authority or completed human inputs are invalid."""


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _is_git_sha(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", str(value or "")))


def _identity_tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.casefold()) if token}


def _valid_timestamp(value: object) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _authority_signature_payload(receipt: Mapping[str, Any]) -> bytes:
    unsigned = dict(receipt)
    unsigned.pop("receipt_digest", None)
    unsigned.pop("external_signature", None)
    return json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _authority_trust_contract() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    path = root / AUTHORITY_TRUST_CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClusterHumanIntakeError(
            f"W9 authority trust contract is unreadable: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ClusterHumanIntakeError("W9 authority trust contract must be an object")
    signature = value.get("signature")
    if (
        value.get("schema_version") != AUTHORITY_TRUST_SCHEMA_VERSION
        or value.get("issuer_ref") != "authority-issuer://evaluation-owner"
        or not isinstance(signature, Mapping)
        or signature.get("algorithm") != "HMAC-SHA256"
        or signature.get("key_id") != "c03-w9-human-authority-v1"
        or signature.get("environment_variable") != "APPS_RG_C03_W9_AUTHORITY_HMAC_KEY"
    ):
        raise ClusterHumanIntakeError("W9 authority trust contract is invalid")
    return {
        "issuer_ref": str(value["issuer_ref"]),
        "algorithm": str(signature["algorithm"]),
        "key_id": str(signature["key_id"]),
        "environment_variable": str(signature["environment_variable"]),
    }


def _authority_signature_issues(receipt: Mapping[str, Any]) -> list[str]:
    try:
        trust = _authority_trust_contract()
    except ClusterHumanIntakeError:
        return ["AUTHORITY_TRUST_CONTRACT"]
    signature = receipt.get("external_signature")
    if not isinstance(signature, Mapping):
        return ["AUTHORITY_EXTERNAL_SIGNATURE"]
    if set(signature) != {"algorithm", "key_id", "signature"}:
        return ["AUTHORITY_EXTERNAL_SIGNATURE_FIELDS"]
    if (
        signature.get("algorithm") != trust["algorithm"]
        or signature.get("key_id") != trust["key_id"]
        or receipt.get("issuer_ref") != trust["issuer_ref"]
    ):
        return ["AUTHORITY_EXTERNAL_SIGNATURE_IDENTITY"]
    secret = os.environ.get(trust["environment_variable"], "")
    if len(secret) < 32:
        return ["AUTHORITY_EXTERNAL_SIGNING_KEY_UNAVAILABLE"]
    expected = hmac.new(
        secret.encode("utf-8"), _authority_signature_payload(receipt), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(str(signature.get("signature") or ""), expected):
        return ["AUTHORITY_EXTERNAL_SIGNATURE_INVALID"]
    return []


def _digest_matches(value: Mapping[str, Any], field: str) -> bool:
    supplied = value.get(field)
    unsigned = dict(value)
    unsigned.pop(field, None)
    return _is_sha256(supplied) and canonical_sha256(unsigned) == supplied


def validate_human_intake_contract(contract: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        issues.append("schema_version")
    if contract.get("wave") != "W9" or contract.get("status") != "FROZEN":
        issues.append("wave_or_status")
    denominator = contract.get("human_denominator") or {}
    expected_counts = {
        "reviewer_count": 2,
        "adjudicator_count": 1,
        "query_section_count": 48,
        "candidate_judgment_count": 456,
        "reviewer_judgment_slot_count": 912,
        "adjudication_count": 456,
    }
    for field, value in expected_counts.items():
        if denominator.get(field) != value:
            issues.append(f"human_denominator.{field}")
    required_true = (
        ("source_authority", "wave8_receipt_required"),
        ("source_authority", "sealed_mapping_required"),
        ("human_authority", "externally_pinned_authority_receipt_required"),
        ("human_authority", "two_distinct_primary_humans_required"),
        ("human_authority", "distinct_human_adjudicator_required"),
        ("human_denominator", "full_candidate_coverage_required"),
        ("human_denominator", "nonempty_rationale_required"),
        ("platform_boundary", "official_finalization_requires_posix_owner_checks"),
        ("activation_boundary", "qualification_is_not_activation"),
    )
    for section, field in required_true:
        if (contract.get(section) or {}).get(field) is not True:
            issues.append(f"{section}.{field}")
    required_false = (
        ("machine_boundary", "machine_labels_allowed"),
        ("machine_boundary", "machine_authority_allowed"),
        ("activation_boundary", "semantic_retrieval_qualified_by_w9_readiness"),
        ("activation_boundary", "activation_manifest_created"),
        ("activation_boundary", "production_promotion_authorized"),
    )
    for section, field in required_false:
        if (contract.get(section) or {}).get(field) is not False:
            issues.append(f"{section}.{field}")
    if issues:
        raise ClusterHumanIntakeError(
            f"Invalid W9 intake contract: {sorted(set(issues))}"
        )


def collect_human_authority_issues(
    receipt: Mapping[str, Any],
    *,
    w8_receipt: Mapping[str, Any],
    packet_manifest: Mapping[str, Any],
    trusted_file_sha256: str,
    observed_file_sha256: str,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    issues: list[str] = []
    expected_keys = {
        "schema_version",
        "authority_mode",
        "official_authority_eligible",
        "wave8_receipt_sha256",
        "packet_manifest_sha256",
        "packet_manifest_file_sha256",
        "reviewer_cohort_manifest_sha256",
        "issuer_ref",
        "approval_ref",
        "issued_at",
        "authorized_participants",
        "unknown_is_pass",
        "external_signature",
        "receipt_digest",
    }
    if set(receipt) != expected_keys:
        issues.append("AUTHORITY_FIELDS")
    if receipt.get("schema_version") != HUMAN_AUTHORITY_SCHEMA_VERSION:
        issues.append("AUTHORITY_SCHEMA")
    if receipt.get("authority_mode") != "TRUSTED_HUMAN_ROSTER_APPROVAL":
        issues.append("AUTHORITY_MODE")
    if receipt.get("official_authority_eligible") is not True:
        issues.append("AUTHORITY_OFFICIAL_ELIGIBILITY")
    if receipt.get("unknown_is_pass") is not False:
        issues.append("AUTHORITY_UNKNOWN_POLICY")
    if not _digest_matches(receipt, "receipt_digest"):
        issues.append("AUTHORITY_RECEIPT_DIGEST")
    issues.extend(_authority_signature_issues(receipt))
    if not _is_sha256(trusted_file_sha256) or observed_file_sha256 != (
        trusted_file_sha256
    ):
        issues.append("AUTHORITY_EXTERNAL_FILE_PIN")
    expected_bindings = {
        "wave8_receipt_sha256": w8_receipt.get("receipt_sha256"),
        "packet_manifest_sha256": packet_manifest.get("manifest_sha256"),
        "packet_manifest_file_sha256": (w8_receipt.get("controlled_packet") or {}).get(
            "packet_manifest_file_sha256"
        ),
        "reviewer_cohort_manifest_sha256": (
            w8_receipt.get("controlled_packet") or {}
        ).get("reviewer_cohort_manifest_sha256"),
    }
    for field, value in expected_bindings.items():
        if receipt.get(field) != value:
            issues.append(f"AUTHORITY_BINDING:{field}")
    if not str(receipt.get("issuer_ref") or "").startswith("authority-issuer://"):
        issues.append("AUTHORITY_ISSUER")
    if not str(receipt.get("approval_ref") or "").startswith("approval://"):
        issues.append("AUTHORITY_APPROVAL")
    if not _valid_timestamp(receipt.get("issued_at")):
        issues.append("AUTHORITY_TIMESTAMP")

    participants = receipt.get("authorized_participants")
    if not isinstance(participants, list):
        participants = []
        issues.append("AUTHORITY_PARTICIPANTS")
    roster: dict[str, dict[str, Any]] = {}
    identities: set[str] = set()
    for index, raw in enumerate(participants):
        if not isinstance(raw, Mapping):
            issues.append(f"AUTHORITY_PARTICIPANT_OBJECT:{index}")
            continue
        expected_participant_keys = {
            "distribution",
            "identity_ref",
            "identity_hash",
            "roles",
            "qualification_ref",
        }
        if set(raw) != expected_participant_keys:
            issues.append(f"AUTHORITY_PARTICIPANT_FIELDS:{index}")
        distribution = str(raw.get("distribution") or "")
        identity = str(raw.get("identity_ref") or "")
        identity_hash = str(raw.get("identity_hash") or "")
        roles = raw.get("roles")
        qualification = str(raw.get("qualification_ref") or "")
        expected_roles = (
            ["primary"] if distribution in COHORTS else ["adjudicator"]
        )
        if distribution not in {*COHORTS, "adjudication"}:
            issues.append(f"AUTHORITY_DISTRIBUTION:{index}")
        if not identity.startswith("human-reviewer://"):
            issues.append(f"AUTHORITY_IDENTITY:{index}")
        if identity_hash != hashlib.sha256(identity.encode("utf-8")).hexdigest():
            issues.append(f"AUTHORITY_IDENTITY_HASH:{index}")
        if roles != expected_roles:
            issues.append(f"AUTHORITY_ROLES:{index}")
        if not qualification.startswith("cluster-relevance://"):
            issues.append(f"AUTHORITY_QUALIFICATION:{index}")
        rejected = _identity_tokens(identity + " " + qualification) & NON_HUMAN_TOKENS
        if rejected:
            issues.append(f"AUTHORITY_NON_HUMAN:{index}")
        if identity in identities:
            issues.append(f"AUTHORITY_IDENTITY_DUPLICATE:{index}")
        identities.add(identity)
        if distribution in roster:
            issues.append(f"AUTHORITY_DISTRIBUTION_DUPLICATE:{distribution}")
        roster[distribution] = dict(raw)
    if set(roster) != {*COHORTS, "adjudication"} or len(identities) != 3:
        issues.append("AUTHORITY_THREE_DISTINCT_HUMANS")
    return sorted(set(issues)), roster


def _validate_review_bundle(
    cohort: str,
    bundle: Mapping[str, Any],
    *,
    packet_items: Sequence[Mapping[str, Any]],
    sealed_items: Sequence[Mapping[str, Any]],
    packet_manifest_sha256: str,
    source_review_items_sha256: str,
    participant: Mapping[str, Any],
) -> tuple[list[str], dict[tuple[str, str, str], int], str]:
    issues: list[str] = []
    manifest = bundle.get("manifest")
    rows = bundle.get("rows")
    observed_file_sha256 = str(bundle.get("observed_file_sha256") or "")
    if not isinstance(manifest, Mapping):
        return [f"{cohort}:MANIFEST_MISSING"], {}, ""
    if not isinstance(rows, list):
        return [f"{cohort}:ROWS_MISSING"], {}, ""
    expected_manifest_keys = {
        "schema_version",
        "status",
        "cohort",
        "packet_manifest_sha256",
        "source_review_items_sha256",
        "human_identity_ref",
        "human_attestation",
        "qualification_ref",
        "completed_at",
        "review_record_count",
        "candidate_grade_count",
        "reviews_file_sha256",
        "manifest_digest",
    }
    if set(manifest) != expected_manifest_keys:
        issues.append(f"{cohort}:MANIFEST_FIELDS")
    if manifest.get("schema_version") != REVIEW_RETURN_MANIFEST_SCHEMA_VERSION:
        issues.append(f"{cohort}:MANIFEST_SCHEMA")
    if manifest.get("status") != "COMPLETED_HUMAN_REVIEW":
        issues.append(f"{cohort}:MANIFEST_STATUS")
    if manifest.get("cohort") != cohort:
        issues.append(f"{cohort}:MANIFEST_COHORT")
    if manifest.get("packet_manifest_sha256") != packet_manifest_sha256:
        issues.append(f"{cohort}:PACKET_BINDING")
    if manifest.get("source_review_items_sha256") != source_review_items_sha256:
        issues.append(f"{cohort}:SOURCE_ITEMS_BINDING")
    identity = str(manifest.get("human_identity_ref") or "")
    if identity != participant.get("identity_ref"):
        issues.append(f"{cohort}:IDENTITY_AUTHORITY")
    if manifest.get("qualification_ref") != participant.get("qualification_ref"):
        issues.append(f"{cohort}:QUALIFICATION_AUTHORITY")
    if manifest.get("human_attestation") is not True:
        issues.append(f"{cohort}:HUMAN_ATTESTATION")
    if not _valid_timestamp(manifest.get("completed_at")):
        issues.append(f"{cohort}:COMPLETED_AT")
    if not _digest_matches(manifest, "manifest_digest"):
        issues.append(f"{cohort}:MANIFEST_DIGEST")
    if (
        not _is_sha256(observed_file_sha256)
        or manifest.get("reviews_file_sha256") != observed_file_sha256
    ):
        issues.append(f"{cohort}:REVIEWS_FILE_DIGEST")

    expected_visible = {
        str(item["item_ref"]): {
            str(candidate["candidate_ref"])
            for candidate in item.get("candidates") or []
        }
        for item in packet_items
    }
    sealed_by_item = {str(item["item_ref"]): item for item in sealed_items}
    if set(expected_visible) != set(sealed_by_item):
        issues.append(f"{cohort}:SEALED_ITEM_PARITY")
    observed_items: set[str] = set()
    grades: dict[tuple[str, str, str], int] = {}
    grade_count = 0
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            issues.append(f"{cohort}:ROW_OBJECT:{index}")
            continue
        if set(row) != {"item_ref", "human_identity", "candidate_grades"}:
            issues.append(f"{cohort}:ROW_FIELDS:{index}")
        item_ref = str(row.get("item_ref") or "")
        if item_ref in observed_items:
            issues.append(f"{cohort}:DUPLICATE_ITEM:{item_ref}")
        observed_items.add(item_ref)
        if row.get("human_identity") != identity:
            issues.append(f"{cohort}:ROW_IDENTITY:{item_ref}")
        candidates = row.get("candidate_grades")
        if not isinstance(candidates, list):
            issues.append(f"{cohort}:CANDIDATE_LIST:{item_ref}")
            continue
        sealed_item = sealed_by_item.get(item_ref) or {}
        sealed_candidates = {
            str(candidate["candidate_ref"]): str(candidate["cluster_id"])
            for candidate in sealed_item.get("candidates") or []
        }
        observed_candidates: set[str] = set()
        for candidate_index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                issues.append(
                    f"{cohort}:CANDIDATE_OBJECT:{item_ref}:{candidate_index}"
                )
                continue
            if set(candidate) != {
                "candidate_ref",
                "relevance_grade",
                "rationale",
            }:
                issues.append(
                    f"{cohort}:CANDIDATE_FIELDS:{item_ref}:{candidate_index}"
                )
            candidate_ref = str(candidate.get("candidate_ref") or "")
            if candidate_ref in observed_candidates:
                issues.append(f"{cohort}:DUPLICATE_CANDIDATE:{candidate_ref}")
            observed_candidates.add(candidate_ref)
            grade = candidate.get("relevance_grade")
            if (
                not isinstance(grade, int)
                or isinstance(grade, bool)
                or grade not in {0, 1, 2, 3}
            ):
                issues.append(f"{cohort}:GRADE:{candidate_ref}")
                continue
            if not str(candidate.get("rationale") or "").strip():
                issues.append(f"{cohort}:RATIONALE:{candidate_ref}")
            cluster_id = sealed_candidates.get(candidate_ref)
            if cluster_id is None:
                issues.append(f"{cohort}:ORPHAN_CANDIDATE:{candidate_ref}")
                continue
            key = (
                str(sealed_item.get("query_id") or ""),
                str(sealed_item.get("section_id") or ""),
                cluster_id,
            )
            grades[key] = grade
            grade_count += 1
        if observed_candidates != expected_visible.get(item_ref, set()):
            issues.append(f"{cohort}:CANDIDATE_DENOMINATOR:{item_ref}")
    if observed_items != set(expected_visible):
        issues.append(f"{cohort}:ITEM_DENOMINATOR")
    if manifest.get("review_record_count") != 48 or len(rows) != 48:
        issues.append(f"{cohort}:REVIEW_RECORD_COUNT")
    if manifest.get("candidate_grade_count") != 456 or grade_count != 456:
        issues.append(f"{cohort}:CANDIDATE_GRADE_COUNT")
    return sorted(set(issues)), grades, identity


def validate_completed_human_inputs(
    *,
    w8_receipt: Mapping[str, Any],
    packet_manifest: Mapping[str, Any],
    packet_items: Mapping[str, Sequence[Mapping[str, Any]]],
    sealed_mapping: Mapping[str, Any],
    source_review_items_sha256: Mapping[str, str],
    authority_receipt: Mapping[str, Any],
    trusted_authority_file_sha256: str,
    observed_authority_file_sha256: str,
    review_bundles: Mapping[str, Mapping[str, Any]],
    adjudication_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate all human inputs and emit W7-compatible QRELs only on PASS."""

    authority_issues, roster = collect_human_authority_issues(
        authority_receipt,
        w8_receipt=w8_receipt,
        packet_manifest=packet_manifest,
        trusted_file_sha256=trusted_authority_file_sha256,
        observed_file_sha256=observed_authority_file_sha256,
    )
    issues = list(authority_issues)
    sealed_cohorts = (sealed_mapping.get("cohorts") or {})
    grades_by_cohort: dict[str, dict[tuple[str, str, str], int]] = {}
    reviewer_ids: dict[str, str] = {}
    for cohort in COHORTS:
        cohort_issues, grades, identity = _validate_review_bundle(
            cohort,
            review_bundles.get(cohort) or {},
            packet_items=packet_items.get(cohort) or [],
            sealed_items=sealed_cohorts.get(cohort) or [],
            packet_manifest_sha256=str(packet_manifest.get("manifest_sha256") or ""),
            source_review_items_sha256=str(
                source_review_items_sha256.get(cohort) or ""
            ),
            participant=roster.get(cohort) or {},
        )
        issues.extend(cohort_issues)
        grades_by_cohort[cohort] = grades
        reviewer_ids[cohort] = identity
    if len(set(reviewer_ids.values())) != 2 or not all(reviewer_ids.values()):
        issues.append("TWO_DISTINCT_PRIMARY_HUMANS")
    if set(grades_by_cohort["reviewer_a"]) != set(
        grades_by_cohort["reviewer_b"]
    ):
        issues.append("CROSS_COHORT_DENOMINATOR")

    adjudication_issues, finals, adjudicator_id = _validate_adjudication_bundle(
        adjudication_bundle,
        packet_items=packet_items.get("reviewer_a") or [],
        sealed_items=sealed_cohorts.get("reviewer_a") or [],
        packet_manifest_sha256=str(packet_manifest.get("manifest_sha256") or ""),
        review_bundles=review_bundles,
        primary_grades=grades_by_cohort,
        participant=roster.get("adjudication") or {},
    )
    issues.extend(adjudication_issues)
    if adjudicator_id in set(reviewer_ids.values()) or not adjudicator_id:
        issues.append("DISTINCT_HUMAN_ADJUDICATOR")

    expected_keys = set(grades_by_cohort["reviewer_a"])
    if set(finals) != expected_keys or len(finals) != 456:
        issues.append("FINAL_ADJUDICATION_DENOMINATOR")
    issues = sorted(set(issues))
    if issues:
        return {
            "status": "BLOCKED_HUMAN_QREL_AUTHORITY",
            "issues": issues,
            "reviewer_judgment_count": sum(
                len(value) for value in grades_by_cohort.values()
            ),
            "adjudication_count": len(finals),
            "qrels": None,
        }

    judgments = [
        {
            "query_id": query_id,
            "section_id": section_id,
            "cluster_id": cluster_id,
            "relevance_grade": finals[(query_id, section_id, cluster_id)],
            "reviewer_ids": [reviewer_ids[cohort] for cohort in COHORTS],
            "adjudicator_id": adjudicator_id,
            "adjudicated": True,
        }
        for query_id, section_id, cluster_id in sorted(finals)
    ]
    qrels: dict[str, Any] = {
        "schema_version": QREL_SCHEMA_VERSION,
        "status": "FROZEN_HUMAN_ADJUDICATED",
        "source_authority": {
            "query_manifest_sha256": w8_receipt["source_baseline"][
                "query_manifest_sha256"
            ],
            "registry_sha256": w8_receipt["source_baseline"][
                "wave4_registry_sha256"
            ],
            "projection_generation_sha256": w8_receipt["source_baseline"][
                "projection_generation_sha256"
            ],
            "ranking_identity_sha256": w8_receipt["source_baseline"][
                "ranking_identity_sha256"
            ],
        },
        "human_review_authority_receipt_sha256": trusted_authority_file_sha256,
        "judgment_count": len(judgments),
        "judgments": judgments,
    }
    qrels["qrel_sha256"] = canonical_sha256(qrels)
    return {
        "status": "PASS_HUMAN_QRELS_FROZEN",
        "issues": [],
        "reviewer_judgment_count": 912,
        "adjudication_count": 456,
        "qrels": qrels,
    }


def _validate_adjudication_bundle(
    bundle: Mapping[str, Any],
    *,
    packet_items: Sequence[Mapping[str, Any]],
    sealed_items: Sequence[Mapping[str, Any]],
    packet_manifest_sha256: str,
    review_bundles: Mapping[str, Mapping[str, Any]],
    primary_grades: Mapping[str, Mapping[tuple[str, str, str], int]],
    participant: Mapping[str, Any],
) -> tuple[list[str], dict[tuple[str, str, str], int], str]:
    issues: list[str] = []
    manifest = bundle.get("manifest")
    rows = bundle.get("rows")
    observed_file_sha256 = str(bundle.get("observed_file_sha256") or "")
    if not isinstance(manifest, Mapping):
        return ["adjudication:MANIFEST_MISSING"], {}, ""
    if not isinstance(rows, list):
        return ["adjudication:ROWS_MISSING"], {}, ""
    expected_manifest_keys = {
        "schema_version",
        "status",
        "packet_manifest_sha256",
        "source_review_manifest_sha256",
        "human_identity_ref",
        "human_attestation",
        "qualification_ref",
        "completed_at",
        "adjudication_record_count",
        "candidate_adjudication_count",
        "adjudications_file_sha256",
        "manifest_digest",
    }
    if set(manifest) != expected_manifest_keys:
        issues.append("adjudication:MANIFEST_FIELDS")
    if manifest.get("schema_version") != ADJUDICATION_MANIFEST_SCHEMA_VERSION:
        issues.append("adjudication:MANIFEST_SCHEMA")
    if manifest.get("status") != "COMPLETED_HUMAN_ADJUDICATION":
        issues.append("adjudication:MANIFEST_STATUS")
    if manifest.get("packet_manifest_sha256") != packet_manifest_sha256:
        issues.append("adjudication:PACKET_BINDING")
    expected_review_manifests = {
        cohort: (review_bundles.get(cohort) or {}).get("manifest", {}).get(
            "manifest_digest"
        )
        for cohort in COHORTS
    }
    if manifest.get("source_review_manifest_sha256") != expected_review_manifests:
        issues.append("adjudication:REVIEW_BINDING")
    identity = str(manifest.get("human_identity_ref") or "")
    if identity != participant.get("identity_ref"):
        issues.append("adjudication:IDENTITY_AUTHORITY")
    if manifest.get("qualification_ref") != participant.get("qualification_ref"):
        issues.append("adjudication:QUALIFICATION_AUTHORITY")
    if manifest.get("human_attestation") is not True:
        issues.append("adjudication:HUMAN_ATTESTATION")
    if not _valid_timestamp(manifest.get("completed_at")):
        issues.append("adjudication:COMPLETED_AT")
    if not _digest_matches(manifest, "manifest_digest"):
        issues.append("adjudication:MANIFEST_DIGEST")
    if (
        not _is_sha256(observed_file_sha256)
        or manifest.get("adjudications_file_sha256") != observed_file_sha256
    ):
        issues.append("adjudication:FILE_DIGEST")

    visible = {
        str(item["item_ref"]): {
            str(candidate["candidate_ref"])
            for candidate in item.get("candidates") or []
        }
        for item in packet_items
    }
    sealed_by_item = {str(item["item_ref"]): item for item in sealed_items}
    observed_items: set[str] = set()
    finals: dict[tuple[str, str, str], int] = {}
    adjudication_count = 0
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            issues.append(f"adjudication:ROW_OBJECT:{index}")
            continue
        if set(row) != {
            "item_ref",
            "adjudicator_identity",
            "candidate_adjudications",
        }:
            issues.append(f"adjudication:ROW_FIELDS:{index}")
        item_ref = str(row.get("item_ref") or "")
        if item_ref in observed_items:
            issues.append(f"adjudication:DUPLICATE_ITEM:{item_ref}")
        observed_items.add(item_ref)
        if row.get("adjudicator_identity") != identity:
            issues.append(f"adjudication:ROW_IDENTITY:{item_ref}")
        candidates = row.get("candidate_adjudications")
        if not isinstance(candidates, list):
            issues.append(f"adjudication:CANDIDATE_LIST:{item_ref}")
            continue
        sealed_item = sealed_by_item.get(item_ref) or {}
        sealed_candidates = {
            str(candidate["candidate_ref"]): str(candidate["cluster_id"])
            for candidate in sealed_item.get("candidates") or []
        }
        observed_candidates: set[str] = set()
        for candidate_index, candidate in enumerate(candidates):
            if not isinstance(candidate, Mapping):
                issues.append(
                    f"adjudication:CANDIDATE_OBJECT:{item_ref}:{candidate_index}"
                )
                continue
            if set(candidate) != {
                "candidate_ref",
                "primary_grades",
                "final_relevance_grade",
                "rationale",
            }:
                issues.append(
                    f"adjudication:CANDIDATE_FIELDS:{item_ref}:{candidate_index}"
                )
            candidate_ref = str(candidate.get("candidate_ref") or "")
            if candidate_ref in observed_candidates:
                issues.append(f"adjudication:DUPLICATE_CANDIDATE:{candidate_ref}")
            observed_candidates.add(candidate_ref)
            cluster_id = sealed_candidates.get(candidate_ref)
            if cluster_id is None:
                issues.append(f"adjudication:ORPHAN_CANDIDATE:{candidate_ref}")
                continue
            key = (
                str(sealed_item.get("query_id") or ""),
                str(sealed_item.get("section_id") or ""),
                cluster_id,
            )
            expected_primary = [
                primary_grades.get(cohort, {}).get(key) for cohort in COHORTS
            ]
            supplied_primary = candidate.get("primary_grades")
            if (
                not isinstance(supplied_primary, list)
                or len(supplied_primary) != 2
                or any(
                    not isinstance(value, int) or isinstance(value, bool)
                    for value in [*supplied_primary, *expected_primary]
                )
                or sorted(supplied_primary) != sorted(expected_primary)
            ):
                issues.append(f"adjudication:PRIMARY_GRADE_BINDING:{candidate_ref}")
            final_grade = candidate.get("final_relevance_grade")
            if (
                not isinstance(final_grade, int)
                or isinstance(final_grade, bool)
                or final_grade not in {0, 1, 2, 3}
            ):
                issues.append(f"adjudication:FINAL_GRADE:{candidate_ref}")
                continue
            if not str(candidate.get("rationale") or "").strip():
                issues.append(f"adjudication:RATIONALE:{candidate_ref}")
            finals[key] = final_grade
            adjudication_count += 1
        if observed_candidates != visible.get(item_ref, set()):
            issues.append(f"adjudication:CANDIDATE_DENOMINATOR:{item_ref}")
    if observed_items != set(visible):
        issues.append("adjudication:ITEM_DENOMINATOR")
    if manifest.get("adjudication_record_count") != 48 or len(rows) != 48:
        issues.append("adjudication:RECORD_COUNT")
    if (
        manifest.get("candidate_adjudication_count") != 456
        or adjudication_count != 456
    ):
        issues.append("adjudication:CANDIDATE_COUNT")
    return sorted(set(issues)), finals, identity


def build_w9_blocked_receipt(
    *,
    contract: Mapping[str, Any],
    w8_receipt: Mapping[str, Any],
    packet_manifest: Mapping[str, Any],
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W9",
        "status": "BLOCKED_HUMAN_REVIEW_INPUTS",
        "completion_marker": W9_COMPLETION_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave8_receipt_sha256": w8_receipt["receipt_sha256"],
            "packet_manifest_sha256": packet_manifest["manifest_sha256"],
            "packet_manifest_file_sha256": w8_receipt["controlled_packet"][
                "packet_manifest_file_sha256"
            ],
            "ranking_identity_sha256": w8_receipt["source_baseline"][
                "ranking_identity_sha256"
            ],
        },
        "contract": {
            "path": CONTRACT_PATH.as_posix(),
            "canonical_sha256": canonical_sha256(contract),
        },
        "intake_readiness": {
            "validator_implemented": True,
            "wave8_packet_verified": True,
            "required_primary_humans": 2,
            "observed_primary_humans": 0,
            "required_adjudicators": 1,
            "observed_adjudicators": 0,
            "required_reviewer_judgment_slots": 912,
            "observed_reviewer_judgment_slots": 0,
            "required_adjudications": 456,
            "observed_adjudications": 0,
            "human_authority_receipt_present": False,
            "adjudicated_qrels_created": False,
        },
        "scope": {
            "human_input_readiness_complete": True,
            "human_qrels_frozen": False,
            "semantic_retrieval_qualified": False,
            "cluster_embedding_activation_created": False,
            "production_promotion_authorized": False,
        },
        "blocking_conditions": [
            "EXTERNALLY_PINNED_HUMAN_AUTHORITY_RECEIPT_MISSING",
            "TWO_COMPLETE_PRIMARY_HUMAN_REVIEWS_MISSING",
            "DISTINCT_HUMAN_ADJUDICATION_MISSING",
            "OFFICIAL_POSIX_CONTROL_STORAGE_REQUIRED",
        ],
        "wave_exit_gates": {
            "prelabel_packet": "PASS_W8",
            "human_review_intake": "BLOCKED_HUMAN_REVIEW_INPUTS",
            "human_cluster_qrels": "OPEN_912_REVIEWS_PLUS_456_ADJUDICATIONS",
            "semantic_retrieval_qualification": "BLOCKED_QREL_AUTHORITY",
            "release_activation": "BLOCKED_UNTIL_QUALIFIED",
            "production_promotion": "NOT_AUTHORIZED",
        },
        "next_action": (
            "On controlled POSIX storage, obtain and externally pin the owner-issued "
            "three-human authority receipt, collect both complete reviewer returns "
            "and all adjudications, then run W9 finalization."
        ),
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_w9_receipt(receipt)
    return receipt


def validate_w9_receipt(receipt: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        issues.append("schema_version")
    if receipt.get("wave_id") != "C03_CLUSTER_EMBEDDING_W9":
        issues.append("wave_id")
    if receipt.get("status") != "BLOCKED_HUMAN_REVIEW_INPUTS":
        issues.append("status")
    if receipt.get("completion_marker") != W9_COMPLETION_MARKER:
        issues.append("completion_marker")
    source = receipt.get("source_baseline") or {}
    for field in ("commit", "tree"):
        if not _is_git_sha(source.get(field)):
            issues.append(f"source_baseline.{field}")
    for field in (
        "wave8_receipt_sha256",
        "packet_manifest_sha256",
        "packet_manifest_file_sha256",
        "ranking_identity_sha256",
    ):
        if not _is_sha256(source.get(field)):
            issues.append(f"source_baseline.{field}")
    contract = receipt.get("contract") or {}
    if contract.get("path") != CONTRACT_PATH.as_posix() or not _is_sha256(
        contract.get("canonical_sha256")
    ):
        issues.append("contract")
    expected_readiness = {
        "validator_implemented": True,
        "wave8_packet_verified": True,
        "required_primary_humans": 2,
        "observed_primary_humans": 0,
        "required_adjudicators": 1,
        "observed_adjudicators": 0,
        "required_reviewer_judgment_slots": 912,
        "observed_reviewer_judgment_slots": 0,
        "required_adjudications": 456,
        "observed_adjudications": 0,
        "human_authority_receipt_present": False,
        "adjudicated_qrels_created": False,
    }
    if receipt.get("intake_readiness") != expected_readiness:
        issues.append("intake_readiness")
    scope = receipt.get("scope") or {}
    if scope.get("human_input_readiness_complete") is not True:
        issues.append("scope.human_input_readiness_complete")
    for field in (
        "human_qrels_frozen",
        "semantic_retrieval_qualified",
        "cluster_embedding_activation_created",
        "production_promotion_authorized",
    ):
        if scope.get(field) is not False:
            issues.append(f"scope.{field}")
    if (receipt.get("wave_exit_gates") or {}).get("production_promotion") != (
        "NOT_AUTHORIZED"
    ):
        issues.append("wave_exit_gates.production_promotion")
    unsigned = dict(receipt)
    supplied = unsigned.pop("receipt_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("receipt_sha256")
    if issues:
        raise ClusterHumanIntakeError(
            f"Invalid W9 receipt: {sorted(set(issues))}"
        )


__all__ = [
    "ADJUDICATION_MANIFEST_SCHEMA_VERSION",
    "COHORTS",
    "CONTRACT_PATH",
    "HUMAN_AUTHORITY_SCHEMA_VERSION",
    "QREL_SCHEMA_VERSION",
    "REVIEW_RETURN_MANIFEST_SCHEMA_VERSION",
    "W9_RECEIPT_PATH",
    "ClusterHumanIntakeError",
    "build_w9_blocked_receipt",
    "collect_human_authority_issues",
    "validate_completed_human_inputs",
    "validate_human_intake_contract",
    "validate_w9_receipt",
]
