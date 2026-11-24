"""Clean-Slate Judge v3 Binding for `headline` (`<= 55L`, zero prose wall)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput
from apps_rg.runtime.judges.policy_backed_section_judges import run_policy_section_judges
from apps_rg.runtime.judges.v3_section_judge import render_section_v3_rubric

JUDGE_RUBRIC_VERSION = "headline_judge_v3"
JUDGE_RUBRIC_REF = "config/governance/judge_rubrics_v3.json#resume_sections:headline"
HEADLINE_RUBRIC = render_section_v3_rubric("headline")


def run_headline_judges(
    *,
    headline_line: str,
    claim_ledger: list[dict[str, Any]],
    judge_keys: list[str],
    companion_context: str = "",
    mode: str = "blocked_if_unavailable",
    artifact_base: Path | None = None,
    targeting_context: dict[str, Any] | None = None,
    deterministic_gate_summary: dict[str, Any] | None = None,
    allowed_fact_packet: dict[str, Any] | None = None,
) -> list[JudgeOutput]:
    candidate = {
        "headline_line": headline_line,
        "resume_display_text": headline_line,
        "companion_context": companion_context,
    }
    packet_path = (artifact_base / "headline_judge_packet.json") if artifact_base else None
    outputs = run_policy_section_judges(
        "headline",
        candidate_output=candidate,
        section_rubric=HEADLINE_RUBRIC,
        rubric_ref=JUDGE_RUBRIC_REF,
        claim_ledger=claim_ledger,
        judge_keys=judge_keys,
        allowed_fact_packet=allowed_fact_packet,
        targeting_context=targeting_context,
        deterministic_gate_summary=deterministic_gate_summary,
        resume_display_text=headline_line,
        mode=mode,
        artifact_base=artifact_base,
        judge_packet_path=packet_path,
    )
    for o in outputs:
        o.judge_id = f"x1d_{o.provider_key}_headline"
        o.rubric_version = JUDGE_RUBRIC_VERSION
    return outputs


__all__ = ["HEADLINE_RUBRIC", "JUDGE_RUBRIC_REF", "JUDGE_RUBRIC_VERSION", "run_headline_judges"]
