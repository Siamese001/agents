"""Tests for the isolated, non-authoritative owner-solo QREL lane.

The complete-ledger fixtures below are synthetic test data in a pytest temporary
directory. They never read, alter, or claim to be human returns or repository
QREL authority.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    ranking_identity_sha256,
)
from apps_rg.evals.c03_graph_evidence_cluster_review_packet import (
    W8_RECEIPT_PATH,
    build_prelabel_packet_content,
)
from apps_rg.evals.owner_solo import c03_owner_solo_qrel as solo
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    REGISTRY_PATH,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)
from tools.apps_rg_standalone.c03_graph_evidence_cluster_review_packet_wave8 import (
    _write_packet,
)

ROOT = Path(__file__).resolve().parents[4]


def _load(relative: Path | str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    sealed = dict(value)
    sealed[field] = canonical_sha256(sealed)
    return sealed


def _all_rankings(manifest: dict[str, Any], registry: dict[str, Any]) -> dict[str, list[str]]:
    allowed_by_section = {
        str(section): sorted(
            str(cluster["cluster_id"])
            for cluster in registry["clusters"]
            if section in cluster["allowed_sections"]
        )
        for section in manifest["section_ids"]
    }
    return {
        f"{query['query_id']}|{section}": list(allowed_by_section[section])
        for query in manifest["queries"]
        for section in manifest["section_ids"]
    }


def _repository_binding() -> dict[str, Any]:
    return copy.deepcopy(solo._repository_bindings(ROOT)["binding"])


def _policy(binding: dict[str, Any] | None = None) -> dict[str, Any]:
    repository_binding = {
        "repository": "Siamese001/apps_rg_v2",
        "source_commit": "58fdf85ff903907aa0ebbfe545842fa0e03a3258",
        "query_manifest_sha256": "a" * 64,
        "registry_sha256": "b" * 64,
        "projection_generation_sha256": "c" * 64,
        "projection_file_sha256": "d" * 64,
        "ranking_identity_sha256": "e" * 64,
        "w6_receipt_sha256": "f" * 64,
        "w7_receipt_sha256": "1" * 64,
        "w8_receipt_sha256": "2" * 64,
        "w8_packet_manifest_sha256": "3" * 64,
    }
    if binding is not None:
        repository_binding.update(
            {
                "query_manifest_sha256": binding["query_manifest_sha256"],
                "registry_sha256": binding["registry_sha256"],
                "projection_generation_sha256": binding[
                    "projection_generation_sha256"
                ],
                "projection_file_sha256": binding["projection_file_sha256"],
                "ranking_identity_sha256": binding["ranking_identity_sha256"],
                "w6_receipt_sha256": binding["w6_receipt_sha256"],
                "w7_receipt_sha256": binding["w7_receipt_sha256"],
                "w8_receipt_sha256": binding["w8_receipt_sha256"],
                "w8_packet_manifest_sha256": binding[
                    "w8_packet_manifest_sha256"
                ],
            }
        )
    return _seal(
        {
            "schema_version": solo.POLICY_SCHEMA_VERSION,
            "status": "OWNER_APPROVED_EXCEPTION",
            "owner_reviewer": {
                "identity_ref": "human-reviewer://amit-owner",
                "roles": ["primary_reviewer", "self_adjudicator"],
                "human_only": True,
            },
            "exception": {
                "independent_second_reviewer_required": False,
                "independent_adjudicator_required": False,
                "waived_controls": [
                    "inter_rater_agreement",
                    "independent_disagreement_resolution",
                    "three_distinct_human_authority",
                ],
                "controls_not_waived": [
                    "full_finite_candidate_universe",
                    "rank_and_score_blinding",
                    "explicit_integer_grade_0_1_2_3",
                    "nonempty_human_rationale",
                    "calibration_holdout_separation",
                    "immutable_query_registry_projection_and_ranking_bindings",
                    "unknown_is_not_pass",
                ],
            },
            "authority_boundary": {
                "required_result_label": solo.RESULT_LABEL,
                "may_not_support": [
                    "independent QREL authority",
                    "inter-rater reliability claims",
                    "release-quality qualification under the existing authoritative contract",
                    "production promotion",
                ],
            },
            "repository_binding": repository_binding,
        },
        "record_digest",
    )


def _execution(binding: dict[str, Any]) -> dict[str, Any]:
    return _seal(
        {
            "schema_version": solo.EXECUTION_MANIFEST_SCHEMA_VERSION,
            "status": "BLOCKED_PENDING_W8_PACKET_EXPORT",
            "runtime_binding": {
                "model_id": "BAAI/bge-m3",
                "model_revision": "5617a9f61b028005a4858fdac845db406aefb181",
                "model_artifact_sha256": "38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263",
                "dimension": 1024,
                "normalization": "l2",
                "logical_retrieval_unit": "graph_evidence_cluster",
                "active_cluster_count": 38,
                "network_allowed": False,
                "fallback_allowed": False,
            },
            "evaluation_denominator": {
                "query_count": 6,
                "calibration_query_count": 3,
                "holdout_query_count": 3,
                "section_count": 8,
                "query_section_case_count": 48,
                "candidate_judgment_count": 456,
                "relevant_grade_floor": 2,
                "full_candidate_universe_required": True,
                "partial_top_k_judging_forbidden": True,
            },
            "seed_label_set": {
                "explicit_grade_count": 50,
                "qrel_status": "UNBOUND_DEVELOPMENT_SEED_NOT_FORMAL_QRELS",
            },
            "repository_binding": {
                "source_commit": "58fdf85ff903907aa0ebbfe545842fa0e03a3258",
                **{
                    field: binding[field]
                    for field in (
                        "query_manifest_sha256",
                        "registry_sha256",
                        "projection_generation_sha256",
                        "projection_file_sha256",
                        "ranking_identity_sha256",
                        "w6_receipt_sha256",
                        "w7_receipt_sha256",
                        "w8_receipt_sha256",
                        "w8_packet_manifest_sha256",
                    )
                },
            },
        },
        "record_digest",
    )


def _test_packet(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Materialize a valid, temporary W8-shaped packet without human labels."""
    query_manifest = _load(solo.QUERY_MANIFEST_PATH)
    registry = _load(REGISTRY_PATH)
    w8 = _load(W8_RECEIPT_PATH)
    rankings = _all_rankings(query_manifest, registry)
    ranking_digest = ranking_identity_sha256(rankings)
    binding = _repository_binding()
    binding["ranking_identity_sha256"] = ranking_digest
    content = build_prelabel_packet_content(
        query_manifest=query_manifest,
        registry=registry,
        rankings=rankings,
        ranking_identity_sha256=ranking_digest,
        authority_bindings={
            "wave7_receipt_sha256": w8["source_baseline"]["wave7_receipt_sha256"],
            "query_manifest_sha256": query_manifest["query_manifest_sha256"],
            "registry_sha256": registry["registry_sha256"],
            "projection_generation_sha256": w8["source_baseline"][
                "projection_generation_sha256"
            ],
        },
        blinding_nonce="f" * 64,
        repository_root=ROOT,
    )
    packet_dir = tmp_path / "packet"
    manifest, manifest_file_sha256 = _write_packet(
        packet_dir=packet_dir,
        content=content,
        runtime_proof={"test_fixture": True},
    )
    binding["w8_packet_manifest_sha256"] = manifest["manifest_sha256"]
    packet = solo._packet_content(
        packet_dir,
        query_manifest=query_manifest,
        registry=registry,
        expected={
            "w8": {
                "controlled_packet": {
                    "packet_manifest_file_sha256": manifest_file_sha256,
                }
            },
            "binding": binding,
        },
    )
    return packet, {
        "packet_dir": packet_dir,
        "query_manifest": query_manifest,
        "registry": registry,
        "binding": binding,
    }


@pytest.fixture
def owner_context(tmp_path: Path) -> dict[str, Any]:
    packet, values = _test_packet(tmp_path)
    policy = _policy(values["binding"])
    return {
        "repo_root": ROOT,
        "runtime_dir": tmp_path / "private-runtime",
        "policy": policy,
        "repository": {
            "query_manifest": values["query_manifest"],
            "binding": values["binding"],
        },
        "packet": packet,
    }


def _first(context: dict[str, Any]) -> dict[str, Any]:
    result = solo.next_blinded_candidate(context)
    assert result is not None
    return result


def _record_one(context: dict[str, Any]) -> dict[str, Any]:
    candidate = _first(context)
    solo.record_judgment(
        context,
        item_ref=candidate["item_ref"],
        candidate_ref=candidate["candidate_ref"],
        grade=2,
        rationale="Temporary explicit test judgment.",
    )
    return candidate


def _complete_test_ledger(context: dict[str, Any]) -> None:
    """Write explicit constant test events only; production paths never do this."""
    owner = context["policy"]["owner_reviewer"]["identity_ref"]
    for item_ref, candidate_ref in solo._visible_candidates(context):
        solo._append_event(
            context,
            solo._new_event(
                event_type="RECORD",
                item_ref=item_ref,
                candidate_ref=candidate_ref,
                grade=2,
                rationale="Temporary explicit test-only fixture judgment.",
                owner_identity=owner,
                prior_event_id=None,
            ),
        )


def test_valid_owner_solo_policy_is_provisional_only() -> None:
    assert solo.validate_owner_solo_exception_policy(_policy()) == []


def test_malformed_policy_fails_closed() -> None:
    policy = _policy()
    policy["status"] = "APPROVED"
    policy["record_digest"] = canonical_sha256(
        {key: value for key, value in policy.items() if key != "record_digest"}
    )

    assert "POLICY_STATUS" in solo.validate_owner_solo_exception_policy(policy)


def test_packet_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    _packet, values = _test_packet(tmp_path)
    manifest_path = values["packet_dir"] / "packet_manifest.v1.json"
    manifest_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(solo.OwnerSoloQrelError, match="PACKET_MANIFEST_FILE_DIGEST"):
        solo._packet_content(
            values["packet_dir"],
            query_manifest=values["query_manifest"],
            registry=values["registry"],
            expected={
                "w8": {"controlled_packet": {"packet_manifest_file_sha256": "0" * 64}},
                "binding": values["binding"],
            },
        )


def test_reviewer_payload_rank_or_score_leakage_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _packet, values = _test_packet(tmp_path)
    manifest_file_sha256 = solo._file_sha256(
        values["packet_dir"] / "packet_manifest.v1.json"
    )
    monkeypatch.setattr(solo, "unsafe_reviewer_keys", lambda _item: ["rank"])

    with pytest.raises(solo.OwnerSoloQrelError, match="REVIEWER_A_LEAKAGE_KEYS"):
        solo._packet_content(
            values["packet_dir"],
            query_manifest=values["query_manifest"],
            registry=values["registry"],
            expected={
                "w8": {
                    "controlled_packet": {
                        "packet_manifest_file_sha256": manifest_file_sha256,
                    }
                },
                "binding": values["binding"],
            },
        )


def test_invalid_grade_rejected(owner_context: dict[str, Any]) -> None:
    candidate = _first(owner_context)

    with pytest.raises(solo.OwnerSoloQrelError, match="explicit integer"):
        solo.record_judgment(
            owner_context,
            item_ref=candidate["item_ref"],
            candidate_ref=candidate["candidate_ref"],
            grade=4,
            rationale="Temporary test rationale.",
        )


def test_empty_rationale_rejected(owner_context: dict[str, Any]) -> None:
    candidate = _first(owner_context)

    with pytest.raises(solo.OwnerSoloQrelError, match="nonempty"):
        solo.record_judgment(
            owner_context,
            item_ref=candidate["item_ref"],
            candidate_ref=candidate["candidate_ref"],
            grade=2,
            rationale="   ",
        )


def test_duplicate_candidate_return_rejected(owner_context: dict[str, Any]) -> None:
    candidate = _record_one(owner_context)

    with pytest.raises(solo.OwnerSoloQrelError, match="already has an active grade"):
        solo.record_judgment(
            owner_context,
            item_ref=candidate["item_ref"],
            candidate_ref=candidate["candidate_ref"],
            grade=3,
            rationale="Temporary duplicate test rationale.",
        )


def test_missing_candidate_return_prevents_finalization(owner_context: dict[str, Any]) -> None:
    with pytest.raises(solo.OwnerSoloQrelError, match="456 active explicit grades"):
        solo.finalize_owner_solo_qrels(owner_context)


def test_correction_chain_is_append_only_and_validated(owner_context: dict[str, Any]) -> None:
    candidate = _record_one(owner_context)
    corrected = solo.correct_judgment(
        owner_context,
        item_ref=candidate["item_ref"],
        candidate_ref=candidate["candidate_ref"],
        grade=3,
        rationale="Temporary corrected test judgment.",
    )
    assert corrected["event"]["prior_event_id"] is not None
    assert solo.status_receipt(owner_context, write=False)["correction_count"] == 1

    solo._append_event(
        owner_context,
        solo._new_event(
            event_type="CORRECTION",
            item_ref=candidate["item_ref"],
            candidate_ref=candidate["candidate_ref"],
            grade=1,
            rationale="Invalid temporary chain test event.",
            owner_identity=owner_context["policy"]["owner_reviewer"]["identity_ref"],
            prior_event_id="event-" + "0" * 32,
        ),
    )
    with pytest.raises(solo.OwnerSoloQrelError, match="CORRECTION_CHAIN"):
        solo.next_blinded_candidate(owner_context)


def test_resume_after_interruption_reuses_append_only_ledger(
    owner_context: dict[str, Any]
) -> None:
    first = _record_one(owner_context)
    resumed_context = dict(owner_context)
    next_candidate = _first(resumed_context)

    assert (
        next_candidate["item_ref"],
        next_candidate["candidate_ref"],
    ) != (first["item_ref"], first["candidate_ref"])
    assert solo.status_receipt(resumed_context, write=False)["completed_judgment_count"] == 1


def test_finalize_before_all_456_judgments_rejected(owner_context: dict[str, Any]) -> None:
    _record_one(owner_context)

    with pytest.raises(solo.OwnerSoloQrelError, match="observed 1"):
        solo.finalize_owner_solo_qrels(owner_context)


def test_sealed_mapping_conservation_requires_456(owner_context: dict[str, Any]) -> None:
    owner_context["packet"]["sealed_mapping"]["cohorts"]["reviewer_a"][0][
        "candidates"
    ].pop()

    with pytest.raises(solo.OwnerSoloQrelError, match="denominator is not 456"):
        solo._sealed_lookup(owner_context)


def test_next_keeps_calibration_holdout_and_ranking_blinded(
    owner_context: dict[str, Any]
) -> None:
    candidate = _first(owner_context)

    assert set(candidate) == {
        "item_ref",
        "target_context",
        "resume_section",
        "candidate_ref",
        "evidence_cluster_text",
        "completed_count",
        "total_count",
    }
    assert not {
        "query_id",
        "split",
        "cluster_id",
        "frozen_rank",
        "bge_score",
        "similarity_score",
        "model_id",
    } & set(candidate)


def test_incorrect_ranking_identity_rejected_for_metrics(
    owner_context: dict[str, Any]
) -> None:
    owner_context["repository"]["binding"]["ranking_identity_sha256"] = "0" * 64
    _complete_test_ledger(owner_context)
    solo.finalize_owner_solo_qrels(owner_context)

    with pytest.raises(solo.OwnerSoloQrelError, match="Frozen ranking identity mismatch"):
        solo.compute_owner_solo_metrics(owner_context)


def test_incorrect_query_or_registry_digest_rejected() -> None:
    binding = _repository_binding()
    policy = _policy(binding)
    execution = _execution(binding)
    policy["repository_binding"]["query_manifest_sha256"] = "0" * 64
    execution["repository_binding"]["registry_sha256"] = "1" * 64

    issues = solo._binding_issues(
        policy,
        execution,
        {"binding": binding},
        ROOT,
    )
    assert "POLICY_BINDING:query_manifest_sha256" in issues
    assert "EXECUTION_BINDING:registry_sha256" in issues


def test_authoritative_release_status_is_rejected(owner_context: dict[str, Any]) -> None:
    _complete_test_ledger(owner_context)
    solo.finalize_owner_solo_qrels(owner_context)
    path = Path(owner_context["runtime_dir"]) / "finalized" / "owner_solo_qrels.v1.json"
    qrels = json.loads(path.read_text(encoding="utf-8"))
    qrels["status"] = "FROZEN_HUMAN_ADJUDICATED"
    qrels["qrel_digest"] = canonical_sha256(
        {key: value for key, value in qrels.items() if key != "qrel_digest"}
    )
    path.write_text(json.dumps(qrels), encoding="utf-8")

    with pytest.raises(solo.OwnerSoloQrelError, match="not provisional-only"):
        solo.compute_owner_solo_metrics(owner_context)


def test_activation_and_production_authority_cannot_be_enabled() -> None:
    contract = solo.load_owner_solo_contract(ROOT)
    contract["publication_boundary"]["activation_manifest_created"] = True
    contract["publication_boundary"]["production_promotion_authorized"] = True

    assert "CONTRACT_PUBLICATION_BOUNDARY" in solo.validate_owner_solo_contract(contract)


def test_exact_qrel_denominator_is_456(owner_context: dict[str, Any]) -> None:
    assert len(solo._visible_candidates(owner_context)) == 456
    assert len(solo._sealed_lookup(owner_context)) == 456


def test_packet_validation_receipt_binds_reviewer_a_artifacts(
    owner_context: dict[str, Any]
) -> None:
    receipt = solo.packet_validation_receipt(owner_context, write=False)

    assert receipt["status"] == "PASS_VALIDATED_BLINDED_W8_PACKET"
    assert receipt["reviewer_a_item_count"] == 48
    assert receipt["reviewer_a_candidate_judgment_count"] == 456
    assert receipt["sealed_mapping_candidate_judgment_count"] == 456
    assert receipt["reviewer_visible_rank_score_split_identity_leakage"] is False
    assert solo._digest_matches(receipt, "receipt_digest")


def test_metric_computation_is_deterministic(owner_context: dict[str, Any]) -> None:
    _complete_test_ledger(owner_context)
    finalization = solo.finalize_owner_solo_qrels(owner_context)
    first = solo.compute_owner_solo_metrics(owner_context)
    second = solo.compute_owner_solo_metrics(owner_context)

    assert finalization["qrels"]["status"] == solo.FINAL_QREL_STATUS
    assert first == second
    assert first["metric_label"] == "OWNER_SOLO_PROVISIONAL — NOT INDEPENDENT RELEASE EVIDENCE"
    assert first["aggregate"]["calibration"]["macro_mrr"] == 1.0


def test_finalized_qrel_ledger_cannot_be_edited(owner_context: dict[str, Any]) -> None:
    _complete_test_ledger(owner_context)
    solo.finalize_owner_solo_qrels(owner_context)
    item_ref, candidate_ref = next(iter(solo._visible_candidates(owner_context)))

    with pytest.raises(solo.OwnerSoloQrelError, match="are frozen"):
        solo.record_judgment(
            owner_context,
            item_ref=item_ref,
            candidate_ref=candidate_ref,
            grade=2,
            rationale="This temporary test event must not be recorded.",
        )


def test_metrics_reject_a_changed_finalized_ledger(owner_context: dict[str, Any]) -> None:
    _complete_test_ledger(owner_context)
    solo.finalize_owner_solo_qrels(owner_context)
    item_ref, candidate_ref = next(iter(solo._visible_candidates(owner_context)))
    solo._append_event(
        owner_context,
        solo._new_event(
            event_type="CORRECTION",
            item_ref=item_ref,
            candidate_ref=candidate_ref,
            grade=3,
            rationale="Temporary tamper-detection test event.",
            owner_identity=owner_context["policy"]["owner_reviewer"]["identity_ref"],
            prior_event_id="event-" + "0" * 32,
        ),
    )

    with pytest.raises(solo.OwnerSoloQrelError, match="append-only ledger binding mismatch"):
        solo.compute_owner_solo_metrics(owner_context)


def test_authoritative_contract_remains_two_reviewer() -> None:
    contract = _load(
        "src/apps_rg/evals/c03_graph_evidence_cluster_human_intake_contract.v1.json"
    )

    assert contract["human_authority"]["two_distinct_primary_humans_required"] is True
    assert contract["human_authority"]["distinct_human_adjudicator_required"] is True
