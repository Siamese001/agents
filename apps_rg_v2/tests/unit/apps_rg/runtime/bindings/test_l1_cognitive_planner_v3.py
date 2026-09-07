"""Regression and QA tests for the capability-first L1 cognitive planner."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest

from apps_rg.runtime.bindings.l1_binding import l1_plan_apps_rg
from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import (
    L1CognitivePlanError,
    _build_l1_cognitive_revision_from_validated_c0_outcomes,
    build_l1_cognitive_plan_v3,
    cognitive_plan_digest,
    cognitive_revision_digest,
    validate_l1_cognitive_plan_v3,
    validate_l1_cognitive_revision_v3,
)
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1_COGNITIVE_V3_CANDIDATE_ARM,
    build_l1_cognitive_treatment,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.spine_contracts import ValidatedRequest


def _profile_manifest() -> dict[str, str]:
    return {
        "l1_planning_profile_ref": l1_planning_profile_ref(),
        "l1_planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
        "manifest_digest": "f" * 64,
    }


def _payload(
    jd_text: str,
    *,
    conflicts: bool = False,
    user_constraints: dict[str, Any] | None = None,
    output_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints: dict[str, Any] = {"output_format": "executive_resume"}
    if conflicts:
        constraints["conflicting_scope"] = "product and engineering ownership conflict"
    if user_constraints:
        constraints.update(user_constraints)
    return {
        "non_product_certified": True,
        "target_company": "Acme Corp",
        "target_role": "VP Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": jd_text,
        "source_resume_text": "Built governed AI infrastructure.",
        "generation_mode": "strategic_tailor",
        "task_spec": {
            "generation_mode": "strategic_tailor",
            "task_class": "resume_generation",
        },
        "query_spec": {"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        "support_expectation": {},
        "output_expectation": {},
        "profile_manifest": _profile_manifest(),
        "user_constraints": constraints,
        "output_preferences": dict(output_preferences or {}),
    }


def _plan(
    jd_text: str,
    *,
    conflicts: bool = False,
    user_constraints: dict[str, Any] | None = None,
    output_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return dict(
        build_l1_cognitive_plan_v3(
            app_payload=_payload(
                jd_text,
                conflicts=conflicts,
                user_constraints=user_constraints,
                output_preferences=output_preferences,
            ),
            request_id="req-l1-cognitive-v3",
            run_id="run-l1-cognitive-v3",
            trace_id="trace-l1-cognitive-v3",
            replay_key="replay-l1-cognitive-v3",
            planning_profile_ref=l1_planning_profile_ref(),
            planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
        )
    )


def _refresh_plan(plan: dict[str, Any]) -> None:
    plan["plan_digest"] = cognitive_plan_digest(plan)


def _sha256(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
    )


def _refresh_atomic_requirement_graph(graph: dict[str, Any]) -> None:
    body = dict(graph)
    body.pop("graph_digest", None)
    graph["graph_digest"] = _sha256(body)


def _refresh_ledger(ledger: dict[str, Any]) -> None:
    body = dict(ledger)
    body.pop("ledger_digest", None)
    ledger["ledger_digest"] = _sha256(body)


def _mutable(value: Any) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def _constraint_slot(
    frame: dict[str, Any],
    *,
    key: str,
    input_origin: str = "USER_CONSTRAINT",
) -> dict[str, Any]:
    source_key_digest = _sha256({"input_origin": input_origin, "source_key": key})
    return next(
        row
        for row in frame["constraint_slots"]
        if row["source_key_digest"] == source_key_digest
    )


def test_qa_atomic_decomposition_creates_related_requirements_without_raw_jd() -> None:
    jd_text = "Requirements\n- Must lead AI strategy and own platform governance."
    first = _plan(jd_text)
    second = _plan(jd_text)

    assert first == second
    requirements = first["atomic_requirement_graph"]["requirements"]
    assert len(requirements) == 2
    assert {row["coverage_status"] for row in requirements} == {"MAPPED"}
    assert first["atomic_requirement_graph"]["relations"]
    assert first["atomic_requirement_graph"]["relations"][0]["relation"] == "AND"
    rendered = json.dumps(first, sort_keys=True)
    assert "Must lead AI strategy" not in rendered
    assert "platform governance" not in rendered
    validate_l1_cognitive_plan_v3(first)


def test_qa_shared_predicate_split_preserves_atomic_source_scope() -> None:
    plan = _plan(
        "Requirements\n- Must lead platform engineering and delivery operations."
    )
    requirements = sorted(
        plan["atomic_requirement_graph"]["requirements"],
        key=lambda row: row["ordinal"],
    )

    assert [row["decomposition_mode"] for row in requirements] == [
        "EXPLICIT_PREDICATE",
        "INHERITED_PREDICATE",
    ]
    assert requirements[1]["inherited_predicate_class"] == "LEADERSHIP_ACTION"
    assert (
        requirements[0]["source_span"]["end_offset"]
        < requirements[1]["source_span"]["start_offset"]
    )
    assert plan["atomic_requirement_graph"]["relations"] == [
        {
            "from_requirement_id": requirements[0]["requirement_id"],
            "to_requirement_id": requirements[1]["requirement_id"],
            "relation": "AND",
            "relation_scope": "CONJUNCTIVE",
        }
    ]
    assert plan["planning_status"] == "READY"


@pytest.mark.parametrize(
    ("jd_text", "expected_modes", "expected_predicate_classes"),
    [
        (
            "Requirements\n- Must lead platform engineering and delivery operations and security governance.",
            [
                "EXPLICIT_PREDICATE",
                "INHERITED_PREDICATE",
                "INHERITED_PREDICATE",
            ],
            ["UNSPECIFIED_ACTION", "LEADERSHIP_ACTION", "LEADERSHIP_ACTION"],
        ),
        (
            "Requirements\n- Must lead platform engineering and own delivery operations and security governance.",
            [
                "EXPLICIT_PREDICATE",
                "EXPLICIT_PREDICATE",
                "INHERITED_PREDICATE",
            ],
            ["UNSPECIFIED_ACTION", "UNSPECIFIED_ACTION", "LEADERSHIP_ACTION"],
        ),
    ],
)
def test_qa_complete_safe_coordination_chain_is_fully_atomic(
    jd_text: str,
    expected_modes: list[str],
    expected_predicate_classes: list[str],
) -> None:
    plan = _plan(jd_text)
    requirements = sorted(
        plan["atomic_requirement_graph"]["requirements"],
        key=lambda row: row["ordinal"],
    )

    assert len(requirements) == 3
    assert [row["decomposition_mode"] for row in requirements] == expected_modes
    assert [row["inherited_predicate_class"] for row in requirements] == (
        expected_predicate_classes
    )
    assert all(row["coverage_status"] == "MAPPED" for row in requirements)
    assert all(
        requirements[index]["source_span"]["end_offset"]
        < requirements[index + 1]["source_span"]["start_offset"]
        for index in range(len(requirements) - 1)
    )
    assert [row["relation"] for row in plan["atomic_requirement_graph"]["relations"]] == [
        "AND",
        "AND",
    ]
    validate_l1_cognitive_plan_v3(plan)


@pytest.mark.parametrize(
    "jd_text",
    [
        "Requirements\n- Must lead teams and compliance and operations.",
        "Requirements\n- Must lead platform engineering and delivery operations or security governance.",
    ],
)
def test_qa_unsafe_coordination_chain_never_partially_targets(jd_text: str) -> None:
    plan = _plan(jd_text)
    requirements = plan["atomic_requirement_graph"]["requirements"]

    assert len(requirements) == 1
    assert requirements[0]["decomposition_mode"] == "AMBIGUOUS_COORDINATION_PRESERVED"
    assert requirements[0]["coverage_status"] == "ESCALATED"
    assert plan["atomic_requirement_graph"]["relations"] == []
    assert plan["planning_status"] == "BLOCKED"


def test_qa_chained_or_relation_preserves_every_alternative_for_review() -> None:
    plan = _plan(
        "Requirements\n- Must lead platform engineering or delivery operations or security governance."
    )
    requirements = sorted(
        plan["atomic_requirement_graph"]["requirements"],
        key=lambda row: row["ordinal"],
    )

    assert len(requirements) == 3
    assert all(row["coverage_status"] == "ESCALATED" for row in requirements)
    assert all(
        row["escalation_reason"] == "RELATION_SCOPE_REVIEW_REQUIRED"
        for row in requirements
    )
    assert [row["relation"] for row in plan["atomic_requirement_graph"]["relations"]] == [
        "OR",
        "OR",
    ]
    validate_l1_cognitive_plan_v3(plan)


def test_qa_explicit_sentences_in_one_bullet_become_related_atomic_requirements() -> (
    None
):
    plan = _plan(
        "Requirements\n- Must lead AI platform strategy. Must own platform governance."
    )
    requirements = sorted(
        plan["atomic_requirement_graph"]["requirements"],
        key=lambda row: row["ordinal"],
    )

    assert len(requirements) == 2
    assert [row["decomposition_mode"] for row in requirements] == [
        "EXPLICIT_SENTENCE_PREDICATE",
        "EXPLICIT_SENTENCE_PREDICATE",
    ]
    assert all(row["coverage_status"] == "MAPPED" for row in requirements)
    assert plan["atomic_requirement_graph"]["relations"] == [
        {
            "from_requirement_id": requirements[0]["requirement_id"],
            "to_requirement_id": requirements[1]["requirement_id"],
            "relation": "AND",
            "relation_scope": "CONJUNCTIVE",
        }
    ]
    assert (
        requirements[0]["source_span"]["end_offset"]
        < requirements[1]["source_span"]["start_offset"]
    )
    validate_l1_cognitive_plan_v3(plan)


def test_qa_ambiguous_coordination_is_preserved_and_escalated() -> None:
    plan = _plan("Requirements\n- Experience with product strategy and operations.")
    requirements = plan["atomic_requirement_graph"]["requirements"]

    assert len(requirements) == 1
    assert requirements[0]["decomposition_mode"] == "AMBIGUOUS_COORDINATION_PRESERVED"
    assert requirements[0]["coverage_status"] == "ESCALATED"
    assert plan["atomic_requirement_graph"]["relations"] == []
    assert plan["planning_status"] == "BLOCKED"


def test_known_but_ambiguous_coordination_is_not_opportunistically_targeted() -> None:
    plan = _plan("Requirements\n- Must lead teams and compliance.")
    requirement = plan["atomic_requirement_graph"]["requirements"][0]

    assert requirement["requirement_type"] != "UNKNOWN"
    assert requirement["decomposition_mode"] == "AMBIGUOUS_COORDINATION_PRESERVED"
    assert requirement["coverage_status"] == "ESCALATED"
    assert requirement["escalation_reason"] == "AMBIGUOUS_COORDINATION_REVIEW_REQUIRED"
    assert plan["planning_status"] == "BLOCKED"


def test_qa_conditional_relation_never_targets_an_arbitrary_clause() -> None:
    plan = _plan(
        "Requirements\n- Must lead platform strategy or own infrastructure governance."
    )
    requirements = plan["atomic_requirement_graph"]["requirements"]
    decisions = plan["alternative_plan_ledger"]["decisions"]

    assert {row["coverage_status"] for row in requirements} == {"ESCALATED"}
    assert {row["escalation_reason"] for row in requirements} == {
        "RELATION_SCOPE_REVIEW_REQUIRED"
    }
    assert all(not row["target_unit_ids"] for row in requirements)
    assert {
        row["relation"] for row in plan["atomic_requirement_graph"]["relations"]
    } == {"OR"}
    assert all(row["tradeoff_present"] is False for row in decisions)
    assert all(
        row["selection_rule"] == "NO_SEMANTICALLY_DEFENSIBLE_TARGET_ESCALATE"
        for row in decisions
    )


def test_qa_generic_hard_requirement_is_unknown_and_escalated() -> None:
    plan = _plan("Requirements\n- Must demonstrate quantum-superiority governance.")
    requirement = plan["atomic_requirement_graph"]["requirements"][0]

    assert requirement["requirement_type"] == "UNKNOWN"
    assert requirement["coverage_status"] == "ESCALATED"
    assert plan["planning_status"] == "BLOCKED"
    assert plan["critique_ledger"]["findings"]


def test_atomic_requirement_records_when_its_v2_parent_is_not_c0_eligible() -> None:
    plan = _plan("Requirements\n- Must lead AI strategy and own platform governance.")
    requirement = plan["atomic_requirement_graph"]["requirements"][0]

    assert requirement["parent_coverage_status"] == "ESCALATED"
    assert requirement["parent_c0_obligation_eligible"] is False
    assert requirement["coverage_status"] == "MAPPED"
    validate_l1_cognitive_plan_v3(plan)


def test_feasibility_ledger_compares_a_conditional_target_with_safe_fallback() -> None:
    plan = _plan("Requirements\n- Must lead platform engineering.")
    requirement = plan["atomic_requirement_graph"]["requirements"][0]
    requirement_id = requirement["requirement_id"]
    options = [
        row
        for row in plan["feasibility_graph"]["options"]
        if row["requirement_id"] == requirement_id
    ]
    target = next(row for row in options if row["option_kind"] == "TARGET_WORK_UNIT")
    escalation = next(row for row in options if row["option_kind"] == "ESCALATE")
    decision = next(
        row
        for row in plan["alternative_plan_ledger"]["decisions"]
        if row["requirement_id"] == requirement_id
    )

    assert "C0_EVIDENCE_OUTCOME_REQUIRED" in target["precondition_codes"]
    assert target["counterevidence_check_required"] is True
    assert decision["primary_option_id"] == target["option_id"]
    assert decision["alternative_option_id"] == escalation["option_id"]
    assert decision["tradeoff_present"] is True
    assert decision["selection_rule"] == "CONDITIONAL_TARGET_REQUIRES_C0_OUTCOME"


def test_critique_challenges_same_type_atoms_sharing_one_target() -> None:
    plan = _plan(
        "Requirements\n- Must lead platform engineering and lead delivery operations."
    )
    requirements = plan["atomic_requirement_graph"]["requirements"]

    assert len(requirements) == 2
    assert {row["requirement_type"] for row in requirements} == {"LEADERSHIP"}
    assert {tuple(row["target_unit_ids"]) for row in requirements} == {
        ("experience_block",)
    }
    collision_findings = [
        row
        for row in plan["critique_ledger"]["findings"]
        if row["code"] == "BROAD_TARGET_COLLISION_REQUIRES_DISTINCT_COVERAGE"
    ]
    assert {row["requirement_id"] for row in collision_findings} == {
        row["requirement_id"] for row in requirements
    }
    assert all(row["severity"] == "MEDIUM" for row in collision_findings)


def test_validator_rejects_redigested_decorative_alternative_choice() -> None:
    plan = _plan("Requirements\n- Must lead platform engineering.")
    tampered = _mutable(plan)
    decision = tampered["alternative_plan_ledger"]["decisions"][0]
    escalation = next(
        row
        for row in tampered["feasibility_graph"]["options"]
        if row["option_kind"] == "ESCALATE"
    )
    decision.update(
        {
            "primary_option_id": escalation["option_id"],
            "alternative_option_id": "",
            "decision": "ESCALATED",
            "tradeoff_present": False,
            "selection_rule": "NO_SEMANTICALLY_DEFENSIBLE_TARGET_ESCALATE",
            "required_preconditions": escalation["precondition_codes"],
            "counterevidence_risk_codes": escalation["counterevidence_risk_codes"],
            "risk": "SEMANTIC_REVIEW_REQUIRED",
            "rationale_code": escalation["rationale_code"],
            "assumption_id": escalation["assumption_id"],
            "assumption_code": escalation["assumption_code"],
        }
    )
    decision_body = dict(decision)
    decision_body.pop("decision_id", None)
    decision["decision_id"] = (
        "l1decide-" + _sha256(decision_body).removeprefix("sha256:")[:16]
    )
    _refresh_ledger(tampered["alternative_plan_ledger"])
    _refresh_plan(tampered)

    with pytest.raises(L1CognitivePlanError, match="does not match feasibility"):
        validate_l1_cognitive_plan_v3(tampered)


def test_validator_rejects_redigested_unjustified_critique() -> None:
    plan = _plan("Requirements\n- Must lead AI strategy and own platform governance.")
    tampered = _mutable(plan)
    finding = next(
        row
        for row in tampered["critique_ledger"]["findings"]
        if row["code"] == "C0_PARENT_OBLIGATION_PRECONDITION_MISSING"
    )
    finding["resolver"] = "PA"
    finding_body = dict(finding)
    finding_body.pop("finding_id", None)
    finding["finding_id"] = (
        "l1crit-" + _sha256(finding_body).removeprefix("sha256:")[:16]
    )
    _refresh_ledger(tampered["critique_ledger"])
    _refresh_plan(tampered)

    with pytest.raises(L1CognitivePlanError, match="does not match selected plan"):
        validate_l1_cognitive_plan_v3(tampered)


def test_qa_critique_blocks_declared_constraint_conflict() -> None:
    plan = _plan("Requirements\n- Must lead platform engineering.", conflicts=True)

    codes = {row["code"] for row in plan["critique_ledger"]["findings"]}
    assert "DECLARED_CONSTRAINT_CONFLICT" in codes
    assert plan["planning_status"] == "BLOCKED"


def test_goal_constraint_slots_drive_safe_deliberation() -> None:
    plan = _plan(
        "Requirements\n- Must lead platform engineering.",
        user_constraints={
            "max_pages": 2,
            "exclude_first_person": True,
            "tone": "executive",
        },
        output_preferences={"max_words": 350},
    )

    frame = plan["goal_constraint_frame"]
    output_format = _constraint_slot(frame, key="output_format")
    assert output_format["semantic_kind"] == "OUTPUT_FORMAT"
    assert output_format["interpretation_status"] == "ACTIONABLE"
    assert output_format["directive_code"] == "EXECUTIVE_RESUME"
    assert output_format["downstream_handling"] == "PA_SAFE_CONSTRAINT_DIRECTIVE"
    max_pages = _constraint_slot(frame, key="max_pages")
    assert max_pages["numeric_limit"] == {
        "comparison": "MAXIMUM",
        "quantity": 2,
        "unit": "PAGES",
    }
    assert max_pages["directive_code"] == "MAXIMUM_PAGES"
    exclude_first_person = _constraint_slot(frame, key="exclude_first_person")
    assert exclude_first_person["directive_code"] == "FIRST_PERSON"
    assert exclude_first_person["polarity"] == "FORBID"
    tone = _constraint_slot(frame, key="tone")
    assert tone["classification"] == "PREFERENCE"
    assert tone["directive_code"] == "EXECUTIVE"
    output_preference = _constraint_slot(
        frame, key="max_words", input_origin="OUTPUT_PREFERENCE"
    )
    assert output_preference["classification"] == "PREFERENCE"
    assert output_preference["directive_code"] == "MAXIMUM_WORDS"
    assert output_preference["numeric_limit"] == {
        "comparison": "MAXIMUM",
        "quantity": 350,
        "unit": "WORDS",
    }
    assert frame["blocking_constraint_ids"] == []

    decisions = {
        row["constraint_id"]: row
        for row in plan["alternative_plan_ledger"]["constraint_decisions"]
    }
    assert all(
        decisions[slot["constraint_id"]]["primary_action"] == "PROJECT_SAFE_DIRECTIVE"
        for slot in frame["constraint_slots"]
        if slot["interpretation_status"] == "ACTIONABLE"
    )
    assert plan["planning_status"] == "READY"
    validate_l1_cognitive_plan_v3(plan)


def test_semantic_length_conflict_blocks_without_a_declared_conflict_marker() -> None:
    plan = _plan(
        "Requirements\n- Must lead platform engineering.",
        user_constraints={"min_pages": 2, "max_pages": 1},
    )

    frame = plan["goal_constraint_frame"]
    min_pages = _constraint_slot(frame, key="min_pages")
    max_pages = _constraint_slot(frame, key="max_pages")
    assert {
        min_pages["classification"],
        max_pages["classification"],
    } == {"HARD"}
    assert {row["code"] for row in frame["constraint_conflicts"]} == {
        "SEMANTIC_LENGTH_CONSTRAINT_CONFLICT"
    }
    assert set(frame["blocking_constraint_ids"]) == {
        min_pages["constraint_id"],
        max_pages["constraint_id"],
    }
    critique_codes = {row["code"] for row in plan["critique_ledger"]["findings"]}
    assert "SEMANTIC_LENGTH_CONSTRAINT_CONFLICT" in critique_codes
    assert "DECLARED_CONSTRAINT_CONFLICT" not in critique_codes
    decisions = {
        row["constraint_id"]: row
        for row in plan["alternative_plan_ledger"]["constraint_decisions"]
    }
    assert decisions[min_pages["constraint_id"]]["primary_action"] == ("ESCALATE_TO_U0")
    assert decisions[max_pages["constraint_id"]]["primary_action"] == ("ESCALATE_TO_U0")
    assert plan["planning_status"] == "BLOCKED"


@pytest.mark.parametrize(
    ("user_constraints", "constraint_keys"),
    [
        ({"output_format": ["resume", "json"]}, ["output_format"]),
        (
            {"output_format": "resume", "export_format": "json"},
            ["output_format", "export_format"],
        ),
    ],
)
def test_semantic_output_format_conflict_blocks_incompatible_hard_directives(
    user_constraints: dict[str, Any],
    constraint_keys: list[str],
) -> None:
    plan = _plan(
        "Requirements\n- Must lead platform engineering.",
        user_constraints=user_constraints,
    )
    frame = plan["goal_constraint_frame"]
    conflicting_slots = [
        _constraint_slot(frame, key=key) for key in constraint_keys
    ]

    assert {row["code"] for row in frame["constraint_conflicts"]} == {
        "SEMANTIC_OUTPUT_FORMAT_CONFLICT"
    }
    assert set(frame["blocking_constraint_ids"]) == {
        slot["constraint_id"] for slot in conflicting_slots
    }
    decisions = {
        row["constraint_id"]: row
        for row in plan["alternative_plan_ledger"]["constraint_decisions"]
    }
    assert all(
        decisions[slot["constraint_id"]]["primary_action"] == "ESCALATE_TO_U0"
        for slot in conflicting_slots
    )
    assert plan["planning_status"] == "BLOCKED"


def test_unknown_hard_constraint_blocks_without_retaining_its_raw_value() -> None:
    raw_constraint_key = "do-not-emit-this-arbitrary-user-key"
    raw_constraint_value = "do-not-emit-this-arbitrary-user-instruction"
    plan = _plan(
        "Requirements\n- Must lead platform engineering.",
        user_constraints={raw_constraint_key: raw_constraint_value},
    )

    slot = _constraint_slot(
        plan["goal_constraint_frame"],
        key=raw_constraint_key,
    )
    assert slot["semantic_kind"] == "UNKNOWN"
    assert slot["interpretation_status"] == "REVIEW_REQUIRED"
    assert slot["downstream_handling"] == "GOVERNED_U0_RESOLUTION"
    assert (
        slot["constraint_id"]
        in plan["goal_constraint_frame"]["blocking_constraint_ids"]
    )
    assert "HARD_CONSTRAINT_SEMANTIC_REVIEW_REQUIRED" in {
        row["code"] for row in plan["critique_ledger"]["findings"]
    }
    decision = next(
        row
        for row in plan["alternative_plan_ledger"]["constraint_decisions"]
        if row["constraint_id"] == slot["constraint_id"]
    )
    assert decision["primary_action"] == "ESCALATE_TO_U0"
    assert raw_constraint_key not in json.dumps(plan, sort_keys=True)
    assert raw_constraint_value not in json.dumps(plan, sort_keys=True)
    assert plan["planning_status"] == "BLOCKED"


def test_hard_constraint_overrides_conflicting_output_preference_without_blocking() -> (
    None
):
    plan = _plan(
        "Requirements\n- Must lead platform engineering.",
        user_constraints={"max_pages": 1},
        output_preferences={"min_pages": 2},
    )

    frame = plan["goal_constraint_frame"]
    hard = _constraint_slot(frame, key="max_pages")
    preference = _constraint_slot(
        frame, key="min_pages", input_origin="OUTPUT_PREFERENCE"
    )
    assert hard["interpretation_status"] == "ACTIONABLE"
    assert hard["directive_code"] == "MAXIMUM_PAGES"
    assert preference["interpretation_status"] == "DEFERRED_PREFERENCE"
    assert preference["directive_code"] == ""
    assert preference["numeric_limit"] is None
    assert preference["resolution_reason"] == "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT"
    assert frame["constraint_conflicts"] == []
    assert frame["blocking_constraint_ids"] == []
    decisions = {
        row["constraint_id"]: row
        for row in plan["alternative_plan_ledger"]["constraint_decisions"]
    }
    assert decisions[hard["constraint_id"]]["primary_action"] == (
        "PROJECT_SAFE_DIRECTIVE"
    )
    assert decisions[preference["constraint_id"]]["primary_action"] == (
        "OMIT_CONFLICTING_PREFERENCE"
    )
    assert "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT" in {
        row["code"] for row in plan["critique_ledger"]["findings"]
    }
    assert plan["planning_status"] == "READY"


def test_hard_output_format_overrides_conflicting_output_preference() -> None:
    plan = _plan(
        "Requirements\n- Must lead platform engineering.",
        user_constraints={"output_format": "resume"},
        output_preferences={"output_format": "json"},
    )
    frame = plan["goal_constraint_frame"]
    hard = _constraint_slot(frame, key="output_format")
    preference = _constraint_slot(
        frame,
        key="output_format",
        input_origin="OUTPUT_PREFERENCE",
    )

    assert hard["directive_code"] == "RESUME"
    assert hard["interpretation_status"] == "ACTIONABLE"
    assert preference["directive_code"] == ""
    assert preference["interpretation_status"] == "DEFERRED_PREFERENCE"
    assert preference["resolution_reason"] == "PREFERENCE_OVERRIDDEN_BY_HARD_CONSTRAINT"
    assert frame["constraint_conflicts"] == []
    decisions = {
        row["constraint_id"]: row
        for row in plan["alternative_plan_ledger"]["constraint_decisions"]
    }
    assert decisions[hard["constraint_id"]]["primary_action"] == (
        "PROJECT_SAFE_DIRECTIVE"
    )
    assert decisions[preference["constraint_id"]]["primary_action"] == (
        "OMIT_CONFLICTING_PREFERENCE"
    )
    assert plan["planning_status"] == "READY"


def test_revision_is_bounded_to_an_observed_requirement_and_never_retries() -> None:
    plan = _plan("Requirements\n- Must lead platform engineering.")
    requirement_id = plan["atomic_requirement_graph"]["requirements"][0][
        "requirement_id"
    ]
    revision = dict(
        _build_l1_cognitive_revision_from_validated_c0_outcomes(
            plan=plan,
            observed_outcomes=[
                {
                    "requirement_id": requirement_id,
                    "code": "C0_INSUFFICIENT",
                    "observation_ref": "receipts/c0_requirement.json",
                }
            ],
            c0_outcome_receipt_digest=_sha256("c0-outcome"),
        )
    )

    assert revision["status"] == "PROPOSED"
    assert revision["revision_scope_requirement_ids"] == [requirement_id]
    assert revision["c0_outcome_receipt_digest"] == _sha256("c0-outcome")
    change = revision["changes"][0]
    assert change["automatic_retry"] is False
    assert change["route_change"] is False
    assert change["revised_decision"] == "ESCALATED"
    assert change["action"] == "REPLACE_TARGET_WITH_ESCALATION"
    assert change["superseded_option_id"] != change["replacement_option_id"]
    assert (
        change["predicted_correction"] == "PREVENT_UNSUPPORTED_REQUIREMENT_SATISFACTION"
    )
    assert revision["parent_vs_revised_comparison"] == {
        "changed_requirement_count": 1,
        "unrelated_requirement_change_count": 0,
        "replacement_policy": "FAILED_ATOM_ONLY_TO_DECLARED_ESCALATION_OPTION",
        "predicted_safety_effect": "UNSUPPORTED_REQUIREMENT_CANNOT_REMAIN_SELECTED",
    }
    validate_l1_cognitive_revision_v3(revision, plan=plan)

    tampered = _mutable(revision)
    tampered["changes"][0]["route_change"] = True
    tampered["revision_digest"] = cognitive_revision_digest(tampered)
    with pytest.raises(L1CognitivePlanError, match="must remain advisory"):
        validate_l1_cognitive_revision_v3(tampered, plan=plan)

    tampered_fallback = _mutable(revision)
    fallback_change = tampered_fallback["changes"][0]
    fallback_change["replacement_option_id"] = fallback_change["superseded_option_id"]
    fallback_change_body = dict(fallback_change)
    fallback_change_body.pop("change_id", None)
    fallback_change["change_id"] = (
        "l1rev-" + _sha256(fallback_change_body).removeprefix("sha256:")[:16]
    )
    tampered_fallback["revision_digest"] = cognitive_revision_digest(tampered_fallback)
    with pytest.raises(L1CognitivePlanError, match="option delta is invalid"):
        validate_l1_cognitive_revision_v3(tampered_fallback, plan=plan)

    tampered_outcome = _mutable(revision)
    outcome_change = tampered_outcome["changes"][0]
    outcome_change["observed_outcome_code"] = "DOWNSTREAM_OMISSION"
    outcome_change_body = dict(outcome_change)
    outcome_change_body.pop("change_id", None)
    outcome_change["change_id"] = (
        "l1rev-" + _sha256(outcome_change_body).removeprefix("sha256:")[:16]
    )
    tampered_outcome["revision_digest"] = cognitive_revision_digest(tampered_outcome)
    with pytest.raises(L1CognitivePlanError, match="observed outcome code is invalid"):
        validate_l1_cognitive_revision_v3(tampered_outcome, plan=plan)

    tampered_reference = _mutable(revision)
    reference_change = tampered_reference["changes"][0]
    reference_change["observation_ref"] = "../unbound-outcome.json"
    reference_change_body = dict(reference_change)
    reference_change_body.pop("change_id", None)
    reference_change["change_id"] = (
        "l1rev-" + _sha256(reference_change_body).removeprefix("sha256:")[:16]
    )
    tampered_reference["revision_digest"] = cognitive_revision_digest(
        tampered_reference
    )
    with pytest.raises(L1CognitivePlanError, match="observation reference is invalid"):
        validate_l1_cognitive_revision_v3(tampered_reference, plan=plan)


def test_downstream_omission_is_not_an_arbitrary_l1_revision_trigger() -> None:
    plan = _plan("Requirements\n- Must lead platform engineering.")
    requirement_id = plan["atomic_requirement_graph"]["requirements"][0][
        "requirement_id"
    ]

    with pytest.raises(L1CognitivePlanError, match="observed outcome code is invalid"):
        _build_l1_cognitive_revision_from_validated_c0_outcomes(
            plan=plan,
            observed_outcomes=[
                {
                    "requirement_id": requirement_id,
                    "code": "DOWNSTREAM_OMISSION",
                    "observation_ref": "l2_output.json",
                }
            ],
            c0_outcome_receipt_digest=_sha256("c0-outcome"),
        )


def test_regression_binding_threads_v3_without_granting_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload("Requirements\n- Must lead platform engineering.")
    payload["task_spec"]["l1_cognitive_treatment"] = build_l1_cognitive_treatment(
        L1_COGNITIVE_V3_CANDIDATE_ARM,
        assignment_origin="U0_VALIDATED_INGRESS",
    )
    validated = ValidatedRequest(
        request_id="req-l1-cognitive-binding",
        run_id="run-l1-cognitive-binding",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-08-10T00:00:00+00:00"
        ),
        trace_id="trace-l1-cognitive-binding",
        tenant_id="tenant-l1-cognitive",
        replay_key="replay-l1-cognitive-binding",
        l5_certification_ref="test:valid:cognitive-v3",
        app_payload=payload,
    )
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "l1-cognitive-v3-test-secret")

    plan = l1_plan_apps_rg(validated)
    cognitive = plan.task_spec["apps_rg_cognitive_v3_plan"]

    assert cognitive["schema_version"] == "apps_rg.l1_cognitive_plan.v3"
    assert plan.task_spec["apps_rg_cognitive_v3_plan_ref"] == cognitive["plan_digest"]
    assert (
        plan.output_expectation["apps_rg_cognitive_v3_critique_ref"]
        == cognitive["critique_ledger"]["ledger_digest"]
    )
    assert any(
        ref.startswith("l1_cognitive_v3_plan_digest:") for ref in plan.audit_refs
    )
    assert cognitive["validation"]["no_model_call"] is True
    assert cognitive["validation"]["no_candidate_evidence_claim"] is True


def test_v3_plan_preserves_an_empty_optional_replay_key() -> None:
    plan = build_l1_cognitive_plan_v3(
        app_payload=_payload("Requirements\n- Must lead platform engineering."),
        request_id="req-l1-cognitive-empty-replay",
        run_id="run-l1-cognitive-empty-replay",
        trace_id="trace-l1-cognitive-empty-replay",
        replay_key="",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )

    assert plan["replay_key"] == ""
    validate_l1_cognitive_plan_v3(plan)


def test_v2_control_omits_v3_cognitive_plan_from_l1_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload("Requirements\n- Must lead platform engineering.")
    payload["task_spec"]["l1_cognitive_treatment"] = build_l1_cognitive_treatment(
        L1_COGNITIVE_V2_CONTROL_ARM,
        assignment_origin="U0_VALIDATED_INGRESS",
    )
    validated = ValidatedRequest(
        request_id="req-l1-cognitive-control",
        run_id="run-l1-cognitive-control",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-08-10T00:00:00+00:00"
        ),
        trace_id="trace-l1-cognitive-control",
        tenant_id="tenant-l1-cognitive",
        replay_key="replay-l1-cognitive-control",
        l5_certification_ref="test:valid:cognitive-v3",
        app_payload=payload,
    )
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "l1-cognitive-v3-test-secret")

    plan = l1_plan_apps_rg(validated)

    assert (
        plan.task_spec["l1_cognitive_treatment"]["arm"] == L1_COGNITIVE_V2_CONTROL_ARM
    )
    assert "apps_rg_cognitive_v3_plan" not in plan.task_spec
    assert "apps_rg_cognitive_v3_plan_ref" not in plan.task_spec
    assert "apps_rg_cognitive_v3_critique_ref" not in plan.output_expectation
    assert not any(
        ref.startswith("l1_cognitive_v3_plan_digest:") for ref in plan.audit_refs
    )


def test_unassigned_legacy_binding_stays_on_v2_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload("Requirements\n- Must lead platform engineering.")
    validated = ValidatedRequest(
        request_id="req-l1-cognitive-legacy-control",
        run_id="run-l1-cognitive-legacy-control",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-08-10T00:00:00+00:00"
        ),
        trace_id="trace-l1-cognitive-legacy-control",
        tenant_id="tenant-l1-cognitive",
        replay_key="replay-l1-cognitive-legacy-control",
        l5_certification_ref="test:valid:cognitive-v3",
        app_payload=payload,
    )
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "l1-cognitive-v3-test-secret")

    plan = l1_plan_apps_rg(validated)

    assert plan.task_spec["l1_cognitive_treatment"] == build_l1_cognitive_treatment(
        L1_COGNITIVE_V2_CONTROL_ARM,
        assignment_origin="LEGACY_L1_DEFAULT",
    )
    assert "apps_rg_cognitive_v3_plan" not in plan.task_spec
    assert "apps_rg_cognitive_v3_critique_ref" not in plan.output_expectation


def test_v3_candidate_keeps_v3_cognitive_plan_when_explicitly_assigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload("Requirements\n- Must lead platform engineering.")
    payload["task_spec"]["l1_cognitive_treatment"] = build_l1_cognitive_treatment(
        L1_COGNITIVE_V3_CANDIDATE_ARM,
        assignment_origin="U0_VALIDATED_INGRESS",
    )
    validated = ValidatedRequest(
        request_id="req-l1-cognitive-candidate",
        run_id="run-l1-cognitive-candidate",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-08-10T00:00:00+00:00"
        ),
        trace_id="trace-l1-cognitive-candidate",
        tenant_id="tenant-l1-cognitive",
        replay_key="replay-l1-cognitive-candidate",
        l5_certification_ref="test:valid:cognitive-v3",
        app_payload=payload,
    )
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "l1-cognitive-v3-test-secret")

    plan = l1_plan_apps_rg(validated)

    assert (
        plan.task_spec["l1_cognitive_treatment"]["arm"] == L1_COGNITIVE_V3_CANDIDATE_ARM
    )
    assert plan.task_spec["apps_rg_cognitive_v3_plan"]["schema_version"] == (
        "apps_rg.l1_cognitive_plan.v3"
    )


def test_validator_rejects_redigested_unknown_target_mapping() -> None:
    plan = _plan("Requirements\n- Must demonstrate quantum-superiority governance.")
    tampered = _mutable(plan)
    tampered["atomic_requirement_graph"]["requirements"][0]["coverage_status"] = (
        "MAPPED"
    )
    tampered["atomic_requirement_graph"]["requirements"][0]["target_unit_ids"] = [
        "experience_block"
    ]
    tampered["atomic_requirement_graph"]["requirements"][0]["escalation_reason"] = ""
    _refresh_atomic_requirement_graph(tampered["atomic_requirement_graph"])
    _refresh_plan(tampered)

    with pytest.raises(L1CognitivePlanError, match="unknown requirement"):
        validate_l1_cognitive_plan_v3(tampered)
