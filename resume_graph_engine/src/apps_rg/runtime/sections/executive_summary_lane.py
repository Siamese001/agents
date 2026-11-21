"""Executive summary section lane — clean-slate cutover to ``executive_summary_v2``.

Preserves public entrypoint ``run_executive_summary_execution`` and shared sibling-lane
constants/utilities (``resolve_provider_model_name``, ``write_x2_gate_outputs``) with
zero legacy post-LLM prose mutators.
"""
from __future__ import annotations

if __name__ == "__main__":
    raise ImportError(
        "This module is not an operator CLI entrypoint. "
        "Use the sole canonical public command: python -m resume_engine run"
    )

import argparse
import json
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.jd_resolution import default_jd_targeting_text
from apps_rg.runtime.section_cli_defaults import default_targeting_briefing_text

EXEC_SUMMARY_TEMP_DEFAULT = 0.45
EXEC_SUMMARY_TEMP_RANGE = (0.35, 0.55)
TARGET_COMPANY_DEFAULT = "Enterprise Target"
TARGET_TITLE_DEFAULT = "SVP Engineering"
from apps_rg.runtime.section_repair_ledger import infer_product_quality_with_repair_ledger
from apps_rg.runtime.sections.executive_summary_v2 import run_executive_summary_v2
from apps_rg.runtime.sections.executive_summary_v2.evidence_firewall import (
    APPS_RG_SRC_ROOT as REPO_ROOT,
    LANE_KEY,
    PROMPT_ID,
    sha16,
)
from apps_rg.runtime.sections.executive_summary_v2.prompt_and_generate import (
    TEMPLATE_PATH as PROMPT_TEMPLATE,
)
from apps_rg.runtime.sections.section_x2_gate_outputs import write_section_x2_gate_outputs

BASE_POINTER = REPO_ROOT / "apps_rg" / "base_resume_ssot" / "CURRENT_POINTER.json"
BASE_JSON_DEFAULT = REPO_ROOT / "apps_rg" / "base_resume_ssot" / "amit_ayer_base_resume_v1.json"

JD_TEXT_DEFAULT = default_jd_targeting_text()
BRIEFING_DEFAULT = default_targeting_briefing_text()


def write_json(path: Path, data: Any) -> None:
    _wg.ensure_dir(path.parent)
    _wg.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_provider_model_name(
    provider_request_data: dict[str, Any] | None,
    provider_result_data: dict[str, Any] | None,
) -> str | None:
    if provider_result_data and provider_result_data.get("model"):
        return str(provider_result_data["model"])
    if provider_request_data and provider_request_data.get("model"):
        return str(provider_request_data["model"])
    return None


def write_x2_gate_outputs(
    path: Path,
    gates: list[dict[str, Any]],
    *,
    section_id: str | None = None,
) -> None:
    if section_id:
        write_section_x2_gate_outputs(path.parent, section_id, gates)
        return
    failed = [g["gate_id"] for g in gates if not g.get("pass")]
    passed_count = sum(1 for g in gates if g.get("pass"))
    write_json(
        path,
        {
            "gates": gates,
            "failed_gates": failed,
            "x2_passed": passed_count,
            "x2_failed": len(failed),
            "total_x2_gates": len(gates),
        },
    )


def infer_product_quality(
    runtime_generation_status: str,
    x2_gates: list[dict[str, Any]],
    resume_display_text: str = "",
    claim_ledger: list[dict[str, Any]] | None = None,
    *,
    graph_only_fact_tight_synthesis: bool = False,
    artifact_dir: Path | None = None,
) -> tuple[str, str]:
    _ = (resume_display_text, claim_ledger, graph_only_fact_tight_synthesis)
    failed = [g["gate_id"] for g in x2_gates if not g.get("pass")]
    return infer_product_quality_with_repair_ledger(
        runtime_generation_status=runtime_generation_status,
        x2_failed_gate_ids=failed,
        pass_reason="REAL_LLM output passed all deterministic X2 gates.",
        artifact_dir=artifact_dir,
    )


def run_executive_summary_execution(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Single end-to-end executive_summary run delegated to greenfield executive_summary_v2."""
    return run_executive_summary_v2(args, artifact_dir_override=artifact_dir_override)


__all__ = [
    "BASE_JSON_DEFAULT",
    "BASE_POINTER",
    "BRIEFING_DEFAULT",
    "EXEC_SUMMARY_TEMP_DEFAULT",
    "EXEC_SUMMARY_TEMP_RANGE",
    "JD_TEXT_DEFAULT",
    "LANE_KEY",
    "PROMPT_ID",
    "PROMPT_TEMPLATE",
    "REPO_ROOT",
    "TARGET_COMPANY_DEFAULT",
    "TARGET_TITLE_DEFAULT",
    "infer_product_quality",
    "resolve_provider_model_name",
    "run_executive_summary_execution",
    "sha16",
    "write_json",
    "write_x2_gate_outputs",
]
