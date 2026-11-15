"""Runtime layer for apps_lic."""

from __future__ import annotations

from apps_lic.runtime.run_bundle_index import (
    RUN_BUNDLE_INDEX_SCHEMA_VERSION,
    build_run_bundle_index,
    execute_canonical_10_stage_spine,
    write_canonical_spine_bundle,
)
from apps_lic.runtime.spine_contracts import (
    CANONICAL_SPINE_STAGE_ORDER,
    ExecutionMode,
    INV_LIC_REAL_LLM_FOR_FINISH,
    INV_SINGLE_CANONICAL_PIPELINE,
    SpineExecutionContext,
    SpineRunArtifacts,
    SpineStageId,
    SpineStageStatus,
    StageExecutionRecord,
    X3Disposition,
    ensure_sha256_digest,
    sanitize_stage_metrics,
)
from apps_lic.runtime.stage_ledger import (
    STAGE_LEDGER_SCHEMA_VERSION,
    OutreachStageLedgerBuilder,
    StageLedgerOrderError,
)
from apps_lic.runtime.whole_run_exit import (
    COMPLETION_RECEIPT_SCHEMA_VERSION,
    TERMINAL_MANIFEST_SCHEMA_VERSION,
    WholeRunExitDecision,
    build_completion_receipt_payload,
    build_terminal_manifest_payload,
    evaluate_whole_run_exit,
    write_exit_artifacts,
)

__all__ = [
    "CANONICAL_SPINE_STAGE_ORDER",
    "COMPLETION_RECEIPT_SCHEMA_VERSION",
    "ExecutionMode",
    "INV_LIC_REAL_LLM_FOR_FINISH",
    "INV_SINGLE_CANONICAL_PIPELINE",
    "OutreachStageLedgerBuilder",
    "RUN_BUNDLE_INDEX_SCHEMA_VERSION",
    "STAGE_LEDGER_SCHEMA_VERSION",
    "SpineExecutionContext",
    "SpineRunArtifacts",
    "SpineStageId",
    "SpineStageStatus",
    "StageExecutionRecord",
    "StageLedgerOrderError",
    "TERMINAL_MANIFEST_SCHEMA_VERSION",
    "WholeRunExitDecision",
    "X3Disposition",
    "build_completion_receipt_payload",
    "build_run_bundle_index",
    "build_terminal_manifest_payload",
    "ensure_sha256_digest",
    "evaluate_whole_run_exit",
    "execute_canonical_10_stage_spine",
    "sanitize_stage_metrics",
    "write_canonical_spine_bundle",
    "write_exit_artifacts",
]
