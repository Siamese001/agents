"""Stage 4b: Post-X3 proof bundle, L6 shadow eval, receipts, and terminal result."""
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


def run_closeout_post_x3(ctx: dict[str, Any]) -> dict[str, Any]:
    """Emit proof bundles, L6 shadow packages, and return terminal lane dict."""
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    proof_pool_metadata = ctx["proof_pool_metadata"]
    messages = ctx["messages"]
    token_budget_receipt = ctx["token_budget_receipt"]
    token_budget_block_reason = ctx["token_budget_block_reason"]
    pool = ctx["pool"]
    base_path = ctx["base_path"]
    base_hash = ctx["base_hash"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    section_compiled = ctx["section_compiled"]
    compiled_prompt = ctx["compiled_prompt"]
    input_payload_hash = ctx["input_payload_hash"]
    prompt_hash = ctx["prompt_hash"]
    provider_request_data = ctx["provider_request_data"]
    provider_result_data = ctx["provider_result_data"]
    provider_resolution_source = ctx["provider_resolution_source"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    parse_error = ctx["parse_error"]
    parse_status = ctx["parse_status"]
    canon_doc = ctx["canon_doc"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    coverage = ctx["coverage"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    model_name = ctx["model_name"]
    temperature = ctx["temperature"]
    l2_output = ctx["l2_output"]
    x1d = ctx["x1d"]
    x2 = ctx["x2"]
    x3 = ctx["x3"]
    trace = ctx["trace"]
    product_quality_status = ctx["product_quality_status"]
    product_quality_reason = ctx["product_quality_reason"]
    _pub_disp = ctx["_pub_disp"]
    _wg = ctx["_wg"]

    from apps_rg.runtime.sections.executive_summary_publish_disposition import (
        apply_publish_disposition_to_proof_bundle,
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
    _lane_attr("write_json", write_json)(artifact_dir / "l2_output.json", l2_output)
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
    _lane_attr("write_json", write_json)(artifact_dir / "l6_shadow_eval_package.json", l6)
    post_rt = artifact_dir / "post_runtime"
    _wg.ensure_dir(post_rt)
    _lane_attr("write_json", write_json)(post_rt / "l6_shadow_eval_package.json", l6)
    l6_learn = build_l6_shadow_learning_record(
        artifact_dir=artifact_dir,
        repo_root=REPO_ROOT,
        section_id="executive_summary",
        lane_key=LANE_KEY,
    )
    _lane_attr("write_json", write_json)(artifact_dir / "l6_shadow_learning.json", l6_learn)
    _lane_attr("write_json", write_json)(post_rt / "l6_shadow_learning.json", l6_learn)
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
    _lane_attr("write_json", write_json)(artifact_dir / "real_l2_generation_result.json", real_result)
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
    _lane_attr("write_json", write_json)(artifact_dir / "section_metric_receipt.json", _smr_es)
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
    _lane_attr("_finalize_executive_summary_l7_binding", _finalize_executive_summary_l7_binding)(artifact_dir, runtime_payload)
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
