"""Unit tests for Wave 2 L0 route-hint unblock and C0 semantic query binding."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from apps_rg.runtime.bindings.c0_planned_binding import (
    C0RetrievalPlan,
    build_c0_retrieval_plan,
    c0_retrieve_apps_rg_planned,
)
from apps_rg.runtime.bindings.l0_binding import (
    _ALL_SIX_L1_ROUTE_HINT_KEYS,
    _condition_value,
    l0_route_apps_rg,
    reset_route_profiles_cache,
)
from apps_rg.runtime.bindings.l1_binding import l1_plan_apps_rg
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V3_CANDIDATE_ARM,
    build_l1_cognitive_treatment,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.l1_cognitive_c0_outcome_receipt import (
    build_l1_cognitive_c0_outcome_receipt,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    build_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.spine_contracts import (
    FinalEvidenceContract,
    L1PlanContract,
    SUPPORT_STATUS_PASS,
    ValidatedRequest,
)


def _profile_manifest() -> dict[str, str]:
    return {
        "l1_planning_profile_ref": l1_planning_profile_ref(),
        "l1_planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
        "manifest_digest": "f" * 64,
    }


def _validated_request(
    *,
    generation_mode: str = "strategic_tailor",
    section_id: str = "",
) -> ValidatedRequest:
    task_spec: dict[str, Any] = {
        "generation_mode": generation_mode,
        "task_class": "resume_generation",
        "l1_cognitive_treatment": build_l1_cognitive_treatment(
            L1_COGNITIVE_V3_CANDIDATE_ARM,
            assignment_origin="U0_VALIDATED_INGRESS",
        ),
    }
    constraints: dict[str, Any] = {"output_format": "executive_resume"}
    if section_id:
        task_spec["section_id"] = section_id
        constraints["section_id"] = section_id
    payload = {
        "non_product_certified": True,
        "target_company": "Acme Corp",
        "target_role": "VP Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": (
            "Requirements\n"
            "- Must lead AI platform strategy and own cloud infrastructure governance.\n"
            "- Must build distributed ML serving systems."
        ),
        "source_resume_text": "Built governed AI infrastructure across global regions.",
        "generation_mode": generation_mode,
        "task_spec": task_spec,
        "query_spec": {"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        "support_expectation": {"provenance_required": True},
        "output_expectation": {},
        "profile_manifest": _profile_manifest(),
        "user_constraints": constraints,
        "output_preferences": {},
    }
    return ValidatedRequest(
        request_id="req-wave2-l0-c0",
        run_id="run-wave2-l0-c0",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-11-09T00:00:00+00:00"
        ),
        trace_id="trace-wave2-l0-c0",
        tenant_id="tenant-wave2",
        replay_key="replay-wave2-l0-c0",
        l5_certification_ref="test:valid:wave2",
        app_payload=payload,
    )


def test_l0_condition_value_unblocks_route_hints_and_evaluates_all_six_hints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "wave2-test-secret")
    reset_route_profiles_cache()

    plan = l1_plan_apps_rg(_validated_request())
    for key in _ALL_SIX_L1_ROUTE_HINT_KEYS:
        val = _condition_value(plan, f"route_hints.{key}")
        assert val is not None
        assert val == plan.route_hints[key]

    route = l0_route_apps_rg(plan)
    for key in _ALL_SIX_L1_ROUTE_HINT_KEYS:
        expected_code = f"l1_route_hint:{key}={plan.route_hints[key]}"
        assert expected_code in route.reason_codes


def test_changing_l1_route_hints_switches_selected_l0_route_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "wave2-test-secret")
    reset_route_profiles_cache()

    base_plan = L1PlanContract(
        request_id="req-wave2-switch",
        run_id="run-wave2-switch",
        app_id="apps_rg",
        trace_id="trace-wave2-switch",
        grounding_required=True,
        merge_required_hint=False,
        task_spec={"generation_mode": "section_regen"},
        query_spec={"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        support_expectation={"provenance_required": True},
        route_hints={
            "execution_shape_hint": "single_work_unit_direct",
            "multi_work_unit_hint": "false",
            "merge_needed_hint": "false",
            "candidate_selection_needed_hint": "false",
            "grounding_needed_hint": "true",
            "hitl_risk_hint": "none",
        },
    )
    route_default = l0_route_apps_rg(base_plan)
    assert route_default.route_id == "R3_SIMPLE_GROUNDED_READ"
    assert (
        route_default.route_profile_ref
        == "arpf::apps_rg::resume_generation::default_single_step::v1"
    )

    candidate_plan = replace(
        base_plan,
        route_hints={
            **dict(base_plan.route_hints),
            "candidate_selection_needed_hint": "true",
        },
    )
    route_candidate = l0_route_apps_rg(candidate_plan)
    assert route_candidate.route_id == "R4_SINGLE_ACTION"
    assert (
        route_candidate.route_profile_ref
        == "arpf::apps_rg::resume_generation::single_unit_hint_action::v1"
    )

    multi_unit_plan = replace(
        base_plan,
        route_hints={
            **dict(base_plan.route_hints),
            "execution_shape_hint": "multi_work_unit_managed_candidate",
            "multi_work_unit_hint": "true",
            "candidate_selection_needed_hint": "true",
        },
    )
    route_multi = l0_route_apps_rg(multi_unit_plan)
    assert route_multi.route_id == "R3R4_MANAGED_WORKFLOW"
    assert (
        route_multi.route_profile_ref
        == "arpf::apps_rg::resume_generation::multi_unit_hint_managed::v1"
    )


def test_c0_planned_binding_builds_c0_retrieval_plan_with_semantic_sub_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "wave2-test-secret")
    reset_route_profiles_cache()

    vr = _validated_request()
    plan = l1_plan_apps_rg(vr)
    route = l0_route_apps_rg(plan)

    c0_plan = build_c0_retrieval_plan(plan)
    assert isinstance(c0_plan, C0RetrievalPlan)
    assert len(c0_plan.semantic_sub_queries) >= 2
    assert c0_plan.competency_weights
    assert c0_plan.plan_digest.startswith("sha256:")

    capsule_ref = str(plan.task_spec["apps_rg_planning_capsule_ref"])
    v2_capsule = plan.task_spec["apps_rg_planning_v2_capsule"]
    obligation_receipt = build_l1_evidence_obligation_receipt(
        capsule=v2_capsule,
        request_id=plan.request_id,
        run_id=plan.run_id,
        trace_id=plan.trace_id,
        final_evidence_digest="d" * 64,
        evidence_items=(),
    )
    cognitive_outcome = build_l1_cognitive_c0_outcome_receipt(
        cognitive_plan=plan.task_spec["apps_rg_cognitive_v3_plan"],
        v2_capsule=v2_capsule,
        c0_obligation_receipt=obligation_receipt,
    )

    def _fake_c0(*_args: Any, **_kwargs: Any) -> FinalEvidenceContract:
        return FinalEvidenceContract(
            request_id=plan.request_id,
            run_id=plan.run_id,
            app_id=plan.app_id,
            trace_id=plan.trace_id,
            l5_certification_ref=plan.l5_certification_ref,
            support_status=SUPPORT_STATUS_PASS,
            support_target_met=True,
            final_evidence_digest="d" * 64,
            retrieval_plan_ref=f"l1_evidence_plan:1234567890abcdef:capsule:{capsule_ref[:24]}",
            audit_refs=(
                f"l1_capsule_digest:{capsule_ref[:24]}",
                "l1_v2_evidence_obligation_ledger:"
                f"{v2_capsule['evidence_obligation_ledger']['ledger_digest']}",
                "l1_evidence_obligation_receipt_digest:"
                f"{obligation_receipt['receipt_digest']}",
                "l1_cognitive_c0_outcome_receipt_digest:"
                f"{cognitive_outcome['receipt_digest']}",
            ),
        )

    monkeypatch.setattr(
        "apps_rg.runtime.bindings.c0_planned_binding.c0_retrieve_apps_rg",
        _fake_c0,
    )
    fec = c0_retrieve_apps_rg_planned(route, vr, l1_plan=plan)
    assert f"l1_c0_retrieval_plan_digest:{c0_plan.plan_digest}" in fec.audit_refs
