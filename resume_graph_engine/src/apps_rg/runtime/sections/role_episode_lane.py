"""Generic proof-bound role episode lanes for InsurTech/EY sections.

These lanes intentionally fail closed when upstream graph/FEC evidence is absent.
They do not hydrate claims from the base resume or targeting text.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from apps_rg.runtime.c0.section_proof_loader import (
    apply_proof_pool_to_usage_ledger,
    load_section_proof_for_lane,
)
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.exit.executive_summary_x3 import aggregate_x3
from apps_rg.runtime.providers import (
    ExternalProvider,
    ProviderGateway,
    ProviderGatewayError,
    ProviderProfile,
)
from apps_rg.runtime.reasoning.bullet_lane_generation import generate_bullet_lane_with_sc_and_claude
from apps_rg.runtime.runtime_proof_layout import (
    finalize_runtime_proof_run,
    prepare_runtime_proof_run_dir,
    rel_posix,
)
from apps_rg.runtime.section_l2_lane_integration import (
    finalize_section_l2_after_output,
    prepare_section_l2_before_provider,
)
from apps_rg.runtime.section_model_limits import (
    external_claude_generation_model,
    external_openai_generation_model,
)
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.section_runtime_exhaust_lane_integration import (
    finalize_section_runtime_exhaust_before_l6,
    gate_section_l6_shadow_after_exhaust,
)
from apps_rg.runtime.sections.lane_artifact_io import runtime_payload_for_json, sha16, write_json
from apps_rg.runtime.sections.role_episode import (
    MAX_OUTPUT_TOKENS,
    REPO_ROOT,
    ROLE_EPISODE_FINAL_BULLET_COUNT,
    ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
    ROLE_EPISODE_GRAPH_BULLET_RENDERER_VERSION,
    ROLE_EPISODE_MAX_OUTPUT_TOKENS_BY_SECTION,
    ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION,
    ROLE_EPISODE_X2_GATE_IDS_BY_RUN_FUNCTION,
    ROLE_EPISODE_X2_RUN_FUNCTION_BY_SECTION,
    RoleEpisodeLaneConfig,
    _MODEL_SURFACE_NON_ANCHOR_TOKENS,
    _NARRATIVE_LEDGER_STOPWORDS,
    _NARRATIVE_SOURCE_BINDING_PATTERNS,
    _PROOF_FACT_COMPOSITION_CONNECTIVES,
    _PROOF_FACT_SURFACE_COMPOSITIONS,
    _ROLE_EPISODE_EVIDENCE_DENSITY_REPAIRS,
    _ROLE_LANES,
    _TARGETING_ONLY_EXPERIENCE_MARKERS,
    _TARGETING_ONLY_TAIL_REPAIRS,
    _X1D_WIRING_GATE_IDS,
    _blocked_provider_result,
    _claim_ledger_from_bullets,
    _compact_text,
    _compiled_prompt,
    _deterministic_graph_bullet_render,
    _display_text,
    _display_text_for_x2,
    _display_text_is_proof_authorized,
    _fact_id_from_row,
    _facts_from_plan,
    _has_first_person,
    _json_hash,
    _judge_rows,
    _llm_generation_status,
    _materialize_bullet_generation,
    _max_output_tokens_for_lane,
    _model_bullet_surface_binding,
    _narrative_from_parsed,
    _narrative_ledger_tokens,
    _narrative_source_ids_for_claim,
    _normalize_bullets,
    _normalize_role_episode_bullet_pool_parsed,
    _normalize_source_ids,
    _ordered_ids_from_bullets,
    _ordered_ids_from_bullets_with_contract,
    _parse_json_object,
    _parsed_claim_ledger_source_ids_for_narrative,
    _prompt_object,
    _proof_authorized_bullets_from_selection,
    _proof_authorized_bullets_from_selection_with_contract,
    _proof_authorized_narrative_from_selection,
    _proof_fact_by_id,
    _proof_fact_composition_is_bound,
    _proof_fact_surface_tokens,
    _proof_fact_text,
    _reconcile_final_materialized_selection_gate,
    _repair_role_episode_bullet_evidence_density,
    _role_episode_evidence_block,
    _role_header,
    _selected_fact_plan_authorized_texts,
    _sentence,
    _source_fact_ids_from_bullets,
    _source_ids_from_parsed_claim_ledger,
    _strip_targeting_only_experience_claims,
    _targeting_only_experience_hits,
    _valid_source_ids_without_fallback,
    _write_blocked_artifacts,
    _x2_gate,
    _x2_gates,
    build_role_episode_lane_args,
    run_ey_bullets_x2_gates,
    run_ey_narrative_x2_gates,
    run_insurtech_bullets_x2_gates,
    run_insurtech_narrative_x2_gates,
    run_role_episode_generation_stage,
    run_role_episode_ingress_stage,
    run_role_episode_x2_gates,
    run_slalom_bullets_x2_gates,
    run_slalom_narrative_x2_gates,
)
from apps_rg.runtime.sections.section_final_materialized_binding import (
    augment_x2_payload_with_final_materialized_binding,
)
from apps_rg.runtime.shadow.l6_handoff_packet import build_l6_shadow_handoff_dict
from apps_rg.runtime.spine.c0_fec_compose import merge_compiled_prompt_artifact_fec_fields
from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3
from apps_rg.runtime.validators.companion_bullet_finalization import load_role_episode_companion_bullets
from apps_rg.runtime.validators.proof_pool_source_fact_validation import write_x2_source_fact_pool_receipt


def _provider_gateway(section_id: str, provider: str) -> ProviderGateway:
    provider_key = str(provider or "").strip().lower()
    if provider_key == ProviderProfile.EXTERNAL_OPENAI.value:
        openai_model = external_openai_generation_model(section_id=section_id)
        return ProviderGateway(
            {
                ProviderProfile.EXTERNAL_OPENAI: ExternalProvider(
                    provider_profile=ProviderProfile.EXTERNAL_OPENAI,
                    model=openai_model,
                    base_url=os.environ.get("APPS_RG_EXTERNAL_OPENAI_BASE_URL", ""),
                ),
            }
        )
    claude_model = external_claude_generation_model(section_id=section_id)
    return ProviderGateway(
        {
            ProviderProfile.EXTERNAL_CLAUDE: ExternalProvider(
                provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
                model=claude_model,
                base_url=os.environ.get("APPS_RG_EXTERNAL_CLAUDE_BASE_URL", ""),
            ),
        }
    )


def run_role_episode_lane_execution(
    section_id: str,
    args: Any,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Execute a role-episode section lane; narrative sections route through role_narrative_v2."""
    if str(section_id or "").strip().lower() in {"slalom_narrative", "insurtech_narrative", "ey_narrative"}:
        from apps_rg.runtime.sections.role_narrative_v2 import run_role_narrative_v2
        return run_role_narrative_v2(
            section_id,
            args,
            artifact_dir_override=artifact_dir_override,
        )
    return _run_role_episode_pipeline_internal(
        section_id,
        args,
        artifact_dir_override=artifact_dir_override,
    )


def _run_role_episode_pipeline_internal(
    section_id: str,
    args: Any,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Internal role-episode execution pipeline for bullet and narrative role-episode contracts."""
    ctx, early_return = run_role_episode_ingress_stage(
        section_id,
        args,
        artifact_dir_override=artifact_dir_override,
    )
    if early_return is not None:
        return early_return
    ctx = run_role_episode_generation_stage(
        args,
        ctx,
        provider_gateway_fn=_provider_gateway,
    )
    sid = ctx["sid"]
    cfg = ctx["cfg"]
    max_output_tokens = ctx["max_output_tokens"]
    run_id = ctx["run_id"]
    artifact_dir: Path = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    pool = ctx["pool"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    prompt_hash = ctx["prompt_hash"]
    provider_result = ctx["provider_result"]
    parsed = ctx["parsed"]
    parse_error = ctx["parse_error"]
    claim_ledger = ctx["claim_ledger"]
    generation_receipt = ctx["generation_receipt"]
    l2 = ctx["l2"]
    x2 = ctx["x2"]
    product_quality_status = ctx["product_quality_status"]
    lane_status = ctx["lane_status"]
    x1d = ctx["x1d"]
    usage_doc = ctx["usage_doc"]
    x3 = ctx["x3"]
    failed = ctx["failed"]
    proof_display_gate = ctx["proof_display_gate"]
    proof_display_obs = ctx["proof_display_obs"]
    output_text = _display_text(l2, cfg)
    (artifact_dir / cfg.output_filename).write_text(
        output_text + ("\n" if output_text else ""),
        encoding="utf-8",
    )
    (artifact_dir / "command_output.txt").write_text(
        output_text + ("\n" if output_text else ""),
        encoding="utf-8",
    )
    write_json(
        artifact_dir / "text_claim_coverage.json",
        {
            "source_fact_ids_checked": allowed_fact_ids,
            "claims": claim_ledger,
            "display_text_authority": l2.get("display_text_authority"),
            "display_text_proof_authorized": bool(proof_display_gate.get("pass")),
            "proof_authorized_rows": proof_display_obs.get("rows") or [],
        },
    )
    write_json(artifact_dir / "parsed_output.json", {"parsed": parsed, "parse_error": parse_error})
    write_json(
        artifact_dir / "x2_gate_outputs.json",
        augment_x2_payload_with_final_materialized_binding(
            {
                "gates": x2,
                "x2_failed": len(failed),
                "x2_passed": len(x2) - len(failed),
                "failed_gates": failed,
            },
            artifact_dir=artifact_dir,
            section_id=sid,
        ),
    )
    write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": x1d})
    # Single-spine authority (E2E-14): aggregate_x3 above is judge math only; the spine finalize
    # helper owns the x3_disposition.json mirror. The real ExitEvalPipeline runs after sealed L2
    # via finalize_section_l2_after_output (called below).
    x3 = finalize_section_lane_x3(
        artifact_dir=artifact_dir,
        section_id=sid,
        runtime_payload=runtime_payload,
        x3_result=x3,
    )
    write_json(artifact_dir / "section_input_usage_ledger.json", usage_doc)
    write_json(
        artifact_dir / "real_l2_generation_result.json",
        {
            **provider_result.to_dict(),
            "product_quality_status": product_quality_status,
            "lane_status": lane_status,
            **generation_receipt,
            "generation_receipt": generation_receipt,
        },
    )
    write_json(
        artifact_dir / "section_metric_receipt.json",
        {
            "lane_id": sid,
            "run_id": run_id,
            "runtime_generation_status": provider_result.runtime_generation_status,
            "product_quality_status": product_quality_status,
            "lane_status": lane_status,
            "x2_failed_gates": failed,
            "x3_code": x3.x3_code,
            "prompt_hash": prompt_hash[:16],
            **generation_receipt,
            "generation_receipt": generation_receipt,
        },
    )
    for gate in x2:
        obs = gate.get("observed_value")
        if isinstance(obs, dict) and obs.get("x2_source_fact_pool_status"):
            write_x2_source_fact_pool_receipt(artifact_dir, obs)
            break
    if not (artifact_dir / "x2_source_fact_pool_receipt.json").is_file():
        write_json(
            artifact_dir / "x2_source_fact_pool_receipt.json",
            {
                "x2_source_fact_pool_status": "PASS" if allowed_fact_ids else "FAIL",
                "source_fact_ids_checked": allowed_fact_ids,
                "proof_pool_ref": pool.proof_pool_ref,
                "proof_pool_digest": pool.proof_pool_digest,
                "generation_method": generation_receipt.get("generation_method"),
                "llm_generation_status": generation_receipt.get("llm_generation_status"),
                "llm_output_used": generation_receipt.get("llm_output_used"),
                "evidence_authority": generation_receipt.get("evidence_authority"),
                "rendered_source_fact_ids": generation_receipt.get("source_fact_ids"),
                "graph_packet_digest": generation_receipt.get("graph_packet_digest"),
                "renderer_version": generation_receipt.get("renderer_version"),
            },
        )
    else:
        pool_receipt_path = artifact_dir / "x2_source_fact_pool_receipt.json"
        try:
            pool_receipt = json.loads(pool_receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pool_receipt = {}
        if isinstance(pool_receipt, dict):
            pool_receipt.update(
                {
                    "generation_method": generation_receipt.get("generation_method"),
                    "llm_generation_status": generation_receipt.get("llm_generation_status"),
                    "llm_output_used": generation_receipt.get("llm_output_used"),
                    "evidence_authority": generation_receipt.get("evidence_authority"),
                    "rendered_source_fact_ids": generation_receipt.get("source_fact_ids"),
                    "graph_packet_digest": generation_receipt.get("graph_packet_digest"),
                    "renderer_version": generation_receipt.get("renderer_version"),
                }
            )
            write_json(pool_receipt_path, pool_receipt)
    finalize_section_l2_after_output(artifact_dir, sid, runtime_payload)
    # Role-episode lanes share the same product-visible L6 identity contract as
    # the dedicated lanes.  Their former hand-written summary bypassed the
    # post-exit RuntimeExhaustBundle, so Apps Eval could not bind the section
    # attempt to the sealed source.  Build the standard handoff only after L2
    # and Exit are sealed; L6 remains future-run-only and cannot rescue X3.
    finalize_section_runtime_exhaust_before_l6(
        artifact_dir,
        sid,
        runtime_payload,
        repo_root=REPO_ROOT,
    )
    gate_section_l6_shadow_after_exhaust(artifact_dir, runtime_payload)
    l6_package = build_l6_shadow_handoff_dict(
        artifact_dir=artifact_dir,
        repo_root=REPO_ROOT,
        section_id=sid,
        prompt_id=str(l2.get("prompt_id") or "role_episode_lane"),
        temperature=float(args.temperature),
        max_tokens=max_output_tokens,
        runtime_payload=runtime_payload,
    )
    l6_package.update(
        {
            "status": "captured",
            "x3_code": x3.x3_code,
            "prompt_hash": prompt_hash[:16],
            "current_run_mutated": False,
            "current_run_mutation_assertion": False,
            "current_run_x3_mutation_assertion": False,
            "direct_l4_write_attempted": False,
            "direct_l4_write_assertion": False,
            "durable_write_attempted": False,
        }
    )
    write_json(artifact_dir / "l6_shadow_eval_package.json", l6_package)
    finalize_runtime_proof_run(
        REPO_ROOT,
        sid,
        str(args.provider),
        artifact_dir,
        run_id=run_id,
        section_id=sid,
        runtime_generation_status=provider_result.runtime_generation_status,
        provider_requested=str(args.provider),
        provider_attempted=provider_result.provider_attempted,
    )
    return {
        "artifact_dir": str(artifact_dir),
        "runtime_payload": runtime_payload,
        "x3": x3,
        "output_text": output_text,
    }


__all__ = [
    "ROLE_EPISODE_X2_GATE_IDS_BY_RUN_FUNCTION",
    "ROLE_EPISODE_X2_RUN_FUNCTION_BY_SECTION",
    "ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT",
    "build_role_episode_lane_args",
    "run_ey_bullets_x2_gates",
    "run_ey_narrative_x2_gates",
    "run_insurtech_bullets_x2_gates",
    "run_insurtech_narrative_x2_gates",
    "run_role_episode_lane_execution",
    "run_role_episode_x2_gates",
    "run_slalom_bullets_x2_gates",
    "run_slalom_narrative_x2_gates",
]
