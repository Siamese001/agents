"""Isolated Phase-1 lane execution context (serial + parallel dispatcher)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from apps_rg.runtime.failure_evidence import (
    atomic_write_json,
    capture_failure_otel_evidence,
    exception_failure_envelope,
)
from apps_rg.runtime.runtime_proof_layout import MODULAR_R4_SECTIONS_ROOT_ENV
from apps_rg.runtime.section_cli_defaults import CLI_PROVIDER_RESOLUTION_CLI_OVERRIDE
from apps_rg.runtime.section_lane_temperature import default_temperature_for_section
from apps_rg.runtime.sections_root_manifest import SECTIONS_ROOT_MANIFEST_FILENAME

# 2026-06-13: removed `_ENV_OVERLAY_LOCK` (a process-global lock formerly held across
# the ENTIRE lane dispatch as a "external model-safe throttle"). It serialized all wave lanes
# despite parallel=True/cap=N (measured: 23-min fully-serial baseline). Since
# MODULAR_R4_SECTIONS_ROOT is a run-level CONSTANT, run_lane_in_context now sets it
# idempotently and lock-free — true wave parallelism, validated at 704s vs 1383s
# (1.96x) with identical per-lane X3 outcomes. See memory
# apps-rg-parallel-orchestration-nonfunctional.


@dataclass
class LaneExecutionContext:
    """Per-lane env isolation for in-process Phase-1 dispatch."""

    sections_root: str
    target_company: str
    target_role: str
    job_description_ref: str
    job_description_text: str
    manual_brief: str
    lane_provider: Any
    # str (same provider for every lane) OR Callable[[lane_id], str] for per-lane defaults.
    # str (same judges for every lane) OR Callable[[lane_id], str] for per-lane composite-judge
    # defaults (competencies -> openai_chatgpt; bullets/narratives -> gemini_pro;
    # summaries/headline -> panel).
    lane_x1d_judges: Any
    lane_mock_judges: bool
    lane_provider_resolution_source: Any = CLI_PROVIDER_RESOLUTION_CLI_OVERRIDE
    lane_allow_non_allow_exit_zero: bool = False
    generation_mode: str = "strategic_tailor"
    integrated_artifact_dir: str = ""
    run_id: str = ""
    canonical_run_identity: dict[str, Any] = field(default_factory=dict)

    def env_overlay(self) -> dict[str, str | None]:
        return {MODULAR_R4_SECTIONS_ROOT_ENV: self.sections_root}

    def x1d_judges_for_lane(self, lane: str) -> Any:
        """Resolve the X1D judge CSV for ``lane`` (honors a per-lane callable)."""
        judges = self.lane_x1d_judges
        if callable(judges):
            return judges(lane)
        return judges

    def provider_for_lane(self, lane: str) -> str:
        """Resolve the generator provider for ``lane`` (honors a per-lane callable)."""
        provider = self.lane_provider
        if callable(provider):
            return str(provider(lane))
        return str(provider)

    def provider_resolution_source_for_lane(self, lane: str) -> str:
        """Resolve the provider-resolution evidence label for ``lane``."""
        source = self.lane_provider_resolution_source
        if callable(source):
            return str(source(lane))
        return str(source or CLI_PROVIDER_RESOLUTION_CLI_OVERRIDE)


@dataclass
class LaneDispatchOutcome:
    lane: str
    dispatch_result: dict[str, Any] = field(default_factory=dict)
    exec_status: str = ""
    error: str | None = None


def ensure_sections_root_manifest(ctx: LaneExecutionContext) -> None:
    """Ensure sections_root_manifest.json exists beside ctx.sections_root before lane execution."""
    root_text = str(ctx.sections_root or "").strip()
    if not root_text:
        return
    sections_root = Path(root_text).expanduser().resolve()
    sections_root.mkdir(parents=True, exist_ok=True)
    manifest_path = sections_root / SECTIONS_ROOT_MANIFEST_FILENAME
    if not manifest_path.is_file():
        from apps_rg.runtime.run_bundle_index import repo_relative_posix
        from apps_rg.runtime.runtime_proof_layout import find_repo_root
        from apps_rg.runtime.sections_root_manifest import emit_sections_root_manifest

        repo = find_repo_root()
        try:
            sections_root.relative_to(repo)
        except ValueError:
            return
        int_ref = (
            repo_relative_posix(repo, Path(ctx.integrated_artifact_dir).resolve())
            if ctx.integrated_artifact_dir
            else None
        )
        try:
            emit_sections_root_manifest(
                repo_root=repo,
                sections_root_abs=sections_root,
                source_env_literal=MODULAR_R4_SECTIONS_ROOT_ENV,
                correlation_id=ctx.canonical_run_identity.get("correlation_id"),
                integrated_run_ref=int_ref,
                run_links_ref=None,
                notes=f"section_lane_executor sections root (run_id={ctx.run_id})",
            )
        except OSError:
            if not manifest_path.is_file():
                raise


def _validated_lane_artifact_dir(ctx: LaneExecutionContext, lane: str) -> Path:
    root_text = str(ctx.sections_root or "").strip()
    lane_text = str(lane or "").strip()
    if not root_text:
        raise ValueError("sections_root is required for lane dispatch")
    if not lane_text or lane_text in {".", ".."} or Path(lane_text).name != lane_text:
        raise ValueError(f"lane must be one safe path component: {lane!r}")
    sections_root = Path(root_text).expanduser().resolve()
    ensure_sections_root_manifest(ctx)
    lane_dir = (sections_root / lane_text).resolve()
    try:
        lane_dir.relative_to(sections_root)
    except ValueError as exc:
        raise ValueError(f"lane artifact directory escapes sections_root: {lane!r}") from exc
    lane_dir.mkdir(parents=True, exist_ok=True)
    return lane_dir


def _persist_dispatch_attempt(
    ctx: LaneExecutionContext,
    lane: str,
    lane_dir: Path,
    *,
    status: str,
    failure_ref: str = "",
) -> None:
    payload = {
        "schema_version": "apps_rg.lane_dispatch_attempt.v1",
        "stage": "PHASE1_LANE_DISPATCH",
        "lane_id": lane,
        "status": status,
        "run_id": ctx.run_id,
        "integrated_artifact_dir": str(ctx.integrated_artifact_dir or ""),
        "sections_root": str(Path(ctx.sections_root).resolve()),
        "lane_artifact_dir": str(lane_dir),
        "identity": dict(ctx.canonical_run_identity),
        "failure_ref": failure_ref,
    }
    atomic_write_json(lane_dir / "lane_dispatch_attempt.json", payload)


def _persist_exception_trace(
    ctx: LaneExecutionContext,
    lane: str,
    exc: BaseException,
    *,
    lane_dir: Path,
    operation: str,
    source_component: str,
    provider: str,
    provider_resolution_source: str,
    dispatch_invoked: bool,
) -> dict[str, Any]:
    """Capture a failed lane dispatch traceback and best-effort persist it.

    Returns the structured trace fields (merged into the ``dispatch_result``) and writes
    ``section_exception_trace.json`` into the lane artifact dir, so a failed integrated
    run carries the exact module/line instead of only ``str(exc)``
    (apps_rg AIG E2E remediation, Wave 0 -- truthful instrumentation for E2E-05/E2E-11).
    """
    try:
        evidence_sections_root: Path | None = Path(ctx.sections_root).resolve()
    except (OSError, ValueError):
        evidence_sections_root = None
    envelope = exception_failure_envelope(
        exc,
        stage="PHASE1_LANE_DISPATCH",
        operation=operation,
        source_component=source_component,
        artifact_dir=lane_dir,
        lane_id=lane,
        sections_root=evidence_sections_root,
        integrated_artifact_dir=(
            Path(ctx.integrated_artifact_dir) if ctx.integrated_artifact_dir else None
        ),
        identity=ctx.canonical_run_identity,
        run_id=ctx.run_id,
        provider=provider,
        provider_resolution_source=provider_resolution_source,
        dispatch_invoked=dispatch_invoked,
    )
    fields: dict[str, Any] = {
        **envelope,
        # Legacy aliases retained for existing consumers while v1 receipts migrate.
        "error_type": envelope["exception_class"],
        "error_module": envelope["callsite"]["file"],
        "error_lineno": envelope["callsite"]["line"],
    }
    try:
        otel = capture_failure_otel_evidence(
            artifact_dir=lane_dir,
            trace_root=str(envelope.get("trace_root") or ""),
            stage="PHASE1_LANE_DISPATCH",
            operation=operation,
        )
        fields["otel_failure_snapshot"] = "failure_otel_trace_snapshot.json"
        fields["otel_capture_status"] = str(otel.get("status") or "")
        payload = {
            "lane": lane,
            "error": str(exc),
            **fields,
            "schema_version": "section_exception_trace_v2",
        }
        atomic_write_json(lane_dir / "section_exception_trace.json", payload)
    except OSError:
        # Best-effort: trace persistence must never mask the original lane fault.
        pass
    return fields


def run_lane_in_context(
    ctx: LaneExecutionContext,
    lane: str,
    *,
    dispatch_fn: Callable[..., dict[str, Any]],
) -> LaneDispatchOutcome:
    """Run one lane dispatch with the run-constant MODULAR_R4_SECTIONS_ROOT.

    ``sections_root`` is identical for every lane in a run (see ``env_overlay`` — it
    sets only that one constant key). Set it idempotently and **lock-free** so lanes
    can execute concurrently. The prior implementation wrapped the ENTIRE lane (C0 +
    generation + X1D judges + X3) in ``_ENV_OVERLAY_LOCK`` and save/restored the env
    per-lane, which forced strict-serial execution despite ``parallel=True``/``cap=N``
    (measured: 23-min fully-serial baseline) AND was racy — one lane's per-lane restore
    could unset the root while a concurrent lane was still running. Because the value is
    a run-level constant, a lock-free idempotent set is correct; no per-lane restore is
    needed (the constant must persist for the run's lifetime). See memory
    ``apps-rg-parallel-orchestration-nonfunctional``.
    """
    operation = str(getattr(dispatch_fn, "__qualname__", "") or getattr(dispatch_fn, "__name__", ""))
    source_component = str(getattr(dispatch_fn, "__module__", ""))
    provider = ""
    provider_resolution_source = ""
    dispatch_invoked = False
    try:
        lane_dir = _validated_lane_artifact_dir(ctx, lane)
    except Exception as exc:
        fallback_root = (
            Path(ctx.integrated_artifact_dir).resolve()
            if str(ctx.integrated_artifact_dir or "").strip()
            else Path.cwd() / ".runtime" / "apps_rg_lane_failures"
        )
        safe_lane = str(lane or "unknown_lane").replace("/", "_").replace("\\", "_")
        lane_dir = fallback_root / "lane_dispatch_validation" / safe_lane
        lane_dir.mkdir(parents=True, exist_ok=True)
        trace_fields = _persist_exception_trace(
            ctx,
            lane,
            exc,
            lane_dir=lane_dir,
            operation="validate_lane_artifact_dir",
            source_component=__name__,
            provider=provider,
            provider_resolution_source=provider_resolution_source,
            dispatch_invoked=False,
        )
        return LaneDispatchOutcome(
            lane=lane,
            dispatch_result={"fault": "exception", "error": str(exc), **trace_fields},
            exec_status=f"error:{exc!s}",
            error=str(exc),
        )
    try:
        _persist_dispatch_attempt(ctx, lane, lane_dir, status="STARTED")
        for k, v in ctx.env_overlay().items():
            if v is not None and os.environ.get(k) != v:
                os.environ[k] = v
        provider = ctx.provider_for_lane(lane)
        provider_resolution_source = ctx.provider_resolution_source_for_lane(lane)
        dispatch_invoked = True
        result = dispatch_fn(
            target_company=ctx.target_company,
            target_role=ctx.target_role,
            jd="",
            job_description_ref=ctx.job_description_ref,
            job_description_text=ctx.job_description_text,
            manual_brief=ctx.manual_brief,
            resume_path="",
            source_resume_text="",
            generation_mode=ctx.generation_mode,
            artifact_dir=str(lane_dir),
            section=lane,
            lane_provider=provider,
            lane_provider_resolution_source=provider_resolution_source,
            lane_temperature=default_temperature_for_section(lane),
            lane_x1d_judges=ctx.x1d_judges_for_lane(lane),
            lane_mock_judges=ctx.lane_mock_judges,
            lane_allow_non_allow_exit_zero=bool(ctx.lane_allow_non_allow_exit_zero),
        )
        dr = dict(result) if isinstance(result, dict) else {}
        _persist_dispatch_attempt(ctx, lane, lane_dir, status="COMPLETED")
        return LaneDispatchOutcome(lane=lane, dispatch_result=dr, exec_status="ok")
    except Exception as exc:  # guardian: allow-broad-exception -- phase1 fail-soft boundary
        trace_fields = _persist_exception_trace(
            ctx,
            lane,
            exc,
            lane_dir=lane_dir,
            operation=operation,
            source_component=source_component,
            provider=provider,
            provider_resolution_source=provider_resolution_source,
            dispatch_invoked=dispatch_invoked,
        )
        try:
            _persist_dispatch_attempt(
                ctx,
                lane,
                lane_dir,
                status="FAILED",
                failure_ref="section_exception_trace.json",
            )
        except OSError:
            pass
        return LaneDispatchOutcome(
            lane=lane,
            dispatch_result={"fault": "exception", "error": str(exc), **trace_fields},
            exec_status=f"error:{exc!s}",
            error=str(exc),
        )


__all__ = [
    "LaneExecutionContext",
    "LaneDispatchOutcome",
    "ensure_sections_root_manifest",
    "run_lane_in_context",
]
