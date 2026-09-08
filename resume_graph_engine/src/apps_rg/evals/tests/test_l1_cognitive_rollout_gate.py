"""Tests for the non-activating Apps RG L1 W6 readiness verifier."""

from __future__ import annotations

import copy
import hashlib
import json

from apps_rg.evals.l1_cognitive_calibration import holdout_commitment_path
from apps_rg.evals.l1_cognitive_capability_outcome import (
    L1_COGNITIVE_CAPABILITY_DIMENSIONS,
    L1_COGNITIVE_CAPABILITY_OUTCOME_SCHEMA_VERSION,
)
from apps_rg.evals.l1_cognitive_blind_review_packet import (
    L1_COGNITIVE_BLIND_REVIEW_MAPPING_SCHEMA_VERSION,
    L1_COGNITIVE_BLIND_REVIEW_PACKET_SCHEMA_VERSION,
)
from apps_rg.evals.l1_cognitive_outcome_protocol import (
    build_l1_cognitive_paired_shadow_receipt,
    load_l1_cognitive_outcome_protocol,
)
from apps_rg.evals.l1_cognitive_paired_cohort import (
    assemble_l1_cognitive_paired_cohort,
)
from apps_rg.evals.l1_cognitive_rollout_gate import (
    L1_COGNITIVE_HUMAN_OUTCOME_SCHEMA_VERSION,
    L1_COGNITIVE_PROTECTED_HOLDOUT_OUTCOME_SCHEMA_VERSION,
    L1_COGNITIVE_RELEASE_APPROVAL_SCHEMA_VERSION,
    L1_COGNITIVE_ROLLOUT_PLAN_SCHEMA_VERSION,
    build_l1_cognitive_rollout_gate,
    validate_l1_cognitive_rollout_gate,
)


def _digest(char: str) -> str:
    return "sha256:" + char * 64


def _seal(value: dict[str, object], field: str) -> dict[str, object]:
    body = {key: item for key, item in value.items() if key != field}
    encoded = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    value[field] = "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return value


def _hashed_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _paired_receipt() -> dict[str, object]:
    pairs: list[dict[str, object]] = []
    for index in range(1, 4):
        token = f"{index:03d}"
        pairs.append(
            {
                "pair_id": f"pair-{token}",
                "frozen_input_digest": _hashed_digest(f"frozen-input-{token}"),
                "provider_model_config_digest": _hashed_digest("provider-config"),
                "tool_config_digest": _hashed_digest("tool-config"),
                "control": {
                    "run_ref": f"control-{token}",
                    "run_id": f"control-run-{token}",
                    "l1_v2_capsule_digest": _hashed_digest(f"control-capsule-{token}"),
                    "l1_cognitive_treatment_execution_digest": _hashed_digest(
                        f"control-execution-{token}"
                    ),
                    "compiled_prompt_digest": _hashed_digest(f"control-prompt-{token}"),
                    "output_digest": _hashed_digest(f"control-output-{token}"),
                    "completion_status": "PASS",
                },
                "candidate": {
                    "run_ref": f"candidate-{token}",
                    "run_id": f"candidate-run-{token}",
                    "l1_cognitive_plan_digest": _hashed_digest(
                        f"candidate-plan-{token}"
                    ),
                    "l1_cognitive_advisory_digest": _hashed_digest(
                        f"candidate-advisory-{token}"
                    ),
                    "c0_outcome_set_digest": _hashed_digest(f"c0-outcome-{token}"),
                    "l1_cognitive_revision_set_digest": _hashed_digest(
                        f"candidate-revision-{token}"
                    ),
                    "l1_cognitive_treatment_execution_digest": _hashed_digest(
                        f"candidate-execution-{token}"
                    ),
                    "compiled_prompt_digest": _hashed_digest(
                        f"candidate-prompt-{token}"
                    ),
                    "output_digest": _hashed_digest(f"candidate-output-{token}"),
                    "completion_status": "PASS",
                },
            }
        )
    return build_l1_cognitive_paired_shadow_receipt(
        protocol=load_l1_cognitive_outcome_protocol(), pairs=pairs
    )


def _paired_cohort_manifest(paired: dict[str, object]) -> dict[str, object]:
    pairs = paired["pairs"]
    assert isinstance(pairs, list)
    protocol = load_l1_cognitive_outcome_protocol()
    source_receipts = [
        build_l1_cognitive_paired_shadow_receipt(protocol=protocol, pairs=[pair])
        for pair in pairs
        if isinstance(pair, dict)
    ]
    combined, manifest = assemble_l1_cognitive_paired_cohort(
        protocol=protocol,
        source_paired_receipts=source_receipts,
    )
    assert combined == paired
    return manifest


def _assessments(
    *,
    control_utility: int = 3,
    candidate_utility: int = 5,
    control_ready: bool = False,
    candidate_ready: bool = True,
    control_unsupported_claims: int = 0,
    candidate_unsupported_claims: int = 0,
) -> list[dict[str, object]]:
    return [
        {
            "variant_id": "variant-a",
            "finished_resume_utility_score": control_utility,
            "grounded_decision_ready": control_ready,
            "unsupported_material_claim_count": control_unsupported_claims,
        },
        {
            "variant_id": "variant-b",
            "finished_resume_utility_score": candidate_utility,
            "grounded_decision_ready": candidate_ready,
            "unsupported_material_claim_count": candidate_unsupported_claims,
        },
    ]


def _measurement_summary(
    *,
    control_utility: int = 3,
    candidate_utility: int = 5,
    control_ready: bool = False,
    candidate_ready: bool = True,
    control_unsupported_claims: int = 0,
    candidate_unsupported_claims: int = 0,
) -> dict[str, int]:
    pair_count = 3
    return {
        "pair_count": pair_count,
        "candidate_finished_resume_utility_score_sum": candidate_utility * pair_count,
        "control_finished_resume_utility_score_sum": control_utility * pair_count,
        "candidate_grounded_decision_ready_count": int(candidate_ready) * pair_count,
        "control_grounded_decision_ready_count": int(control_ready) * pair_count,
        "candidate_unsupported_material_claim_count": candidate_unsupported_claims
        * pair_count,
        "control_unsupported_material_claim_count": control_unsupported_claims
        * pair_count,
    }


def _capability_scores(
    *, control_score: int = 1, candidate_score: int = 2
) -> dict[str, dict[str, int]]:
    return {
        dimension: {"control": control_score, "candidate": candidate_score}
        for dimension in L1_COGNITIVE_CAPABILITY_DIMENSIONS
    }


def _capability_measurement_summary(
    *, control_score: int = 1, candidate_score: int = 2
) -> dict[str, object]:
    return {
        "pair_count": 3,
        "dimensions": {
            dimension: {
                "control_score_sum": control_score * 3,
                "candidate_score_sum": candidate_score * 3,
            }
            for dimension in L1_COGNITIVE_CAPABILITY_DIMENSIONS
        },
    }


def _capability_outcomes(*, candidate_improved: bool = True) -> dict[str, str]:
    return {
        dimension: "IMPROVED" if candidate_improved else "NOT_IMPROVED"
        for dimension in L1_COGNITIVE_CAPABILITY_DIMENSIONS
    }


def _capability_source_bindings(
    pair: dict[str, object],
) -> dict[str, str]:
    control = pair["control"]
    candidate = pair["candidate"]
    assert isinstance(control, dict)
    assert isinstance(candidate, dict)
    return {
        "frozen_input_digest": str(pair["frozen_input_digest"]),
        "control_l1_v2_capsule_digest": str(control["l1_v2_capsule_digest"]),
        "candidate_l1_cognitive_plan_digest": str(
            candidate["l1_cognitive_plan_digest"]
        ),
        "candidate_l1_cognitive_revision_set_digest": str(
            candidate["l1_cognitive_revision_set_digest"]
        ),
    }


def _valid_sources() -> dict[str, dict[str, object]]:
    paired = _paired_receipt()
    cohort_manifest = _paired_cohort_manifest(paired)
    raw_pairs = paired["pairs"]
    assert isinstance(raw_pairs, list)
    pairs = [pair for pair in raw_pairs if isinstance(pair, dict)]
    assert len(pairs) == 3
    packet_pairs: list[dict[str, object]] = []
    mapping_pairs: list[dict[str, object]] = []
    for index, pair in enumerate(pairs, start=1):
        blind_pair_id = f"blind-pair-{index:03d}"
        control = pair["control"]
        candidate = pair["candidate"]
        assert isinstance(control, dict)
        assert isinstance(candidate, dict)
        packet_pairs.append(
            {
                "blind_pair_id": blind_pair_id,
                "target": {"company": "Acme", "role": "VP Engineering"},
                "variants": [
                    {"variant_id": "variant-a"},
                    {"variant_id": "variant-b"},
                ],
            }
        )
        mapping_pairs.append(
            {
                "blind_pair_id": blind_pair_id,
                "source_pair_id": pair["pair_id"],
                "variants": [
                    {
                        "variant_id": "variant-a",
                        "arm": "control",
                        "run_ref": control["run_ref"],
                        "output_digest": control["output_digest"],
                    },
                    {
                        "variant_id": "variant-b",
                        "arm": "candidate",
                        "run_ref": candidate["run_ref"],
                        "output_digest": candidate["output_digest"],
                    },
                ],
            }
        )
    packet = _seal(
        {
            "schema_version": L1_COGNITIVE_BLIND_REVIEW_PACKET_SCHEMA_VERSION,
            "app_scope": "APPS_RG_V2_ONLY",
            "status": "PENDING_HUMAN_REVIEW",
            "paired_receipt_digest": paired["receipt_digest"],
            "reviewer_instructions": {},
            "pairs": packet_pairs,
            "authority": {
                "human_labels_present": False,
                "human_qualified": False,
                "release_authorizing": False,
                "production_authorizing": False,
            },
            "packet_digest": "",
        },
        "packet_digest",
    )
    mapping = _seal(
        {
            "schema_version": L1_COGNITIVE_BLIND_REVIEW_MAPPING_SCHEMA_VERSION,
            "app_scope": "APPS_RG_V2_ONLY",
            "distribution": "SEALED_DO_NOT_SEND_TO_REVIEWERS",
            "paired_receipt_digest": paired["receipt_digest"],
            "pairs": mapping_pairs,
            "mapping_digest": "",
        },
        "mapping_digest",
    )
    reviews: list[dict[str, object]] = []
    adjudications: list[dict[str, object]] = []
    for index in range(1, len(pairs) + 1):
        blind_pair_id = f"blind-pair-{index:03d}"
        pair_reviews: list[dict[str, object]] = []
        for suffix in ("a", "b"):
            review = _seal(
                {
                    "reviewer_identity_ref": (
                        f"human-reviewer://output-{index}-{suffix}"
                    ),
                    "qualification_ref": "resume-coach://executive",
                    "independent_review": True,
                    "human_attestation": True,
                    "completed_at": "2026-08-11T12:00:00Z",
                    "blind_review_packet_digest": packet["packet_digest"],
                    "blind_pair_id": blind_pair_id,
                    "variant_assessments": _assessments(),
                    "record_digest": "",
                },
                "record_digest",
            )
            reviews.append(review)
            pair_reviews.append(review)
        adjudications.append(
            _seal(
                {
                    "adjudicator_identity_ref": (
                        f"human-reviewer://output-adjudicator-{index}"
                    ),
                    "qualification_ref": "resume-coach://executive",
                    "human_attestation": True,
                    "completed_at": "2026-08-11T12:05:00Z",
                    "blind_review_packet_digest": packet["packet_digest"],
                    "blind_pair_id": blind_pair_id,
                    "reviewer_record_digests": [
                        review["record_digest"] for review in pair_reviews
                    ],
                    "variant_assessments": _assessments(),
                    "record_digest": "",
                },
                "record_digest",
            )
        )
    human_outcome = _seal(
        {
            "schema_version": L1_COGNITIVE_HUMAN_OUTCOME_SCHEMA_VERSION,
            "app_scope": "APPS_RG_V2_ONLY",
            "status": "PASS",
            "paired_receipt_digest": paired["receipt_digest"],
            "blind_review_packet_digest": packet["packet_digest"],
            "sealed_mapping_digest": mapping["mapping_digest"],
            "reviewer_evidence": reviews,
            "adjudications": adjudications,
            "adjudicated_measurement_summary": _measurement_summary(),
            "primary_outcomes": {"P1": "IMPROVED", "P2": "IMPROVED"},
            "record_digest": "",
        },
        "record_digest",
    )
    commitment = json.loads(holdout_commitment_path().read_text(encoding="utf-8"))
    raw_cases = commitment["commitments"]
    assert isinstance(raw_cases, list)
    cases = [case for case in raw_cases if isinstance(case, dict)]
    assert len(cases) == len(pairs)
    holdout_case_bindings: list[dict[str, object]] = []
    capability_reviews: list[dict[str, object]] = []
    capability_adjudications: list[dict[str, object]] = []
    for index, (pair, case) in enumerate(zip(pairs, cases), start=1):
        pair_id = str(pair["pair_id"])
        capability_bindings = _capability_source_bindings(pair)
        holdout_case_bindings.append(
            _seal(
                {
                    "source_pair_id": pair_id,
                    "fixture_id": case["fixture_id"],
                    "source_input_digest": case["source_input_digest"],
                    "frozen_input_digest": pair["frozen_input_digest"],
                    "verifier_identity_ref": (
                        f"human-eval-authority://holdout-case-{index}"
                    ),
                    "human_attestation": True,
                    "verified_at": "2026-08-11T12:06:00Z",
                    "verification_ref": (
                        f"human-eval-authority://holdout-case-{index}-binding"
                    ),
                    "binding_digest": "",
                },
                "binding_digest",
            )
        )
        pair_capability_reviews: list[dict[str, object]] = []
        for suffix in ("a", "b"):
            review = _seal(
                {
                    "reviewer_identity_ref": (
                        f"human-reviewer://capability-{index}-{suffix}"
                    ),
                    "qualification_ref": "resume-coach://executive",
                    "independent_review": True,
                    "human_attestation": True,
                    "completed_at": "2026-08-11T12:06:00Z",
                    "paired_receipt_digest": paired["receipt_digest"],
                    "source_pair_id": pair_id,
                    "source_bindings": capability_bindings,
                    "capability_scores": _capability_scores(),
                    "record_digest": "",
                },
                "record_digest",
            )
            capability_reviews.append(review)
            pair_capability_reviews.append(review)
        capability_adjudications.append(
            _seal(
                {
                    "adjudicator_identity_ref": (
                        f"human-reviewer://capability-adjudicator-{index}"
                    ),
                    "qualification_ref": "resume-coach://executive",
                    "human_attestation": True,
                    "completed_at": "2026-08-11T12:07:00Z",
                    "paired_receipt_digest": paired["receipt_digest"],
                    "source_pair_id": pair_id,
                    "source_bindings": capability_bindings,
                    "reviewer_record_digests": [
                        review["record_digest"] for review in pair_capability_reviews
                    ],
                    "capability_scores": _capability_scores(),
                    "record_digest": "",
                },
                "record_digest",
            )
        )
    capability_outcome = _seal(
        {
            "schema_version": L1_COGNITIVE_CAPABILITY_OUTCOME_SCHEMA_VERSION,
            "app_scope": "APPS_RG_V2_ONLY",
            "status": "PASS",
            "protected_holdout_commitment_ref": "apps_rg/evals/fixtures/l1_v2_protected_holdout_commitment.v1.json",
            "protected_holdout_commitment_digest": commitment["commitment_digest"],
            "paired_receipt_digest": paired["receipt_digest"],
            "holdout_case_bindings": holdout_case_bindings,
            "reviewer_evidence": capability_reviews,
            "adjudications": capability_adjudications,
            "capability_measurement_summary": _capability_measurement_summary(),
            "capability_outcomes": _capability_outcomes(),
            "external_seal": {
                "verified": True,
                "verification_ref": "human-eval-authority://capability-2026-08-11",
                "verified_at": "2026-08-11T12:08:00Z",
            },
            "authority": {
                "human_qualified": True,
                "release_authorizing": False,
                "production_authorizing": False,
                "automatic_promotion": False,
            },
            "record_digest": "",
        },
        "record_digest",
    )
    holdout = _seal(
        {
            "schema_version": L1_COGNITIVE_PROTECTED_HOLDOUT_OUTCOME_SCHEMA_VERSION,
            "app_scope": "APPS_RG_V2_ONLY",
            "status": "PASS",
            "protected_holdout_commitment_ref": "apps_rg/evals/fixtures/l1_v2_protected_holdout_commitment.v1.json",
            "protected_holdout_commitment_digest": commitment["commitment_digest"],
            "paired_receipt_digest": paired["receipt_digest"],
            "blind_review_packet_digest": packet["packet_digest"],
            "human_outcome_digest": human_outcome["record_digest"],
            "adjudicated_measurement_summary": _measurement_summary(),
            "primary_outcomes": {"P1": "IMPROVED", "P2": "IMPROVED"},
            "guardrails": {
                "unsupported_material_claim_count": 0,
                "critical_binding_error_count": 0,
                "critical_run_divergence_count": 0,
            },
            "external_seal": {
                "verified": True,
                "verification_ref": "human-eval-authority://holdout-2026-08-11",
                "verified_at": "2026-08-11T12:10:00Z",
            },
            "authority": {
                "human_qualified": True,
                "release_authorizing": False,
                "production_authorizing": False,
                "automatic_promotion": False,
            },
            "record_digest": "",
        },
        "record_digest",
    )
    rollout_plan = _seal(
        {
            "schema_version": L1_COGNITIVE_ROLLOUT_PLAN_SCHEMA_VERSION,
            "app_scope": "APPS_RG_V2_ONLY",
            "scope": {
                "treatment_id": "l1_cognitive_v3",
                "max_candidate_runs": 3,
                "expires_at": "2026-08-18T00:00:00Z",
            },
            "observation": {
                "requirement_level_observation": True,
                "c0_outcome_observation": True,
                "output_disposition_observation": True,
            },
            "rollback": {
                "enabled": True,
                "fallback_treatment": "l1_v2_control",
                "trigger_refs": ["guardrail:any_nonzero", "operator:stop"],
            },
            "plan_digest": "",
        },
        "plan_digest",
    )
    approval = _seal(
        {
            "schema_version": L1_COGNITIVE_RELEASE_APPROVAL_SCHEMA_VERSION,
            "app_scope": "APPS_RG_V2_ONLY",
            "status": "APPROVED",
            "approver_identity_ref": "human-release://apps-rg-owner",
            "human_attestation": True,
            "approved_at": "2026-08-11T12:15:00Z",
            "protected_holdout_outcome_digest": holdout["record_digest"],
            "cognitive_capability_outcome_digest": capability_outcome["record_digest"],
            "rollout_plan_digest": rollout_plan["plan_digest"],
            "approval_digest": "",
        },
        "approval_digest",
    )
    return {
        "paired_receipt": paired,
        "paired_cohort_manifest": cohort_manifest,
        "blind_review_packet": packet,
        "sealed_mapping": mapping,
        "human_outcome": human_outcome,
        "cognitive_capability_outcome": capability_outcome,
        "protected_holdout_outcome": holdout,
        "rollout_plan": rollout_plan,
        "release_approval": approval,
    }


def test_rollout_gate_blocks_when_evidence_is_absent_and_never_activates() -> None:
    receipt = build_l1_cognitive_rollout_gate()

    assert receipt["status"] == "BLOCKED"
    assert receipt["authority"]["automatic_promotion"] is False
    assert receipt["authority"]["runtime_activation_performed"] is False
    assert receipt["authority"]["release_authorizing"] is False


def test_rollout_gate_verifies_complete_human_governed_evidence_without_promoting() -> (
    None
):
    sources = _valid_sources()
    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "READY_FOR_HUMAN_OPERATED_LIMITED_ROLLOUT"
    assert receipt["failure_codes"] == []
    assert receipt["authority"]["automatic_promotion"] is False
    assert receipt["authority"]["human_operated_rollout_required"] is True
    validate_l1_cognitive_rollout_gate(receipt, **sources)


def test_rollout_gate_rejects_release_approval_not_bound_to_holdout_outcome() -> None:
    sources = _valid_sources()
    approval = copy.deepcopy(sources["release_approval"])
    approval["protected_holdout_outcome_digest"] = _digest("9")
    sources["release_approval"] = _seal(approval, "approval_digest")

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "NAMED_HUMAN_RELEASE_APPROVAL_INVALID_OR_MISSING" in receipt["failure_codes"]


def test_rollout_gate_requires_direct_cognitive_capability_evidence() -> None:
    sources = _valid_sources()
    sources.pop("cognitive_capability_outcome")

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "COGNITIVE_CAPABILITY_OUTCOME_INVALID_OR_MISSING" in receipt["failure_codes"]


def test_rollout_gate_requires_a_complete_captured_protected_cohort() -> None:
    sources = _valid_sources()
    sources.pop("paired_cohort_manifest")

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "PROTECTED_HOLDOUT_COHORT_INVALID_OR_MISSING" in receipt["failure_codes"]


def test_rollout_gate_rejects_a_capability_outcome_missing_a_committed_case() -> None:
    sources = _valid_sources()
    capability_outcome = copy.deepcopy(sources["cognitive_capability_outcome"])
    bindings = capability_outcome["holdout_case_bindings"]
    assert isinstance(bindings, list)
    bindings.pop()
    sources["cognitive_capability_outcome"] = _seal(
        capability_outcome,
        "record_digest",
    )

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "COGNITIVE_CAPABILITY_OUTCOME_INVALID_OR_MISSING" in receipt["failure_codes"]


def test_rollout_gate_records_valid_negative_capability_evidence() -> None:
    sources = _valid_sources()
    negative_scores = _capability_scores(control_score=2, candidate_score=1)
    negative_summary = _capability_measurement_summary(
        control_score=2,
        candidate_score=1,
    )
    negative_outcomes = _capability_outcomes(candidate_improved=False)

    capability_outcome = copy.deepcopy(sources["cognitive_capability_outcome"])
    adjudications = capability_outcome["adjudications"]
    assert isinstance(adjudications, list)
    for index, raw_adjudication in enumerate(adjudications):
        adjudication = dict(raw_adjudication)
        adjudication["capability_scores"] = negative_scores
        adjudications[index] = _seal(adjudication, "record_digest")
    capability_outcome["capability_measurement_summary"] = negative_summary
    capability_outcome["capability_outcomes"] = negative_outcomes
    capability_outcome = _seal(capability_outcome, "record_digest")

    approval = copy.deepcopy(sources["release_approval"])
    approval["cognitive_capability_outcome_digest"] = capability_outcome[
        "record_digest"
    ]
    approval = _seal(approval, "approval_digest")
    sources["cognitive_capability_outcome"] = capability_outcome
    sources["release_approval"] = approval

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert receipt["outcome_observations"]["cognitive_capability_outcomes"] == (
        negative_outcomes
    )
    assert "COGNITIVE_CAPABILITY_OUTCOMES_NOT_IMPROVED" in receipt["failure_codes"]
    assert (
        "COGNITIVE_CAPABILITY_OUTCOME_INVALID_OR_MISSING"
        not in receipt["failure_codes"]
    )


def test_rollout_gate_rejects_capability_improvement_not_backed_by_scores() -> None:
    sources = _valid_sources()
    capability_outcome = copy.deepcopy(sources["cognitive_capability_outcome"])
    capability_outcome["capability_outcomes"] = _capability_outcomes(
        candidate_improved=False
    )
    sources["cognitive_capability_outcome"] = _seal(
        capability_outcome,
        "record_digest",
    )

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "COGNITIVE_CAPABILITY_OUTCOME_INVALID_OR_MISSING" in receipt["failure_codes"]


def test_rollout_gate_rejects_metadata_only_human_review_records() -> None:
    sources = _valid_sources()
    human_outcome = copy.deepcopy(sources["human_outcome"])
    reviews = human_outcome["reviewer_evidence"]
    assert isinstance(reviews, list)
    first_review = dict(reviews[0])
    first_review.pop("variant_assessments")
    reviews[0] = _seal(first_review, "record_digest")
    sources["human_outcome"] = _seal(human_outcome, "record_digest")

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "INDEPENDENT_HUMAN_REVIEW_INVALID_OR_MISSING" in receipt["failure_codes"]


def test_rollout_gate_rejects_unattested_reviewer_record() -> None:
    sources = _valid_sources()
    human_outcome = copy.deepcopy(sources["human_outcome"])
    reviews = human_outcome["reviewer_evidence"]
    assert isinstance(reviews, list)
    first_review = dict(reviews[0])
    first_review["human_attestation"] = False
    reviews[0] = _seal(first_review, "record_digest")
    sources["human_outcome"] = _seal(human_outcome, "record_digest")

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "INDEPENDENT_HUMAN_REVIEW_INVALID_OR_MISSING" in receipt["failure_codes"]


def test_rollout_gate_records_valid_negative_human_evidence_without_promoting() -> None:
    sources = _valid_sources()
    negative_assessments = _assessments(
        candidate_utility=2,
        candidate_ready=False,
    )
    negative_summary = _measurement_summary(
        candidate_utility=2,
        candidate_ready=False,
    )
    negative_outcomes = {"P1": "NOT_IMPROVED", "P2": "NOT_IMPROVED"}

    human_outcome = copy.deepcopy(sources["human_outcome"])
    adjudications = human_outcome["adjudications"]
    assert isinstance(adjudications, list)
    for index, raw_adjudication in enumerate(adjudications):
        adjudication = dict(raw_adjudication)
        adjudication["variant_assessments"] = negative_assessments
        adjudications[index] = _seal(adjudication, "record_digest")
    human_outcome["adjudicated_measurement_summary"] = negative_summary
    human_outcome["primary_outcomes"] = negative_outcomes
    human_outcome = _seal(human_outcome, "record_digest")

    holdout = copy.deepcopy(sources["protected_holdout_outcome"])
    holdout["human_outcome_digest"] = human_outcome["record_digest"]
    holdout["adjudicated_measurement_summary"] = negative_summary
    holdout["primary_outcomes"] = negative_outcomes
    holdout = _seal(holdout, "record_digest")

    approval = copy.deepcopy(sources["release_approval"])
    approval["protected_holdout_outcome_digest"] = holdout["record_digest"]
    approval = _seal(approval, "approval_digest")

    sources["human_outcome"] = human_outcome
    sources["protected_holdout_outcome"] = holdout
    sources["release_approval"] = approval
    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert receipt["outcome_observations"]["primary_outcomes"] == negative_outcomes
    assert "PROTECTED_HOLDOUT_PRIMARY_OUTCOMES_NOT_IMPROVED" in receipt["failure_codes"]
    assert "INDEPENDENT_HUMAN_REVIEW_INVALID_OR_MISSING" not in receipt["failure_codes"]
    assert receipt["authority"]["automatic_promotion"] is False


def test_rollout_gate_rejects_claimed_improvement_not_backed_by_adjudication() -> None:
    sources = _valid_sources()
    negative_assessments = _assessments(
        candidate_utility=2,
        candidate_ready=False,
    )
    negative_summary = _measurement_summary(
        candidate_utility=2,
        candidate_ready=False,
    )
    human_outcome = copy.deepcopy(sources["human_outcome"])
    adjudications = human_outcome["adjudications"]
    assert isinstance(adjudications, list)
    for index, raw_adjudication in enumerate(adjudications):
        adjudication = dict(raw_adjudication)
        adjudication["variant_assessments"] = negative_assessments
        adjudications[index] = _seal(adjudication, "record_digest")
    human_outcome["adjudicated_measurement_summary"] = negative_summary
    human_outcome = _seal(human_outcome, "record_digest")
    sources["human_outcome"] = human_outcome

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "INDEPENDENT_HUMAN_REVIEW_INVALID_OR_MISSING" in receipt["failure_codes"]


def test_rollout_gate_rejects_blind_mapping_that_substitutes_an_output() -> None:
    sources = _valid_sources()
    mapping = copy.deepcopy(sources["sealed_mapping"])
    pairs = mapping["pairs"]
    assert isinstance(pairs, list)
    variants = pairs[0]["variants"]
    assert isinstance(variants, list)
    variants[0]["output_digest"] = _digest("9")
    sources["sealed_mapping"] = _seal(mapping, "mapping_digest")

    receipt = build_l1_cognitive_rollout_gate(**sources)

    assert receipt["status"] == "BLOCKED"
    assert "BLINDED_REVIEW_MATERIAL_INVALID_OR_MISSING" in receipt["failure_codes"]
