"""Apps Research grounding uses Apps RG-owned route and evidence contracts."""

from __future__ import annotations

from apps_rg.runtime.spine_contracts import FinalEvidenceContract, RouteContract


def test_grounding_route_is_explicit_and_has_no_write_authority() -> None:
    route = RouteContract(
        request_id="research-request",
        run_id="research-run",
        app_id="apps_research",
        trace_id="research-trace",
        route_id="apps_research_grounded",
        l3_required=False,
        grounding_required=True,
        model_generation_required=False,
        write_authority_present=False,
        allowed_next_stage=frozenset({"C0"}),
    )

    assert route.grounding_required is True
    assert route.write_authority_present is False
    assert route.allowed_next_stage == frozenset({"C0"})


def test_evidence_contract_preserves_the_grounding_boundary() -> None:
    evidence = FinalEvidenceContract(
        request_id="research-request",
        run_id="research-run",
        app_id="apps_research",
        trace_id="research-trace",
        support_target_met=False,
        support_status="UNKNOWN",
        blocked_source_refs=("unverified-source",),
    )

    assert evidence.has_blocked_sources is True
    assert evidence.support_status_is_passing is False
    assert evidence.evidence_items == ()
