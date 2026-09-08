"""Apps Research receives advisory L1 plans through Apps RG-owned contracts."""

from __future__ import annotations

from apps_research.runtime.app_contracts import (
    AuthorityValidationReceipt,
    ValidatedRequest,
)
from apps_rg.runtime.spine_contracts import L1PlanContract


def _validated_request() -> ValidatedRequest:
    return ValidatedRequest(
        request_id="research-request",
        run_id="research-run",
        app_id="apps_research",
        task_class="company_brief",
        payload_digest="payload-digest",
        authority_validation_receipt=AuthorityValidationReceipt(
            allowed=True,
            passed=True,
            forbidden_fields_detected=(),
            timestamp_iso="2026-08-11T00:00:00+00:00",
        ),
        trace_id="research-trace",
        tenant_id="apps_research",
        app_payload={"target_company": "TestCorp"},
    )


def test_l1_plan_is_advisory_and_carries_the_validated_request_identity() -> None:
    request = _validated_request()
    plan = L1PlanContract(
        request_id=request.request_id,
        run_id=request.run_id,
        app_id=request.app_id,
        trace_id=request.trace_id,
        task_plan=("decompose research question", "collect bounded evidence"),
        required_capabilities=("research",),
        grounding_required=True,
        apps_research_call_required=True,
        model_generation_required=False,
        write_authority_present=False,
        task_spec={"target_company": request.app_payload["target_company"]},
        non_authority_assertion={"route_selection": False, "execution": False},
    )

    assert plan.request_id == request.request_id
    assert plan.app_id == "apps_research"
    assert plan.grounding_required is True
    assert plan.write_authority_present is False
    assert plan.non_authority_assertion["execution"] is False


def test_l1_plan_keeps_route_and_execution_decisions_out_of_the_plan_contract() -> None:
    plan = L1PlanContract(
        request_id="request",
        run_id="run",
        app_id="apps_research",
        trace_id="trace",
        task_plan=("plan",),
    )

    assert plan.route_hints == {}
    assert plan.model_generation_required is False
    assert plan.write_authority_present is False
