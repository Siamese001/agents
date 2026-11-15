"""Stage 3: IBM bullets X3 finalization, L2/L6 closeout, and artifact inventory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.exit.ibm_bullets_x3 import aggregate_x3 as _aggregate_ibm_bullets_x3
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
from apps_rg.runtime.shadow.ibm_bullets_l6 import (
    build_l6_shadow_package,
    extend_ibm_bullets_l6_learning_fields,
)
from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3
from ._parent import parent_attr
from .lane_constants import IBM_MAX_OUTPUT_TOKENS, IBM_TEMP_DEFAULT, LANE_KEY, PROMPT_ID, REPO_ROOT, write_json
from .provider_io import bullets_display_text


def run_ibm_closeout_stage(
    args: argparse.Namespace,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Finalize X3, attach L2/exhaust/L6 receipts, seal proof directory, and return lane result."""
    artifact_dir: Path = ctx["artifact_dir"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    runtime_payload = ctx["runtime_payload"]
    input_payload_hash = ctx["input_payload_hash"]
    section_compiled = ctx["section_compiled"]
    messages = ctx["messages"]
    prompt_hash = ctx["prompt_hash"]
    placement_bucket = ctx["placement_bucket"]
    provider_request_data = ctx["provider_request_data"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parse_error = ctx["parse_error"]
    bullets = ctx["bullets"]
    claim_ledger = ctx["claim_ledger"]
    canon_doc = ctx["canon_doc"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    model_name = ctx["model_name"]
    l2_output = ctx["l2_output"]
    usage_doc = ctx["usage_doc"]
    x1d = ctx["x1d"]
    x2 = ctx["x2"]
    product_quality_status = ctx["product_quality_status"]
    product_quality_reason = ctx["product_quality_reason"]

    display_for_x3 = parent_attr("bullets_display_text", bullets_display_text)(bullets)
    x3 = parent_attr("finalize_section_lane_x3", finalize_section_lane_x3)(
        artifact_dir=artifact_dir,
        section_id="ibm_bullets",
        runtime_payload=runtime_payload,
        defer_graph_binding_l2_persistence=True,
        aggregate_x3_fn=_aggregate_ibm_bullets_x3,
        resume_display_text=display_for_x3,
        claim_ledger=claim_ledger,
        x2_gates=x2,
        x1d_judges=x1d,
        runtime_generation_status=runtime_generation_status,
        product_quality_status=product_quality_status,
        canonical_claims_for_hash=canon_doc.get("claims"),
        section_input_usage_ledger=usage_doc,
    )
    bundle = parent_attr("compute_lane_proof_bundle", compute_lane_proof_bundle)(
        args,
        section_id="ibm_bullets",
        runtime_generation_status=runtime_generation_status,
        x1d_judges=x1d,
        x2_gates=x2,
        x3=x3,
        offline_contract_stub_used=False,
    )
    l2_output["product_quality_status"] = product_quality_status
    l2_output["product_quality_reason"] = product_quality_reason
    parent_attr("attach_lane_proof_bundle_fields", attach_lane_proof_bundle_fields)(
        l2_output,
        runtime_generation_status=runtime_generation_status,
        bundle=bundle,
    )
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        merge_resume_graph_claim_binding_fields,
    )

    l2_output = merge_resume_graph_claim_binding_fields(
        l2_output,
        artifact_dir=artifact_dir,
    )
    parent_attr("write_json", write_json)(artifact_dir / "l2_output.json", l2_output)
    parent_attr("finalize_section_l2_after_output", finalize_section_l2_after_output)(artifact_dir, "ibm_bullets", runtime_payload)
    parent_attr("finalize_section_runtime_exhaust_before_l6", finalize_section_runtime_exhaust_before_l6)(
        artifact_dir, "ibm_bullets", runtime_payload, repo_root=parent_attr("REPO_ROOT", REPO_ROOT)
    )

    l6_temp = float(args.temperature) if args.provider == "external_claude" else IBM_TEMP_DEFAULT
    l6_max = IBM_MAX_OUTPUT_TOKENS if args.provider == "external_claude" else None
    parent_attr("gate_section_l6_shadow_after_exhaust", gate_section_l6_shadow_after_exhaust)(artifact_dir, runtime_payload)
    l6_base = parent_attr("build_l6_shadow_package", build_l6_shadow_package)(
        artifact_dir=artifact_dir,
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        prompt_id=PROMPT_ID,
        temperature=l6_temp,
        max_tokens=l6_max,
    )
    l6 = parent_attr("extend_ibm_bullets_l6_learning_fields", extend_ibm_bullets_l6_learning_fields)(
        l6_base,
        artifact_dir=artifact_dir,
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        provider=str(args.provider),
        x2_gates=x2,
        x3_code=str(x3.x3_code),
        authorization_scope=str(x3.authorization_scope),
        mocked_judges=list(x3.mocked_judges),
        proof_bundle=bundle,
        claim_ledger=claim_ledger,
        allowed_fact_ids=allowed_fact_ids,
        bullets=bullets,
    )
    parent_attr("write_json", write_json)(artifact_dir / "l6_shadow_eval_package.json", l6)

    rl2 = {
        "provider_attempted": args.provider,
        "runtime_generation_status": runtime_generation_status,
        "prompt_hash": prompt_hash,
        "model": model_name,
        "raw_model_output": raw_output,
        "bullets": bullets,
        "product_quality_status": product_quality_status,
        "x3_code": x3.x3_code,
    }
    parent_attr("attach_lane_proof_bundle_fields", attach_lane_proof_bundle_fields)(
        rl2,
        runtime_generation_status=runtime_generation_status,
        bundle=bundle,
    )

    _smr_ibm_b = {
        "run_id": runtime_payload["run_id"],
        "lane_id": "ibm_bullets",
        "prompt_id": PROMPT_ID,
        "prompt_hash": prompt_hash,
        "input_payload_hash": input_payload_hash,
        "output_payload_hash": (parsed_for_x2 or {}).get("output_payload_hash"),
        "claim_ledger_hash": (parsed_for_x2 or {}).get("claim_ledger_hash"),
        "runtime_generation_status": runtime_generation_status,
        "product_quality_status": product_quality_status,
        "x2_failed_gates": [g["gate_id"] for g in x2 if not g["pass"]],
        "x3_code": x3.x3_code,
        "proof_eligible": bundle["proof_eligible"],
        "judge_proof_eligible": bundle["judge_proof_eligible"],
    }
    parent_attr("merge_graph_evidence_reporting_into_dict", merge_graph_evidence_reporting_into_dict)(
        _smr_ibm_b,
        section_id="ibm_bullets",
        runtime_payload=runtime_payload,
        x2_gates=x2,
        selected_fact_plan=l2_output.get("selected_fact_plan") if isinstance(l2_output, dict) else None,
        claim_ledger=claim_ledger,
    )
    parent_attr("write_json", write_json)(artifact_dir / "section_metric_receipt.json", _smr_ibm_b)

    parent_attr("write_json", write_json)(
        artifact_dir / "real_l2_generation_result.json",
        rl2,
    )

    lines = [
        "IBM_BULLETS_OUTPUT:",
        parent_attr("bullets_display_text", bullets_display_text)(bullets) if bullets else f"BLOCKED: {parse_error}",
        "",
        "X1D_LLM_JUDGE_OUTPUTS:",
        "| Provider | Mode | Status | Score | Pass | Decisive Failure |",
        "|---|---|---|---:|---|---|",
    ]
    for judge in x1d:
        lines.append(
            f"| {judge['provider_name']} | {judge['evaluator_mode']} | {judge.get('provider_status')} | "
            f"{judge.get('score')} | {judge.get('pass')} | {judge.get('decisive_failure')} |"
        )
    lines.extend(["", "X2_DETERMINISTIC_GATE_OUTPUTS:"])
    for gate in x2:
        lines.append(f"- {gate['gate_id']}: {'PASS' if gate['pass'] else 'FAIL'}")
    lines.extend(["", "X3_DISPOSITION:", json.dumps(x3.to_dict(), indent=2), "", "L6_SHADOW_EVAL_PACKAGE:", str(artifact_dir / "l6_shadow_eval_package.json"), "offline_only=true"])
    output_text = "\n".join(lines)
    _wg.write_text(artifact_dir / "command_output.txt", output_text + "\n", encoding="utf-8")
    prq = str((provider_request_data or {}).get("provider_requested", args.provider))
    pratt = (provider_request_data or {}).get("provider_attempted", args.provider)
    from apps_rg.runtime.section_one_spine_certification_lane_integration import (
        finalize_section_one_spine_certification,
    )

    finalize_section_one_spine_certification(
        artifact_dir,
        "ibm_bullets",
        runtime_payload,
        proof_bundle=bundle,
        runtime_generation_status=runtime_generation_status,
    )
    parent_attr("finalize_runtime_proof_run", finalize_runtime_proof_run)(
        parent_attr("REPO_ROOT", REPO_ROOT),
        LANE_KEY,
        args.provider,
        artifact_dir,
        run_id=runtime_payload["run_id"],
        section_id="ibm_bullets",
        runtime_generation_status=runtime_generation_status,
        provider_requested=prq,
        provider_attempted=pratt,
        command=" ".join(sys.argv),
        placement_bucket=placement_bucket,
        proof_eligible=bundle["proof_eligible"],
        proof_scope=bundle["proof_scope"],
        proof_status=bundle["proof_status"],
        artifact_namespace_class=bundle["artifact_namespace_class"],
        runtime_generation_status_class=bundle["runtime_generation_status_class"],
        offline_contract_stub_used=bundle["offline_contract_stub_used"],
        offline_contract_stub_reason=None,
        authorization_scope=bundle["authorization_scope"],
        mocked_judges=list(x3.mocked_judges),
        test_only_mock_provider=bundle["test_only_mock_provider"],
        runtime_certification=bundle["runtime_certification"],
        x1d_runtime_status=bundle["x1d_runtime_status"],
        judge_proof_eligible=bundle["judge_proof_eligible"],
        provider_proof_eligible=bundle["provider_proof_eligible"],
        test_only_mock_judges=bundle["test_only_mock_judges"],
        proof_closeout_note=bundle["proof_closeout_note"] if bundle.get("proof_closeout_note") else None,
    )
    return {
        "artifact_dir": artifact_dir,
        "repo_root": parent_attr("REPO_ROOT", REPO_ROOT),
        "lane_key": LANE_KEY,
        "args": args,
        "runtime_payload": runtime_payload,
        "section_compiled": section_compiled,
        "messages": messages,
        "prompt_hash": prompt_hash,
        "input_payload_hash": input_payload_hash,
        "x3": x3,
        "output_text": output_text,
        "runtime_generation_status": runtime_generation_status,
        "allowed_fact_ids": allowed_fact_ids,
    }
