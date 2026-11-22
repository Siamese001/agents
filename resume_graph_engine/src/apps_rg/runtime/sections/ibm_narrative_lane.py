"""Public facade for ibm_narrative_lane delegating to role_narrative_v2 (<=120 LOC)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from apps_rg.runtime.sections.executive_summary_lane import write_x2_gate_outputs
from apps_rg.runtime.sections.ibm_narrative_lane_defaults import (
    BRIEFING_DEFAULT, JD_TEXT_DEFAULT, NARRATIVE_TEMP_DEFAULT, NARRATIVE_TEMP_DEFAULT as IBM_NARRATIVE_TEMP_DEFAULT,
    PROMPT_ID, REPO_ROOT as _DEFAULT_REPO_ROOT, TARGET_COMPANY_DEFAULT, TARGET_TITLE_DEFAULT,
)
from apps_rg.runtime.sections.lane_artifact_io import sha16, write_json
from apps_rg.runtime.sections.role_narrative_v2 import (
    apply_ibm_narrative_judge_feedback_rewrite, bind_missing_ibm_narrative_theme_citations, build_narrative_mock_output,
    build_narrative_prompt_messages, build_narrative_runtime_payload, build_narrative_selected_fact_plan,
    build_selected_graph_evidence_plan_for_narrative, companion_bullets_as_list as _companion_bullets_as_list,
    cosine_echo_diagnostic_summary as _cosine_echo_diagnostic_summary, decompose_ibm_narrative_claim_ledger_by_clause,
    extract_employer_employment, get_employer_narrative_spec, infer_narrative_product_quality,
    load_base_resume as _load_base_resume, load_companion_bullets_context,
    normalize_ibm_narrative_parsed as normalize_parsed_output, parse_narrative_model_json as parse_model_json,
    pre_judge_failed_gate_ids as _pre_judge_failed_gate_ids, redact_banned_lexicon_from_attestation_change_log,
    redact_banned_lexicon_from_attestation_metadata, remap_ibm_narrative_claim_ledger_to_fact_pool,
    run_role_narrative_v2,
)

REPO_ROOT = _DEFAULT_REPO_ROOT
_SPEC = get_employer_narrative_spec("ibm_narrative")
LANE_KEY = "ibm_narrative"
IBM_NARRATIVE_TEMP_RANGE = _SPEC.temp_range


def load_base_resume() -> tuple[dict[str, Any], Path, str]:
    return _load_base_resume(REPO_ROOT)


def extract_ibm_employment(base_resume: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    return extract_employer_employment(
        base_resume, employer_match=_SPEC.employer_match_substring, default_fact_id=_SPEC.default_employment_fact_id,
        base_narrative_fact_id=_SPEC.base_narrative_fact_id,
    )


def load_companion_ibm_bullets_context() -> dict[str, Any]:
    return load_companion_bullets_context("ibm_narrative", repo_root=REPO_ROOT)


def load_companion_ibm_bullets_text() -> str:
    return str(load_companion_ibm_bullets_context().get("text") or "")


def build_selected_fact_plan(facts: list[dict[str, Any]]) -> dict[str, Any]:
    return build_narrative_selected_fact_plan("ibm_narrative", facts)


def build_selected_graph_evidence_plan_ibm_narrative(facts: list[dict[str, Any]]) -> dict[str, Any]:
    return build_selected_graph_evidence_plan_for_narrative("ibm_narrative", facts)


def build_runtime_payload(
    *, base_json_path: Path, base_hash: str, ibm_header: dict[str, Any], selected_fact_plan: dict[str, Any],
    allowed_fact_ids: set[str], companion_bullets_ref: str | None, companion_bullets_status: str = "UNKNOWN",
    companion_bullets_reason: str = "", companion_bullet_ids: list[str] | None = None, companion_x3_code: str = "UNKNOWN",
    companion_product_quality_status: str = "UNKNOWN", target_title: str, target_company: str, jd_text: str,
    briefing: str, candidate_name: str = "",
) -> dict[str, Any]:
    return build_narrative_runtime_payload(
        "ibm_narrative", base_json_path=base_json_path, base_hash=base_hash, header=ibm_header,
        selected_fact_plan=selected_fact_plan, allowed_fact_ids=allowed_fact_ids,
        companion_bullets_ref=companion_bullets_ref, companion_bullets_status=companion_bullets_status,
        companion_bullets_reason=companion_bullets_reason, companion_bullet_ids=companion_bullet_ids,
        companion_x3_code=companion_x3_code, companion_product_quality_status=companion_product_quality_status,
        target_title=target_title, target_company=target_company, jd_text=jd_text, briefing=briefing,
        candidate_name=candidate_name, repo_root=REPO_ROOT,
    )


def build_prompt_messages(runtime_payload: dict[str, Any], companion_bullets_text: str) -> list[dict[str, str]]:
    return build_narrative_prompt_messages("ibm_narrative", runtime_payload, companion_bullets_text)


def build_mock_output(runtime_payload: dict[str, Any], companion_bullets_text: str = "") -> dict[str, Any]:
    return build_narrative_mock_output("ibm_narrative", runtime_payload, companion_bullets_text)


def infer_product_quality(runtime_status: str, x2_gates: list[dict[str, Any]], *, artifact_dir: Path | None = None) -> tuple[str, str]:
    return infer_narrative_product_quality("ibm_narrative", runtime_status, x2_gates, artifact_dir=artifact_dir)


def run_ibm_narrative_lane_execution(
    args: Any, *, artifact_dir_override: Path | None = None,
    trace_runtime_path: str = "apps_rg.runtime.sections.ibm_narrative_lane", print_output: bool = False,
) -> dict[str, Any]:
    return run_role_narrative_v2(
        "ibm_narrative", args, artifact_dir_override=artifact_dir_override,
        trace_runtime_path=trace_runtime_path, print_output=print_output, repo_root_override=REPO_ROOT,
    )


run_ibm_narrative_execution = run_ibm_narrative_lane_execution
