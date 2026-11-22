"""Stage 2: IBM bullets model invocation, repairs, usage ledger, X2, and composite judge."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    classify_ledger_parse_state,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.judges.ibm_bullets_x1d import run_ibm_bullets_judges
from apps_rg.runtime.product_evidence_authority import x2_proof_pool_gate_flags
from apps_rg.runtime.reasoning.bullet_lane_generation import (
    generate_bullet_lane_with_sc_and_claude,
    should_short_circuit_empty_selection,
    truthful_block_reason,
)
from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
    strip_employment_bullet_intensity_model,
)
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    build_employment_targeting_context,
    employment_pool_x1d_judge_rows,
    is_employment_pool_generation,
)
from apps_rg.runtime.runtime_proof_layout import rel_posix
from apps_rg.runtime.section_proof.lane_proof_accounting import generation_status_allows_json_parse
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.section_repair_lane_integration import record_mechanical, record_parse_json_retry
from apps_rg.runtime.sections.executive_summary_lane import resolve_provider_model_name, write_x2_gate_outputs
from apps_rg.runtime.sections.section_generation import generate_section, tag_reasoning_lane
from apps_rg.runtime.validators.ibm_bullets_x2 import (
    IBM_BULLET_IDS,
    build_ibm_bullets_text_claim_coverage,
    run_ibm_bullets_x2_gates,
)
from apps_rg.runtime.validators.proof_pool_source_fact_validation import (
    write_x2_source_fact_pool_receipt,
)
from ._parent import parent_attr
from .frozen_allocation import (
    _bind_ibm_change_log_to_frozen_allocation,
    _materialize_ibm_bullets_from_frozen_allocation,
    normalize_parsed_output,
    reconcile_ibm_frozen_materialized_selection_gate,
)
from .lane_constants import (
    IBM_MAX_OUTPUT_TOKENS,
    IBM_TEMP_DEFAULT,
    IBM_TEMP_RANGE,
    LANE_KEY,
    PROMPT_ID,
    REPO_ROOT,
    should_hydrate_ibm_bullets_from_canonical,
    write_json,
)
from .metric_repairs import (
    align_ibm_claim_ledger_from_canonical_facts,
    build_ibm_bullets_allowed_fact_packet,
    demote_gated_ibm_metrics,
    demote_hold_metrics,
    inject_ibm_locked_metric_anchors,
    repair_ibm_bullet_metric_anchors_from_plan,
    scrub_cross_slot_plan_metrics,
)
from .provider_io import (
    bullets_display_text,
    build_mock_output,
    parse_model_json,
    retry_provider_for_parse,
)


def run_ibm_generation_and_x2_stage(
    args: argparse.Namespace,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Execute IBM generation, mechanical repairs, canonical ledger, X2 gates, and X1D judge."""
    artifact_dir: Path = ctx["artifact_dir"]
    base = ctx["base"]
    pool = ctx["pool"]
    ibm_header = ctx["ibm_header"]
    ibm_facts = ctx["ibm_facts"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    selected_fact_plan = ctx["selected_fact_plan"]
    runtime_payload = ctx["runtime_payload"]
    input_payload_hash = ctx["input_payload_hash"]
    section_compiled = ctx["section_compiled"]
    messages = ctx["messages"]
    prompt_hash = ctx["prompt_hash"]
    section_model = ctx["section_model"]
    provider_payload = ctx["provider_payload"]
    provider_request_data = ctx["provider_request_data"]
    tagged = ctx["tagged"]
    req_model = str(tagged.get("model", section_model))
    judge_mode = "mocked" if getattr(args, "mock_judges", False) else "blocked_if_unavailable"
    plan_obj = runtime_payload.get("selected_fact_plan") or {}
    if isinstance(plan_obj, dict) and "facts" in plan_obj:
        plan_facts = [
            str(f.get("fact_id", "")).strip()
            for f in (plan_obj.get("facts") or [])
            if isinstance(f, dict) and str(f.get("fact_id", "")).strip().startswith("bul_ibm_")
        ]
    elif isinstance(plan_obj, dict):
        plan_facts = [
            str(k).strip()
            for k in plan_obj.keys()
            if str(k).strip().startswith("bul_ibm_")
        ]
    else:
        plan_facts = []
    active_bullet_ids = tuple(plan_facts) if plan_facts else IBM_BULLET_IDS

    _ibm_has_frozen_allocation = any(
        isinstance(row, dict) and str(row.get("section_id") or "") == "ibm_bullets"
        for row in (selected_fact_plan.get("allocation_assignments") or [])
    )
    _ibm_targeting_ctx = build_employment_targeting_context(runtime_payload, section_lane=LANE_KEY)
    if _ibm_has_frozen_allocation:
        _ibm_targeting_ctx["frozen_allocation_materialized"] = True
    _frozen_ibm_materialized = False

    result, raw_output, parsed, parse_error, gen_meta = parent_attr("generate_bullet_lane_with_sc_and_claude", generate_bullet_lane_with_sc_and_claude)(
        section_lane=LANE_KEY,
        slot_kind="bullets",
        provider_payload=tagged,
        parse_model_json=parse_model_json,
        normalize_parsed=lambda p: parent_attr("normalize_parsed_output", normalize_parsed_output)(p, runtime_payload),
        artifact_dir=artifact_dir,
        run_id=str(runtime_payload.get("run_id") or ""),
        temperature_bounds=IBM_TEMP_RANGE,
        base_temperature=float(args.temperature) if args.provider == "external_claude" else IBM_TEMP_DEFAULT,
        required_bullet_ids=active_bullet_ids,
        targeting_context=_ibm_targeting_ctx,
        judge_mode=judge_mode,
        provider_profile=str(args.provider),
    )
    parent_attr("write_json", write_json)(artifact_dir / "bullet_lane_generation.json", gen_meta)
    provider_result_data = result.to_dict() if result else {}
    runtime_generation_status = result.runtime_generation_status if result else "BLOCKED"
    parent_attr("write_json", write_json)(artifact_dir / "provider_response.json", provider_result_data)
    if generation_status_allows_json_parse(runtime_generation_status):
        if parsed is None:
            if str(args.provider) == "external_claude":
                raw_output, parsed, parse_error = parent_attr("retry_provider_for_parse", retry_provider_for_parse)(
                    messages, tagged, raw_output, parse_error
                )
                if parsed is not None:
                    record_parse_json_retry(artifact_dir, reason=parse_error or "parse_retry")
                    parsed = parent_attr("normalize_parsed_output", normalize_parsed_output)(parsed, runtime_payload)
        if parsed is not None:
            from apps_rg.runtime.c0.graph_story_authority import forbid_base_resume_bullet_hydration

            forbid_base_resume_bullet_hydration(
                section_id="ibm_bullets",
                runtime_payload=runtime_payload,
                parsed=parsed,
                base_resume=base,
                would_hydrate_fn=should_hydrate_ibm_bullets_from_canonical,
            )
            if runtime_generation_status != "REAL_LLM":
                # Deterministic metric anchoring: when a bullet's graph-selected plan fact carries
                # an approved metric the model dropped, surface that fact-backed token so
                # x2_ibm_metric_anchor_bullet_ownership is satisfied without fabricating figures.
                parent_attr("inject_ibm_locked_metric_anchors", inject_ibm_locked_metric_anchors)(
                    parsed,
                    plan_facts=ibm_facts,
                    allowed_fact_ids=allowed_fact_ids,
                )
            # Demote gated/unconfirmed metrics to qualitative so
            # x2_ibm_metric_outcome_id_required_when_has_metric does not block on an
            # unpromotable figure.
            parent_attr("demote_gated_ibm_metrics", demote_gated_ibm_metrics)(parsed)
            if runtime_generation_status != "REAL_LLM":
                # W5 backstop: strip HOLD/DO_NOT_PROMOTE figures (25/30/35/40%, $15M, $30M)
                # any path still surfaced despite the PA ban.
                parent_attr("demote_hold_metrics", demote_hold_metrics)(parsed)
                # W4-residual: a bullet must not claim ANOTHER slot's plan metric; scrub deterministically.
                parent_attr("scrub_cross_slot_plan_metrics", scrub_cross_slot_plan_metrics)(parsed, ibm_facts)
            parent_attr("align_ibm_claim_ledger_from_canonical_facts", align_ibm_claim_ledger_from_canonical_facts)(
                parsed,
                plan_facts=ibm_facts,
                allowed_fact_ids=allowed_fact_ids,
            )
            if runtime_generation_status != "REAL_LLM":
                _frozen_ibm_materialized = parent_attr("_materialize_ibm_bullets_from_frozen_allocation", _materialize_ibm_bullets_from_frozen_allocation)(
                    parsed,
                    selected_fact_plan=selected_fact_plan,
                )
                if _frozen_ibm_materialized and gen_meta:
                    reconcile_ibm_frozen_materialized_selection_gate(
                        artifact_dir=artifact_dir,
                        parsed=parsed,
                        gen_meta=gen_meta,
                        active_bullet_ids=active_bullet_ids,
                    )
            parent_attr("_bind_ibm_change_log_to_frozen_allocation", _bind_ibm_change_log_to_frozen_allocation)(
                parsed,
                selected_fact_plan=selected_fact_plan,
            )
            record_mechanical(
                artifact_dir,
                operation="align_ibm_claim_ledger_from_canonical_facts",
                reason="graph_plan_fact_id_alignment",
            )
            if runtime_generation_status != "REAL_LLM":
                record_mechanical(
                    artifact_dir,
                    operation="inject_ibm_plan_fact_metric_anchors",
                    reason="surface_fact_backed_metric_tokens_model_dropped",
                )
    else:
        parsed = None
        # E2E-09/10: do not label REAL_LLM output as 'provider blocked' — the provider
        # produced output; an empty selection / parse failure is the real downstream cause.
        parse_error = truthful_block_reason(result, runtime_generation_status, parse_error)

    bullets = list((parsed or {}).get("bullets") or [])
    claim_ledger_raw = list((parsed or {}).get("claim_ledger") or [])
    parse_status, invalid_reason = parent_attr("classify_ledger_parse_state", classify_ledger_parse_state)(
        parsed,
        parse_error=parse_error,
        raw_output=raw_output,
        lane_profile="ibm_bullets",
    )
    norm_rows = parent_attr("normalize_exec_summary_claim_ledger", normalize_exec_summary_claim_ledger)(claim_ledger_raw) if parse_status == "OK" else []
    canon_doc = parent_attr("build_canonical_claim_ledger_v2_payload", build_canonical_claim_ledger_v2_payload)(
        norm_rows,
        parse_status=parse_status,
        invalid_reason=invalid_reason if parse_status != "OK" else None,
        claim_id_prefix="ibm_bullets_claim",
    )
    _wg.write_text(artifact_dir / "raw_model_output.txt", raw_output or "", encoding="utf-8")
    parent_attr("write_json", write_json)(
        artifact_dir / "parsed_output.json",
        {"parsed": parsed, "parse_error": parse_error, "parse_status": parse_status},
    )
    parent_attr("write_json", write_json)(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)

    # W4.4 (G16): a REAL_LLM employment-pool run that merged 0 bullets fails ONCE with the
    # true reason instead of cascading through X1D + the ~15-gate X2 wall. Provider-BLOCKED
    # runs keep today's path. Raw/parsed/provider/pool artifacts above stay as written.
    sc_fire, sc_reason = should_short_circuit_empty_selection(
        gen_meta, bullets, runtime_generation_status, artifact_dir=artifact_dir
    )
    if sc_fire:
        from apps_rg.runtime.sections.upstream_evidence_block import (
            write_empty_selection_short_circuit_artifacts,
        )

        return write_empty_selection_short_circuit_artifacts(
            repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
            artifact_dir=artifact_dir,
            section_id="ibm_bullets",
            provider=str(args.provider),
            runtime_payload=runtime_payload,
            reason=sc_reason,
            gen_meta=gen_meta,
            bullets_in_merged=len(bullets),
            output_filename="ibm_bullets_output.txt",
        )

    claim_ledger = claim_ledger_raw
    coverage = parent_attr("build_ibm_bullets_text_claim_coverage", build_ibm_bullets_text_claim_coverage)(
        bullets, claim_ledger, allowed_fact_ids, active_bullet_ids=active_bullet_ids
    )

    parsed_for_x2 = strip_employment_bullet_intensity_model(
        {**(parsed or {}), "text_claim_coverage": coverage}
    ) or {"text_claim_coverage": coverage}
    model_name = parent_attr("resolve_provider_model_name", resolve_provider_model_name)(provider_request_data, provider_result_data)

    l2_output = {
        "run_id": runtime_payload["run_id"],
        "section_id": "ibm_bullets",
        "runtime_generation_status": runtime_generation_status,
        "product_quality_status": "PENDING",
        "ibm_header": ibm_header,
        "bullets": bullets,
        "selected_fact_plan": (parsed or {}).get("selected_fact_plan") or selected_fact_plan,
        "claim_ledger": claim_ledger,
        "jd_alignment": (parsed or {}).get("jd_alignment") or {"targeting_only": True},
        "gap_notes": (parsed or {}).get("gap_notes") or [],
        "change_log": (parsed or {}).get("change_log") or [],
        "self_check": (parsed or {}).get("self_check") or {"parse_error": parse_error},
        "text_claim_coverage": coverage,
        "prompt_id": PROMPT_ID,
        "prompt_hash": prompt_hash,
        "section_prompt_adapter": True,
        "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref,
        "compiler_template_id": section_compiled.artifact.template_id,
        "input_payload_hash": input_payload_hash,
    }
    _wg.write_text(artifact_dir / "ibm_bullets_output.txt", parent_attr("bullets_display_text", bullets_display_text)(bullets) + "\n", encoding="utf-8")
    parent_attr("write_json", write_json)(artifact_dir / "claim_ledger.json", claim_ledger)
    parent_attr("write_json", write_json)(artifact_dir / "selected_fact_plan.json", l2_output["selected_fact_plan"])
    parent_attr("write_json", write_json)(artifact_dir / "text_claim_coverage.json", coverage)
    req_id = str(
        (provider_request_data or {}).get("request_id")
        or (provider_request_data or {}).get("id")
        or runtime_payload["run_id"]
    )
    trace_rr = rel_posix(artifact_dir, parent_attr("REPO_ROOT", REPO_ROOT))
    usage_doc = parent_attr("build_section_input_usage_ledger_v1", build_section_input_usage_ledger_v1)(
        section_id="ibm_bullets",
        run_id=str(runtime_payload["run_id"]),
        request_id=req_id,
        trace_root=trace_rr,
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        artifact_dir=artifact_dir,
        runtime_payload=runtime_payload,
        selected_fact_plan=l2_output["selected_fact_plan"],
        claim_ledger=claim_ledger,
        allowed_fact_ids=allowed_fact_ids,
        jd_text=str(runtime_payload.get("jd_text") or ""),
        target_title=str(runtime_payload.get("target_title") or ""),
        target_company=str(runtime_payload.get("target_company") or ""),
        briefing_text=str(runtime_payload.get("briefing") or ""),
        jd_alignment=l2_output.get("jd_alignment"),
    )
    from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger

    parent_attr("write_json", write_json)(
        artifact_dir / "section_input_usage_ledger.json",
        parent_attr("apply_proof_pool_to_usage_ledger", apply_proof_pool_to_usage_ledger)(usage_doc, pool),
    )

    judge_keys = [j.strip() for j in str(getattr(args, "x1d_judges", "") or "").split(",") if j.strip()]
    judge_mode = "mocked" if getattr(args, "mock_judges", False) else "blocked_if_unavailable"
    from apps_rg.runtime.judges.ibm_bullets_x1d import JUDGE_RUBRIC_VERSION as _IBM_BULLETS_RUBRIC_VERSION
    from apps_rg.runtime.section_judge_policy import get_section_judge_policy
    from apps_rg.runtime.sections.ibm_role_episode_evidence import (
        approved_promotable_metric_evidence,
    )
    from apps_rg.runtime.sections.lane_perf_sync_helpers import build_blocked_pre_judge_rows

    pp_x2 = runtime_payload.get("proof_pool_metadata") or {}
    proof_pool_x2_active, srfs_slice_x2_active = x2_proof_pool_gate_flags(pp_x2)

    pre_x2 = [
        g.to_dict()
        for g in parent_attr("run_ibm_bullets_x2_gates", run_ibm_bullets_x2_gates)(
            bullets=bullets,
            parsed_output=parsed_for_x2,
            claim_ledger=claim_ledger,
            allowed_fact_ids=allowed_fact_ids,
            jd_text=args.jd_text,
            runtime_generation_status=runtime_generation_status,
            artifacts_dir=artifact_dir,
            provider_requested=args.provider,
            provider_attempted=args.provider,
            model_name=model_name,
            raw_output=raw_output,
            x1d_judges=[],
            srfs_source_fact_slice_gate_active=srfs_slice_x2_active,
            proof_pool_metadata=pp_x2,
            proof_pool_ref=str(pool.proof_pool_ref or ""),
            proof_pool_digest=str(pool.proof_pool_digest or ""),
            base_resume=base,
            runtime_payload=runtime_payload,
        )
    ]
    pre_x2_failed = [
        str(g.get("gate_id") or "")
        for g in pre_x2
        if not g.get("pass")
        and str(g.get("gate_id") or "") not in {"x2_x1d_required_judges_present", "x2_x1d_schema_valid"}
    ]

    allowed_fact_packet = parent_attr("build_ibm_bullets_allowed_fact_packet", build_ibm_bullets_allowed_fact_packet)(
        ibm_facts=ibm_facts,
        ibm_header=ibm_header,
        proof_pool_ref=str(pool.proof_pool_ref or ""),
        proof_pool_digest=str(pool.proof_pool_digest or ""),
        approved_metric_evidence=approved_promotable_metric_evidence("ibm_bullets"),
    )
    # Variance-class alignment (2026-06): on the employment-pool path the Claude pool
    # SELECTOR has already model-scored every slot, but that selector is advisory-only. The
    # formal X1D proof row still comes from the section policy provider roster.
    proof_judge_keys = list(get_section_judge_policy("ibm_bullets").required_judge_providers)
    if pre_x2_failed and judge_mode != "mocked":
        proof_x1d = build_blocked_pre_judge_rows(
            section_id="ibm_bullets",
            judge_keys=proof_judge_keys,
            failed_gate_ids=pre_x2_failed,
            rubric_version=_IBM_BULLETS_RUBRIC_VERSION,
        )
    else:
        proof_x1d = [
            j.to_dict()
            for j in parent_attr("run_ibm_bullets_judges", run_ibm_bullets_judges)(
                bullets=bullets,
                claim_ledger=claim_ledger,
                judge_keys=proof_judge_keys,
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
    if is_employment_pool_generation(gen_meta):
        x1d = proof_x1d + employment_pool_x1d_judge_rows(
            artifact_dir=artifact_dir,
            section_id="ibm_bullets",
            gen_meta=gen_meta,
        )
    else:
        x1d = proof_x1d
    temperature = float(args.temperature) if args.provider == "external_claude" else IBM_TEMP_DEFAULT

    parent_attr("write_json", write_json)(
        artifact_dir / "prompt_selection_trace.json",
        {
            "runtime_path": "apps_rg.runtime.sections.ibm_bullets_lane",
            "prompt_id": PROMPT_ID,
            "provider": args.provider,
            "temperature": temperature,
            "section_prompt_adapter": True,
            "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref,
            "compiler_template_id": section_compiled.artifact.template_id,
        },
    )

    x2 = [
        g.to_dict()
        for g in parent_attr("run_ibm_bullets_x2_gates", run_ibm_bullets_x2_gates)(
            bullets=bullets,
            parsed_output=parsed_for_x2,
            claim_ledger=claim_ledger,
            allowed_fact_ids=allowed_fact_ids,
            jd_text=args.jd_text,
            runtime_generation_status=runtime_generation_status,
            artifacts_dir=artifact_dir,
            provider_requested=args.provider,
            provider_attempted=args.provider,
            model_name=model_name,
            raw_output=raw_output,
            x1d_judges=x1d,
            srfs_source_fact_slice_gate_active=srfs_slice_x2_active,
            proof_pool_metadata=pp_x2,
            proof_pool_ref=str(pool.proof_pool_ref or ""),
            proof_pool_digest=str(pool.proof_pool_digest or ""),
            base_resume=base,
            runtime_payload=runtime_payload,
        )
    ]

    for g in x2:
        obs = g.get("observed_value")
        if isinstance(obs, dict) and obs.get("x2_source_fact_pool_status"):
            write_x2_source_fact_pool_receipt(artifact_dir, obs)
            break
    parent_attr("write_x2_gate_outputs", write_x2_gate_outputs)(artifact_dir / "x2_gate_outputs.json", x2, section_id="ibm_bullets")
    parent_attr("write_json", write_json)(
        artifact_dir / "fact_check_result.json",
        {"passed": not [g for g in x2 if not g["pass"]], "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]]},
    )
    ctx.update(
        {
            "req_model": req_model,
            "judge_mode": judge_mode,
            "active_bullet_ids": active_bullet_ids,
            "_ibm_has_frozen_allocation": _ibm_has_frozen_allocation,
            "_frozen_ibm_materialized": _frozen_ibm_materialized,
            "provider_result_data": provider_result_data,
            "raw_output": raw_output,
            "runtime_generation_status": runtime_generation_status,
            "parsed": parsed,
            "parse_error": parse_error,
            "gen_meta": gen_meta,
            "bullets": bullets,
            "claim_ledger": claim_ledger,
            "canon_doc": canon_doc,
            "parsed_for_x2": parsed_for_x2,
            "model_name": model_name,
            "l2_output": l2_output,
            "usage_doc": usage_doc,
            "allowed_fact_packet": allowed_fact_packet,
            "x1d": x1d,
            "pp_x2": pp_x2,
            "srfs_slice_x2_active": srfs_slice_x2_active,
            "x2": x2,
            "req_id": req_id,
            "trace_rr": trace_rr,
        }
    )
    return ctx
