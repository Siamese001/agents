"""W0 unit test for per-lane exception-trace persistence.

When a lane dispatch raises, ``run_lane_in_context`` must capture the traceback
(module + line) into the returned ``dispatch_result`` AND persist
``section_exception_trace.json`` into the lane artifact dir, so a failed integrated
run carries the exact origin instead of only ``str(exc)``
(apps_rg AIG E2E remediation, Wave 0 -- truthful instrumentation).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.orchestration.section_lane_executor import (
    LaneExecutionContext,
    run_lane_in_context,
)
from apps_rg.runtime.runtime_proof_layout import MODULAR_R4_SECTIONS_ROOT_ENV


def _ctx(sections_root: Path) -> LaneExecutionContext:
    return LaneExecutionContext(
        sections_root=str(sections_root),
        target_company="AIG",
        target_role="VP Global Head of Agentic AI Solutions",
        job_description_ref="",
        job_description_text="",
        manual_brief="",
        lane_provider="external_claude",
        lane_x1d_judges="",
        lane_mock_judges=False,
        integrated_artifact_dir=str(sections_root.parent),
        run_id="w1-run",
        canonical_run_identity={
            "request_id": "w1-request",
            "trace_root": "w1-trace",
            "tenant_id": "w1-tenant",
        },
    )


def test_exception_trace_persisted(monkeypatch, tmp_path):
    monkeypatch.delenv("APPS_OTEL_COLLECTOR_SPANS_FILE", raising=False)
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(tmp_path))
    captured = {}

    def boom(**kwargs):
        captured.update(kwargs)
        started = json.loads(
            (Path(kwargs["artifact_dir"]) / "lane_dispatch_attempt.json").read_text(
                encoding="utf-8"
            )
        )
        assert started["status"] == "STARTED"
        raise RuntimeError("kaboom-from-test")

    outcome = run_lane_in_context(_ctx(tmp_path), "ibm_bullets", dispatch_fn=boom)

    # The fault is still surfaced (control flow unchanged) ...
    assert outcome.error and "kaboom-from-test" in outcome.error
    dr = outcome.dispatch_result
    assert dr["fault"] == "exception"
    # ... and now enriched with structured trace fields.
    assert dr["error_type"] == "RuntimeError"
    assert dr["exception_class"] == "RuntimeError"
    assert dr["exception_message"] == "kaboom-from-test"
    assert dr["stage"] == "PHASE1_LANE_DISPATCH"
    assert dr["operation"]
    assert dr["source_component"] == __name__
    assert dr["callsite"]["function"] == "boom"
    assert dr["request_id"] == "w1-request"
    assert dr["trace_root"] == "w1-trace"
    assert dr["attempt"] == {"logical": 1, "transport": None}
    assert dr["provider_boundary"]["provider"] == "external_claude"
    assert dr["provider_boundary"]["canonical_dispatch_invoked"] is True
    assert dr["error_module"].endswith(".py")
    assert isinstance(dr["error_lineno"], int) and dr["error_lineno"] > 0
    assert "kaboom-from-test" in dr["traceback"]

    trace_file = tmp_path / "ibm_bullets" / "section_exception_trace.json"
    assert trace_file.is_file()
    payload = json.loads(trace_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "section_exception_trace_v2"
    assert payload["lane"] == "ibm_bullets"
    assert payload["error_lineno"] > 0
    assert payload["error_module"].endswith(".py")
    assert "kaboom-from-test" in payload["traceback"]
    assert Path(captured["artifact_dir"]).resolve() == trace_file.parent.resolve()
    assert payload["otel_capture_status"] == "NOT_CONFIGURED"
    otel = json.loads(
        (trace_file.parent / "failure_otel_trace_snapshot.json").read_text(encoding="utf-8")
    )
    assert otel["status"] == "NOT_CONFIGURED"

    attempt = json.loads(
        (trace_file.parent / "lane_dispatch_attempt.json").read_text(encoding="utf-8")
    )
    assert attempt["status"] == "FAILED"
    assert attempt["failure_ref"] == "section_exception_trace.json"


@pytest.mark.parametrize("lane", GENERATED_LANES)
def test_every_generated_lane_persists_the_w1_failure_bundle(
    monkeypatch, tmp_path: Path, lane: str
) -> None:
    monkeypatch.delenv("APPS_OTEL_COLLECTOR_SPANS_FILE", raising=False)
    sections_root = tmp_path / "sections"
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(sections_root))

    def injected_failure(**kwargs):
        lane_dir = Path(kwargs["artifact_dir"])
        assert lane_dir.is_dir()
        attempt = json.loads(
            (lane_dir / "lane_dispatch_attempt.json").read_text(encoding="utf-8")
        )
        assert attempt["status"] == "STARTED"
        raise OSError(22, f"injected-{lane}")

    outcome = run_lane_in_context(_ctx(sections_root), lane, dispatch_fn=injected_failure)

    lane_dir = sections_root / lane
    failure = json.loads(
        (lane_dir / "section_exception_trace.json").read_text(encoding="utf-8")
    )
    attempt = json.loads(
        (lane_dir / "lane_dispatch_attempt.json").read_text(encoding="utf-8")
    )
    otel = json.loads(
        (lane_dir / "failure_otel_trace_snapshot.json").read_text(encoding="utf-8")
    )
    assert outcome.exec_status == f"error:[Errno 22] injected-{lane}"
    assert failure["schema_version"] == "section_exception_trace_v2"
    assert failure["lane_id"] == lane
    assert failure["stage"] == "PHASE1_LANE_DISPATCH"
    assert failure["operation"] == "test_every_generated_lane_persists_the_w1_failure_bundle.<locals>.injected_failure"
    assert failure["source_component"] == __name__
    assert failure["exception_class"] == "OSError"
    assert failure["exception_message"] == f"[Errno 22] injected-{lane}"
    assert failure["traceback"]
    assert failure["artifact_dir"] == str(lane_dir.resolve())
    assert failure["sections_root"] == str(sections_root.resolve())
    assert failure["integrated_artifact_dir"] == str(tmp_path.resolve())
    assert failure["run_id"] == "w1-run"
    assert failure["request_id"] == "w1-request"
    assert failure["trace_root"] == "w1-trace"
    assert failure["tenant_id"] == "w1-tenant"
    assert failure["provider_boundary"] == {
        "provider": "external_claude",
        "resolution_source": "CLI_OVERRIDE",
        "canonical_dispatch_invoked": True,
        "provider_call_attempted": None,
        "attempt_evidence": "UNKNOWN_AT_LANE_EXCEPTION_BOUNDARY",
    }
    assert attempt["status"] == "FAILED"
    assert attempt["failure_ref"] == "section_exception_trace.json"
    assert otel["status"] == "NOT_CONFIGURED"
    assert not list(lane_dir.glob(".*.tmp"))


@pytest.mark.parametrize("unsafe_lane", ["", "../escape", "nested/lane"])
def test_lane_artifact_validation_fails_before_dispatch_with_durable_fallback(
    monkeypatch, tmp_path: Path, unsafe_lane: str
) -> None:
    monkeypatch.delenv("APPS_OTEL_COLLECTOR_SPANS_FILE", raising=False)
    sections_root = tmp_path / "sections"
    integrated = tmp_path / "integrated"
    ctx = _ctx(sections_root)
    ctx.integrated_artifact_dir = str(integrated)
    called = False

    def must_not_dispatch(**_kwargs):
        nonlocal called
        called = True
        return {}

    outcome = run_lane_in_context(ctx, unsafe_lane, dispatch_fn=must_not_dispatch)

    safe_lane = str(unsafe_lane or "unknown_lane").replace("/", "_").replace("\\", "_")
    fallback = integrated / "lane_dispatch_validation" / safe_lane
    failure = json.loads(
        (fallback / "section_exception_trace.json").read_text(encoding="utf-8")
    )
    assert called is False
    assert outcome.dispatch_result["provider_boundary"]["canonical_dispatch_invoked"] is False
    assert failure["operation"] == "validate_lane_artifact_dir"
    assert failure["source_component"] == "apps_rg.runtime.orchestration.section_lane_executor"
    assert failure["artifact_dir"] == str(fallback.resolve())
    assert (fallback / "failure_otel_trace_snapshot.json").is_file()
    assert not (fallback / "lane_dispatch_attempt.json").exists()


def test_successful_dispatch_writes_no_trace(monkeypatch, tmp_path):
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(tmp_path))
    def ok(**_kwargs):
        return {"exit_status": "ok", "x3_disposition": "X3_ALLOW"}

    outcome = run_lane_in_context(_ctx(tmp_path), "competencies", dispatch_fn=ok)
    assert outcome.exec_status == "ok"
    assert outcome.error is None
    assert not (tmp_path / "competencies" / "section_exception_trace.json").exists()
    attempt = json.loads(
        (tmp_path / "competencies" / "lane_dispatch_attempt.json").read_text(encoding="utf-8")
    )
    assert attempt["status"] == "COMPLETED"


def test_exception_snapshot_selects_exact_trace_root(monkeypatch, tmp_path):
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(tmp_path / "sections"))
    source = tmp_path / "collector.jsonl"
    source.write_text(
        json.dumps(
            {
                "resourceSpans": [
                    {
                        "scopeSpans": [
                            {
                                "spans": [
                                    {
                                        "name": "wrong-run",
                                        "traceId": "other-trace",
                                        "spanId": "1",
                                    },
                                    {
                                        "name": "lane-failure",
                                        "traceId": "provider-trace-id",
                                        "spanId": "2",
                                        "attributes": [
                                            {
                                                "key": "trace.root",
                                                "value": {"stringValue": "w1-trace"},
                                            }
                                        ],
                                    },
                                ]
                            }
                        ]
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPS_OTEL_COLLECTOR_SPANS_FILE", str(source))

    def boom(**_kwargs):
        raise OSError(22, "Invalid argument")

    outcome = run_lane_in_context(_ctx(tmp_path / "sections"), "competencies", dispatch_fn=boom)
    assert outcome.dispatch_result["otel_capture_status"] == "CAPTURED"
    snapshot = json.loads(
        (
            tmp_path
            / "sections"
            / "competencies"
            / "failure_otel_trace_snapshot.json"
        ).read_text(encoding="utf-8")
    )
    assert snapshot["status"] == "CAPTURED"
    assert [span["name"] for span in snapshot["spans"]] == ["lane-failure"]
