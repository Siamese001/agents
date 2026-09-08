"""Downstream-consumption tests for the Apps RG L1 v3 cognitive plan."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any

try:
    import pytest
except ModuleNotFoundError:
    import re
    from contextlib import contextmanager

    class _PytestShim:
        @staticmethod
        @contextmanager
        def raises(expected_exception: Any, match: str | None = None) -> Any:
            try:
                yield
            except expected_exception as exc:
                if match:
                    pattern = getattr(match, "pattern", match)
                    assert re.search(pattern, str(exc)), (
                        f"Pattern '{pattern}' not found in exception message: '{exc}'"
                    )
            else:
                raise AssertionError(
                    f"Expected exception {expected_exception} was not raised"
                )

    pytest = _PytestShim()  # type: ignore[assignment]

from apps_rg.prompt_assembly.contracts import (
    EvidenceSource,
    PromptAssemblyError,
    PromptAssemblyInput,
)
from apps_rg.runtime.bindings.l1_cognitive_consumption import (
    L1CognitiveConsumptionError,
    build_l1_cognitive_consumer_advisory,
    build_l1_cognitive_revision_advisory,
    cognitive_advisory_prompt_lines,
    cognitive_consumer_advisory_digest,
    cognitive_revision_advisory_digest,
    validate_l1_cognitive_consumer_advisory_from_cognitive_plan,
)
from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import build_l1_cognitive_plan_v3
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    build_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.bindings.section_prompt_adapter import compile_section_prompt
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.dispatch.unify_ibm_pa_common import load_w7_shell_slot_bodies
from apps_rg.runtime.contracts.l1_cognitive_c0_outcome_receipt import (
    build_l1_cognitive_c0_outcome_receipt,
    build_l1_cognitive_revision_from_c0_outcome,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    build_l1_evidence_obligation_receipt,
)


def _payload(
    *,
    jd_text: str | None = None,
    user_constraints: dict[str, Any] | None = None,
    output_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "target_company": "Acme Corp",
        "target_role": "VP Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": jd_text
        or (
            "Requirements\n"
            "- Must have 10+ years of AI platform leadership.\n"
            "- Bachelor's degree in Computer Science."
        ),
        "source_resume_text": "Built governed AI infrastructure.",
        "generation_mode": "strategic_tailor",
        "task_spec": {"generation_mode": "strategic_tailor"},
        "query_spec": {"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        "support_expectation": {},
        "output_expectation": {},
        "user_constraints": dict(user_constraints or {}),
        "output_preferences": dict(output_preferences or {}),
    }


def _cognitive_plan(
    *,
    jd_text: str | None = None,
    user_constraints: dict[str, Any] | None = None,
    output_preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return dict(
        build_l1_cognitive_plan_v3(
            app_payload=_payload(
                jd_text=jd_text,
                user_constraints=user_constraints,
                output_preferences=output_preferences,
            ),
            request_id="cognitive-consumer-request",
            run_id="cognitive-consumer-run",
            trace_id="cognitive-consumer-trace",
            replay_key="cognitive-consumer-replay",
            planning_profile_ref=l1_planning_profile_ref(),
            planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
        )
    )


def _l1_contract(cognitive_plan: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        task_spec={
            "apps_rg_cognitive_v3_plan": cognitive_plan,
            "apps_rg_cognitive_v3_plan_ref": cognitive_plan["plan_digest"],
        }
    )


def _c0_bound_revision(
    cognitive: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    v2 = dict(
        build_apps_rg_l1_planning_capsule_v2(
            app_payload=_payload(),
            request_id="cognitive-consumer-request",
            run_id="cognitive-consumer-run",
            trace_id="cognitive-consumer-trace",
            replay_key="cognitive-consumer-replay",
            planning_profile_ref=l1_planning_profile_ref(),
            planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
        )
    )
    c0 = build_l1_evidence_obligation_receipt(
        capsule=v2,
        request_id="cognitive-consumer-request",
        run_id="cognitive-consumer-run",
        trace_id="cognitive-consumer-trace",
        final_evidence_digest="sha256:" + "9" * 64,
        evidence_items=[],
    )
    outcome = build_l1_cognitive_c0_outcome_receipt(
        cognitive_plan=cognitive,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )
    revision = build_l1_cognitive_revision_from_c0_outcome(
        cognitive_plan=cognitive,
        outcome_receipt=outcome,
        outcome_receipt_ref="l1_cognitive_c0_outcome_receipt.json",
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )
    advisory = build_l1_cognitive_revision_advisory(
        cognitive_plan=cognitive,
        revision=revision,
        c0_outcome_receipt_digest=outcome["receipt_digest"],
    )
    return revision, advisory


def _assembly_input() -> PromptAssemblyInput:
    slots = load_w7_shell_slot_bodies()
    return PromptAssemblyInput(
        template_id="strategic_tailor_v1",
        request_id="cognitive-consumer-request",
        run_id="cognitive-consumer-run",
        trace_root="cognitive-consumer-trace",
        s0_system_preamble=slots["S0"],
        d0_fences=slots["D0"],
        e0_examples=slots["E0"],
        y0_style_preferences=slots["Y0"],
        i0_instructions="Use only C0 candidate facts for claims.",
        c0_candidate_facts=EvidenceSource(
            source_type="candidate_facts",
            source_tag="candidate_facts",
            content="Candidate has platform leadership evidence.",
        ),
        c0_jd_requirements=EvidenceSource(
            source_type="jd_requirements",
            source_tag="jd_requirements",
            content="Targeting only; not claim proof.",
            confidence=0.0,
        ),
        u0_user_task="Create one grounded employment bullet.",
        r0_response_schema='{"type":"object"}',
    )


def test_advisory_is_source_bound_semantic_and_section_scoped() -> None:
    cognitive = _cognitive_plan()
    advisory = build_l1_cognitive_consumer_advisory(_l1_contract(cognitive))

    assert advisory is not None
    assert advisory["mapped_requirement_type_counts"] == {
        "CREDENTIAL": 1,
        "LEADERSHIP": 1,
    }
    experience_lines = cognitive_advisory_prompt_lines(
        advisory, section_id="ibm_bullets"
    )
    rendered_lines = "\n".join(experience_lines)
    leadership_slot = next(
        row
        for row in advisory["mapped_requirement_slots"]
        if row["requirement_type"] == "LEADERSHIP"
    )
    assert f"id={leadership_slot['requirement_id']}" in rendered_lines
    assert "type=LEADERSHIP" in rendered_lines
    assert "qualifiers=MINIMUM_YEARS=10" in rendered_lines
    assert "type=CREDENTIAL" not in rendered_lines
    # Lean debloat mode eliminates intrusive audit tags and cuts token footprint
    assert "L1_COGNITIVE_ATOM:" not in rendered_lines
    assert cognitive_advisory_prompt_lines(advisory, section_id="headline") == ()
    rendered = json.dumps(advisory, sort_keys=True)
    assert "10+ years of AI platform leadership" not in rendered
    assert "Bachelor's degree" not in rendered
    assert leadership_slot["raw_targeting_text_omitted"] is True
    assert leadership_slot["decision_risk"] == "COUNTEREVIDENCE_REQUIRED"
    assert leadership_slot["qualifier_scope"] == "LOCAL"
    assert (
        "C0_EVIDENCE_OUTCOME_REQUIRED" in leadership_slot["selected_precondition_codes"]
    )

    tampered = copy.deepcopy(advisory)
    tampered["mapped_requirement_type_counts"] = {"LEADERSHIP": 2}
    tampered["advisory_digest"] = cognitive_consumer_advisory_digest(tampered)
    with pytest.raises(L1CognitiveConsumptionError, match="does not match plan"):
        validate_l1_cognitive_consumer_advisory_from_cognitive_plan(
            tampered,
            cognitive_plan=cognitive,
        )


def test_goal_constraints_reach_pa_as_safe_directives_or_a_governed_gate() -> None:
    raw_constraint_value = "do-not-emit-this-arbitrary-user-instruction"
    cognitive = _cognitive_plan(
        user_constraints={
            "max_pages": 2,
            "exclude_first_person": True,
            "publication_rule": raw_constraint_value,
        },
        output_preferences={"max_words": 350},
    )
    advisory = build_l1_cognitive_consumer_advisory(_l1_contract(cognitive))

    assert advisory is not None
    directives = {
        row["directive_code"]: row for row in advisory["constraint_directives"]
    }
    assert directives["MAXIMUM_PAGES"]["numeric_limit"] == {
        "comparison": "MAXIMUM",
        "quantity": 2,
        "unit": "PAGES",
    }
    assert directives["FIRST_PERSON"]["polarity"] == "FORBID"
    assert directives["MAXIMUM_WORDS"]["numeric_limit"] == {
        "comparison": "MAXIMUM",
        "quantity": 350,
        "unit": "WORDS",
    }
    assert advisory["goal_constraint_blocked"] is True
    assert len(advisory["constraint_escalations"]) == 1
    escalation = advisory["constraint_escalations"][0]
    assert escalation["semantic_kind"] == "UNKNOWN"
    assert escalation["classification"] == "HARD"
    assert escalation["interpretation_status"] == "REVIEW_REQUIRED"
    assert escalation["risk"] == "SEMANTIC_REVIEW_REQUIRED"
    assert escalation["constraint_id"].startswith("l1constraint-")
    assert escalation["constraint_decision_id"].startswith("l1constraintdecision-")
    lines = cognitive_advisory_prompt_lines(advisory, section_id="ibm_bullets")
    rendered_lines = "\n".join(lines)
    assert "directive=MAXIMUM_PAGES" in rendered_lines
    assert "numeric_limit=MAXIMUM:2:PAGES" in rendered_lines
    assert "directive=FIRST_PERSON" in rendered_lines
    assert "directive=MAXIMUM_WORDS" in rendered_lines
    assert "require governed U0 resolution" in rendered_lines
    assert raw_constraint_value not in rendered_lines
    assert raw_constraint_value not in json.dumps(advisory, sort_keys=True)

    compiled = compile_section_prompt(
        _assembly_input(),
        section_id="ibm_bullets",
        l1_cognitive_advisory=advisory,
        l1_cognitive_plan=cognitive,
    )
    rendered_prompt = "\n".join(
        str(message.get("content") or "") for message in compiled.artifact.messages
    )
    assert "directive=MAXIMUM_PAGES" in rendered_prompt
    assert "require governed U0 resolution" in rendered_prompt
    assert raw_constraint_value not in rendered_prompt


def test_hard_goal_constraint_wins_over_conflicting_output_preference() -> None:
    cognitive = _cognitive_plan(
        user_constraints={"max_pages": 1},
        output_preferences={"min_pages": 2},
    )
    advisory = build_l1_cognitive_consumer_advisory(_l1_contract(cognitive))

    assert advisory is not None
    assert advisory["goal_constraint_blocked"] is False
    assert advisory["constraint_escalations"] == []
    assert advisory["deferred_preference_constraint_count"] == 1
    assert advisory["conflict_deferred_preference_constraint_count"] == 1
    assert {row["directive_code"] for row in advisory["constraint_directives"]} == {
        "MAXIMUM_PAGES"
    }
    lines = "\n".join(cognitive_advisory_prompt_lines(advisory, section_id="headline"))
    assert "directive=MAXIMUM_PAGES" in lines
    assert "directive=MINIMUM_PAGES" not in lines
    assert "L1 cognitive precedence:" in lines
    assert "min_pages" not in lines


def test_advisory_propagates_atomic_relation_and_shared_predicate_scope() -> None:
    cognitive = _cognitive_plan(
        jd_text=(
            "Requirements\n- Must lead platform engineering and delivery operations."
        )
    )
    advisory = build_l1_cognitive_consumer_advisory(_l1_contract(cognitive))

    assert advisory is not None
    slots = sorted(advisory["mapped_requirement_slots"], key=lambda row: row["ordinal"])
    assert [row["decomposition_mode"] for row in slots] == [
        "EXPLICIT_PREDICATE",
        "INHERITED_PREDICATE",
    ]
    assert slots[1]["inherited_predicate_class"] == "LEADERSHIP_ACTION"
    assert slots[0]["relation_context"] == [
        {
            "direction": "OUTGOING",
            "relation": "AND",
            "relation_scope": "CONJUNCTIVE",
            "related_requirement_id": slots[1]["requirement_id"],
        }
    ]
    lines = "\n".join(
        cognitive_advisory_prompt_lines(advisory, section_id="ibm_bullets")
    )
    # Debloat mode renders clean target requirements without internal parser markers
    assert "L1 target requirement:" in lines
    assert "decomposition=" not in lines
    assert "relations=" not in lines
    assert "platform engineering and delivery operations" not in lines

    # Legacy verbose mode preserves full relation context in prompt lines
    import os
    os.environ["APPS_RG_L1_PROMPT_DEBLOAT"] = "false"
    try:
        legacy_lines = "\n".join(
            cognitive_advisory_prompt_lines(advisory, section_id="ibm_bullets")
        )
        assert "decomposition=INHERITED_PREDICATE" in legacy_lines
        assert "relations=INCOMING:AND:CONJUNCTIVE:" in legacy_lines
    finally:
        os.environ.pop("APPS_RG_L1_PROMPT_DEBLOAT", None)


def test_section_prompt_receives_only_verified_relevant_cognitive_advisory() -> None:
    cognitive = _cognitive_plan()
    advisory = build_l1_cognitive_consumer_advisory(_l1_contract(cognitive))
    assert advisory is not None

    compiled = compile_section_prompt(
        _assembly_input(),
        section_id="ibm_bullets",
        l1_cognitive_advisory=advisory,
        l1_cognitive_plan=cognitive,
    )
    rendered = "\n".join(
        str(message.get("content") or "") for message in compiled.artifact.messages
    )
    assert "<L1_COGNITIVE_ADVISORY>" in rendered
    assert "L1 target requirement:" in rendered
    assert "type=LEADERSHIP" in rendered
    assert "L1_COGNITIVE_ATOM:" not in rendered
    assert "10+ years of AI platform leadership" not in rendered

    tampered = copy.deepcopy(advisory)
    tampered["mapped_requirement_count"] = 99
    tampered["advisory_digest"] = cognitive_consumer_advisory_digest(tampered)
    with pytest.raises(PromptAssemblyError, match="L1_COGNITIVE_BINDING_INVALID"):
        compile_section_prompt(
            _assembly_input(),
            section_id="ibm_bullets",
            l1_cognitive_advisory=tampered,
            l1_cognitive_plan=cognitive,
        )


def test_section_prompt_receives_c0_bound_revision_and_rejects_redigested_tampering() -> (
    None
):
    cognitive = _cognitive_plan()
    advisory = build_l1_cognitive_consumer_advisory(_l1_contract(cognitive))
    assert advisory is not None
    revision, revision_advisory = _c0_bound_revision(cognitive)

    compiled = compile_section_prompt(
        _assembly_input(),
        section_id="ibm_bullets",
        l1_cognitive_advisory=advisory,
        l1_cognitive_plan=cognitive,
        l1_cognitive_revision=revision,
        l1_cognitive_revision_advisory=revision_advisory,
    )
    rendered = "\n".join(
        str(message.get("content") or "") for message in compiled.artifact.messages
    )
    assert "<L1_COGNITIVE_C0_REVISION>" in rendered
    revision_slot = next(
        row
        for row in revision_advisory["affected_requirement_slots"]
        if row["requirement_type"] == "LEADERSHIP"
    )
    assert revision_slot["required_gap_tag"] in rendered
    assert "do not compensate for a C0 gap" in rendered
    assert "10+ years of AI platform leadership" not in rendered

    tampered = copy.deepcopy(revision_advisory)
    tampered["affected_requirement_count"] = 99
    tampered["advisory_digest"] = cognitive_revision_advisory_digest(tampered)
    with pytest.raises(
        PromptAssemblyError, match="L1_COGNITIVE_REVISION_BINDING_INVALID"
    ):
        compile_section_prompt(
            _assembly_input(),
            section_id="ibm_bullets",
            l1_cognitive_advisory=advisory,
            l1_cognitive_plan=cognitive,
            l1_cognitive_revision=revision,
            l1_cognitive_revision_advisory=tampered,
        )


def test_revision_advisory_requires_the_revision_c0_outcome_binding() -> None:
    cognitive = _cognitive_plan()
    revision, _advisory = _c0_bound_revision(cognitive)

    with pytest.raises(
        L1CognitiveConsumptionError, match="revision C0 outcome binding is invalid"
    ):
        build_l1_cognitive_revision_advisory(
            cognitive_plan=cognitive,
            revision=revision,
            c0_outcome_receipt_digest="sha256:" + "0" * 64,
        )


def test_advisory_never_projects_conflicting_hard_output_formats() -> None:
    cognitive = _cognitive_plan(
        user_constraints={"output_format": "resume", "export_format": "json"}
    )
    advisory = build_l1_cognitive_consumer_advisory(_l1_contract(cognitive))

    assert advisory is not None
    assert advisory["goal_constraint_blocked"] is True
    assert advisory["constraint_directives"] == []
    assert len(advisory["constraint_escalations"]) == 2
    assert {
        row["semantic_kind"] for row in advisory["constraint_escalations"]
    } == {"OUTPUT_FORMAT"}
