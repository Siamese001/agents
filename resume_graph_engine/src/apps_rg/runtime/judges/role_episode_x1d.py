"""Clean-Slate Judge v3 Binding for Role Episode Lanes (`<= 60L`, zero prose wall)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput
from apps_rg.runtime.judges.policy_backed_section_judges import run_policy_section_judges
from apps_rg.runtime.judges.v3_section_judge import render_section_v3_rubric

JUDGE_RUBRIC_VERSION = "role_episode_judge_v3"
DEFAULT_THRESHOLD = 0.80
JUDGE_RUBRIC_REF = "config/governance/judge_rubrics_v3.json#resume_sections:role_narrative"
ROLE_EPISODE_RUBRIC = render_section_v3_rubric("role_episode")


def run_role_episode_judges(
    *,
    section_id: str,
    candidate_output: dict[str, Any],
    claim_ledger: list[dict[str, Any]],
    judge_keys: list[str],
    mode: str = "blocked_if_unavailable",
    artifact_base: Path | None = None,
    targeting_context: dict[str, Any] | None = None,
    deterministic_gate_summary: dict[str, Any] | None = None,
    allowed_fact_packet: dict[str, Any] | None = None,
) -> list[JudgeOutput]:
    display = str(
        candidate_output.get("resume_display_text")
        or candidate_output.get("narrative_sentence")
        or "\n".join(
            str(row.get("bullet_text") or "")
            for row in (candidate_output.get("bullets") or [])
            if isinstance(row, dict)
        )
    )
    rubric = render_section_v3_rubric(section_id)
    r_ref = (
        "config/governance/judge_rubrics_v3.json#resume_sections:employment_bullets"
        if str(section_id).endswith("_bullets")
        else JUDGE_RUBRIC_REF
    )
    packet_path = (artifact_base / f"{section_id}_judge_packet.json") if artifact_base else None
    outputs = run_policy_section_judges(
        section_id,
        candidate_output=candidate_output,
        section_rubric=rubric,
        rubric_ref=r_ref,
        claim_ledger=claim_ledger,
        judge_keys=judge_keys,
        allowed_fact_packet=allowed_fact_packet,
        targeting_context=targeting_context,
        deterministic_gate_summary=deterministic_gate_summary,
        resume_display_text=display,
        mode=mode,
        artifact_base=artifact_base,
        judge_packet_path=packet_path,
    )
    for output in outputs:
        output.judge_id = f"x1d_{output.provider_key}_{section_id}"
        output.rubric_version = JUDGE_RUBRIC_VERSION
    return outputs


__all__ = [
    "DEFAULT_THRESHOLD",
    "JUDGE_RUBRIC_REF",
    "JUDGE_RUBRIC_VERSION",
    "ROLE_EPISODE_RUBRIC",
    "run_role_episode_judges",
]
