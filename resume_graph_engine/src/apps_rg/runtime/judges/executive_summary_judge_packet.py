"""Blind Executive-Summary JudgePacket Builder (`<= 210L`, Judge v3 Clean-Slate).

Strips all `deterministic_gate_summary` and internal allocation fields before
rendering the `<= 300`-word Judge v3 prompt, and never coerces failing judge
verdicts upward.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.judges.v3_section_judge import render_section_v3_rubric

JUDGE_PACKET_VERSION = "executive_summary_judge_packet_v3_blind"
JUDGE_RUBRIC_REF = "config/governance/judge_rubrics_v3.json#resume_sections:executive_summary"
GRAPH_ONLY_JUDGE_RUBRIC_REF = JUDGE_RUBRIC_REF

GRADE_ONLY_INSTRUCTION = (
    "Blind hiring-committee evaluation (GRADE_ONLY). Evaluate candidate_output strictly against "
    "allowed_fact_packet and targeting_context using atomic YES/NO checks and verbatim failure spans. "
    "DISPLAY_OVERRIDE PARITY: treat the union of claim_text and display_override_text as authorized proof. "
    "Do NOT write replacement prose."
)
SRFS_GRADE_ONLY_RUBRIC = render_section_v3_rubric("executive_summary")
GRAPH_ONLY_GRADE_ONLY_RUBRIC = SRFS_GRADE_ONLY_RUBRIC
REQUIRED_JUDGE_OUTPUT_SCHEMA = (
    '{"cold_read_takeaway":"...","checks":{"<check_id>":{"verdict":"YES|NO","evidence_span":"..."}},"failure_tags":[]}'
)


def enrich_allowed_fact_packet_for_judges(
    allowed_fact_packet: Any,
    allowed_fact_ids: set[str] | frozenset[str] | list[str] | None = None,
) -> Any:
    from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
        FACT_C0_DISPLAY_OVERRIDES,
    )

    allowed_set = {str(x) for x in allowed_fact_ids} if allowed_fact_ids is not None else None

    def _enrich_row(row: Any) -> Any:
        if not isinstance(row, Mapping):
            return row
        out = dict(row)
        fid = str(out.get("fact_id") or "").strip()
        if fid and fid in FACT_C0_DISPLAY_OVERRIDES and (allowed_set is None or fid in allowed_set):
            out["display_override_text"] = FACT_C0_DISPLAY_OVERRIDES[fid]
            out["display_substrate_authority"] = "union_claim_text_and_display_override_text"
        return out

    if isinstance(allowed_fact_packet, Mapping):
        clean = {k: v for k, v in allowed_fact_packet.items() if k not in {"allocation_assignments", "selection_rationale"}}
        if isinstance(clean.get("facts"), list):
            clean["facts"] = [_enrich_row(r) for r in clean["facts"]]
        return clean
    if isinstance(allowed_fact_packet, list):
        return [_enrich_row(row) for row in allowed_fact_packet]
    return allowed_fact_packet


def build_deterministic_gate_summary(**gates: Any) -> dict[str, Any]:
    return {str(k): v for k, v in gates.items()}


def build_deterministic_gate_summary_from_x2_gates(x2_gates: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(x2_gates, Mapping):
        return {}
    return {str(k): v for k, v in x2_gates.items()}


def packet_forbids_generator_prompt_reuse(packet: Mapping[str, Any], compiled_prompt: str | None = None) -> bool:
    if not compiled_prompt:
        return True
    rendered = json.dumps(dict(packet), sort_keys=True)
    probe = compiled_prompt.strip()[:240]
    return not (probe and probe in rendered)


def build_executive_summary_judge_packet(
    *,
    candidate_output: Mapping[str, Any] | None = None,
    parsed_output: Mapping[str, Any] | None = None,
    resume_display_text: str = "",
    claim_ledger: list[dict[str, Any]] | None = None,
    allowed_fact_packet: Any = None,
    allowed_fact_ids: set[str] | frozenset[str] | list[str] | None = None,
    targeting_context: Mapping[str, Any] | None = None,
    deterministic_gate_summary: Mapping[str, Any] | None = None,
    rubric_ref: str = JUDGE_RUBRIC_REF,
    section_rubric: str | None = None,
    proof_boundary: Mapping[str, Any] | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """Construct blind Executive Summary judge packet (strips deterministic gate priming from rendered prompt)."""
    from apps_rg.runtime.validators.exec_summary_x2.surface_checks import (
        check_judge_packet_display_override_parity,
    )

    cand = dict(candidate_output or parsed_output or {})
    if resume_display_text and not cand.get("resume_display_text"):
        cand["resume_display_text"] = resume_display_text
    ledger_rows = list(claim_ledger or [])
    enriched_facts = enrich_allowed_fact_packet_for_judges(allowed_fact_packet, allowed_fact_ids)
    cited_ids: list[str] = [
        str(fid)
        for row in ledger_rows
        if isinstance(row, Mapping)
        for fid in (row.get("source_fact_ids") or ())
    ]
    fact_rows = enriched_facts if isinstance(enriched_facts, list) else (enriched_facts.get("facts") if isinstance(enriched_facts, Mapping) else [])
    parity_ok, parity_detail = check_judge_packet_display_override_parity(
        judge_allowed_fact_packet=fact_rows if isinstance(fact_rows, list) else [],
        cited_fact_ids=cited_ids,
    )
    gate_summary = dict(deterministic_gate_summary or {})
    gate_summary["x2_executive_summary_judge_packet_display_override_parity"] = {
        "pass": parity_ok,
        "detail": parity_detail or "ok",
    }
    return {
        "judge_packet_version": JUDGE_PACKET_VERSION,
        "section": "executive_summary",
        "judge_task": "GRADE_ONLY",
        "rubric_ref": rubric_ref,
        "section_rubric": section_rubric or SRFS_GRADE_ONLY_RUBRIC,
        "candidate_output": cand,
        "claim_ledger": ledger_rows,
        "allowed_fact_packet": enriched_facts,
        "targeting_context": dict(targeting_context or {}),
        "deterministic_gate_summary": gate_summary,
        "proof_boundary": dict(
            proof_boundary
            or {
                "jd_used_as_proof": False,
                "briefing_used_as_proof": False,
                "companion_used_as_proof": False,
            }
        ),
    }


def judge_packet_hash(packet: Mapping[str, Any]) -> str:
    clean = {k: v for k, v in packet.items() if k != "deterministic_gate_summary"}
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def judge_contract_hash(packet: Mapping[str, Any]) -> str:
    clean = {
        "section": packet.get("section", "executive_summary"),
        "rubric_ref": packet.get("rubric_ref", JUDGE_RUBRIC_REF),
        "candidate_output": packet.get("candidate_output"),
        "allowed_fact_packet": packet.get("allowed_fact_packet"),
        "targeting_context": packet.get("targeting_context"),
    }
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render_judge_prompt_from_packet(packet: Mapping[str, Any]) -> str:
    """Render concise blind Judge v3 prompt (`<= 300`-word rubric + clean evidence JSON, zero gate priming)."""
    rubric = render_section_v3_rubric(str(packet.get("section") or "executive_summary"))
    blind_payload = {
        "candidate_output": packet.get("candidate_output"),
        "claim_ledger": packet.get("claim_ledger"),
        "allowed_fact_packet": packet.get("allowed_fact_packet"),
        "targeting_context": packet.get("targeting_context"),
    }
    return f"{rubric}\n\nBLIND_EVALUATION_PACKET:\n{json.dumps(blind_payload, ensure_ascii=False, sort_keys=True)}"


def write_executive_summary_judge_packet(path: Path, packet: Mapping[str, Any]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in packet.items() if k != "deterministic_gate_summary"}
    target.write_text(json.dumps(clean, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return str(target)


def reconcile_judge_result_against_deterministic_gate_closures(
    result: Mapping[str, Any],
    deterministic_gate_summary: Mapping[str, Any] | None = None,
    *,
    section_id: str | None = None,
) -> dict[str, Any]:
    """Strictly preserve Stage B LLM judge verdicts without upward score coercion."""
    _ = (deterministic_gate_summary, section_id)
    return dict(result)


reconcile_grade_only_judge_result = reconcile_judge_result_against_deterministic_gate_closures
