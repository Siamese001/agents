"""Stage 2b: Persist L2 artifacts, build usage ledger, and run initial X2 gates."""
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


def run_generation_x2_eval(ctx: dict[str, Any]) -> None:
    """Emit initial L2 outputs and compute deterministic X2 gate results."""
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    proof_pool_metadata = ctx["proof_pool_metadata"]
    targeting_ingress = ctx["targeting_ingress"]
    pool = ctx["pool"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    allowed_fact_ids_ordered = ctx["allowed_fact_ids_ordered"]
    provider_request_data = ctx["provider_request_data"]
    provider_result_data = ctx["provider_result_data"]
    provider_resolution_source = ctx["provider_resolution_source"]
    section_compiled = ctx["section_compiled"]
    compiled_prompt = ctx["compiled_prompt"]
    input_payload_hash = ctx["input_payload_hash"]
    prompt_hash = ctx["prompt_hash"]
    _bundle_mat = ctx["_bundle_mat"]
    _generation_material = ctx["_generation_material"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    parse_error = ctx["parse_error"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    coverage = ctx["coverage"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    model_name = ctx["model_name"]
    selected_facts_for_x2 = ctx["selected_facts_for_x2"]
    temperature = ctx["temperature"]
    apply_proof_pool_to_usage_ledger = ctx["apply_proof_pool_to_usage_ledger"]
    _wg = ctx["_wg"]

    l2_output = {
        "run_id": runtime_payload["run_id"],
        "section_id": "executive_summary",
        "runtime_generation_status": runtime_generation_status,
        "product_quality_status": "PENDING",
        "product_quality_reason": "",
        "executive_strategy_thesis": str((parsed or {}).get("executive_strategy_thesis") or "").strip(),
        "resume_display_text": resume_display_text,
        "selected_fact_plan": selected_fact_plan,
        "claim_ledger": claim_ledger,
        "jd_alignment": (parsed or {}).get("jd_alignment")
        or {"targeting_only": True, "jd_used_as_proof": False},
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
    _lane_attr("write_json", write_json)(artifact_dir / "l2_output.json", l2_output)
    _wg.write_text(artifact_dir / "resume_display_text.txt", resume_display_text + "\n", encoding="utf-8")
    _lane_attr("write_json", write_json)(artifact_dir / "selected_fact_plan.json", l2_output["selected_fact_plan"])
    _lane_attr("write_json", write_json)(artifact_dir / "claim_ledger.json", claim_ledger)
    _lane_attr("write_json", write_json)(artifact_dir / "text_claim_coverage.json", coverage)
    sfp_for_usage = (parsed or {}).get("selected_fact_plan") or selected_fact_plan
    trace_rr = rel_posix(artifact_dir, REPO_ROOT)
    req_id = str(
        (provider_request_data or {}).get("request_id")
        or (provider_request_data or {}).get("id")
        or runtime_payload["run_id"]
    )
    judge_keys = [j.strip() for j in args.x1d_judges.split(",") if j.strip()]
    judge_mode = "mocked" if (args.mock_judges and getattr(args, "allow_test_mock_judges", False)) else "blocked_if_unavailable"
    _judge_jd = _bundle_mat.jd_text_frozen
    _judge_briefing = _bundle_mat.briefing_text_frozen
    x1d: list[dict[str, Any]] = []
    judge_packet: dict[str, Any] = {}
    judge_packet_ref = ""

    usage_doc = build_section_input_usage_ledger_v1(
        section_id="executive_summary",
        run_id=str(runtime_payload["run_id"]),
        request_id=req_id,
        trace_root=trace_rr,
        repo_root=REPO_ROOT,
        artifact_dir=artifact_dir,
        runtime_payload=runtime_payload,
        selected_fact_plan=sfp_for_usage if isinstance(sfp_for_usage, dict) else {"facts": []},
        claim_ledger=claim_ledger,
        allowed_fact_ids=allowed_fact_ids,
        # Canonical inputs for the cross-lane digest: the aggregation preflight compares
        # jd_text_hash/briefing_hash ACROSS lanes (x2_preflight_*_digest_coherence), and
        # exec was the lone mismatch on every integrated run (live: attempt4 f7cc... vs
        # all other lanes e6a2...) because (a) the materialized slice was stamped and
        # (b) exec's runtime_payload carries the exec-only _CAP_NOTICE sentinel appended
        # by the targeting cap. Strip the sentinel so the hash is over the same canonical
        # text every other lane stamps; the slice digests stay receipted by the
        # targeting-parity machinery.
        jd_text=_lane_attr("_strip_targeting_cap_notice", _strip_targeting_cap_notice)(
            str(runtime_payload.get("jd_text") or "") or _generation_material.jd_text_material
        ),
        target_title=_lane_attr("_args_target_title", _args_target_title)(args),
        target_company=str(args.target_company),
        briefing_text=_lane_attr("_strip_targeting_cap_notice", _strip_targeting_cap_notice)(
            str(runtime_payload.get("briefing") or "") or _generation_material.briefing_text_material
        ),
        jd_alignment=l2_output.get("jd_alignment"),
    )
    usage_doc = apply_proof_pool_to_usage_ledger(usage_doc, pool)
    # Keep the exact final-plan reconciliation through X2.  ``pool`` retains
    # the broader whole-run metadata so that usage reporting can preserve its
    # lineage, but the executive section may only validate against its final
    # section allowlist.  Replacing this with ``pool.proof_pool_metadata``
    # silently reintroduced C0.3 candidates removed before L2.
    runtime_payload["proof_pool_metadata"] = proof_pool_metadata
    _targeting_parity, usage_doc = publish_targeting_parity_and_usage_ledger(
        artifact_dir=artifact_dir,
        runtime_payload=runtime_payload,
        generation_material=_generation_material,
        judge_packet=judge_packet or {},
        usage_doc=usage_doc,
        write_json_fn=_lane_attr("write_json", write_json),
    )

    trace = {
        "runtime_path": "apps_rg.runtime.sections.executive_summary_lane",
        "prompt_id": PROMPT_ID,
        "provider": args.provider,
        "provider_resolution_source": provider_resolution_source,
        "temperature": temperature,
        "monolithic_prompt_invoked": False,
        "section_prompt_adapter": True,
        "contract_template_ref": section_compiled.apps_rg_prompt_template_ref,
        "apps_rg_prompt_template_ref": section_compiled.apps_rg_prompt_template_ref,
        "pa_shell_ref": "apps_rg/prompt_assembly/templates/strategic_tailor_v1.yaml",
        "prompt_bom_ref": "apps_rg/prompt_assembly/prompt_bom.yaml",
        "selected_template_id": section_compiled.artifact.template_id,
        "compiler_template_id": section_compiled.artifact.template_id,
        "prompt_hash": prompt_hash,
        "component_hash_map": {
            "pa_prompt_hash": section_compiled.artifact.prompt_hash,
            "provider_prompt_hash": prompt_hash,
        },
        "w3_execution_path_bucket": W3_EXECUTION_PATH_BUCKET,
        "w3_execution_path_plan_slug": W3_EXECUTION_PATH_PLAN_SLUG,
    }
    trace = attach_reasoning_to_prompt_trace(
        trace,
        provider=args.provider,
        lane_key=LANE_KEY,
        provider_result_data=provider_result_data if isinstance(provider_result_data, dict) else None,
    )
    _lane_attr("write_json", write_json)(artifact_dir / "prompt_selection_trace.json", trace)
    _lane_attr("write_x2_gate_outputs", write_x2_gate_outputs)(artifact_dir / "x2_gate_outputs.json", [], section_id="executive_summary")

    from apps_rg.runtime.product_evidence_authority import x2_proof_pool_gate_flags

    pp_x2 = runtime_payload.get("proof_pool_metadata") or proof_pool_metadata or {}
    proof_pool_x2_active, _legacy_slice_x2_active = x2_proof_pool_gate_flags(pp_x2)

    x2 = [
        g.to_dict()
        for g in run_x2_gates(
        resume_display_text=resume_display_text,
        parsed_output=parsed_for_x2,
        claim_ledger=claim_ledger,
        text_claim_coverage=coverage,
        allowed_fact_ids=allowed_fact_ids,
        target_company=args.target_company,
        jd_text=_generation_material.jd_text_material,
        temperature=temperature,
        runtime_generation_status=runtime_generation_status,
        monolithic_prompt_invoked=False,
        strategic_tailor_v1_invoked=False,
        artifacts_dir=artifact_dir,
        provider_requested=args.provider,
        provider_attempted=args.provider,
        model_name=model_name,
        prompt_hash=prompt_hash,
        compiled_prompt=compiled_prompt,
        raw_output=raw_output,
        target_role=args.target_role if hasattr(args, "target_role") else None,
        selected_facts=selected_facts_for_x2,
        x1d_judges=x1d,
        defer_x1d_gates=True,
        proof_pool_metadata=pp_x2 if proof_pool_x2_active else None,
        proof_pool_ref=str(pool.proof_pool_ref or ""),
        proof_pool_digest=str(pool.proof_pool_digest or ""),
        )
    ]
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        GRAPH_CLAIM_BINDING_GATE_ID,
        build_pre_x2_resume_graph_claim_binding_gate,
    )

    _graph_binding_gate = build_pre_x2_resume_graph_claim_binding_gate(
        section_id="executive_summary",
        claim_rows=claim_ledger,
        selected_fact_plan=selected_fact_plan,
    )
    if _graph_binding_gate is not None:
        x2 = [
            gate
            for gate in x2
            if str(gate.get("gate_id") or "") != GRAPH_CLAIM_BINDING_GATE_ID
        ]
        x2.append(_graph_binding_gate)
    from apps_rg.runtime.validators.proof_pool_source_fact_validation import (
        write_x2_source_fact_pool_receipt,
    )

    for g in x2:
        obs = g.get("observed_value")
        if isinstance(obs, dict) and obs.get("x2_source_fact_pool_status"):
            write_x2_source_fact_pool_receipt(artifact_dir, obs)
            break
    _lane_attr("write_x2_gate_outputs", write_x2_gate_outputs)(artifact_dir / "x2_gate_outputs.json", x2, section_id="executive_summary")
    from apps_rg.runtime.section_repair_ledger import load_ledger, record_x2_run

    _ledger = load_ledger(artifact_dir) or {}
    record_x2_run(
        artifact_dir,
        run_number=len(list(_ledger.get("x2_runs") or [])) + 1,
        after_l2_source=str(_ledger.get("authoritative_l2_source") or "initial_llm"),
        x2_gates=x2,
    )
    ctx.update({
        "l2_output": l2_output,
        "judge_keys": judge_keys,
        "judge_mode": judge_mode,
        "_judge_jd": _judge_jd,
        "_judge_briefing": _judge_briefing,
        "x1d": x1d,
        "judge_packet": judge_packet,
        "judge_packet_ref": judge_packet_ref,
        "usage_doc": usage_doc,
        "_targeting_parity": _targeting_parity,
        "trace": trace,
        "pp_x2": pp_x2,
        "proof_pool_x2_active": proof_pool_x2_active,
        "x2": x2,
    })
