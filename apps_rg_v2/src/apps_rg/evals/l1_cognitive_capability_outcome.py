"""Validate human-governed protected evidence for the five L1 capabilities.

The validator records no judgment. It checks that independently authored human
reviews and adjudications are tied to the exact paired L1 source artifacts,
then re-derives whether candidate scores exceed control scores for the cognitive
capabilities the roadmap requires.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.evals.l1_cognitive_calibration import holdout_commitment_path
from apps_rg.evals.l1_cognitive_outcome_protocol import (
    load_l1_cognitive_outcome_protocol,
    validate_l1_cognitive_paired_shadow_receipt,
)


L1_COGNITIVE_CAPABILITY_OUTCOME_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_capability_outcome.v2"
)
L1_COGNITIVE_CAPABILITY_DIMENSIONS: Final[tuple[str, ...]] = (
    "goal_constraint_fidelity",
    "atomic_requirement_fidelity",
    "feasibility_plan_coherence",
    "critique_quality",
    "revision_quality",
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_HOLDOUT_COMMITMENT_REF: Final[str] = (
    "apps_rg/evals/fixtures/l1_v2_protected_holdout_commitment.v1.json"
)


class L1CognitiveCapabilityOutcomeError(ValueError):
    """Raised when a capability outcome is not source-bound human evidence."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def capability_outcome_digest(value: Mapping[str, Any]) -> str:
    """Return the canonical digest excluding the outcome self-reference."""

    body = dict(value)
    body.pop("record_digest", None)
    return _sha256(body)


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise L1CognitiveCapabilityOutcomeError(f"{label} is invalid")
    return dict(value)


def _nonempty(value: Any, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1CognitiveCapabilityOutcomeError(f"{label} is required")
    return normalized


def _digest(value: Any, *, label: str) -> str:
    normalized = _nonempty(value, label=label)
    if not normalized.startswith("sha256:") or len(normalized) != len("sha256:") + 64:
        raise L1CognitiveCapabilityOutcomeError(f"{label} is invalid")
    return normalized


def _nonnegative_score(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2:
        raise L1CognitiveCapabilityOutcomeError(f"{label} is invalid")
    return value


def _record_digest(value: Mapping[str, Any]) -> bool:
    return value.get("record_digest") == capability_outcome_digest(value)


def _holdout_commitments() -> tuple[str, dict[str, str]]:
    """Load and validate opaque holdout identities without opening cases."""

    path = Path(holdout_commitment_path())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1CognitiveCapabilityOutcomeError(
            "protected holdout commitment is unreadable"
        ) from exc
    if not isinstance(payload, Mapping):
        raise L1CognitiveCapabilityOutcomeError(
            "protected holdout commitment is invalid"
        )
    commitment = dict(payload)
    if (
        commitment.get("schema_version")
        != "apps_rg.l1_v2_protected_holdout_commitment.v1"
        or commitment.get("app_scope") != _APP_SCOPE
        or commitment.get("development_access") != "DENIED"
        or commitment.get("external_seal_required") is not True
        or commitment.get("promotion_requires_external_holdout_results") is not True
    ):
        raise L1CognitiveCapabilityOutcomeError(
            "protected holdout commitment is invalid"
        )
    commitment_digest = _digest(
        commitment.get("commitment_digest"),
        label="protected holdout commitment digest",
    )
    expected_digest = _sha256(
        {key: item for key, item in commitment.items() if key != "commitment_digest"}
    )
    if commitment_digest != expected_digest:
        raise L1CognitiveCapabilityOutcomeError(
            "protected holdout commitment digest is invalid"
        )
    raw_cases = commitment.get("commitments")
    if (
        not isinstance(raw_cases, Sequence)
        or isinstance(raw_cases, (str, bytes))
        or not raw_cases
    ):
        raise L1CognitiveCapabilityOutcomeError(
            "protected holdout commitments are invalid"
        )
    commitments: dict[str, str] = {}
    for raw_case in raw_cases:
        case = _mapping(raw_case, label="protected holdout case")
        fixture_id = _nonempty(
            case.get("fixture_id"), label="protected holdout fixture identity"
        )
        source_input_digest = _digest(
            case.get("source_input_digest"),
            label="protected holdout source input digest",
        )
        if fixture_id in commitments:
            raise L1CognitiveCapabilityOutcomeError(
                "protected holdout fixture identities are invalid"
            )
        commitments[fixture_id] = source_input_digest
    return commitment_digest, commitments


def _pair_source_bindings(
    paired_receipt: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    pairs = paired_receipt.get("pairs")
    if not isinstance(pairs, Sequence) or isinstance(pairs, (str, bytes)) or not pairs:
        raise L1CognitiveCapabilityOutcomeError("paired receipt pairs are invalid")
    bindings: dict[str, dict[str, str]] = {}
    for raw_pair in pairs:
        pair = _mapping(raw_pair, label="paired receipt pair")
        pair_id = _nonempty(pair.get("pair_id"), label="source pair identity")
        control = _mapping(pair.get("control"), label="paired control arm")
        candidate = _mapping(pair.get("candidate"), label="paired candidate arm")
        if pair_id in bindings:
            raise L1CognitiveCapabilityOutcomeError(
                "source pair identities are invalid"
            )
        bindings[pair_id] = {
            "frozen_input_digest": _digest(
                pair.get("frozen_input_digest"), label="paired frozen input digest"
            ),
            "control_l1_v2_capsule_digest": _digest(
                control.get("l1_v2_capsule_digest"),
                label="paired control L1 v2 capsule digest",
            ),
            "candidate_l1_cognitive_plan_digest": _digest(
                candidate.get("l1_cognitive_plan_digest"),
                label="paired candidate cognitive plan digest",
            ),
            "candidate_l1_cognitive_revision_set_digest": _digest(
                candidate.get("l1_cognitive_revision_set_digest"),
                label="paired candidate revision-set digest",
            ),
        }
    return bindings


def _holdout_case_binding_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("binding_digest", None)
    return _sha256(body)


def _verify_holdout_case_bindings(
    value: Any,
    *,
    commitments: Mapping[str, str],
    bindings_by_pair: Mapping[str, Mapping[str, str]],
) -> None:
    """Bind every opaque committed case to one captured frozen input.

    Apps RG cannot open the protected case contents.  A qualified external
    authority therefore attests to the bridge from each opaque source-input
    digest to the Apps-local frozen-input digest.  The validator requires a
    complete one-to-one cohort so a favorable subset cannot be presented as the
    sealed holdout result.
    """

    raw_bindings = value
    if (
        not isinstance(raw_bindings, Sequence)
        or isinstance(raw_bindings, (str, bytes))
        or len(raw_bindings) != len(commitments)
        or len(raw_bindings) != len(bindings_by_pair)
    ):
        raise L1CognitiveCapabilityOutcomeError(
            "protected holdout case binding coverage is invalid"
        )
    seen_pairs: set[str] = set()
    seen_fixtures: set[str] = set()
    required = {
        "source_pair_id",
        "fixture_id",
        "source_input_digest",
        "frozen_input_digest",
        "verifier_identity_ref",
        "human_attestation",
        "verified_at",
        "verification_ref",
        "binding_digest",
    }
    for raw_binding in raw_bindings:
        binding = _mapping(raw_binding, label="protected holdout case binding")
        if set(binding) != required:
            raise L1CognitiveCapabilityOutcomeError(
                "protected holdout case binding fields are invalid"
            )
        pair_id = _nonempty(
            binding.get("source_pair_id"),
            label="protected holdout source pair identity",
        )
        fixture_id = _nonempty(
            binding.get("fixture_id"), label="protected holdout fixture identity"
        )
        expected_binding = bindings_by_pair.get(pair_id)
        expected_source_digest = commitments.get(fixture_id)
        if (
            pair_id in seen_pairs
            or fixture_id in seen_fixtures
            or expected_binding is None
            or expected_source_digest is None
            or binding.get("source_input_digest") != expected_source_digest
            or binding.get("frozen_input_digest")
            != expected_binding.get("frozen_input_digest")
        ):
            raise L1CognitiveCapabilityOutcomeError(
                "protected holdout case binding is invalid"
            )
        verifier = _nonempty(
            binding.get("verifier_identity_ref"),
            label="protected holdout case verifier",
        )
        verification_ref = _nonempty(
            binding.get("verification_ref"),
            label="protected holdout case verification reference",
        )
        if (
            not verifier.startswith("human-eval-authority://")
            or not verification_ref.startswith("human-eval-authority://")
            or binding.get("human_attestation") is not True
        ):
            raise L1CognitiveCapabilityOutcomeError(
                "protected holdout case verifier is invalid"
            )
        _nonempty(
            binding.get("verified_at"),
            label="protected holdout case verification timestamp",
        )
        if binding.get("binding_digest") != _holdout_case_binding_digest(binding):
            raise L1CognitiveCapabilityOutcomeError(
                "protected holdout case binding digest is invalid"
            )
        seen_pairs.add(pair_id)
        seen_fixtures.add(fixture_id)
    if seen_pairs != set(bindings_by_pair) or seen_fixtures != set(commitments):
        raise L1CognitiveCapabilityOutcomeError(
            "protected holdout case binding coverage is invalid"
        )


def _capability_scores(value: Any, *, label: str) -> dict[str, dict[str, int]]:
    scores = _mapping(value, label=f"{label} capability scores")
    if set(scores) != set(L1_COGNITIVE_CAPABILITY_DIMENSIONS):
        raise L1CognitiveCapabilityOutcomeError(
            f"{label} capability dimensions are invalid"
        )
    normalized: dict[str, dict[str, int]] = {}
    for dimension in L1_COGNITIVE_CAPABILITY_DIMENSIONS:
        pair = _mapping(scores[dimension], label=f"{label} {dimension} scores")
        if set(pair) != {"control", "candidate"}:
            raise L1CognitiveCapabilityOutcomeError(
                f"{label} {dimension} score fields are invalid"
            )
        normalized[dimension] = {
            "control": _nonnegative_score(
                pair.get("control"), label=f"{label} {dimension} control score"
            ),
            "candidate": _nonnegative_score(
                pair.get("candidate"), label=f"{label} {dimension} candidate score"
            ),
        }
    return normalized


def _verify_reviewer_record(
    value: Any,
    *,
    paired_digest: str,
    bindings_by_pair: Mapping[str, Mapping[str, str]],
) -> tuple[str, str, str]:
    record = _mapping(value, label="capability reviewer record")
    required = {
        "reviewer_identity_ref",
        "qualification_ref",
        "independent_review",
        "human_attestation",
        "completed_at",
        "paired_receipt_digest",
        "source_pair_id",
        "source_bindings",
        "capability_scores",
        "record_digest",
    }
    if set(record) != required:
        raise L1CognitiveCapabilityOutcomeError(
            "capability reviewer fields are invalid"
        )
    identity = _nonempty(
        record.get("reviewer_identity_ref"), label="capability reviewer"
    )
    if not identity.startswith("human-reviewer://"):
        raise L1CognitiveCapabilityOutcomeError(
            "capability reviewer identity is invalid"
        )
    if not _nonempty(
        record.get("qualification_ref"), label="capability reviewer qualification"
    ).startswith("resume-coach://"):
        raise L1CognitiveCapabilityOutcomeError(
            "capability reviewer qualification is invalid"
        )
    if (
        record.get("independent_review") is not True
        or record.get("human_attestation") is not True
    ):
        raise L1CognitiveCapabilityOutcomeError(
            "capability reviewer attestation is invalid"
        )
    _nonempty(record.get("completed_at"), label="capability review timestamp")
    if record.get("paired_receipt_digest") != paired_digest:
        raise L1CognitiveCapabilityOutcomeError(
            "capability reviewer paired binding is invalid"
        )
    pair_id = _nonempty(record.get("source_pair_id"), label="capability source pair")
    expected_bindings = bindings_by_pair.get(pair_id)
    if expected_bindings is None or record.get("source_bindings") != expected_bindings:
        raise L1CognitiveCapabilityOutcomeError(
            "capability reviewer source binding is invalid"
        )
    _capability_scores(record.get("capability_scores"), label="capability reviewer")
    if not _record_digest(record):
        raise L1CognitiveCapabilityOutcomeError("capability reviewer digest is invalid")
    return pair_id, str(record["record_digest"]), identity


def _measurement_summary(
    scores_by_pair: Mapping[str, Mapping[str, Mapping[str, int]]],
) -> dict[str, Any]:
    dimensions: dict[str, dict[str, int]] = {}
    for dimension in L1_COGNITIVE_CAPABILITY_DIMENSIONS:
        dimensions[dimension] = {
            "control_score_sum": sum(
                scores_by_pair[pair_id][dimension]["control"]
                for pair_id in sorted(scores_by_pair)
            ),
            "candidate_score_sum": sum(
                scores_by_pair[pair_id][dimension]["candidate"]
                for pair_id in sorted(scores_by_pair)
            ),
        }
    return {"pair_count": len(scores_by_pair), "dimensions": dimensions}


def _capability_outcomes(summary: Mapping[str, Any]) -> dict[str, str]:
    dimensions = _mapping(
        summary.get("dimensions"), label="capability summary dimensions"
    )
    outcomes: dict[str, str] = {}
    for dimension in L1_COGNITIVE_CAPABILITY_DIMENSIONS:
        scores = _mapping(dimensions.get(dimension), label=f"{dimension} summary")
        outcomes[dimension] = (
            "IMPROVED"
            if scores.get("candidate_score_sum") > scores.get("control_score_sum")
            else "NOT_IMPROVED"
        )
    return outcomes


def validate_l1_cognitive_capability_outcome(
    value: Mapping[str, Any], *, paired_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate human semantic evidence and return its re-derived measurements."""

    outcome = _mapping(value, label="cognitive capability outcome")
    required = {
        "schema_version",
        "app_scope",
        "status",
        "protected_holdout_commitment_ref",
        "protected_holdout_commitment_digest",
        "paired_receipt_digest",
        "holdout_case_bindings",
        "reviewer_evidence",
        "adjudications",
        "capability_measurement_summary",
        "capability_outcomes",
        "external_seal",
        "authority",
        "record_digest",
    }
    if set(outcome) != required:
        raise L1CognitiveCapabilityOutcomeError("capability outcome fields are invalid")
    if outcome.get("schema_version") != L1_COGNITIVE_CAPABILITY_OUTCOME_SCHEMA_VERSION:
        raise L1CognitiveCapabilityOutcomeError("capability outcome schema is invalid")
    if outcome.get("app_scope") != _APP_SCOPE or outcome.get("status") != "PASS":
        raise L1CognitiveCapabilityOutcomeError("capability outcome status is invalid")
    if outcome.get("protected_holdout_commitment_ref") != _HOLDOUT_COMMITMENT_REF:
        raise L1CognitiveCapabilityOutcomeError(
            "capability holdout reference is invalid"
        )
    commitment_digest, commitments = _holdout_commitments()
    if outcome.get("protected_holdout_commitment_digest") != commitment_digest:
        raise L1CognitiveCapabilityOutcomeError("capability holdout binding is invalid")
    source_pairs = paired_receipt.get("pairs")
    if not isinstance(source_pairs, Sequence) or isinstance(source_pairs, (str, bytes)):
        raise L1CognitiveCapabilityOutcomeError("paired receipt pairs are invalid")
    try:
        validate_l1_cognitive_paired_shadow_receipt(
            paired_receipt,
            protocol=load_l1_cognitive_outcome_protocol(),
            pairs=source_pairs,
        )
    except ValueError as exc:
        raise L1CognitiveCapabilityOutcomeError("paired receipt is invalid") from exc
    paired_digest = _digest(
        paired_receipt.get("receipt_digest"), label="paired receipt digest"
    )
    if outcome.get("paired_receipt_digest") != paired_digest:
        raise L1CognitiveCapabilityOutcomeError("capability paired binding is invalid")
    bindings_by_pair = _pair_source_bindings(paired_receipt)
    _verify_holdout_case_bindings(
        outcome.get("holdout_case_bindings"),
        commitments=commitments,
        bindings_by_pair=bindings_by_pair,
    )
    reviews = outcome.get("reviewer_evidence")
    if (
        not isinstance(reviews, Sequence)
        or isinstance(reviews, (str, bytes))
        or len(reviews) != len(bindings_by_pair) * 2
    ):
        raise L1CognitiveCapabilityOutcomeError(
            "two capability reviews per source pair are required"
        )
    reviews_by_pair: dict[str, list[tuple[str, str]]] = {
        pair_id: [] for pair_id in bindings_by_pair
    }
    for raw_review in reviews:
        pair_id, digest, identity = _verify_reviewer_record(
            raw_review,
            paired_digest=paired_digest,
            bindings_by_pair=bindings_by_pair,
        )
        reviews_by_pair[pair_id].append((digest, identity))
    if any(
        len(records) != 2 or len({identity for _digest, identity in records}) != 2
        for records in reviews_by_pair.values()
    ):
        raise L1CognitiveCapabilityOutcomeError("capability reviewer quorum is invalid")
    adjudications = outcome.get("adjudications")
    if (
        not isinstance(adjudications, Sequence)
        or isinstance(adjudications, (str, bytes))
        or len(adjudications) != len(bindings_by_pair)
    ):
        raise L1CognitiveCapabilityOutcomeError(
            "one capability adjudication per source pair is required"
        )
    adjudicated_scores: dict[str, dict[str, dict[str, int]]] = {}
    required_adjudication = {
        "adjudicator_identity_ref",
        "qualification_ref",
        "human_attestation",
        "completed_at",
        "paired_receipt_digest",
        "source_pair_id",
        "source_bindings",
        "reviewer_record_digests",
        "capability_scores",
        "record_digest",
    }
    for raw_adjudication in adjudications:
        adjudication = _mapping(raw_adjudication, label="capability adjudication")
        if set(adjudication) != required_adjudication:
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudication fields are invalid"
            )
        pair_id = _nonempty(
            adjudication.get("source_pair_id"), label="capability adjudication pair"
        )
        if pair_id not in reviews_by_pair or pair_id in adjudicated_scores:
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudication pair binding is invalid"
            )
        adjudicator = _nonempty(
            adjudication.get("adjudicator_identity_ref"), label="capability adjudicator"
        )
        reviewer_identities = {
            identity for _digest, identity in reviews_by_pair[pair_id]
        }
        if (
            not adjudicator.startswith("human-reviewer://")
            or adjudicator in reviewer_identities
        ):
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudicator independence is invalid"
            )
        if not _nonempty(
            adjudication.get("qualification_ref"),
            label="capability adjudicator qualification",
        ).startswith("resume-coach://"):
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudicator qualification is invalid"
            )
        if adjudication.get("human_attestation") is not True:
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudicator attestation is invalid"
            )
        _nonempty(
            adjudication.get("completed_at"), label="capability adjudication timestamp"
        )
        if adjudication.get("paired_receipt_digest") != paired_digest:
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudication paired binding is invalid"
            )
        if adjudication.get("source_bindings") != bindings_by_pair[pair_id]:
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudication source binding is invalid"
            )
        review_digests = [digest for digest, _identity in reviews_by_pair[pair_id]]
        if sorted(adjudication.get("reviewer_record_digests") or []) != sorted(
            review_digests
        ):
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudication does not bind both reviews"
            )
        scores = _capability_scores(
            adjudication.get("capability_scores"), label="capability adjudication"
        )
        if not _record_digest(adjudication):
            raise L1CognitiveCapabilityOutcomeError(
                "capability adjudication digest is invalid"
            )
        adjudicated_scores[pair_id] = scores
    if set(adjudicated_scores) != set(bindings_by_pair):
        raise L1CognitiveCapabilityOutcomeError(
            "capability adjudication coverage is invalid"
        )
    summary = _measurement_summary(adjudicated_scores)
    if outcome.get("capability_measurement_summary") != summary:
        raise L1CognitiveCapabilityOutcomeError(
            "capability measurement summary is invalid"
        )
    outcomes = _capability_outcomes(summary)
    if outcome.get("capability_outcomes") != outcomes:
        raise L1CognitiveCapabilityOutcomeError("capability outcomes are invalid")
    seal = _mapping(outcome.get("external_seal"), label="capability external seal")
    if seal.get("verified") is not True or not _nonempty(
        seal.get("verification_ref"), label="capability seal reference"
    ).startswith("human-eval-authority://"):
        raise L1CognitiveCapabilityOutcomeError("capability external seal is invalid")
    _nonempty(seal.get("verified_at"), label="capability seal timestamp")
    if outcome.get("authority") != {
        "human_qualified": True,
        "release_authorizing": False,
        "production_authorizing": False,
        "automatic_promotion": False,
    }:
        raise L1CognitiveCapabilityOutcomeError(
            "capability outcome authority is invalid"
        )
    if not _record_digest(outcome):
        raise L1CognitiveCapabilityOutcomeError("capability outcome digest is invalid")
    return {
        "record_digest": str(outcome["record_digest"]),
        "capability_measurement_summary": summary,
        "capability_outcomes": outcomes,
    }


__all__ = [
    "L1CognitiveCapabilityOutcomeError",
    "L1_COGNITIVE_CAPABILITY_DIMENSIONS",
    "L1_COGNITIVE_CAPABILITY_OUTCOME_SCHEMA_VERSION",
    "capability_outcome_digest",
    "validate_l1_cognitive_capability_outcome",
]
