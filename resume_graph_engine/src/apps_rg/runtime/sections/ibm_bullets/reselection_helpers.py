"""Callbacks bound into ``run_bullet_judge_reselection`` for IBM bullets."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    classify_ledger_parse_state,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.judges.ibm_bullets_x1d import run_ibm_bullets_judges
from apps_rg.runtime.reasoning.bullet_pool_reselection import LaneRebuildState
from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
    strip_employment_bullet_intensity_model,
)
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.sections.executive_summary_lane import write_x2_gate_outputs
from apps_rg.runtime.validators.ibm_bullets_x2 import (
    build_ibm_bullets_text_claim_coverage,
    run_ibm_bullets_x2_gates,
)
from ._parent import parent_attr
from .frozen_allocation import (
    _bind_ibm_change_log_to_frozen_allocation,
    _materialize_ibm_bullets_from_frozen_allocation,
    normalize_parsed_output,
)
from .lane_constants import REPO_ROOT, write_json
from .metric_repairs import (
    align_ibm_claim_ledger_from_canonical_facts,
    demote_gated_ibm_metrics,
    demote_hold_metrics,
    inject_ibm_locked_metric_anchors,
    scrub_cross_slot_plan_metrics,
)
from .provider_io import bullets_display_text


def build_ibm_reselection_callbacks(
    args: argparse.Namespace,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Construct bounded callback dict for ``run_bullet_judge_reselection``."""
    artifact_dir: Path = ctx["artifact_dir"]
    base = ctx["base"]
    pool = ctx["pool"]
    ibm_facts = ctx["ibm_facts"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    selected_fact_plan = ctx["selected_fact_plan"]
    runtime_payload = ctx["runtime_payload"]
    active_bullet_ids = ctx["active_bullet_ids"]
    judge_mode = ctx["judge_mode"]
    allowed_fact_packet = ctx["allowed_fact_packet"]
    pp_x2 = ctx["pp_x2"]
    srfs_slice_x2_active = ctx["srfs_slice_x2_active"]
    model_name = ctx["model_name"]
    raw_output = ctx["raw_output"]
    parse_error = ctx["parse_error"]
    runtime_generation_status = ctx["runtime_generation_status"]
    l2_output = ctx["l2_output"]
    req_id = ctx["req_id"]
    trace_rr = ctx["trace_rr"]
    def _resel_post_chain(doc: dict[str, Any]) -> dict[str, Any]:
        doc = parent_attr("normalize_parsed_output", normalize_parsed_output)(doc, runtime_payload) or doc
        if runtime_generation_status != "REAL_LLM":
            parent_attr("inject_ibm_locked_metric_anchors", inject_ibm_locked_metric_anchors)(doc, plan_facts=ibm_facts, allowed_fact_ids=allowed_fact_ids)
        parent_attr("demote_gated_ibm_metrics", demote_gated_ibm_metrics)(doc)
        if runtime_generation_status != "REAL_LLM":
            parent_attr("demote_hold_metrics", demote_hold_metrics)(doc)
            parent_attr("scrub_cross_slot_plan_metrics", scrub_cross_slot_plan_metrics)(doc, ibm_facts)
        parent_attr("align_ibm_claim_ledger_from_canonical_facts", align_ibm_claim_ledger_from_canonical_facts)(
            doc, plan_facts=ibm_facts, allowed_fact_ids=allowed_fact_ids
        )
        if runtime_generation_status != "REAL_LLM":
            parent_attr("_materialize_ibm_bullets_from_frozen_allocation", _materialize_ibm_bullets_from_frozen_allocation)(
                doc,
                selected_fact_plan=selected_fact_plan,
            )
        parent_attr("_bind_ibm_change_log_to_frozen_allocation", _bind_ibm_change_log_to_frozen_allocation)(
            doc,
            selected_fact_plan=selected_fact_plan,
        )
        return doc

    def _resel_rebuild_state(new_parsed: dict[str, Any]) -> LaneRebuildState:
        new_bullets = list(new_parsed.get("bullets") or [])
        new_ledger = list(new_parsed.get("claim_ledger") or [])
        new_parse_status, new_invalid = parent_attr("classify_ledger_parse_state", classify_ledger_parse_state)(
            new_parsed,
            parse_error=parse_error,
            raw_output=raw_output,
            lane_profile="ibm_bullets",
        )
        new_norm = parent_attr("normalize_exec_summary_claim_ledger", normalize_exec_summary_claim_ledger)(new_ledger) if new_parse_status == "OK" else []
        new_canon = parent_attr("build_canonical_claim_ledger_v2_payload", build_canonical_claim_ledger_v2_payload)(
            new_norm,
            parse_status=new_parse_status,
            invalid_reason=new_invalid if new_parse_status != "OK" else None,
            claim_id_prefix="ibm_bullets_claim",
        )
        new_coverage = parent_attr("build_ibm_bullets_text_claim_coverage", build_ibm_bullets_text_claim_coverage)(
            new_bullets, new_ledger, allowed_fact_ids, active_bullet_ids=active_bullet_ids
        )
        new_parsed_for_x2 = strip_employment_bullet_intensity_model(
            {**new_parsed, "text_claim_coverage": new_coverage}
        ) or {"text_claim_coverage": new_coverage}
        new_usage = parent_attr("build_section_input_usage_ledger_v1", build_section_input_usage_ledger_v1)(
            section_id="ibm_bullets",
            run_id=str(runtime_payload["run_id"]),
            request_id=req_id,
            trace_root=trace_rr,
            repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
            artifact_dir=artifact_dir,
            runtime_payload=runtime_payload,
            selected_fact_plan=new_parsed.get("selected_fact_plan") or l2_output["selected_fact_plan"],
            claim_ledger=new_ledger,
            allowed_fact_ids=allowed_fact_ids,
            jd_text=str(runtime_payload.get("jd_text") or ""),
            target_title=str(runtime_payload.get("target_title") or ""),
            target_company=str(runtime_payload.get("target_company") or ""),
            briefing_text=str(runtime_payload.get("briefing") or ""),
            jd_alignment=l2_output.get("jd_alignment"),
        )
        return LaneRebuildState(
            parsed=new_parsed,
            bullets=new_bullets,
            claim_ledger=new_ledger,
            coverage=new_coverage,
            parsed_for_x2=new_parsed_for_x2,
            canon_doc=new_canon,
            usage_doc=new_usage,
            display_text=parent_attr("bullets_display_text", bullets_display_text)(new_bullets),
            parse_status=new_parse_status,
        )

    def _resel_run_x2(
        state: LaneRebuildState, x1d_rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            g.to_dict()
            for g in parent_attr("run_ibm_bullets_x2_gates", run_ibm_bullets_x2_gates)(
                bullets=state.bullets,
                parsed_output=state.parsed_for_x2,
                claim_ledger=state.claim_ledger,
                allowed_fact_ids=allowed_fact_ids,
                jd_text=args.jd_text,
                runtime_generation_status=runtime_generation_status,
                artifacts_dir=artifact_dir,
                provider_requested=args.provider,
                provider_attempted=args.provider,
                model_name=model_name,
                raw_output=raw_output,
                x1d_judges=x1d_rows,
                srfs_source_fact_slice_gate_active=srfs_slice_x2_active,
                proof_pool_metadata=pp_x2,
                proof_pool_ref=str(pool.proof_pool_ref or ""),
                proof_pool_digest=str(pool.proof_pool_digest or ""),
                base_resume=base,
                runtime_payload=runtime_payload,
            )
        ]

    def _resel_run_judges(state: LaneRebuildState, keys: list[str]) -> list[dict[str, Any]]:
        return [
            j.to_dict()
            for j in parent_attr("run_ibm_bullets_judges", run_ibm_bullets_judges)(
                bullets=state.bullets,
                claim_ledger=state.claim_ledger,
                judge_keys=list(keys),
                mode=judge_mode,
                artifact_base=artifact_dir,
                allowed_fact_packet=allowed_fact_packet,
                targeting_context={
                    "target_title": str(runtime_payload.get("target_title") or ""),
                    "target_company": str(runtime_payload.get("target_company") or ""),
                    "jd_text": str(runtime_payload.get("jd_text") or ""),
                    "briefing": str(runtime_payload.get("briefing") or ""),
                },
            )
        ]

    def _resel_write_usage(state: LaneRebuildState) -> None:
        parent_attr("write_json", write_json)(
            artifact_dir / "section_input_usage_ledger.json",
            parent_attr("apply_proof_pool_to_usage_ledger", apply_proof_pool_to_usage_ledger)(state.usage_doc, pool),
        )

    def _resel_write_artifacts(state: LaneRebuildState, x2_rows: list[dict[str, Any]]) -> None:
        parent_attr("write_json", write_json)(
            artifact_dir / "parsed_output.json",
            {"parsed": state.parsed, "parse_error": parse_error, "parse_status": state.parse_status},
        )
        _wg.write_text(artifact_dir / "ibm_bullets_output.txt", state.display_text + "\n", encoding="utf-8")
        parent_attr("write_json", write_json)(artifact_dir / "claim_ledger.json", state.claim_ledger)
        parent_attr("write_json", write_json)(artifact_dir / "text_claim_coverage.json", state.coverage)
        parent_attr("write_json", write_json)(artifact_dir / "canonical_claim_ledger_v2.json", state.canon_doc)
        _resel_write_usage(state)
        parent_attr("write_x2_gate_outputs", write_x2_gate_outputs)(artifact_dir / "x2_gate_outputs.json", x2_rows, section_id="ibm_bullets")
        parent_attr("write_json", write_json)(
            artifact_dir / "fact_check_result.json",
            {
                "passed": not [g for g in x2_rows if not g["pass"]],
                "failed_gates": [g["gate_id"] for g in x2_rows if not g["pass"]],
            },
        )
        l2_output["bullets"] = state.bullets
        l2_output["claim_ledger"] = state.claim_ledger
        l2_output["selected_fact_plan"] = (
            state.parsed.get("selected_fact_plan") or l2_output["selected_fact_plan"]
        )
        l2_output["gap_notes"] = state.parsed.get("gap_notes") or []
        l2_output["change_log"] = state.parsed.get("change_log") or []
        l2_output["self_check"] = state.parsed.get("self_check") or l2_output["self_check"]
        l2_output["text_claim_coverage"] = state.coverage

    return {
        "post_chain": _resel_post_chain,
        "rebuild_state": _resel_rebuild_state,
        "run_x2": _resel_run_x2,
        "run_judges": _resel_run_judges,
        "write_usage_ledger": _resel_write_usage,
        "write_lane_artifacts": _resel_write_artifacts,
    }
