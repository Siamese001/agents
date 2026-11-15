"""Canonical 10-stage execution spine contracts for Outreach Engine (`apps_lic`).

Defines stage identifiers (`U0 -> D0 -> C0 -> PA -> X1A -> X1B -> X1C -> X2 -> X1D -> X3`),
execution modes (`REAL_LLM`, `OFFLINE_SMOKE`), 5-code `X3Disposition`, and typed records.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from apps_lic.runtime.model_registry import OutreachModelRegistry

INV_LIC_REAL_LLM_FOR_FINISH: str = "INV-LIC-REAL-LLM-FOR-FINISH"
INV_SINGLE_CANONICAL_PIPELINE: str = "INV-SINGLE-CANONICAL-PIPELINE"

_DIGEST_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")


class SpineStageId(str, Enum):
    """Canonical 10-stage execution order for Outreach Engine runs."""

    U0 = "U0"
    D0 = "D0"
    C0 = "C0"
    PA = "PA"
    X1A = "X1A"
    X1B = "X1B"
    X1C = "X1C"
    X2 = "X2"
    X1D = "X1D"
    X3 = "X3"


CANONICAL_SPINE_STAGE_ORDER: tuple[SpineStageId, ...] = (
    SpineStageId.U0,
    SpineStageId.D0,
    SpineStageId.C0,
    SpineStageId.PA,
    SpineStageId.X1A,
    SpineStageId.X1B,
    SpineStageId.X1C,
    SpineStageId.X2,
    SpineStageId.X1D,
    SpineStageId.X3,
)


class SpineStageStatus(str, Enum):
    """Deterministic per-stage execution outcomes."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SKIPPED_NON_PRODUCT = "SKIPPED_NON_PRODUCT"


class ExecutionMode(str, Enum):
    """Runtime execution mode governing terminal disposition eligibility."""

    REAL_LLM = "REAL_LLM"
    OFFLINE_SMOKE = "OFFLINE_SMOKE"


class X3Disposition(str, Enum):
    """Canonical 5-code whole-run exit dispositions at stage X3."""

    X3A_REPAIR_INLINE = "X3A_REPAIR_INLINE"
    X3B_ESCALATE_HITL = "X3B_ESCALATE_HITL"
    X3C_PATCH_RERUN = "X3C_PATCH_RERUN"
    X3D_ALLOW_FINISH = "X3D_ALLOW_FINISH"
    X3E_SAFE_ABSTAIN = "X3E_SAFE_ABSTAIN"


def ensure_sha256_digest(value: Any, *, prefix: bool = True) -> str:
    """Normalize or compute a schema-compliant SHA-256 digest string."""
    if isinstance(value, str):
        stripped = value.strip()
        if _DIGEST_RE.match(stripped):
            raw_hex = stripped.split("sha256:", 1)[-1]
            return f"sha256:{raw_hex}" if prefix else raw_hex
        raw_bytes = stripped.encode("utf-8")
    elif isinstance(value, bytes):
        raw_bytes = value
    elif value is None:
        raw_bytes = b"apps_lic:empty"
    else:
        try:
            serialized = json.dumps(value, sort_keys=True, default=str)
        except TypeError:
            serialized = str(value)
        raw_bytes = serialized.encode("utf-8")

    hex_digest = hashlib.sha256(raw_bytes).hexdigest()
    return f"sha256:{hex_digest}" if prefix else hex_digest


def sanitize_stage_metrics(
    metrics: Mapping[str, Any] | None,
) -> dict[str, int | float | str | bool | None]:
    """Coerce stage metrics dictionary values to schema-allowed scalar types."""
    if not metrics:
        return {}
    clean: dict[str, int | float | str | bool | None] = {}
    for key, val in metrics.items():
        str_key = str(key)
        if val is None or isinstance(val, (bool, int, float, str)):
            clean[str_key] = val
        else:
            try:
                clean[str_key] = json.dumps(val, sort_keys=True, default=str)
            except TypeError:
                clean[str_key] = str(val)
    return clean


def _default_primary_model_id() -> str:
    pin = OutreachModelRegistry.get_model_pin("executive_outreach_generator")
    return pin.model


def _default_primary_provider_id() -> str:
    pin = OutreachModelRegistry.get_model_pin("executive_outreach_generator")
    return pin.provider


class StageExecutionRecord(BaseModel):
    """Single stage execution record conforming to `apps_lic_stage_ledger.v1.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    stage_id: SpineStageId
    status: SpineStageStatus = SpineStageStatus.PASS
    input_digest: str
    output_digest: str
    duration_ms: float = Field(default=0.1, ge=0.0)
    metrics: dict[str, int | float | str | bool | None] = Field(default_factory=dict)

    def to_schema_dict(self) -> dict[str, Any]:
        """Serialize strictly to the 6 properties permitted by StageRecord schema."""
        return {
            "stage_id": self.stage_id.value,
            "status": self.status.value,
            "input_digest": ensure_sha256_digest(self.input_digest),
            "output_digest": ensure_sha256_digest(self.output_digest),
            "duration_ms": float(max(0.0, self.duration_ms)),
            "metrics": sanitize_stage_metrics(self.metrics),
        }


class SpineExecutionContext(BaseModel):
    """Immutable-by-convention execution context carried across canonical spine stages."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    mission_id: str
    execution_mode: ExecutionMode = ExecutionMode.REAL_LLM
    provider_id: str = Field(default_factory=_default_primary_provider_id)
    model_id: str = Field(default_factory=_default_primary_model_id)
    used_fallback: bool = False
    drafter_family: str = Field(default_factory=_default_primary_provider_id)
    judge_families: tuple[str, ...] = ("openai", "google", "local_vllm")
    prompt_hash: str = Field(default_factory=lambda: ensure_sha256_digest("default-prompt"))
    allocation_plan_digest: str = Field(
        default_factory=lambda: ensure_sha256_digest("default-allocation-plan")
    )
    candidate_graph_db_sha256: str = Field(
        default_factory=lambda: ensure_sha256_digest("default-candidate-graph-db")
    )
    artifact_dir: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpineRunArtifacts(BaseModel):
    """Paths and payloads emitted by a completed canonical 10-stage spine run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    mission_id: str
    execution_mode: ExecutionMode
    x3_disposition: X3Disposition
    stage_ledger_path: str
    terminal_manifest_path: str
    completion_receipt_path: str
    bundle_index_path: str
    bundle_index_digest: str
    export_files: list[str] = Field(default_factory=list)
    stage_ledger: dict[str, Any] = Field(default_factory=dict)
    terminal_manifest: dict[str, Any] = Field(default_factory=dict)
    completion_receipt: dict[str, Any] = Field(default_factory=dict)
    bundle_index: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "CANONICAL_SPINE_STAGE_ORDER",
    "ExecutionMode",
    "INV_LIC_REAL_LLM_FOR_FINISH",
    "INV_SINGLE_CANONICAL_PIPELINE",
    "SpineExecutionContext",
    "SpineRunArtifacts",
    "SpineStageId",
    "SpineStageStatus",
    "StageExecutionRecord",
    "X3Disposition",
    "ensure_sha256_digest",
    "sanitize_stage_metrics",
]
