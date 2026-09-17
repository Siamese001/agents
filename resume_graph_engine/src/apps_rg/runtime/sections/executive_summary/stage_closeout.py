"""Stage 4: Post-repair validation, product quality inference, X3 aggregation, and return."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *

def run_closeout_stage(ctx: dict[str, Any]) -> dict[str, Any]:
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    proof_pool_metadata = ctx["proof_pool_metadata"]
    targeting_ingress = ctx["targeting_ingress"]
    messages = ctx["messages"]
    req = ctx["req"]
    scratch_max_tokens = ctx["scratch_max_tokens"]
    token_budget_receipt = ctx["token_budget_receipt"]
    usage_doc = ctx["usage_doc"]
    briefing_text_bounded = ctx["briefing_text_bounded"]
    pool = ctx["pool"]
    base_path = ctx["base_path"]
    base_hash = ctx["base_hash"]
    base = ctx["base"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    allowed_fact_ids_ordered = ctx["allowed_fact_ids_ordered"]
    result = ctx["result"]
    provider_result_data = ctx["provider_result_data"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    parse_error = ctx["parse_error"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    _word_budget_repair_accepted = ctx["_word_budget_repair_accepted"]
    _word_budget_repair_audit = ctx["_word_budget_repair_audit"]
    _composition_plan_early = ctx["_composition_plan_early"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    x2 = ctx["x2"]
    _generation_material = ctx["_generation_material"]
    _bundle_mat = ctx["_bundle_mat"]
    _targeting_parity = ctx["_targeting_parity"]
    x1d = ctx["x1d"]
    x2_failed_initial = ctx["x2_failed_initial"]
    judge_packet = ctx.get("judge_packet", {})
    judge_packet_ref = ctx.get("judge_packet_ref", "")
    _cycles_receipt = ctx.get("_cycles_receipt", {})

    _graph_only_repaired = False
    _repair_meta_path = artifact_dir / "graph_only_generation_quality_repair.json"
    if _repair_meta_path.is_file():
        try:
            _graph_only_repaired = bool(
                json.loads(_repair_meta_path.read_text(encoding="utf-8")).get("repaired")
            )
        except (json.JSONDecodeError, OSError):  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
            _graph_only_repaired = False

    product_quality_status, product_quality_reason = infer_product_quality(
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
    write_json(artifact_dir / "l2_output.json", l2_output)

    _jp_final = resolve_judge_packet_for_parity(artifact_dir, fallback=judge_packet)
    _targeting_parity, usage_doc = publish_targeting_parity_and_usage_ledger(
        artifact_dir=artifact_dir,
        runtime_payload=runtime_payload,
        generation_material=_generation_material,
        judge_packet=_jp_final,
        usage_doc=usage_doc,
        write_json_fn=write_json,
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
        published_from_pool=bool(locals().get("_pool_publish_applied")),
    )
    write_json(artifact_dir / "publish_disposition.json", _pub_disp)

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
    write_json(
        artifact_dir / "fact_check_result.json",
        {
            "passed": not [g for g in x2 if not g["pass"]],
            "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]],
            "x3_code": x3.get("x3_code") if isinstance(x3, dict) else None,
            "product_quality_status": product_quality_status,
        },
    )
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        merge_resume_graph_claim_binding_fields,
    )
    from apps_rg.runtime.section_l2_lane_integration import finalize_section_l2_after_output
    from apps_rg.runtime.section_runtime_exhaust_lane_integration import (
        finalize_section_runtime_exhaust_before_l6,
        gate_section_l6_shadow_after_exhaust,
    )
  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
    emit_executive_summary_post_x3_proof_artifacts(
        repo_root=REPO_ROOT,
        artifact_dir=artifact_dir,
        x3=x3,
        x2_gates=x2,
    )

    proof_bundle = compute_lane_proof_bundle(
        args,
        section_id="executive_summary",
        runtime_generation_status=runtime_generation_status,
        x1d_judges=x1d,
        x2_gates=x2,
        x3=x3,
    )
    proof_bundle = apply_publish_disposition_to_proof_bundle(proof_bundle, _pub_disp)
    attach_lane_proof_bundle_fields(
        l2_output,
        runtime_generation_status=runtime_generation_status,
        bundle=proof_bundle,
    )
    l2_output = merge_resume_graph_claim_binding_fields(
        l2_output,
        artifact_dir=artifact_dir,
    )
    write_json(artifact_dir / "l2_output.json", l2_output)
    finalize_section_l2_after_output(artifact_dir, "executive_summary", runtime_payload)
    finalize_section_runtime_exhaust_before_l6(
        artifact_dir, "executive_summary", runtime_payload, repo_root=REPO_ROOT
    )

    l6_temp = float(args.temperature)
    gate_section_l6_shadow_after_exhaust(artifact_dir, runtime_payload)
    l6 = build_l6_shadow_package(
        artifact_dir=artifact_dir,
        repo_root=REPO_ROOT,
        prompt_id=PROMPT_ID,
        temperature=l6_temp,
        max_tokens=None,
    )
    write_json(artifact_dir / "l6_shadow_eval_package.json", l6)
    post_rt = artifact_dir / "post_runtime"
    _wg.ensure_dir(post_rt)
    write_json(post_rt / "l6_shadow_eval_package.json", l6)
    l6_learn = build_l6_shadow_learning_record(
        artifact_dir=artifact_dir,
        repo_root=REPO_ROOT,
        section_id="executive_summary",
        lane_key=LANE_KEY,
    )
    write_json(artifact_dir / "l6_shadow_learning.json", l6_learn)
    write_json(post_rt / "l6_shadow_learning.json", l6_learn)
    write_executive_summary_artifact_inventory(repo_root=REPO_ROOT, artifact_dir=artifact_dir)
    real_result = {
        "provider_attempted": args.provider,
        "provider_available": bool(provider_result_data and provider_result_data.get("provider_available")),
        "exact_provider_error": (provider_result_data or {}).get("exact_provider_error"),
        "runtime_generation_status": runtime_generation_status,
        "prompt_id": PROMPT_ID,
        "prompt_hash": prompt_hash,
        "model": model_name,
        "temperature": temperature,
        "input_payload_hash": input_payload_hash,
        "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"),
        "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"),
        "allowed_fact_ids_hash": (parsed_for_x2 or {}).get("allowed_fact_ids_hash"),
        "raw_model_output": raw_output,
        "parsed_model_output": parsed_for_x2,
        "resume_display_text": resume_display_text,
        "selected_fact_plan": l2_output["selected_fact_plan"],
        "claim_ledger": claim_ledger,
        "text_claim_coverage": coverage,
        "fact_check_result": {"passed": not [g for g in x2 if not g["pass"]], "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]]},
        "product_quality_status": product_quality_status,
        "x3_disposition_ref": str(artifact_dir / "x3_disposition.json"),
        "l6_shadow_eval_package_ref": str(artifact_dir / "l6_shadow_eval_package.json"),
    }
    attach_lane_proof_bundle_fields(
        real_result,
        runtime_generation_status=runtime_generation_status,
        bundle=proof_bundle,
    )
    write_json(artifact_dir / "real_l2_generation_result.json", real_result)
    _allowlist_receipt = (
        proof_pool_metadata.get("exec_summary_allowlist_receipt")
        if isinstance(proof_pool_metadata, dict)
        else {}
    )
    _smr_es = {
        "run_id": runtime_payload["run_id"],
        "lane_id": "executive_summary",
        "prompt_id": PROMPT_ID,
        "prompt_hash": prompt_hash,
        "input_payload_hash": input_payload_hash,
        "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"),
        "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"),
        "runtime_generation_status": runtime_generation_status,
        "product_quality_status": product_quality_status,
        "x2_failed_gates": [
            (g.get("gate_id") if isinstance(g, dict) else getattr(g, "gate_id", ""))
            for g in x2
            if not (g.get("pass") if isinstance(g, dict) else getattr(g, "pass_", False))
        ],
        "x3_code": (x3.get("x3_code") if isinstance(x3, dict) else x3.x3_code),
        "proof_eligible": proof_bundle["proof_eligible"],
        "judge_proof_eligible": proof_bundle["judge_proof_eligible"],
        "proof_pool_digest": str(pool.proof_pool_digest or ""),
        "allowed_fact_ids": sorted(allowed_fact_ids),
        "c03_context_fact_ids": list(
            (_allowlist_receipt or {}).get("c03_context_fact_ids")
            or (proof_pool_metadata or {}).get("c03_context_fact_ids")
            or []
        ),
        "c03_filtered_out_fact_ids": list(
            (_allowlist_receipt or {}).get("c03_filtered_out_fact_ids")
            or (proof_pool_metadata or {}).get("c03_filtered_out_fact_ids")
            or []
        ),
        "promoted_fact_ids": list((_allowlist_receipt or {}).get("promoted_fact_ids") or []),
        "c03_promotion_candidates_ref": str(artifact_dir / "c03_promotion_candidates.json"),
        "graph_targeting_skill_ids": list(
            (_allowlist_receipt or {}).get("graph_targeting_skill_ids") or []
        ),
        "allowlist_mismatch": bool(
            (_allowlist_receipt or {}).get("allowlist_mismatch")
            or (proof_pool_metadata or {}).get("allowlist_mismatch")
        ),
        "native_c03_status": str((proof_pool_metadata or {}).get("native_c03_status") or ""),
        "c03_graphrag_bound_status": str((proof_pool_metadata or {}).get("c03_graphrag_bound_status") or ""),
        "c03_sqlite_attach_status": str((proof_pool_metadata or {}).get("c03_sqlite_attach_status") or ""),
        "canonical_c0_3_claimed": False,
    }
    merge_graph_evidence_reporting_into_dict(
        _smr_es,
        section_id="executive_summary",
        runtime_payload=runtime_payload,
        x2_gates=x2,
        selected_fact_plan=l2_output.get("selected_fact_plan") if isinstance(l2_output, dict) else None,
        claim_ledger=claim_ledger,
    )
    auth = _smr_es.get("evidence_authority")
    if isinstance(auth, dict) and isinstance(pp_meta := proof_pool_metadata, dict):
        digest = str(pp_meta.get("graph_digest") or auth.get("graph_digest") or "").strip()
        if digest:
            auth = dict(auth)
            auth["graph_digest"] = digest
            _smr_es["evidence_authority"] = auth
    write_json(artifact_dir / "section_metric_receipt.json", _smr_es)
    output_lines = []
    if token_budget_block_reason and isinstance(token_budget_receipt, dict):
        _tb_msg = str(token_budget_receipt.get("operator_message") or "").strip()
        if _tb_msg:
            output_lines.append("TOKEN_BUDGET_OPERATOR_GUIDANCE:")
            output_lines.extend(_tb_msg.splitlines())
            output_lines.append("")
    output_lines.append("L2_EXECUTIVE_SUMMARY_OUTPUT:")
    _tb_summary = (
        str(token_budget_receipt.get("operator_summary") or "").strip()
        if isinstance(token_budget_receipt, dict)
        else ""
    )
    if token_budget_block_reason and _tb_summary:
        output_lines.append(f"BLOCKED: {_tb_summary}")
    else:
        output_lines.append(resume_display_text if resume_display_text else f"BLOCKED: {parse_error}")
    output_lines.append("")
    output_lines.append("X1D_LLM_JUDGE_OUTPUTS:")
    output_lines.append("| Provider | Mode | Score | Threshold | Pass | Decisive Failure | Error |")
    output_lines.append("|---|---|---:|---:|---|---|---|")
    for judge in x1d:
        output_lines.append(
            f"| {judge['provider_name']} | {judge['evaluator_mode']} | {judge.get('score')} | {judge.get('threshold')} | {judge.get('pass')} | {judge.get('decisive_failure')} | {judge.get('exact_provider_error') or ''} |"
        )
    output_lines.append("")
    output_lines.append("X2_DETERMINISTIC_GATE_OUTPUTS:")
    for gate in x2:
        output_lines.append(f"- {gate['gate_id']}: {'PASS' if gate['pass'] else 'FAIL'}")
    output_lines.append("")
    output_lines.append("X3_DISPOSITION:")
    output_lines.append(
        json.dumps(x3 if isinstance(x3, dict) else x3.to_dict(), indent=2)
    )
    output_lines.append("")
    output_lines.append("L6_SHADOW_EVAL_PACKAGE:")
    output_lines.append(str(artifact_dir / "l6_shadow_eval_package.json"))
    output_lines.append("offline_only=true")
    output_text = "\n".join(output_lines)
    _wg.write_text(artifact_dir / "command_output.txt", output_text + "\n", encoding="utf-8")
    prq = str((provider_request_data or {}).get("provider_requested", args.provider))
    pratt = (provider_request_data or {}).get("provider_attempted", args.provider)
    from apps_rg.runtime.section_one_spine_certification_lane_integration import (
        finalize_section_one_spine_certification,
    )

    finalize_section_one_spine_certification(
        artifact_dir,
        "executive_summary",
        runtime_payload,
        proof_bundle=proof_bundle,
        runtime_generation_status=runtime_generation_status,
    )
    finalize_runtime_proof_run(
        REPO_ROOT,
        LANE_KEY,
        args.provider,
        artifact_dir,
        run_id=runtime_payload["run_id"],
        section_id="executive_summary",
        runtime_generation_status=runtime_generation_status,
        provider_requested=prq,
        provider_attempted=pratt,
        command=" ".join(sys.argv),
        provider_resolution_source=provider_resolution_source,
        proof_eligible=proof_bundle["proof_eligible"],
        proof_scope=proof_bundle["proof_scope"],
        test_only_mock_provider=proof_bundle["test_only_mock_provider"],
        runtime_certification=proof_bundle["runtime_certification"],
        x1d_runtime_status=proof_bundle["x1d_runtime_status"],
        judge_proof_eligible=proof_bundle["judge_proof_eligible"],
        provider_proof_eligible=proof_bundle["provider_proof_eligible"],
        test_only_mock_judges=proof_bundle["test_only_mock_judges"],
        proof_closeout_note=proof_bundle.get("proof_closeout_note") or None,
    )
    _finalize_executive_summary_l7_binding(artifact_dir, runtime_payload)
    return {
        "artifact_dir": artifact_dir,
        "repo_root": REPO_ROOT,
        "lane_key": LANE_KEY,
        "args": args,
        "runtime_payload": runtime_payload,
        "base_path": base_path,
        "base_hash": base_hash,
        "selected_fact_plan_initial": selected_fact_plan,
        "allowed_fact_ids": allowed_fact_ids,
        "section_compiled": section_compiled,
        "messages": messages,
        "input_payload_hash": input_payload_hash,
        "prompt_hash": prompt_hash,
        "compiled_prompt": compiled_prompt,
        "provider_request_data": provider_request_data,
        "provider_result_data": provider_result_data,
        "raw_output": raw_output,
        "parsed": parsed,
        "parse_error": parse_error,
        "parse_status": parse_status,
        "canon_doc": canon_doc,
        "runtime_generation_status": runtime_generation_status,
        "claim_ledger": claim_ledger,
        "resume_display_text": resume_display_text,
        "coverage": coverage,
        "parsed_for_x2": parsed_for_x2,
        "model_name": model_name,
        "temperature": temperature,
        "l2_output": l2_output,
        "x1d": x1d,
        "x2": x2,
        "x3": x3,
        "trace": trace,
        "product_quality_status": product_quality_status,
        "product_quality_reason": product_quality_reason,
        "provider_requested_resolved": prq,
        "provider_attempted_resolved": pratt,
        "output_text": output_text,
        "token_budget_operator_message": (
            str(token_budget_receipt.get("operator_message") or "").strip()
            if isinstance(token_budget_receipt, dict)
            else ""
        ),
    }

