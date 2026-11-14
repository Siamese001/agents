"""Stage 2: Provider execution, bullet-pool/text materialization, X2/X1D, and canonical ledger."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.exit.executive_summary_x3 import aggregate_x3
from apps_rg.runtime.providers import ProviderGatewayError
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.reasoning.bullet_lane_generation import generate_bullet_lane_with_sc_and_claude
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    REQUIRED_BULLET_IDS,
    build_employment_targeting_context,
    is_employment_bullet_lane,
)
from apps_rg.runtime.runtime_proof_layout import rel_posix
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.sections.lane_artifact_io import runtime_payload_for_json, write_json
from apps_rg.runtime.sections.section_generation import build_section_request
from apps_rg.runtime.validators.proof_pool_source_fact_validation import write_x2_source_fact_pool_receipt
from ._parent import parent_attr
from .lane_config import (
    REPO_ROOT,
    ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
    ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION,
    _json_hash,
    _role_header,
)
from .materialization import (
    _claim_ledger_from_bullets,
    _display_text,
    _llm_generation_status,
    _materialize_bullet_generation,
    _normalize_role_episode_bullet_pool_parsed,
    _parse_json_object,
    _reconcile_final_materialized_selection_gate,
)
from .narrative_binding import (
    _narrative_from_parsed,
    _narrative_source_ids_for_claim,
    _parsed_claim_ledger_source_ids_for_narrative,
)
from .proof_selection import _ordered_ids_from_bullets, _proof_authorized_narrative_from_selection
from .prompt_compiler import _blocked_provider_result
from .x2_gates import _judge_rows, run_role_episode_x2_gates


def run_role_episode_generation_stage(
    args: Any,
    ctx: dict[str, Any],
    *,
    provider_gateway_fn: Any,
) -> dict[str, Any]:
    """Execute provider dispatch, bullet/narrative materialization, X2, X1D, and ledger build."""
    sid = ctx["sid"]
    cfg = ctx["cfg"]
    max_output_tokens = ctx["max_output_tokens"]
    run_id = ctx["run_id"]
    artifact_dir: Path = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    pool = ctx["pool"]
    base = ctx["base"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    facts = ctx["facts"]
    companion_text = ctx["companion_text"]
    prompt_text = ctx["prompt_text"]
    prompt_hash = ctx["prompt_hash"]
    compiled_obj = ctx["compiled_obj"]
    generation_model = ctx["generation_model"]
    messages = [
        {"role": "system", "content": compiled_obj.system_preamble},
        {"role": "user", "content": prompt_text},
    ]
    provider_req, provider_payload = build_section_request(
        messages=messages,
        prompt_hash=prompt_hash[:16],
        input_payload_hash=_json_hash(runtime_payload),
        temperature=float(args.temperature),
        max_tokens=max_output_tokens,
        model=generation_model,
        provider_requested=str(args.provider),
    )
    parent_attr("write_json", write_json)(artifact_dir / "provider_request.json", provider_req.to_dict())
    generation_meta: dict[str, Any] = {}
    if sid == "ey_bullets":
        # Short-circuit EY bullets: 0 standalone bullets, no external provider call.
        provider_result = ProviderResult(
            provider_requested=str(args.provider),
            provider_attempted=False,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="zero_bullet_consolidation",
            raw_model_output=json.dumps({"bullets": [], "claim_ledger": [], "jd_alignment": {"targeting_only": True}}),
            provider_response={"status": "zero_bullets_consolidated", "section_lane": sid},
        )
        parent_attr("write_json", write_json)(artifact_dir / "provider_response.json", provider_result.to_dict())
        raw_output = provider_result.raw_model_output
        parsed = {"bullets": [], "claim_ledger": [], "jd_alignment": {"targeting_only": True}}
        parse_error = ""
    elif cfg.is_bullet_lane and is_employment_bullet_lane(sid):
        provider_result, raw_output, parsed, parse_error, generation_meta = (
            parent_attr("generate_bullet_lane_with_sc_and_claude", generate_bullet_lane_with_sc_and_claude)(
                section_lane=sid,
                slot_kind="bullets",
                provider_payload=provider_payload,
                parse_model_json=_parse_json_object,
                normalize_parsed=lambda p: _normalize_role_episode_bullet_pool_parsed(
                    p,
                    cfg=cfg,
                    allowed=allowed_fact_ids,
                ),
                artifact_dir=artifact_dir,
                run_id=run_id,
                base_temperature=float(args.temperature),
                required_bullet_ids=REQUIRED_BULLET_IDS.get(sid, ()),
                targeting_context=build_employment_targeting_context(
                    runtime_payload,
                    section_lane=sid,
                ),
                judge_mode="mocked"
                if bool(getattr(args, "mock_judges", False) and getattr(args, "allow_test_mock_judges", False))
                else "blocked_if_unavailable",
                use_sc_path=True,
                provider_profile=str(args.provider),
            )
        )
        if provider_result is None:
            provider_result = _blocked_provider_result(
                str(args.provider),
                parse_error or "SC pool generation returned no provider result",
                model=generation_model,
            )
        parent_attr("write_json", write_json)(
            artifact_dir / "provider_response.json",
            {
                **provider_result.to_dict(),
                "generation_meta": generation_meta,
            },
        )
    elif sid == "ey_narrative":
        # Short-circuit EY narrative: 0 standalone narrative sentences, no external provider call.
        provider_result = ProviderResult(
            provider_requested=str(args.provider),
            provider_attempted=False,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="zero_narrative_consolidation",
            raw_model_output=json.dumps({"narrative_sentence": "", "claim_ledger": [], "jd_alignment": {"targeting_only": True}}),
            provider_response={"status": "zero_narrative_consolidated", "section_lane": sid},
        )
        parent_attr("write_json", write_json)(artifact_dir / "provider_response.json", provider_result.to_dict())
        raw_output = provider_result.raw_model_output
        parsed = {"narrative_sentence": "", "claim_ledger": [], "jd_alignment": {"targeting_only": True}}
        parse_error = ""
    else:
        from apps_rg.runtime.sections.lane_perf_sync_helpers import invoke_role_episode_gateway_with_usage_scope
        try:
            provider_result = invoke_role_episode_gateway_with_usage_scope(
                artifact_dir=artifact_dir, run_id=run_id, sid=sid, provider=str(args.provider),
                gateway_fn=parent_attr("_provider_gateway", provider_gateway_fn), compiled_obj=compiled_obj, max_output_tokens=max_output_tokens, temperature=float(args.temperature),
            )
        except ProviderGatewayError as exc:
            provider_result = _blocked_provider_result(str(args.provider), str(exc), model=generation_model)
        parent_attr("write_json", write_json)(artifact_dir / "provider_response.json", provider_result.to_dict())
        raw_output = provider_result.raw_model_output
        parsed, parse_error = _parse_json_object(raw_output)

    header = parent_attr("_role_header", _role_header)(base, cfg, args)
    if cfg.is_bullet_lane:
        bullets, generation_receipt = parent_attr("_materialize_bullet_generation", _materialize_bullet_generation)(
            cfg=cfg,
            parsed=parsed,
            parse_error=parse_error,
            provider_runtime_generation_status=provider_result.runtime_generation_status,
            facts=facts,
            allowed=allowed_fact_ids,
            graph_packet_digest=pool.proof_pool_digest,
        )
        if generation_meta:
            parent_attr("_reconcile_final_materialized_selection_gate", _reconcile_final_materialized_selection_gate)(
                artifact_dir=artifact_dir,
                section_id=sid,
                bullets=bullets,
                generation_meta=generation_meta,
            )
            generation_receipt.update(
                {
                    "generation_mode": generation_meta.get("generation_mode"),
                    "initial_path_count": generation_meta.get("initial_path_count"),
                    "total_paths_executed": generation_meta.get("total_paths_executed"),
                    "regen_rounds_executed": generation_meta.get("regen_rounds_executed"),
                    "selection_gate": generation_meta.get("selection_gate"),
                    "producer_selection_gate": generation_meta.get("producer_selection_gate"),
                    "final_materialized_selection_gate": generation_meta.get(
                        "final_materialized_selection_gate"
                    ),
                    "selection_mode": generation_meta.get("selection_mode"),
                    "source_path_by_slot": generation_meta.get("source_path_by_slot"),
                }
            )
        claim_ledger = _claim_ledger_from_bullets(bullets)
        l2 = {
            "run_id": run_id,
            "section_id": sid,
            "runtime_generation_status": provider_result.runtime_generation_status,
            "product_quality_status": "PENDING",
            cfg.header_key: header,
            "bullets": bullets,
            "selected_fact_plan": selected_fact_plan,
            "claim_ledger": claim_ledger,
            "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
            "prompt_hash": prompt_hash[:16],
            **generation_receipt,
        }
        if generation_meta:
            l2["generation_meta"] = generation_meta
        l2["generation_receipt"] = dict(generation_receipt)
    else:
        model_surface_used = False
        if sid == "ey_narrative":
            narrative_from_model = False
            narrative = ""
            source_ids = []
            narrative_selection_source = "zero_narrative_consolidation"
            narrative_source_repairs = []
            claim_ledger = []
        else:
            narrative_from_model = _narrative_from_parsed(parsed or {})
            narrative, source_ids, narrative_selection_source, model_surface_used = _proof_authorized_narrative_from_selection(
                parsed=parsed or {},
                facts=facts,
                allowed=allowed_fact_ids,
                section_id=sid,
                companion_bullet_texts=companion_text,
            )
            parsed_ledger_source_ids = _parsed_claim_ledger_source_ids_for_narrative(
                parsed=parsed or {},
                narrative=narrative,
                allowed=allowed_fact_ids,
            )
            raw_source_ids = source_ids or (parsed or {}).get("source_fact_ids") or parsed_ledger_source_ids
            source_ids, narrative_source_repairs = _narrative_source_ids_for_claim(
                narrative=narrative,
                raw_source_ids=raw_source_ids,
                allowed=allowed_fact_ids,
                selected_fact_plan=selected_fact_plan,
            )
            for fid in parsed_ledger_source_ids:
                if fid not in source_ids:
                    source_ids.append(fid)
                    narrative_source_repairs.append(fid)
            claim_ledger = [{"claim_text": narrative, "source_fact_ids": source_ids}] if narrative else []
        llm_status = "not_run"
        if provider_result.runtime_generation_status == "REAL_LLM":
            if parse_error == "empty_model_output":
                llm_status = "empty_output"
            elif parsed is None or not narrative_from_model:
                llm_status = "invalid_output"
            else:
                llm_status = "usable_output"
        display_auth = (
            "model_selected_graph_bound_surface"
            if model_surface_used
            else "selected_fact_plan_claim_text"
            if narrative
            else ""
        )
        generation_receipt = {
            "generation_method": (
                "llm_selected_graph_bound_surface"
                if model_surface_used
                else "llm_selected_proof_render"
                if narrative_from_model
                else "deterministic_graph_render"
            ),
            "llm_generation_status": llm_status,
            "llm_output_used": bool(model_surface_used),
            "llm_selection_used": bool(narrative_from_model and narrative),
            "model_display_text_discarded": bool(narrative_from_model and not model_surface_used),
            "display_text_authority": display_auth,
            "selection_source": narrative_selection_source,
            "evidence_authority": "augmented_skills_graph",
            "source_fact_ids": source_ids if narrative else [],
            "graph_packet_digest": str(pool.proof_pool_digest or ""),
            "renderer_version": (
                "model_selected_graph_bound_surface.v1"
                if model_surface_used
                else ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION
                if narrative
                else ""
            ),
            "lane_contract_allows_deterministic_graph_render": False,
            "allowed_graph_packet_fact_count": len(allowed_fact_ids),
            "rendered_source_fact_ids_within_allowed_packet": set(source_ids).issubset(set(allowed_fact_ids)),
        }
        if narrative_source_repairs:
            generation_receipt["source_fact_binding_repair"] = {
                "operation": "role_episode_narrative_material_claim_source_reconciliation",
                "added_source_fact_ids": narrative_source_repairs,
            }
        l2 = {
            "run_id": run_id,
            "section_id": sid,
            "runtime_generation_status": provider_result.runtime_generation_status,
            "product_quality_status": "PENDING",
            cfg.header_key: header,
            "narrative_sentence": narrative,
            "selected_fact_plan": selected_fact_plan,
            "claim_ledger": claim_ledger,
            "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
            "prompt_hash": prompt_hash[:16],
            **generation_receipt,
        }
        if companion_text:
            l2["companion_bullet_texts"] = companion_text
        l2["generation_receipt"] = dict(generation_receipt)

    proof_meta = dict(pool.proof_pool_metadata or {})
    bundle_consumed = bool(proof_meta.get("role_episode_bundle_consumption"))
    l2["role_episode_bundle_consumed"] = bundle_consumed
    x2 = parent_attr("run_role_episode_x2_gates", run_role_episode_x2_gates)(
        section_id=sid,
        l2=l2,
        allowed=allowed_fact_ids,
        runtime_generation_status=provider_result.runtime_generation_status,
    )
    product_quality_status = (
        "PASS" if provider_result.runtime_generation_status == "REAL_LLM" and all(g.get("pass") for g in x2) else "FAIL"
    )
    l2["product_quality_status"] = product_quality_status
    l2["product_quality_reason"] = "x2_pass" if product_quality_status == "PASS" else "x2_or_provider_blocked"
    lane_status = "PASS" if product_quality_status == "PASS" else "FAIL"
    generation_receipt["lane_status"] = lane_status
    l2["lane_status"] = lane_status
    l2["generation_receipt"] = dict(generation_receipt)
    x1d = parent_attr("_judge_rows", _judge_rows)(
        cfg=cfg,
        provider_result=provider_result,
        x2_gates=x2,
        l2=l2,
        allowed_fact_ids=allowed_fact_ids,
        mock_judges=bool(getattr(args, "mock_judges", False)),
        artifact_dir=artifact_dir,
        generation_meta=generation_meta,
    )
    usage_doc = parent_attr("build_section_input_usage_ledger_v1", build_section_input_usage_ledger_v1)(
        section_id=sid,
        run_id=run_id,
        request_id=run_id,
        trace_root=rel_posix(artifact_dir, parent_attr("REPO_ROOT", REPO_ROOT)),
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        artifact_dir=artifact_dir,
        runtime_payload=runtime_payload,
        selected_fact_plan=selected_fact_plan,
        claim_ledger=claim_ledger,
        allowed_fact_ids=set(allowed_fact_ids),
        jd_text=str(runtime_payload.get("jd_text") or ""),
        target_title=str(runtime_payload.get("target_title") or ""),
        target_company=str(runtime_payload.get("target_company") or ""),
        briefing_text=str(runtime_payload.get("briefing") or ""),
        jd_alignment=l2.get("jd_alignment"),
    )
    usage_doc = parent_attr("apply_proof_pool_to_usage_ledger", apply_proof_pool_to_usage_ledger)(usage_doc, pool)

    norm_rows = parent_attr("normalize_exec_summary_claim_ledger", normalize_exec_summary_claim_ledger)(claim_ledger)
    canon_doc = parent_attr("build_canonical_claim_ledger_v2_payload", build_canonical_claim_ledger_v2_payload)(
        norm_rows,
        parse_status="OK" if parsed is not None else "INVALID_JSON",
        invalid_reason=parse_error if parsed is None else None,
        claim_id_prefix=f"{sid}_claim",
    )
    x3 = parent_attr("aggregate_x3", aggregate_x3)(
        resume_display_text=_display_text(l2, cfg),
        claim_ledger=claim_ledger,
        x2_gates=x2,
        x1d_judges=x1d,
        runtime_generation_status=provider_result.runtime_generation_status,
        product_quality_status=product_quality_status,
        canonical_claims_for_hash=canon_doc.get("claims"),
        section_input_usage_ledger=usage_doc,
        judge_required_for_allow=True,
    )

    failed = [g["gate_id"] for g in x2 if not g.get("pass")]
    parent_attr("write_json", write_json)(artifact_dir / "l2_output.json", l2)
    if cfg.is_bullet_lane:
        parent_attr("write_json", write_json)(
            artifact_dir / ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
            l2.get("final_materialized_selection_contract") or {},
        )
    parent_attr("write_json", write_json)(artifact_dir / "selected_fact_plan.json", selected_fact_plan)
    parent_attr("write_json", write_json)(artifact_dir / "claim_ledger.json", claim_ledger)
    parent_attr("write_json", write_json)(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)
    proof_display_gate = next(
        (g for g in x2 if g.get("gate_id") == f"x2_{sid}_display_text_proof_authorized"),
        {},
    )
    proof_display_obs = (
        proof_display_gate.get("observed_value")
        if isinstance(proof_display_gate.get("observed_value"), dict)
        else {}
    )
    ctx.update(
        {
            "provider_result": provider_result,
            "parsed": parsed,
            "parse_error": parse_error,
            "claim_ledger": claim_ledger,
            "generation_receipt": generation_receipt,
            "l2": l2,
            "x2": x2,
            "product_quality_status": product_quality_status,
            "lane_status": lane_status,
            "x1d": x1d,
            "usage_doc": usage_doc,
            "x3": x3,
            "failed": failed,
            "proof_display_gate": proof_display_gate,
            "proof_display_obs": proof_display_obs,
        }
    )
    return ctx
