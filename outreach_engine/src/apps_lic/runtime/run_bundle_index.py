"""Canonical spine run bundle indexer and artifact writer for `apps_lic`.

Writes `stage_execution_ledger.json`, `terminal_manifest.json`, `completion_receipt.json`,
and `RUN_BUNDLE_INDEX.json` with SHA-256 artifact digests and `0644` permissions.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_lic.runtime.spine_contracts import (
    ExecutionMode,
    SpineRunArtifacts,
    SpineStageId,
    SpineStageStatus,
    ensure_sha256_digest,
)
from apps_lic.runtime.stage_ledger import OutreachStageLedgerBuilder
from apps_lic.runtime.whole_run_exit import (
    WholeRunExitDecision,
    build_completion_receipt_payload,
    build_terminal_manifest_payload,
    evaluate_whole_run_exit,
)

RUN_BUNDLE_INDEX_SCHEMA_VERSION: str = "apps_lic.run_bundle_index.v1"


def _write_json_file(path: Path, payload: Mapping[str, Any]) -> tuple[str, int]:
    """Write JSON deterministically (`0644`) and return `(sha256_prefixed, byte_length)`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw_bytes)
    os.chmod(path, 0o644)
    digest = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
    return digest, len(raw_bytes)


def build_run_bundle_index(
    *,
    run_id: str,
    mission_id: str,
    execution_mode: ExecutionMode | str,
    x3_disposition: str,
    artifact_entries: Sequence[Mapping[str, Any]],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build deterministic `RUN_BUNDLE_INDEX.json` payload with SHA-256 artifact digests."""
    mode_val = (
        execution_mode.value
        if isinstance(execution_mode, ExecutionMode)
        else str(execution_mode)
    )
    normalized_entries: list[dict[str, Any]] = []
    for item in artifact_entries:
        normalized_entries.append(
            {
                "artifact_id": str(item.get("artifact_id", item.get("artifact_ref", "artifact"))),
                "artifact_ref": str(item.get("artifact_ref", "artifact.json")),
                "sha256": ensure_sha256_digest(item.get("sha256", "")),
                "byte_length": max(0, int(item.get("byte_length", 0))),
            }
        )
    return {
        "schema_version": RUN_BUNDLE_INDEX_SCHEMA_VERSION,
        "run_id": str(run_id),
        "mission_id": str(mission_id),
        "execution_mode": mode_val,
        "x3_disposition": str(x3_disposition),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "artifacts": normalized_entries,
    }


def write_canonical_spine_bundle(
    output_dir: str | Path,
    *,
    ledger_builder: OutreachStageLedgerBuilder,
    exit_decision: WholeRunExitDecision,
    prompt_hash: str | None = None,
    allocation_plan_digest: str | None = None,
    extra_export_files: Sequence[str] | None = None,
) -> SpineRunArtifacts:
    """Write all 4 canonical spine bundle JSON files and return `SpineRunArtifacts`."""
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)

    if not ledger_builder.is_complete():
        x2_status = (
            SpineStageStatus.PASS if exit_decision.x2_passed else SpineStageStatus.FAIL
        )
        x1d_status = (
            SpineStageStatus.PASS if exit_decision.quorum_passed else SpineStageStatus.FAIL
        )
        x3_status = (
            SpineStageStatus.PASS
            if exit_decision.allow_finish
            else SpineStageStatus.BLOCKED
        )
        ledger_builder.record_remaining_canonical_stages(
            stage_statuses={
                SpineStageId.X2.value: x2_status,
                SpineStageId.X1D.value: x1d_status,
                SpineStageId.X3.value: x3_status,
            },
            stage_metrics={
                SpineStageId.X2.value: {"x2_passed": exit_decision.x2_passed},
                SpineStageId.X1D.value: {
                    "quorum_passed": exit_decision.quorum_passed,
                    "drafter_judge_orthogonal": exit_decision.drafter_judge_orthogonal,
                },
                SpineStageId.X3.value: {
                    "x3_disposition": exit_decision.x3_disposition.value,
                    "pct_certificates_count": exit_decision.pct_certificates_count,
                },
            },
        )

    ledger_path = base / "stage_execution_ledger.json"
    receipt_path = base / "completion_receipt.json"
    manifest_path = base / "terminal_manifest.json"
    index_path = base / "RUN_BUNDLE_INDEX.json"

    export_files = [
        "stage_execution_ledger.json",
        "terminal_manifest.json",
        "completion_receipt.json",
        "RUN_BUNDLE_INDEX.json",
    ]
    for extra in extra_export_files or []:
        if str(extra) not in export_files:
            export_files.append(str(extra))

    ledger_payload = ledger_builder.to_dict()
    ledger_sha, ledger_bytes = _write_json_file(ledger_path, ledger_payload)

    receipt_payload = build_completion_receipt_payload(
        exit_decision,
        export_files=export_files,
    )
    receipt_sha, receipt_bytes = _write_json_file(receipt_path, receipt_payload)

    artifact_refs: list[dict[str, Any]] = [
        {
            "artifact_id": "stage_execution_ledger",
            "artifact_ref": "stage_execution_ledger.json",
            "sha256": ledger_sha,
            "byte_length": ledger_bytes,
        },
        {
            "artifact_id": "completion_receipt",
            "artifact_ref": "completion_receipt.json",
            "sha256": receipt_sha,
            "byte_length": receipt_bytes,
        },
    ]

    index_payload = build_run_bundle_index(
        run_id=exit_decision.run_id,
        mission_id=exit_decision.mission_id,
        execution_mode=exit_decision.execution_mode,
        x3_disposition=exit_decision.x3_disposition.value,
        artifact_entries=artifact_refs,
    )
    index_sha, index_bytes = _write_json_file(index_path, index_payload)

    manifest_artifacts = list(artifact_refs) + [
        {
            "artifact_id": "run_bundle_index",
            "artifact_ref": "RUN_BUNDLE_INDEX.json",
            "sha256": index_sha,
            "byte_length": index_bytes,
        }
    ]
    manifest_payload = build_terminal_manifest_payload(
        exit_decision,
        prompt_hash=prompt_hash or f"prompt:{exit_decision.run_id}",
        allocation_plan_digest=(
            allocation_plan_digest or ledger_builder.allocation_plan_digest
        ),
        artifacts=manifest_artifacts,
        bundle_index_digest=index_sha,
    )
    _write_json_file(manifest_path, manifest_payload)

    return SpineRunArtifacts(
        run_id=exit_decision.run_id,
        mission_id=exit_decision.mission_id,
        execution_mode=exit_decision.execution_mode,
        x3_disposition=exit_decision.x3_disposition,
        stage_ledger_path=ledger_path.as_posix(),
        terminal_manifest_path=manifest_path.as_posix(),
        completion_receipt_path=receipt_path.as_posix(),
        bundle_index_path=index_path.as_posix(),
        bundle_index_digest=index_sha,
        export_files=export_files,
        stage_ledger=ledger_payload,
        terminal_manifest=manifest_payload,
        completion_receipt=receipt_payload,
        bundle_index=index_payload,
    )


def execute_canonical_10_stage_spine(
    output_dir: str | Path,
    *,
    run_id: str = "run-default",
    mission_id: str = "mission-default",
    execution_mode: ExecutionMode | str = ExecutionMode.REAL_LLM,
    x2_passed: bool = True,
    quorum_passed: bool = True,
    drafter_judge_orthogonal: bool | None = None,
    used_fallback: bool = False,
    drafter_family: str | None = None,
    provider_id: str | None = None,
    model_id: str | None = None,
    pct_certificates_count: int = 0,
    offline_smoke: bool = False,
    allocation_plan_digest: str | None = None,
    candidate_graph_db_sha256: str | None = None,
    prompt_hash: str | None = None,
) -> SpineRunArtifacts:
    """Execute and persist all 10 canonical spine stages (`U0..X3`) in one call."""
    decision = evaluate_whole_run_exit(
        run_id=run_id,
        mission_id=mission_id,
        execution_mode=execution_mode,
        x2_passed=x2_passed,
        quorum_passed=quorum_passed,
        drafter_judge_orthogonal=drafter_judge_orthogonal,
        used_fallback=used_fallback,
        drafter_family=drafter_family,
        provider_id=provider_id,
        model_id=model_id,
        pct_certificates_count=pct_certificates_count,
        offline_smoke=offline_smoke,
    )
    builder = OutreachStageLedgerBuilder(
        run_id=decision.run_id,
        mission_id=decision.mission_id,
        execution_mode=decision.execution_mode,
        allocation_plan_digest=allocation_plan_digest,
        candidate_graph_db_sha256=candidate_graph_db_sha256,
    )
    return write_canonical_spine_bundle(
        output_dir,
        ledger_builder=builder,
        exit_decision=decision,
        prompt_hash=prompt_hash,
        allocation_plan_digest=allocation_plan_digest,
    )


__all__ = [
    "RUN_BUNDLE_INDEX_SCHEMA_VERSION",
    "build_run_bundle_index",
    "execute_canonical_10_stage_spine",
    "write_canonical_spine_bundle",
]
