from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from apps_rg.evals.authoritative.artifacts import file_sha256, seal_record
from apps_rg.evals.authoritative.cluster_qrel_review import (
    CLUSTER_ADJUDICATION_BUNDLE_SCHEMA,
    CLUSTER_REVIEW_BUNDLE_SCHEMA,
    CLUSTER_REVIEW_SOURCE_SCHEMA,
    CLUSTER_RUBRIC_SCHEMA,
    CLUSTER_SPLIT_POLICY_SCHEMA,
    ClusterQrelReviewError,
    REQUIRED_CLUSTER_COVERAGE_TAGS,
    build_cluster_qrel_prelabel_packet,
    validate_cluster_qrel_prelabel_packet,
    validate_completed_cluster_qrel_reviews,
)
from apps_rg.evals.authoritative.cluster_retrieval import (
    CLUSTER_UNIVERSE_SCHEMA,
    LOGICAL_RETRIEVAL_UNIT,
    seal_cluster_authority_bindings,
)
from apps_rg.evals.resume_graph.reporting import canonical_digest


def _rubric() -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_RUBRIC_SCHEMA,
            "rubric_id": "cluster_relevance_evidence_section_v1",
            "reviewer_policy": {
                "independent_primary_reviewers": 2,
                "human_only": True,
                "unknown_is_pass": False,
                "rank_visible": False,
                "score_visible": False,
                "split_visible": False,
                "authority_ids_visible": False,
            },
            "dimensions": {
                "relevance_grade": [0, 1, 2, 3],
                "evidence_sufficiency": [
                    "SUFFICIENT",
                    "PARTIAL",
                    "INSUFFICIENT",
                ],
                "section_fitness": ["FIT", "CONDITIONAL", "NOT_FIT"],
                "ambiguity": ["UNAMBIGUOUS", "AMBIGUOUS", "CONFLICTING"],
                "rejection_reason": [
                    "NONE",
                    "IRRELEVANT",
                    "INSUFFICIENT_EVIDENCE",
                    "SECTION_MISMATCH",
                    "POLICY_RESTRICTED",
                    "LIFECYCLE_INELIGIBLE",
                    "WRONG_EMPLOYER",
                    "WRONG_ROLE",
                    "DUPLICATE",
                ],
            },
            "consistency_rules": [
                "relevance_grade_gte_2_requires_nonrejected_sufficient_or_partial_evidence",
                "relevance_grade_0_requires_rejection_reason",
                "insufficient_evidence_caps_relevance_at_1",
                "not_fit_caps_relevance_at_1",
                "conflicting_ambiguity_caps_relevance_at_1",
            ],
        }
    )


def _split_policy() -> dict[str, Any]:
    return seal_record(
        {
            "schema_version": CLUSTER_SPLIT_POLICY_SCHEMA,
            "policy_id": "cluster-qrel-calibration-holdout-v1",
            "splits": ["CALIBRATION", "HOLDOUT"],
            "required_target_profiles": ["executive"],
            "required_sections": ["experience"],
            "required_employers": ["Acme"],
            "required_cluster_kinds": [
                "role_episode",
                "capability_evidence",
            ],
            "required_coverage_tags": sorted(REQUIRED_CLUSTER_COVERAGE_TAGS),
        }
    )


def _bindings(query_text: str) -> dict[str, str]:
    return seal_cluster_authority_bindings(
        {
            "graph_sha256": "1" * 64,
            "cluster_registry_sha256": "2" * 64,
            "corpus_sha256": "3" * 64,
            "model_artifact_sha256": "4" * 64,
            "projection_sha256": "5" * 64,
            "runtime_config_sha256": "6" * 64,
            "query_sha256": hashlib.sha256(query_text.encode()).hexdigest(),
        }
    )


def _case(suffix: str, split: str) -> dict[str, Any]:
    query_text = f"product operations leadership target {suffix}"
    cluster_specs = (
        (
            f"cluster-{suffix}-role",
            "role_episode",
            [f"fact-{suffix}-role"] if split == "CALIBRATION" else [],
            "HELD" if split == "HOLDOUT" else "ACTIVE_CONFIRMED",
            (
                ["ROLE_EPISODE", "SHARED_EVIDENCE_ANCHOR"]
                if split == "CALIBRATION"
                else [
                    "ROLE_EPISODE",
                    "FACTLESS_OR_HELD",
                    "CROSS_EMPLOYER_NEAR_NEIGHBOR",
                ]
            ),
        ),
        (
            f"cluster-{suffix}-capability",
            "capability_evidence",
            [f"fact-{suffix}-capability"],
            "ACTIVE_CONFIRMED",
            (
                ["CAPABILITY_EVIDENCE", "AMBIGUOUS_CAPABILITY"]
                if split == "CALIBRATION"
                else [
                    "CAPABILITY_EVIDENCE",
                    "POLICY_RESTRICTED",
                    "SINGLETON_EXCEPTION",
                ]
            ),
        ),
    )
    universe = seal_record(
        {
            "schema_version": CLUSTER_UNIVERSE_SCHEMA,
            "query_id": f"source-query-{suffix}",
            "query_text": query_text,
            "target_profile": "executive",
            "section": "experience",
            "graph_lane": "achievement",
            "employer": "Acme",
            "evidence_density": "MEDIUM",
            "logical_retrieval_unit": LOGICAL_RETRIEVAL_UNIT,
            "authority_bindings": _bindings(query_text),
            "clusters": [
                {
                    "cluster_id": cluster_id,
                    "cluster_kind": cluster_kind,
                    "cluster_authority_envelope_sha256": (
                        f"{index + (7 if split == 'CALIBRATION' else 9):x}" * 64
                    ),
                    "member_node_ids": [f"node-{suffix}-{index}"],
                    "linked_fact_ids": facts,
                    "allowed_sections": ["experience"],
                    "activation_status": activation,
                    "external_claim_policy": "source_bound_only",
                    "graph_path": ["person", f"node-{suffix}-{index}"],
                    "employer": "Acme",
                    "role": "Director",
                    "evidence_type": cluster_kind,
                    "metric_bearing": index == 0,
                }
                for index, (
                    cluster_id,
                    cluster_kind,
                    facts,
                    activation,
                    _tags,
                ) in enumerate(cluster_specs)
            ],
        }
    )
    source_rows = []
    for index, (
        cluster_id,
        cluster_kind,
        _facts,
        _activation,
        coverage_tags,
    ) in enumerate(cluster_specs):
        universe_row = universe["clusters"][index]
        source_rows.append(
            {
                "cluster_id": cluster_id,
                "cluster_kind": cluster_kind,
                "cluster_authority_envelope_sha256": universe_row[
                    "cluster_authority_envelope_sha256"
                ],
                "claim_summary": (
                    "Led a governed operating-model improvement with measurable scope."
                ),
                "operating_context": "Enterprise product and operations leadership.",
                "capability_summaries": [
                    "Cross-functional operating model design",
                    "Evidence-bound execution governance",
                ],
                "approved_evidence_summaries": [
                    "Approved source describes the operating mechanism and outcome."
                ],
                "evidence_anchor_ids": [f"anchor-{suffix}-{index}"],
                "coverage_tags": coverage_tags,
            }
        )
    review_source = seal_record(
        {
            "schema_version": CLUSTER_REVIEW_SOURCE_SCHEMA,
            "query_id": universe["query_id"],
            "universe_digest": universe["record_digest"],
            "clusters": source_rows,
        }
    )
    return {
        "universe": universe,
        "expected_universe_digest": universe["record_digest"],
        "split": split,
        "review_source": review_source,
        "expected_review_source_digest": review_source["record_digest"],
    }


def _packet() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    rubric = _rubric()
    policy = _split_policy()
    packet, manifest, receipt = build_cluster_qrel_prelabel_packet(
        [_case("cal", "CALIBRATION"), _case("hold", "HOLDOUT")],
        packet_id="cluster-qrel-w2-test",
        blinding_nonce="test-only-blinding-nonce-0000000000000001",
        rubric=rubric,
        expected_rubric_digest=rubric["record_digest"],
        split_policy=policy,
        expected_split_policy_digest=policy["record_digest"],
    )
    return packet, manifest, receipt, rubric, policy


def _walk_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _walk_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _walk_keys(child)}
    return set()


def test_prelabel_packet_is_blinded_and_contains_no_labels() -> None:
    packet, manifest, receipt, _, _ = _packet()

    encoded = json.dumps(packet, sort_keys=True)
    assert "cluster-cal-role" not in encoded
    assert "source-query-cal" not in encoded
    assert "anchor-cal-0" not in encoded
    assert not {
        "cluster_id",
        "query_id",
        "split",
        "rank",
        "score",
        "similarity",
        "evidence_anchor_ids",
    } & _walk_keys(packet)
    assert "labels" not in _walk_keys(packet)
    assert receipt["labels_created"] is False
    assert receipt["qrels_created"] is False
    assert receipt["evaluation_executed"] is False
    assert receipt["release_authorizing"] is False
    assert receipt["coverage"]["cluster_split_overlap_count"] == 0
    assert receipt["coverage"]["evidence_anchor_split_overlap_count"] == 0
    assert manifest["reviewer_packet_digest"] == packet["record_digest"]


def test_prelabel_packet_is_deterministic_for_the_frozen_nonce() -> None:
    first = _packet()
    second = _packet()

    assert first[:3] == second[:3]


def test_stored_prelabel_packet_revalidates_without_labels() -> None:
    packet, manifest, receipt, rubric, policy = _packet()

    validation = validate_cluster_qrel_prelabel_packet(
        reviewer_packet=packet,
        expected_reviewer_packet_digest=packet["record_digest"],
        blinding_manifest=manifest,
        expected_blinding_manifest_digest=manifest["record_digest"],
        rubric=rubric,
        expected_rubric_digest=rubric["record_digest"],
        split_policy=policy,
        expected_split_policy_digest=policy["record_digest"],
    )

    assert validation["status"] == "PASS"
    assert validation["labels_present"] is False
    assert validation["checks"]["cluster_split_disjoint"] is True
    assert validation["checks"]["evidence_anchor_split_disjoint"] is True
    assert validation["release_authorizing"] is False
    assert receipt["prelabel_validation_digest"] == validation["record_digest"]


def test_prelabel_packet_rejects_evidence_anchor_split_leakage() -> None:
    calibration = _case("cal", "CALIBRATION")
    holdout = _case("hold", "HOLDOUT")
    holdout["review_source"]["clusters"][0]["evidence_anchor_ids"] = [
        "anchor-cal-0"
    ]
    holdout["review_source"] = seal_record(holdout["review_source"])
    holdout["expected_review_source_digest"] = holdout["review_source"][
        "record_digest"
    ]
    rubric = _rubric()
    policy = _split_policy()

    with pytest.raises(
        ClusterQrelReviewError,
        match="CLUSTER_REVIEW_EVIDENCE_ANCHOR_SPLIT_LEAKAGE",
    ):
        build_cluster_qrel_prelabel_packet(
            [calibration, holdout],
            packet_id="cluster-qrel-w2-leak",
            blinding_nonce="test-only-blinding-nonce-0000000000000002",
            rubric=rubric,
            expected_rubric_digest=rubric["record_digest"],
            split_policy=policy,
            expected_split_policy_digest=policy["record_digest"],
        )


def test_prelabel_packet_rejects_missing_required_stratum() -> None:
    cases = [_case("cal", "CALIBRATION"), _case("hold", "HOLDOUT")]
    cases[1]["review_source"]["clusters"][1]["coverage_tags"] = [
        "CAPABILITY_EVIDENCE"
    ]
    cases[1]["review_source"] = seal_record(cases[1]["review_source"])
    cases[1]["expected_review_source_digest"] = cases[1]["review_source"][
        "record_digest"
    ]
    rubric = _rubric()
    policy = _split_policy()

    with pytest.raises(
        ClusterQrelReviewError,
        match="CLUSTER_REVIEW_REQUIRED_COVERAGE_TAGS_INCOMPLETE",
    ):
        build_cluster_qrel_prelabel_packet(
            cases,
            packet_id="cluster-qrel-w2-coverage",
            blinding_nonce="test-only-blinding-nonce-0000000000000003",
            rubric=rubric,
            expected_rubric_digest=rubric["record_digest"],
            split_policy=policy,
            expected_split_policy_digest=policy["record_digest"],
        )


def _participant(name: str, roles: list[str]) -> dict[str, Any]:
    identity_ref = f"human-reviewer://{name}"
    return {
        "cohort": "retrieval",
        "identity_ref": identity_ref,
        "identity_hash": hashlib.sha256(identity_ref.encode()).hexdigest(),
        "roles": roles,
        "qualification_ref": "cluster-qrel-qualified",
    }


def _authority(tmp_path: Path) -> tuple[Path, str]:
    authority = seal_record(
        {
            "schema_version": (
                "apps_rg.c03_human_eval.human_review_authority_receipt.v1"
            ),
            "authority_mode": "TRUSTED_HUMAN_ROSTER_APPROVAL",
            "official_authority_eligible": True,
            "packet_id": "cluster-qrel-w2-test",
            "packet_manifest_digest": "a" * 64,
            "prelabel_packet_manifest_sha256": "b" * 64,
            "source_freeze_receipt_digest": "c" * 64,
            "cohort_manifest_digests": {
                "proof": "d" * 64,
                "retrieval": "e" * 64,
                "w9": "f" * 64,
            },
            "issuer_ref": "authority-issuer://test-owner",
            "approval_ref": "approval://test-only",
            "issued_at": "2026-08-02T00:00:00Z",
            "authorized_participants": [
                _participant("cluster-primary-1", ["primary"]),
                _participant("cluster-primary-2", ["primary"]),
                _participant("cluster-adjudicator", ["adjudicator"]),
            ],
            "unknown_is_pass": False,
        },
        digest_field="receipt_digest",
    )
    path = tmp_path / "human-authority.json"
    path.write_text(json.dumps(authority, sort_keys=True), encoding="utf-8")
    return path, file_sha256(path)


def _labels() -> dict[str, Any]:
    return {
        "relevance_grade": 3,
        "evidence_sufficiency": "SUFFICIENT",
        "section_fitness": "FIT",
        "ambiguity": "UNAMBIGUOUS",
        "rejection_reason": "NONE",
    }


def _completed_bundles(
    packet: dict[str, Any],
    rubric: dict[str, Any],
    authority_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    reviews = []
    reviews_by_item: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for query in packet["queries"]:
        for candidate in query["candidates"]:
            key = (query["query_blind_id"], candidate["candidate_blind_id"])
            rows = []
            for reviewer_index in (1, 2):
                identity_ref = f"human-reviewer://cluster-primary-{reviewer_index}"
                row = seal_record(
                    {
                        "review_id": (
                            f"review-{query['query_blind_id']}-"
                            f"{candidate['candidate_blind_id']}-{reviewer_index}"
                        ),
                        "query_blind_id": query["query_blind_id"],
                        "candidate_blind_id": candidate["candidate_blind_id"],
                        "candidate_content_digest": canonical_digest(candidate),
                        "reviewer_type": "human",
                        "reviewer_identity_ref": identity_ref,
                        "reviewer_identity_hash": hashlib.sha256(
                            identity_ref.encode()
                        ).hexdigest(),
                        "qualification_ref": "cluster-qrel-qualified",
                        "label_batch_id": f"batch-{reviewer_index}",
                        "human_attestation": True,
                        "labeled_at": f"2026-08-03T0{reviewer_index}:00:00Z",
                        "labels": _labels(),
                    }
                )
                reviews.append(row)
                rows.append(row)
            reviews_by_item[key] = rows
    review_bundle = seal_record(
        {
            "schema_version": CLUSTER_REVIEW_BUNDLE_SCHEMA,
            "packet_digest": packet["record_digest"],
            "rubric_digest": rubric["record_digest"],
            "authority_receipt_file_sha256": authority_sha256,
            "reviews": reviews,
        }
    )
    adjudications = []
    adjudicator_ref = "human-reviewer://cluster-adjudicator"
    for (query_blind_id, candidate_blind_id), rows in reviews_by_item.items():
        adjudications.append(
            seal_record(
                {
                    "adjudication_id": (
                        f"adjudication-{query_blind_id}-{candidate_blind_id}"
                    ),
                    "query_blind_id": query_blind_id,
                    "candidate_blind_id": candidate_blind_id,
                    "review_ids": [row["review_id"] for row in rows],
                    "review_digests": [row["record_digest"] for row in rows],
                    "status": "ADJUDICATED",
                    "adjudicator_type": "human",
                    "adjudicator_identity_ref": adjudicator_ref,
                    "adjudicator_identity_hash": hashlib.sha256(
                        adjudicator_ref.encode()
                    ).hexdigest(),
                    "qualification_ref": "cluster-qrel-qualified",
                    "human_attestation": True,
                    "adjudicated_at": "2026-08-04T00:00:00Z",
                    "final_labels": _labels(),
                }
            )
        )
    adjudication_bundle = seal_record(
        {
            "schema_version": CLUSTER_ADJUDICATION_BUNDLE_SCHEMA,
            "packet_digest": packet["record_digest"],
            "review_bundle_digest": review_bundle["record_digest"],
            "rubric_digest": rubric["record_digest"],
            "authority_receipt_file_sha256": authority_sha256,
            "adjudications": adjudications,
        }
    )
    return review_bundle, adjudication_bundle


def _validate_completed(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    packet, manifest, _, rubric, policy = _packet()
    authority_path, authority_sha256 = _authority(tmp_path)
    reviews, adjudications = _completed_bundles(
        packet,
        rubric,
        authority_sha256,
    )
    receipt = validate_completed_cluster_qrel_reviews(
        reviewer_packet=packet,
        expected_reviewer_packet_digest=packet["record_digest"],
        blinding_manifest=manifest,
        expected_blinding_manifest_digest=manifest["record_digest"],
        rubric=rubric,
        expected_rubric_digest=rubric["record_digest"],
        split_policy=policy,
        expected_split_policy_digest=policy["record_digest"],
        review_bundle=reviews,
        expected_review_bundle_digest=reviews["record_digest"],
        adjudication_bundle=adjudications,
        expected_adjudication_bundle_digest=adjudications["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha256,
    )
    return receipt, reviews, adjudications


def test_completed_reviews_require_two_humans_and_adjudication(
    tmp_path: Path,
) -> None:
    receipt, reviews, adjudications = _validate_completed(tmp_path)

    assert receipt["status"] == "PASS"
    assert receipt["item_count"] == 4
    assert receipt["review_count"] == 8
    assert receipt["adjudication_count"] == 4
    assert receipt["two_human_reviews_per_item"] is True
    assert receipt["adjudication_per_item"] is True
    assert receipt["zero_unresolved_judgments"] is True
    assert receipt["qrels_ready"] is True
    assert receipt["release_authorizing"] is False
    assert len(reviews["reviews"]) == 8
    assert len(adjudications["adjudications"]) == 4


def test_completed_reviews_reject_missing_second_reviewer(tmp_path: Path) -> None:
    packet, manifest, _, rubric, policy = _packet()
    authority_path, authority_sha256 = _authority(tmp_path)
    reviews, adjudications = _completed_bundles(
        packet,
        rubric,
        authority_sha256,
    )
    reviews["reviews"].pop(0)
    reviews = seal_record(reviews)

    receipt = validate_completed_cluster_qrel_reviews(
        reviewer_packet=packet,
        expected_reviewer_packet_digest=packet["record_digest"],
        blinding_manifest=manifest,
        expected_blinding_manifest_digest=manifest["record_digest"],
        rubric=rubric,
        expected_rubric_digest=rubric["record_digest"],
        split_policy=policy,
        expected_split_policy_digest=policy["record_digest"],
        review_bundle=reviews,
        expected_review_bundle_digest=reviews["record_digest"],
        adjudication_bundle=adjudications,
        expected_adjudication_bundle_digest=adjudications["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha256,
    )

    assert receipt["status"] == "UNKNOWN"
    assert "CLUSTER_REVIEW_EXACTLY_TWO_PRIMARY_REQUIRED" in receipt["unknown_reasons"]


def test_completed_reviews_reject_unresolved_or_inconsistent_label(
    tmp_path: Path,
) -> None:
    packet, manifest, _, rubric, policy = _packet()
    authority_path, authority_sha256 = _authority(tmp_path)
    reviews, adjudications = _completed_bundles(
        packet,
        rubric,
        authority_sha256,
    )
    changed = deepcopy(reviews["reviews"][0])
    changed["labels"]["evidence_sufficiency"] = "UNKNOWN"
    reviews["reviews"][0] = seal_record(changed)
    reviews = seal_record(reviews)

    receipt = validate_completed_cluster_qrel_reviews(
        reviewer_packet=packet,
        expected_reviewer_packet_digest=packet["record_digest"],
        blinding_manifest=manifest,
        expected_blinding_manifest_digest=manifest["record_digest"],
        rubric=rubric,
        expected_rubric_digest=rubric["record_digest"],
        split_policy=policy,
        expected_split_policy_digest=policy["record_digest"],
        review_bundle=reviews,
        expected_review_bundle_digest=reviews["record_digest"],
        adjudication_bundle=adjudications,
        expected_adjudication_bundle_digest=adjudications["record_digest"],
        authority_receipt_path=authority_path,
        expected_authority_file_sha256=authority_sha256,
    )

    assert receipt["status"] == "UNKNOWN"
    assert "CLUSTER_REVIEW_EVIDENCE_SUFFICIENCY_INVALID" in receipt[
        "unknown_reasons"
    ]
