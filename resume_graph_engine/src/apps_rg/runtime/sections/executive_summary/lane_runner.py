"""Executive summary lane runner orchestrating the execution stages."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from apps_rg.runtime.sections.executive_summary_context_limits import (
    resolve_scratch_max_output_tokens,
)
from .stage_ingress import run_ingress_stage
from .stage_generation import run_generation_stage
from .stage_remediation import run_remediation_stage
from .stage_closeout import run_closeout_stage

def run_executive_summary_execution(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Single end-to-end executive_summary run: artifacts + X2/X1D/X3."""
    _ = resolve_scratch_max_output_tokens
    ctx = run_ingress_stage(args, artifact_dir_override=artifact_dir_override)
    run_generation_stage(ctx)
    run_remediation_stage(ctx)
    return run_closeout_stage(ctx)

__all__ = ["run_executive_summary_execution", "resolve_scratch_max_output_tokens"]
