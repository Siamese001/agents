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
        reasoning_effort=getattr(args, "reasoning_effort", None) or "low",
        force_new_seed=bool(getattr(args, "force_new_seed", False)),
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
                    allow_prose_mutation=False,
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
            allow_narr_mut = provider_result.runtime_generation_status != "REAL_LLM"
            narrative_from_model = _narrative_from_parsed(parsed or {}, allow_prose_mutation=allow_narr_mut)
            narrative, source_ids, narrative_selection_source, model_surface_used = _proof_authorized_narrative_from_selection(
                parsed=parsed or {},
                facts=facts,
                allowed=allowed_fact_ids,
                section_id=sid,
                companion_bullet_texts=companion_text,
                allow_prose_mutation=allow_narr_mut,
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
    l2["target_company"] = str(runtime_payload.get("target_company") or "")
    l2["target_title"] = str(runtime_payload.get("target_title") or "")
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
    mock_judges_flag = bool(getattr(args, "mock_judges", False))
    x1d = parent_attr("_judge_rows", _judge_rows)(
        cfg=cfg,
        provider_result=provider_result,
        x2_gates=x2,
        l2=l2,
        allowed_fact_ids=allowed_fact_ids,
        mock_judges=mock_judges_flag,
        artifact_dir=artifact_dir,
        generation_meta=generation_meta,
        runtime_payload=runtime_payload,
        product_quality_status=product_quality_status,
    )

    proof_x1d_failed = any(
        not bool(j.get("pass", True))
        for j in x1d
        if not j.get("advisory_only")
        and not bool(j.get("provider_blocked"))
        and not str(j.get("provider_status") or "").upper().startswith("BLOCKED_PROVIDER")
    )
    if (
        provider_result.runtime_generation_status == "REAL_LLM"
        and not mock_judges_flag
        and sid not in {"ey_bullets", "ey_narrative"}
        and (product_quality_status != "PASS" or proof_x1d_failed)
    ):
        from apps_rg.runtime.providers.section_provider_call import call_section_model_provider
        from apps_rg.runtime.sections.section_generation import tag_reasoning_lane

        import re

        rw_receipt: dict[str, Any] = {
            "schema_version": "role_episode_judge_rewrite_receipt_v1",
            "section_id": sid,
            "attempted": True,
            "accepted": False,
            "trigger": "x2_failure" if product_quality_status != "PASS" else "x1d_judge_feedback",
            "critique": "",
        }
        cur_draft_raw = raw_output or ""
        cur_x2 = x2
        cur_x1d = x1d
        for _rw_attempt in range(2):
            x2_fail_msgs = [
                f"{g.get('gate_id')}: {g.get('failure_reason') or g.get('observed_value')}"
                for g in cur_x2
                if not g.get("pass")
            ]
            x1d_fail_msgs = [
                f"{j.get('provider_key')}(score={j.get('score')}): {f}"
                for j in cur_x1d
                if not j.get("advisory_only") and not bool(j.get("pass", True))
                for f in (j.get("findings") or [])
            ]
            critique = "; ".join((x2_fail_msgs + x1d_fail_msgs)[:6]) or "Ground every claim strictly in ALLOWED_SOURCE_FACT_IDS."
            rw_receipt["critique"] = critique
            rw_receipt["attempts_used"] = _rw_attempt + 1
            if cfg.is_bullet_lane:
                shape_note = (
                    f"Rewrite all required bullets ({', '.join(REQUIRED_BULLET_IDS.get(sid, ()))}) as distinct proof-bearing achievements "
                    "citing only ALLOWED_SOURCE_FACT_IDS with within-section pairwise cosine <= 0.35 and zero targeting-only buzzwords."
                )
            else:
                comp_blob = " ".join(companion_text) if isinstance(companion_text, list) else str(companion_text or "")
                narr_cur = str(l2.get("narrative_sentence") or cur_draft_raw)
                comp_words = set(re.findall(r"[a-z]{4,}", comp_blob.lower()))
                narr_words = set(re.findall(r"[a-z]{4,}", narr_cur.lower()))
                stop_ok = {"with", "from", "into", "across", "that", "this", "over", "under", "through", "while", "using"}
                overlap_words = sorted((comp_words & narr_words) - stop_ok)[:18]
                overlap_hint = (
                    f" CRITICAL COSINE ECHO FIX: replace/avoid these exact companion-bullet words {overlap_words} and frame the higher-level organizational charter/mandate using fresh executive vocabulary."
                    if overlap_words
                    else ""
                )
                shape_note = (
                    "Rewrite narrative_sentence as one crisp active executive sentence (15 to 42 words, zero 'frontier AI' / 'partner-led deployments' / target-company employment claims, "
                    f"zero companion bullet metric replay, pairwise cosine <= 0.30 against companion bullets) citing only ALLOWED_SOURCE_FACT_IDS.{overlap_hint}"
                )
            rewrite_msgs = [
                *messages,
                {"role": "assistant", "content": cur_draft_raw},
                {
                    "role": "user",
                    "content": f"IN_LANE_REVISION (attempt {_rw_attempt + 1}): prior draft failed validation/judge review: [{critique}]. {shape_note} Return one compact JSON object only.",
                },
            ]
            rw_res = call_section_model_provider(
                str(args.provider),
                tag_reasoning_lane({**provider_payload, "messages": rewrite_msgs, "reasoning_effort": "low"}, sid),
                artifact_dir=artifact_dir,
                run_id=run_id,
            )
            if rw_res.runtime_generation_status == "REAL_LLM":
                import copy

                cand_raw = str(rw_res.raw_model_output or "")
                cand_parsed, cand_err = _parse_json_object(cand_raw)
                if isinstance(cand_parsed, dict):
                    cand_generation_meta = copy.deepcopy(generation_meta) if generation_meta else None
                    selection_path = artifact_dir / "bullet_pool_selection.json"
                    selection_snapshot = selection_path.read_bytes() if cfg.is_bullet_lane and selection_path.is_file() else None
                    rewrite_accepted = False
                    try:
                        if cfg.is_bullet_lane:
                            cand_norm = _normalize_role_episode_bullet_pool_parsed(
                                cand_parsed,
                                cfg=cfg,
                                allowed=allowed_fact_ids,
                                allow_prose_mutation=False,
                            )
                            cand_bullets, cand_rec = parent_attr("_materialize_bullet_generation", _materialize_bullet_generation)(
                                cfg=cfg, parsed=cand_norm, parse_error="", provider_runtime_generation_status="REAL_LLM",
                                facts=facts, allowed=allowed_fact_ids, graph_packet_digest=pool.proof_pool_digest,
                            )
                            if selection_snapshot is not None:
                                try:
                                    sel_doc = json.loads(selection_snapshot.decode("utf-8"))
                                    if isinstance(sel_doc, dict):
                                        cand_by_id = {
                                            str(b.get("bullet_id") or "").strip(): b
                                            for b in cand_bullets
                                            if isinstance(b, dict)
                                        }
                                        new_src_map = dict(sel_doc.get("source_path_by_slot") or {})
                                        new_selections = []
                                        for row in sel_doc.get("selections") or []:
                                            if isinstance(row, dict):
                                                nrow = dict(row)
                                                bid = str(nrow.get("bullet_id") or "").strip()
                                                if bid in cand_by_id:
                                                    cb = cand_by_id[bid]
                                                    nrow["bullet_text"] = cb.get("bullet_text", nrow.get("bullet_text"))
                                                    nrow["source_fact_ids"] = list(cb.get("source_fact_ids") or nrow.get("source_fact_ids") or [])
                                                    nrow["in_lane_rewrite_applied"] = True
                                                    new_src_map[bid] = "in_lane_rewrite"
                                                new_selections.append(nrow)
                                            else:
                                                new_selections.append(row)
                                        sel_doc["selections"] = new_selections
                                        sel_doc["source_path_by_slot"] = new_src_map
                                        sel_doc["in_lane_rewrite_applied"] = True
                                        parent_attr("write_json", write_json)(selection_path, sel_doc)
                                except (OSError, json.JSONDecodeError):
                                    pass
                            if cand_generation_meta:
                                prior_mode = str(cand_generation_meta.get("selection_mode") or "sc")
                                if not prior_mode.endswith("_in_lane_rewrite"):
                                    cand_generation_meta["selection_mode"] = f"{prior_mode}_in_lane_rewrite"
                                cand_generation_meta["in_lane_rewrite_applied"] = True
                                src_map = dict(cand_generation_meta.get("source_path_by_slot") or {})
                                for b in cand_bullets:
                                    if isinstance(b, dict) and b.get("bullet_id"):
                                        src_map[str(b["bullet_id"])] = "in_lane_rewrite"
                                cand_generation_meta["source_path_by_slot"] = src_map
                                parent_attr("_reconcile_final_materialized_selection_gate", _reconcile_final_materialized_selection_gate)(
                                    artifact_dir=artifact_dir, section_id=sid, bullets=cand_bullets, generation_meta=cand_generation_meta,
                                )
                                cand_rec.update({
                                    "generation_mode": cand_generation_meta.get("generation_mode"),
                                    "initial_path_count": cand_generation_meta.get("initial_path_count"),
                                    "total_paths_executed": cand_generation_meta.get("total_paths_executed"),
                                    "regen_rounds_executed": cand_generation_meta.get("regen_rounds_executed"),
                                    "selection_gate": cand_generation_meta.get("selection_gate"),
                                    "producer_selection_gate": cand_generation_meta.get("producer_selection_gate"),
                                    "final_materialized_selection_gate": cand_generation_meta.get("final_materialized_selection_gate"),
                                    "selection_mode": cand_generation_meta.get("selection_mode"),
                                    "source_path_by_slot": cand_generation_meta.get("source_path_by_slot"),
                                })
                            cand_ledger = _claim_ledger_from_bullets(cand_bullets)
                            cand_l2 = {
                                "run_id": run_id, "section_id": sid, "runtime_generation_status": "REAL_LLM",
                                "product_quality_status": "PENDING", cfg.header_key: header, "bullets": cand_bullets,
                                "selected_fact_plan": selected_fact_plan, "claim_ledger": cand_ledger,
                                "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
                                "prompt_hash": prompt_hash[:16], **cand_rec,
                            }
                            if cand_generation_meta:
                                cand_l2["generation_meta"] = cand_generation_meta
                            cand_l2["generation_receipt"] = dict(cand_rec)
                        else:
                            cand_nf = _narrative_from_parsed(cand_parsed, allow_prose_mutation=False)
                            cand_narr, cand_sids, cand_sel_src, cand_msu = _proof_authorized_narrative_from_selection(
                                parsed=cand_parsed,
                                facts=facts,
                                allowed=allowed_fact_ids,
                                section_id=sid,
                                companion_bullet_texts=companion_text,
                                allow_prose_mutation=False,
                            )
                            cand_pl_sids = _parsed_claim_ledger_source_ids_for_narrative(
                                parsed=cand_parsed, narrative=cand_narr, allowed=allowed_fact_ids,
                            )
                            cand_raw_sids = cand_sids or cand_parsed.get("source_fact_ids") or cand_pl_sids
                            cand_sids, cand_repairs = _narrative_source_ids_for_claim(
                                narrative=cand_narr, raw_source_ids=cand_raw_sids, allowed=allowed_fact_ids, selected_fact_plan=selected_fact_plan,
                            )
                            for fid in cand_pl_sids:
                                if fid not in cand_sids:
                                    cand_sids.append(fid)
                                    cand_repairs.append(fid)
                            cand_ledger = [{"claim_text": cand_narr, "source_fact_ids": cand_sids}] if cand_narr else []
                            cand_rec = {
                                "generation_method": "llm_selected_graph_bound_surface" if cand_msu else "llm_selected_proof_render",
                                "llm_generation_status": "usable_output" if cand_nf else "invalid_output",
                                "llm_output_used": bool(cand_msu),
                                "llm_selection_used": bool(cand_nf and cand_narr),
                                "model_display_text_discarded": bool(cand_nf and not cand_msu),
                                "display_text_authority": "model_selected_graph_bound_surface" if cand_msu else "selected_fact_plan_claim_text",
                                "selection_source": cand_sel_src,
                                "evidence_authority": "augmented_skills_graph",
                                "source_fact_ids": cand_sids if cand_narr else [],
                                "graph_packet_digest": str(pool.proof_pool_digest or ""),
                                "renderer_version": "model_selected_graph_bound_surface.v1" if cand_msu else ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION,
                                "lane_contract_allows_deterministic_graph_render": False,
                                "allowed_graph_packet_fact_count": len(allowed_fact_ids),
                                "rendered_source_fact_ids_within_allowed_packet": set(cand_sids).issubset(set(allowed_fact_ids)),
                            }
                            cand_l2 = {
                                "run_id": run_id, "section_id": sid, "runtime_generation_status": "REAL_LLM",
                                "product_quality_status": "PENDING", cfg.header_key: header, "narrative_sentence": cand_narr,
                                "selected_fact_plan": selected_fact_plan, "claim_ledger": cand_ledger,
                                "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
                                "prompt_hash": prompt_hash[:16], **cand_rec,
                            }
                            if companion_text:
                                cand_l2["companion_bullet_texts"] = companion_text
                            cand_l2["generation_receipt"] = dict(cand_rec)
                            cand_norm = cand_parsed

                        cand_l2["role_episode_bundle_consumed"] = bundle_consumed
                        cand_l2["target_company"] = str(runtime_payload.get("target_company") or "")
                        cand_l2["target_title"] = str(runtime_payload.get("target_title") or "")
                        cand_x2 = parent_attr("run_role_episode_x2_gates", run_role_episode_x2_gates)(
                            section_id=sid, l2=cand_l2, allowed=allowed_fact_ids, runtime_generation_status="REAL_LLM",
                        )
                        if all(g.get("pass") for g in cand_x2):
                            cand_l2["product_quality_status"] = "PASS"
                            cand_l2["product_quality_reason"] = "x2_pass"
                            cand_rec["lane_status"] = "PASS"
                            cand_l2["lane_status"] = "PASS"
                            cand_l2["generation_receipt"] = dict(cand_rec)
                            cand_x1d = parent_attr("_judge_rows", _judge_rows)(
                                cfg=cfg, provider_result=rw_res, x2_gates=cand_x2, l2=cand_l2,
                                allowed_fact_ids=allowed_fact_ids, mock_judges=mock_judges_flag,
                                artifact_dir=artifact_dir, generation_meta=cand_generation_meta,
                                runtime_payload=runtime_payload, product_quality_status="PASS",
                            )
                            old_proof = [j for j in x1d if not j.get("advisory_only")]
                            new_proof = [j for j in cand_x1d if not j.get("advisory_only")]
                            old_rank = (sum(1 for j in old_proof if j.get("pass")), min((float(j.get("score") or 0.0) for j in old_proof), default=0.0))
                            new_rank = (sum(1 for j in new_proof if j.get("pass")), min((float(j.get("score") or 0.0) for j in new_proof), default=0.0))
                            rw_receipt["old_rank"] = list(old_rank)
                            rw_receipt["new_rank"] = list(new_rank)
                            if product_quality_status != "PASS" or new_rank > old_rank:
                                rewrite_accepted = True
                                provider_result = rw_res
                                raw_output = cand_raw
                                parsed, parse_error = cand_norm, cand_err
                                claim_ledger = cand_ledger
                                generation_receipt = cand_rec
                                generation_meta = cand_generation_meta
                                l2 = cand_l2
                                x2 = cand_x2
                                x1d = cand_x1d
                                product_quality_status = "PASS"
                                lane_status = "PASS"
                                if selection_snapshot is not None:
                                    (artifact_dir / "bullet_pool_selection_pre_rewrite.json").write_bytes(selection_snapshot)
                                resp_doc = provider_result.to_dict()
                                if generation_meta:
                                    resp_doc["generation_meta"] = generation_meta
                                parent_attr("write_json", write_json)(artifact_dir / "provider_response.json", resp_doc)
                                rw_receipt["accepted"] = True
                            else:
                                rw_receipt["rejected_reason"] = "rejudge_not_improved"
                        else:
                            rw_receipt["rejected_reason"] = f"x2_failed_after_rewrite:{[g.get('gate_id') for g in cand_x2 if not g.get('pass')]}"
                            cur_draft_raw = cand_raw
                            cur_x2 = cand_x2
                    finally:
                        if not rewrite_accepted and selection_snapshot is not None:
                            selection_path.write_bytes(selection_snapshot)
                    if rewrite_accepted and all(bool(j.get("pass", True)) for j in x1d if not j.get("advisory_only")):
                        break
                    if rewrite_accepted:
                        cur_draft_raw = raw_output or ""
                        cur_x2 = x2
                        cur_x1d = x1d
            else:
                break
        parent_attr("write_json", write_json)(artifact_dir / "role_episode_judge_rewrite_receipt.json", rw_receipt)
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
