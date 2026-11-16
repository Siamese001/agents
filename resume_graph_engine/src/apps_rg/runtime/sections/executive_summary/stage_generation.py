"""Stage 2a: Model output normalization, voice/authority repairs, and L2 coverage."""
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

from .stage_generation_x2 import run_generation_x2_eval


def run_generation_stage(ctx: dict[str, Any]) -> None:
    """Parse model JSON, run repairs/coherence, build coverage, and run initial X2."""
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    proof_pool_metadata = ctx["proof_pool_metadata"]
    targeting_ingress = ctx["targeting_ingress"]
    messages = ctx["messages"]
    pool = ctx["pool"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    provider_payload = ctx["provider_payload"]
    provider_request_data = ctx["provider_request_data"]
    result = ctx["result"]
    provider_result_data = ctx["provider_result_data"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    input_payload_hash = ctx["input_payload_hash"]
    prompt_hash = ctx["prompt_hash"]

    _lane_attr("write_json", write_json)(artifact_dir / "provider_response.json", provider_result_data)
    parse_error = ""
    _composition_plan_early: dict[str, Any] | None = None
    if result.runtime_generation_status == "REAL_LLM":
        parsed, parse_error = _lane_attr("parse_model_json", parse_model_json)(raw_output)
        if parsed and isinstance(parsed, dict):
            from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import apply_pre_synthesis_candidate_repairs
            parsed, raw_output = apply_pre_synthesis_candidate_repairs(
                parsed, selected_fact_plan,
                normalize_fn=_lane_attr("normalize_executive_summary_llm_output", normalize_executive_summary_llm_output),
                prune_orphans_fn=_lane_attr("prune_exec_summary_claim_ledger_orphans", prune_exec_summary_claim_ledger_orphans),
                allowed_fact_ids_override=allowed_fact_ids,
                target_company=str(getattr(args, "target_company", "") or ""),
            )
        if parsed and str(args.provider) == "external_claude":
            from apps_rg.runtime.sections.executive_summary_pa import (
                is_strategy_executive_target_title,
            )

            _target_role_for_regen = str(
                runtime_payload.get("target_role")
                or runtime_payload.get("target_title")
                or ""
            ).strip()
            raw_output, parsed, parse_error = _lane_attr("retry_provider_for_synthesis", retry_provider_for_synthesis)(
                messages,
                provider_payload,
                raw_output,
                parsed,
                selected_facts=list(selected_fact_plan.get("facts") or []),
                selected_fact_plan=selected_fact_plan,
                strategy_executive=is_strategy_executive_target_title(_target_role_for_regen),
                artifact_dir=artifact_dir,
                run_id=str(runtime_payload.get("run_id") or "") or None,
                jd_text=str(runtime_payload.get("jd_text") or ""),
            )
        if parsed:
            parsed = _lane_attr("normalize_executive_summary_llm_output", normalize_executive_summary_llm_output)(parsed, selected_fact_plan)
            _lane_attr("prune_exec_summary_claim_ledger_orphans", prune_exec_summary_claim_ledger_orphans)(parsed, allowed_fact_ids)
            from apps_rg.runtime.section_repair_policy import graph_only_reformat_allowed

            _pp_meta_early = proof_pool_metadata if isinstance(proof_pool_metadata, dict) else {}
            _painting_early = bool(
                _pp_meta_early.get("graph_skills_proof_pool")
                or pool.proof_source == "augmented_skills_graph"
            )
            if _painting_early:
                from apps_rg.runtime.sections.executive_summary_composition import (
                    build_executive_summary_composition_plan,
                )

                _composition_plan_early = build_executive_summary_composition_plan(
                    selected_facts=list(selected_fact_plan.get("facts") or []),
                    allowed_fact_ids=allowed_fact_ids,
                    target_role=str(
                        getattr(args, "target_role", None)
                        or getattr(args, "target_title", None)
                        or ""
                    ),
                    target_company=str(args.target_company or ""),
                    proof_pool_metadata=_pp_meta_early,
                    briefing_text=str(targeting_ingress.briefing_text_bounded or ""),
                    jd_text=str(targeting_ingress.jd_text or ""),
                )

            if pool.proof_source == "augmented_skills_graph" and graph_only_reformat_allowed():
                from apps_rg.runtime.sections.executive_summary_repair_policy import (
                    graph_only_repair_mode_env_state,
                )
                from apps_rg.runtime.sections.exec_summary_graph_only_quality import (
                    apply_graph_only_generation_quality_repair,
                    parsed_to_raw_model_output_json as _graph_quality_to_raw,
                )
                from apps_rg.runtime.section_repair_ledger import (
                    KIND_DETERMINISTIC_REWRITE,
                    record_repair,
                )

                _plan_facts = list(selected_fact_plan.get("facts") or [])
                parsed, graph_quality_meta = apply_graph_only_generation_quality_repair(
                    parsed,
                    allowed_fact_ids=allowed_fact_ids,
                    plan_facts=_plan_facts,
                    composition_plan=_composition_plan_early,
                    target_role=str(
                        getattr(args, "target_role", None)
                        or getattr(args, "target_title", None)
                        or ""
                    ),
                )
                _lane_attr("write_json", write_json)(artifact_dir / "graph_only_generation_quality_repair.json", graph_quality_meta)
                if graph_quality_meta.get("applied") and not graph_quality_meta.get(
                    "skipped_x2_regression"
                ):
                    record_repair(
                        artifact_dir,
                        kind=KIND_DETERMINISTIC_REWRITE,
                        operation="graph_only_generation_quality_repair",
                        reason=str(
                            graph_quality_meta.get("cross_fact_conflation_reason")
                            or graph_quality_meta.get("mechanical_opener_stack_reason")
                            or graph_quality_meta.get("x2_regression_check")
                            or "graph_only_synthesis_violations"
                        )[:240],
                        replaced_l2=True,
                        detail={
                            "section_id": "executive_summary",
                            "repair_mode": "explicit_graph_only_repair",
                            "explicit_repair_mode": True,
                            "repair_mode_env": graph_only_repair_mode_env_state(),
                            "evidence_authority": "augmented_skills_graph",
                        },
                    )
                raw_output = _graph_quality_to_raw(parsed)
        if parsed and isinstance(parsed, dict):
            coerced_resume = coerce_resume_display_sentence_count_band(
                str(parsed.get("resume_display_text") or ""),
            )
            if coerced_resume != parsed.get("resume_display_text"):
                parsed["resume_display_text"] = coerced_resume
                reconcile_claim_ledger_to_sentence_count(parsed)
            if result.runtime_generation_status == "REAL_LLM":
                raw_output = json.dumps(
                    {k: v for k, v in parsed.items() if k != "selected_fact_plan"},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
    elif str(result.runtime_generation_status) == OFFLINE_CONTRACT_STUB_RUNTIME_STATUS:
        parsed, parse_error = _lane_attr("parse_model_json", parse_model_json)(raw_output)
        if parsed:
            parsed = _lane_attr("normalize_executive_summary_llm_output", normalize_executive_summary_llm_output)(parsed, selected_fact_plan)
        else:
            parsed = None
            if not parse_error:
                parse_error = "offline_contract_stub: model JSON parse failed"
    else:
        parsed = None
        parse_error = result.exact_provider_error or "provider blocked"

    resume_display_text = (parsed or {}).get("resume_display_text") or raw_output or ""
    _pp_meta = proof_pool_metadata if isinstance(proof_pool_metadata, dict) else {}
    _painting_active = bool(  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
        _pp_meta.get("graph_skills_proof_pool") or pool.proof_source == "augmented_skills_graph"
    )
    if parsed and isinstance(parsed, dict) and _painting_active:
        from apps_rg.runtime.sections.executive_summary_composition import (
            attach_composition_to_parsed,
            build_executive_summary_composition_plan,
        )

        parsed["resume_display_text"] = resume_display_text
        _plan_facts = list(selected_fact_plan.get("facts") or [])
        composition_plan = _composition_plan_early if _composition_plan_early is not None else build_executive_summary_composition_plan(
            selected_facts=_plan_facts,
            allowed_fact_ids=allowed_fact_ids,
            target_role=str(
                getattr(args, "target_role", None) or getattr(args, "target_title", None) or ""
            ),
            target_company=str(args.target_company or ""),
            proof_pool_metadata=_pp_meta,
            briefing_text=str(targeting_ingress.briefing_text_bounded or ""),
            jd_text=str(targeting_ingress.jd_text or ""),
        )
        parsed = attach_composition_to_parsed(
            parsed,
            composition_plan,
            resume_display_text=resume_display_text,
        )
        _lane_attr("write_json", write_json)(artifact_dir / "executive_summary_composition_plan.json", composition_plan)
        resume_display_text = str(parsed.get("resume_display_text") or resume_display_text)
        claim_ledger = list(parsed.get("claim_ledger") or [])
    else:
        claim_ledger = list((parsed or {}).get("claim_ledger") or [])
    parse_status, invalid_reason = classify_ledger_parse_state(
        parsed, parse_error=parse_error, raw_output=raw_output
    )
    norm_rows = normalize_exec_summary_claim_ledger(claim_ledger) if parse_status == "OK" else []
    canon_doc = build_canonical_claim_ledger_v2_payload(
        norm_rows,
        parse_status=parse_status,
        invalid_reason=invalid_reason if parse_status != "OK" else None,
    )
    _wg.write_text(artifact_dir / "raw_model_output.txt", raw_output or "", encoding="utf-8")
    _lane_attr("write_json", write_json)(
        artifact_dir / "parsed_output.json",
        {"parsed": parsed, "parse_error": parse_error, "parse_status": parse_status},
    )
    _lane_attr("write_json", write_json)(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)
    if parsed and isinstance(parsed, dict):
        from apps_rg.runtime.sections.section_authority_repairs import (
            apply_exec_summary_display_authority_repairs,
        )

        parsed = apply_exec_summary_display_authority_repairs(
            parsed,
            allowed_fact_ids=allowed_fact_ids,
            plan_facts=list(selected_fact_plan.get("facts") or []),
            artifact_dir=artifact_dir,
            target_company=str(getattr(args, "target_company", "") or ""),
        )
        from apps_rg.runtime.sections.executive_summary_voice_repair import (
            finalize_executive_summary_coherence,
        )

        parsed, finalize_receipt = finalize_executive_summary_coherence(
            parsed,
            selected_facts=list(selected_fact_plan.get("facts") or []),
            allowed_fact_ids=allowed_fact_ids,
            target_role=str(
                getattr(args, "target_role", None)
                or getattr(args, "target_title", None)
                or ""
            ),
            runtime_generation_status=str(runtime_generation_status or ""),
        )
        if artifact_dir is not None:
            _lane_attr("write_json", write_json)(
                artifact_dir / "executive_summary_finalize_coherence.json",
                finalize_receipt,
            )
            if finalize_receipt.get("voice_repair", {}).get("repaired") or finalize_receipt.get(
                "gap_excuses_added"
            ):
                from apps_rg.runtime.section_repair_ledger import (
                    KIND_MECHANICAL,
                    record_repair,
                )

                record_repair(
                    artifact_dir,
                    kind=KIND_MECHANICAL,
                    operation="executive_summary_finalize_coherence",
                    reason=str(
                        finalize_receipt.get("materialization_reason")
                        or "display_ledger_coherence"
                    )[:240],
                    replaced_l2=True,
                )
            if finalize_receipt.get("orphan_citations_stripped") and artifact_dir is not None:
                _lane_attr("write_json", write_json)(
                    artifact_dir / "voice_repair_orphan_citations_stripped.json",
                    {
                        "stripped": list(finalize_receipt.get("orphan_citations_stripped") or []),
                        "allowed_fact_ids": sorted(allowed_fact_ids),
                    },
                )
        resume_display_text = str(parsed.get("resume_display_text") or resume_display_text)
        claim_ledger = list(parsed.get("claim_ledger") or claim_ledger)
        norm_rows = normalize_exec_summary_claim_ledger(claim_ledger) if parse_status == "OK" else []
        canon_doc = build_canonical_claim_ledger_v2_payload(
            norm_rows,
            parse_status=parse_status,
            invalid_reason=invalid_reason if parse_status != "OK" else None,
        )
        _lane_attr("write_json", write_json)(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)
    # W4 last-seam rung: final post-polish display text is known here, X2 has not run yet.
    # ONE bounded regen when the word ceiling (x2_exec_summary_paragraph_max_words) would fail.
    (
        raw_output,
        parsed,
        resume_display_text,
        claim_ledger,
        _word_budget_repair_accepted,
    ) = _lane_attr("apply_exec_summary_word_budget_repair", apply_exec_summary_word_budget_repair)(
        messages=messages,
        provider_payload=provider_payload,
        raw_output=raw_output,
        parsed=parsed,
        resume_display_text=resume_display_text,
        claim_ledger=claim_ledger,
        selected_fact_plan=selected_fact_plan,
        allowed_fact_ids=allowed_fact_ids,
        artifact_dir=artifact_dir,
        runtime_payload=runtime_payload,
        runtime_generation_status=runtime_generation_status,
        target_role=str(
            getattr(args, "target_role", None) or getattr(args, "target_title", None) or ""
        ),
        target_company=str(getattr(args, "target_company", "") or ""),
        run_id=str(runtime_payload.get("run_id") or "") or None,
    )
    coverage = build_sentence_claim_coverage(resume_display_text, claim_ledger, allowed_fact_ids)
    parsed_for_x2 = enrich_parsed_for_x2(
        parsed,
        coverage=coverage,
        input_payload_hash=input_payload_hash,
        allowed_fact_ids=allowed_fact_ids,
        runtime_payload=runtime_payload,
    )
    model_name = resolve_provider_model_name(provider_request_data, provider_result_data)
    selected_facts_for_x2 = list(selected_fact_plan.get("facts") or [])
    temperature = float(args.temperature)

    ctx.update({
        "raw_output": raw_output,
        "parsed": parsed,
        "parse_error": parse_error,
        "_composition_plan_early": _composition_plan_early,
        "_word_budget_repair_accepted": _word_budget_repair_accepted,
        "resume_display_text": resume_display_text,
        "claim_ledger": claim_ledger,
        "parse_status": parse_status,
        "invalid_reason": invalid_reason,
        "canon_doc": canon_doc,
        "coverage": coverage,
        "parsed_for_x2": parsed_for_x2,
        "model_name": model_name,
        "selected_facts_for_x2": selected_facts_for_x2,
        "temperature": temperature,
    })
    run_generation_x2_eval(ctx)
