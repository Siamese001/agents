"""Unit tests verifying Wave 1 orchestrator terminal authority and closeout integrity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps_rg.runtime.mandatory_run_outputs import MANDATORY_OUTPUT_HARD_STOP_GATE_ID
from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import (
    ProductE2EAuthorityError,
    _emit_terminal_mandatory_closeout,
    _seal_product_terminal_authority,
)


def test_terminal_mandatory_closeout_exception_sets_hard_stop_and_blocks(tmp_path: Path) -> None:
    """When mandatory closeout raises an unhandled exception, mandatory_output_hard_stop is marked failed."""
    artifact_dir = tmp_path / "run_test"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    repo_root = tmp_path

    payload: dict[str, Any] = {
        "run_id": "test_run_001",
        "exit_status": "success",
        "execution_status": "completed",
        "outcome_authorized": True,
        "product_authorized": True,
        "pipeline_complete": True,
        "completion_status": "PASS",
        "fault": "",
    }

    with patch(
        "apps_rg.runtime.mandatory_run_outputs.emit_mandatory_run_outputs",
        side_effect=RuntimeError("simulated closeout disk failure"),
    ):
        result = _emit_terminal_mandatory_closeout(
            artifact_dir=artifact_dir,
            repo_root=repo_root,
            payload=payload,
            final_resume_outputs_pre_emitted=False,
        )

    assert result["exit_status"] == "error"
    assert result["execution_status"] == "failed"
    assert result["outcome_authorized"] is False
    assert result["completion_status"] == "BLOCKED"
    assert result["fault"] == MANDATORY_OUTPUT_HARD_STOP_GATE_ID
    assert result["completion_fault"] == MANDATORY_OUTPUT_HARD_STOP_GATE_ID
    assert result.get("terminal_closeout_failed") is True

    hard_stop = result.get("mandatory_output_hard_stop")
    assert isinstance(hard_stop, dict)
    assert hard_stop.get("pass") is False
    assert hard_stop.get("required") is True
    assert hard_stop.get("reason") == "TERMINAL_MANDATORY_CLOSEOUT_FAILED"
    assert "simulated closeout disk failure" in str(hard_stop.get("error"))


def test_terminal_mandatory_closeout_forensics_failure_marks_terminal_closeout_failed(
    tmp_path: Path,
) -> None:
    """When forensics gate fails, terminal_closeout_failed is set to True."""
    artifact_dir = tmp_path / "run_test_forensics"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    repo_root = tmp_path

    payload: dict[str, Any] = {
        "run_id": "test_run_002",
        "exit_status": "success",
        "execution_status": "completed",
        "fault": "",
    }

    mock_emit = {
        "json_path": artifact_dir / "mandatory.json",
        "markdown_path": artifact_dir / "mandatory.md",
        "bcg_markdown_path": artifact_dir / "bcg.md",
        "payload": {
            "section_failure_forensics": {
                "required": True,
                "pass": False,
                "failed_sections": ["competencies"],
            }
        },
        "mandatory_output_gate": {"required": True, "pass": True},
    }

    with patch(
        "apps_rg.runtime.mandatory_run_outputs.emit_mandatory_run_outputs",
        return_value=mock_emit,
    ):
        result = _emit_terminal_mandatory_closeout(
            artifact_dir=artifact_dir,
            repo_root=repo_root,
            payload=payload,
            final_resume_outputs_pre_emitted=False,
        )

    assert result["exit_status"] == "error"
    assert result["completion_status"] == "BLOCKED"
    assert result.get("terminal_closeout_failed") is True


def test_terminal_mandatory_output_gate_failure_sets_terminal_closeout_failed(
    tmp_path: Path,
) -> None:
    """When mandatory output hard stop gate fails, terminal_closeout_failed is set to True."""
    artifact_dir = tmp_path / "run_test_mandatory_gate"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    repo_root = tmp_path

    payload: dict[str, Any] = {
        "run_id": "test_run_003",
        "exit_status": "success",
        "execution_status": "completed",
        "fault": "",
    }

    mock_emit = {
        "json_path": artifact_dir / "mandatory.json",
        "markdown_path": artifact_dir / "mandatory.md",
        "bcg_markdown_path": artifact_dir / "bcg.md",
        "payload": {
            "section_failure_forensics": {
                "required": False,
                "pass": True,
            }
        },
        "mandatory_output_gate": {
            "required": True,
            "pass": False,
            "reason": "MISSING_REQUIRED_OUTPUTS",
        },
    }

    with patch(
        "apps_rg.runtime.mandatory_run_outputs.emit_mandatory_run_outputs",
        return_value=mock_emit,
    ):
        result = _emit_terminal_mandatory_closeout(
            artifact_dir=artifact_dir,
            repo_root=repo_root,
            payload=payload,
            final_resume_outputs_pre_emitted=False,
        )

    assert result["exit_status"] == "error"
    assert result["completion_status"] == "BLOCKED"
    assert result.get("terminal_closeout_failed") is True
    assert result.get("fault") == MANDATORY_OUTPUT_HARD_STOP_GATE_ID


def test_terminal_mandatory_closeout_clean_success(tmp_path: Path) -> None:
    """Clean mandatory output emission leaves terminal_closeout_failed unset."""
    artifact_dir = tmp_path / "run_test_clean"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    repo_root = tmp_path

    payload: dict[str, Any] = {
        "run_id": "test_run_004",
        "exit_status": "success",
        "execution_status": "completed",
        "outcome_authorized": True,
        "product_authorized": True,
        "pipeline_complete": True,
        "completion_status": "PASS",
        "fault": "",
    }

    mock_emit = {
        "json_path": artifact_dir / "mandatory.json",
        "markdown_path": artifact_dir / "mandatory.md",
        "bcg_markdown_path": artifact_dir / "bcg.md",
        "payload": {
            "section_failure_forensics": {
                "required": False,
                "pass": True,
            }
        },
        "mandatory_output_gate": {"required": True, "pass": True},
    }

    with patch(
        "apps_rg.runtime.mandatory_run_outputs.emit_mandatory_run_outputs",
        return_value=mock_emit,
    ):
        result = _emit_terminal_mandatory_closeout(
            artifact_dir=artifact_dir,
            repo_root=repo_root,
            payload=payload,
            final_resume_outputs_pre_emitted=False,
        )

    assert result["exit_status"] == "success"
    assert result["completion_status"] == "PASS"
    assert result.get("terminal_closeout_failed") is not True


def test_seal_product_terminal_authority_exception_revokes_authorization(tmp_path: Path) -> None:
    """If _seal_product_terminal_authority fails, an exception is raised so the caller can revoke authorization."""
    art = tmp_path / "run_seal_fail"
    art.mkdir(parents=True, exist_ok=True)
    (art / "APPS_RG_MANDATORY_RUN_OUTPUT.json").write_text(
        json.dumps({"schema_version": "apps_rg.mandatory_run_output.v1"}),
        encoding="utf-8",
    )

    mock_ledger = MagicMock()
    mock_ledger.record_from_receipt.return_value = {"status": "PASS"}

    with pytest.raises(Exception):
        _seal_product_terminal_authority(
            artifact_dir=art,
            product_ledger=mock_ledger,
            identity={"run_id": "r1"},
            product_authorization_ref="nonexistent_receipt.json",
        )


def test_seal_product_terminal_authority_fails_when_mandatory_receipt_blocked(tmp_path: Path) -> None:
    """When product_ledger blocks the mandatory output stage, ProductE2EAuthorityError is raised."""
    art = tmp_path / "run_seal_blocked"
    art.mkdir(parents=True, exist_ok=True)
    (art / "APPS_RG_MANDATORY_RUN_OUTPUT.json").write_text(
        json.dumps({"schema_version": "apps_rg.mandatory_run_output.v1"}),
        encoding="utf-8",
    )
    receipt_file = art / "receipt_mandatory.json"
    receipt_file.write_text(
        json.dumps({
            "schema_version": "v1",
            "source_bindings": [{"artifact_ref": "APPS_RG_MANDATORY_RUN_OUTPUT.json"}],
        }),
        encoding="utf-8",
    )

    mock_ledger = MagicMock()
    mock_ledger.record_from_receipt.return_value = {"status": "FAIL"}

    with patch(
        "apps_rg.runtime.product_stage_authority.emit_mandatory_outputs_authority_receipt",
        return_value=receipt_file,
    ):
        with pytest.raises(ProductE2EAuthorityError) as exc_info:
            _seal_product_terminal_authority(
                artifact_dir=art,
                product_ledger=mock_ledger,
                identity={"run_id": "r1"},
                product_authorization_ref="auth.json",
            )

    assert "mandatory output authority receipt blocked" in str(exc_info.value)


def test_seal_product_terminal_authority_fails_when_decision_output_missing(tmp_path: Path) -> None:
    """When product authorization receipt lacks decision or output bindings, ProductE2EAuthorityError is raised."""
    art = tmp_path / "run_seal_missing_bindings"
    art.mkdir(parents=True, exist_ok=True)
    (art / "APPS_RG_MANDATORY_RUN_OUTPUT.json").write_text(
        json.dumps({"schema_version": "apps_rg.mandatory_run_output.v1"}),
        encoding="utf-8",
    )
    receipt_file = art / "receipt_mandatory.json"
    receipt_file.write_text(
        json.dumps({
            "schema_version": "v1",
            "source_bindings": [{"artifact_ref": "APPS_RG_MANDATORY_RUN_OUTPUT.json"}],
        }),
        encoding="utf-8",
    )
    (art / "auth_empty.json").write_text(
        json.dumps({"schema_version": "apps_rg.product_authorization.v1"}),
        encoding="utf-8",
    )

    mock_ledger = MagicMock()
    mock_ledger.record_from_receipt.return_value = {"status": "PASS"}

    with patch(
        "apps_rg.runtime.product_stage_authority.emit_mandatory_outputs_authority_receipt",
        return_value=receipt_file,
    ):
        with pytest.raises(ProductE2EAuthorityError) as exc_info:
            _seal_product_terminal_authority(
                artifact_dir=art,
                product_ledger=mock_ledger,
                identity={"run_id": "r1"},
                product_authorization_ref="auth_empty.json",
            )

    assert "product authorization receipt lacks exact decision/output bindings" in str(exc_info.value)
