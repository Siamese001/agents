"""Stage 4a: Product quality inference, generation-grade manifest, and X3 finalization."""
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

from .stage_closeout_output import run_closeout_post_x3


def run_closeout_pre_x3(ctx: dict[str, Any]) -> None:
    """Compute product quality, write contract manifest, and finalize section X3."""
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    token_budget_receipt = ctx["token_budget_receipt"]
    usage_doc = ctx["usage_doc"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    runtime_generation_status = ctx["runtime_generation_status"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    x2 = ctx["x2"]
    x1d = ctx["x1d"]
    l2_output = ctx["l2_output"]
    canon_doc = ctx["canon_doc"]
    selected_facts_for_x2 = ctx["selected_facts_for_x2"]
    judge_packet = ctx["judge_packet"]
    _generation_material = ctx["_generation_material"]
    _targeting_parity = ctx["_targeting_parity"]
    _pool_publish_applied = bool(ctx.get("_pool_publish_applied", False))

    _graph_only_repaired = False
    _repair_meta_path = artifact_dir / "graph_only_generation_quality_repair.json"
    if _repair_meta_path.is_file():
        try:
            _graph_only_repaired = bool(
                json.loads(_repair_meta_path.read_text(encoding="utf-8")).get("repaired")
            )
        except (json.JSONDecodeError, OSError):  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
            _graph_only_repaired = False

    product_quality_status, product_quality_reason = _lane_attr("infer_product_quality", infer_product_quality)(
        runtime_generation_status,
        x2,
        resume_display_text,
        claim_ledger,
        graph_only_fact_tight_synthesis=_graph_only_repaired,
        artifact_dir=artifact_dir,
    )
    l2_output["product_quality_status"] = product_quality_status
    l2_output["product_quality_reason"] = product_quality_reason
    from apps_rg.runtime.section_repair_ledger import attach_ledger_summary_to_l2

    attach_ledger_summary_to_l2(l2_output, artifact_dir)
    _lane_attr("write_json", write_json)(artifact_dir / "l2_output.json", l2_output)

    _jp_final = resolve_judge_packet_for_parity(artifact_dir, fallback=judge_packet)
    _targeting_parity, usage_doc = publish_targeting_parity_and_usage_ledger(
        artifact_dir=artifact_dir,
        runtime_payload=runtime_payload,
        generation_material=_generation_material,
        judge_packet=_jp_final,
        usage_doc=usage_doc,
        write_json_fn=_lane_attr("write_json", write_json),
    )
    _tb_receipt: dict[str, Any] | None = (
        token_budget_receipt
        if isinstance(token_budget_receipt, dict)
        else None
    )
    if _tb_receipt is None and (artifact_dir / "token_budget_receipt.json").is_file():
        try:
            _tb_receipt = json.loads(
                (artifact_dir / "token_budget_receipt.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
            _tb_receipt = None
    _comp_plan_manifest: dict[str, Any] = {}
    if (artifact_dir / "executive_summary_composition_plan.json").is_file():
        try:
            _raw_mp = json.loads(
                (artifact_dir / "executive_summary_composition_plan.json").read_text(encoding="utf-8")
            )
            if isinstance(_raw_mp, dict):
                _comp_plan_manifest = _raw_mp
        except (OSError, json.JSONDecodeError):  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
            _comp_plan_manifest = {}
    from apps_rg.runtime.sections.executive_summary_generation_grade_contract import (
        build_generation_grade_contract_manifest,
        write_generation_grade_contract_manifest,
    )
    from apps_rg.runtime.targeting_context_authority import judge_material_context_from_packet

    write_generation_grade_contract_manifest(
        artifact_dir / "generation_grade_contract_manifest.json",
        build_generation_grade_contract_manifest(
            run_id=str(runtime_payload["run_id"]),
            generation=_generation_material,
            judge=judge_material_context_from_packet(_jp_final if isinstance(_jp_final, dict) else {}),
            parity_receipt=_targeting_parity if isinstance(_targeting_parity, dict) else {},
            judge_packet=_jp_final if isinstance(_jp_final, dict) else None,
            token_budget_receipt=_tb_receipt,
            composition_plan=_comp_plan_manifest,
            allowed_fact_packet=selected_facts_for_x2,
        ),
    )

    from apps_rg.runtime.sections.executive_summary_regen_dispatch import (
        regen_budget_ledger,
    )

    regen_budget_ledger(artifact_dir).flush()

    from apps_rg.runtime.sections.executive_summary_publish_disposition import (
        apply_publish_disposition_to_proof_bundle,
        apply_publish_disposition_to_x3_dict,
        best_effort_publish_allowed_from_env,
        resolve_publish_disposition,
    )

    _best_effort_publish = bool(getattr(args, "best_effort_publish_allowed", False)) or (
        best_effort_publish_allowed_from_env()
    )
    _pub_disp = resolve_publish_disposition(
        x1d,
        best_effort_publish_allowed=_best_effort_publish,
        published_from_pool=bool(_pool_publish_applied),
    )
    _lane_attr("write_json", write_json)(artifact_dir / "publish_disposition.json", _pub_disp)

    from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3

    x3 = finalize_section_lane_x3(
        artifact_dir=artifact_dir,
        section_id="executive_summary",
        runtime_payload=runtime_payload,
        defer_graph_binding_l2_persistence=True,
        aggregate_x3_fn=_aggregate_executive_summary_x3,
        resume_display_text=resume_display_text,
        claim_ledger=claim_ledger,
        x2_gates=x2,
        x1d_judges=x1d,
        runtime_generation_status=runtime_generation_status,
        product_quality_status=product_quality_status,
        canonical_claims_for_hash=canon_doc.get("claims"),
        section_input_usage_ledger=usage_doc,
    )
    from apps_rg.runtime.spine.section_x3_finalize import persist_section_x3_mirror

    x3_doc = apply_publish_disposition_to_x3_dict(
        x3.to_dict() if hasattr(x3, "to_dict") else dict(x3),
        _pub_disp,
    )
    x3_doc = persist_section_x3_mirror(artifact_dir, x3_doc)
    x3 = x3_doc
    ctx.update({
        "product_quality_status": product_quality_status,
        "product_quality_reason": product_quality_reason,
        "_targeting_parity": _targeting_parity,
        "usage_doc": usage_doc,
        "_pub_disp": _pub_disp,
        "x3": x3,
        "l2_output": l2_output,
    })


def emit_final_fact_check_result(ctx: dict[str, Any]) -> None:
    """Write terminal fact_check_result.json from X2/X3/product quality state."""
    x3 = ctx["x3"]
    x2 = ctx["x2"]
    _lane_attr("write_json", write_json)(
        ctx["artifact_dir"] / "fact_check_result.json",
        {
            "passed": not [g for g in x2 if not g["pass"]],
            "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]],
            "x3_code": x3.get("x3_code") if isinstance(x3, dict) else None,
            "product_quality_status": ctx["product_quality_status"],
        },
    )


def run_closeout_stage(ctx: dict[str, Any]) -> dict[str, Any]:
    """Full Stage 4 closeout (for callers invoking stage_closeout directly)."""
    run_closeout_pre_x3(ctx)
    emit_final_fact_check_result(ctx)
    return run_closeout_post_x3(ctx)
