"""apps_research UWG writer regression tests."""

from __future__ import annotations


def test_commit_brief_record_supplies_l5_certification_ref() -> None:
    from apps_rg.runtime.local_state import (
        compute_state_diffs_digest,
    )
    from apps_research.integrations.governed_research_run import GovernedE2ERunRecord
    from apps_research.integrations.research_brief_uwg_writer import (
        _BLUEPRINT_REF,
        _POLICY_REF,
        _commit_request_signature,
        commit_brief_record,
    )

    captured = {}

    class _Receipt:
        commit_receipt_id = "receipt-research-brief-test"

    class _Gateway:
        def commit(self, *, commit_request, state_diffs, rollback_plan, refresh_plan):
            captured["commit_request"] = commit_request
            captured["state_diffs"] = state_diffs
            captured["rollback_plan"] = rollback_plan
            captured["refresh_plan"] = refresh_plan
            return _Receipt(), None, None

    run_record = GovernedE2ERunRecord(
        run_id="research-run-test",
        topic="Anthropic",
        l1_sub_queries=("Anthropic",),
        l1_fallback=False,
        l0_intent="research",
        l0_target="research_assembly",
        l0_confidence=0.9,
        l0_fallback=False,
        c0_raw_count=3,
        c0_shaped_count=3,
        c0_collection="process_docs",
        disposition="proceed",
        gate_disposition="allow_response",
        grounded=True,
        citation_count=3,
        support_coverage=0.9,
        l6_ingested=True,
        error="",
        research_depth_profile="COMPANY_BRIEF_STANDARD",
        fec_run_context={"company_brief": {"company_brief_text": "brief"}},
    )

    brief = commit_brief_record(run_record, gateway=_Gateway())

    assert brief.commit_receipt_ref == "receipt-research-brief-test"
    request = captured["commit_request"]
    assert request.l5_certification_ref
    assert request.capability_token_ref == "capability:apps_research:research-brief:research-run-test"
    assert captured["refresh_plan"].before_snapshot == ""
    assert request.clearance_proof_id == request.cleared_exit_review_packet_ref
    assert request.registry_digest_set == (
        f"registry:policy:{_POLICY_REF}",
        f"registry:blueprint:{_BLUEPRINT_REF}",
    )
    assert request.staged_diff_hash == compute_state_diffs_digest(
        captured["state_diffs"]
    )
    assert request.commit_request_signature == _commit_request_signature(
        commit_request_id=request.commit_request_id,
        staged_diff_hash=request.staged_diff_hash,
        clearance_proof_id=request.clearance_proof_id,
        registry_digest_set=request.registry_digest_set,
    )


def test_commit_brief_record_uses_default_gateway_snapshot_contract() -> None:
    from apps_rg.runtime.local_state import DurableWriteGateway
    from apps_research.integrations.governed_research_run import GovernedE2ERunRecord
    from apps_research.integrations.research_brief_uwg_writer import commit_brief_record

    run_record = GovernedE2ERunRecord(
        run_id="research-run-default-gateway",
        topic="Anthropic",
        l1_sub_queries=("Anthropic",),
        l1_fallback=False,
        l0_intent="research",
        l0_target="research_assembly",
        l0_confidence=0.9,
        l0_fallback=False,
        c0_raw_count=3,
        c0_shaped_count=3,
        c0_collection="process_docs",
        disposition="proceed",
        gate_disposition="allow_response",
        grounded=True,
        citation_count=3,
        support_coverage=0.9,
        l6_ingested=True,
        error="",
        research_depth_profile="COMPANY_BRIEF_STANDARD",
        fec_run_context={"company_brief": {"company_brief_text": "brief"}},
    )
    gateway = DurableWriteGateway()
    before_snapshot = gateway.last_snapshot_id

    brief = commit_brief_record(run_record, gateway=gateway)

    assert brief.commit_receipt_ref.startswith("ucr:")
    assert gateway.last_snapshot_id != before_snapshot
