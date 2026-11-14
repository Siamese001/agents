"""Stage 2: Unify bullets model invocation, repairs, usage ledger, X2, and composite judge."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    classify_ledger_parse_state,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.judges.unify_bullets_x1d import run_unify_bullets_judges
from apps_rg.runtime.offline_contract_status import OFFLINE_CONTRACT_STUB_RUNTIME_STATUS
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
    sc_path_count_for_lane,
)
from apps_rg.runtime.runtime_proof_layout import rel_posix
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.section_repair_lane_integration import (
    record_deterministic_rewrite,
    record_parse_json_retry,
)
from apps_rg.runtime.sections.executive_summary_lane import (
    resolve_provider_model_name,
    write_x2_gate_outputs,
)
from apps_rg.runtime.sections.prompt_trace_reasoning import attach_reasoning_to_prompt_trace
from apps_rg.runtime.validators.proof_pool_source_fact_validation import (
    write_x2_source_fact_pool_receipt,
)
from apps_rg.runtime.validators.unify_bullets_x2 import (
    UNIFY_BULLET_IDS,
    build_unify_bullets_text_claim_coverage,
    run_unify_bullets_x2_gates,
)
from ._parent import parent_attr
from .lane_constants import (
    LANE_KEY,
    PROMPT_ID,
    REPO_ROOT,
    UNIFY_MAX_OUTPUT_TOKENS,
    UNIFY_TEMP_DEFAULT,
    UNIFY_TEMP_RANGE,
    sha16,
    write_json,
)
from .metric_surfaces import _authoritative_selected_fact_plan
from .provider_io import (
    build_mock_output,
    bullets_display_text,
    enrich_unify_parsed_for_x2,
    parse_model_json,
    retry_provider_for_parse,
)
from .repairs import (
    _repair_protected_unify_bullet_metrics,
    normalize_unify_parsed_without_ledger_synthesis,
)


def _write_pre_x2_evaluation_state_delegate(artifact_dir: Path) -> None:
    parent_attr("write_json", write_json)(
        artifact_dir / "x3_disposition.json", {"x3_code": "PENDING", "status": "pending"}
    )
    parent_attr("write_x2_gate_outputs", write_x2_gate_outputs)(
        artifact_dir / "x2_gate_outputs.json", [], section_id="unify_bullets"
    )


def run_unify_generation_and_x2_stage(
    args: argparse.Namespace,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Execute Unify generation, repairs, canonical ledger, X2 gates, and X1D judge."""
    artifact_dir: Path = ctx["artifact_dir"]
    base = ctx["base"]
    pool = ctx["pool"]
    unify_header = ctx["unify_header"]
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
    _write_pre_x2_evaluation_state = parent_attr(
        "_write_pre_x2_evaluation_state", _write_pre_x2_evaluation_state_delegate
    )
    req_model = str(provider_payload.get("model", section_model))
    judge_mode = "mocked" if getattr(args, "mock_judges", False) else "blocked_if_unavailable"
    result, raw_output, parsed_in, parse_error, gen_meta = parent_attr("generate_bullet_lane_with_sc_and_claude", generate_bullet_lane_with_sc_and_claude)(
        section_lane=LANE_KEY,
        slot_kind="bullets",
        provider_payload=provider_payload,
        parse_model_json=parse_model_json,
        normalize_parsed=lambda p: parent_attr("normalize_unify_parsed_without_ledger_synthesis", normalize_unify_parsed_without_ledger_synthesis)(p, runtime_payload),
        artifact_dir=artifact_dir,
        run_id=str(runtime_payload.get("run_id") or ""),
        temperature_bounds=UNIFY_TEMP_RANGE,
        base_temperature=float(args.temperature) if args.provider == "external_claude" else UNIFY_TEMP_DEFAULT,
        required_bullet_ids=UNIFY_BULLET_IDS,
        targeting_context=build_employment_targeting_context(runtime_payload, section_lane=LANE_KEY),
        judge_mode=judge_mode,
        provider_profile=str(args.provider),
    )
    parent_attr("write_json", write_json)(artifact_dir / "bullet_lane_generation.json", gen_meta)
    provider_result_data = result.to_dict() if result else {}
    runtime_generation_status = result.runtime_generation_status if result else "BLOCKED"
    parent_attr("write_json", write_json)(artifact_dir / "provider_response.json", provider_result_data)
    parsed = parsed_in
    if (
        str(args.provider) == "external_claude"
        and result
        and result.runtime_generation_status == "REAL_LLM"
        and parsed_in is None
    ):
        raw_output, parsed_in, parse_error = parent_attr("retry_provider_for_parse", retry_provider_for_parse)(
            messages, provider_payload, raw_output, parse_error
        )
        if parsed_in is not None:
            record_parse_json_retry(artifact_dir, reason=parse_error or "parse_retry")
        parsed = (
            parent_attr("normalize_unify_parsed_without_ledger_synthesis", normalize_unify_parsed_without_ledger_synthesis)(parsed_in, runtime_payload) if parsed_in else None
        )
    if parsed is not None:
        from apps_rg.runtime.c0.graph_story_authority import forbid_base_resume_bullet_hydration
        from apps_rg.runtime.sections.unify_canonical_hydration import (
            should_hydrate_unify_bullets_from_canonical,
        )

        forbid_base_resume_bullet_hydration(
            section_id="unify_bullets",
            runtime_payload=runtime_payload,
            parsed=parsed,
            base_resume=base,
            would_hydrate_fn=should_hydrate_unify_bullets_from_canonical,
        )
        _pre_metric_repair = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        _repair_protected_unify_bullet_metrics(out=parsed, runtime_payload=runtime_payload)
        if json.dumps(parsed, sort_keys=True, separators=(",", ":")) != _pre_metric_repair:
            record_deterministic_rewrite(
                artifact_dir,
                operation="repair_protected_unify_bullet_metrics",
                reason="restore_canonical_protected_metrics",
            )
    elif result and result.runtime_generation_status == OFFLINE_CONTRACT_STUB_RUNTIME_STATUS:
        parsed_in, parse_error = parent_attr("parse_model_json", parse_model_json)(raw_output)
        parsed = parent_attr("normalize_unify_parsed_without_ledger_synthesis", normalize_unify_parsed_without_ledger_synthesis)(parsed_in, runtime_payload) if parsed_in else None
    elif not parsed:
        # E2E-09/10: do not label REAL_LLM output as 'provider blocked' — an empty selection /
        # parse failure on real provider output is a downstream cause, not a provider block.
        parse_error = truthful_block_reason(result, runtime_generation_status, parse_error)

    bullets = list((parsed or {}).get("bullets") or [])
    claim_ledger_raw = list((parsed or {}).get("claim_ledger") or []) if parsed else []
    parse_status, invalid_reason = parent_attr("classify_ledger_parse_state", classify_ledger_parse_state)(
        parsed,
        parse_error=parse_error,
        raw_output=raw_output,
        lane_profile="unify_bullets",
    )
    norm_rows = parent_attr("normalize_exec_summary_claim_ledger", normalize_exec_summary_claim_ledger)(claim_ledger_raw) if parse_status == "OK" else []
    canon_doc = parent_attr("build_canonical_claim_ledger_v2_payload", build_canonical_claim_ledger_v2_payload)(
        norm_rows,
        parse_status=parse_status,
        invalid_reason=invalid_reason if parse_status != "OK" else None,
        claim_id_prefix="unify_bullets_claim",
    )
    claim_ledger = claim_ledger_raw

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
            section_id="unify_bullets",
            provider=str(args.provider),
            runtime_payload=runtime_payload,
            reason=sc_reason,
            gen_meta=gen_meta,
            bullets_in_merged=len(bullets),
            output_filename="unify_bullets_output.txt",
        )

    display_for_coverage = parent_attr("bullets_display_text", bullets_display_text)(bullets)
    coverage = parent_attr("build_unify_bullets_text_claim_coverage", build_unify_bullets_text_claim_coverage)(bullets, claim_ledger, allowed_fact_ids)
    parsed_for_x2 = parent_attr("enrich_unify_parsed_for_x2", enrich_unify_parsed_for_x2)(
        parsed,
        coverage=coverage,
        input_payload_hash=input_payload_hash,
        allowed_fact_ids=allowed_fact_ids,
    )
    model_name = parent_attr("resolve_provider_model_name", resolve_provider_model_name)(provider_request_data, provider_result_data)
    temperature = float(args.temperature) if args.provider == "external_claude" else UNIFY_TEMP_DEFAULT

    l2_output = {
        "run_id": runtime_payload["run_id"],
        "section_id": "unify_bullets",
        "runtime_generation_status": runtime_generation_status,
        "product_quality_status": "PENDING",
        "product_quality_reason": "",
        "unify_header": unify_header,
        "bullets": bullets,
        "selected_fact_plan": _authoritative_selected_fact_plan(
            (parsed or {}).get("selected_fact_plan"),
            runtime_payload,
        )
        or selected_fact_plan,
        "claim_ledger": claim_ledger,
        "jd_alignment": (parsed or {}).get("jd_alignment") or {"targeting_only": True, "jd_used_as_proof": False},
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
        "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"),
        "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"),
        "allowed_fact_ids_hash": (parsed_for_x2 or {}).get("allowed_fact_ids_hash"),
    }
    from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
        sanitize_l2_employment_bullet_record,
    )

    parent_attr("write_json", write_json)(artifact_dir / "l2_output.json", sanitize_l2_employment_bullet_record(l2_output))
    _wg.write_text(artifact_dir / "unify_bullets_output.txt", display_for_coverage + "\n", encoding="utf-8")
    parent_attr("write_json", write_json)(artifact_dir / "selected_fact_plan.json", l2_output["selected_fact_plan"])
    parent_attr("write_json", write_json)(artifact_dir / "claim_ledger.json", claim_ledger)
    parent_attr("write_json", write_json)(artifact_dir / "text_claim_coverage.json", coverage)
    req_id = str(
        (provider_request_data or {}).get("request_id")
        or (provider_request_data or {}).get("id")
        or runtime_payload["run_id"]
    )
    trace_rr = rel_posix(artifact_dir, parent_attr("REPO_ROOT", REPO_ROOT))
    usage_doc = parent_attr("build_section_input_usage_ledger_v1", build_section_input_usage_ledger_v1)(
        section_id="unify_bullets",
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
    judge_mode = "mocked" if getattr(args, "mock_judges", False) else "blocked_if_unavailable"
    from apps_rg.runtime.section_judge_policy import get_section_judge_policy

    judge_keys = list(get_section_judge_policy(LANE_KEY).required_judge_providers)
    proof_x1d = [
        j.to_dict()
        for j in parent_attr("run_unify_bullets_judges", run_unify_bullets_judges)(
            bullets=bullets,
            claim_ledger=claim_ledger,
            judge_keys=judge_keys,
            mode=judge_mode,
            artifact_base=artifact_dir,
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
            section_id=LANE_KEY,
            gen_meta=gen_meta,
        )
    else:
        x1d = proof_x1d
    trace = parent_attr("attach_reasoning_to_prompt_trace", attach_reasoning_to_prompt_trace)(
        {
            "runtime_path": "apps_rg.runtime.sections.unify_bullets_lane",
            "prompt_id": PROMPT_ID,
            "provider": args.provider,
            "temperature": temperature,
            "section_prompt_adapter": True,
            "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref,
            "compiler_template_id": section_compiled.artifact.template_id,
        },
        provider=args.provider,
        lane_key=LANE_KEY,
        provider_result_data=provider_result_data if isinstance(provider_result_data, dict) else None,
    )
    parent_attr("write_json", write_json)(artifact_dir / "prompt_selection_trace.json", trace)
    # ``fact_check_result.json`` is a final X2 receipt, not an in-progress
    # marker.  Materializing a tiny pending placeholder and then replacing it
    # with the real failed-gate list trips the guarded writer's amplification
    # check even though the final receipt is ordinary, bounded output.
    # Keep it absent until X2 has actually evaluated the generated bullets.
    parent_attr("_write_pre_x2_evaluation_state", _write_pre_x2_evaluation_state)(artifact_dir)


    pp_x2 = runtime_payload.get("proof_pool_metadata") or {}
    proof_pool_x2_active, srfs_slice_x2_active = x2_proof_pool_gate_flags(pp_x2)

    x2 = [
        g.to_dict()
        for g in parent_attr("run_unify_bullets_x2_gates", run_unify_bullets_x2_gates)(
            bullets=bullets,
            parsed_output=parsed_for_x2,
            claim_ledger=claim_ledger,
            allowed_fact_ids=allowed_fact_ids,
            jd_text=runtime_payload["jd_text"],
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
    parent_attr("write_x2_gate_outputs", write_x2_gate_outputs)(artifact_dir / "x2_gate_outputs.json", x2, section_id="unify_bullets")
    parent_attr("write_json", write_json)(
        artifact_dir / "fact_check_result.json",
        {
            "passed": not [g for g in x2 if not g["pass"]],
            "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]],
        },
    )
    ctx.update(
        {
            "req_model": req_model,
            "judge_mode": judge_mode,
            "provider_result_data": provider_result_data,
            "raw_output": raw_output,
            "runtime_generation_status": runtime_generation_status,
            "parsed": parsed,
            "parse_error": parse_error,
            "parse_status": parse_status,
            "gen_meta": gen_meta,
            "bullets": bullets,
            "claim_ledger": claim_ledger,
            "canon_doc": canon_doc,
            "parsed_for_x2": parsed_for_x2,
            "model_name": model_name,
            "l2_output": l2_output,
            "usage_doc": usage_doc,
            "x1d": x1d,
            "pp_x2": pp_x2,
            "srfs_slice_x2_active": srfs_slice_x2_active,
            "x2": x2,
            "req_id": req_id,
            "trace_rr": trace_rr,
            "coverage": coverage,
            "display_for_coverage": display_for_coverage,
            "temperature": temperature,
            "trace": trace,
        }
    )
    return ctx
