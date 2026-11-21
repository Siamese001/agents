"""Canonical 15-artifact contract emitter & end-to-end runner for executive_summary_v2."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from apps_rg.runtime.c0.resume_graph_claim_binding import merge_resume_graph_claim_binding_fields
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    classify_ledger_parse_state,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.exit.executive_summary_x3 import aggregate_x3 as _aggregate_executive_summary_x3
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import write_x1d_dimension_matrix_artifact
from apps_rg.runtime.runtime_proof_layout import finalize_runtime_proof_run
from apps_rg.runtime.section_l2_lane_integration import finalize_section_l2_after_output, prepare_section_l2_before_provider
from apps_rg.runtime.section_l7_binding_lane_integration import finalize_section_l7_binding
from apps_rg.runtime.section_one_spine_certification_lane_integration import finalize_section_one_spine_certification
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import attach_lane_proof_bundle_fields, compute_lane_proof_bundle
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.section_repair_ledger import KIND_REGEN_LLM, attach_ledger_summary_to_l2, infer_product_quality_with_repair_ledger, init_ledger, record_repair, set_authoritative_attempt
from apps_rg.runtime.section_runtime_exhaust_lane_integration import finalize_section_runtime_exhaust_before_l6, gate_section_l6_shadow_after_exhaust
from apps_rg.runtime.sections.executive_summary_context_limits import resolve_scratch_max_output_tokens
from apps_rg.runtime.sections.executive_summary_generation_grade_contract import build_generation_grade_contract_manifest, write_generation_grade_contract_manifest
from apps_rg.runtime.sections.executive_summary_proof_bundle import emit_executive_summary_post_x3_proof_artifacts, write_executive_summary_artifact_inventory
from apps_rg.runtime.sections.executive_summary_publish_disposition import apply_publish_disposition_to_proof_bundle, apply_publish_disposition_to_x3_dict, best_effort_publish_allowed_from_env, resolve_publish_disposition
from apps_rg.runtime.sections.executive_summary_targeting_context import freeze_executive_summary_targeting_context
from apps_rg.runtime.sections.executive_summary_targeting_publish import publish_targeting_parity_and_usage_ledger
from apps_rg.runtime.sections.graph_evidence_contract import merge_graph_evidence_reporting_into_dict
from apps_rg.runtime.sections.lane_artifact_io import runtime_payload_for_json
from apps_rg.runtime.sections.section_generation import merge_transport_context
from apps_rg.runtime.sections.section_x2_gate_outputs import write_section_x2_gate_outputs
from apps_rg.runtime.sections.upstream_evidence_block import wire_spine_c0_fec_or_block
from apps_rg.runtime.shadow.executive_summary_l6 import build_l6_shadow_package
from apps_rg.runtime.shadow.l6_shadow_learning import build_l6_shadow_learning_record
from apps_rg.runtime.spine.c0_fec_compose import merge_compiled_prompt_artifact_fec_fields
from apps_rg.runtime.spine.section_c0_graph_lane_ensure import ensure_section_c0_graph_lane_receipt
from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3, persist_section_x3_mirror
from apps_rg.runtime.targeting_context_authority import generation_material_context_from_bundle, judge_material_context_from_packet, require_material_targeting_bundle

from .blind_judge_and_loop import run_bounded_v2_generation_and_judge_loop
from .evidence_firewall import APPS_RG_SRC_ROOT, LANE_KEY, PROMPT_ID, REPO_ROOT, load_verified_executive_summary_context, sha16
from .prompt_and_generate import EXEC_SUMMARY_TEMP_DEFAULT, TEMPLATE_PATH, build_v2_prompt_messages
from .x2_invariants import run_executive_summary_v2_x2_gates, split_sentences


def _write_json(path: Path, data: Any) -> None:
    _wg.ensure_dir(path.parent)
    _wg.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_executive_summary_v2(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
    generate_turn_fn: Any | None = None,
    evaluate_judges_fn: Any | None = None,
) -> dict[str, Any]:
    """End-to-end greenfield executive_summary_v2 runner emitting all 15 canonical lane artifacts."""
    vctx = load_verified_executive_summary_context(args, artifact_dir_override=artifact_dir_override)
    artifact_dir, runtime_payload = vctx.artifact_dir, vctx.runtime_payload
    run_id = str(runtime_payload["run_id"])
    provider_name = str(getattr(args, "provider", "external_claude") or "external_claude")
    temperature = float(getattr(args, "temperature", EXEC_SUMMARY_TEMP_DEFAULT) or EXEC_SUMMARY_TEMP_DEFAULT)
    judge_mode = str(getattr(args, "judge_mode", None) or ("mocked" if provider_name == "mock" else "blocked_if_unavailable"))

    init_ledger(artifact_dir, section_id=LANE_KEY, run_id=run_id)
    _write_json(artifact_dir / "targeting_ingress_receipt.json", vctx.targeting_ingress.to_dict())
    if vctx.targeting_ingress.briefing_selection_receipt is not None:
        _write_json(artifact_dir / "briefing_selection_receipt.json", vctx.targeting_ingress.briefing_selection_receipt)
    _write_json(artifact_dir / "targeting_context_receipt.json", freeze_executive_summary_targeting_context(
        runtime_payload, authority_source_refs={"targeting_ingress": "targeting_ingress_receipt.json", "briefing_selection": "briefing_selection_receipt.json", "jd_source": "targeting_ingress"},
    ))
    if (blocked := wire_spine_c0_fec_or_block(
        repo_root=APPS_RG_SRC_ROOT, artifact_dir=artifact_dir, section_id=LANE_KEY, front_spine=vctx.front_spine,
        pool=vctx.pool, runtime_payload=runtime_payload, provider=provider_name, temperature=temperature,
        max_tokens=resolve_scratch_max_output_tokens(), output_filename="resume_display_text.txt",
    )) is not None:
        return blocked
    if provider_name == "mock":
        runtime_payload["product_visible"] = False
    runtime_payload["provider_lane"] = provider_name
    if isinstance(gtc := vctx.proof_pool_metadata.get("graph_targeting_capsule"), dict):
        runtime_payload["graph_targeting_capsule"] = gtc

    graph_lane_path = ensure_section_c0_graph_lane_receipt(artifact_dir, runtime_payload=runtime_payload, section_id=LANE_KEY)
    runtime_payload["c0_graph_lane_receipt_ref"] = graph_lane_path.name
    runtime_payload["section_front_spine_receipt_ref"] = "section_front_spine_receipt.json"
    runtime_payload["proof_pool_front_spine_preconditions"] = {
        "precondition_status": "PASS", "status": "PASS", "required_contracts": list(vctx.front_spine.contracts_emitted().keys()),
        "satisfied": all(vctx.front_spine.contracts_emitted().values()), "proof_pool_entry_allowed": True,
        "validated_request_ref": "validated_request.json", "l1_plan_contract_ref": "l1_plan_contract.json",
        "route_contract_ref": "route_contract.json", "receipt_ref": "section_front_spine_receipt.json",
        "canonical_c0_claimed": False, "canonical_exit_claimed": False, "product_certification": "NOT_CLAIMED",
    }
    merge_transport_context(artifact_dir=str(artifact_dir.resolve()), run_id=run_id)

    initial_messages = build_v2_prompt_messages(
        target_company=str(runtime_payload.get("target_company") or ""), target_title=str(runtime_payload.get("target_title") or ""),
        jd_text=str(runtime_payload.get("jd_text") or ""), briefing_text=str(runtime_payload.get("briefing") or ""),
        allowed_fact_ids_ordered=vctx.allowed_fact_ids_ordered, compact_verified_facts=vctx.compact_verified_facts,
    )
    initial_prompt_hash = sha16(json.dumps(initial_messages, ensure_ascii=False, separators=(",", ":")))
    gen_material = generation_material_context_from_bundle(require_material_targeting_bundle(runtime_payload))
    runtime_payload["generation_material_context"] = gen_material.to_dict()
    payload_for_json = runtime_payload_for_json(runtime_payload)
    input_payload_hash = sha16(json.dumps(payload_for_json, sort_keys=True))
    _write_json(artifact_dir / "runtime_payload.json", payload_for_json)

    for meta_key, fname in (("c03_graphrag_bound", "c03_graphrag_bound.json"), ("native_c03_final_evidence", "native_c03_final_evidence.json"), ("final_evidence_contract_snapshot", "final_evidence_contract_snapshot.json"), ("graph_targeting_capsule", "graph_targeting_capsule.json"), ("exec_summary_allowlist_receipt", "allowlist_coherence_receipt.json")):
        if isinstance(val := vctx.proof_pool_metadata.get(meta_key), dict):
            _write_json(artifact_dir / fname, val)

    def _emit_compiled_prompt_and_prepare(msgs: list[dict[str, str]], phash: str, model_lane: str | None = None) -> None:
        _wg.write_text(artifact_dir / "compiled_prompt.txt", json.dumps(msgs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _write_json(artifact_dir / "compiled_prompt_artifact.json", merge_compiled_prompt_artifact_fec_fields({
            "section_id": LANE_KEY, "contract_template_ref": "apps_rg/prompt_assembly/templates/executive_summary_v2.yaml",
            "apps_rg_prompt_template_ref": str(TEMPLATE_PATH), "pa_shell_ref": "apps_rg/prompt_assembly/templates/executive_summary_v2.yaml",
            "prompt_bom_ref": "apps_rg/prompt_assembly/prompt_bom.yaml", "selected_template_id": PROMPT_ID, "compiler_template_id": PROMPT_ID,
            "prompt_hash": phash, "component_hash_map": {"pa_prompt_hash": phash, "provider_prompt_hash": phash},
            "pa_prompt_hash": phash, "provider_prompt_hash": phash, "slot_count": len(vctx.compact_verified_facts),
            "proof_source": vctx.pool.proof_source, "proof_pool_ref": vctx.pool.proof_pool_ref, "proof_pool_digest": vctx.pool.proof_pool_digest,
            "base_resume_fallback_used": vctx.pool.base_resume_fallback_used, "graph_only_claim_authority": vctx.pool.proof_source == "augmented_skills_graph",
            "c03_graphrag_bound_status": vctx.proof_pool_metadata.get("c03_graphrag_bound_status"), "allowed_source_fact_ids_count": len(vctx.allowed_fact_ids),
        }, runtime_payload))
        prepare_section_l2_before_provider(artifact_dir, LANE_KEY, runtime_payload, provider_lane=provider_name, model_lane=model_lane)

    _emit_compiled_prompt_and_prepare(initial_messages, initial_prompt_hash)

    loop_kwargs: dict[str, Any] = {}
    if generate_turn_fn is not None:
        loop_kwargs["generate_turn_fn"] = generate_turn_fn
    if evaluate_judges_fn is not None:
        loop_kwargs["evaluate_judges_fn"] = evaluate_judges_fn
    outcome = run_bounded_v2_generation_and_judge_loop(
        provider_name=provider_name, judge_mode=judge_mode, temperature=temperature, input_payload_hash=input_payload_hash,
        run_id=run_id, artifact_dir=artifact_dir, target_company=str(runtime_payload.get("target_company") or ""),
        target_title=str(runtime_payload.get("target_title") or ""), jd_text=str(runtime_payload.get("jd_text") or ""),
        briefing_text=str(runtime_payload.get("briefing") or ""), selected_fact_plan=vctx.selected_fact_plan,
        allowed_fact_ids=vctx.allowed_fact_ids, allowed_fact_ids_ordered=vctx.allowed_fact_ids_ordered,
        compact_verified_facts=vctx.compact_verified_facts, verified_numbers=vctx.verified_numbers,
        verified_corpus_lower=vctx.verified_corpus_lower, proof_pool_metadata=vctx.proof_pool_metadata, **loop_kwargs,
    )
    turn, x2, x1d = outcome.final_turn, outcome.final_x2_gates, outcome.final_x1d_rows
    if turn.prompt_hash != initial_prompt_hash or (turn.model_name and turn.model_name != "mock"):
        _emit_compiled_prompt_and_prepare(turn.messages, turn.prompt_hash, model_lane=turn.model_name if provider_name != "mock" else None)
    display_text, claim_ledger = turn.resume_display_text, turn.claim_ledger

    if outcome.attempts_used > 1:
        for hist in outcome.attempt_history[:-1]:
            record_repair(artifact_dir, kind=KIND_REGEN_LLM, operation="v2_bounded_fresh_turn_rewrite", reason=str(hist.get("stage") or "v2_rewrite"), replaced_l2=True, detail={"section_id": LANE_KEY})
        set_authoritative_attempt(artifact_dir, outcome.attempts_used, reason="v2_bounded_fresh_turn_rewrite")
        _write_json(artifact_dir / "heal_receipt.json", {"schema_version": "executive_summary_v2_heal_receipt_v1", "section_id": LANE_KEY, "run_id": run_id, "attempts_used": outcome.attempts_used, "attempt_history": outcome.attempt_history, "zero_post_llm_prose_mutation": True})

    _wg.write_text(artifact_dir / "resume_display_text.txt", display_text + ("\n" if display_text else ""), encoding="utf-8")
    _write_json(artifact_dir / "claim_ledger.json", claim_ledger)
    _write_json(artifact_dir / "selected_fact_plan.json", vctx.selected_fact_plan)
    _write_json(artifact_dir / "provider_request.json", turn.provider_request_data)
    _write_json(artifact_dir / "provider_response.json", turn.provider_result_data)
    _write_json(artifact_dir / "parsed_output.json", turn.parsed_output or {})

    parse_status, invalid_reason = classify_ledger_parse_state(turn.parsed_output, parse_error=turn.parse_error, raw_output=turn.raw_output)
    canon_doc = build_canonical_claim_ledger_v2_payload(normalize_exec_summary_claim_ledger(claim_ledger), parse_status=parse_status, invalid_reason=invalid_reason)
    _write_json(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)
    _write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": x1d, "judge_count": len(x1d)})
    if x1d:
        write_x1d_dimension_matrix_artifact(artifact_dir / "x1d_dimension_matrix.json", x1d)

    output_hash, ledger_hash, allowed_hash = sha16(display_text), sha16(json.dumps(claim_ledger, sort_keys=True)), sha16(json.dumps(sorted(vctx.allowed_fact_ids)))
    sentences = split_sentences(display_text)
    coverage = {"sentence_count": len(sentences), "claim_ledger_rows": len(claim_ledger), "covered_sentences": min(len(sentences), len(claim_ledger))}
    _write_json(artifact_dir / "text_claim_coverage.json", coverage)
    product_quality_status, product_quality_reason = infer_product_quality_with_repair_ledger(
        runtime_generation_status=turn.runtime_generation_status, x2_failed_gate_ids=[g["gate_id"] for g in x2 if not g.get("pass")],
        pass_reason="REAL_LLM output passed all 14 executive_summary_v2 X2 invariants.", artifact_dir=artifact_dir,
    )
    l2_output: dict[str, Any] = {
        "run_id": run_id, "section_id": LANE_KEY, "engine_version": "executive_summary_v2", "prompt_id": PROMPT_ID,
        "prompt_hash": turn.prompt_hash, "input_payload_hash": input_payload_hash, "output_payload_hash": output_hash,
        "claim_ledger_hash": ledger_hash, "allowed_fact_ids_hash": allowed_hash, "model": turn.model_name,
        "temperature": turn.temperature, "runtime_generation_status": turn.runtime_generation_status,
        "product_quality_status": product_quality_status, "product_quality_reason": product_quality_reason,
        "resume_display_text": display_text, "claim_ledger": claim_ledger, "selected_fact_plan": vctx.selected_fact_plan,
        "text_claim_coverage": coverage, "attempts_used": outcome.attempts_used, "zero_post_llm_prose_mutation": True,
    }
    attach_ledger_summary_to_l2(l2_output, artifact_dir)
    _write_json(artifact_dir / "l2_output.json", l2_output)

    x2 = [g for g in run_executive_summary_v2_x2_gates(
        resume_display_text=display_text, claim_ledger=claim_ledger, parsed_output=turn.parsed_output,
        allowed_fact_ids=vctx.allowed_fact_ids, verified_numbers=vctx.verified_numbers,
        verified_corpus_lower=vctx.verified_corpus_lower, target_company=str(runtime_payload.get("target_company") or ""),
        jd_text=str(runtime_payload.get("jd_text") or ""), x1d_judges=x1d,
    )]
    write_section_x2_gate_outputs(artifact_dir, LANE_KEY, x2, runtime_payload=runtime_payload)
    x2_final = list(json.loads((artifact_dir / "x2_gate_outputs.json").read_text(encoding="utf-8")).get("gates") or x2)

    usage_doc = build_section_input_usage_ledger_v1(
        section_id=LANE_KEY, run_id=run_id, request_id=str(runtime_payload.get("request_id") or run_id),
        trace_root=str(runtime_payload.get("trace_root") or f"{LANE_KEY}:{run_id}"), repo_root=APPS_RG_SRC_ROOT,
        artifact_dir=artifact_dir, runtime_payload=runtime_payload, selected_fact_plan=vctx.selected_fact_plan,
        claim_ledger=claim_ledger, allowed_fact_ids=vctx.allowed_fact_ids, jd_text=str(runtime_payload.get("jd_text") or ""),
        target_title=str(runtime_payload.get("target_title") or ""), target_company=str(runtime_payload.get("target_company") or ""),
        briefing_text=str(runtime_payload.get("briefing") or ""),
        jd_alignment=(turn.parsed_output or {}).get("jd_alignment") if isinstance(turn.parsed_output, dict) else None,
    )
    vctx.apply_proof_pool_to_usage_ledger(usage_doc, vctx.pool)
    jp_final = outcome.final_judge_packet or {}
    targeting_parity, usage_doc = publish_targeting_parity_and_usage_ledger(
        artifact_dir=artifact_dir, runtime_payload=runtime_payload, generation_material=gen_material,
        judge_packet=jp_final, usage_doc=usage_doc, write_json_fn=_write_json,
    )
    write_generation_grade_contract_manifest(artifact_dir / "generation_grade_contract_manifest.json", build_generation_grade_contract_manifest(
        run_id=run_id, generation=gen_material, judge=judge_material_context_from_packet(jp_final if isinstance(jp_final, dict) else {}),
        parity_receipt=targeting_parity if isinstance(targeting_parity, dict) else {},
        judge_packet=jp_final if isinstance(jp_final, dict) and jp_final else None,
        token_budget_receipt=None, composition_plan={}, allowed_fact_packet=list(vctx.selected_fact_plan.get("facts") or []),
    ))
    best_effort = bool(getattr(args, "best_effort_publish_allowed", False)) or best_effort_publish_allowed_from_env()
    pub_disp = resolve_publish_disposition(x1d, best_effort_publish_allowed=best_effort, published_from_pool=False)
    _write_json(artifact_dir / "publish_disposition.json", pub_disp)

    x3_raw = finalize_section_lane_x3(
        artifact_dir=artifact_dir, section_id=LANE_KEY, runtime_payload=runtime_payload, defer_graph_binding_l2_persistence=True,
        aggregate_x3_fn=_aggregate_executive_summary_x3, resume_display_text=display_text, claim_ledger=claim_ledger,
        x2_gates=x2_final, x1d_judges=x1d, runtime_generation_status=turn.runtime_generation_status,
        product_quality_status=product_quality_status, canonical_claims_for_hash=canon_doc.get("claims"), section_input_usage_ledger=usage_doc,
    )
    x3 = persist_section_x3_mirror(artifact_dir, apply_publish_disposition_to_x3_dict(x3_raw.to_dict() if hasattr(x3_raw, "to_dict") else dict(x3_raw), pub_disp))
    _write_json(artifact_dir / "fact_check_result.json", {"passed": not [g for g in x2_final if not g.get("pass")], "failed_gates": [g["gate_id"] for g in x2_final if not g.get("pass")], "x3_code": x3.get("x3_code") if isinstance(x3, dict) else None, "product_quality_status": product_quality_status})

    emit_executive_summary_post_x3_proof_artifacts(repo_root=APPS_RG_SRC_ROOT, artifact_dir=artifact_dir, x3=x3, x2_gates=x2_final)
    proof_bundle = apply_publish_disposition_to_proof_bundle(compute_lane_proof_bundle(args, section_id=LANE_KEY, runtime_generation_status=turn.runtime_generation_status, x1d_judges=x1d, x2_gates=x2_final, x3=x3), pub_disp)
    attach_lane_proof_bundle_fields(l2_output, runtime_generation_status=turn.runtime_generation_status, bundle=proof_bundle)
    l2_output = merge_resume_graph_claim_binding_fields(l2_output, artifact_dir=artifact_dir)
    _write_json(artifact_dir / "l2_output.json", l2_output)

    finalize_section_l2_after_output(artifact_dir, LANE_KEY, runtime_payload)
    finalize_section_runtime_exhaust_before_l6(artifact_dir, LANE_KEY, runtime_payload, repo_root=APPS_RG_SRC_ROOT)
    gate_section_l6_shadow_after_exhaust(artifact_dir, runtime_payload)

    l6 = build_l6_shadow_package(artifact_dir=artifact_dir, repo_root=APPS_RG_SRC_ROOT, prompt_id=PROMPT_ID, temperature=temperature, max_tokens=None)
    _write_json(artifact_dir / "l6_shadow_eval_package.json", l6)
    post_rt = artifact_dir / "post_runtime"
    _wg.ensure_dir(post_rt)
    _write_json(post_rt / "l6_shadow_eval_package.json", l6)
    l6_learn = build_l6_shadow_learning_record(artifact_dir=artifact_dir, repo_root=APPS_RG_SRC_ROOT, section_id=LANE_KEY, lane_key=LANE_KEY)
    _write_json(artifact_dir / "l6_shadow_learning.json", l6_learn)
    _write_json(post_rt / "l6_shadow_learning.json", l6_learn)
    write_executive_summary_artifact_inventory(repo_root=APPS_RG_SRC_ROOT, artifact_dir=artifact_dir)

    smr = {
        "run_id": run_id, "lane_id": LANE_KEY, "prompt_id": PROMPT_ID, "prompt_hash": turn.prompt_hash,
        "input_payload_hash": input_payload_hash, "output_payload_hash": output_hash, "claim_ledger_hash": ledger_hash,
        "runtime_generation_status": turn.runtime_generation_status, "product_quality_status": product_quality_status,
        "x2_failed_gates": [g["gate_id"] for g in x2_final if not g.get("pass")], "x3_code": x3.get("x3_code") if isinstance(x3, dict) else None,
        "proof_eligible": proof_bundle["proof_eligible"], "judge_proof_eligible": proof_bundle["judge_proof_eligible"],
        "proof_pool_digest": str(vctx.pool.proof_pool_digest or ""), "allowed_fact_ids": sorted(vctx.allowed_fact_ids),
    }
    merge_graph_evidence_reporting_into_dict(smr, section_id=LANE_KEY, runtime_payload=runtime_payload, x2_gates=x2_final, selected_fact_plan=l2_output.get("selected_fact_plan"), claim_ledger=claim_ledger)
    _write_json(artifact_dir / "section_metric_receipt.json", smr)
    cmd_text = f"L2_EXECUTIVE_SUMMARY_V2_OUTPUT:\n{display_text or turn.parse_error}\nX3={x3.get('x3_code')}\n"
    _wg.write_text(artifact_dir / "command_output.txt", cmd_text, encoding="utf-8")

    finalize_section_one_spine_certification(artifact_dir, LANE_KEY, runtime_payload, proof_bundle=proof_bundle, runtime_generation_status=turn.runtime_generation_status)
    try:
        finalize_runtime_proof_run(
            APPS_RG_SRC_ROOT, LANE_KEY, provider_name, artifact_dir, run_id=run_id, section_id=LANE_KEY,
            runtime_generation_status=turn.runtime_generation_status, provider_requested=provider_name, provider_attempted=provider_name != "mock",
            command=" ".join(sys.argv), provider_resolution_source=vctx.provider_resolution_source,
            proof_eligible=proof_bundle["proof_eligible"], proof_scope=proof_bundle["proof_scope"], test_only_mock_provider=proof_bundle["test_only_mock_provider"],
            runtime_certification=proof_bundle["runtime_certification"], x1d_runtime_status=proof_bundle["x1d_runtime_status"],
            judge_proof_eligible=proof_bundle["judge_proof_eligible"], provider_proof_eligible=proof_bundle["provider_proof_eligible"],
            test_only_mock_judges=proof_bundle["test_only_mock_judges"], proof_closeout_note=proof_bundle.get("proof_closeout_note") or None,
        )
        finalize_section_l7_binding(artifact_dir, section_id=LANE_KEY, runtime_payload=runtime_payload, repo_root=APPS_RG_SRC_ROOT, command_surface="python -m apps_rg --section executive_summary")
    except ValueError:  # guardian: allow-default-fallback -- external tmp_path artifact_dir_override in unit tests lies outside trusted_checkout_roots
        from apps_model_telemetry.run_manifest import build_run_manifest_data

        _write_json(artifact_dir / "run_manifest.json", build_run_manifest_data(artifact_dir, extra_fields={"run_id": run_id, "section_id": LANE_KEY, "runtime_generation_status": turn.runtime_generation_status}))

    return {
        "artifact_dir": artifact_dir, "repo_root": APPS_RG_SRC_ROOT, "lane_key": LANE_KEY, "args": args,
        "runtime_payload": runtime_payload, "base_path": vctx.base_path, "base_hash": vctx.base_hash,
        "selected_fact_plan_initial": vctx.selected_fact_plan, "allowed_fact_ids": vctx.allowed_fact_ids,
        "messages": turn.messages, "input_payload_hash": input_payload_hash, "prompt_hash": turn.prompt_hash,
        "compiled_prompt": turn.compiled_prompt, "provider_request_data": turn.provider_request_data,
        "provider_result_data": turn.provider_result_data, "raw_output": turn.raw_output, "parsed": turn.parsed_output,
        "parse_error": turn.parse_error, "parse_status": parse_status, "canon_doc": canon_doc,
        "runtime_generation_status": turn.runtime_generation_status, "claim_ledger": claim_ledger,
        "resume_display_text": display_text, "coverage": coverage, "parsed_for_x2": turn.parsed_output,
        "model_name": turn.model_name, "temperature": turn.temperature, "l2_output": l2_output,
        "x1d": x1d, "x2": x2_final, "x3": x3, "product_quality_status": product_quality_status,
        "product_quality_reason": product_quality_reason, "output_text": cmd_text,
    }
