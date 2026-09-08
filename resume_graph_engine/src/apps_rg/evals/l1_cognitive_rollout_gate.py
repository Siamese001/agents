"""Fail-closed W6 readiness gate for the Apps RG L1 cognitive experiment.

The gate verifies supplied human-governed evidence but never creates reviewer
judgments, opens a protected holdout, invokes a runtime, or activates a
treatment.  A passing receipt only tells an operator that the named human
approval and bounded rollback plan are present; it is not an automatic release.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.evals.l1_cognitive_calibration import holdout_commitment_path
from apps_rg.evals.l1_cognitive_capability_outcome import (
    L1_COGNITIVE_CAPABILITY_DIMENSIONS,
    validate_l1_cognitive_capability_outcome,
)
from apps_rg.evals.l1_cognitive_paired_cohort import (
    validate_l1_cognitive_paired_cohort_manifest,
)
from apps_rg.evals.l1_cognitive_outcome_protocol import (
    load_l1_cognitive_outcome_protocol,
    validate_l1_cognitive_paired_shadow_receipt,
)
from apps_rg.evals.l1_cognitive_blind_review_packet import (
    L1_COGNITIVE_BLIND_REVIEW_MAPPING_SCHEMA_VERSION,
    L1_COGNITIVE_BLIND_REVIEW_PACKET_SCHEMA_VERSION,
)


L1_COGNITIVE_HUMAN_OUTCOME_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_human_outcome.v2"
)
L1_COGNITIVE_PROTECTED_HOLDOUT_OUTCOME_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_protected_holdout_outcome.v2"
)
L1_COGNITIVE_ROLLOUT_PLAN_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_rollout_plan.v1"
)
L1_COGNITIVE_RELEASE_APPROVAL_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_release_approval.v2"
)
L1_COGNITIVE_ROLLOUT_GATE_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_rollout_gate.v3"
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_HOLDOUT_COMMITMENT_REF: Final[str] = (
    "apps_rg/evals/fixtures/l1_v2_protected_holdout_commitment.v1.json"
)
_GUARDRAIL_FIELDS: Final[tuple[str, ...]] = (
    "unsupported_material_claim_count",
    "critical_binding_error_count",
    "critical_run_divergence_count",
)
_VARIANT_ASSESSMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "variant_id",
        "finished_resume_utility_score",
        "grounded_decision_ready",
        "unsupported_material_claim_count",
    }
)
_HANDOFF_DIGEST_FIELDS: Final[frozenset[str]] = frozenset(
    {"record_digest", "plan_digest", "approval_digest"}
)


class L1CognitiveRolloutGateError(ValueError):
    """Raised when a caller attempts to persist an invalid W6 gate receipt."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def _digest_is_valid(value: Any) -> bool:
    digest = str(value or "")
    return digest.startswith("sha256:") and len(digest) == len("sha256:") + 64


def _record_digest(value: Mapping[str, Any], *, field: str) -> bool:
    body = dict(value)
    observed = body.pop(field, None)
    return observed == _sha256(body)


def rollout_gate_digest(receipt: Mapping[str, Any]) -> str:
    """Return the stable digest excluding the rollout receipt self-reference."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return _sha256(body)


def seal_l1_cognitive_handoff_record(
    value: Mapping[str, Any], *, digest_field: str
) -> dict[str, Any]:
    """Seal exactly human-authored handoff content without attesting to it.

    This utility only calculates a canonical integrity digest. It does not
    validate the record's schema, invent a reviewer assessment, attest to a
    human identity, or determine whether the record supports rollout.
    """

    if digest_field not in _HANDOFF_DIGEST_FIELDS:
        raise L1CognitiveRolloutGateError("handoff digest field is unsupported")
    record = _mapping(value, label="handoff record")
    observed = record.pop(digest_field, None)
    expected = _sha256(record)
    if observed not in (None, "") and observed != expected:
        raise L1CognitiveRolloutGateError("handoff record already has a wrong digest")
    record[digest_field] = expected
    return record


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise L1CognitiveRolloutGateError(f"{label} is invalid")
    return dict(value)


def _nonempty(value: Any, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1CognitiveRolloutGateError(f"{label} is required")
    return normalized


def _nonnegative_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise L1CognitiveRolloutGateError(f"{label} is invalid")
    return value


def _variant_assessments(
    value: Any, *, variant_ids: set[str], label: str
) -> list[dict[str, Any]]:
    """Validate human blind-variant scores without exposing an arm."""

    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != len(variant_ids)
    ):
        raise L1CognitiveRolloutGateError(f"{label} variant assessments are invalid")
    by_variant: dict[str, dict[str, Any]] = {}
    for raw_assessment in value:
        assessment = _mapping(raw_assessment, label=f"{label} variant assessment")
        if set(assessment) != _VARIANT_ASSESSMENT_FIELDS:
            raise L1CognitiveRolloutGateError(
                f"{label} variant assessment fields are invalid"
            )
        variant_id = _nonempty(
            assessment.get("variant_id"), label=f"{label} variant identity"
        )
        if variant_id not in variant_ids or variant_id in by_variant:
            raise L1CognitiveRolloutGateError(
                f"{label} variant assessment binding is invalid"
            )
        utility = assessment.get("finished_resume_utility_score")
        if (
            isinstance(utility, bool)
            or not isinstance(utility, int)
            or not 1 <= utility <= 5
        ):
            raise L1CognitiveRolloutGateError(
                f"{label} finished-resume utility score is invalid"
            )
        if not isinstance(assessment.get("grounded_decision_ready"), bool):
            raise L1CognitiveRolloutGateError(
                f"{label} grounded decision-ready assessment is invalid"
            )
        unsupported = _nonnegative_int(
            assessment.get("unsupported_material_claim_count"),
            label=f"{label} unsupported material claim count",
        )
        by_variant[variant_id] = {
            "variant_id": variant_id,
            "finished_resume_utility_score": utility,
            "grounded_decision_ready": assessment["grounded_decision_ready"],
            "unsupported_material_claim_count": unsupported,
        }
    if set(by_variant) != variant_ids:
        raise L1CognitiveRolloutGateError(
            f"{label} variant assessment coverage is invalid"
        )
    return [by_variant[variant_id] for variant_id in sorted(variant_ids)]


def _adjudicated_measurement_summary(
    *,
    assessments_by_pair: Mapping[str, Sequence[Mapping[str, Any]]],
    variant_arms_by_pair: Mapping[str, Mapping[str, str]],
) -> dict[str, int]:
    """Derive primary outcomes and material-claim counts from opaque verdicts."""

    summary = {
        "pair_count": 0,
        "candidate_finished_resume_utility_score_sum": 0,
        "control_finished_resume_utility_score_sum": 0,
        "candidate_grounded_decision_ready_count": 0,
        "control_grounded_decision_ready_count": 0,
        "candidate_unsupported_material_claim_count": 0,
        "control_unsupported_material_claim_count": 0,
    }
    for pair_id in sorted(assessments_by_pair):
        arms = variant_arms_by_pair.get(pair_id)
        if arms is None or set(arms.values()) != {"control", "candidate"}:
            raise L1CognitiveRolloutGateError(
                "adjudicated variant arm binding is invalid"
            )
        summary["pair_count"] += 1
        for assessment in assessments_by_pair[pair_id]:
            variant_id = str(assessment.get("variant_id") or "")
            arm = arms.get(variant_id)
            if arm not in {"control", "candidate"}:
                raise L1CognitiveRolloutGateError(
                    "adjudicated variant assessment binding is invalid"
                )
            summary[f"{arm}_finished_resume_utility_score_sum"] += int(
                assessment["finished_resume_utility_score"]
            )
            if assessment["grounded_decision_ready"]:
                summary[f"{arm}_grounded_decision_ready_count"] += 1
            summary[f"{arm}_unsupported_material_claim_count"] += int(
                assessment["unsupported_material_claim_count"]
            )
    return summary


def _primary_outcomes_from_measurements(
    measurements: Mapping[str, int],
) -> dict[str, str]:
    return {
        "P1": (
            "IMPROVED"
            if measurements["candidate_finished_resume_utility_score_sum"]
            > measurements["control_finished_resume_utility_score_sum"]
            else "NOT_IMPROVED"
        ),
        "P2": (
            "IMPROVED"
            if measurements["candidate_grounded_decision_ready_count"]
            > measurements["control_grounded_decision_ready_count"]
            else "NOT_IMPROVED"
        ),
    }


def _load_holdout_commitment_digest() -> str:
    """Read only the tracked opaque commitment metadata, never a holdout case."""

    path = Path(holdout_commitment_path())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1CognitiveRolloutGateError(
            "protected holdout commitment is unreadable"
        ) from exc
    if not isinstance(payload, Mapping) or not _digest_is_valid(
        payload.get("commitment_digest")
    ):
        raise L1CognitiveRolloutGateError("protected holdout commitment is invalid")
    return str(payload["commitment_digest"])


def _verify_paired_receipt(
    value: Any,
) -> tuple[str, list[str], dict[str, dict[str, str]]]:
    receipt = _mapping(value, label="paired receipt")
    pairs = receipt.get("pairs")
    if not isinstance(pairs, Sequence) or isinstance(pairs, (str, bytes)):
        raise L1CognitiveRolloutGateError("paired receipt pairs are invalid")
    try:
        validate_l1_cognitive_paired_shadow_receipt(
            receipt,
            protocol=load_l1_cognitive_outcome_protocol(),
            pairs=pairs,
        )
    except ValueError as exc:
        raise L1CognitiveRolloutGateError("paired receipt is invalid") from exc
    pair_ids = sorted(
        _nonempty(
            _mapping(pair, label="paired receipt pair").get("pair_id"),
            label="paired pair identity",
        )
        for pair in pairs
    )
    if len(pair_ids) != len(set(pair_ids)):
        raise L1CognitiveRolloutGateError("paired receipt pair identities are invalid")
    completed_pair_count = receipt.get("summary", {}).get("completed_pair_count")
    if completed_pair_count != len(pair_ids):
        raise L1CognitiveRolloutGateError(
            "paired receipt does not contain completed pairs for blinded review"
        )
    paired_runs: dict[str, dict[str, str]] = {}
    for raw_pair in pairs:
        pair = _mapping(raw_pair, label="paired receipt pair")
        pair_id = _nonempty(pair.get("pair_id"), label="paired pair identity")
        control = _mapping(pair.get("control"), label="paired control arm")
        candidate = _mapping(pair.get("candidate"), label="paired candidate arm")
        paired_runs[pair_id] = {
            "control_run_ref": _nonempty(
                control.get("run_ref"), label="paired control run reference"
            ),
            "control_output_digest": _nonempty(
                control.get("output_digest"), label="paired control output digest"
            ),
            "candidate_run_ref": _nonempty(
                candidate.get("run_ref"), label="paired candidate run reference"
            ),
            "candidate_output_digest": _nonempty(
                candidate.get("output_digest"),
                label="paired candidate output digest",
            ),
        }
    return str(receipt["receipt_digest"]), pair_ids, paired_runs


def _verify_blind_material(
    packet_value: Any,
    mapping_value: Any,
    *,
    paired_digest: str,
    paired_pair_ids: Sequence[str],
    paired_runs: Mapping[str, Mapping[str, str]],
) -> tuple[str, str, list[str], dict[str, dict[str, str]]]:
    packet = _mapping(packet_value, label="blind review packet")
    mapping = _mapping(mapping_value, label="blind review mapping")
    if packet.get("schema_version") != L1_COGNITIVE_BLIND_REVIEW_PACKET_SCHEMA_VERSION:
        raise L1CognitiveRolloutGateError("blind review packet schema is invalid")
    if (
        packet.get("app_scope") != _APP_SCOPE
        or packet.get("status") != "PENDING_HUMAN_REVIEW"
    ):
        raise L1CognitiveRolloutGateError("blind review packet status is invalid")
    if packet.get("paired_receipt_digest") != paired_digest:
        raise L1CognitiveRolloutGateError(
            "blind review packet does not bind paired receipt"
        )
    if not _record_digest(packet, field="packet_digest"):
        raise L1CognitiveRolloutGateError("blind review packet digest is invalid")
    if packet.get("authority") != {
        "human_labels_present": False,
        "human_qualified": False,
        "release_authorizing": False,
        "production_authorizing": False,
    }:
        raise L1CognitiveRolloutGateError("blind review packet authority is invalid")
    raw_pairs = packet.get("pairs")
    if (
        not isinstance(raw_pairs, Sequence)
        or isinstance(raw_pairs, (str, bytes))
        or not raw_pairs
    ):
        raise L1CognitiveRolloutGateError("blind review packet pairs are invalid")
    blind_pair_ids: list[str] = []
    packet_variants_by_pair: dict[str, set[str]] = {}
    for raw_pair in raw_pairs:
        pair = _mapping(raw_pair, label="blind review packet pair")
        pair_id = _nonempty(pair.get("blind_pair_id"), label="blind pair identity")
        target = pair.get("target")
        variants = pair.get("variants")
        if (
            not isinstance(target, Mapping)
            or not isinstance(variants, Sequence)
            or isinstance(variants, (str, bytes))
            or len(variants) != 2
        ):
            raise L1CognitiveRolloutGateError(
                "blind review packet pair payload is invalid"
            )
        variant_ids: set[str] = set()
        for raw_variant in variants:
            variant = _mapping(raw_variant, label="blind review packet variant")
            if "arm" in variant:
                raise L1CognitiveRolloutGateError("blind review packet exposes an arm")
            variant_ids.add(
                _nonempty(variant.get("variant_id"), label="blind variant identity")
            )
        if len(variant_ids) != 2:
            raise L1CognitiveRolloutGateError(
                "blind review packet variant identities are invalid"
            )
        blind_pair_ids.append(pair_id)
        packet_variants_by_pair[pair_id] = variant_ids
    blind_pair_ids.sort()
    if len(blind_pair_ids) != len(set(blind_pair_ids)) or len(blind_pair_ids) != len(
        paired_pair_ids
    ):
        raise L1CognitiveRolloutGateError(
            "blind review packet pair identities are invalid"
        )
    if (
        mapping.get("schema_version")
        != L1_COGNITIVE_BLIND_REVIEW_MAPPING_SCHEMA_VERSION
    ):
        raise L1CognitiveRolloutGateError("blind review mapping schema is invalid")
    if mapping.get("app_scope") != _APP_SCOPE:
        raise L1CognitiveRolloutGateError("blind review mapping scope is invalid")
    if mapping.get("distribution") != "SEALED_DO_NOT_SEND_TO_REVIEWERS":
        raise L1CognitiveRolloutGateError(
            "blind review mapping distribution is invalid"
        )
    if mapping.get("paired_receipt_digest") != paired_digest:
        raise L1CognitiveRolloutGateError(
            "blind review mapping does not bind paired receipt"
        )
    mapped_pairs = mapping.get("pairs")
    if not isinstance(mapped_pairs, Sequence) or isinstance(mapped_pairs, (str, bytes)):
        raise L1CognitiveRolloutGateError("blind review mapping pairs are invalid")
    mapped_blind_pair_ids: set[str] = set()
    mapped_source_pair_ids: set[str] = set()
    variant_arms_by_pair: dict[str, dict[str, str]] = {}
    for raw_pair in mapped_pairs:
        pair = _mapping(raw_pair, label="blind review mapping pair")
        blind_pair_id = _nonempty(
            pair.get("blind_pair_id"), label="mapped blind pair identity"
        )
        source_pair_id = _nonempty(
            pair.get("source_pair_id"), label="mapped source pair identity"
        )
        variants = pair.get("variants")
        if (
            not isinstance(variants, Sequence)
            or isinstance(variants, (str, bytes))
            or len(variants) != 2
        ):
            raise L1CognitiveRolloutGateError(
                "blind review mapping variants are invalid"
            )
        mapped_variant_ids: set[str] = set()
        mapped_arms: set[str] = set()
        variant_arms: dict[str, str] = {}
        paired_run = paired_runs.get(source_pair_id)
        if paired_run is None:
            raise L1CognitiveRolloutGateError(
                "blind review mapping source pair is unavailable"
            )
        for raw_variant in variants:
            variant = _mapping(raw_variant, label="blind review mapping variant")
            variant_id = _nonempty(
                variant.get("variant_id"), label="mapped variant identity"
            )
            arm = _nonempty(variant.get("arm"), label="mapped variant arm")
            run_ref = _nonempty(
                variant.get("run_ref"), label="mapped variant run reference"
            )
            output_digest = str(variant.get("output_digest") or "")
            mapped_variant_ids.add(variant_id)
            mapped_arms.add(arm)
            if variant_id in variant_arms or not _digest_is_valid(output_digest):
                raise L1CognitiveRolloutGateError(
                    "mapped variant output digest is invalid"
                )
            expected_run_ref = paired_run.get(f"{arm}_run_ref")
            expected_output_digest = paired_run.get(f"{arm}_output_digest")
            if run_ref != expected_run_ref or output_digest != expected_output_digest:
                raise L1CognitiveRolloutGateError(
                    "blind review mapping does not match paired output provenance"
                )
            variant_arms[variant_id] = arm
        if (
            len(mapped_variant_ids) != 2
            or mapped_arms != {"control", "candidate"}
            or mapped_variant_ids != packet_variants_by_pair.get(blind_pair_id)
        ):
            raise L1CognitiveRolloutGateError(
                "blind review mapping variants are invalid"
            )
        mapped_blind_pair_ids.add(blind_pair_id)
        mapped_source_pair_ids.add(source_pair_id)
        variant_arms_by_pair[blind_pair_id] = variant_arms
    if (
        mapped_blind_pair_ids != set(blind_pair_ids)
        or mapped_source_pair_ids != set(paired_pair_ids)
        or len(mapped_pairs) != len(paired_pair_ids)
    ):
        raise L1CognitiveRolloutGateError(
            "blind review mapping pair bindings are invalid"
        )
    if not _record_digest(mapping, field="mapping_digest"):
        raise L1CognitiveRolloutGateError("blind review mapping digest is invalid")
    return (
        str(packet["packet_digest"]),
        str(mapping["mapping_digest"]),
        blind_pair_ids,
        variant_arms_by_pair,
    )


def _verify_reviewer_record(
    value: Any,
    *,
    packet_digest: str,
    blind_pair_ids: set[str],
    variant_arms_by_pair: Mapping[str, Mapping[str, str]],
) -> tuple[str, str, str]:
    record = _mapping(value, label="human reviewer record")
    required = {
        "reviewer_identity_ref",
        "qualification_ref",
        "independent_review",
        "human_attestation",
        "completed_at",
        "blind_review_packet_digest",
        "blind_pair_id",
        "variant_assessments",
        "record_digest",
    }
    if set(record) != required:
        raise L1CognitiveRolloutGateError("human reviewer record fields are invalid")
    identity = _nonempty(record.get("reviewer_identity_ref"), label="reviewer identity")
    if not identity.startswith("human-reviewer://"):
        raise L1CognitiveRolloutGateError("human reviewer identity is invalid")
    if not _nonempty(
        record.get("qualification_ref"), label="reviewer qualification"
    ).startswith("resume-coach://"):
        raise L1CognitiveRolloutGateError("reviewer qualification is invalid")
    if record.get("independent_review") is not True:
        raise L1CognitiveRolloutGateError("reviewer independence is invalid")
    if record.get("human_attestation") is not True:
        raise L1CognitiveRolloutGateError("human reviewer attestation is required")
    _nonempty(record.get("completed_at"), label="review completion timestamp")
    if record.get("blind_review_packet_digest") != packet_digest:
        raise L1CognitiveRolloutGateError("reviewer record packet binding is invalid")
    pair_id = _nonempty(
        record.get("blind_pair_id"), label="reviewer blind pair identity"
    )
    if pair_id not in blind_pair_ids:
        raise L1CognitiveRolloutGateError(
            "reviewer record blind pair binding is invalid"
        )
    _variant_assessments(
        record.get("variant_assessments"),
        variant_ids=set(variant_arms_by_pair[pair_id]),
        label="reviewer record",
    )
    if not _record_digest(record, field="record_digest"):
        raise L1CognitiveRolloutGateError("reviewer record digest is invalid")
    return pair_id, str(record["record_digest"]), identity


def _verify_human_outcome(
    value: Any,
    *,
    paired_digest: str,
    packet_digest: str,
    mapping_digest: str,
    blind_pair_ids: Sequence[str],
    variant_arms_by_pair: Mapping[str, Mapping[str, str]],
) -> tuple[str, dict[str, int]]:
    outcome = _mapping(value, label="human outcome")
    required = {
        "schema_version",
        "app_scope",
        "status",
        "paired_receipt_digest",
        "blind_review_packet_digest",
        "sealed_mapping_digest",
        "reviewer_evidence",
        "adjudications",
        "adjudicated_measurement_summary",
        "primary_outcomes",
        "record_digest",
    }
    if set(outcome) != required:
        raise L1CognitiveRolloutGateError("human outcome fields are invalid")
    if outcome.get("schema_version") != L1_COGNITIVE_HUMAN_OUTCOME_SCHEMA_VERSION:
        raise L1CognitiveRolloutGateError("human outcome schema is invalid")
    if outcome.get("app_scope") != _APP_SCOPE or outcome.get("status") != "PASS":
        raise L1CognitiveRolloutGateError("human outcome status is invalid")
    if (
        outcome.get("paired_receipt_digest") != paired_digest
        or outcome.get("blind_review_packet_digest") != packet_digest
        or outcome.get("sealed_mapping_digest") != mapping_digest
    ):
        raise L1CognitiveRolloutGateError("human outcome provenance binding is invalid")
    reviews = outcome.get("reviewer_evidence")
    if (
        not isinstance(reviews, Sequence)
        or isinstance(reviews, (str, bytes))
        or len(reviews) != len(blind_pair_ids) * 2
    ):
        raise L1CognitiveRolloutGateError(
            "two independent human reviews per pair are required"
        )
    reviews_by_pair: dict[str, list[tuple[str, str]]] = {
        pair_id: [] for pair_id in blind_pair_ids
    }
    for row in reviews:
        pair_id, digest, identity = _verify_reviewer_record(
            row,
            packet_digest=packet_digest,
            blind_pair_ids=set(blind_pair_ids),
            variant_arms_by_pair=variant_arms_by_pair,
        )
        reviews_by_pair[pair_id].append((digest, identity))
    if any(
        len(records) != 2 or len({identity for _digest, identity in records}) != 2
        for records in reviews_by_pair.values()
    ):
        raise L1CognitiveRolloutGateError("human reviewer quorum is invalid")
    adjudications = outcome.get("adjudications")
    if (
        not isinstance(adjudications, Sequence)
        or isinstance(adjudications, (str, bytes))
        or len(adjudications) != len(blind_pair_ids)
    ):
        raise L1CognitiveRolloutGateError(
            "one independent human adjudication per pair is required"
        )
    adjudicated_pairs: set[str] = set()
    adjudicated_assessments: dict[str, list[dict[str, Any]]] = {}
    required_adjudication = {
        "adjudicator_identity_ref",
        "qualification_ref",
        "human_attestation",
        "completed_at",
        "blind_review_packet_digest",
        "blind_pair_id",
        "reviewer_record_digests",
        "variant_assessments",
        "record_digest",
    }
    for raw_adjudication in adjudications:
        adjudication = _mapping(raw_adjudication, label="human adjudication")
        if set(adjudication) != required_adjudication:
            raise L1CognitiveRolloutGateError("human adjudication fields are invalid")
        pair_id = _nonempty(
            adjudication.get("blind_pair_id"), label="adjudication blind pair identity"
        )
        if pair_id not in reviews_by_pair or pair_id in adjudicated_pairs:
            raise L1CognitiveRolloutGateError(
                "adjudication blind pair binding is invalid"
            )
        adjudicated_pairs.add(pair_id)
        adjudicator = _nonempty(
            adjudication.get("adjudicator_identity_ref"), label="adjudicator identity"
        )
        reviewer_identities = {
            identity for _digest, identity in reviews_by_pair[pair_id]
        }
        if (
            not adjudicator.startswith("human-reviewer://")
            or adjudicator in reviewer_identities
        ):
            raise L1CognitiveRolloutGateError("human adjudicator must be independent")
        if not _nonempty(
            adjudication.get("qualification_ref"), label="adjudicator qualification"
        ).startswith("resume-coach://"):
            raise L1CognitiveRolloutGateError("adjudicator qualification is invalid")
        if adjudication.get("human_attestation") is not True:
            raise L1CognitiveRolloutGateError(
                "human adjudicator attestation is required"
            )
        _nonempty(adjudication.get("completed_at"), label="adjudication timestamp")
        if adjudication.get("blind_review_packet_digest") != packet_digest:
            raise L1CognitiveRolloutGateError("adjudication packet binding is invalid")
        review_digests = [digest for digest, _identity in reviews_by_pair[pair_id]]
        if sorted(adjudication.get("reviewer_record_digests") or []) != sorted(
            review_digests
        ):
            raise L1CognitiveRolloutGateError("adjudication does not bind both reviews")
        assessments = _variant_assessments(
            adjudication.get("variant_assessments"),
            variant_ids=set(variant_arms_by_pair[pair_id]),
            label="human adjudication",
        )
        if not _record_digest(adjudication, field="record_digest"):
            raise L1CognitiveRolloutGateError("adjudication record digest is invalid")
        adjudicated_assessments[pair_id] = assessments
    if set(adjudicated_assessments) != set(blind_pair_ids):
        raise L1CognitiveRolloutGateError("human adjudication coverage is invalid")
    measurements = _adjudicated_measurement_summary(
        assessments_by_pair=adjudicated_assessments,
        variant_arms_by_pair=variant_arms_by_pair,
    )
    if outcome.get("adjudicated_measurement_summary") != measurements:
        raise L1CognitiveRolloutGateError(
            "human outcome adjudicated measurement summary is invalid"
        )
    if outcome.get("primary_outcomes") != _primary_outcomes_from_measurements(
        measurements
    ):
        raise L1CognitiveRolloutGateError("human outcome primary measures are invalid")
    if not _record_digest(outcome, field="record_digest"):
        raise L1CognitiveRolloutGateError("human outcome digest is invalid")
    return str(outcome["record_digest"]), measurements


def _verify_holdout_outcome(
    value: Any,
    *,
    paired_digest: str,
    packet_digest: str,
    human_outcome_digest: str,
    human_measurements: Mapping[str, int],
) -> tuple[str, dict[str, str], dict[str, int]]:
    outcome = _mapping(value, label="protected holdout outcome")
    required = {
        "schema_version",
        "app_scope",
        "status",
        "protected_holdout_commitment_ref",
        "protected_holdout_commitment_digest",
        "paired_receipt_digest",
        "blind_review_packet_digest",
        "human_outcome_digest",
        "adjudicated_measurement_summary",
        "primary_outcomes",
        "guardrails",
        "external_seal",
        "authority",
        "record_digest",
    }
    if set(outcome) != required:
        raise L1CognitiveRolloutGateError(
            "protected holdout outcome fields are invalid"
        )
    if (
        outcome.get("schema_version")
        != L1_COGNITIVE_PROTECTED_HOLDOUT_OUTCOME_SCHEMA_VERSION
    ):
        raise L1CognitiveRolloutGateError("protected holdout outcome schema is invalid")
    if outcome.get("app_scope") != _APP_SCOPE or outcome.get("status") != "PASS":
        raise L1CognitiveRolloutGateError("protected holdout outcome status is invalid")
    if outcome.get("protected_holdout_commitment_ref") != _HOLDOUT_COMMITMENT_REF:
        raise L1CognitiveRolloutGateError(
            "protected holdout commitment reference is invalid"
        )
    if (
        outcome.get("protected_holdout_commitment_digest")
        != _load_holdout_commitment_digest()
    ):
        raise L1CognitiveRolloutGateError(
            "protected holdout commitment binding is invalid"
        )
    if (
        outcome.get("paired_receipt_digest") != paired_digest
        or outcome.get("blind_review_packet_digest") != packet_digest
        or outcome.get("human_outcome_digest") != human_outcome_digest
    ):
        raise L1CognitiveRolloutGateError(
            "protected holdout outcome provenance is invalid"
        )
    measurements = dict(human_measurements)
    if outcome.get("adjudicated_measurement_summary") != measurements:
        raise L1CognitiveRolloutGateError(
            "protected holdout adjudicated measurement summary is invalid"
        )
    primary_outcomes = _primary_outcomes_from_measurements(measurements)
    if outcome.get("primary_outcomes") != primary_outcomes:
        raise L1CognitiveRolloutGateError(
            "protected holdout primary outcomes are invalid"
        )
    raw_guardrails = outcome.get("guardrails")
    if not isinstance(raw_guardrails, Mapping) or set(raw_guardrails) != set(
        _GUARDRAIL_FIELDS
    ):
        raise L1CognitiveRolloutGateError("protected holdout guardrails are invalid")
    guardrails = {
        field: _nonnegative_int(
            raw_guardrails.get(field), label=f"protected holdout {field}"
        )
        for field in _GUARDRAIL_FIELDS
    }
    if (
        guardrails["unsupported_material_claim_count"]
        != measurements["candidate_unsupported_material_claim_count"]
    ):
        raise L1CognitiveRolloutGateError(
            "protected holdout unsupported-claim count is not adjudication-bound"
        )
    seal = _mapping(outcome.get("external_seal"), label="external holdout seal")
    if seal.get("verified") is not True or not _nonempty(
        seal.get("verification_ref"), label="holdout seal reference"
    ).startswith("human-eval-authority://"):
        raise L1CognitiveRolloutGateError("external holdout seal is invalid")
    _nonempty(seal.get("verified_at"), label="holdout seal timestamp")
    authority = outcome.get("authority")
    if authority != {
        "human_qualified": True,
        "release_authorizing": False,
        "production_authorizing": False,
        "automatic_promotion": False,
    }:
        raise L1CognitiveRolloutGateError("protected holdout authority is invalid")
    if not _record_digest(outcome, field="record_digest"):
        raise L1CognitiveRolloutGateError("protected holdout outcome digest is invalid")
    return str(outcome["record_digest"]), primary_outcomes, guardrails


def _verify_rollout_plan(value: Any) -> str:
    plan = _mapping(value, label="rollout plan")
    if plan.get("schema_version") != L1_COGNITIVE_ROLLOUT_PLAN_SCHEMA_VERSION:
        raise L1CognitiveRolloutGateError("rollout plan schema is invalid")
    if plan.get("app_scope") != _APP_SCOPE:
        raise L1CognitiveRolloutGateError("rollout plan scope is invalid")
    scope = _mapping(plan.get("scope"), label="rollout plan scope")
    if (
        scope.get("treatment_id") != "l1_cognitive_v3"
        or not isinstance(scope.get("max_candidate_runs"), int)
        or not 1 <= int(scope["max_candidate_runs"]) <= 10
    ):
        raise L1CognitiveRolloutGateError("rollout scope is not bounded")
    _nonempty(scope.get("expires_at"), label="rollout expiry")
    observation = plan.get("observation")
    if observation != {
        "requirement_level_observation": True,
        "c0_outcome_observation": True,
        "output_disposition_observation": True,
    }:
        raise L1CognitiveRolloutGateError("rollout observation plan is invalid")
    rollback = _mapping(plan.get("rollback"), label="rollout rollback plan")
    triggers = rollback.get("trigger_refs")
    if (
        rollback.get("enabled") is not True
        or rollback.get("fallback_treatment") != "l1_v2_control"
        or not isinstance(triggers, Sequence)
        or isinstance(triggers, (str, bytes))
        or not triggers
        or any(not str(trigger).strip() for trigger in triggers)
    ):
        raise L1CognitiveRolloutGateError("rollout rollback plan is invalid")
    if not _record_digest(plan, field="plan_digest"):
        raise L1CognitiveRolloutGateError("rollout plan digest is invalid")
    return str(plan["plan_digest"])


def _verify_release_approval(
    value: Any, *, holdout_digest: str, capability_digest: str, plan_digest: str
) -> str:
    approval = _mapping(value, label="release approval")
    if set(approval) != {
        "schema_version",
        "app_scope",
        "status",
        "approver_identity_ref",
        "human_attestation",
        "approved_at",
        "protected_holdout_outcome_digest",
        "cognitive_capability_outcome_digest",
        "rollout_plan_digest",
        "approval_digest",
    }:
        raise L1CognitiveRolloutGateError("release approval fields are invalid")
    if approval.get("schema_version") != L1_COGNITIVE_RELEASE_APPROVAL_SCHEMA_VERSION:
        raise L1CognitiveRolloutGateError("release approval schema is invalid")
    if approval.get("app_scope") != _APP_SCOPE or approval.get("status") != "APPROVED":
        raise L1CognitiveRolloutGateError("release approval status is invalid")
    approver = _nonempty(
        approval.get("approver_identity_ref"), label="release approver"
    )
    if (
        not approver.startswith("human-release://")
        or approval.get("human_attestation") is not True
    ):
        raise L1CognitiveRolloutGateError("release approval must be human-attested")
    _nonempty(approval.get("approved_at"), label="release approval timestamp")
    if (
        approval.get("protected_holdout_outcome_digest") != holdout_digest
        or approval.get("cognitive_capability_outcome_digest") != capability_digest
        or approval.get("rollout_plan_digest") != plan_digest
    ):
        raise L1CognitiveRolloutGateError("release approval provenance is invalid")
    if not _record_digest(approval, field="approval_digest"):
        raise L1CognitiveRolloutGateError("release approval digest is invalid")
    return str(approval["approval_digest"])


def build_l1_cognitive_rollout_gate(
    *,
    paired_receipt: Mapping[str, Any] | None = None,
    paired_cohort_manifest: Mapping[str, Any] | None = None,
    blind_review_packet: Mapping[str, Any] | None = None,
    sealed_mapping: Mapping[str, Any] | None = None,
    human_outcome: Mapping[str, Any] | None = None,
    cognitive_capability_outcome: Mapping[str, Any] | None = None,
    protected_holdout_outcome: Mapping[str, Any] | None = None,
    rollout_plan: Mapping[str, Any] | None = None,
    release_approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate W6 readiness without creating evidence or activating a rollout."""

    failure_codes: list[str] = []
    verified: dict[str, str] = {
        "paired_receipt_digest": "",
        "paired_cohort_manifest_digest": "",
        "blind_review_packet_digest": "",
        "sealed_mapping_digest": "",
        "human_outcome_digest": "",
        "cognitive_capability_outcome_digest": "",
        "protected_holdout_outcome_digest": "",
        "rollout_plan_digest": "",
        "release_approval_digest": "",
    }
    blind_pair_ids: list[str] = []
    paired_runs: dict[str, dict[str, str]] = {}
    variant_arms_by_pair: dict[str, dict[str, str]] = {}
    human_measurements: dict[str, int] = {}
    cognitive_capability_measurements: dict[str, Any] = {}
    cognitive_capability_outcomes: dict[str, str] = {}
    holdout_primary_outcomes: dict[str, str] = {}
    holdout_guardrails: dict[str, int] = {}
    try:
        paired_digest, paired_pair_ids, paired_runs = _verify_paired_receipt(
            paired_receipt
        )
        verified["paired_receipt_digest"] = paired_digest
    except L1CognitiveRolloutGateError:
        failure_codes.append("PAIRED_EXECUTION_EVIDENCE_INVALID_OR_MISSING")
        paired_pair_ids = []
    if verified["paired_receipt_digest"]:
        try:
            validate_l1_cognitive_paired_cohort_manifest(
                _mapping(
                    paired_cohort_manifest,
                    label="paired cohort manifest",
                ),
                paired_receipt=_mapping(paired_receipt, label="paired receipt"),
                protocol=load_l1_cognitive_outcome_protocol(),
            )
            verified["paired_cohort_manifest_digest"] = str(
                paired_cohort_manifest["cohort_digest"]
            )
        except (L1CognitiveRolloutGateError, ValueError, TypeError):
            failure_codes.append("PROTECTED_HOLDOUT_COHORT_INVALID_OR_MISSING")
    else:
        failure_codes.append("PROTECTED_HOLDOUT_COHORT_UNVERIFIABLE")
    if verified["paired_receipt_digest"] and verified["paired_cohort_manifest_digest"]:
        try:
            (
                packet_digest,
                mapping_digest,
                blind_pair_ids,
                variant_arms_by_pair,
            ) = _verify_blind_material(
                blind_review_packet,
                sealed_mapping,
                paired_digest=verified["paired_receipt_digest"],
                paired_pair_ids=paired_pair_ids,
                paired_runs=paired_runs,
            )
            verified["blind_review_packet_digest"] = packet_digest
            verified["sealed_mapping_digest"] = mapping_digest
        except L1CognitiveRolloutGateError:
            failure_codes.append("BLINDED_REVIEW_MATERIAL_INVALID_OR_MISSING")
    else:
        failure_codes.append("BLINDED_REVIEW_MATERIAL_UNVERIFIABLE")
    if verified["paired_receipt_digest"] and verified["paired_cohort_manifest_digest"]:
        try:
            capability_evidence = validate_l1_cognitive_capability_outcome(
                _mapping(
                    cognitive_capability_outcome, label="cognitive capability outcome"
                ),
                paired_receipt=_mapping(paired_receipt, label="paired receipt"),
            )
            verified["cognitive_capability_outcome_digest"] = str(
                capability_evidence["record_digest"]
            )
            cognitive_capability_measurements = dict(
                capability_evidence["capability_measurement_summary"]
            )
            cognitive_capability_outcomes = dict(
                capability_evidence["capability_outcomes"]
            )
        except (L1CognitiveRolloutGateError, ValueError):
            failure_codes.append("COGNITIVE_CAPABILITY_OUTCOME_INVALID_OR_MISSING")
    else:
        failure_codes.append("COGNITIVE_CAPABILITY_OUTCOME_UNVERIFIABLE")
    if verified["cognitive_capability_outcome_digest"] and any(
        cognitive_capability_outcomes.get(dimension) != "IMPROVED"
        for dimension in L1_COGNITIVE_CAPABILITY_DIMENSIONS
    ):
        failure_codes.append("COGNITIVE_CAPABILITY_OUTCOMES_NOT_IMPROVED")
    if verified["blind_review_packet_digest"] and verified["sealed_mapping_digest"]:
        try:
            verified["human_outcome_digest"], human_measurements = (
                _verify_human_outcome(
                    human_outcome,
                    paired_digest=verified["paired_receipt_digest"],
                    packet_digest=verified["blind_review_packet_digest"],
                    mapping_digest=verified["sealed_mapping_digest"],
                    blind_pair_ids=blind_pair_ids,
                    variant_arms_by_pair=variant_arms_by_pair,
                )
            )
        except L1CognitiveRolloutGateError:
            failure_codes.append("INDEPENDENT_HUMAN_REVIEW_INVALID_OR_MISSING")
    else:
        failure_codes.append("INDEPENDENT_HUMAN_REVIEW_UNVERIFIABLE")
    if verified["human_outcome_digest"]:
        try:
            (
                verified["protected_holdout_outcome_digest"],
                holdout_primary_outcomes,
                holdout_guardrails,
            ) = _verify_holdout_outcome(
                protected_holdout_outcome,
                paired_digest=verified["paired_receipt_digest"],
                packet_digest=verified["blind_review_packet_digest"],
                human_outcome_digest=verified["human_outcome_digest"],
                human_measurements=human_measurements,
            )
        except L1CognitiveRolloutGateError:
            failure_codes.append("PROTECTED_HOLDOUT_OUTCOME_INVALID_OR_MISSING")
    else:
        failure_codes.append("PROTECTED_HOLDOUT_OUTCOME_UNVERIFIABLE")
    if verified["protected_holdout_outcome_digest"]:
        if holdout_primary_outcomes != {"P1": "IMPROVED", "P2": "IMPROVED"}:
            failure_codes.append("PROTECTED_HOLDOUT_PRIMARY_OUTCOMES_NOT_IMPROVED")
        if any(holdout_guardrails.get(field) != 0 for field in _GUARDRAIL_FIELDS):
            failure_codes.append("PROTECTED_HOLDOUT_GUARDRAIL_REGRESSION")
    try:
        verified["rollout_plan_digest"] = _verify_rollout_plan(rollout_plan)
    except L1CognitiveRolloutGateError:
        failure_codes.append("BOUNDED_ROLLOUT_AND_ROLLBACK_PLAN_INVALID_OR_MISSING")
    if (
        verified["protected_holdout_outcome_digest"]
        and verified["cognitive_capability_outcome_digest"]
        and verified["rollout_plan_digest"]
    ):
        try:
            verified["release_approval_digest"] = _verify_release_approval(
                release_approval,
                holdout_digest=verified["protected_holdout_outcome_digest"],
                capability_digest=verified["cognitive_capability_outcome_digest"],
                plan_digest=verified["rollout_plan_digest"],
            )
        except L1CognitiveRolloutGateError:
            failure_codes.append("NAMED_HUMAN_RELEASE_APPROVAL_INVALID_OR_MISSING")
    else:
        failure_codes.append("NAMED_HUMAN_RELEASE_APPROVAL_UNVERIFIABLE")
    failure_codes = sorted(set(failure_codes))
    status = (
        "READY_FOR_HUMAN_OPERATED_LIMITED_ROLLOUT" if not failure_codes else "BLOCKED"
    )
    receipt: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_ROLLOUT_GATE_SCHEMA_VERSION,
        "app_scope": _APP_SCOPE,
        "status": status,
        "verified_evidence": verified,
        "outcome_observations": {
            "adjudicated_measurement_summary": human_measurements,
            "primary_outcomes": holdout_primary_outcomes,
            "guardrails": holdout_guardrails,
            "cognitive_capability_measurement_summary": cognitive_capability_measurements,
            "cognitive_capability_outcomes": cognitive_capability_outcomes,
        },
        "failure_codes": failure_codes,
        "authority": {
            "technical_readiness_verification_only": True,
            "automatic_promotion": False,
            "runtime_activation_performed": False,
            "release_authorizing": False,
            "production_authorizing": False,
            "human_operated_rollout_required": True,
        },
        "receipt_digest": "",
    }
    receipt["receipt_digest"] = rollout_gate_digest(receipt)
    return receipt


def validate_l1_cognitive_rollout_gate(
    receipt: Mapping[str, Any],
    **sources: Mapping[str, Any] | None,
) -> None:
    """Re-derive and validate a W6 readiness receipt from its supplied sources."""

    if not isinstance(receipt, Mapping):
        raise L1CognitiveRolloutGateError("rollout gate receipt is invalid")
    if receipt.get("schema_version") != L1_COGNITIVE_ROLLOUT_GATE_SCHEMA_VERSION:
        raise L1CognitiveRolloutGateError("rollout gate receipt schema is invalid")
    if receipt.get("receipt_digest") != rollout_gate_digest(receipt):
        raise L1CognitiveRolloutGateError("rollout gate receipt digest is invalid")
    expected = build_l1_cognitive_rollout_gate(**sources)
    if dict(receipt) != expected:
        raise L1CognitiveRolloutGateError(
            "rollout gate receipt does not match its sources"
        )


__all__ = [
    "L1CognitiveRolloutGateError",
    "L1_COGNITIVE_HUMAN_OUTCOME_SCHEMA_VERSION",
    "L1_COGNITIVE_PROTECTED_HOLDOUT_OUTCOME_SCHEMA_VERSION",
    "L1_COGNITIVE_RELEASE_APPROVAL_SCHEMA_VERSION",
    "L1_COGNITIVE_ROLLOUT_GATE_SCHEMA_VERSION",
    "L1_COGNITIVE_ROLLOUT_PLAN_SCHEMA_VERSION",
    "build_l1_cognitive_rollout_gate",
    "rollout_gate_digest",
    "seal_l1_cognitive_handoff_record",
    "validate_l1_cognitive_rollout_gate",
]
