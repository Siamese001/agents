"""HOP pipeline substrate — shared inner-DAG executor for apps_*.

Standalone implementation for apps_rg_v2 without agentic_core dependencies.
"""

from __future__ import annotations

import importlib
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_log = logging.getLogger(__name__)


class StageStatus(str, Enum):
    """Terminal status of a single stage execution."""

    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    GATED = "GATED"


@dataclass(frozen=True)
class Checkpoint:
    """Immutable record of one stage's execution."""

    stage_id: int
    stage_name: str
    status: StageStatus
    output: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0


class HopStageSpec(BaseModel):
    """Frozen Pydantic declaration of one stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_id: int
    stage_name: str
    engine_module: str
    engine_class: str
    inputs: tuple[str, ...] = Field(default_factory=tuple)
    outputs: tuple[str, ...] = Field(default_factory=tuple)
    required: bool = True
    skip_when: str | None = None


class HopRegistry:
    """Ordered collection of HopStageSpec declarations."""

    def __init__(self, app_name: str) -> None:
        self.app_name = app_name
        self._stages: list[HopStageSpec] = []

    def register(self, spec: HopStageSpec) -> HopRegistry:
        self._stages.append(spec)
        return self

    def register_all(self, specs: list[HopStageSpec]) -> HopRegistry:
        for spec in specs:
            self.register(spec)
        return self

    def stages(self) -> list[HopStageSpec]:
        return list(self._stages)


@dataclass(frozen=True)
class HopRunRecord:
    """Sealed result of an entire hop pipeline execution."""

    run_id: str
    trace_id: str
    checkpoints: tuple[Checkpoint, ...]
    terminal_error: str = ""
    final_context: dict[str, Any] = field(default_factory=dict)


class HopPipelineExecutor:
    """Executes stages declared in a HopRegistry sequentially."""

    def __init__(
        self,
        registry: HopRegistry,
        *,
        seal_step_provider: Any | None = None,
    ) -> None:
        self._registry = registry
        self._seal_step_provider = seal_step_provider

    def run(
        self,
        context: dict[str, Any],
        *,
        run_id: str = "",
        trace_id: str = "",
    ) -> HopRunRecord:
        run_id = run_id or str(uuid.uuid4())
        trace_id = trace_id or run_id
        checkpoints: list[Checkpoint] = []
        current_context = dict(context)
        terminal_error = ""

        for spec in self._registry.stages():
            t0 = time.time()
            stage_out: dict[str, Any] = {}
            stage_err = ""
            status = StageStatus.COMPLETED

            try:
                mod = importlib.import_module(spec.engine_module)
                engine_cls = getattr(mod, spec.engine_class)
                engine = engine_cls()
                out = engine.execute(current_context)
                if isinstance(out, dict):
                    stage_out = out
                    current_context.update(out)
                else:
                    stage_out = {"result": out}
            except Exception as exc:  # noqa: BLE001
                stage_err = f"{type(exc).__name__}: {exc}"
                status = StageStatus.FAILED
                terminal_error = f"Stage {spec.stage_name} failed: {stage_err}"
                _log.warning("[HopPipelineExecutor] %s", terminal_error)

            duration_ms = int((time.time() - t0) * 1000)
            cp = Checkpoint(
                stage_id=spec.stage_id,
                stage_name=spec.stage_name,
                status=status,
                output=stage_out,
                error=stage_err,
                duration_ms=duration_ms,
            )
            checkpoints.append(cp)

            if status == StageStatus.FAILED and spec.required:
                break

        return HopRunRecord(
            run_id=run_id,
            trace_id=trace_id,
            checkpoints=tuple(checkpoints),
            terminal_error=terminal_error,
            final_context=current_context,
        )


__all__ = [
    "Checkpoint",
    "HopPipelineExecutor",
    "HopRegistry",
    "HopRunRecord",
    "HopStageSpec",
    "StageStatus",
]
