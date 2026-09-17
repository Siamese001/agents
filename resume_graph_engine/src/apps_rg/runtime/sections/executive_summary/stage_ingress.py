"""Stage 1: Ingress, targeting preparation, and initial model generation dispatch."""
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

def run_ingress_stage(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {"args": args}
    from apps_rg.runtime.sections.resume_employment_bullets import collect_employment_bullets
    from apps_rg.runtime.c0.section_proof_loader import (
        apply_proof_pool_to_usage_ledger,
        load_section_proof_for_lane,
    )

    from apps_rg.runtime.ingress.executive_summary_targeting_ingress import (
        prepare_executive_summary_targeting_ingress,
    )

    briefing_raw = str(getattr(args, "briefing", "") or "")
    targeting_ingress = prepare_executive_summary_targeting_ingress(
        jd_text=_args_jd_text(args),
        briefing_raw=briefing_raw,
        target_role=str(getattr(args, "target_role", "") or ""),
        target_title=_args_target_title(args),
        repo_root=REPO_ROOT,
    )
    if (
        isinstance(targeting_ingress.briefing_selection_receipt, dict)
        and targeting_ingress.briefing_selection_receipt.get("fail_closed")
    ):
        raise RuntimeError(
            str(
                targeting_ingress.briefing_selection_receipt.get("truncation_or_selection_reason")
                or "briefing_fail_closed"
            )
        )

    pool, base, base_path, base_hash, front_spine = load_section_proof_for_lane(
        section_id="executive_summary",
        args=args,
        repo_root=REPO_ROOT,
        collect_employment_bullets_fn=collect_employment_bullets,
        jd_text_override=targeting_ingress.jd_text,
        briefing_text_override=targeting_ingress.briefing_text_bounded,
    )
    selected_fact_plan = pool.selected_fact_plan
    allowed_fact_ids = pool.allowed_fact_ids
    allowed_fact_ids_ordered = list(pool.allowed_fact_ids_ordered)
    proof_pool_metadata = _reconcile_final_plan_c03_allowlist(
        pool.proof_pool_metadata,
        allowed_fact_ids=allowed_fact_ids,
        proof_pool_digest=str(pool.proof_pool_digest or ""),
        jd_text=targeting_ingress.jd_text,
    )

    provider_resolution_source = coalesce_lane_provider_resolution_source(
        explicit=getattr(args, "provider_resolution_source", None),
        resolved_provider=str(args.provider),
    )

    runtime_payload = build_runtime_payload(
        base_json_path=base_path,
        base_hash=base_hash,
        selected_fact_plan=selected_fact_plan,
        target_title=_args_target_title(args),
        target_company=str(getattr(args, "target_company", None) or TARGET_COMPANY_DEFAULT),
        jd_text=targeting_ingress.jd_text,
        briefing=targeting_ingress.briefing_text_bounded,
        allowed_fact_ids_ordered=allowed_fact_ids_ordered,
    )
    runtime_payload["targeting_ingress"] = targeting_ingress.to_dict()
    runtime_payload["briefing_signal_packet"] = targeting_ingress.briefing_signal_packet
    if targeting_ingress.briefing_selection_receipt is not None:
        runtime_payload["briefing_selection"] = targeting_ingress.briefing_selection_receipt
    runtime_payload["proof_pool_metadata"] = proof_pool_metadata
    if pool.proof_source == "augmented_skills_graph":
        runtime_payload["graph_only_claim_authority"] = True
        runtime_payload["base_resume_claim_authority"] = False
    if artifact_dir_override is not None:
        artifact_dir = Path(artifact_dir_override)
        _wg.ensure_dir(artifact_dir)
    else:
        artifact_dir = prepare_runtime_proof_run_dir(REPO_ROOT, LANE_KEY, args.provider, runtime_payload["run_id"])
    from apps_rg.runtime.section_repair_ledger import init_ledger
    from apps_rg.runtime.sections.executive_summary_regen_dispatch import (
        clear_regen_budget_ledger,
    )

    clear_regen_budget_ledger(artifact_dir)
    init_ledger(
        artifact_dir,
        section_id="executive_summary",
        run_id=str(runtime_payload["run_id"]),
    )
    write_json(
        artifact_dir / "targeting_ingress_receipt.json",
        targeting_ingress.to_dict(),
    )
    if targeting_ingress.briefing_selection_receipt is not None:
        write_json(
            artifact_dir / "briefing_selection_receipt.json",
            targeting_ingress.briefing_selection_receipt,
        )

    _tc_receipt = freeze_executive_summary_targeting_context(
        runtime_payload,
        authority_source_refs={
            "targeting_ingress": "targeting_ingress_receipt.json",
            "briefing_selection": "briefing_selection_receipt.json",
            "jd_source": "targeting_ingress",
        },
    )
    write_json(artifact_dir / "targeting_context_receipt.json", _tc_receipt)
    from apps_rg.runtime.spine.c0_fec_compose import (
        merge_compiled_prompt_artifact_fec_fields,
    )
    from apps_rg.runtime.sections.upstream_evidence_block import wire_spine_c0_fec_or_block

    blocked = wire_spine_c0_fec_or_block(
        repo_root=REPO_ROOT,
        artifact_dir=artifact_dir,
        section_id="executive_summary",
        front_spine=front_spine,
        pool=pool,
        runtime_payload=runtime_payload,
        provider=str(args.provider),
        temperature=float(args.temperature),
        max_tokens=resolve_scratch_max_output_tokens(),
        output_filename="resume_display_text.txt",
    )
    if blocked is not None:
        return blocked
    from apps_rg.runtime.spine.section_c0_graph_lane_ensure import (
        ensure_section_c0_graph_lane_receipt,
    )

    _graph_lane_path = ensure_section_c0_graph_lane_receipt(
        artifact_dir,
        runtime_payload=runtime_payload,
        section_id="executive_summary",
    )
    runtime_payload["c0_graph_lane_receipt_ref"] = _graph_lane_path.name
    runtime_payload["section_front_spine_receipt_ref"] = "section_front_spine_receipt.json"
    runtime_payload["proof_pool_front_spine_preconditions"] = {
        "precondition_status": "PASS",
        "status": "PASS",
        "required_contracts": list(front_spine.contracts_emitted().keys()),
        "satisfied": all(front_spine.contracts_emitted().values()),
        "proof_pool_entry_allowed": True,
        "validated_request_ref": "validated_request.json",
        "l1_plan_contract_ref": "l1_plan_contract.json",
        "route_contract_ref": "route_contract.json",
        "receipt_ref": "section_front_spine_receipt.json",
        "canonical_c0_claimed": False,
        "canonical_exit_claimed": False,
        "product_certification": "NOT_CLAIMED",
    }
    from apps_rg.runtime.sections.section_generation import merge_transport_context

    merge_transport_context(
        artifact_dir=str(artifact_dir.resolve()),
        run_id=str(runtime_payload.get("run_id") or ""),
    )
    from apps_rg.runtime.sections.lane_artifact_io import runtime_payload_for_json

    payload_for_json = runtime_payload_for_json(runtime_payload)
    input_payload_hash = sha16(json.dumps(payload_for_json, sort_keys=True))
    from apps_rg.runtime.sections.executive_summary_evidence_capsule import (
        ExecutiveSummaryEvidenceCapsuleError,
        _capsule_enabled,
        compile_executive_summary_evidence_capsule,
        write_evidence_capsule_receipt,
    )
    from apps_rg.runtime.sections.executive_summary_token_budget import (
        ExecutiveSummaryTokenBudgetExceeded,
        apply_executive_summary_token_budget_policy,
        estimate_tokens_approximate,
        write_token_budget_receipt,
    )

    from apps_rg.runtime.c0.c03_allowlist_coherence import assert_pre_l2_allowlist_coherence

    allowlist_block_reason: str | None = assert_pre_l2_allowlist_coherence(
        allowed_fact_ids=allowed_fact_ids,
        c03_bound=proof_pool_metadata.get("c03_graphrag_bound")
        if isinstance(proof_pool_metadata, dict)
        else None,
        # The full track expansion is retained as non-proof targeting context.
        # Its complete surplus set is recorded in the reconciliation receipt
        # above and checked again by X2; C0.3 is the claimable projection.
        track_expansion=None,
        runtime_payload=runtime_payload,
    )
    if allowlist_block_reason:
        runtime_payload["allowlist_coherence_policy"] = {
            "fail_closed": True,
            "fail_closed_reason": allowlist_block_reason,
            "dispatch_allowed": False,
        }

    capsule_doc = (
        proof_pool_metadata.get("graph_targeting_capsule")
        if isinstance(proof_pool_metadata, dict)
        else None
    )
    if isinstance(capsule_doc, dict):
        runtime_payload["graph_targeting_capsule"] = capsule_doc
        write_json(artifact_dir / "graph_targeting_capsule.json", capsule_doc)
    _allowlist_receipt_early = (
        proof_pool_metadata.get("exec_summary_allowlist_receipt")
        if isinstance(proof_pool_metadata, dict)
        else None
    )
    if isinstance(_allowlist_receipt_early, dict):
        write_json(artifact_dir / "allowlist_coherence_receipt.json", _allowlist_receipt_early)
        _promo_early = _allowlist_receipt_early.get("c03_promotion_candidates")
        if isinstance(_promo_early, dict) and _promo_early:
            write_json(artifact_dir / "c03_promotion_candidates.json", _promo_early)

    evidence_capsule_block_reason: str | None = allowlist_block_reason
    if _capsule_enabled(runtime_payload) and not evidence_capsule_block_reason:
        try:
            baseline_payload = dict(runtime_payload)
            baseline_payload["evidence_capsule_active"] = False
            baseline_payload["evidence_capsule_disabled"] = True
            baseline_compiled = compile_executive_summary_prompt(
                baseline_payload, run_id=runtime_payload["run_id"]
            )
            before_capsule_est = estimate_tokens_approximate(
                str(baseline_compiled.artifact.messages[0].get("content") or "")
            )
            _, capsule_receipt = compile_executive_summary_evidence_capsule(runtime_payload)
            if before_capsule_est and capsule_receipt.get("capsule_token_estimate") is not None:
                capsule_receipt["capsule_reduction_estimate"] = max(
                    0,
                    before_capsule_est
                    - int(capsule_receipt["capsule_token_estimate"]),
                )
            write_evidence_capsule_receipt(artifact_dir, capsule_receipt)
            section_compiled = compile_executive_summary_prompt(
                runtime_payload, run_id=runtime_payload["run_id"]
            )
            after_capsule_est = estimate_tokens_approximate(
                str(section_compiled.artifact.messages[0].get("content") or "")
            )
            runtime_payload["prompt_token_estimates"] = {
                "before_capsule_prompt_estimate": before_capsule_est,
                "after_capsule_prompt_estimate": after_capsule_est,
            }
        except ExecutiveSummaryEvidenceCapsuleError as cap_exc:
            evidence_capsule_block_reason = str(
                cap_exc.receipt.get("fail_closed_reason") or cap_exc
            )
            write_evidence_capsule_receipt(artifact_dir, cap_exc.receipt)
            runtime_payload["evidence_capsule_policy"] = {
                "fail_closed": True,
                "fail_closed_reason": evidence_capsule_block_reason,
            }
            section_compiled = compile_executive_summary_prompt(
                runtime_payload, run_id=runtime_payload["run_id"]
            )
    else:
        section_compiled = compile_executive_summary_prompt(
            runtime_payload, run_id=runtime_payload["run_id"]
        )

    token_budget_block_reason: str | None = None
    token_budget_receipt: dict[str, Any] | None = None

    max_out_tokens = resolve_scratch_max_output_tokens()
    from apps_rg.runtime.section_model_limits import (
        external_openai_generation_model,
        resolve_section_generation_model,
    )

    section_model = (
        external_openai_generation_model(section_id=LANE_KEY)
        if str(args.provider) == "external_openai"
        else resolve_section_generation_model(
            LANE_KEY, provider_profile=str(args.provider)
        )
    )
    if not evidence_capsule_block_reason:
        try:
            section_compiled, token_budget_receipt = apply_executive_summary_token_budget_policy(
                section_compiled,
                runtime_payload=runtime_payload,
                provider=str(args.provider),
                model=section_model,
                requested_max_output_tokens=max_out_tokens,
            )
            write_token_budget_receipt(artifact_dir, token_budget_receipt)
        except ExecutiveSummaryTokenBudgetExceeded as budget_exc:
            token_budget_receipt = budget_exc.receipt
            write_token_budget_receipt(artifact_dir, token_budget_receipt)
            token_budget_block_reason = str(
                token_budget_receipt.get("fail_closed_reason") or budget_exc
            )
            _tb_guidance = token_budget_receipt.get("operator_guidance")
            _tb_operator_message = (
                str(token_budget_receipt.get("operator_message") or "").strip()
                or (
                    str(_tb_guidance.get("operator_message") or "").strip()
                    if isinstance(_tb_guidance, dict)
                    else ""
                )
            )
            if _tb_operator_message:
                print(_tb_operator_message, file=sys.stderr, flush=True)
            runtime_payload["token_budget_policy"] = {
                "fail_closed": True,
                "fail_closed_reason": token_budget_block_reason,
                "dispatch_allowed": False,
                "prompt_shape_preserved": token_budget_receipt.get("prompt_shape_preserved"),
                "evidence_contract_preserved": token_budget_receipt.get(
                    "evidence_contract_preserved"
                ),
                "operator_summary": token_budget_receipt.get("operator_summary"),
                "operator_message": _tb_operator_message or None,
            }
    messages = section_compiled.artifact.messages
    compiled_prompt = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    from apps_rg.runtime.targeting_context_authority import (
        generation_material_context_from_bundle,
        require_material_targeting_bundle,
    )

    _bundle_mat = require_material_targeting_bundle(runtime_payload)
    _generation_material = generation_material_context_from_bundle(_bundle_mat)
    runtime_payload["generation_material_context"] = _generation_material.to_dict()
    prompt_hash = sha16(compiled_prompt)
    write_json(artifact_dir / "runtime_payload.json", payload_for_json)
    pp_c03 = proof_pool_metadata or {}
    c03_doc = pp_c03.get("c03_graphrag_bound")
    if isinstance(c03_doc, dict):
        write_json(artifact_dir / "c03_graphrag_bound.json", c03_doc)
    native_c03 = pp_c03.get("native_c03_final_evidence")
    if isinstance(native_c03, dict):
        write_json(artifact_dir / "native_c03_final_evidence.json", native_c03)
    fec_snap = pp_c03.get("final_evidence_contract_snapshot")
    if isinstance(fec_snap, dict):
        write_json(artifact_dir / "final_evidence_contract_snapshot.json", fec_snap)
    _wg.write_text(
        artifact_dir / "compiled_prompt.txt",
        json.dumps(messages, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_json(
        artifact_dir / "compiled_prompt_artifact.json",
        merge_compiled_prompt_artifact_fec_fields(
            {
                "section_id": section_compiled.section_id,
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
                "pa_prompt_hash": section_compiled.artifact.prompt_hash,
                "provider_prompt_hash": prompt_hash,
                "slot_count": section_compiled.artifact.slot_count,
                "proof_source": pool.proof_source,
                "proof_pool_ref": pool.proof_pool_ref,
                "proof_pool_digest": pool.proof_pool_digest,
                "base_resume_fallback_used": pool.base_resume_fallback_used,
                "graph_only_claim_authority": pool.proof_source == "augmented_skills_graph",
                "c03_graphrag_bound_status": (proof_pool_metadata or {}).get("c03_graphrag_bound_status"),
                "allowed_source_fact_ids_count": len(allowed_fact_ids),
                **(
                    {
                        "token_budget_trim_applied": token_budget_receipt.get("trim_applied"),
                        "token_budget_receipt_ref": "token_budget_receipt.json",
                    }
                    if token_budget_receipt
                    else {}
                ),
                **(
                    {
                        "evidence_capsule_active": True,
                        "evidence_capsule_receipt_ref": "evidence_capsule_receipt.json",
                    }
                    if runtime_payload.get("evidence_capsule_active")
                    else {}
                ),
            },
            runtime_payload,
        ),
    )

    provider_request_data = None
    provider_result_data = None
    raw_output = ""
    parsed: dict[str, Any] | None = None
    parse_error = ""
    runtime_generation_status = "BLOCKED"

    from apps_rg.runtime.section_l2_lane_integration import prepare_section_l2_before_provider

    prepare_section_l2_before_provider(
        artifact_dir,
        "executive_summary",
        runtime_payload,
        provider_lane=str(args.provider),
    )

    provider_req: Any = None
    provider_payload: dict[str, Any] = {}
    if evidence_capsule_block_reason:
        _block_ref = (
            "allowlist_coherence_receipt.json"
            if allowlist_block_reason
            else "evidence_capsule_receipt.json"
        )
        provider_request_data = {
            "provider_requested": str(args.provider),
            "provider_attempted": False,
            "blocked_before_dispatch": True,
            "fail_closed_reason": evidence_capsule_block_reason,
            "max_tokens": max_out_tokens,
            "pre_l2_block_receipt_ref": _block_ref,
            "mock_fallback_allowed": False,
        }
        write_json(artifact_dir / "provider_request.json", provider_request_data)
        result = ProviderResult(
            provider_requested=str(args.provider),
            provider_attempted=False,
            provider_available=False,
            exact_provider_error=f"L2_BLOCK:{evidence_capsule_block_reason}",
            runtime_generation_status="BLOCKED",
            model=section_model,
            raw_model_output="",
            provider_response={
                "pre_l2_blocked": True,
                "allowlist_coherence_blocked": bool(allowlist_block_reason),
                "evidence_capsule_blocked": bool(
                    evidence_capsule_block_reason and not allowlist_block_reason
                ),
                "reason": evidence_capsule_block_reason,
            },
        )
        req_model = str(provider_request_data.get("model") or section_model)
    elif token_budget_block_reason:
        _tb_op_summary = ""
        if isinstance(token_budget_receipt, dict):
            _tb_op_summary = str(token_budget_receipt.get("operator_summary") or "").strip()
        provider_request_data = {
            "provider_requested": str(args.provider),
            "provider_attempted": False,
            "blocked_before_dispatch": True,
            "fail_closed_reason": token_budget_block_reason,
            "max_tokens": max_out_tokens,
            "token_budget_receipt_ref": "token_budget_receipt.json",
            "mock_fallback_allowed": False,
            "operator_summary": _tb_op_summary or None,
        }
        write_json(artifact_dir / "provider_request.json", provider_request_data)
        result = ProviderResult(
            provider_requested=str(args.provider),
            provider_attempted=False,
            provider_available=False,
            exact_provider_error=(
                f"L2_BLOCK:{_tb_op_summary or token_budget_block_reason}"
            ),
            runtime_generation_status="BLOCKED",
            model=section_model,
            raw_model_output="",
            provider_response={
                "token_budget_blocked": True,
                "reason": token_budget_block_reason,
                "operator_summary": _tb_op_summary or None,
                "operator_guidance": (
                    token_budget_receipt.get("operator_guidance")
                    if isinstance(token_budget_receipt, dict)
                    else None
                ),
            },
        )
        req_model = str(provider_request_data.get("model") or section_model)
    else:
        provider_req, provider_payload = build_section_request(
            messages=messages,
            prompt_hash=prompt_hash,
            input_payload_hash=input_payload_hash,
            temperature=args.temperature,
            max_tokens=max_out_tokens,
            model=section_model,
            provider_requested=str(args.provider),
            compiled_prompt_artifact=section_compiled.artifact,
            anthropic_workload_kind="ONE_SHOT",
            idempotent_replay_safe=True,
        )
        provider_payload = tag_reasoning_lane(provider_payload, LANE_KEY)
        provider_request_data = provider_req.to_dict()
        if token_budget_receipt:
            provider_request_data["token_budget"] = {
                "trim_applied": token_budget_receipt.get("trim_applied"),
                "compiled_prompt_tokens_after_trim": token_budget_receipt.get(
                    "compiled_prompt_tokens_after_trim"
                ),
                "available_input_tokens": token_budget_receipt.get("available_input_tokens"),
                "provider_context_window": token_budget_receipt.get("provider_context_window"),
            }
        write_json(artifact_dir / "provider_request.json", provider_request_data)
        req_model = str(provider_payload.get("model", section_model))
    if (
        evidence_capsule_block_reason
        or token_budget_block_reason
        or allowlist_block_reason
    ):
        pass
    else:
        from apps_rg.runtime.providers.section_provider_call import call_section_model_provider

        result = call_section_model_provider(
            str(args.provider),
            provider_payload,
            artifact_dir=artifact_dir,
            run_id=str(runtime_payload.get("run_id") or "") or None,
        )
    provider_result_data = result.to_dict()
    raw_output = result.raw_model_output
    runtime_generation_status = result.runtime_generation_status

    ctx["artifact_dir"] = artifact_dir
    ctx["runtime_payload"] = runtime_payload
    ctx["proof_pool_metadata"] = proof_pool_metadata
    ctx["targeting_ingress"] = targeting_ingress
    ctx["messages"] = messages
    ctx["req"] = req
    ctx["scratch_max_tokens"] = scratch_max_tokens
    ctx["token_budget_receipt"] = token_budget_receipt
    ctx["usage_doc"] = usage_doc
    ctx["briefing_text_bounded"] = targeting_ingress.briefing_text_bounded
    ctx["pool"] = pool
    ctx["base_path"] = base_path
    ctx["base_hash"] = base_hash
    ctx["base"] = base
    ctx["selected_fact_plan"] = selected_fact_plan
    ctx["allowed_fact_ids"] = allowed_fact_ids
    ctx["allowed_fact_ids_ordered"] = allowed_fact_ids_ordered
    ctx["result"] = result
    return ctx
