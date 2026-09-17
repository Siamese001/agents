"""BCG forensics, evidence mapping, and truth validators."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .research_context import *
from .section_lane_tables import *
from .causal_plan import *
from .causal_allocation import *

__all__ = ['_bcg_row', '_active_bcg_evidence', '_forensic_gate', '_forensic_artifacts', '_output_bisect_sections', '_forensic_artifact_by_section', '_forensic_evidence_map_rows', '_truthy_signal', '_clean_pass_hardening_rows', '_build_bcg_recommendations', '_build_bcg_recommended_next_moves', '_bcg_truth_errors', '_bcg_forensics_truth_errors']

def _bcg_row(priority: str, recommendation: str, evidence: str, gate_outcome: str) -> dict[str, str]:
    return {
        "priority": priority,
        "recommendation": recommendation,
        "evidence": evidence,
        "gate_outcome": gate_outcome,
    }


def _active_bcg_evidence(doc: dict[str, Any]) -> dict[str, Any]:
    final_out = doc.get("final_resume_output") if isinstance(doc.get("final_resume_output"), dict) else {}
    research = _research_row(doc)
    lane_rows = doc.get("section_lane_table") if isinstance(doc.get("section_lane_table"), list) else []
    blocked_generated_lanes = [
        str(row.get("section") or "")
        for row in lane_rows
        if isinstance(row, dict)
        and str(row.get("section") or "") != "research_briefing_input"
        and str(row.get("x3") or "").startswith("X3_BLOCK")
    ]
    provider_gap_sections = [
        str(row.get("section") or "")
        for row in lane_rows
        if isinstance(row, dict)
        and str(row.get("x3") or "").startswith("X3_BLOCK")
        and str(row.get("generation_status") or "") == "REAL_LLM"
        and (
            row.get("provider_call_attempted") is not True
            or str(row.get("primary_provider") or "") in {"", "NOT_OBSERVED"}
            or str(row.get("primary_model_observed") or "") in {"", "NOT_OBSERVED"}
        )
    ]
    phase1_no_run_lanes = [
        str(row.get("section") or "")
        for row in lane_rows
        if isinstance(row, dict)
        and "PHASE1_NO_RUN_DIR" in str(row.get("x3") or row.get("past_fail_blocker") or "")
    ]
    final_aggregation_blockers: list[str] = []
    for section in doc.get("sections", []):
        if not isinstance(section, dict) or str(section.get("section") or "") != FINAL_AGGREGATION_LANE:
            continue
        x2_pass = str(section.get("x2_pass") or "UNKNOWN")
        product = str(section.get("product_quality_status") or "UNKNOWN")
        x3_code = str(section.get("x3_code") or "UNKNOWN")
        failed_gates = [
            str(gate.get("gate_id") or "unknown_gate")
            for gate in section.get("failed_gates") or []
            if isinstance(gate, dict)
        ]
        if x2_pass != "PASS" or product != "PASS" or x3_code != "X3_ALLOW":
            evidence_bits = []
            if failed_gates:
                evidence_bits.append(",".join(failed_gates))
            evidence_bits.extend([f"x2={x2_pass}", f"product={product}", f"x3={x3_code}"])
            final_aggregation_blockers.append(f"{FINAL_AGGREGATION_LANE}: " + "; ".join(evidence_bits))
    return {
        "final_status": str(final_out.get("status") or "UNKNOWN"),
        "failed_final": final_out.get("failed_gate_ids") if isinstance(final_out.get("failed_gate_ids"), list) else [],
        "research": research,
        "research_status": str(research.get("generation_status") or "NOT_OBSERVED"),
        "research_source_class": str(research.get("research_source_class") or "NOT_OBSERVED"),
        "blocked_generated_lanes": blocked_generated_lanes,
        "provider_gap_sections": provider_gap_sections,
        "phase1_no_run_lanes": phase1_no_run_lanes,
        "final_aggregation_blockers": final_aggregation_blockers,
        "competencies_blocker": next(
            (
                finding
                for finding in doc.get("rca_findings", [])
                if isinstance(finding, dict) and str(finding.get("section") or "") == "competencies"
            ),
            None,
        ),
    }


def _forensic_gate(doc: dict[str, Any]) -> dict[str, Any]:
    gate = doc.get("section_failure_forensics")
    return gate if isinstance(gate, dict) else {}


def _forensic_artifacts(doc: dict[str, Any]) -> list[dict[str, Any]]:
    gate = _forensic_gate(doc)
    artifacts = gate.get("artifacts")
    return [row for row in artifacts if isinstance(row, dict)] if isinstance(artifacts, list) else []


def _output_bisect_sections(
    run_root: Path,
    forensics: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    artifacts = forensics.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, list) else []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        section_id = str(artifact.get("section_id") or "")
        if not section_id:
            continue
        rca = _load_json(
            run_root / SECTION_FAILURE_FORENSICS_DIR / f"{section_id}.json"
        )
        bisect = rca.get("output_bisect")
        if isinstance(bisect, dict):
            rows.append(bisect)
    return rows


def _forensic_artifact_by_section(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("section_id") or ""): row
        for row in _forensic_artifacts(doc)
        if str(row.get("section_id") or "").strip()
    }


def _forensic_evidence_map_rows(doc: dict[str, Any]) -> list[dict[str, str]]:
    gate = _forensic_gate(doc)
    if not gate.get("required"):
        return []
    rows: list[dict[str, str]] = []
    artifact_dir = str(gate.get("artifact_dir") or "").strip()
    if artifact_dir:
        rows.append(
            {
                "label": "Section failure forensics index",
                "path": f"@{artifact_dir}/index.json; @{artifact_dir}/index.md",
            }
        )
    for artifact in _forensic_artifacts(doc):
        section_id = str(artifact.get("section_id") or "unknown_section")
        json_path = str(artifact.get("json_path") or "").strip()
        md_path = str(artifact.get("md_path") or "").strip()
        refs = "; ".join(f"@{path}" for path in (json_path, md_path) if path)
        rows.append(
            {
                "label": f"Section forensic RCA: {section_id}",
                "path": refs or f"missing_forensic_artifact:{section_id}",
            }
        )
    return rows


def _truthy_signal(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "not_observed", "n/a", "none"} else text


def _clean_pass_hardening_rows(doc: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, str]]:
    summary = doc.get("result_summary") if isinstance(doc.get("result_summary"), dict) else {}
    final_pass = evidence.get("final_status") == "PASS"
    if not (bool(summary.get("outcome_authorized")) and final_pass):
        return []
    lane_rows = doc.get("section_lane_table") if isinstance(doc.get("section_lane_table"), list) else []
    retry_signals: list[str] = []
    l6_signals: list[str] = []
    warning_signals: list[str] = []
    for row in lane_rows:
        if not isinstance(row, dict) or str(row.get("section") or "") == "research_briefing_input":
            continue
        section_id = str(row.get("section") or "unknown_section")
        retry = _truthy_signal(row.get("judge_retry_fallback"))
        if retry:
            retry_signals.append(f"{section_id}: {retry}")
        l6 = _truthy_signal(row.get("l6_evidence"))
        if l6:
            l6_signals.append(f"{section_id}: {l6}")
        x2 = str(row.get("x2") or "")
        if "WARN" in x2.upper():
            warning_signals.append(f"{section_id}: {x2}")
    rows: list[dict[str, str]] = []
    if retry_signals:
        rows.append(
            _bcg_row(
                "PX",
                "Review retry and judge fallback signals before promoting the passing run pattern.",
                " | ".join(retry_signals[:6]),
                "Passing run stays authorized; capture hardening backlog from observed retries.",
            )
        )
    if warning_signals:
        rows.append(
            _bcg_row(
                "PX",
                "Review warning-level gates before treating the passing run as a hardened baseline.",
                " | ".join(warning_signals[:6]),
                "Passing run stays authorized; warnings remain hardening opportunities.",
            )
        )
    if l6_signals:
        rows.append(
            _bcg_row(
                "PX",
                "Review L6 shadow observations as future-run hardening inputs, not product blockers.",
                " | ".join(l6_signals[:6]),
                "Passing run stays authorized; L6 remains advisory unless promoted by policy.",
            )
        )
    return rows


def _build_bcg_recommendations(doc: dict[str, Any]) -> list[dict[str, str]]:
    evidence = _active_bcg_evidence(doc)
    research = evidence["research"]
    research_status = evidence["research_status"]
    research_source_class = evidence["research_source_class"]
    rows: list[dict[str, str]] = []
    operational = doc.get("operational_failure_forensics")
    operational = operational if isinstance(operational, dict) else {}
    if operational.get("required"):
        root_cause = str(operational.get("root_cause") or "operational preflight failure")
        first_causal = operational.get("first_causally_relevant_divergence")
        first_causal = first_causal if isinstance(first_causal, dict) else {}
        return [
            _bcg_row(
                "P0",
                "Restore the missing external preflight configuration before starting a new E2E run.",
                root_cause,
                f"Blocked at {first_causal.get('stage') or 'PREFLIGHT'} before research, generation, judges, and final assembly.",
            ),
            _bcg_row(
                "P1",
                "Keep the canonical preflight RCA and zero-retry accounting mandatory on every blocked run.",
                str(operational.get("retry_analysis") or {}),
                "Do not replace the recorded failure with a bare launcher exception or post-run backfill.",
            ),
        ]
    if research_status == "P0_STATIC_MANUAL_BRIEF_USED":
        rows.extend(
            [
                _bcg_row(
                    "P0",
                    "Fail closed when auto_research_internal=True but apps_research delegation does not execute.",
                    str(research.get("past_fail_blocker") or "research_delegation_executed=False"),
                    "Block before section generation.",
                ),
                _bcg_row(
                    "P0",
                    "Keep row 0 named research_briefing_input; do not call it apps_research unless apps_research actually ran.",
                    str(research.get("past_fail_blocker") or "research_delegation_executed=False"),
                    "Prevent false provenance.",
                ),
                _bcg_row(
                    "P0",
                    "Require a fresh research artifact or explicit operator skip before resume lanes run.",
                    str(research.get("past_fail_blocker") or "static manual brief"),
                    "Block stale/manual research.",
                ),
            ]
        )
    first_blocker = evidence["competencies_blocker"]
    if isinstance(first_blocker, dict):
        rows.append(
            _bcg_row(
                "P0",
                "Fix competencies first-lane execution failure before scheduling downstream lanes.",
                str(first_blocker.get("evidence") or first_blocker.get("classification") or "competencies blocked"),
                "No downstream lane without upstream authorization.",
            )
        )
    if evidence["blocked_generated_lanes"]:
        rows.append(
            _bcg_row(
                "P0",
                "Fix X3-blocked generated lanes before authorizing the final resume.",
                ", ".join(evidence["blocked_generated_lanes"]),
                "Outcome remains blocked until every required generated lane clears X3.",
            )
        )
    if evidence["final_aggregation_blockers"]:
        rows.append(
            _bcg_row(
                "P0",
                "Fix final_resume_aggregation before authorizing the final resume.",
                " | ".join(evidence["final_aggregation_blockers"]),
                "Outcome remains blocked until full-resume aggregation clears X2/product gates.",
            )
        )
    if evidence["final_status"] != "PASS":
        rows.append(
            _bcg_row(
                "P0",
                "Keep final resume product gate failed while generated-section gap markers exist.",
                ", ".join(str(x) for x in evidence["failed_final"]) or evidence["final_status"],
                "Final resume unauthorized.",
            )
        )
    if evidence["provider_gap_sections"]:
        rows.append(
            _bcg_row(
                "P1",
                "Capture provider attempts, retries, fallback, and observed model IDs for failed lanes.",
                "Provider proof gap in: " + ", ".join(evidence["provider_gap_sections"]),
                "Make failure RCA auditable.",
            )
        )
    if evidence["phase1_no_run_lanes"]:
        rows.append(
            _bcg_row(
                "P1",
                "Add dependency-token reporting for every PHASE1_NO_RUN_DIR lane.",
                "PHASE1_NO_RUN_DIR lanes: " + ", ".join(evidence["phase1_no_run_lanes"]),
                "Show exact upstream repair order.",
            )
        )
    if research_source_class in {"", "NOT_OBSERVED"}:
        rows.append(
            _bcg_row(
                "PX",
                "Add research source class to the locked BCG and lane table.",
                str(research.get("past_fail_blocker") or "research_source_class=NOT_OBSERVED"),
                "Distinguish FRESH_APPS_RESEARCH, STATIC_MANUAL_BRIEF, and OPERATOR_SKIP.",
            )
        )
    if research_source_class == "STATIC_MANUAL_BRIEF":
        rows.append(
            _bcg_row(
                "PX",
                "Compare latest run to prior passing research wiring when latest run uses a static/manual research path.",
                str(research.get("past_fail_blocker") or "research_source_class=STATIC_MANUAL_BRIEF"),
                "Surface regression automatically.",
            )
        )
    rows.extend(_clean_pass_hardening_rows(doc, evidence))
    return rows


def _build_bcg_recommended_next_moves(doc: dict[str, Any], recommendations: list[dict[str, str]]) -> list[str]:
    summary = doc.get("result_summary") if isinstance(doc.get("result_summary"), dict) else {}
    final_out = doc.get("final_resume_output") if isinstance(doc.get("final_resume_output"), dict) else {}
    authorized = bool(summary.get("outcome_authorized")) and str(final_out.get("status") or "UNKNOWN") == "PASS"
    if authorized:
        return [
            "Preserve the generated output package and run evidence.",
            "Review the mandatory ledger and section-status table for audit details.",
            "Treat future edits as new changes requiring the same X2/X3 gates.",
        ]
    p0_rows = [row for row in recommendations if row.get("priority") == "P0"]
    if p0_rows:
        first = p0_rows[0]
        moves = [
            f"Resolve P0: {first['recommendation']} Evidence: {first['evidence']}.",
        ]
        if len(p0_rows) > 1:
            moves.append(f"Resolve the remaining {len(p0_rows) - 1} P0 row(s) before rerun.")
        moves.extend(
            [
                "Rerun the integrated apps_rg path only after the listed P0 evidence clears.",
                "Treat final assembly as valid only when every required section and product output is product-authorized.",
            ]
        )
        return moves
    if recommendations:
        first = recommendations[0]
        return [
            f"Resolve {first['priority']}: {first['recommendation']} Evidence: {first['evidence']}.",
            "Rerender the mandatory BCG and section ledger after that evidence changes.",
        ]
    return ["No evidence-backed BCG recommendation was generated; inspect the mandatory ledger before rerun."]


def _bcg_truth_errors(doc: dict[str, Any], recommendations: list[dict[str, str]], next_moves: list[str]) -> list[str]:
    evidence = _active_bcg_evidence(doc)
    errors: list[str] = []
    p0_rows = [row for row in recommendations if row.get("priority") == "P0"]
    for idx, row in enumerate(recommendations):
        recommendation = str(row.get("recommendation") or "")
        row_evidence = str(row.get("evidence") or "")
        if not recommendation.strip() or not row_evidence.strip():
            errors.append(f"bcg.recommendations[{idx}].empty")
        if "X3-blocked generated lanes" in recommendation and not evidence["blocked_generated_lanes"]:
            errors.append(f"bcg.recommendations[{idx}].no_x3_blocked_lanes")
        if "final_resume_aggregation" in recommendation and not evidence["final_aggregation_blockers"]:
            errors.append(f"bcg.recommendations[{idx}].no_final_aggregation_blocker")
        if "final resume product gate failed" in recommendation and evidence["final_status"] == "PASS":
            errors.append(f"bcg.recommendations[{idx}].final_status_pass")
        if "provider attempts" in recommendation and not evidence["provider_gap_sections"]:
            errors.append(f"bcg.recommendations[{idx}].no_provider_gap")
        if "PHASE1_NO_RUN_DIR" in recommendation and not evidence["phase1_no_run_lanes"]:
            errors.append(f"bcg.recommendations[{idx}].no_phase1_no_run_dir")
        if "research source class" in recommendation and evidence["research_source_class"] not in {"", "NOT_OBSERVED"}:
            errors.append(f"bcg.recommendations[{idx}].research_source_class_already_present")
        if "static/manual research path" in recommendation and evidence["research_source_class"] != "STATIC_MANUAL_BRIEF":
            errors.append(f"bcg.recommendations[{idx}].not_static_manual_research")
        if "apps_research delegation does not execute" in recommendation and evidence["research_status"] != "P0_STATIC_MANUAL_BRIEF_USED":
            errors.append(f"bcg.recommendations[{idx}].research_not_static_manual_p0")
    joined_next = " ".join(str(item) for item in next_moves)
    if p0_rows:
        if "P0" not in joined_next:
            errors.append("bcg.recommended_next_move.missing_p0_reference")
        first_evidence = str(p0_rows[0].get("evidence") or "")
        if first_evidence and first_evidence not in joined_next:
            errors.append("bcg.recommended_next_move.missing_active_p0_evidence")
    elif "P0" in joined_next:
        errors.append("bcg.recommended_next_move.stale_p0_reference")
    inline = doc.get("inline_required_output") if isinstance(doc.get("inline_required_output"), dict) else {}
    bcg = inline.get("bcg") if isinstance(inline.get("bcg"), dict) else {}
    issue_tree = bcg.get("issue_tree") if isinstance(bcg.get("issue_tree"), list) else []
    evidence_map = bcg.get("evidence_map") if isinstance(bcg.get("evidence_map"), list) else []
    errors.extend(_bcg_forensics_truth_errors(doc, issue_tree, evidence_map))
    return errors


def _bcg_forensics_truth_errors(
    doc: dict[str, Any],
    issue_tree: list[Any],
    evidence_map: list[Any],
) -> list[str]:
    gate = _forensic_gate(doc)
    if not gate.get("required"):
        return []
    artifacts = _forensic_artifact_by_section(doc)
    required_sections = set(artifacts)
    evidence_blob = "\n".join(
        f"{row.get('label') or ''} {row.get('path') or ''}"
        for row in evidence_map
        if isinstance(row, dict)
    )
    issue_sections = {
        str(row.get("section") or "")
        for row in issue_tree
        if isinstance(row, dict) and str(row.get("section") or "")
    }
    errors: list[str] = []
    if not required_sections:
        errors.append("bcg.forensics.required_without_artifacts")
    for section_id in sorted(required_sections):
        artifact = artifacts[section_id]
        json_path = str(artifact.get("json_path") or "")
        md_path = str(artifact.get("md_path") or "")
        represented = section_id in issue_sections or section_id in evidence_blob
        if not represented:
            errors.append(f"bcg.forensics.missing_failed_section:{section_id}")
        if not json_path or json_path not in evidence_blob:
            errors.append(f"bcg.forensics.missing_json_ref:{section_id}")
        if not md_path or md_path not in evidence_blob:
            errors.append(f"bcg.forensics.missing_md_ref:{section_id}")
        if artifact.get("complete") is not True:
            errors.append(f"bcg.forensics.incomplete_artifact:{section_id}")
    for row in issue_tree:
        if not isinstance(row, dict):
            continue
        section_id = str(row.get("section") or "")
        if not section_id or section_id == "research_briefing_input":
            continue
        artifact = artifacts.get(section_id)
        if artifact is None:
            errors.append(f"bcg.issue_tree.missing_forensic_artifact:{section_id}")
        elif artifact.get("complete") is not True:
            errors.append(f"bcg.issue_tree.incomplete_forensic_artifact:{section_id}")
    return errors

