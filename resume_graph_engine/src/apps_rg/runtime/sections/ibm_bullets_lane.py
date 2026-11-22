"""IBM bullets section lane — canonical implementation for ``python -m apps_rg --section ibm_bullets``.

Wires PA → provider → X1D → X2 → X3 → L6 shadow handoff under ``artifacts/apps_rg/runtime_proofs/ibm_bullets``.

``apps_rg.runtime.sections.ibm_bullets_lane`` is **import-only** (legacy module path for helpers).
Legacy dispatch module paths are not CLI entrypoints; use ``python -m apps_rg --section ibm_bullets``.

**W3:** ``declared_temporary_slice`` — section runtime proof seam.
"""
from __future__ import annotations

if __name__ == "__main__":
    raise ImportError(
        "This module is not an operator CLI entrypoint. "
        "Use the sole canonical public command: python -m resume_engine run"
    )

from apps_rg.runtime.w3_execution_path_labels import (
    BUCKET_DECLARED_TEMPORARY_SLICE,
    PLAN_SLUG,
    validate_bucket,
)

W3_EXECUTION_PATH_BUCKET = BUCKET_DECLARED_TEMPORARY_SLICE
W3_EXECUTION_PATH_PLAN_SLUG = PLAN_SLUG
validate_bucket(W3_EXECUTION_PATH_BUCKET, context=__name__)

import argparse
from pathlib import Path
from typing import Any

from apps_rg.runtime.briefing_resolution import resolve_briefing_for_lanes
from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    classify_ledger_parse_state,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.exit.ibm_bullets_x3 import aggregate_x3 as _aggregate_ibm_bullets_x3
from apps_rg.runtime.jd_resolution import resolve_jd_for_lanes
from apps_rg.runtime.judges.ibm_bullets_x1d import run_ibm_bullets_judges
from apps_rg.runtime.reasoning.bullet_fact_entailment import build_slot_entailment_corpus
from apps_rg.runtime.reasoning.bullet_lane_generation import generate_bullet_lane_with_sc_and_claude
from apps_rg.runtime.reasoning.bullet_pool_reselection import (
    run_bullet_judge_llm_rewrite,
    run_bullet_judge_reselection,
)
from apps_rg.runtime.resume_resolution import load_lane_base_resume_json
from apps_rg.runtime.runtime_proof_layout import finalize_runtime_proof_run, prepare_runtime_proof_run_dir
from apps_rg.runtime.section_l2_lane_integration import finalize_section_l2_after_output
from apps_rg.runtime.section_proof.lane_proof_accounting import resolve_lane_placement_bucket
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import (
    attach_lane_proof_bundle_fields,
    compute_lane_proof_bundle,
    infer_product_quality_blocked_or_mock,
)
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.section_repair_lane_integration import start_lane_repair_ledger
from apps_rg.runtime.section_runtime_exhaust_lane_integration import (
    finalize_section_runtime_exhaust_before_l6,
    gate_section_l6_shadow_after_exhaust,
)
from apps_rg.runtime.sections.executive_summary_lane import (
    resolve_provider_model_name,
    write_x2_gate_outputs,
)
from apps_rg.runtime.sections.graph_evidence_contract import merge_graph_evidence_reporting_into_dict
from apps_rg.runtime.sections.ibm_bullets import (
    BRIEFING_DEFAULT,
    BULLET_ID_ALIASES,
    DEFAULT_INTENSITY_BY_BULLET,
    IBM_DEFAULT_DISTRIBUTION,
    IBM_LOCKED_METRIC_CANONICAL,
    IBM_MAX_OUTPUT_TOKENS,
    IBM_TEMP_DEFAULT,
    IBM_TEMP_RANGE,
    JD_TEXT_DEFAULT,
    LANE_KEY,
    PROMPT_ID,
    REPO_ROOT,
    TARGET_COMPANY_DEFAULT,
    TARGET_TITLE_DEFAULT,
    _HOLD_METRIC_TEXT_RE,
    _IBM_FROZEN_ALLOCATION_DISPLAY_COMPOSITIONS,
    _IBM_FOREIGN_METRIC_SCRUB_RE,
    _bind_ibm_change_log_to_frozen_allocation,
    _canonicalize_bul_ibm_source_fact_id,
    _clamp_to_ibm_fact_scope,
    _count_intensities,
    _find_repo_root,
    _materialize_ibm_bullets_from_frozen_allocation,
    _normalize_fact_id_list,
    _normalize_ibm_claim_ledger,
    _plan_metric_display_token,
    _scrub_foreign_ibm_metric_tokens,
    align_ibm_claim_ledger_from_canonical_facts,
    build_ibm_bullets_allowed_fact_packet,
    build_ibm_reselection_callbacks,
    build_mock_output,
    build_prompt_messages,
    build_runtime_payload,
    build_selected_fact_plan,
    bullets_display_text,
    demote_gated_ibm_metrics,
    demote_hold_metrics,
    extract_ibm_employment,
    infer_product_quality,
    inject_ibm_locked_metric_anchors,
    load_base_resume,
    normalize_parsed_output,
    parse_model_json,
    repair_ibm_bullet_metric_anchors_from_plan,
    retry_provider_for_parse,
    run_ibm_closeout_stage,
    run_ibm_generation_and_x2_stage,
    run_ibm_ingress_stage,
    run_ibm_prompt_compile_stage,
    scrub_cross_slot_plan_metrics,
    sha16,
    write_json,
)
from apps_rg.runtime.sections.ibm_bullets_pa import compile_ibm_bullets_prompt
from apps_rg.runtime.sections.ibm_canonical_hydration import should_hydrate_ibm_bullets_from_canonical
from apps_rg.runtime.sections.section_generation import (
    build_section_request,
    generate_section,
    tag_reasoning_lane,
)
from apps_rg.runtime.shadow.ibm_bullets_l6 import (
    build_l6_shadow_package,
    extend_ibm_bullets_l6_learning_fields,
)
from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3
from apps_rg.runtime.validators.ibm_bullets_x2 import (
    IBM_BULLET_IDS,
    build_ibm_bullets_text_claim_coverage,
    run_ibm_bullets_x2_gates,
)


def run_ibm_bullets_execution(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Execute IBM bullets lane through ingress, generation, adjudication, reselection, and closeout."""
    ctx = run_ibm_ingress_stage(args, artifact_dir_override=artifact_dir_override)
    artifact_dir: Path = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    start_lane_repair_ledger(
        artifact_dir, section_id="ibm_bullets", run_id=str(runtime_payload["run_id"])
    )
    ctx, early_return = run_ibm_prompt_compile_stage(args, ctx)
    if early_return is not None:
        return early_return
    input_payload_hash = ctx["input_payload_hash"]
    section_compiled = ctx["section_compiled"]
    messages = ctx["messages"]
    prompt_hash = ctx["prompt_hash"]
    from apps_rg.runtime.section_model_limits import (
        external_openai_generation_model,
        resolve_section_generation_model,
    )

    section_model = (
        external_openai_generation_model(section_id=LANE_KEY)
        if str(args.provider) == "external_openai"
        else resolve_section_generation_model(
            LANE_KEY, provider_profile=str(args.provider)
        )
    )
    provider_req, provider_payload = build_section_request(
        messages=messages,
        prompt_hash=prompt_hash,
        input_payload_hash=input_payload_hash,
        temperature=args.temperature,
        max_tokens=IBM_MAX_OUTPUT_TOKENS,
        temperature_bounds=IBM_TEMP_RANGE,
        model=section_model,
        provider_requested=str(args.provider),
        compiled_prompt_artifact=section_compiled.artifact,
        anthropic_workload_kind="SELF_CONSISTENCY",
        reasoning_effort=getattr(args, "reasoning_effort", None) or "low",
        force_new_seed=bool(getattr(args, "force_new_seed", False)),
    )
    provider_request_data = provider_req.to_dict()
    write_json(artifact_dir / "provider_request.json", provider_request_data)
    tagged = tag_reasoning_lane(provider_payload, LANE_KEY)
    ctx["section_model"] = section_model
    ctx["provider_req"] = provider_req
    ctx["provider_payload"] = provider_payload
    ctx["provider_request_data"] = provider_request_data
    ctx["tagged"] = tagged
    ctx = run_ibm_generation_and_x2_stage(args, ctx)
    x2 = ctx["x2"]
    x1d = ctx["x1d"]
    gen_meta = ctx["gen_meta"]
    bullets = ctx["bullets"]
    claim_ledger = ctx["claim_ledger"]
    judge_mode = ctx["judge_mode"]
    allowed_fact_packet = ctx["allowed_fact_packet"]
    _frozen_ibm_materialized = ctx["_frozen_ibm_materialized"]
    active_bullet_ids = ctx["active_bullet_ids"]
    parsed = ctx["parsed"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    usage_doc = ctx["usage_doc"]
    canon_doc = ctx["canon_doc"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    runtime_generation_status = ctx["runtime_generation_status"]
    l2_output = ctx["l2_output"]
    from apps_rg.runtime.judges.bullet_adjudicator import ADJUDICATOR_PANEL_PROVIDER_KEYS, evaluate_bullet_adjudicator_trigger
    from apps_rg.runtime.judges.bullet_x2_aggregation import aggregate_bullet_section

    _x2_failed_ids = [g["gate_id"] for g in x2 if not g.get("pass", True)]
    _existing_judge_keys = {str(j.get("provider_key") or "") for j in x1d}
    _sel_map = (gen_meta.get("pool_selection") or {}).get("selections") if isinstance(gen_meta, dict) and isinstance(gen_meta.get("pool_selection"), dict) else None
    _adj_decision = evaluate_bullet_adjudicator_trigger(
        section_id="ibm_bullets", composite_judges=x1d, x2_failed_gate_ids=_x2_failed_ids, bullets=bullets, selector_selections=_sel_map,
    )
    _agg = aggregate_bullet_section(
        section_id="ibm_bullets", composite_judges=x1d, x2_failed_gate_ids=_x2_failed_ids,
    )
    _should_adjudicate = (not _x2_failed_ids) and (_adj_decision.should_escalate or _agg.should_adjudicate)
    _panel_keys = [k for k in ADJUDICATOR_PANEL_PROVIDER_KEYS if k and k not in _existing_judge_keys]
    _adjudication_record: dict[str, Any] = {
        "section_id": "ibm_bullets", "trigger_decision": _adj_decision.to_dict(),
        "aggregation": _agg.to_dict(), "escalated": False, "panel_provider_keys": [],
    }
    if _should_adjudicate and _panel_keys:
        _panel_rows = [
            j.to_dict()
            for j in run_ibm_bullets_judges(
                bullets=bullets,
                claim_ledger=claim_ledger,
                judge_keys=_panel_keys,
                mode=judge_mode,
                artifact_base=artifact_dir,
                allowed_fact_packet=allowed_fact_packet,
                targeting_context={
                    "target_title": str(runtime_payload.get("target_title") or ""),
                    "target_company": str(runtime_payload.get("target_company") or ""),
                    "jd_text": str(runtime_payload.get("jd_text") or ""),
                    "briefing": str(runtime_payload.get("briefing") or ""),
                },
            )
        ]
        for _r in _panel_rows:
            _r["adjudicator_panel_row"] = True
        x1d = list(x1d) + _panel_rows
        _adjudication_record["escalated"] = True
        _adjudication_record["panel_provider_keys"] = list(_panel_keys)
        # Re-aggregate after the panel.  The final-prose quality verdict is
        # conservative: a lower/failing panel score cannot be hidden by the
        # initial composite judge's higher score.
        _agg = aggregate_bullet_section(
            section_id="ibm_bullets",
            composite_judges=x1d,
            x2_failed_gate_ids=_x2_failed_ids,
        )
        _adjudication_record["aggregation"] = _agg.to_dict()
    write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": x1d})
    write_json(artifact_dir / "bullet_adjudication.json", _adjudication_record)
    write_json(artifact_dir / "bullet_x2_aggregation.json", _agg.to_dict())
    callbacks = build_ibm_reselection_callbacks(args, ctx)
    _resel_post_chain = callbacks["post_chain"]
    _resel_rebuild_state = callbacks["rebuild_state"]
    _resel_run_x2 = callbacks["run_x2"]
    _resel_run_judges = callbacks["run_judges"]
    _resel_write_usage = callbacks["write_usage_ledger"]
    _resel_write_artifacts = callbacks["write_lane_artifacts"]
    if not _frozen_ibm_materialized:
        _resel = run_bullet_judge_reselection(
            artifact_dir=artifact_dir,
            section_id="ibm_bullets",
            run_id=str(runtime_payload["run_id"]),
            required_bullet_ids=active_bullet_ids,
            parsed=parsed,
            bullets=bullets,
            claim_ledger=claim_ledger,
            parsed_for_x2=parsed_for_x2,
            x1d=x1d,
            x2=x2,
            usage_doc=usage_doc,
            canon_doc=canon_doc,
            allowed_fact_ids=allowed_fact_ids,
            judge_mode=judge_mode,
            entailment_corpus=build_slot_entailment_corpus(
                "ibm_bullets", runtime_payload.get("selected_fact_plan") or {}
            ),
            post_chain=_resel_post_chain,
            rebuild_state=_resel_rebuild_state,
            run_x2=_resel_run_x2,
            run_judges=_resel_run_judges,
            write_usage_ledger=_resel_write_usage,
            write_lane_artifacts=_resel_write_artifacts,
        )
        parsed = _resel.parsed
        bullets = _resel.bullets
        claim_ledger = _resel.claim_ledger
        parsed_for_x2 = _resel.parsed_for_x2
        x2 = _resel.x2
        x1d = _resel.x1d
        usage_doc = _resel.usage_doc
        canon_doc = _resel.canon_doc
    _llm_rw, _new_raw = run_bullet_judge_llm_rewrite(
        artifact_dir=artifact_dir,
        section_id="ibm_bullets",
        run_id=str(runtime_payload["run_id"]),
        provider_name=str(args.provider),
        provider_payload=provider_payload,
        base_messages=list(ctx.get("messages") or []),
        prior_raw_output=str(ctx.get("raw_output") or ""),
        required_bullet_ids=tuple(active_bullet_ids),
        parsed=parsed,
        bullets=bullets,
        claim_ledger=claim_ledger,
        parsed_for_x2=parsed_for_x2,
        x1d=x1d,
        x2=x2,
        usage_doc=usage_doc,
        canon_doc=canon_doc,
        runtime_generation_status=runtime_generation_status,
        judge_mode=judge_mode,
        parse_json_fn=parse_model_json,
        post_chain=_resel_post_chain,
        rebuild_state=_resel_rebuild_state,
        run_x2=_resel_run_x2,
        run_judges=_resel_run_judges,
        write_usage_ledger=_resel_write_usage,
        write_lane_artifacts=_resel_write_artifacts,
    )
    if _llm_rw.fired:
        parsed = _llm_rw.parsed
        bullets = _llm_rw.bullets
        claim_ledger = _llm_rw.claim_ledger
        parsed_for_x2 = _llm_rw.parsed_for_x2
        x2 = _llm_rw.x2
        x1d = _llm_rw.x1d
        usage_doc = _llm_rw.usage_doc
        canon_doc = _llm_rw.canon_doc
        ctx["raw_output"] = _new_raw
    from apps_rg.runtime.section_repair_lane_integration import finalize_lane_product_quality

    product_quality_status, product_quality_reason = finalize_lane_product_quality(
        artifact_dir,
        runtime_generation_status=runtime_generation_status,
        x2_gates=x2,
        pass_reason="REAL_LLM output passed all deterministic IBM bullet gates.",
        l2_output=l2_output,
    )
    ctx.update(
        {
            "parsed": parsed,
            "bullets": bullets,
            "claim_ledger": claim_ledger,
            "parsed_for_x2": parsed_for_x2,
            "x2": x2,
            "x1d": x1d,
            "usage_doc": usage_doc,
            "canon_doc": canon_doc,
            "product_quality_status": product_quality_status,
            "product_quality_reason": product_quality_reason,
        }
    )
    return run_ibm_closeout_stage(args, ctx)


__all__ = [
    "BRIEFING_DEFAULT",
    "BULLET_ID_ALIASES",
    "DEFAULT_INTENSITY_BY_BULLET",
    "IBM_BULLET_IDS",
    "IBM_DEFAULT_DISTRIBUTION",
    "IBM_MAX_OUTPUT_TOKENS",
    "IBM_TEMP_DEFAULT",
    "IBM_TEMP_RANGE",
    "JD_TEXT_DEFAULT",
    "LANE_KEY",
    "PROMPT_ID",
    "REPO_ROOT",
    "TARGET_COMPANY_DEFAULT",
    "TARGET_TITLE_DEFAULT",
    "_canonicalize_bul_ibm_source_fact_id",
    "build_mock_output",
    "build_prompt_messages",
    "build_runtime_payload",
    "build_selected_fact_plan",
    "bullets_display_text",
    "extract_ibm_employment",
    "infer_product_quality",
    "load_base_resume",
    "normalize_parsed_output",
    "parse_model_json",
    "retry_provider_for_parse",
    "run_ibm_bullets_execution",
    "sha16",
    "write_json",
]
