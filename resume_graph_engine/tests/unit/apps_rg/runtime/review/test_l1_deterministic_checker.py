"""Unit tests for L1 Post-L2 Deterministic Check Engine."""

from __future__ import annotations

import json
from typing import Any

import pytest
from apps_rg.runtime.bindings.l2_authority_contracts import SignedAppsRgL2ExecutionPacket
from apps_rg.runtime.contracts.l1_post_tool_review_contracts import L1DeterministicCheckResult
from apps_rg.runtime.review.l1_deterministic_checker import (
    L1_DETERMINISTIC_CHECK_SCHEMA_VERSION,
    l1_post_l2_deterministic_check,
)
from apps_rg.runtime.spine_contracts import L1PlanContract, SealedL2Artifact


def _build_valid_sealed_artifact(**kwargs: Any) -> SealedL2Artifact:
    base = {
        "request_id": "req-001",
        "run_id": "run-001",
        "app_id": "apps_rg",
        "trace_id": "trace-001",
        "execution_status": "completed",
        "generated_content": (
            "## Summary\n"
            "Experienced software engineer with strong Python background [fact_101].\n\n"
            "## Experience\n"
            "Led platform architecture scaling systems to 10M users [fact_102]."
        ),
        "sovereign_execution_receipt": "rcpt-abc-123",
        "state_diff_authorized": True,
        "proposed_state_diff": {"updated_sections": ["Summary", "Experience"]},
    }
    base.update(kwargs)
    return SealedL2Artifact(**base)


def _build_execution_packet(**kwargs: Any) -> SignedAppsRgL2ExecutionPacket:
    base = {
        "schema_version": "apps_rg.l2_execution_packet.v2",
        "request_id": "req-001",
        "run_id": "run-001",
        "app_id": "apps_rg",
        "trace_id": "trace-001",
        "tenant_id": "tenant-001",
        "route_id": "route-001",
        "workflow_id": "wf-001",
        "node_id": "node-001",
        "step_id": "step-001",
        "execution_lane": "MODEL",
        "capability_scope_digest": "cap-001",
        "sandbox_envelope_digest": "sand-001",
        "sandbox_required": False,
        "egress_policy_ref": "none",
        "policy_hash": "pol-001",
        "blueprint_hash": "blue-001",
        "prompt_hash": "prompt-001",
        "replay_key": "rep-001",
        "attempt_number": 1,
        "attempt_seed": "seed-001",
        "snapshot_manifest": "",
        "idempotency_key": "idem-001",
        "registry_digest_set": (),
        "compiled_prompt_artifact_ref": "cp-001",
        "final_evidence_contract_ref": "fec-001",
        "canonical_provider": "gemini",
        "target_model": "gemini-2.5-flash",
        "allowed_tools": (),
        "allowed_models": ("gemini-2.5-flash",),
        "allowed_networks": (),
        "allowed_file_roots": (),
        "side_effect_class": "READ",
        "budget": {"max_tokens": 2048},
        "signature_chain": (),
        "signature_chain_digest": "sig-001",
        "expected_output_schema_ref": "markdown:section",
        "success_criteria_refs": (
            "non_empty_content",
            "require_section:Summary",
            "require_section:Experience",
            "sovereign_receipt_present",
        ),
        "evidence_requirement_refs": ("fact_101", "fact_102"),
    }
    base.update(kwargs)
    return SignedAppsRgL2ExecutionPacket(**base)


def _build_l1_plan(**kwargs: Any) -> L1PlanContract:
    base = {
        "request_id": "req-001",
        "run_id": "run-001",
        "app_id": "apps_rg",
        "trace_id": "trace-001",
        "output_expectation": {
            "required_sections": ("Summary", "Experience"),
            "schema_ref": "markdown:section",
        },
        "support_expectation": {
            "required_fact_ids": ("fact_101",),
        },
    }
    base.update(kwargs)
    return L1PlanContract(**base)


def test_happy_path_all_checks_pass() -> None:
    sealed = _build_valid_sealed_artifact()
    packet = _build_execution_packet()
    plan = _build_l1_plan()

    res = l1_post_l2_deterministic_check(sealed, packet, plan)

    assert isinstance(res, L1DeterministicCheckResult)
    assert res.schema_version == L1_DETERMINISTIC_CHECK_SCHEMA_VERSION
    assert res.status == "PASS"
    assert res.tool_execution_success is True
    assert res.schema_valid is True
    assert res.required_fields_present is True
    assert res.missing_fields == ()
    assert res.missing_evidence_ids == ()
    assert res.failure_reasons == ()
    assert bool(res.check_digest)


def test_tool_execution_failure() -> None:
    sealed = _build_valid_sealed_artifact(execution_status="failed")
    packet = _build_execution_packet()

    res = l1_post_l2_deterministic_check(sealed, packet)

    assert res.status == "FAIL"
    assert res.tool_execution_success is False
    assert any("execution status 'failed' is not successful" in r for r in res.failure_reasons)


def test_missing_required_section() -> None:
    sealed = _build_valid_sealed_artifact(
        generated_content="## Summary\nOnly summary content here [fact_101]."
    )
    packet = _build_execution_packet(
        success_criteria_refs=("require_section:Summary", "require_section:Education"),
        evidence_requirement_refs=("fact_101",),
    )

    res = l1_post_l2_deterministic_check(sealed, packet)

    assert res.status == "FAIL"
    assert res.required_fields_present is False
    assert "section:Education" in res.missing_fields
    assert any("Missing required fields/sections" in r for r in res.failure_reasons)


def test_missing_evidence_obligation() -> None:
    sealed = _build_valid_sealed_artifact(
        generated_content="## Summary\nSoftware engineer with Python experience [fact_101].",
        proposed_state_diff={},
    )
    packet = _build_execution_packet(
        evidence_requirement_refs=("fact_101", "fact_missing_999"),
        success_criteria_refs=("require_section:Summary",),
    )

    res = l1_post_l2_deterministic_check(sealed, packet)

    assert res.status == "FAIL"
    assert "fact_missing_999" in res.missing_evidence_ids
    assert any("Missing required evidence obligations" in r for r in res.failure_reasons)


def test_evidence_satisfied_via_state_diff() -> None:
    # When evidence is in proposed_state_diff instead of text
    sealed = _build_valid_sealed_artifact(
        generated_content="## Summary\nText without explicit bracket tag.\n\n## Experience\nRole details here.",
        proposed_state_diff={"evidence_citations": ["fact_101", "fact_102"]},
    )
    packet = _build_execution_packet()

    res = l1_post_l2_deterministic_check(sealed, packet)

    assert res.status == "PASS"
    assert res.missing_evidence_ids == ()


def test_schema_json_validation_failure() -> None:
    sealed = _build_valid_sealed_artifact(
        generated_content="not a valid json string {",
        proposed_state_diff={},
    )
    packet = _build_execution_packet(
        expected_output_schema_ref="json:object",
        success_criteria_refs=(),
        evidence_requirement_refs=(),
    )

    res = l1_post_l2_deterministic_check(sealed, packet)

    assert res.status == "FAIL"
    assert res.schema_valid is False
    assert any("requires valid JSON output" in r for r in res.failure_reasons)


def test_schema_json_validation_success() -> None:
    sealed = _build_valid_sealed_artifact(
        generated_content=json.dumps({"key": "val", "count": 42}),
        proposed_state_diff={},
    )
    packet = _build_execution_packet(
        expected_output_schema_ref="json:object",
        success_criteria_refs=(),
        evidence_requirement_refs=(),
    )

    res = l1_post_l2_deterministic_check(sealed, packet)

    assert res.status == "PASS"
    assert res.schema_valid is True


def test_explicit_success_criteria_assertions() -> None:
    sealed = _build_valid_sealed_artifact(
        generated_content="Short text.",
        sovereign_execution_receipt="",
    )
    packet = _build_execution_packet(
        success_criteria_refs=(
            "min_words:50",
            "sovereign_receipt_present",
        ),
        evidence_requirement_refs=(),
    )

    res = l1_post_l2_deterministic_check(sealed, packet)

    assert res.status == "FAIL"
    assert res.checked_assertions["min_words:50"] is False
    assert res.checked_assertions["sovereign_receipt_present"] is False
    assert any("Explicit success criterion 'min_words:50' failed" in r for r in res.failure_reasons)
    assert any("Explicit success criterion 'sovereign_receipt_present' failed" in r for r in res.failure_reasons)


def test_dict_payload_interchangeability() -> None:
    sealed_dict = {
        "execution_status": "completed",
        "generated_content": "# Skills\nPython, Rust [fact_42]",
        "proposed_state_diff": {"skills": ["Python", "Rust"]},
        "sovereign_execution_receipt": "rcpt-001",
    }
    packet_dict = {
        "expected_output_schema_ref": "markdown:section",
        "success_criteria_refs": ["require_section:Skills", "non_empty_content"],
        "evidence_requirement_refs": ["fact_42"],
    }
    plan_dict = {
        "output_expectation": {"required_sections": ["Skills"]},
        "support_expectation": {"required_fact_ids": ["fact_42"]},
    }

    res = l1_post_l2_deterministic_check(sealed_dict, packet_dict, plan_dict)

    assert res.status == "PASS"
    assert res.tool_execution_success is True
    assert res.schema_valid is True
    assert res.required_fields_present is True
    assert res.missing_fields == ()
    assert res.missing_evidence_ids == ()


def test_custom_assertions_and_custom_schema_validator() -> None:
    sealed = _build_valid_sealed_artifact()

    # Custom validator rejects
    res_reject = l1_post_l2_deterministic_check(
        sealed,
        custom_assertions={"schema_validator": lambda s: False},
    )
    assert res_reject.status == "FAIL"
    assert res_reject.schema_valid is False

    # Custom boolean assertion
    res_bool = l1_post_l2_deterministic_check(
        sealed,
        custom_assertions={"is_mock_forbidden": True, "token_count_within_bound": False},
    )
    assert res_bool.status == "FAIL"
    assert res_bool.checked_assertions["token_count_within_bound"] is False
    assert any("Custom assertion 'token_count_within_bound' evaluated to False" in r for r in res_bool.failure_reasons)
