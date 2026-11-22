"""Public facade for unify_narrative_lane delegating to role_narrative_v2 (<=120 LOC)."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from apps_rg.runtime.sections.role_narrative_v2 import (
    BRIEFING_DEFAULT, JD_TEXT_DEFAULT, REPO_ROOT as _DEFAULT_REPO_ROOT, TARGET_COMPANY_DEFAULT, TARGET_TITLE_DEFAULT,
    UNIFY_NARRATIVE_BASE_FACT_ID, UNIFY_NARRATIVE_C0_BULLET_PRIORITY, build_narrative_mock_output,
    build_narrative_prompt_messages, build_narrative_runtime_payload, build_narrative_selected_fact_plan,
    build_selected_graph_evidence_plan_for_narrative, companion_bullets_accepted as _companion_bullets_accepted,
    enrich_unify_narrative_parsed_for_x2, extract_employer_employment, get_employer_narrative_spec,
    infer_narrative_product_quality, load_base_resume as _load_base_resume, load_companion_bullets_context,
    normalize_unify_narrative_parsed, parse_narrative_model_json as parse_model_json, run_role_narrative_v2,
    run_unify_narrative_v2_healing_loop, sha16, shell_jd_alignment as _shell_jd_alignment, write_json,
)

REPO_ROOT = _DEFAULT_REPO_ROOT
_SPEC = get_employer_narrative_spec("unify_narrative")
LANE_KEY, PROMPT_ID, PROMPT_TEMPLATE = _SPEC.section_id, _SPEC.prompt_id, _SPEC.template_rel_path
NARRATIVE_TEMP_DEFAULT, NARRATIVE_TEMP_RANGE, NARRATIVE_MAX_OUTPUT_TOKENS = _SPEC.temp_default, _SPEC.temp_range, _SPEC.max_output_tokens
apply_unify_narrative_in_lane_healing = run_unify_narrative_v2_healing_loop


def load_base_resume() -> tuple[dict[str, Any], Path, str]:
    return _load_base_resume(REPO_ROOT)


def extract_unify_employment(base_resume: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    return extract_employer_employment(
        base_resume, employer_match=_SPEC.employer_match_substring, default_fact_id=_SPEC.default_employment_fact_id,
        base_narrative_fact_id=_SPEC.base_narrative_fact_id,
    )


def build_selected_fact_plan(unify_bullets: list[dict[str, Any]], *, role_narrative: str = "", employment_fact_id: str = "exp_unify_001") -> dict[str, Any]:
    return build_narrative_selected_fact_plan("unify_narrative", unify_bullets, role_narrative=role_narrative, employment_fact_id=employment_fact_id)


def build_selected_graph_evidence_plan(unify_bullets: list[dict[str, Any]], *, role_narrative: str = "", employment_fact_id: str = "exp_unify_001") -> dict[str, Any]:
    return build_selected_graph_evidence_plan_for_narrative("unify_narrative", unify_bullets, role_narrative=role_narrative, employment_fact_id=employment_fact_id)


def load_companion_unify_bullets_context() -> dict[str, Any]:
    return load_companion_bullets_context("unify_narrative", repo_root=REPO_ROOT)


def build_runtime_payload(
    *, base_json_path: Path, base_hash: str, unify_header: dict[str, Any], selected_fact_plan: dict[str, Any],
    allowed_fact_ids: set[str], companion_bullets_ref: str | None, companion_bullets_status: str,
    companion_bullets_reason: str, companion_bullet_ids: list[str], companion_x3_code: str,
    companion_product_quality_status: str, target_title: str, target_company: str, jd_text: str, briefing: str,
    candidate_name: str = "",
) -> dict[str, Any]:
    return build_narrative_runtime_payload(
        "unify_narrative", base_json_path=base_json_path, base_hash=base_hash, header=unify_header,
        selected_fact_plan=selected_fact_plan, allowed_fact_ids=allowed_fact_ids,
        companion_bullets_ref=companion_bullets_ref, companion_bullets_status=companion_bullets_status,
        companion_bullets_reason=companion_bullets_reason, companion_bullet_ids=companion_bullet_ids,
        companion_x3_code=companion_x3_code, companion_product_quality_status=companion_product_quality_status,
        target_title=target_title, target_company=target_company, jd_text=jd_text, briefing=briefing,
        candidate_name=candidate_name, repo_root=REPO_ROOT,
    )


def build_prompt_messages(runtime_payload: dict[str, Any], companion_bullets_text: str) -> list[dict[str, str]]:
    return build_narrative_prompt_messages("unify_narrative", runtime_payload, companion_bullets_text)


def build_mock_output(runtime_payload: dict[str, Any]) -> dict[str, Any]:
    return build_narrative_mock_output("unify_narrative", runtime_payload)


def infer_unify_narrative_product_quality(runtime_status: str, x2_gates: list[dict[str, Any]], *, artifact_dir: Path | None = None) -> tuple[str, str]:
    return infer_narrative_product_quality("unify_narrative", runtime_status, x2_gates, artifact_dir=artifact_dir)


def run_unify_narrative_execution(args: argparse.Namespace, *, artifact_dir_override: Path | None = None) -> dict[str, Any]:
    return run_role_narrative_v2("unify_narrative", args, artifact_dir_override=artifact_dir_override, repo_root_override=REPO_ROOT)
