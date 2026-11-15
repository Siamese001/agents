"""AppsResearchBridge implementation for outreach_engine briefing delegation."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from apps_lic.integrations.research_boundary_policy import (
    ResearchBoundaryPolicy,
    _build_canonical_sidecar,
    _find_valid_persisted_artifact_bundle,
    _resolve_canonical_targeting_brief,
    build_cost_limit_exceeded_result,
    build_timeout_result,
    execute_bounded_live_research,
)
from apps_lic.integrations.research_bridge_pkg.models import EvidenceItem, ResearchResult
from apps_lic.integrations.research_bridge_pkg.persistence import (
    build_hermetic_fallback_result,
    translate_and_persist_research_result,
)

_log = logging.getLogger(__name__)


class AppsResearchBridge:
    """Bridge delegating company intelligence synthesis to apps_research with durable artifact persistence."""

    SUPPORTED_CAPABILITIES = frozenset({"apps_research.v1", "apps_research.v2"})

    def __init__(
        self,
        capability_ref: str = "apps_research.v1",
        *,
        artifact_runs_root: Path | None = None,
        policy: ResearchBoundaryPolicy | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        cost_limit_usd: float | None = None,
        cost_per_call_usd: float | None = None,
        force_fresh: bool | None = None,
    ) -> None:
        self._capability_ref = capability_ref
        self._bridge_id = f"outreach_research_bridge:{uuid.uuid4().hex[:8]}"
        self._artifact_runs_root = Path(artifact_runs_root).resolve() if artifact_runs_root else None

        base_policy = policy or ResearchBoundaryPolicy()
        self.policy = ResearchBoundaryPolicy(
            timeout_seconds=timeout_seconds if timeout_seconds is not None else base_policy.timeout_seconds,
            max_retries=max_retries if max_retries is not None else base_policy.max_retries,
            cost_limit_usd=cost_limit_usd if cost_limit_usd is not None else base_policy.cost_limit_usd,
            cost_per_call_usd=cost_per_call_usd if cost_per_call_usd is not None else base_policy.cost_per_call_usd,
            force_fresh=force_fresh if force_fresh is not None else base_policy.force_fresh,
        )
        self.cumulative_cost_usd: float = 0.0
        self.live_invocation_count: int = 0
        self.failed_invocation_count: int = 0

    def fetch(
        self,
        *,
        company_name: str,
        job_title: str = "",
        capability_ref: str = "apps_research.v1",
        request_id: str = "",
        run_id: str = "",
        trace_id: str = "",
        job_description_ref: str = "",
        job_description_text: str = "",
        force_fresh: bool | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        cost_limit_usd: float | None = None,
    ) -> ResearchResult:
        t_start = time.time() * 1000.0
        req_id = request_id or f"req-{uuid.uuid4().hex[:8]}"
        r_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
        tr_id = trace_id or f"trace-{uuid.uuid4().hex[:8]}"
        bridge_trace_id = f"bridge:{self._bridge_id}:{tr_id}"

        effective_force_fresh = force_fresh if force_fresh is not None else self.policy.force_fresh
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.policy.timeout_seconds
        effective_retries = max_retries if max_retries is not None else self.policy.max_retries
        effective_cost_limit = cost_limit_usd if cost_limit_usd is not None else self.policy.cost_limit_usd
        cost_per_call = self.policy.cost_per_call_usd

        if not effective_force_fresh:
            if self._artifact_runs_root is not None:
                persisted_bundle, _ = _find_valid_persisted_artifact_bundle(
                    artifact_runs_root=self._artifact_runs_root,
                    company_name=company_name,
                    job_title=job_title,
                )
                if persisted_bundle is not None:
                    return persisted_bundle

            canonical_brief, canonical_path = _resolve_canonical_targeting_brief(
                company_name=company_name,
                job_title=job_title,
            )
            if canonical_brief:
                sidecar = _build_canonical_sidecar(
                    company_name=company_name,
                    brief_text=canonical_brief,
                    run_id=r_id,
                    trace_id=tr_id,
                    role_archetype=job_title or "technology_leadership",
                    handoff_persistence=self._artifact_runs_root is not None,
                )
                raw = SimpleNamespace(
                    run_id=r_id,
                    parent_run_id=r_id,
                    request_id=req_id,
                    trace_root=tr_id,
                    trace_id=tr_id,
                    tenant_id="default",
                    company_brief_text=canonical_brief,
                    support_coverage=0.90,
                    confidence_score=0.90,
                    is_blocked=False,
                    block_reason="",
                    evidence_items=[
                        EvidenceItem(
                            source_id="ev-canonical-1",
                            label="canonical_targeting_brief",
                            uri=canonical_path or "config/targeting",
                            source_type="company_brief",
                            field_ref="company_brief",
                            confidence=0.90,
                        )
                    ],
                    fec_run_context={
                        "company_brief": {
                            "apps_rg_targeting_brief_sidecar": sidecar,
                        }
                    },
                )
                return self._translate_and_persist(
                    raw=raw,
                    run_id=r_id,
                    trace_id=tr_id,
                    request_id=req_id,
                    t_start=t_start,
                    company_name=company_name,
                    job_title=job_title,
                    job_description_text=job_description_text,
                    resolution_source="CANONICAL_FIXTURE",
                )

        if (self.cumulative_cost_usd + cost_per_call) > effective_cost_limit:
            _log.warning(
                "Cost limit exceeded: cumulative=$%.2f + call=$%.2f > limit=$%.2f",
                self.cumulative_cost_usd,
                cost_per_call,
                effective_cost_limit,
            )
            return build_cost_limit_exceeded_result(
                run_id=r_id, trace_id=bridge_trace_id, request_id=req_id,
                cumulative_cost_usd=self.cumulative_cost_usd,
                cost_per_call_usd=cost_per_call, cost_limit_usd=effective_cost_limit, t_start=t_start,
            )

        resolution_source = "WEB_RESEARCH"
        raw: Any = None
        try:
            def _on_attempt(attempt_idx: int) -> None:
                self.cumulative_cost_usd += cost_per_call

            raw = execute_bounded_live_research(
                invoke_fn=lambda: self._invoke_apps_research(
                    company_name=company_name,
                    job_title=job_title,
                    capability_ref=capability_ref,
                    request_id=req_id,
                    run_id=r_id,
                    trace_id=tr_id,
                    job_description_ref=job_description_ref,
                    job_description_text=job_description_text,
                ),
                timeout_seconds=effective_timeout,
                max_retries=effective_retries,
                cost_per_call_usd=cost_per_call,
                cost_limit_usd=effective_cost_limit,
                cumulative_cost_usd=self.cumulative_cost_usd,
                on_attempt_fn=_on_attempt,
            )
            self.live_invocation_count += 1
        except TimeoutError as exc:
            self.failed_invocation_count += 1
            _log.warning("Live apps_research timed out: %s", exc)
            return build_timeout_result(
                run_id=r_id, trace_id=bridge_trace_id, request_id=req_id, error=exc, t_start=t_start
            )
        except Exception as exc:  # noqa: BLE001
            self.failed_invocation_count += 1
            _log.info("Live apps_research invocation bypassed or failed: %s", exc)

        brief_text = ""
        if raw is not None:
            brief_text = str(getattr(raw, "company_brief_text", "") or "").strip()

        if not brief_text or getattr(raw, "is_blocked", False):
            canonical_brief, canonical_path = _resolve_canonical_targeting_brief(
                company_name=company_name,
                job_title=job_title,
            )
            if canonical_brief:
                resolution_source = "CANONICAL_FIXTURE"
                brief_text = canonical_brief
                sidecar = _build_canonical_sidecar(
                    company_name=company_name,
                    brief_text=canonical_brief,
                    run_id=r_id,
                    trace_id=tr_id,
                    role_archetype=job_title or "technology_leadership",
                    handoff_persistence=self._artifact_runs_root is not None,
                )
                raw = SimpleNamespace(
                    run_id=r_id,
                    parent_run_id=r_id,
                    request_id=req_id,
                    trace_root=tr_id,
                    trace_id=tr_id,
                    tenant_id="default",
                    company_brief_text=canonical_brief,
                    support_coverage=0.90,
                    confidence_score=0.90,
                    is_blocked=False,
                    block_reason="",
                    evidence_items=[
                        EvidenceItem(
                            "ev-canonical-1",
                            "canonical_targeting_brief",
                            canonical_path or "config/targeting",
                            "company_brief",
                            "company_brief",
                            0.90,
                        )
                    ],
                    fec_run_context={"company_brief": {"apps_rg_targeting_brief_sidecar": sidecar}},
                )
            else:
                resolution_source = "HERMETIC_FALLBACK"
                return self._hermetic_fallback(
                    company_name=company_name,
                    job_title=job_title,
                    job_description_text=job_description_text,
                    req_id=req_id,
                    r_id=r_id,
                    bridge_trace_id=bridge_trace_id,
                    t_start=t_start,
                )

        return self._translate_and_persist(
            raw=raw,
            run_id=r_id,
            trace_id=tr_id,
            request_id=req_id,
            t_start=t_start,
            company_name=company_name,
            job_title=job_title,
            job_description_text=job_description_text,
            resolution_source=resolution_source,
        )

    def _invoke_apps_research(
        self,
        *,
        company_name: str,
        job_title: str,
        capability_ref: str,
        request_id: str,
        run_id: str,
        trace_id: str,
        job_description_ref: str = "",
        job_description_text: str = "",
    ) -> Any:
        from apps_research.integrations.governed_research_run import GovernedResearchRun
        from apps_research.integrations.spine_handoff import run_research_via_spine
        from apps_research.types.research_types import ResearchRequest

        research_request = ResearchRequest(
            topic=company_name,
            mode="brief",
            audience_style="executive",
            depth_profile="COMPANY_BRIEF_STANDARD",
            trace_id=trace_id,
            jd_context={
                "company_name": company_name,
                "job_title": job_title,
                "request_id": request_id,
                "run_id": run_id,
                "trace_root": trace_id,
                "output_format": "apps_rg_targeting_brief_v1",
                "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
                "content": job_description_text,
                "jd_text": job_description_text,
                "jd_ref": job_description_ref,
            },
        )
        runner = GovernedResearchRun()
        return run_research_via_spine(research_request, runner=runner)

    def _translate_and_persist(
        self,
        *,
        raw: Any,
        run_id: str,
        trace_id: str,
        request_id: str,
        t_start: float,
        company_name: str,
        job_title: str,
        job_description_text: str = "",
        resolution_source: str = "WEB_RESEARCH",
    ) -> ResearchResult:
        return translate_and_persist_research_result(
            artifact_runs_root=self._artifact_runs_root,
            raw=raw,
            run_id=run_id,
            trace_id=trace_id,
            request_id=request_id,
            t_start=t_start,
            company_name=company_name,
            job_title=job_title,
            job_description_text=job_description_text,
            resolution_source=resolution_source,
        )

    def _hermetic_fallback(
        self,
        *,
        company_name: str,
        job_title: str,
        job_description_text: str,
        req_id: str,
        r_id: str,
        bridge_trace_id: str,
        t_start: float,
    ) -> ResearchResult:
        return build_hermetic_fallback_result(
            artifact_runs_root=self._artifact_runs_root,
            company_name=company_name,
            job_title=job_title,
            job_description_text=job_description_text,
            req_id=req_id,
            r_id=r_id,
            bridge_trace_id=bridge_trace_id,
            t_start=t_start,
        )
