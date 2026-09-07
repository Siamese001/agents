from __future__ import annotations

import hashlib
import copy

from apps_rg.evals.owner_solo.c03_rendered_unit_qrel import (
    _collapse_competency_candidates,
    _rendered_resume_unit,
    append_human_judgments,
    build_blinded_packet,
    build_packet_successor_transition,
    finalize_owner_solo_qrels,
    freeze_blinded_packet,
    load_contract,
    readiness_receipt,
    reconcile_prior_labels,
    resolved_active_events,
    validate_frozen_packet,
    validate_registry,
)


def _candidate(index: int) -> dict[str, object]:
    text = f"Final, source-bound resume unit {index}"
    return {
        "rendered_unit_id": f"unit-{index}",
        "complete_rendered_resume_unit": text,
        "final_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "embedding_text_sha256": "a" * 64,
        "embedding_identity": f"bge-m3-vector-{index}",
        "frozen_ranking_identity_sha256": "b" * 64,
        "frozen_rank": 1,
        "source_assertion_ids": [f"fact-{index}"],
        "graph_bundle_ids": [f"bundle-{index}"],
    }


def _registry(contract: dict[str, object]) -> dict[str, object]:
    targets = [
        {"target_id": target_id, "split": "CALIBRATION" if position < 3 else "HOLDOUT"}
        for position, target_id in enumerate(contract["required_scope"]["target_ids"])
    ]
    cases = []
    index = 0
    for target in targets:
        for section in range(11):
            index += 1
            cases.append({"target_id": target["target_id"], "section_id": f"section-{section}", "target_context": "Target role context", "candidates": [_candidate(index)]})
    return {
        "schema_version": "apps_rg.owner_solo_rendered_unit_qrel_registry.v1",
        "status": "FROZEN_FOR_BLINDED_REVIEW",
        "targets": targets,
        "query_section_cases": cases,
        "candidate_judgment_count": index,
    }


def test_rendered_unit_registry_is_ready_only_with_full_bound_scope() -> None:
    contract = load_contract(".")
    receipt = readiness_receipt(_registry(contract), contract)
    assert receipt["status"] == "READY_FOR_BLINDED_OWNER_QREL_REVIEW"
    assert receipt["candidate_judgment_count"] == 66
    assert receipt["human_grades_created"] is False


def test_rendered_unit_registry_fails_closed_on_text_or_case_drift() -> None:
    contract = load_contract(".")
    registry = _registry(contract)
    case = registry["query_section_cases"][0]
    case["candidates"][0]["complete_rendered_resume_unit"] = "changed after digest"
    registry["query_section_cases"].pop()
    receipt = readiness_receipt(registry, contract)
    assert receipt["status"] == "BLOCKED_RENDERED_UNIT_QREL_BINDING"
    assert "CASE_DENOMINATOR" in receipt["issues"]
    assert "FINAL_TEXT_DIGEST" in receipt["issues"]


def test_packet_ledger_and_metrics_require_explicit_human_returns(tmp_path) -> None:
    contract = load_contract(".")
    registry = _registry(contract)
    packet, sealed = build_blinded_packet(registry, contract)
    submissions = [
        {"item_ref": item["item_ref"], "candidate_ref": item["candidates"][0]["candidate_ref"], "grade": 3, "rationale": "Direct fit"}
        for item in packet["items"]
    ]
    events = append_human_judgments(tmp_path / "ledger.jsonl", packet=packet, submissions=submissions)
    result = finalize_owner_solo_qrels(registry=registry, contract=contract, packet=packet, sealed_mapping=sealed, events=events)
    assert result["qrel_count"] == 66
    assert result["metrics"]["macro_recall_at_10"] == 1.0
    assert result["release_authorizing"] is False


def test_prior_label_reconciliation_preserves_grades_without_silent_transfer() -> None:
    contract = load_contract(".")
    registry = _registry(contract)
    registry["query_section_cases"][0]["target_id"] = "brown_brown_svp_it_strategy_innovation"
    registry["query_section_cases"][0]["section_id"] = "competencies"
    registry["query_section_cases"][0]["candidates"][0]["embedding_identity"] = "BAAI/bge-m3:graph_evidence_cluster:cluster-1"
    registry["query_section_cases"][0]["candidates"][0]["complete_rendered_resume_unit"] = "Prior final competency"
    registry["query_section_cases"][0]["candidates"][0]["final_text_sha256"] = hashlib.sha256(b"Prior final competency").hexdigest()
    prior = {
        "prior_labels": [{"calibration_id": 1, "evidence_candidate": "Different raw evidence", "grade": 3, "rationale": "Direct fit"}],
        "proposals": [{"calibration_id": 1, "status": "OWNER_CONFIRMATION_REQUIRED", "candidate_ref": "old-candidate"}],
    }
    sealed = {"cohorts": [{"reviewer_a": [{"candidates": [{"candidate_ref": "old-candidate", "cluster_id": "cluster-1"}]}]}]}
    receipt, queue = reconcile_prior_labels(prior_reconciliation=prior, registry=registry, w8_sealed_mapping=sealed)
    assert receipt["prior_human_label_count"] == 1
    assert receipt["same_graph_evidence_re_rate_candidates"] == 1
    assert receipt["formal_qrels_created"] == 0
    assert receipt["human_grades_transferred"] is False
    assert queue["items"][0]["reason"] == "SAME_GRAPH_EVIDENCE_DIFFERENT_REVIEW_UNIT"


def test_r3_freeze_hides_rank_and_binds_the_sealed_mapping() -> None:
    contract = load_contract(".")
    registry = _registry(contract)
    packet, sealed, receipt = freeze_blinded_packet(registry=registry, contract=contract)
    assert receipt["status"] == "R3_FROZEN_BLINDED_REVIEW_PACKET_READY"
    assert receipt["candidate_judgment_count"] == 66
    assert all("frozen_rank" not in candidate for item in packet["items"] for candidate in item["candidates"])
    assert validate_frozen_packet(registry=registry, contract=contract, packet=packet, sealed_mapping=sealed) == []
    packet["items"][0]["candidates"][0]["frozen_rank"] = 1
    assert "REVIEWER_VISIBLE_LEAKAGE" in validate_frozen_packet(registry=registry, contract=contract, packet=packet, sealed_mapping=sealed)


def test_final_bullet_excludes_graph_authoring_guidance() -> None:
    cluster = {
        "semantic_components": {
            "claim_action": "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities",
            "claim_outcome": "Frame as alliance GTM leadership: joint planning and 20% joint revenue growth only when selected.",
        }
    }
    assert _rendered_resume_unit(cluster, "ibm_bullets") == "• Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities."


def test_competency_review_uses_complete_governed_resume_surface() -> None:
    cluster = {
        "cluster_id": "cluster-agentic",
        "member_node_ids": ["skill_agentic_control_plane_design"],
        "linked_fact_ids": ["fact_engineering_platform_001"],
        "semantic_components": {
            "claim_action": "Internal graph action note",
            "claim_scope": "Agentic runtime architecture",
            "concrete_capabilities": ["raw internal capability note"],
        },
    }
    bundles = [
        {
            "competency_bundle_id": "ccb_agentic_platforms",
            "display_label_candidate": "Governed Agentic AI Platform Architecture",
            "graph_skill_node_ids": ["skill_agentic_control_plane_design"],
            "linked_source_fact_ids": ["fact_engineering_platform_001"],
            "role_episode_bindings": [],
            "vocabulary_anchors": [
                "governed multi-agent orchestration control planes",
                "agentic workflow routing across enterprise systems",
            ],
            "allowed_sections": ["competencies"],
            "activation_status": "ACTIVE",
        }
    ]
    rendered = _rendered_resume_unit(cluster, "competencies", bundles)
    assert rendered == (
        "Governed Agentic AI Platform Architecture: governed multi-agent orchestration control planes, "
        "agentic workflow routing across enterprise systems"
    )
    assert "note" not in rendered.casefold()


def test_competency_candidates_collapse_to_one_question_per_final_line() -> None:
    first = _candidate(1)
    first.update(
        {
            "complete_rendered_resume_unit": "Governed AI: control gates, audit trails",
            "final_text_sha256": hashlib.sha256(b"Governed AI: control gates, audit trails").hexdigest(),
            "competency_bundle_id": "ccb-governed-ai",
            "frozen_rank": 2,
            "graph_bundle_ids": ["cluster-a"],
        }
    )
    second = copy.deepcopy(first)
    second.update(
        {
            "rendered_unit_id": "unit-2",
            "embedding_identity": "bge-m3-vector-2",
            "frozen_rank": 5,
            "source_assertion_ids": ["fact-2"],
            "graph_bundle_ids": ["cluster-b"],
        }
    )
    collapsed = _collapse_competency_candidates(
        target_id="target",
        section_id="competencies",
        candidates=[second, first],
    )
    assert len(collapsed) == 1
    assert collapsed[0]["frozen_rank"] == 1
    assert collapsed[0]["best_constituent_frozen_rank"] == 2
    assert collapsed[0]["graph_bundle_ids"] == ["cluster-a", "cluster-b"]
    assert collapsed[0]["supporting_cluster_count"] == 2


def test_registry_rejects_duplicate_visible_question_within_target_section() -> None:
    contract = load_contract(".")
    registry = _registry(contract)
    duplicate = copy.deepcopy(registry["query_section_cases"][0]["candidates"][0])
    duplicate["rendered_unit_id"] = "different-unit-id"
    duplicate["frozen_rank"] = 2
    registry["query_section_cases"][0]["candidates"].append(duplicate)
    registry["candidate_judgment_count"] += 1
    assert "DUPLICATE_FINAL_REVIEW_UNIT" in validate_registry(registry, contract)


def test_chained_successor_preserves_ancestor_events_without_copying_grades(tmp_path) -> None:
    contract = load_contract(".")
    first_registry = _registry(contract)
    first_packet, first_sealed, _ = freeze_blinded_packet(registry=first_registry, contract=contract)
    first_events = append_human_judgments(
        tmp_path / "first.jsonl",
        packet=first_packet,
        submissions=[
            {
                "item_ref": first_packet["items"][0]["item_ref"],
                "candidate_ref": first_packet["items"][0]["candidates"][0]["candidate_ref"],
                "grade": 3,
                "rationale": "Direct fit",
            }
        ],
    )
    second_registry = copy.deepcopy(first_registry)
    second_packet, second_sealed, _ = freeze_blinded_packet(registry=second_registry, contract=contract)
    first_transition = build_packet_successor_transition(
        predecessor_packet=first_packet,
        predecessor_sealed_mapping=first_sealed,
        predecessor_events=first_events,
        successor_packet=second_packet,
        successor_sealed_mapping=second_sealed,
    )
    second_active = resolved_active_events(
        successor_packet=second_packet,
        successor_events=[],
        transition=first_transition,
        predecessor_packet=first_packet,
        predecessor_events=first_events,
    )
    third_registry = copy.deepcopy(second_registry)
    third_packet, third_sealed, _ = freeze_blinded_packet(registry=third_registry, contract=contract)
    second_transition = build_packet_successor_transition(
        predecessor_packet=second_packet,
        predecessor_sealed_mapping=second_sealed,
        predecessor_events=[],
        predecessor_active_events=second_active,
        successor_packet=third_packet,
        successor_sealed_mapping=third_sealed,
    )
    third_active = resolved_active_events(
        successor_packet=third_packet,
        successor_events=[],
        transition=second_transition,
        predecessor_packet=second_packet,
        predecessor_events=[],
        predecessor_active_events=second_active,
    )
    assert len(third_active) == 1
    assert next(iter(third_active.values()))["event_id"] == first_events[0]["event_id"]
    assert second_transition["human_grades_created"] is False
    assert second_transition["human_grades_transferred"] is False


def test_successor_packet_carries_only_unchanged_human_judgments(tmp_path) -> None:
    contract = load_contract(".")
    predecessor_registry = _registry(contract)
    predecessor_packet, predecessor_sealed, _ = freeze_blinded_packet(registry=predecessor_registry, contract=contract)
    predecessor_events = append_human_judgments(
        tmp_path / "predecessor.jsonl",
        packet=predecessor_packet,
        submissions=[
            {"item_ref": predecessor_packet["items"][0]["item_ref"], "candidate_ref": predecessor_packet["items"][0]["candidates"][0]["candidate_ref"], "grade": 2, "rationale": "Supporting"},
            {"item_ref": predecessor_packet["items"][1]["item_ref"], "candidate_ref": predecessor_packet["items"][1]["candidates"][0]["candidate_ref"], "grade": 0, "rationale": "Wrong review text"},
        ],
    )
    successor_registry = copy.deepcopy(predecessor_registry)
    changed = successor_registry["query_section_cases"][1]["candidates"][0]
    changed["complete_rendered_resume_unit"] = "Corrected final resume unit"
    changed["final_text_sha256"] = hashlib.sha256(b"Corrected final resume unit").hexdigest()
    successor_packet, successor_sealed, _ = freeze_blinded_packet(registry=successor_registry, contract=contract)
    transition = build_packet_successor_transition(
        predecessor_packet=predecessor_packet,
        predecessor_sealed_mapping=predecessor_sealed,
        predecessor_events=predecessor_events,
        successor_packet=successor_packet,
        successor_sealed_mapping=successor_sealed,
    )
    assert transition["byte_identical_carried_forward_count"] == 1
    assert transition["prior_events_requiring_explicit_regrade_count"] == 1
    active = resolved_active_events(
        successor_packet=successor_packet,
        successor_events=[],
        transition=transition,
        predecessor_packet=predecessor_packet,
        predecessor_events=predecessor_events,
    )
    assert len(active) == 1
