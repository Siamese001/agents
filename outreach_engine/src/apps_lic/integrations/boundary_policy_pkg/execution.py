"""Persisted artifact bundle cache resolution and bounded live execution for apps_research."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from apps_lic.integrations.boundary_policy_pkg.briefs import (
    _extract_priorities_from_text,
    _normalize_role,
)

_log = logging.getLogger(__name__)


def _find_valid_persisted_artifact_bundle(
    *,
    artifact_runs_root: Path | None,
    company_name: str,
    job_title: str = "",
    freshness_ttl_seconds: float = 7 * 86400.0,
) -> tuple[Any | None, str]:
    """Inspect persisted artifact runs root for a matching, valid, and fresh research bundle."""
    target_company = str(company_name or "").strip().lower()
    if not target_company:
        return None, "missing_company_name"
    search_roots: list[Path] = []
    if artifact_runs_root is not None and Path(artifact_runs_root).is_dir():
        search_roots.append(Path(artifact_runs_root))
    for fallback in (
        Path("artifacts/apps_research/runs"),
        Path("../artifacts/apps_research/runs"),
        Path(__file__).resolve().parents[5] / "artifacts" / "apps_research" / "runs",
    ):
        if fallback.is_dir() and fallback not in search_roots:
            search_roots.append(fallback)
    if not search_roots:
        return None, "root_not_dir" if artifact_runs_root else "no_root"

    for root in search_roots:
        try:
            subdirs = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
        except OSError:
            continue

        for run_dir in subdirs:
            handoff_path = run_dir / "apps_research_apps_rg_handoff_v2.json"
            meta_path = run_dir / "run_metadata.json"
            briefing_path = run_dir / "company_brief.md"
            if not briefing_path.is_file():
                briefing_path = run_dir / "briefing.md"
            brief_json_path = run_dir / "company_brief.json"
            if not brief_json_path.is_file():
                brief_json_path = run_dir / "briefing.json"
            if not (handoff_path.is_file() and meta_path.is_file() and briefing_path.is_file()):
                continue

            try:
                if (time.time() - meta_path.stat().st_mtime) > freshness_ttl_seconds:
                    continue
                handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            identity = handoff.get("identity") if isinstance(handoff, dict) else {}
            cand_company = str(
                identity.get("company_name") or identity.get("target_company") or meta.get("company_name") or meta.get("topic") or ""
            ).strip().lower()
            if not cand_company or cand_company != target_company:
                continue
            if job_title.strip():
                cand_role = str(identity.get("target_role") or "").strip()
                if cand_role and _normalize_role(job_title) != _normalize_role(cand_role):
                    continue

            exit_auth = handoff.get("exit_authorization") if isinstance(handoff.get("exit_authorization"), dict) else {}
            is_handoff_pass = handoff.get("status") == "PASS" or exit_auth.get("x3_code") == "X3D_ALLOW_FINISH"
            is_meta_verified = meta.get("is_verified") is True or meta.get("x3_code") == "X3D_ALLOW_FINISH" or exit_auth.get("x3_code") == "X3D_ALLOW_FINISH"
            if not (is_handoff_pass and is_meta_verified) or meta.get("is_blocked", False) or handoff.get("is_blocked", False):
                continue

            confidence = float(meta.get("confidence_score", 0.0) or handoff.get("confidence_score", 0.0) or 0.0)
            b_json: dict[str, Any] = {}
            if brief_json_path.is_file():
                try:
                    loaded_b = json.loads(brief_json_path.read_text(encoding="utf-8"))
                    if isinstance(loaded_b, dict):
                        b_json = loaded_b
                        if confidence <= 0.0:
                            confidence = float(b_json.get("confidence_score", 0.0) or 0.0)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    pass
            if confidence <= 0.0:
                confidence = 0.90

            try:
                brief_text = briefing_path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not brief_text:
                continue

            raw_priorities = b_json.get("priorities") or b_json.get("strategic_priorities") or ()
            priorities = tuple(str(item) for item in raw_priorities if str(item).strip()) if isinstance(raw_priorities, (list, tuple)) else ()
            if not priorities:
                priorities = tuple(_extract_priorities_from_text(brief_text))

            run_id = str(meta.get("run_id") or run_dir.name)
            trace_id = str(meta.get("trace_id") or f"trace-reused-{run_id}")
            request_id = str(meta.get("request_id") or f"req-reused-{run_id}")
            brief_sha = "sha256:" + hashlib.sha256(briefing_path.read_bytes()).hexdigest()
            meta_sha = "sha256:" + hashlib.sha256(meta_path.read_bytes()).hexdigest()
            manifest_sha = "sha256:" + hashlib.sha256(handoff_path.read_bytes()).hexdigest()

            from apps_lic.integrations.apps_research_bridge import EvidenceItem, ResearchResult
            from apps_lic.integrations.managed_research_delegation import (
                RequestForOutreachBriefing,
                _validate_persisted_research_artifacts,
            )

            candidate = ResearchResult(
                run_id=run_id,
                trace_id=trace_id,
                request_id=request_id,
                is_blocked=False,
                block_reason="",
                is_stale=False,
                evidence_items=(
                    EvidenceItem(
                        source_id=f"ev-reused-{run_id[:8]}",
                        label=f"persisted_research_artifact_{run_id[:8]}",
                        uri=str(briefing_path.resolve()),
                        source_type="persisted_artifact",
                        field_ref="company_brief",
                        confidence=confidence,
                    ),
                ),
                confidence_score=confidence,
                brief_sha256=brief_sha,
                company_brief_text=brief_text,
                strategic_priorities=priorities,
                fetch_duration_ms=1.0,
                audit_ref=trace_id,
                apps_research_handoff_envelope=handoff,
                research_artifact_dir=str(run_dir.resolve()),
                briefing_artifact_path=str(briefing_path.resolve()),
                result_metadata_digest=meta_sha,
                bundle_manifest_digest=manifest_sha,
                resolution_source="PERSISTED_ARTIFACT",
                is_verified=True,
            )
            req_ctx = (
                RequestForOutreachBriefing(
                    request_id=request_id, run_id=run_id, trace_id=trace_id, company_name=company_name, job_title=job_title
                )
                if (company_name or job_title)
                else None
            )
            valid, _, _ = _validate_persisted_research_artifacts(candidate, request=req_ctx)
            if valid:
                return candidate, "reused_persisted_artifact"

    return None, "no_valid_bundle_found"


def execute_bounded_live_research(
    *,
    invoke_fn: Callable[[], Any],
    timeout_seconds: float,
    max_retries: int,
    cost_per_call_usd: float = 0.0,
    cost_limit_usd: float = float("inf"),
    cumulative_cost_usd: float = 0.0,
    on_attempt_fn: Callable[[int], None] | None = None,
) -> Any:
    """Execute live research invocation with bounded timeouts and retries."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    current_cost = float(cumulative_cost_usd)
    last_exc: Exception | None = None
    for attempt in range(max(1, max_retries + 1)):
        if cost_limit_usd is not None and cost_per_call_usd > 0.0:
            if (current_cost + cost_per_call_usd) > cost_limit_usd:
                _log.warning(
                    "Cost limit would be exceeded on attempt %d (cost=%.2f, limit=%.2f); aborting retries",
                    attempt + 1,
                    current_cost + cost_per_call_usd,
                    cost_limit_usd,
                )
                break

        if on_attempt_fn is not None:
            on_attempt_fn(attempt)
        current_cost += cost_per_call_usd

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(invoke_fn)
        try:
            res = future.result(timeout=timeout_seconds)
            executor.shutdown(wait=False)
            return res
        except FuturesTimeoutError:
            executor.shutdown(wait=False, cancel_futures=True)
            last_exc = TimeoutError(f"apps_research timed out after {timeout_seconds}s (attempt {attempt + 1})")
            _log.warning("apps_research timeout on attempt %d: %s", attempt + 1, last_exc)
        except Exception as exc:  # noqa: BLE001
            executor.shutdown(wait=False)
            last_exc = exc
            _log.warning("apps_research failed on attempt %d: %s", attempt + 1, exc)
        if attempt < max_retries:
            time.sleep(0.01 * (attempt + 1))

    if last_exc:
        raise last_exc
    raise RuntimeError("Live research execution failed")


def build_cost_limit_exceeded_result(
    *, run_id: str, trace_id: str, request_id: str, cumulative_cost_usd: float,
    cost_per_call_usd: float, cost_limit_usd: float, t_start: float = 0.0,
) -> Any:
    """Build a blocked ResearchResult when cumulative cost limit is exceeded."""
    from apps_lic.integrations.apps_research_bridge import ResearchResult
    reason = f"COST_LIMIT_EXCEEDED: current spend ${cumulative_cost_usd:.2f} + ${cost_per_call_usd:.2f} exceeds limit ${cost_limit_usd:.2f}"
    return ResearchResult(
        run_id=run_id, trace_id=trace_id, request_id=request_id, is_blocked=True, block_reason=reason,
        is_stale=False, evidence_items=(), confidence_score=0.0, brief_sha256="", company_brief_text="",
        strategic_priorities=(), fetch_duration_ms=(time.time() * 1000.0 - t_start) if t_start > 0 else 5.0,
        audit_ref=trace_id, resolution_source="HERMETIC_FALLBACK", is_verified=False,
    )


def build_timeout_result(
    *, run_id: str, trace_id: str, request_id: str, error: Exception | str, t_start: float = 0.0,
) -> Any:
    """Build a blocked ResearchResult when live research invocation times out."""
    from apps_lic.integrations.apps_research_bridge import ResearchResult
    return ResearchResult(
        run_id=run_id, trace_id=trace_id, request_id=request_id, is_blocked=True, block_reason=f"TIMEOUT: {error}",
        is_stale=False, evidence_items=(), confidence_score=0.0, brief_sha256="", company_brief_text="",
        strategic_priorities=(), fetch_duration_ms=(time.time() * 1000.0 - t_start) if t_start > 0 else 5.0,
        audit_ref=trace_id, resolution_source="HERMETIC_FALLBACK", is_verified=False,
    )
