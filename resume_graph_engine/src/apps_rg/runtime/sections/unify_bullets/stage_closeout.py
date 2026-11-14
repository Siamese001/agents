"""Stage 3: Unify bullets X3 aggregation, L2/L6 closeout, and artifact sealing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.exit.unify_bullets_x3 import aggregate_x3 as _aggregate_unify_bullets_x3
from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
    sanitize_l2_employment_bullet_record,
)
from apps_rg.runtime.runtime_proof_layout import finalize_runtime_proof_run, rel_posix
from apps_rg.runtime.section_l2_lane_integration import finalize_section_l2_after_output
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import (
    attach_lane_proof_bundle_fields,
    compute_lane_proof_bundle,
)
from apps_rg.runtime.section_runtime_exhaust_lane_integration import (
    finalize_section_runtime_exhaust_before_l6,
    gate_section_l6_shadow_after_exhaust,
)
from apps_rg.runtime.sections.graph_evidence_contract import merge_graph_evidence_reporting_into_dict
from apps_rg.runtime.shadow.unify_bullets_l6 import (
    build_l6_shadow_package,
    extend_unify_bullets_l6_learning_fields,
)
from ._parent import parent_attr
from .lane_constants import (
    LANE_KEY,
    PROMPT_ID,
    REPO_ROOT,
    UNIFY_MAX_OUTPUT_TOKENS,
    write_json,
)


def run_unify_closeout_stage(
    args: argparse.Namespace,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate X3, publish L2/exhaust/L6 receipts, seal proof run, and return payload."""
    artifact_dir: Path = ctx["artifact_dir"]
    base_path = ctx["base_path"]
    base_hash = ctx["base_hash"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    selected_fact_plan = ctx["selected_fact_plan"]
    runtime_payload = ctx["runtime_payload"]
    input_payload_hash = ctx["input_payload_hash"]
    section_compiled = ctx["section_compiled"]
    messages = ctx["messages"]
    compiled_prompt = ctx["compiled_prompt"]
    prompt_hash = ctx["prompt_hash"]
    provider_request_data = ctx["provider_request_data"]
    provider_result_data = ctx["provider_result_data"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    parse_error = ctx["parse_error"]
    parse_status = ctx["parse_status"]
    bullets = ctx["bullets"]
    claim_ledger = ctx["claim_ledger"]
    canon_doc = ctx["canon_doc"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    model_name = ctx["model_name"]
    l2_output = ctx["l2_output"]
    usage_doc = ctx["usage_doc"]
    x1d = ctx["x1d"]
    x2 = ctx["x2"]
    coverage = ctx["coverage"]
    display_for_coverage = ctx["display_for_coverage"]
    temperature = ctx["temperature"]
    trace = ctx["trace"]
    product_quality_status = ctx["product_quality_status"]
    product_quality_reason = ctx["product_quality_reason"]
    display_for_x3 = display_for_coverage
    x3 = parent_attr("_aggregate_unify_bullets_x3", _aggregate_unify_bullets_x3)(
        resume_display_text=display_for_x3,
        claim_ledger=claim_ledger,
        x2_gates=x2,
        x1d_judges=x1d,
        runtime_generation_status=runtime_generation_status,
        product_quality_status=product_quality_status,
        canonical_claims_for_hash=canon_doc.get("claims"),
        section_input_usage_ledger=usage_doc,
    )
    proof_bundle = parent_attr("compute_lane_proof_bundle", compute_lane_proof_bundle)(
        args,
        section_id="unify_bullets",
        runtime_generation_status=runtime_generation_status,
        x1d_judges=x1d,
        x2_gates=x2,
        x3=x3,
    )
    parent_attr("attach_lane_proof_bundle_fields", attach_lane_proof_bundle_fields)(
        l2_output,
        runtime_generation_status=runtime_generation_status,
        bundle=proof_bundle,
    )
    parent_attr("write_json", write_json)(artifact_dir / "l2_output.json", sanitize_l2_employment_bullet_record(l2_output))

    from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3

    x3 = finalize_section_lane_x3(
        artifact_dir=artifact_dir,
        section_id="unify_bullets",
        runtime_payload=runtime_payload,
        x3_result=x3,
        x3_doc_extra={
            "proof_eligible": proof_bundle["proof_eligible"],
            "judge_proof_eligible": proof_bundle["judge_proof_eligible"],
        },
    )
    parent_attr("finalize_section_l2_after_output", finalize_section_l2_after_output)(artifact_dir, "unify_bullets", runtime_payload)
    parent_attr("finalize_section_runtime_exhaust_before_l6", finalize_section_runtime_exhaust_before_l6)(
        artifact_dir, "unify_bullets", runtime_payload, repo_root=parent_attr("REPO_ROOT", REPO_ROOT)
    )

    l6_temp = float(args.temperature)
    l6_max = UNIFY_MAX_OUTPUT_TOKENS
    parent_attr("gate_section_l6_shadow_after_exhaust", gate_section_l6_shadow_after_exhaust)(artifact_dir, runtime_payload)
    l6_base = parent_attr("build_l6_shadow_package", build_l6_shadow_package)(
        artifact_dir=artifact_dir,
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        prompt_id=PROMPT_ID,
        temperature=l6_temp,
        max_tokens=l6_max,
    )
    l6 = parent_attr("extend_unify_bullets_l6_learning_fields", extend_unify_bullets_l6_learning_fields)(
        l6_base,
        artifact_dir=artifact_dir,
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        provider=str(args.provider),
        x2_gates=x2,
        x3_code=str(x3.x3_code),
        proof_bundle=proof_bundle,
    )
    parent_attr("write_json", write_json)(artifact_dir / "l6_shadow_eval_package.json", l6)

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
        "bullets": bullets,
        "claim_ledger": claim_ledger,
        "text_claim_coverage": coverage,
        "fact_check_result": {
            "passed": not [g for g in x2 if not g["pass"]],
            "failed_gates": [g["gate_id"] for g in x2 if not g["pass"]],
        },
        "product_quality_status": product_quality_status,
        "x3_disposition_ref": str(artifact_dir / "x3_disposition.json"),
        "l6_shadow_eval_package_ref": str(artifact_dir / "l6_shadow_eval_package.json"),
    }
    parent_attr("attach_lane_proof_bundle_fields", attach_lane_proof_bundle_fields)(
        real_result,
        runtime_generation_status=runtime_generation_status,
        bundle=proof_bundle,
    )
    parent_attr("write_json", write_json)(artifact_dir / "real_l2_generation_result.json", real_result)
    _smr_ub = {
        "run_id": runtime_payload["run_id"],
        "lane_id": "unify_bullets",
        "prompt_id": PROMPT_ID,
        "prompt_hash": prompt_hash,
        "input_payload_hash": input_payload_hash,
        "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"),
        "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"),
        "runtime_generation_status": runtime_generation_status,
        "product_quality_status": product_quality_status,
        "x2_failed_gates": [g["gate_id"] for g in x2 if not g["pass"]],
        "x3_code": x3.x3_code,
        "proof_eligible": proof_bundle["proof_eligible"],
        "judge_proof_eligible": proof_bundle["judge_proof_eligible"],
    }
    parent_attr("merge_graph_evidence_reporting_into_dict", merge_graph_evidence_reporting_into_dict)(
        _smr_ub,
        section_id="unify_bullets",
        runtime_payload=runtime_payload,
        x2_gates=x2,
        selected_fact_plan=l2_output.get("selected_fact_plan") if isinstance(l2_output, dict) else None,
        claim_ledger=claim_ledger,
    )
    parent_attr("write_json", write_json)(artifact_dir / "section_metric_receipt.json", _smr_ub)

    output_lines = [
        "L2_UNIFY_BULLETS_OUTPUT:",
        display_for_coverage if bullets else f"BLOCKED: {parse_error}",
        "",
        "X1D_LLM_JUDGE_OUTPUTS:",
        "| Provider | Mode | Score | Threshold | Pass | Decisive Failure | Error |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for judge in x1d:
        output_lines.append(
            f"| {judge['provider_name']} | {judge['evaluator_mode']} | {judge.get('score')} | "
            f"{judge.get('threshold')} | {judge.get('pass')} | {judge.get('decisive_failure')} | "
            f"{judge.get('exact_provider_error') or ''} |"
        )
    output_lines.extend(["", "X2_DETERMINISTIC_GATE_OUTPUTS:"])
    for gate in x2:
        output_lines.append(f"- {gate['gate_id']}: {'PASS' if gate['pass'] else 'FAIL'}")
    output_lines.extend(["", "X3_DISPOSITION:", json.dumps(x3.to_dict(), indent=2), "", "L6_SHADOW_EVAL_PACKAGE:"])
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
        "unify_bullets",
        runtime_payload,
        proof_bundle=proof_bundle,
        runtime_generation_status=runtime_generation_status,
    )
    parent_attr("finalize_runtime_proof_run", finalize_runtime_proof_run)(
        parent_attr("REPO_ROOT", REPO_ROOT),
        LANE_KEY,
        args.provider,
        artifact_dir,
        run_id=runtime_payload["run_id"],
        section_id="unify_bullets",
        runtime_generation_status=runtime_generation_status,
        provider_requested=prq,
        provider_attempted=pratt,
        command=" ".join(sys.argv),
        proof_eligible=proof_bundle["proof_eligible"],
        judge_proof_eligible=proof_bundle["judge_proof_eligible"],
        proof_scope=proof_bundle["proof_scope"],
        test_only_mock_provider=proof_bundle["test_only_mock_provider"],
        runtime_certification=proof_bundle["runtime_certification"],
        x1d_runtime_status=proof_bundle["x1d_runtime_status"],
        provider_proof_eligible=proof_bundle["provider_proof_eligible"],
        test_only_mock_judges=proof_bundle["test_only_mock_judges"],
        proof_closeout_note=proof_bundle.get("proof_closeout_note") or None,
    )
    return {
        "artifact_dir": artifact_dir,
        "repo_root": parent_attr("REPO_ROOT", REPO_ROOT),
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
        "bullets_display_text": display_for_coverage,
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
    }
