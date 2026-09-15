"""Unit tests for L1 -> L2 -> L1 Spine Return Path Wiring (Wave 4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from apps_rg.runtime.contracts.l1_post_tool_review_contracts import L1ReviewVerdict
from apps_rg.runtime.orchestration.app_single_action_spine import (
    run_apps_rg_single_action_spine,
)
from apps_rg.runtime.spine.section_x3_finalize import (
    _run_section_spine_exit_eval,
)


def test_single_action_spine_emits_l1_post_tool_review_on_success(tmp_path: Path) -> None:
    """Verify that single action spine executes L1 review and includes receipt in bundle."""
    l2_output = {
        "execution_status": "completed",
        "generated_content": "## Summary\nEngineered large scale systems.",
        "sovereign_execution_receipt": "rcpt-001",
    }
    raw_request = {
        "run_id": "run-test-w4-pass",
        "request_id": "req-test-w4-pass",
        "app_id": "apps_rg",
        "execution_scope": "section",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": ["non_empty_content"],
            "evidence_requirement_refs": [],
        },
    }

    result = run_apps_rg_single_action_spine(
        raw_request=raw_request,
        artifact_dir=tmp_path,
        cache_preflight_evidence={"status": "READY"},
        l2_callable=lambda: l2_output,
    )

    assert result.fault == ""
    assert result.x3_disposition == "X3D_ALLOW_FINISH"

    review_file = tmp_path / "l1_post_tool_review.json"
    assert review_file.is_file()
    review_doc = json.loads(review_file.read_text(encoding="utf-8"))
    payload = review_doc.get("payload", review_doc)
    assert payload["verdict"] == L1ReviewVerdict.SUFFICIENT.value
    assert payload["deterministic_checks"]["status"] == "PASS"

    manifest_file = tmp_path / "integrated_runtime_artifact_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_payload = manifest.get("payload", manifest)
    assert "l1_post_tool_review.json" in manifest_payload["artifact_filenames"]


def test_single_action_spine_fails_closed_when_l1_review_fails(tmp_path: Path) -> None:
    """Verify that single action spine fails closed if L1 review does not pass."""
    l2_output = {
        "execution_status": "failed",
        "generated_content": "",
    }
    raw_request = {
        "run_id": "run-test-w4-fail",
        "request_id": "req-test-w4-fail",
        "app_id": "apps_rg",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": ["non_empty_content"],
            "evidence_requirement_refs": [],
        },
    }

    result = run_apps_rg_single_action_spine(
        raw_request=raw_request,
        artifact_dir=tmp_path,
        cache_preflight_evidence={"status": "READY"},
        l2_callable=lambda: l2_output,
    )

    assert result.fault.startswith("L1_REVIEW_")
    assert result.x3_disposition == "X3A_DENY_REROUTE"


def test_section_x3_exit_hard_gated_by_l1_review_failure(tmp_path: Path) -> None:
    """Verify that X3 exit evaluation blocks authorization when L1 review failed."""
    # Write a sealed artifact on disk
    sealed_file = tmp_path / "sealed_l2_artifact.json"
    sealed_file.write_text(json.dumps({"execution_status": "completed"}), encoding="utf-8")

    # Write an insufficient L1 review on disk
    l1_review_file = tmp_path / "l1_post_tool_review.json"
    l1_review_doc = {
        "verdict": "INSUFFICIENT_REPLAN",
        "deterministic_checks": {"status": "FAIL", "check_digest": "cd1"},
        "semantic_review": {"status": "INSUFFICIENT", "review_digest": "sd1"},
    }
    l1_review_file.write_text(json.dumps(l1_review_doc), encoding="utf-8")

    x3_doc = {"pass_": True, "x3_code": "X3_PASS"}
    runtime_payload: dict[str, Any] = {
        "run_id": "run-x3-gate-test",
        "request_id": "req-x3-gate-test",
        "l1_post_tool_review": l1_review_doc,
    }

    _run_section_spine_exit_eval(
        tmp_path,
        section_id="headline",
        runtime_payload=runtime_payload,
        x3_doc=x3_doc,
    )

    # Verify that x3_doc was hard blocked
    assert x3_doc["pass_"] is False
    assert x3_doc["blocked_by_gate"] == "l1_post_tool_review"
    assert x3_doc["x3_code"] == "X3_BLOCK_L1_REVIEW_INSUFFICIENT_REPLAN"
    assert runtime_payload["l1_review_blocked"] is True
