"""Stage 1: Unify bullets ingress, transport/FEC bind, and prompt compilation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apps_rg.runtime.briefing_resolution import resolve_briefing_for_lanes
from apps_rg.runtime.c0.section_proof_loader import load_section_proof_for_lane
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.jd_resolution import resolve_jd_for_lanes
from apps_rg.runtime.runtime_proof_layout import prepare_runtime_proof_run_dir
from apps_rg.runtime.section_l2_lane_integration import prepare_section_l2_before_provider
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import compute_lane_proof_bundle
from apps_rg.runtime.sections.graph_evidence_contract import merge_graph_evidence_reporting_into_dict
from apps_rg.runtime.sections.section_generation import merge_transport_context
from apps_rg.runtime.sections.unify_bullets_pa import compile_unify_bullets_prompt
from apps_rg.runtime.sections.upstream_evidence_block import wire_spine_c0_fec_or_block
from apps_rg.runtime.spine.c0_fec_compose import merge_compiled_prompt_artifact_fec_fields
from apps_rg.runtime.validators.unify_bullets_x2 import UNIFY_BULLET_IDS
from ._parent import parent_attr
from .lane_constants import (
    BRIEFING_DEFAULT,
    JD_TEXT_DEFAULT,
    LANE_KEY,
    REPO_ROOT,
    TARGET_COMPANY_DEFAULT,
    TARGET_TITLE_DEFAULT,
    UNIFY_MAX_OUTPUT_TOKENS,
    UNIFY_TEMP_DEFAULT,
    build_runtime_payload,
    build_selected_fact_plan,
    extract_unify_employment,
    load_base_resume,
    sha16,
    write_json,
)


def run_unify_ingress_stage(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Load base resume, resolve proof pool, and prepare artifact directory."""
    """Single end-to-end unify_bullets run (external_model): artifacts + X2/X1D/X3/L6."""
    from apps_rg.runtime.sections.resume_employment_bullets import collect_employment_bullets
    from apps_rg.runtime.c0.section_proof_loader import load_section_proof_for_lane

    pool, base, base_path, base_hash, front_spine = load_section_proof_for_lane(
        section_id="unify_bullets",
        args=args,
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        collect_employment_bullets_fn=collect_employment_bullets,
    )
    unify_header, _, _ = parent_attr("extract_unify_employment", extract_unify_employment)(base)
    unify_facts = list(pool.selected_fact_plan.get("facts") or [])
    unify_facts.sort(
        key=lambda r: UNIFY_BULLET_IDS.index(r["fact_id"]) if r["fact_id"] in UNIFY_BULLET_IDS else 99,
    )
    selected_fact_plan = {**pool.selected_fact_plan, "facts": unify_facts}
    allowed_fact_ids = pool.allowed_fact_ids
    proof_pool_metadata = pool.proof_pool_metadata
    runtime_payload = parent_attr("build_runtime_payload", build_runtime_payload)(
        base_json_path=base_path,
        base_hash=base_hash,
        unify_header=unify_header,
        selected_fact_plan=selected_fact_plan,
        allowed_fact_ids=allowed_fact_ids,
        target_title=str(getattr(args, "target_title", "") or "").strip() or TARGET_TITLE_DEFAULT,
        target_company=str(getattr(args, "target_company", "") or "").strip() or TARGET_COMPANY_DEFAULT,
        jd_text=str(getattr(args, "jd_text", "") or "").strip() or JD_TEXT_DEFAULT,
        briefing=str(getattr(args, "briefing", "") or "").strip() or BRIEFING_DEFAULT,
    )
    runtime_payload["proof_pool_metadata"] = proof_pool_metadata
    if focus := str(getattr(args, "diagnostic_focus", "") or "").strip():
        runtime_payload["recovery_diagnostic_focus"] = focus
    if artifact_dir_override is not None:
        artifact_dir = Path(artifact_dir_override)
        _wg.ensure_dir(artifact_dir)
    else:
        artifact_dir = parent_attr("prepare_runtime_proof_run_dir", prepare_runtime_proof_run_dir)(parent_attr("REPO_ROOT", REPO_ROOT), LANE_KEY, args.provider, runtime_payload["run_id"])
    return {
        "base": base,
        "base_path": base_path,
        "base_hash": base_hash,
        "pool": pool,
        "selected_fact_plan": selected_fact_plan,
        "allowed_fact_ids": allowed_fact_ids,
        "unify_header": unify_header,
        "unify_facts": unify_facts,
        "proof_pool_metadata": proof_pool_metadata,
        "runtime_payload": runtime_payload,
        "front_spine": front_spine,
        "artifact_dir": artifact_dir,
    }


def run_unify_prompt_compile_stage(
    args: argparse.Namespace,
    ctx: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Bind transport/FEC evidence, compile Unify prompt, and preflight L2."""
    artifact_dir: Path = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    front_spine = ctx["front_spine"]
    pool = ctx["pool"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    selected_fact_plan = ctx["selected_fact_plan"]

    parent_attr("merge_transport_context", merge_transport_context)(
        artifact_dir=str(artifact_dir.resolve()),
        run_id=str(runtime_payload.get("run_id") or ""),
    )

    blocked = parent_attr("wire_spine_c0_fec_or_block", wire_spine_c0_fec_or_block)(
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        artifact_dir=artifact_dir,
        section_id="unify_bullets",
        front_spine=front_spine,
        pool=pool,
        runtime_payload=runtime_payload,
        provider=str(args.provider),
        temperature=float(args.temperature),
        max_tokens=UNIFY_MAX_OUTPUT_TOKENS,
        output_filename="unify_bullets_output.txt",
    )
    if blocked is not None:
        return ctx, blocked

    input_payload_hash = parent_attr("sha16", sha16)(json.dumps(runtime_payload, sort_keys=True))
    section_compiled = parent_attr("compile_unify_bullets_prompt", compile_unify_bullets_prompt)(runtime_payload, run_id=runtime_payload["run_id"])
    messages = section_compiled.artifact.messages
    compiled_prompt = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    prompt_hash = parent_attr("sha16", sha16)(compiled_prompt)
    parent_attr("write_json", write_json)(artifact_dir / "runtime_payload.json", runtime_payload)
    _wg.write_text(
        artifact_dir / "compiled_prompt.txt",
        json.dumps(messages, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    parent_attr("write_json", write_json)(
        artifact_dir / "compiled_prompt_artifact.json",
        parent_attr("merge_compiled_prompt_artifact_fec_fields", merge_compiled_prompt_artifact_fec_fields)(
            {
                "section_id": section_compiled.section_id,
                "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref,
                "compiler_template_id": section_compiled.artifact.template_id,
                "pa_prompt_hash": section_compiled.artifact.prompt_hash,
                "provider_prompt_hash": prompt_hash,
                "slot_count": section_compiled.artifact.slot_count,
            },
            runtime_payload,
        ),
    )

    provider_request_data: dict[str, Any] | None = None
    provider_result_data: dict[str, Any] | None = None
    raw_output = ""
    parsed: dict[str, Any] | None = None
    parse_error = ""
    runtime_generation_status = "BLOCKED"

    from apps_rg.runtime.spine.exit_lane_hooks import finalize_section_exit_after_l2
    from apps_rg.runtime.section_l2_lane_integration import (
        finalize_section_l2_after_output,
        prepare_section_l2_before_provider,
    )
    from apps_rg.runtime.section_runtime_exhaust_lane_integration import (
        finalize_section_runtime_exhaust_before_l6,
        gate_section_l6_shadow_after_exhaust,
    )

    parent_attr("prepare_section_l2_before_provider", prepare_section_l2_before_provider)(
        artifact_dir,
        "unify_bullets",
        runtime_payload,
        provider_lane=str(args.provider),
    )

    ctx.update(
        {
            "allowed_fact_ids": allowed_fact_ids,
            "selected_fact_plan": selected_fact_plan,
            "runtime_payload": runtime_payload,
            "input_payload_hash": input_payload_hash,
            "section_compiled": section_compiled,
            "messages": messages,
            "compiled_prompt": compiled_prompt,
            "prompt_hash": prompt_hash,
        }
    )
    return ctx, None
