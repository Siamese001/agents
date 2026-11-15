"""Stage 1: IBM bullets ingress, repair-ledger start readiness, and prompt compilation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apps_rg.runtime.briefing_resolution import resolve_briefing_for_lanes
from apps_rg.runtime.c0.section_proof_loader import (
    apply_proof_pool_to_usage_ledger,
    load_section_proof_for_lane,
)
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.jd_resolution import resolve_jd_for_lanes
from apps_rg.runtime.runtime_proof_layout import prepare_runtime_proof_run_dir
from apps_rg.runtime.section_l2_lane_integration import prepare_section_l2_before_provider
from apps_rg.runtime.section_proof.lane_proof_accounting import resolve_lane_placement_bucket
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import compute_lane_proof_bundle
from apps_rg.runtime.sections.graph_evidence_contract import merge_graph_evidence_reporting_into_dict
from apps_rg.runtime.sections.ibm_bullets_pa import compile_ibm_bullets_prompt
from apps_rg.runtime.sections.section_generation import merge_transport_context
from apps_rg.runtime.sections.upstream_evidence_block import wire_spine_c0_fec_or_block
from apps_rg.runtime.spine.c0_fec_compose import merge_compiled_prompt_artifact_fec_fields
from apps_rg.runtime.validators.ibm_bullets_x2 import IBM_BULLET_IDS
from ._parent import parent_attr
from .lane_constants import (
    IBM_MAX_OUTPUT_TOKENS,
    IBM_TEMP_DEFAULT,
    LANE_KEY,
    REPO_ROOT,
    TARGET_COMPANY_DEFAULT,
    build_prompt_messages,
    build_runtime_payload,
    build_selected_fact_plan,
    extract_ibm_employment,
    load_base_resume,
    sha16,
    write_json,
)
from .metric_repairs import _HOLD_METRIC_TEXT_RE


def run_ibm_ingress_stage(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Load base resume, resolve proof pool, and prepare artifact directory."""
    """Single end-to-end ibm_bullets run (external_model): artifacts + X2/X1D/X3/L6."""
    from apps_rg.runtime.sections.resume_employment_bullets import collect_employment_bullets
    from apps_rg.runtime.c0.section_proof_loader import load_section_proof_for_lane

    pool, base, base_path, base_hash, front_spine = load_section_proof_for_lane(
        section_id="ibm_bullets",
        args=args,
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        collect_employment_bullets_fn=collect_employment_bullets,
    )
    canon_header, canon_facts, canon_allowed = parent_attr("extract_ibm_employment", extract_ibm_employment)(base)
    ibm_header = canon_header
    ibm_facts = list(pool.selected_fact_plan.get("facts") or [])
    ibm_facts.sort(
        key=lambda r: IBM_BULLET_IDS.index(r["fact_id"]) if r["fact_id"] in IBM_BULLET_IDS else 99,
    )
    # Plan-level HOLD demotion (W5, apps-rg-aig-remaining-lanes-closeout-d4e1f7): the ledger can
    # assign a slot a HOLD/DO_NOT_PROMOTE figure as its plan metric (e.g. bul_ibm_002 ->
    # "30% cost optimization"), which made the prompt's METRIC SURFACING and the anchor gate
    # demand the very token x2_ibm_hold_metric_forbidden_in_output bans — unsatisfiable by
    # construction. Demote the fact to qualitative at the plan seam so prompt, anchor gate, and
    # HOLD gate agree; the fact's qualitative claim_text is unchanged.
    for _f in ibm_facts:
        if isinstance(_f, dict) and _HOLD_METRIC_TEXT_RE.search(str(_f.get("metric_raw") or "")):
            _f["metric_raw"] = ""
            _f["has_metric"] = False
            _f["metric_demoted_hold"] = True
    selected_fact_plan = {**pool.selected_fact_plan, "facts": ibm_facts}
    allowed_fact_ids = pool.allowed_fact_ids
    proof_pool_metadata = pool.proof_pool_metadata
    runtime_payload = parent_attr("build_runtime_payload", build_runtime_payload)(
        base_json_path=base_path,
        base_hash=base_hash,
        ibm_header=ibm_header,
        selected_fact_plan=selected_fact_plan,
        allowed_fact_ids=allowed_fact_ids,
        target_title=args.target_title,
        target_company=args.target_company,
        jd_text=args.jd_text,
        briefing=args.briefing,
    )
    runtime_payload["proof_pool_metadata"] = proof_pool_metadata
    runtime_payload["max_tokens"] = IBM_MAX_OUTPUT_TOKENS
    placement_bucket = parent_attr("resolve_lane_placement_bucket", resolve_lane_placement_bucket)(
        args.provider,
        mock_judges=bool(getattr(args, "mock_judges", False)),
        offline_stub_env=False,
    )
    if artifact_dir_override is not None:
        artifact_dir = Path(artifact_dir_override)
        _wg.ensure_dir(artifact_dir)
    else:
        artifact_dir = parent_attr("prepare_runtime_proof_run_dir", prepare_runtime_proof_run_dir)(
            parent_attr("REPO_ROOT", REPO_ROOT),
            LANE_KEY,
            args.provider,
            runtime_payload["run_id"],
            placement_bucket=placement_bucket,
        )
    return {
        "base": base,
        "base_path": base_path,
        "base_hash": base_hash,
        "canon_header": canon_header,
        "canon_facts": canon_facts,
        "canon_allowed": canon_allowed,
        "pool": pool,
        "selected_fact_plan": selected_fact_plan,
        "allowed_fact_ids": allowed_fact_ids,
        "ibm_header": ibm_header,
        "ibm_facts": ibm_facts,
        "proof_pool_metadata": proof_pool_metadata,
        "runtime_payload": runtime_payload,
        "front_spine": front_spine,
        "placement_bucket": placement_bucket,
        "artifact_dir": artifact_dir,
    }


def run_ibm_prompt_compile_stage(
    args: argparse.Namespace,
    ctx: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Bind transport/FEC evidence, compile IBM bullets prompt, and preflight L2."""
    artifact_dir: Path = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    front_spine = ctx["front_spine"]
    pool = ctx["pool"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    selected_fact_plan = ctx["selected_fact_plan"]
    ibm_facts = ctx["ibm_facts"]

    merge_transport_context(
        artifact_dir=str(artifact_dir.resolve()),
        run_id=str(runtime_payload.get("run_id") or ""),
    )

    blocked = wire_spine_c0_fec_or_block(
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        artifact_dir=artifact_dir,
        section_id="ibm_bullets",
        front_spine=front_spine,
        pool=pool,
        runtime_payload=runtime_payload,
        provider=str(args.provider),
        temperature=float(args.temperature),
        max_tokens=IBM_MAX_OUTPUT_TOKENS,
        output_filename="ibm_bullets_output.txt",
    )
    if blocked is not None:
        return ctx, blocked
    allowed_fact_ids = {str(x) for x in (runtime_payload.get("allowed_fact_ids") or allowed_fact_ids)}
    selected_fact_plan = dict(runtime_payload.get("selected_fact_plan") or selected_fact_plan)
    ibm_facts = list(selected_fact_plan.get("facts") or [])
    ibm_facts.sort(
        key=lambda r: IBM_BULLET_IDS.index(r["fact_id"]) if r.get("fact_id") in IBM_BULLET_IDS else 99,
    )
    for _f in ibm_facts:
        if isinstance(_f, dict) and _HOLD_METRIC_TEXT_RE.search(str(_f.get("metric_raw") or "")):
            _f["metric_raw"] = ""
            _f["has_metric"] = False
            _f["metric_demoted_hold"] = True
    selected_fact_plan = {**selected_fact_plan, "facts": ibm_facts}
    runtime_payload["selected_fact_plan"] = selected_fact_plan
    input_payload_hash = parent_attr("sha16", sha16)(json.dumps(runtime_payload, sort_keys=True))
    section_compiled = parent_attr("compile_ibm_bullets_prompt", compile_ibm_bullets_prompt)(runtime_payload, run_id=runtime_payload["run_id"])
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
        merge_compiled_prompt_artifact_fec_fields(
            {
                "section_id": section_compiled.section_id,
                "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref,
                "compiler_template_id": section_compiled.artifact.template_id,
                "pa_prompt_hash": section_compiled.artifact.prompt_hash,
                "dispatch_sha256_prompt16": prompt_hash,
                "slot_count": section_compiled.artifact.slot_count,
                "allowed_fact_ids": list(runtime_payload.get("allowed_fact_ids") or []),
            },
            runtime_payload,
        ),
    )

    provider_request_data = None
    provider_result_data = None
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

    prepare_section_l2_before_provider(
        artifact_dir,
        "ibm_bullets",
        runtime_payload,
        provider_lane=str(args.provider),
    )

    ctx.update(
        {
            "allowed_fact_ids": allowed_fact_ids,
            "selected_fact_plan": selected_fact_plan,
            "ibm_facts": ibm_facts,
            "runtime_payload": runtime_payload,
            "input_payload_hash": input_payload_hash,
            "section_compiled": section_compiled,
            "messages": messages,
            "compiled_prompt": compiled_prompt,
            "prompt_hash": prompt_hash,
        }
    )
    return ctx, None
