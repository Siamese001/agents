"""Stage 1a: Ingress proof pool loading and artifact directory setup."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *
from .parent_proxy import _lane_attr

from .stage_ingress_dispatch import run_ingress_dispatch


def run_ingress_setup(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Load section proof pool, freeze initial payload, and prepare artifact_dir."""
    from apps_rg.runtime.sections.resume_employment_bullets import collect_employment_bullets
    from apps_rg.runtime.c0.section_proof_loader import (
        apply_proof_pool_to_usage_ledger,
        load_section_proof_for_lane,
    )

    from apps_rg.runtime.ingress.executive_summary_targeting_ingress import (
        prepare_executive_summary_targeting_ingress,
    )

    briefing_raw = str(getattr(args, "briefing", "") or "")
    targeting_ingress = prepare_executive_summary_targeting_ingress(
        jd_text=_lane_attr("_args_jd_text", _args_jd_text)(args),
        briefing_raw=briefing_raw,
        target_role=str(getattr(args, "target_role", "") or ""),
        target_title=_lane_attr("_args_target_title", _args_target_title)(args),
        repo_root=REPO_ROOT,
    )
    if (
        isinstance(targeting_ingress.briefing_selection_receipt, dict)
        and targeting_ingress.briefing_selection_receipt.get("fail_closed")
    ):
        raise RuntimeError(
            str(
                targeting_ingress.briefing_selection_receipt.get("truncation_or_selection_reason")
                or "briefing_fail_closed"
            )
        )

    pool, base, base_path, base_hash, front_spine = load_section_proof_for_lane(
        section_id="executive_summary",
        args=args,
        repo_root=REPO_ROOT,
        collect_employment_bullets_fn=collect_employment_bullets,
        jd_text_override=targeting_ingress.jd_text,
        briefing_text_override=targeting_ingress.briefing_text_bounded,
    )
    selected_fact_plan = pool.selected_fact_plan
    allowed_fact_ids = pool.allowed_fact_ids
    allowed_fact_ids_ordered = list(pool.allowed_fact_ids_ordered)
    proof_pool_metadata = _lane_attr("_reconcile_final_plan_c03_allowlist", _reconcile_final_plan_c03_allowlist)(
        pool.proof_pool_metadata,
        allowed_fact_ids=allowed_fact_ids,
        proof_pool_digest=str(pool.proof_pool_digest or ""),
        jd_text=targeting_ingress.jd_text,
    )

    provider_resolution_source = coalesce_lane_provider_resolution_source(
        explicit=getattr(args, "provider_resolution_source", None),
        resolved_provider=str(args.provider),
    )

    runtime_payload = build_runtime_payload(
        base_json_path=base_path,
        base_hash=base_hash,
        selected_fact_plan=selected_fact_plan,
        target_title=_lane_attr("_args_target_title", _args_target_title)(args),
        target_company=str(getattr(args, "target_company", None) or TARGET_COMPANY_DEFAULT),
        jd_text=targeting_ingress.jd_text,
        briefing=targeting_ingress.briefing_text_bounded,
        allowed_fact_ids_ordered=allowed_fact_ids_ordered,
    )
    runtime_payload["targeting_ingress"] = targeting_ingress.to_dict()
    runtime_payload["briefing_signal_packet"] = targeting_ingress.briefing_signal_packet
    if targeting_ingress.briefing_selection_receipt is not None:
        runtime_payload["briefing_selection"] = targeting_ingress.briefing_selection_receipt
    runtime_payload["proof_pool_metadata"] = proof_pool_metadata
    if pool.proof_source == "augmented_skills_graph":
        runtime_payload["graph_only_claim_authority"] = True
        runtime_payload["base_resume_claim_authority"] = False
    if artifact_dir_override is not None:
        artifact_dir = Path(artifact_dir_override)
        _wg.ensure_dir(artifact_dir)
    else:
        artifact_dir = prepare_runtime_proof_run_dir(REPO_ROOT, LANE_KEY, args.provider, runtime_payload["run_id"])
    from apps_rg.runtime.section_repair_ledger import init_ledger
    from apps_rg.runtime.sections.executive_summary_regen_dispatch import (
        clear_regen_budget_ledger,
    )

    clear_regen_budget_ledger(artifact_dir)
    return {
        "args": args,
        "artifact_dir": artifact_dir,
        "runtime_payload": runtime_payload,
        "proof_pool_metadata": proof_pool_metadata,
        "targeting_ingress": targeting_ingress,
        "briefing_text_bounded": targeting_ingress.briefing_text_bounded,
        "pool": pool,
        "base": base,
        "base_path": base_path,
        "base_hash": base_hash,
        "front_spine": front_spine,
        "selected_fact_plan": selected_fact_plan,
        "allowed_fact_ids": allowed_fact_ids,
        "allowed_fact_ids_ordered": allowed_fact_ids_ordered,
        "provider_resolution_source": provider_resolution_source,
        "apply_proof_pool_to_usage_ledger": apply_proof_pool_to_usage_ledger,
        "_wg": _wg,
    }


def run_ingress_stage(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Full Stage 1 ingress: setup, repair ledger initialization, and provider dispatch."""
    from apps_rg.runtime.section_repair_ledger import init_ledger

    ctx = run_ingress_setup(args, artifact_dir_override=artifact_dir_override)
    init_ledger(
        ctx["artifact_dir"],
        section_id="executive_summary",
        run_id=str(ctx["runtime_payload"]["run_id"]),
    )
    early = run_ingress_dispatch(ctx)
    if early is not None:
        return early
    return ctx
