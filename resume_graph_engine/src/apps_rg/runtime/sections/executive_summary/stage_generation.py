"""Stage 2: Model output parsing, voice repair, and word budget polish."""
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

def run_generation_stage(ctx: dict[str, Any]) -> None:
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

    write_json(artifact_dir / "provider_response.json", provider_result_data)
    parse_error = ""
    _composition_plan_early: dict[str, Any] | None = None
    if result.runtime_generation_status == "REAL_LLM":
        parsed, parse_error = parse_model_json(raw_output)
        if parsed and str(args.provider) == "external_claude":
            from apps_rg.runtime.sections.executive_summary_pa import (
                is_strategy_executive_target_title,
            )

            _target_role_for_regen = str(
                runtime_payload.get("target_role")
                or runtime_payload.get("target_title")
                or ""
            ).strip()
            raw_output, parsed, parse_error = retry_provider_for_synthesis(
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
            parsed = normalize_executive_summary_llm_output(parsed, selected_fact_plan)
            prune_exec_summary_claim_ledger_orphans(parsed, allowed_fact_ids)
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
                write_json(artifact_dir / "graph_only_generation_quality_repair.json", graph_quality_meta)
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
        parsed, parse_error = parse_model_json(raw_output)
        if parsed:
            parsed = normalize_executive_summary_llm_output(parsed, selected_fact_plan)
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
        write_json(artifact_dir / "executive_summary_composition_plan.json", composition_plan)
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
    write_json(
        artifact_dir / "parsed_output.json",
        {"parsed": parsed, "parse_error": parse_error, "parse_status": parse_status},
    )
    write_json(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)
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
        )
        if artifact_dir is not None:
            write_json(
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
                write_json(
                    artifact_dir / "voice_repair_orphan_citations_stripped.json",
                    {
                        "stripped": list(finalize_receipt.get("orphan_citations_stripped") or []),
                        "allowed_fact_ids": sorted(allowed_fact_ids),
                    },
                )
        resume_display_text = str(parsed.get("resume_display_text") or resume_display_text)
        claim_ledger = list(parsed.get("claim_ledger") or claim_ledger)
    # W4 last-seam rung: final post-polish display text is known here, X2 has not run yet.
    # ONE bounded regen when the word ceiling (x2_exec_summary_paragraph_max_words) would fail.
    (
        raw_output,
        parsed,
        resume_display_text,
        claim_ledger,
        _word_budget_repair_accepted,
    ) = apply_exec_summary_word_budget_repair(
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
    write_json(artifact_dir / "l2_output.json", l2_output)
    _wg.write_text(artifact_dir / "resume_display_text.txt", resume_display_text + "\n", encoding="utf-8")
    write_json(artifact_dir / "selected_fact_plan.json", l2_output["selected_fact_plan"])
    write_json(artifact_dir / "claim_ledger.json", claim_ledger)
    write_json(artifact_dir / "text_claim_coverage.json", coverage)
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
        jd_text=_strip_targeting_cap_notice(
            str(runtime_payload.get("jd_text") or "") or _generation_material.jd_text_material
        ),
        target_title=_args_target_title(args),
        target_company=str(args.target_company),
        briefing_text=_strip_targeting_cap_notice(
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
        write_json_fn=write_json,
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
    write_json(artifact_dir / "prompt_selection_trace.json", trace)
    write_x2_gate_outputs(artifact_dir / "x2_gate_outputs.json", [], section_id="executive_summary")

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
    write_x2_gate_outputs(artifact_dir / "x2_gate_outputs.json", x2, section_id="executive_summary")
    from apps_rg.runtime.section_repair_ledger import load_ledger, record_x2_run

    _ledger = load_ledger(artifact_dir) or {}
    record_x2_run(
        artifact_dir,
        run_number=len(list(_ledger.get("x2_runs") or [])) + 1,
        after_l2_source=str(_ledger.get("authoritative_l2_source") or "initial_llm"),
        x2_gates=x2,
    )
    x2_failed_initial = [g for g in x2 if not g["pass"]]


    ctx["provider_result_data"] = provider_result_data
    ctx["raw_output"] = raw_output
    ctx["runtime_generation_status"] = runtime_generation_status
    ctx["parsed"] = parsed
    ctx["parse_error"] = parse_error
    ctx["resume_display_text"] = resume_display_text
    ctx["claim_ledger"] = claim_ledger
    ctx["_word_budget_repair_accepted"] = _word_budget_repair_accepted
    ctx["_word_budget_repair_audit"] = _word_budget_repair_audit
    ctx["_composition_plan_early"] = _composition_plan_early
    ctx["parsed_for_x2"] = parsed_for_x2
    ctx["x2"] = x2
    ctx["_generation_material"] = _generation_material
    ctx["_bundle_mat"] = _bundle_mat
    ctx["_targeting_parity"] = _targeting_parity
    ctx["usage_doc"] = usage_doc
