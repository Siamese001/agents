"""Negative-control and positive-control tests for evaluation parent run lineage gating."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.__main__ import _evaluate_product_run


def _create_minimal_run_scaffold(
    run_dir: Path,
    *,
    parent_run_id: str = "parent-run-target-123",
    x3_disposition: str = "X3D_ALLOW_FINISH",
    pipeline_complete: bool = True,
    authorized: bool = True,
    saved_decision: dict[str, Any] | None = None,
) -> None:
    """Helper to populate canonical prerequisite run receipts."""
    # 1. Identity envelope
    identity_payload = {
        "schema_version": "apps_rg.runtime_identity_envelope.v1",
        "payload": {
            "parent_run_id": parent_run_id,
            "child_run_id": "child-run-456",
        },
    }
    (run_dir / "runtime_identity_envelope.json").write_text(
        json.dumps(identity_payload, indent=2), encoding="utf-8"
    )

    # 2. X3 disposition receipt
    x3_payload = {
        "schema_version": "apps_rg.x3_disposition_receipt.v1",
        "x3_disposition": x3_disposition,
        "x3_code": x3_disposition,
    }
    (run_dir / "x3_disposition_receipt.json").write_text(
        json.dumps(x3_payload, indent=2), encoding="utf-8"
    )

    # 3. Product authorization receipt
    auth_payload = {
        "schema_version": "apps_rg.product_authorization_receipt.v1",
        "authorized": authorized,
    }
    (run_dir / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps(auth_payload, indent=2), encoding="utf-8"
    )

    # 4. Pipeline completion receipt
    comp_payload: dict[str, Any] = {
        "schema_version": "apps_rg.pipeline_completion_receipt.v1",
        "pipeline_complete": pipeline_complete,
        "completed": pipeline_complete,
        "parent_run_id": parent_run_id,
    }
    if saved_decision is not None:
        comp_payload["payload"] = {"evaluation_decision": saved_decision}
    (run_dir / "apps_rg_post_x3_completion_receipt.json").write_text(
        json.dumps(comp_payload, indent=2), encoding="utf-8"
    )


def test_matching_parent_run_id_eval_record_passes(tmp_path: Path) -> None:
    """Positive control: eval record with exact matching parent_run_id passes cleanly."""
    parent_id = "parent-run-valid-789"
    _create_minimal_run_scaffold(tmp_path, parent_run_id=parent_id)

    eval_dir = tmp_path / "apps_eval" / "01"
    eval_dir.mkdir(parents=True, exist_ok=True)
    eval_record = {
        "schema_version": "apps_eval.record.v1",
        "status": "PASS",
        "verdict": "PASS",
        "disposition": "FINAL",
        "parent_run_id": parent_id,
        "scorecard": {"verdict": "PASS", "status": "PASS"},
    }
    (eval_dir / "eval_record.json").write_text(json.dumps(eval_record), encoding="utf-8")

    result = _evaluate_product_run(tmp_path)

    assert result["status"] == "PASS"
    assert result["evaluation_status"] == "PASS"
    assert result["exit_code"] == 0
    assert result["stale_eval_records"] == []
    assert result["malformed_eval_records"] == []
    assert result["non_passing_eval_records"] == []
    assert result["apps_eval_record_count"] == 1


def test_missing_parent_run_id_eval_record_fails_closed(tmp_path: Path) -> None:
    """Negative control: eval record omitting parent_run_id when parent is expected fails closed."""
    parent_id = "parent-run-required-001"
    _create_minimal_run_scaffold(tmp_path, parent_run_id=parent_id)

    eval_dir = tmp_path / "apps_eval" / "01"
    eval_dir.mkdir(parents=True, exist_ok=True)
    # Notice: parent_run_id is omitted or empty
    eval_record = {
        "schema_version": "apps_eval.record.v1",
        "status": "PASS",
        "verdict": "PASS",
        "disposition": "FINAL",
        "scorecard": {"verdict": "PASS", "status": "PASS"},
    }
    record_path = eval_dir / "eval_record.json"
    record_path.write_text(json.dumps(eval_record), encoding="utf-8")

    result = _evaluate_product_run(tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["exit_code"] != 0
    assert str(record_path) in result["stale_eval_records"]
    assert result["evaluation_validity"] == "INVALID"


def test_mismatched_parent_run_id_eval_record_fails_closed(tmp_path: Path) -> None:
    """Negative control: eval record with different parent_run_id fails closed."""
    parent_id = "parent-run-expected-555"
    _create_minimal_run_scaffold(tmp_path, parent_run_id=parent_id)

    eval_dir = tmp_path / "apps_eval" / "01"
    eval_dir.mkdir(parents=True, exist_ok=True)
    eval_record = {
        "schema_version": "apps_eval.record.v1",
        "status": "PASS",
        "verdict": "PASS",
        "disposition": "FINAL",
        "parent_run_id": "other-parent-run-999",
        "scorecard": {"verdict": "PASS", "status": "PASS"},
    }
    record_path = eval_dir / "eval_record.json"
    record_path.write_text(json.dumps(eval_record), encoding="utf-8")

    result = _evaluate_product_run(tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["exit_code"] != 0
    assert str(record_path) in result["stale_eval_records"]
    assert result["evaluation_validity"] == "INVALID"


def test_superseded_package_eval_record_fails_closed(tmp_path: Path) -> None:
    """Negative control: eval record located in superseded_apps_eval_packages fails closed."""
    parent_id = "parent-run-legacy-333"
    _create_minimal_run_scaffold(tmp_path, parent_run_id=parent_id)

    superseded_dir = tmp_path / "apps_eval" / "superseded_apps_eval_packages" / "01"
    superseded_dir.mkdir(parents=True, exist_ok=True)
    eval_record = {
        "schema_version": "apps_eval.record.v1",
        "status": "PASS",
        "verdict": "PASS",
        "disposition": "FINAL",
        "parent_run_id": parent_id,
        "scorecard": {"verdict": "PASS", "status": "PASS"},
    }
    record_path = superseded_dir / "eval_record.json"
    record_path.write_text(json.dumps(eval_record), encoding="utf-8")

    result = _evaluate_product_run(tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["exit_code"] != 0
    assert str(record_path) in result["stale_eval_records"]


def test_malformed_eval_record_fails_closed(tmp_path: Path) -> None:
    """Negative control: empty or non-dict eval record fails closed."""
    parent_id = "parent-run-corrupt-111"
    _create_minimal_run_scaffold(tmp_path, parent_run_id=parent_id)

    eval_dir = tmp_path / "apps_eval" / "01"
    eval_dir.mkdir(parents=True, exist_ok=True)
    record_path = eval_dir / "eval_record.json"
    record_path.write_text("{}", encoding="utf-8")

    result = _evaluate_product_run(tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["exit_code"] != 0
    assert str(record_path) in result["malformed_eval_records"]
    assert result["evaluation_validity"] == "INVALID"


def test_saved_completion_pass_overridden_when_stale_record_present(tmp_path: Path) -> None:
    """Negative control: saved completion claiming PASS is overridden when stale record exists."""
    parent_id = "parent-run-override-444"
    saved_decision = {
        "execution_status": "PASS",
        "package_integrity_status": "PASS",
        "evaluation_validity": "PASS",
        "deterministic_product_status": "PASS",
        "evaluation_status": "PASS",
    }
    _create_minimal_run_scaffold(
        tmp_path,
        parent_run_id=parent_id,
        saved_decision=saved_decision,
    )

    eval_dir = tmp_path / "apps_eval" / "01"
    eval_dir.mkdir(parents=True, exist_ok=True)
    # Stale record missing parent_run_id
    eval_record = {
        "schema_version": "apps_eval.record.v1",
        "status": "PASS",
        "verdict": "PASS",
        "disposition": "FINAL",
        "scorecard": {"verdict": "PASS", "status": "PASS"},
    }
    record_path = eval_dir / "eval_record.json"
    record_path.write_text(json.dumps(eval_record), encoding="utf-8")

    result = _evaluate_product_run(tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["evaluation_status"] in ("EVALUATION_INVALID", "PRODUCT_FAIL")
    assert result["exit_code"] != 0
    assert str(record_path) in result["stale_eval_records"]
