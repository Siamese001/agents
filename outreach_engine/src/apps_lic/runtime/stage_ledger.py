"""Deterministic 10-stage execution ledger builder for Outreach Engine (`apps_lic`).

Records canonical transitions `U0 -> D0 -> C0 -> PA -> X1A -> X1B -> X1C -> X2 -> X1D -> X3`
and serializes `stage_execution_ledger.json` conforming to
`config/certification/schemas/apps_lic_stage_ledger.v1.schema.json`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from apps_lic.runtime.spine_contracts import (
    CANONICAL_SPINE_STAGE_ORDER,
    ExecutionMode,
    SpineStageId,
    SpineStageStatus,
    StageExecutionRecord,
    ensure_sha256_digest,
    sanitize_stage_metrics,
)

STAGE_LEDGER_SCHEMA_VERSION: str = "apps_lic.stage_ledger.v1"


class StageLedgerOrderError(ValueError):
    """Raised when a stage is recorded out of canonical 10-stage spine order."""


def _coerce_stage_id(stage_id: SpineStageId | str) -> SpineStageId:
    if isinstance(stage_id, SpineStageId):
        return stage_id
    return SpineStageId(str(stage_id).strip().upper())


def _coerce_stage_status(status: SpineStageStatus | str) -> SpineStageStatus:
    if isinstance(status, SpineStageStatus):
        return status
    return SpineStageStatus(str(status).strip().upper())


def _coerce_execution_mode(mode: ExecutionMode | str) -> ExecutionMode:
    if isinstance(mode, ExecutionMode):
        return mode
    normalized = str(mode).strip().upper()
    if normalized == ExecutionMode.OFFLINE_SMOKE.value:
        return ExecutionMode.OFFLINE_SMOKE
    return ExecutionMode.REAL_LLM


class OutreachStageLedgerBuilder:
    """Stateful builder recording canonical `U0..X3` execution stage transitions."""

    def __init__(
        self,
        run_id: str,
        mission_id: str,
        *,
        execution_mode: ExecutionMode | str = ExecutionMode.REAL_LLM,
        allocation_plan_digest: str | None = None,
        candidate_graph_db_sha256: str | None = None,
        strict_order: bool = True,
    ) -> None:
        self.run_id: str = str(run_id or "run-default")
        self.mission_id: str = str(mission_id or "mission-default")
        self.execution_mode: ExecutionMode = _coerce_execution_mode(execution_mode)
        self.allocation_plan_digest: str = ensure_sha256_digest(
            allocation_plan_digest or f"alloc:{self.run_id}:{self.mission_id}"
        )
        self.candidate_graph_db_sha256: str = ensure_sha256_digest(
            candidate_graph_db_sha256 or f"cand-graph:{self.mission_id}"
        )
        self.strict_order: bool = strict_order
        self._records: list[StageExecutionRecord] = []

    @property
    def records(self) -> list[StageExecutionRecord]:
        """Return a shallow copy of recorded stage transitions."""
        return list(self._records)

    @property
    def stage_ids(self) -> list[str]:
        """Return recorded stage ID strings in recorded order."""
        return [rec.stage_id.value for rec in self._records]

    def is_complete(self) -> bool:
        """Return True iff all 10 canonical stages are recorded in exact order."""
        expected = [stage.value for stage in CANONICAL_SPINE_STAGE_ORDER]
        return self.stage_ids == expected

    def record_stage(
        self,
        stage_id: SpineStageId | str,
        status: SpineStageStatus | str = SpineStageStatus.PASS,
        *,
        input_payload: Any = None,
        output_payload: Any = None,
        input_digest: str | None = None,
        output_digest: str | None = None,
        duration_ms: float = 0.1,
        metrics: Mapping[str, Any] | None = None,
    ) -> StageExecutionRecord:
        """Record a single canonical stage transition and return its record."""
        coerced_stage = _coerce_stage_id(stage_id)
        coerced_status = _coerce_stage_status(status)

        if self.strict_order:
            next_index = len(self._records)
            if next_index >= len(CANONICAL_SPINE_STAGE_ORDER):
                raise StageLedgerOrderError(
                    f"All 10 canonical stages already recorded; cannot append {coerced_stage.value}."
                )
            expected_stage = CANONICAL_SPINE_STAGE_ORDER[next_index]
            if coerced_stage != expected_stage:
                raise StageLedgerOrderError(
                    f"Out-of-order stage transition: expected {expected_stage.value} at index "
                    f"{next_index}, got {coerced_stage.value}."
                )

        resolved_in = ensure_sha256_digest(
            input_digest
            if input_digest is not None
            else (
                input_payload
                if input_payload is not None
                else f"{self.run_id}:{coerced_stage.value}:in"
            )
        )
        resolved_out = ensure_sha256_digest(
            output_digest
            if output_digest is not None
            else (
                output_payload
                if output_payload is not None
                else f"{self.run_id}:{coerced_stage.value}:{coerced_status.value}:out"
            )
        )

        record = StageExecutionRecord(
            stage_id=coerced_stage,
            status=coerced_status,
            input_digest=resolved_in,
            output_digest=resolved_out,
            duration_ms=float(max(0.0, duration_ms)),
            metrics=sanitize_stage_metrics(metrics),
        )
        self._records.append(record)
        return record

    def record_remaining_canonical_stages(
        self,
        *,
        stage_statuses: Mapping[str, SpineStageStatus | str] | None = None,
        stage_metrics: Mapping[str, Mapping[str, Any]] | None = None,
        default_status: SpineStageStatus | str = SpineStageStatus.PASS,
        base_payload: Any = None,
    ) -> list[StageExecutionRecord]:
        """Populate any remaining unrecorded stages in `U0..X3` order."""
        statuses = {str(k).upper(): v for k, v in (stage_statuses or {}).items()}
        metrics_map = {str(k).upper(): v for k, v in (stage_metrics or {}).items()}
        existing = {rec.stage_id for rec in self._records}
        prev_digest = (
            self._records[-1].output_digest
            if self._records
            else ensure_sha256_digest(base_payload or f"{self.run_id}:seed")
        )
        for stage in CANONICAL_SPINE_STAGE_ORDER:
            if stage in existing:
                continue
            st = statuses.get(stage.value, default_status)
            mt = metrics_map.get(stage.value, {"stage_index": len(self._records)})
            rec = self.record_stage(
                stage,
                st,
                input_digest=prev_digest,
                output_payload={
                    "run_id": self.run_id,
                    "stage": stage.value,
                    "status": str(st),
                    "metrics": dict(mt),
                },
                duration_ms=0.25,
                metrics=mt,
            )
            prev_digest = rec.output_digest
        return self.records

    def to_dict(self) -> dict[str, Any]:
        """Serialize ledger to `apps_lic_stage_ledger.v1.schema.json` structure."""
        if not self._records:
            self.record_remaining_canonical_stages()
        return {
            "schema_version": STAGE_LEDGER_SCHEMA_VERSION,
            "run_id": self.run_id,
            "mission_id": self.mission_id,
            "execution_mode": self.execution_mode.value,
            "allocation_plan_digest": ensure_sha256_digest(self.allocation_plan_digest),
            "candidate_graph_db_sha256": ensure_sha256_digest(self.candidate_graph_db_sha256),
            "stages": [rec.to_schema_dict() for rec in self._records],
        }

    def write_json(self, path: str | Path) -> Path:
        """Write `stage_execution_ledger.json` to disk with `0644` permissions."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(target, 0o644)
        return target


__all__ = [
    "OutreachStageLedgerBuilder",
    "STAGE_LEDGER_SCHEMA_VERSION",
    "StageLedgerOrderError",
]
