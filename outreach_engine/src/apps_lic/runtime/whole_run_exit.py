"""Whole-run exit evaluator (`X3`) and terminal manifest/receipt builders for `apps_lic`.

Enforces `INV-LIC-REAL-LLM-FOR-FINISH`:
- `X3D_ALLOW_FINISH` is ONLY permitted when `execution_mode == "REAL_LLM"` AND
  `x2_passed == True` AND `quorum_passed == True` AND `drafter_judge_orthogonal == True`.
- When `execution_mode == "OFFLINE_SMOKE"` (`--offline-smoke`), terminal disposition is
  ALWAYS isolated to `X3E_SAFE_ABSTAIN` (never `X3D_ALLOW_FINISH`).
- When fallback drafter (`used_fallback == True` or `drafter_family == "openai"`) drafted
  the sequence, routes to `X3B_ESCALATE_HITL` rather than allowing same-family self-judging.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

from apps_lic.runtime.model_registry import OutreachModelRegistry
from apps_lic.runtime.spine_contracts import (
    ExecutionMode,
    INV_LIC_REAL_LLM_FOR_FINISH,
    X3Disposition,
    ensure_sha256_digest,
)

TERMINAL_MANIFEST_SCHEMA_VERSION: str = "apps_lic.terminal_manifest.v1"
COMPLETION_RECEIPT_SCHEMA_VERSION: str = "apps_lic.completion_receipt.v1"


class WholeRunExitDecision(BaseModel):
    """Typed terminal decision returned by `evaluate_whole_run_exit`."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    mission_id: str
    execution_mode: ExecutionMode
    x3_disposition: X3Disposition
    legacy_x3_code: str
    quorum_passed: bool
    x2_passed: bool
    drafter_judge_orthogonal: bool
    used_fallback: bool
    drafter_family: str
    provider_id: str
    model_id: str
    pct_certificates_count: int = Field(default=0, ge=0)
    reason_codes: list[str] = Field(default_factory=list)
    invariant_id: str = INV_LIC_REAL_LLM_FOR_FINISH

    @property
    def allow_finish(self) -> bool:
        """Return True iff terminal disposition is `X3D_ALLOW_FINISH`."""
        return self.x3_disposition == X3Disposition.X3D_ALLOW_FINISH


def _resolve_execution_mode(
    execution_mode: ExecutionMode | str,
    *,
    offline_smoke: bool = False,
) -> ExecutionMode:
    if offline_smoke:
        return ExecutionMode.OFFLINE_SMOKE
    if isinstance(execution_mode, ExecutionMode):
        return execution_mode
    normalized = str(execution_mode).strip().upper()
    if normalized == ExecutionMode.OFFLINE_SMOKE.value:
        return ExecutionMode.OFFLINE_SMOKE
    return ExecutionMode.REAL_LLM


def evaluate_whole_run_exit(
    *,
    run_id: str = "run-default",
    mission_id: str = "mission-default",
    execution_mode: ExecutionMode | str = ExecutionMode.REAL_LLM,
    x2_passed: bool = True,
    quorum_passed: bool = True,
    drafter_judge_orthogonal: bool | None = None,
    used_fallback: bool = False,
    drafter_family: str | None = None,
    judge_families: Sequence[str] | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
    repairable_inline: bool = False,
    patch_rerun_eligible: bool = False,
    hitl_escalate: bool = False,
    pct_certificates_count: int = 0,
    offline_smoke: bool = False,
) -> WholeRunExitDecision:
    """Evaluate terminal 5-code `X3Disposition` under `INV-LIC-REAL-LLM-FOR-FINISH`."""
    mode = _resolve_execution_mode(execution_mode, offline_smoke=offline_smoke)
    pin = OutreachModelRegistry.get_model_pin("executive_outreach_generator")

    resolved_model_id = str(
        model_id
        or (pin.backup_model if used_fallback else pin.model)
    )
    is_fallback_model = bool(
        used_fallback
        or (pin.backup_model and resolved_model_id == pin.backup_model)
    )

    if drafter_family is not None:
        resolved_drafter_family = OutreachModelRegistry.normalize_provider_family(drafter_family)
    elif provider_id is not None:
        resolved_drafter_family = OutreachModelRegistry.normalize_provider_family(provider_id)
    elif is_fallback_model:
        resolved_drafter_family = OutreachModelRegistry.normalize_provider_family(
            pin.backup_provider or "openai"
        )
    elif model_id is not None:
        resolved_drafter_family = OutreachModelRegistry.normalize_provider_family(model_id)
    else:
        resolved_drafter_family = OutreachModelRegistry.normalize_provider_family(
            pin.provider
        )

    resolved_provider_id = str(provider_id or resolved_drafter_family)
    effective_used_fallback = bool(
        is_fallback_model or resolved_drafter_family == "openai"
    )

    active_judges = {
        OutreachModelRegistry.normalize_provider_family(jf)
        for jf in (judge_families or ("openai", "google", "local_vllm"))
    }
    family_orthogonal = (
        resolved_drafter_family not in active_judges
        and resolved_drafter_family != "openai"
        and not effective_used_fallback
    )
    if drafter_judge_orthogonal is None:
        effective_orthogonal = family_orthogonal
    else:
        effective_orthogonal = bool(drafter_judge_orthogonal and family_orthogonal)

    reasons: list[str] = []
    if mode == ExecutionMode.OFFLINE_SMOKE:
        disposition = X3Disposition.X3E_SAFE_ABSTAIN
        reasons.append("OFFLINE_SMOKE_ISOLATED_TO_SAFE_ABSTAIN")
    elif effective_used_fallback or resolved_drafter_family == "openai":
        disposition = X3Disposition.X3B_ESCALATE_HITL
        reasons.append("FALLBACK_DRAFTER_OPENAI_ESCALATE_HITL")
    elif not effective_orthogonal or hitl_escalate:
        disposition = X3Disposition.X3B_ESCALATE_HITL
        reasons.append("NON_ORTHOGONAL_JUDGE_OR_HITL_ESCALATION")
    elif (not x2_passed or not quorum_passed) and repairable_inline:
        disposition = X3Disposition.X3A_REPAIR_INLINE
        reasons.append("INLINE_RESERVE_REPAIR_ELIGIBLE")
    elif (not x2_passed or not quorum_passed) and patch_rerun_eligible:
        disposition = X3Disposition.X3C_PATCH_RERUN
        reasons.append("PATCH_RERUN_ELIGIBLE")
    elif (
        mode == ExecutionMode.REAL_LLM
        and x2_passed
        and quorum_passed
        and effective_orthogonal
        and not effective_used_fallback
    ):
        disposition = X3Disposition.X3D_ALLOW_FINISH
        reasons.append("REAL_LLM_ORTHOGONAL_QUORUM_AND_X2_VERIFIED")
    else:
        disposition = X3Disposition.X3E_SAFE_ABSTAIN
        if not x2_passed:
            reasons.append("X2_SEQUENCE_GATE_FAILED")
        if not quorum_passed:
            reasons.append("JUDGE_QUORUM_GATE_FAILED")
        if not reasons:
            reasons.append("SAFE_ABSTAIN_DEFAULT")

    legacy_code = (
        "X3D_ALLOW_FINISH"
        if disposition == X3Disposition.X3D_ALLOW_FINISH
        else "X3D_BLOCK"
    )

    return WholeRunExitDecision(
        run_id=str(run_id),
        mission_id=str(mission_id),
        execution_mode=mode,
        x3_disposition=disposition,
        legacy_x3_code=legacy_code,
        quorum_passed=bool(quorum_passed),
        x2_passed=bool(x2_passed),
        drafter_judge_orthogonal=bool(effective_orthogonal),
        used_fallback=bool(effective_used_fallback),
        drafter_family=resolved_drafter_family,
        provider_id=resolved_provider_id,
        model_id=resolved_model_id,
        pct_certificates_count=max(0, int(pct_certificates_count)),
        reason_codes=reasons,
    )


def build_terminal_manifest_payload(
    decision: WholeRunExitDecision,
    *,
    prompt_hash: str,
    allocation_plan_digest: str,
    artifacts: Sequence[str | dict[str, Any]],
    bundle_index_digest: str,
) -> dict[str, Any]:
    """Build payload conforming 100% to `apps_lic_terminal_manifest.v1.schema.json`."""
    normalized_artifacts: list[str | dict[str, Any]] = []
    for item in artifacts:
        if isinstance(item, str):
            normalized_artifacts.append(item)
        elif isinstance(item, dict):
            entry: dict[str, Any] = {
                "artifact_ref": str(item.get("artifact_ref", item.get("path", "artifact.json"))),
                "sha256": ensure_sha256_digest(item.get("sha256", item)),
            }
            if "artifact_id" in item and item["artifact_id"] is not None:
                entry["artifact_id"] = str(item["artifact_id"])
            if "byte_length" in item and item["byte_length"] is not None:
                entry["byte_length"] = max(0, int(item["byte_length"]))
            normalized_artifacts.append(entry)
    if not normalized_artifacts:
        normalized_artifacts.append("stage_execution_ledger.json")

    return {
        "schema_version": TERMINAL_MANIFEST_SCHEMA_VERSION,
        "run_id": decision.run_id,
        "mission_id": decision.mission_id,
        "execution_mode": decision.execution_mode.value,
        "x3_disposition": decision.x3_disposition.value,
        "provider_id": decision.provider_id,
        "model_id": decision.model_id,
        "prompt_hash": ensure_sha256_digest(prompt_hash),
        "allocation_plan_digest": ensure_sha256_digest(allocation_plan_digest),
        "artifacts": normalized_artifacts,
        "bundle_index_digest": ensure_sha256_digest(bundle_index_digest),
    }


def build_completion_receipt_payload(
    decision: WholeRunExitDecision,
    *,
    export_files: Sequence[str] | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    """Build payload conforming 100% to `apps_lic_completion_receipt.v1.schema.json`."""
    resolved_files = [str(f) for f in (export_files or []) if str(f).strip()]
    if not resolved_files:
        resolved_files = ["stage_execution_ledger.json", "terminal_manifest.json"]
    timestamp = completed_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": COMPLETION_RECEIPT_SCHEMA_VERSION,
        "run_id": decision.run_id,
        "mission_id": decision.mission_id,
        "completed_at": timestamp,
        "x3_disposition": decision.x3_disposition.value,
        "execution_mode": decision.execution_mode.value,
        "quorum_passed": bool(decision.quorum_passed),
        "x2_passed": bool(decision.x2_passed),
        "pct_certificates_count": max(0, int(decision.pct_certificates_count)),
        "export_files": resolved_files,
    }


def write_exit_artifacts(
    output_dir: str | Path,
    decision: WholeRunExitDecision,
    *,
    prompt_hash: str,
    allocation_plan_digest: str,
    artifacts: Sequence[str | dict[str, Any]],
    bundle_index_digest: str,
    export_files: Sequence[str] | None = None,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    """Write `terminal_manifest.json` and `completion_receipt.json` to `output_dir`."""
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    manifest_payload = build_terminal_manifest_payload(
        decision,
        prompt_hash=prompt_hash,
        allocation_plan_digest=allocation_plan_digest,
        artifacts=artifacts,
        bundle_index_digest=bundle_index_digest,
    )
    receipt_payload = build_completion_receipt_payload(
        decision,
        export_files=export_files,
    )
    manifest_path = base / "terminal_manifest.json"
    receipt_path = base / "completion_receipt.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt_path.write_text(
        json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(manifest_path, 0o644)
    os.chmod(receipt_path, 0o644)
    return manifest_path, receipt_path, manifest_payload, receipt_payload


__all__ = [
    "COMPLETION_RECEIPT_SCHEMA_VERSION",
    "TERMINAL_MANIFEST_SCHEMA_VERSION",
    "WholeRunExitDecision",
    "build_completion_receipt_payload",
    "build_terminal_manifest_payload",
    "evaluate_whole_run_exit",
    "write_exit_artifacts",
]
