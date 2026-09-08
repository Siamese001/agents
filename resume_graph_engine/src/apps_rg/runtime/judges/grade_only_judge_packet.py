"""Generic GRADE_ONLY JudgePacket builder for apps_rg section X1D judges."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from apps_rg.runtime.section_judge_policy import get_section_judge_policy, normalize_section_id

JUDGE_PACKET_VERSION = "apps_rg_grade_only_judge_packet_v2"
_PRE_X2_PENDING_GATE_KEY = "x2_judge_snapshot_pending"

# ``selected_fact_plan`` is both a proof surface and an operational audit surface.
# Judges need the former, but traversal ledgers and ranking diagnostics can be
# megabytes large and are not claim authority.  Keep the proof-bearing fields in
# provider input and bind the omitted audit fields by digest so the durable lane
# artifacts remain traceable without exceeding provider input limits.
_SELECTED_FACT_PLAN_JUDGE_FIELDS = frozenset(
    {
        "allocation_assignments",
        "allocation_plan_digest",
        "allocation_plan_id",
        "allocation_scope",
        "allowed_graph_evidence_ids",
        "durable_graph_state_mutated",
        "facts",
        "global_uniqueness_claimed",
        "graph_evidence_depth_status",
        "graph_evidence_semantic_coverage_pct",
        "plan_digest",
        "plan_id",
        "required_fact_ids",
        "role_family_key",
        "schema_version",
        "section_id",
        "selected_competency_families",
        "selected_employer_lane_ids",
        "selected_employer_lanes",
        "selected_employer_roots",
        "selected_headline_positioning_families",
        "selected_metrics",
        "selected_skill_ids",
        "selected_skills",
        "selection_method",
        "selection_rationale",
        "target_role_profile",
    }
)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def compact_candidate_output_for_judge(candidate_output: dict[str, Any]) -> dict[str, Any]:
    """Project candidate output to proof-bearing judge input.

    The complete candidate remains in its lane artifact.  This projection only
    removes non-authoritative traversal/ranking diagnostics nested under
    ``selected_fact_plan`` and records a digest plus exact omitted field names.
    """
    compact = dict(candidate_output)
    selected_fact_plan = candidate_output.get("selected_fact_plan")
    if not isinstance(selected_fact_plan, dict):
        return compact

    projected = {
        key: value
        for key, value in selected_fact_plan.items()
        if key in _SELECTED_FACT_PLAN_JUDGE_FIELDS
    }
    omitted_fields = sorted(set(selected_fact_plan) - set(projected))
    projected["judge_projection"] = {
        "projection_version": "selected_fact_plan_judge_projection_v1",
        "source_sha256": hashlib.sha256(_canonical_json_bytes(selected_fact_plan)).hexdigest(),
        "omitted_non_authoritative_fields": omitted_fields,
    }
    compact["selected_fact_plan"] = projected
    return compact


def ensure_panel_gate_summary(
    deterministic_gate_summary: dict[str, Any] | None,
    *,
    section_id: str,
) -> dict[str, Any]:
    """Non-empty gate summary for core JudgePanelRunner when X2 runs after X1D."""
    summary = dict(deterministic_gate_summary or {})
    if summary:
        return summary
    sid = normalize_section_id(section_id)
    return {
        _PRE_X2_PENDING_GATE_KEY: {
            "pass": True,
            "detail": (
                f"Pre-X2 GRADE_ONLY for {sid}: lane runs X2 after judges; grade on rubric, "
                "allowed_fact_packet, and candidate_output only — do not fail on missing x2_* keys."
            ),
        }
    }

GRADE_ONLY_INSTRUCTION = """
You are grading a generated resume section candidate produced by a separate generator.
judge_task: GRADE_ONLY

Mandatory rules:
- Do NOT write replacement section content.
- Do NOT rewrite or edit the candidate text.
- Do NOT add claims, metrics, credentials, or facts.
- JD_TEXT and BRIEFING are targeting context only — never proof.
- Grade only against the rubric, allowed_fact_packet (when provided), and candidate_output.
- Return ONLY the required structured judge JSON schema (no markdown fences, no prose).
""".strip()

REQUIRED_JUDGE_OUTPUT_SCHEMA = """
Return ONLY one compact JSON object:
{"score_scale":"0_to_5","score":0.0,"threshold":4.0,"pass":true,"decisive_failure":false,
 "findings":["short strings"],"cited_sentence_indexes":[1],
 "remediation_suggestions":[],"rationale":"one short paragraph",
 "fail_reasons":[],"unsupported_claims":[],"quality_flags":[]}
score_scale must be 0_to_5 or 0_to_1 with in-range score/threshold.
""".strip()


def build_grade_only_judge_packet(
    *,
    section_id: str,
    candidate_output: dict[str, Any],
    section_rubric: str,
    rubric_ref: str,
    claim_ledger: list[dict[str, Any]] | None = None,
    allowed_fact_packet: dict[str, Any] | list[dict[str, Any]] | None = None,
    targeting_context: dict[str, Any] | None = None,
    deterministic_gate_summary: dict[str, Any] | None = None,
    source_fact_ids: list[str] | None = None,
    proof_pool_metadata: dict[str, Any] | None = None,
    graph_binding_materiality_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical GRADE_ONLY JudgePacket for any section."""
    sid = normalize_section_id(section_id)
    policy = get_section_judge_policy(sid)

    targeting = dict(targeting_context or {})
    materiality = dict(graph_binding_materiality_summary or {})
    if not materiality and isinstance(proof_pool_metadata, dict):
        from apps_rg.runtime.graph_skills_utilization_scorer import (
            build_graph_binding_materiality_summary,
        )

        materiality = build_graph_binding_materiality_summary(
            section_id=sid,
            proof_pool_metadata=proof_pool_metadata,
            candidate_output=candidate_output,
            claim_ledger=claim_ledger,
        )
    packet = {
        "judge_packet_version": JUDGE_PACKET_VERSION,
        "section": sid,
        "judge_task": "GRADE_ONLY",
        "candidate_output": compact_candidate_output_for_judge(candidate_output),
        "claim_ledger": list(claim_ledger or []),
        "source_fact_ids": list(source_fact_ids or []),
        "allowed_fact_packet": allowed_fact_packet,
        "targeting_context": {
            "target_title": targeting.get("target_title", ""),
            "target_company": targeting.get("target_company", ""),
            "jd_text": targeting.get("jd_text", ""),
            "briefing": targeting.get("briefing", ""),
        },
        "proof_boundary": {
            "jd_is_targeting_context_only": True,
            "briefing_is_targeting_context_only": True,
            "claims_must_be_supported_by_allowed_fact_packet": True,
            "judges_must_not_rewrite": True,
            "metadata_only_graph_context_is_insufficient": True,
        },
        "graph_binding_materiality_summary": materiality,
        "deterministic_gate_summary": ensure_panel_gate_summary(
            deterministic_gate_summary, section_id=sid
        ),
        "section_specific_rubric": section_rubric.strip(),
        "grading_only_instructions": GRADE_ONLY_INSTRUCTION,
        "required_judge_output_schema": REQUIRED_JUDGE_OUTPUT_SCHEMA,
        "rubric_ref": rubric_ref,
        "judge_tier": policy.judge_tier.value,
        "judge_packet_required": policy.judge_packet_required,
    }
    return packet


def judge_packet_hash(packet: dict[str, Any]) -> str:
    payload = {k: v for k, v in packet.items() if k != "judge_packet_hash"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def write_judge_packet(path: Path, packet: dict[str, Any]) -> str:
    enriched = dict(packet)
    enriched["judge_packet_hash"] = judge_packet_hash(packet)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        from apps_rg.runtime.runtime_proof_layout import repo_relative_path

        return repo_relative_path(path)
    except Exception:  # noqa: BLE001  # guardian: allow-broad-exception -- P2 burndown: fail-soft optional boundary
        return path.as_posix()


def render_judge_prompt_from_packet(packet: dict[str, Any]) -> str:
    """Render judge user message from JudgePacket — never the generator compiled_prompt."""
    candidate = packet.get("candidate_output") or {}
    return "\n\n".join(
        [
            packet.get("grading_only_instructions") or GRADE_ONLY_INSTRUCTION,
            f"SECTION: {packet.get('section')}",
            f"RUBRIC_REF: {packet.get('rubric_ref')}",
            (packet.get("section_specific_rubric") or "").strip(),
            (packet.get("required_judge_output_schema") or REQUIRED_JUDGE_OUTPUT_SCHEMA).strip(),
            "CANDIDATE_OUTPUT:\n" + json.dumps(candidate, ensure_ascii=False, indent=2),
            "ALLOWED_FACT_PACKET:\n"
            + json.dumps(packet.get("allowed_fact_packet"), ensure_ascii=False, indent=2),
            "CLAIM_LEDGER:\n"
            + json.dumps(packet.get("claim_ledger") or [], separators=(",", ":")),
            "TARGETING_CONTEXT (not proof):\n"
            + json.dumps(packet.get("targeting_context") or {}, ensure_ascii=False, indent=2),
            "PROOF_BOUNDARY:\n"
            + json.dumps(packet.get("proof_boundary") or {}, ensure_ascii=False, indent=2),
            "GRAPH_BINDING_MATERIALITY_SUMMARY:\n"
            + json.dumps(
                packet.get("graph_binding_materiality_summary") or {},
                ensure_ascii=False,
                indent=2,
            ),
            "DETERMINISTIC_GATE_SUMMARY:\n"
            + json.dumps(packet.get("deterministic_gate_summary") or {}, ensure_ascii=False, indent=2),
        ]
    )


__all__ = [
    "GRADE_ONLY_INSTRUCTION",
    "JUDGE_PACKET_VERSION",
    "REQUIRED_JUDGE_OUTPUT_SCHEMA",
    "_PRE_X2_PENDING_GATE_KEY",
    "build_grade_only_judge_packet",
    "compact_candidate_output_for_judge",
    "ensure_panel_gate_summary",
    "judge_packet_hash",
    "render_judge_prompt_from_packet",
    "write_judge_packet",
]
