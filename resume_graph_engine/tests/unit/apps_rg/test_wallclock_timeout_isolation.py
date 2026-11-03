"""Wave 1 unit and subprocess isolation tests for hard wall-clock timeouts and daemon pools."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.judges.bullet_pool_claude_selector import _write_selector_timing_receipt
from apps_rg.runtime.judges.executive_summary_x1d import (
    JudgeOutput,
    _invoke_judge_with_bounded_retries,
    _write_artifact,
)
from apps_rg.runtime.orchestration.managed_section_lane_dispatcher import (
    dispatch_phase1_lanes_managed,
)
from apps_rg.runtime.orchestration.section_lane_executor import LaneExecutionContext
from apps_rg.runtime.providers.external_provider import urlopen_provider_request
from apps_rg.runtime.providers.wallclock_http_guard import (
    clear_cancelled_artifact_dirs,
    is_lane_or_dir_cancelled,
)
from apps_rg.runtime.sections.ExecutiveVoiceRepairAgent import (
    repair_section_with_executive_voice_agent,
)


@pytest.fixture(autouse=True)
def _reset_cancelled_dirs() -> Any:
    clear_cancelled_artifact_dirs()
    yield
    clear_cancelled_artifact_dirs()


class _TrickleFakeResponse:
    """Simulates a slow-trickle HTTP body that sends bytes well within socket idle timeout
    but exceeds total wall-clock cap."""

    def __init__(self, *, chunks: int = 30, delay_s: float = 0.04) -> None:
        self._chunks = chunks
        self._delay_s = delay_s
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self.closed = False

    def read(self) -> bytes:
        buf = bytearray()
        for _ in range(self._chunks):
            if self.closed:
                break
            time.sleep(self._delay_s)
            buf.extend(b"x")
        return bytes(buf)

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> _TrickleFakeResponse:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def test_urlopen_provider_request_enforces_hard_wallclock_on_trickle_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trickle streams that never violate per-chunk socket idle timeout still fail closed at wall-clock cap."""

    def _fake_urlopen(req: Any, timeout: float = 60.0) -> _TrickleFakeResponse:
        return _TrickleFakeResponse(chunks=40, delay_s=0.03)  # ~1.2s total trickle

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    req = urllib.request.Request("https://example.invalid/v1/judge", data=b"{}", method="POST")

    t0 = time.monotonic()
    with pytest.raises(TimeoutError, match="wall-clock timeout"):
        with urlopen_provider_request(req, timeout=0.18) as resp:
            _ = resp.read()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.65, f"Trickle response bypassed wall-clock cap: elapsed={elapsed:.3f}s"


def test_phase1_dispatcher_cuts_off_stalled_lane_and_blocks_post_timeout_writes(tmp_path: Path) -> None:
    """Stalled lane fails closed at lane_timeout_s, independent sibling finishes, and late writes are suppressed."""
    sections_root = tmp_path / "modular_r4" / "sections"
    late_write_attempted = threading.Event()
    late_write_finished = threading.Event()

    def _dispatch_fn(**kwargs: Any) -> dict[str, Any]:
        lane = str(kwargs.get("section") or "")
        lane_dir = Path(str(kwargs.get("artifact_dir") or (sections_root / lane)))
        if lane == "unify_bullets":
            time.sleep(0.70)
            late_write_attempted.set()
            _write_artifact(lane_dir / "orphaned_judge.json", {"late": True})
            _write_selector_timing_receipt(lane_dir, {"phase": "orphaned_late"})
            repair_section_with_executive_voice_agent(
                section_id="headline",
                candidate_data={"headline_line": "SVP Engineering | AI Platforms | Enterprise Scale | Cloud"},
                diagnostic={"repair_needed": True},
                mock_mode=True,
                artifact_dir=lane_dir,
            )
            late_write_finished.set()
            return {"section": lane, "exit_status": "ok"}
        return {"section": lane, "exit_status": "ok"}

    ctx = LaneExecutionContext(
        sections_root=str(sections_root),
        target_company="Acme",
        target_role="VP AI",
        job_description_ref="",
        job_description_text="",
        manual_brief="",
        lane_provider="mock",
        lane_x1d_judges=(),
        lane_mock_judges=True,
    )

    t0 = time.monotonic()
    outcomes = dispatch_phase1_lanes_managed(
        ("unify_bullets", "ibm_bullets", "unify_narrative", "ibm_narrative"),
        ctx,
        dispatch_fn=_dispatch_fn,
        parallel=True,
        max_parallel=4,
        lane_timeout_s=0.35,
        run_timeout_s=5.0,
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 1.2, f"Dispatcher did not return promptly on lane timeout: {elapsed:.3f}s"
    assert outcomes["unify_bullets"].exec_status == "error:LANE_TIMEOUT"
    assert outcomes["unify_bullets"].dispatch_result["fault"] == "timeout"
    assert outcomes["unify_narrative"].exec_status == "pre_run_blocked:UPSTREAM_DEPENDENCY_FAILED"
    assert outcomes["ibm_bullets"].exec_status == "ok"
    assert outcomes["ibm_narrative"].exec_status == "ok"

    # Wait for the abandoned worker thread to wake up and attempt late writes.
    assert late_write_finished.wait(timeout=1.5)
    unify_dir = sections_root / "unify_bullets"
    assert is_lane_or_dir_cancelled(unify_dir)
    assert not (unify_dir / "orphaned_judge.json").exists()
    assert not (unify_dir / "bullet_pool_claude_selector_timing.json").exists()
    assert not (unify_dir / "x1_repair_receipt.json").exists()


def test_phase1_whole_run_deadline_aborts_pending_lanes(tmp_path: Path) -> None:
    """Whole-run deadline aborts remaining queued lanes without hanging."""
    sections_root = tmp_path / "sections"

    def _slow_dispatch(**kwargs: Any) -> dict[str, Any]:
        time.sleep(0.25)
        return {"section": kwargs.get("section"), "exit_status": "ok"}

    ctx = LaneExecutionContext(
        sections_root=str(sections_root),
        target_company="Acme",
        target_role="VP",
        job_description_ref="",
        job_description_text="",
        manual_brief="",
        lane_provider="mock",
        lane_x1d_judges=(),
        lane_mock_judges=True,
    )
    outcomes = dispatch_phase1_lanes_managed(
        ("competencies", "slalom_bullets", "unify_bullets"),
        ctx,
        dispatch_fn=_slow_dispatch,
        parallel=True,
        max_parallel=1,
        lane_timeout_s=1.0,
        run_timeout_s=0.18,
    )
    assert outcomes["competencies"].exec_status in {"error:RUN_TIMEOUT", "error:LANE_TIMEOUT"}
    assert outcomes["slalom_bullets"].exec_status == "pre_run_blocked:PHASE1_RUN_TIMEOUT"
    assert outcomes["unify_bullets"].exec_status == "pre_run_blocked:PHASE1_RUN_TIMEOUT"


def test_judge_bounded_retries_respect_total_wallclock_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """Judge retry loop stops once cumulative judge_http.total_budget_seconds is exhausted."""
    monkeypatch.setenv("APPS_RG_JUDGE_TOTAL_BUDGET_SECONDS", "0.12")
    attempts: list[int] = []

    def _retriable_fail(attempt_no: int) -> JudgeOutput:
        attempts.append(attempt_no)
        time.sleep(0.14)
        return JudgeOutput(
            judge_id="x1d_openai_exec_summary",
            provider_name="OpenAI ChatGPT",
            provider_key="openai_chatgpt",
            evaluator_mode="BLOCKED_PROVIDER_UNAVAILABLE",
            provider_status="BLOCKED_PROVIDER_UNAVAILABLE",
            model_name="test-model",
            provider_available=False,
            provider_blocked=True,
            exact_provider_error="Read timed out",
        )

    out = _invoke_judge_with_bounded_retries(
        _retriable_fail,
        provider_key="openai_chatgpt",
        section_id="executive_summary",
    )
    assert out.provider_blocked is True
    assert attempts == [1], f"Expected budget cap to stop retries after attempt 1, got {attempts}"


def test_stalled_daemon_workers_do_not_block_process_exit(tmp_path: Path) -> None:
    """Subprocess running stalled phase1 and patch-run workers exits cleanly in <2.0s."""
    repo_root = Path(__file__).resolve().parents[4]
    script = """
import pathlib, tempfile, time
from types import SimpleNamespace
from apps_rg.runtime.orchestration.managed_section_lane_dispatcher import dispatch_phase1_lanes_managed
from apps_rg.runtime.orchestration.patch_run_wave_dispatch import dispatch_patch_lanes_wave_parallel
from apps_rg.runtime.orchestration.section_lane_executor import LaneExecutionContext

tmp = pathlib.Path(tempfile.mkdtemp())
sections_root = tmp / "modular_r4" / "sections"
sections_root.mkdir(parents=True, exist_ok=True)

ctx = LaneExecutionContext(
    sections_root=str(sections_root),
    target_company="Acme",
    target_role="VP",
    job_description_ref="",
    job_description_text="",
    manual_brief="",
    lane_provider="mock",
    lane_x1d_judges=(),
    lane_mock_judges=True,
)
dispatch_phase1_lanes_managed(
    ("competencies",),
    ctx,
    dispatch_fn=lambda **kw: (time.sleep(30.0), {"exit_status": "ok"})[1],
    parallel=True,
    max_parallel=1,
    lane_timeout_s=0.12,
    run_timeout_s=1.0,
)

plan = SimpleNamespace(repo=tmp, run_dir=tmp, target_lanes=["competencies"])
dispatch_patch_lanes_wave_parallel(
    plan,
    lane_provider="mock",
    dispatch=lambda **kw: (time.sleep(30.0), {"exit_status": "ok"})[1],
    sections_root=sections_root,
    lane_timeout=0.12,
    run_timeout=2.0,
    clock_start=time.monotonic(),
)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_root}:{repo_root / 'resume_graph_engine' / 'src'}:{repo_root / 'outreach_engine' / 'src'}"
    env["APPS_RG_DISABLE_PROGRESS"] = "1"

    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    elapsed = time.monotonic() - t0
    assert proc.returncode == 0, f"Subprocess failed: stderr={proc.stderr}"
    assert elapsed < 2.0, f"Process shutdown hung waiting for stalled worker threads ({elapsed:.2f}s >= 2.0s)"
