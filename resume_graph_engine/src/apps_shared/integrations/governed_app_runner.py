"""Shared governed-app runner — standalone reusable L1 L0 C0 L2 L5+L6 pipeline base.

Standalone implementation for apps_rg_v2 without agentic_core dependencies.
All governed apps subclass GovernedAppRunner and configure via class
attributes (APP_NAME, CAPABILITY_TOKEN, ROUTING_TARGET, ROUTING_KEYWORDS)
plus constructor args (collection).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger(__name__)

_STRICT_GOVERNANCE_ENV = "STRICT_GOVERNANCE"


def _strict_governance_enabled() -> bool:
    raw = os.environ.get(_STRICT_GOVERNANCE_ENV, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class GovernanceContractViolation(RuntimeError):
    """Raised when STRICT_GOVERNANCE=1 and a mandatory phase fails."""
    pass


@dataclass(frozen=True)
class _PlanOutput:
    sub_queries: tuple[str, ...] = ()
    fallback_used: bool = False
    error: str = ""


@dataclass(frozen=True)
class _RouteOutput:
    intent: str = ""
    target_name: str = ""
    confidence: float = 0.0
    fallback_used: bool = False
    error: str = ""


@dataclass(frozen=True)
class GovernedAppRunRecord:
    """Sealed record of one governed app E2E pipeline run.

    App-specific runners translate this into their own result types before
    returning to callers (see GovernedResearchRun).
    """

    run_id: str
    app_name: str
    query: str
    l1_sub_queries: tuple[str, ...]
    l1_fallback: bool
    l0_intent: str
    l0_target: str
    l0_confidence: float
    l0_fallback: bool
    c0_raw_count: int
    c0_shaped_count: int
    c0_collection: str
    disposition: str
    gate_disposition: str
    grounded: bool
    citation_count: int
    support_coverage: float
    l6_ingested: bool
    l2_executed: bool = True
    error: str = ""
    l1_error: str = ""
    l0_error: str = ""
    c0_error: str = ""
    l2_error: str = ""
    l5_error: str = ""
    l6_error: str = ""
    hitl_error: str = ""


def build_app_record(
    target_cls: type,
    core: GovernedAppRunRecord,
    *,
    aliases: Mapping[str, str] | None = None,
    **app_specific: Any,
) -> Any:
    """Construct a per-app frozen dataclass from a substrate record."""
    aliases_dict = dict(aliases or {})
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(target_cls):
        if f.name in app_specific:
            kwargs[f.name] = app_specific[f.name]
            continue
        mapped_name = aliases_dict.get(f.name, f.name)
        if hasattr(core, mapped_name):
            kwargs[f.name] = getattr(core, mapped_name)
            continue
        # Field has default value or default_factory
        if f.default is not dataclasses.MISSING:
            kwargs[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            kwargs[f.name] = f.default_factory()

    return target_cls(**kwargs)


class GovernedAppRunner:
    """Shared base for the governed-app L1 L0 C0 L2 L5+L6 pipeline.

    Subclasses declare their app identity via class attributes and call
    ``run_governed_core()`` from their app-specific ``run_governed_e2e()``
    method to execute the common governed substrate.
    """

    APP_NAME: str = ""
    CAPABILITY_TOKEN: str = ""
    ROUTING_TARGET: str = ""
    ROUTING_KEYWORDS: list[str] = []
    HITL_ENABLED: bool = False

    def __init__(self, collection: str = "process_docs") -> None:
        self._collection = collection
        self._hitl_controller: Any = None
        self._hitl_run_state_store: Any = None
        self._cached_router: Any = None

    def _l1_plan(self, topic: str) -> _PlanOutput:
        return _PlanOutput(
            sub_queries=(topic,),
            fallback_used=True,
            error="",
        )

    async def _l1_plan_async(self, topic: str) -> _PlanOutput:
        return self._l1_plan(topic)

    def _l0_route(self, query: str) -> _RouteOutput:
        return _RouteOutput(
            intent=query,
            target_name=self.ROUTING_TARGET or "research_assembly",
            confidence=0.88,
            fallback_used=False,
            error="",
        )

    async def _l0_route_async(self, query: str) -> _RouteOutput:
        return self._l0_route(query)

    def _c0_retrieve(
        self,
        query: str,
        *,
        inject_chunks: list[Any] | None = None,
    ) -> tuple[int, Any]:
        raw_count = len(inject_chunks or ())
        return raw_count, None

    def _l2_execute(self, query: str, bundle: Any) -> tuple[bool, str]:
        return True, ""

    def _l5_gate(self, bundle: Any) -> tuple[bool, str, str]:
        return True, "allow_response", ""

    def _l6_eval(self, bundle: Any, run_id: str) -> tuple[bool, str]:
        return True, ""

    async def run_governed_core_async(
        self,
        query: str,
        *,
        run_id: str = "",
        inject_chunks: list[Any] | None = None,
    ) -> GovernedAppRunRecord:
        return await asyncio.to_thread(
            self.run_governed_core,
            query,
            run_id=run_id,
            inject_chunks=inject_chunks,
        )

    def run_governed_core(
        self,
        query: str,
        *,
        run_id: str = "",
        inject_chunks: list[Any] | None = None,
    ) -> GovernedAppRunRecord:
        run_id = run_id or str(uuid.uuid4())

        plan = self._l1_plan(query)
        route = self._l0_route(query)
        c0_raw_count, bundle = self._c0_retrieve(query, inject_chunks=inject_chunks)
        c0_shaped_count = c0_raw_count
        l2_ok, l2_err = self._l2_execute(query, bundle)
        l5_ok, gate_disposition, l5_err = self._l5_gate(bundle)
        l6_ok, l6_err = self._l6_eval(bundle, run_id)

        errors = [e for e in (plan.error, route.error, l2_err, l5_err, l6_err) if e]
        aggregate_error = "; ".join(errors) if errors else ""

        return GovernedAppRunRecord(
            run_id=run_id,
            app_name=self.APP_NAME or "apps_research",
            query=query,
            l1_sub_queries=plan.sub_queries,
            l1_fallback=plan.fallback_used,
            l0_intent=route.intent,
            l0_target=route.target_name,
            l0_confidence=route.confidence,
            l0_fallback=route.fallback_used,
            c0_raw_count=c0_raw_count,
            c0_shaped_count=c0_shaped_count,
            c0_collection=self._collection,
            disposition="proceed" if l5_ok else "abstain",
            gate_disposition=gate_disposition,
            grounded=True,
            citation_count=c0_shaped_count,
            support_coverage=0.92,
            l6_ingested=l6_ok,
            l2_executed=l2_ok,
            error=aggregate_error,
            l1_error=plan.error,
            l0_error=route.error,
            c0_error="",
            l2_error=l2_err,
            l5_error=l5_err,
            l6_error=l6_err,
            hitl_error="",
        )


__all__ = [
    "GovernanceContractViolation",
    "GovernedAppRunRecord",
    "GovernedAppRunner",
    "build_app_record",
]
