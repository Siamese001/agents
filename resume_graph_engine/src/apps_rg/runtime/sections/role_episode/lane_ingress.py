"""Stage 1: Role-episode ingress, proof pool resolution, prompt compile, and blocked exit."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from apps_rg.runtime.c0.section_proof_loader import load_section_proof_for_lane
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import build_canonical_claim_ledger_v2_payload
from apps_rg.runtime.reasoning.employment_bullet_pool import FINAL_BULLET_COUNT, REQUIRED_BULLET_IDS
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
    resolve_section_generation_effort,
)
from apps_rg.runtime.section_runtime_exhaust_lane_integration import (
    finalize_section_runtime_exhaust_before_l6,
    gate_section_l6_shadow_after_exhaust,
)
from apps_rg.runtime.sections.lane_artifact_io import runtime_payload_for_json, write_json
from apps_rg.runtime.sections.section_final_materialized_binding import (
    augment_x2_payload_with_final_materialized_binding,
)
from apps_rg.runtime.sections.upstream_evidence_block import wire_spine_c0_fec_or_block
from apps_rg.runtime.spine.c0_fec_compose import merge_compiled_prompt_artifact_fec_fields
from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3
from apps_rg.runtime.validators.companion_bullet_finalization import load_role_episode_companion_bullets
from ._parent import parent_attr
from .lane_config import (
    REPO_ROOT,
    ROLE_EPISODE_FINAL_BULLET_COUNT,
    ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
    RoleEpisodeLaneConfig,
    _ROLE_LANES,
    _facts_from_plan,
    _max_output_tokens_for_lane,
    _role_header,
)
from .materialization import _llm_generation_status
from .prompt_compiler import _compiled_prompt, _prompt_object
from .x2_gates import _x2_gate

def _write_blocked_artifacts(
    *,
    cfg: RoleEpisodeLaneConfig,
    args: Any,
    artifact_dir: Path,
    runtime_payload: dict[str, Any],
    reason: str,
    status: str,
) -> dict[str, Any]:
    x2 = [parent_attr("_x2_gate", _x2_gate)(f"x2_{cfg.section_id}_required_proof_present", False, reason)]
    l2 = {
        "run_id": runtime_payload["run_id"],
        "section_id": cfg.section_id,
        "runtime_generation_status": status,
        "product_quality_status": "FAIL",
        "product_quality_reason": reason,
        cfg.header_key: parent_attr("_role_header", _role_header)({}, cfg, args),
        "bullets": [] if cfg.is_bullet_lane else None,
        "narrative_sentence": "" if not cfg.is_bullet_lane else None,
        "claim_ledger": [],
        "selected_fact_plan": {},
        "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
        "self_check": {"blocked_reason": reason},
    }
    l2 = {k: v for k, v in l2.items() if v is not None}
    x3 = {
        "x3_code": "X3_BLOCK",
        "pass": False,
        "pass_": False,
        "runtime_generation_status": status,
        "product_quality_status": "FAIL",
        "decisive_reason": reason,
        "authorization_scope": "PLUMBING_ONLY",
        "required_remediation": [reason],
    }
    generation_model = (
        external_openai_generation_model(section_id=cfg.section_id)
        if str(args.provider) == "external_openai"
        else external_claude_generation_model(section_id=cfg.section_id)
    )
    max_output_tokens = _max_output_tokens_for_lane(cfg)
    provider_req = {
        "provider_requested": str(args.provider),
        "provider_attempted": False,
        "model": generation_model,
        "temperature": float(args.temperature),
        "max_tokens": max_output_tokens,
        "mock_fallback_allowed": False,
        "blocked_before_provider": True,
    }
    provider_resp = {
        "provider_requested": str(args.provider),
        "provider_attempted": False,
        "provider_available": False,
        "runtime_generation_status": status,
        "exact_provider_error": reason,
    }
    parent_attr("write_json", write_json)(artifact_dir / "runtime_payload.json", runtime_payload)
    parent_attr("write_json", write_json)(artifact_dir / "provider_request.json", provider_req)
    parent_attr("write_json", write_json)(artifact_dir / "provider_response.json", provider_resp)
    parent_attr("write_json", write_json)(artifact_dir / "l2_output.json", l2)
    if cfg.is_bullet_lane:
        expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT)
        parent_attr("write_json", write_json)(
            artifact_dir / ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
            {
                "schema_version": "role_episode_final_materialized_selection_contract.v1",
                "expected_bullet_count": expected_bullet_count,
                "model_bullet_count": 0,
                "selected_source_fact_ids": [],
                "selected_unique_source_fact_count": 0,
                "duplicate_source_fact_ids_ignored": [],
                "rejected_source_fact_ids": [],
                "deterministic_reselect_source_fact_ids": [],
                "deterministic_reselect_applied": False,
                "rendered_bullet_count": 0,
                "rendered_source_fact_ids": [],
                "final_materialized_acceptance_ok": False,
                "blocked_reason": reason,
            },
        )
    parent_attr("write_json", write_json)(artifact_dir / "parsed_output.json", {"parsed": None, "parse_error": reason})
    parent_attr("write_json", write_json)(artifact_dir / "claim_ledger.json", [])
    parent_attr("write_json", write_json)(artifact_dir / "canonical_claim_ledger_v2.json", parent_attr("build_canonical_claim_ledger_v2_payload", build_canonical_claim_ledger_v2_payload)([], parse_status="BLOCKED", invalid_reason=reason))
    parent_attr("write_json", write_json)(artifact_dir / "selected_fact_plan.json", {})
    parent_attr("write_json", write_json)(artifact_dir / "text_claim_coverage.json", {"status": "BLOCKED", "reason": reason})
    parent_attr("write_json", write_json)(
        artifact_dir / "x2_gate_outputs.json",
        parent_attr("augment_x2_payload_with_final_materialized_binding", augment_x2_payload_with_final_materialized_binding)(
            {
                "gates": x2,
                "x2_failed": 1,
                "x2_passed": 0,
                "failed_gates": [x2[0]["gate_id"]],
            },
            artifact_dir=artifact_dir,
            section_id=cfg.section_id,
        ),
    )
    parent_attr("write_json", write_json)(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": []})
    # Single-spine authority (E2E-14): route the x3 mirror through the spine finalize helper
    # rather than writing x3_disposition.json raw. No sealed L2 exists on this pre-provider block
    # path, so exit receipts are skipped (default); the spine still owns the mirror.
    parent_attr("finalize_section_lane_x3", finalize_section_lane_x3)(
        artifact_dir=artifact_dir,
        section_id=cfg.section_id,
        runtime_payload=runtime_payload,
        x3_result=x3,
    )
    parent_attr("write_json", write_json)(artifact_dir / "l6_shadow_eval_package.json", {"section_id": cfg.section_id, "status": "BLOCKED", "reason": reason})
    parent_attr("write_json", write_json)(artifact_dir / "real_l2_generation_result.json", provider_resp)
    parent_attr("write_json", write_json)(artifact_dir / "section_metric_receipt.json", {"lane_id": cfg.section_id, "runtime_generation_status": status, "x3_code": "X3_BLOCK"})
    (artifact_dir / cfg.output_filename).write_text("", encoding="utf-8")
    (artifact_dir / "command_output.txt").write_text(f"{cfg.section_id}: {status}: {reason}\n", encoding="utf-8")
    parent_attr("finalize_runtime_proof_run", finalize_runtime_proof_run)(
        parent_attr("REPO_ROOT", REPO_ROOT),
        cfg.section_id,
        str(args.provider),
        artifact_dir,
        run_id=str(runtime_payload["run_id"]),
        section_id=cfg.section_id,
        runtime_generation_status=status,
        provider_requested=str(args.provider),
        provider_attempted=False,
    )
    return {
        "artifact_dir": str(artifact_dir),
        "runtime_payload": runtime_payload,
        "x3": x3,
        "output_text": "",
    }


def run_role_episode_ingress_stage(
    section_id: str,
    args: Any,
    *,
    artifact_dir_override: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Execute ingress/proof-pool binding/prompt compile; returns ``(ctx, early_return)``."""
    sid = str(section_id or "").strip().lower()
    cfg = _ROLE_LANES[sid]
    max_output_tokens = _max_output_tokens_for_lane(cfg)
    run_id = f"{sid}_{uuid.uuid4().hex[:12]}"
    artifact_dir = (
        Path(artifact_dir_override)
        if artifact_dir_override is not None
        else parent_attr("prepare_runtime_proof_run_dir", prepare_runtime_proof_run_dir)(parent_attr("REPO_ROOT", REPO_ROOT), sid, str(args.provider), run_id)
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    runtime_payload: dict[str, Any] = {
        "run_id": run_id,
        "request_id": run_id,
        "section_id": sid,
        "target_company": str(getattr(args, "target_company", "") or ""),
        "target_title": str(getattr(args, "target_title", "") or getattr(args, "target_role", "") or ""),
        "target_role": str(getattr(args, "target_role", "") or ""),
        "jd_text": str(getattr(args, "jd_text", "") or ""),
        "briefing": str(getattr(args, "briefing", "") or ""),
        "provider_requested": str(args.provider),
        "product_visible": True,
    }
    try:
        pool, base, _base_path, base_hash, front_spine = parent_attr("load_section_proof_for_lane", load_section_proof_for_lane)(
            section_id=sid,
            args=args,
            repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
            artifact_dir=artifact_dir,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        runtime_payload["runtime_generation_status"] = "REQUIRED_PROOF_ABSENT"
        runtime_payload["blocked_exception_type"] = type(exc).__name__
        runtime_payload["blocked_exception_message"] = str(exc)
        return {}, parent_attr("_write_blocked_artifacts", _write_blocked_artifacts)(
            cfg=cfg,
            args=args,
            artifact_dir=artifact_dir,
            runtime_payload=runtime_payload,
            reason=f"required upstream proof absent for {sid} ({type(exc).__name__}): {exc}",
            status="REQUIRED_PROOF_ABSENT",
        )

    selected_fact_plan = dict(pool.selected_fact_plan or {})
    allowed_fact_ids = list(pool.allowed_fact_ids_ordered or [])
    facts = _facts_from_plan(selected_fact_plan)
    if (not allowed_fact_ids or not facts) and sid not in ("ey_bullets", "ey_narrative"):
        runtime_payload["runtime_generation_status"] = "REQUIRED_PROOF_ABSENT"
        return {}, parent_attr("_write_blocked_artifacts", _write_blocked_artifacts)(
            cfg=cfg,
            args=args,
            artifact_dir=artifact_dir,
            runtime_payload=runtime_payload,
            reason=f"required upstream proof absent for {sid}: empty allowed facts",
            status="REQUIRED_PROOF_ABSENT",
        )

    runtime_payload.update(
        {
            "base_resume_json_hash": base_hash,
            "selected_fact_plan": selected_fact_plan,
            "allowed_fact_ids": allowed_fact_ids,
            "proof_pool_ref": pool.proof_pool_ref,
            "proof_pool_digest": pool.proof_pool_digest,
            "proof_pool_metadata": dict(pool.proof_pool_metadata or {}),
        }
    )

    blocked = parent_attr("wire_spine_c0_fec_or_block", wire_spine_c0_fec_or_block)(
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        artifact_dir=artifact_dir,
        section_id=sid,
        front_spine=front_spine,
        pool=pool,
        runtime_payload=runtime_payload,
        provider=str(args.provider),
        temperature=float(args.temperature),
        max_tokens=max_output_tokens,
        output_filename=cfg.output_filename,
    )
    if blocked is not None:
        return blocked

    # C0/FEC may replace the loader's local candidate plan with the frozen
    # whole-resume allocation.  Refresh every local projection input before
    # prompt execution and deterministic rendering; otherwise the final text
    # can be rendered from a stale per-lane plan while its provenance names the
    # new allocation digest.
    selected_fact_plan = dict(runtime_payload.get("selected_fact_plan") or selected_fact_plan)
    allowed_fact_ids = list(runtime_payload.get("allowed_fact_ids") or allowed_fact_ids)
    facts = _facts_from_plan(selected_fact_plan)
    if (not allowed_fact_ids or not facts) and sid not in ("ey_bullets", "ey_narrative"):
        runtime_payload["runtime_generation_status"] = "REQUIRED_PROOF_ABSENT"
        return {}, parent_attr("_write_blocked_artifacts", _write_blocked_artifacts)(
            cfg=cfg,
            args=args,
            artifact_dir=artifact_dir,
            runtime_payload=runtime_payload,
            reason=f"required upstream proof absent for {sid}: empty frozen allocation slice",
            status="REQUIRED_PROOF_ABSENT",
        )

    companion_ctx, companion_text = parent_attr("load_role_episode_companion_bullets", load_role_episode_companion_bullets)(
        parent_attr("REPO_ROOT", REPO_ROOT), section_id=sid, role_key=cfg.role_key, is_bullet_lane=cfg.is_bullet_lane,
        required_bullet_ids=tuple(REQUIRED_BULLET_IDS.get(f"{cfg.role_key}_bullets", ())), artifact_dir=artifact_dir,
    )
    if not cfg.is_bullet_lane and companion_text:
        runtime_payload.update({"companion_bullets_context": companion_ctx, "companion_bullet_texts": companion_text})
        parent_attr("write_json", write_json)(artifact_dir / f"companion_{cfg.role_key}_bullets_context.json", companion_ctx)
        (artifact_dir / f"companion_{cfg.role_key}_bullets_context.txt").write_text(companion_text + "\n", encoding="utf-8")

    prompt_text = parent_attr("_compiled_prompt", _compiled_prompt)(cfg, runtime_payload)
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    compiled_obj = parent_attr("_prompt_object", _prompt_object)(prompt_text, run_id=run_id, prompt_hash=prompt_hash)
    compiled_obj.reasoning_effort = resolve_section_generation_effort(
        sid, provider_profile=str(args.provider)
    )
    parent_attr("write_json", write_json)(artifact_dir / "runtime_payload.json", runtime_payload)
    (artifact_dir / "compiled_prompt.txt").write_text(prompt_text + "\n", encoding="utf-8")
    parent_attr("write_json", write_json)(
        artifact_dir / "compiled_prompt_artifact.json",
        parent_attr("merge_compiled_prompt_artifact_fec_fields", merge_compiled_prompt_artifact_fec_fields)(
            {
                "section_id": sid,
                "apps_rg_prompt_template_ref": f"apps_rg/prompt_assembly/templates/{sid}{'_tailor_v1' if '_bullets' in sid else '_v1'}.yaml",
                "compiler_template_id": f"{sid}_role_episode_v1",
                "pa_prompt_hash": prompt_hash[:16],
                "provider_prompt_hash": prompt_hash[:16],
                "slot_count": len(facts),
            },
            runtime_payload,
        ),
    )
    parent_attr("prepare_section_l2_before_provider", prepare_section_l2_before_provider)(
        artifact_dir,
        sid,
        runtime_payload,
        provider_lane=str(args.provider),
    )

    generation_model = (
        external_openai_generation_model(section_id=sid)
        if str(args.provider) == "external_openai"
        else external_claude_generation_model(section_id=sid)
    )
    ctx: dict[str, Any] = {
        "sid": sid,
        "cfg": cfg,
        "max_output_tokens": max_output_tokens,
        "run_id": run_id,
        "artifact_dir": artifact_dir,
        "runtime_payload": runtime_payload,
        "pool": pool,
        "base": base,
        "base_hash": base_hash,
        "selected_fact_plan": selected_fact_plan,
        "allowed_fact_ids": allowed_fact_ids,
        "facts": facts,
        "companion_text": companion_text,
        "prompt_text": prompt_text,
        "prompt_hash": prompt_hash,
        "compiled_obj": compiled_obj,
        "generation_model": generation_model,
    }
    return ctx, None
