"""Clean-Slate Judge v3 Binding for `competencies` (`<= 90L`, zero prose wall)."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput
from apps_rg.runtime.judges.policy_backed_section_judges import run_policy_section_judges
from apps_rg.runtime.judges.v3_section_judge import (
    build_section_v3_response_schema,
    get_apps_rg_v3_profile,
    render_section_v3_rubric,
)

JUDGE_RUBRIC_VERSION = "competencies_judge_v3"
JUDGE_RUBRIC_REF = "config/governance/judge_rubrics_v3.json#resume_sections:competencies"

COMPETENCIES_RUBRIC_DIMENSION_IDS: tuple[str, ...] = tuple(
    c.id for c in get_apps_rg_v3_profile("competencies").checks
)
COMPETENCIES_JUDGE_RESPONSE_SCHEMA = build_section_v3_response_schema("competencies")
COMPETENCIES_RUBRIC = render_section_v3_rubric("competencies")


def _is_test_environment() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST") or ("pytest" in sys.modules))


def _competencies_display_text(categories: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in categories or []:
        if isinstance(row, dict):
            label = str(row.get("category") or row.get("label") or "").strip()
            terms = ", ".join(str(t) for t in (row.get("terms") or row.get("skills") or []) if str(t).strip())
            lines.append(f"{label}: {terms}".strip(": "))
    return "\n".join(lines)


def run_competencies_judges(
    *,
    competency_categories: list[dict[str, Any]] | None = None,
    candidate_output: dict[str, Any] | None = None,
    claim_ledger: list[dict[str, Any]] | None = None,
    judge_keys: list[str] | None = None,
    mode: str = "blocked_if_unavailable",
    artifact_base: Path | None = None,
    targeting_context: dict[str, Any] | None = None,
    deterministic_gate_summary: dict[str, Any] | None = None,
    allowed_fact_packet: dict[str, Any] | list[dict[str, Any]] | None = None,
    resume_display_text: str = "",
    **_extra: Any,
) -> list[JudgeOutput]:
    cats = list(competency_categories or (candidate_output or {}).get("competency_categories") or [])
    display = resume_display_text or str((candidate_output or {}).get("resume_display_text") or "") or _competencies_display_text(cats)
    cand = dict(candidate_output or {"competency_categories": cats, "resume_display_text": display})
    packet_path = (artifact_base / "competencies_judge_packet.json") if artifact_base else None
    outputs = run_policy_section_judges(
        "competencies",
        candidate_output=cand,
        section_rubric=COMPETENCIES_RUBRIC,
        rubric_ref=JUDGE_RUBRIC_REF,
        claim_ledger=list(claim_ledger or []),
        judge_keys=list(judge_keys or ["gemini_pro", "openai_chatgpt"]),
        allowed_fact_packet=allowed_fact_packet,
        targeting_context=targeting_context,
        deterministic_gate_summary=deterministic_gate_summary,
        resume_display_text=display,
        mode=mode,
        artifact_base=artifact_base,
        judge_packet_path=packet_path,
    )
    for out in outputs:
        out.judge_id = f"x1d_{out.provider_key}_competencies"
        out.rubric_version = JUDGE_RUBRIC_VERSION
    return outputs


__all__ = [
    "COMPETENCIES_JUDGE_RESPONSE_SCHEMA",
    "COMPETENCIES_RUBRIC",
    "COMPETENCIES_RUBRIC_DIMENSION_IDS",
    "JUDGE_RUBRIC_VERSION",
    "_is_test_environment",
    "run_competencies_judges",
]
