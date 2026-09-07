"""Wave 1 acceptance for causal separation and terminal closeout evidence."""

from __future__ import annotations

import json
import hashlib
import inspect
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_headline_persists_real_l2_before_x3_binding_and_l2_seal() -> None:
    """Prevent the live 334x placeholder-to-real-L2 amplification failure."""
    from apps_rg.runtime.sections.headline_lane import run_headline_execution

    source = inspect.getsource(run_headline_execution)
    aggregate_at = source.index("x3 = _aggregate_headline_x3(")
    l2_write_at = source.index(
        'write_json(artifact_dir / "l2_output.json", l2_output)',
        aggregate_at,
    )
    x3_finalize_at = source.index("x3 = finalize_section_lane_x3(", l2_write_at)
    l2_seal_at = source.index(
        'finalize_section_l2_after_output(artifact_dir, "headline", runtime_payload)',
        x3_finalize_at,
    )

    assert aggregate_at < l2_write_at < x3_finalize_at < l2_seal_at


def test_valid_stage_ledger_seal_prevents_post_closeout_mutation(tmp_path: Path) -> None:
    from apps_rg.__main__ import _has_valid_sealed_stage_ledger

    ledger = tmp_path / "e2e_stage_ledger.json"
    ledger.write_text('{"terminal":"TERMINAL_NON_PRODUCT"}\n', encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(ledger.read_bytes()).hexdigest()
    (tmp_path / "e2e_stage_ledger_seal_receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "apps_rg.e2e_stage_ledger_seal.v1",
                "ledger_ref": ledger.name,
                "ledger_sha256": digest,
            }
        ),
        encoding="utf-8",
    )

    assert _has_valid_sealed_stage_ledger(tmp_path) is True
    ledger.write_text('{"tampered":true}\n', encoding="utf-8")
    assert _has_valid_sealed_stage_ledger(tmp_path) is False


def test_orchestration_does_not_append_closeout_after_non_product_seal(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.e2e_stage_ledger import E2E_STAGE_LEDGER_SEAL_FILENAME
    from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import (
        _record_closeout_stage_unless_sealed,
    )

    class SealedLedger:
        path = tmp_path / "e2e_stage_ledger.json"

        def record(self, **_kwargs) -> None:
            raise AssertionError("sealed ledger must not be mutated")

    SealedLedger.path.write_text("{}\n", encoding="utf-8")
    (tmp_path / E2E_STAGE_LEDGER_SEAL_FILENAME).write_text("{}\n", encoding="utf-8")

    recorded = _record_closeout_stage_unless_sealed(
        stage_ledger=SealedLedger(),
        payload={"pipeline_complete": False, "fault": "UPSTREAM_FAILURE"},
    )

    assert recorded is False


def test_orchestration_does_not_call_legacy_record_on_receipt_derived_ledger(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import (
        _record_closeout_stage_unless_sealed,
    )

    class ReceiptDerivedLedger:
        path = tmp_path / "e2e_stage_ledger.json"

    ReceiptDerivedLedger.path.write_text("{}\n", encoding="utf-8")

    recorded = _record_closeout_stage_unless_sealed(
        stage_ledger=ReceiptDerivedLedger(),
        payload={"pipeline_complete": False, "fault": "POST_BOUNDARY_FAILURE"},
    )

    assert recorded is False


def test_executive_summary_l7_packaging_uses_checkout_not_package_src_root() -> None:
    from apps_rg.runtime.sections import executive_summary_lane

    assert executive_summary_lane.CHECKOUT_ROOT == REPO_ROOT
    assert executive_summary_lane.REPO_ROOT in {
        REPO_ROOT,
        REPO_ROOT / "src",
    }
    artifact = REPO_ROOT / "artifacts" / "apps_rg" / "runs" / "w1-regression"
    assert artifact.is_relative_to(executive_summary_lane.CHECKOUT_ROOT)

    expected = artifact / "section_l7_binding_manifest.json"
    with patch(
        "apps_rg.runtime.section_l7_binding_lane_integration.finalize_section_l7_binding",
        return_value=expected,
    ) as finalize:
        observed = executive_summary_lane._finalize_executive_summary_l7_binding(
            artifact,
            {"run_id": "w1-regression"},
        )

    assert observed == expected
    assert finalize.call_args.kwargs["repo_root"] == REPO_ROOT
    assert finalize.call_args.kwargs["repo_root"] != REPO_ROOT / "src"


def test_apps_rg_write_gateway_is_local_and_atomic(tmp_path: Path) -> None:
    """Artifact writes need no external callback or package bootstrap."""

    from apps_rg.runtime.core_io import write_gateway

    target = tmp_path / "receipts" / "result.json"
    write_gateway.write_text(target, "before", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "before"

    write_gateway.write_json_atomic(target, {"status": "PASS", "count": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "count": 1,
        "status": "PASS",
    }

    copied = tmp_path / "copy" / "result.json"
    write_gateway.copy_file(target, copied)
    assert copied.read_bytes() == target.read_bytes()
    write_gateway.remove_file(copied)
    assert not copied.exists()


def test_missing_pointer_is_downstream_consequence_not_primary_fault(
    monkeypatch, tmp_path: Path
) -> None:
    from apps_rg.l2_recipe.modular_resume_generation import (
        _phase1_materialize_lane_run_dir,
    )

    def missing(*_args, **_kwargs):
        raise FileNotFoundError("no latest lane pointer")

    monkeypatch.setattr(
        "apps_rg.l2_recipe.modular_lane_adapter.resolve_latest_lane_run_dir",
        missing,
    )
    emitted = {}

    def capture(**kwargs):
        emitted.update(kwargs)

    dispatch = {
        "fault": "exception",
        "exception_class": "OSError",
        "exception_message": "[Errno 22] Invalid argument",
        "traceback": "trace",
    }
    statuses = {"competencies": "error:[Errno 22] Invalid argument"}
    result = _phase1_materialize_lane_run_dir(
        repo=tmp_path,
        sections_root=tmp_path / "sections",
        integrated_dir=tmp_path / "run",
        lane="competencies",
        lane_provider="external_claude",
        lane_dispatch_results={"competencies": dispatch},
        lane_exec_status=statuses,
        emit_integrated_lane_pre_run_failure=capture,
        product_fail_closed=False,
    )

    assert result is None
    assert statuses["competencies"] == "error:[Errno 22] Invalid argument"
    assert emitted["dispatch_result"] == dispatch
    assert emitted["downstream_consequences"] == [
        {
            "stage": "PHASE1_LANE_MATERIALIZATION",
            "operation": "resolve_latest_lane_run_dir",
            "code": "LANE_RUN_POINTER_NOT_FOUND",
            "exception_class": "FileNotFoundError",
            "exception_message": "no latest lane pointer",
        }
    ]


def test_terminal_closeout_exception_emits_last_resort_receipt(
    monkeypatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.mandatory_run_outputs import MANDATORY_OUTPUT_HARD_STOP_GATE_ID
    from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import (
        _emit_terminal_mandatory_closeout,
    )

    for name in (
        "APPS_OTEL_COLLECTOR_SPANS_FILE",
        "APPS_OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)

    def explode(*_args, **_kwargs):
        raise RuntimeError("mandatory closeout exploded")

    monkeypatch.setattr(
        "apps_rg.runtime.mandatory_run_outputs.emit_mandatory_run_outputs",
        explode,
    )
    artifact_dir = tmp_path / "run"
    payload = {
        "fault": "UPSTREAM_L2_FAILURE",
        "exit_status": "error",
        "execution_status": "failed",
        "run_id": "w1-terminal",
        "request_id": "w1-request",
        "trace_root": "w1-trace",
    }

    result = _emit_terminal_mandatory_closeout(
        artifact_dir=artifact_dir,
        repo_root=tmp_path,
        payload=payload,
    )

    assert result["fault"] == "UPSTREAM_L2_FAILURE"
    assert result["completion_fault"] == MANDATORY_OUTPUT_HARD_STOP_GATE_ID
    assert result["mandatory_output_emit_error_class"] == "RuntimeError"
    receipt_path = Path(result["terminal_closeout_failure_receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "FAILED"
    assert receipt["upstream_outcome"]["fault"] == "UPSTREAM_L2_FAILURE"
    failure = receipt["closeout_failure"]
    assert failure["stage"] == "TERMINAL_MANDATORY_CLOSEOUT"
    assert failure["exception_class"] == "RuntimeError"
    assert failure["traceback"]
    assert receipt["otel_capture_status"] == "NOT_CONFIGURED"


def test_modular_replay_preserves_primary_errno_and_pointer_consequence(
    monkeypatch, tmp_path: Path
) -> None:
    from apps_rg.l2_recipe.modular_resume_generation import (
        ModularResumeInputPackage,
        ModularResumeProfile,
        run_modular_resume_generation,
    )
    from tests.helpers.standalone_repo_view import materialize_standalone_repo_view

    monkeypatch.delenv("APPS_RG_TEST_HARNESS", raising=False)
    monkeypatch.delenv("APPS_RG_ALLOW_PRODUCT_SHORTCUTS", raising=False)
    monkeypatch.delenv("APPS_OTEL_COLLECTOR_SPANS_FILE", raising=False)
    repo = materialize_standalone_repo_view(tmp_path)
    artifact_dir = repo / "w1_full_replay"
    artifact_dir.mkdir(parents=True)

    def raise_invalid_argument(**_kwargs):
        raise OSError(22, "Invalid argument")

    with patch(
        "apps_rg.l2_recipe.modular_resume_generation.run_canonical_apps_rg_from_cli_primitives",
        side_effect=raise_invalid_argument,
    ):
        run_modular_resume_generation(
            ModularResumeInputPackage(
                repo_root=repo,
                canonical_run_identity={
                    "request_id": "w1-replay-request",
                    "trace_root": "w1-replay-trace",
                    "tenant_id": "w1-replay-tenant",
                },
            ),
            artifact_dir,
            "w1-replay-run",
            ModularResumeProfile(
                phase1_invoke_real_lanes=True,
                run_phase0_synthetic_assembly=False,
                validate_rg_output_fixture=False,
            ),
        )

    lane_root = artifact_dir / "modular_r4" / "sections" / "competencies"
    trace = json.loads((lane_root / "section_exception_trace.json").read_text(encoding="utf-8"))
    assert trace["exception_class"] == "OSError"
    assert trace["exception_message"] == "[Errno 22] Invalid argument"
    assert trace["request_id"] == "w1-replay-request"
    assert trace["trace_root"] == "w1-replay-trace"

    failure = json.loads(
        (lane_root / "integrated_lane_pre_run_failure.json").read_text(encoding="utf-8")
    )
    assert failure["schema_version"] == "integrated_lane_pre_run_failure_v2"
    assert failure["primary_failure"]["exception_class"] == "OSError"
    assert failure["primary_failure"]["exception_message"] == "[Errno 22] Invalid argument"
    assert "missing_pointer" not in failure["lane_exec_status"]
    assert failure["downstream_consequences"][0]["code"] == "LANE_RUN_POINTER_NOT_FOUND"
