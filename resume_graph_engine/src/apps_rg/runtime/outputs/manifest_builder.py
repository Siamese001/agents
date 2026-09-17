"""Manifest builder for mandatory run output payloads."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .section_lane_tables import *
from .resume_inline import *
from .causal_plan import *
from .causal_allocation import *
from .bcg_forensics import *
from .bcg_inline_output import *
from .markdown_renderer import *
from .proof_verifier import *

__all__ = ['_result_summary', '_final_resume_output_required', 'build_mandatory_run_output']

def _result_summary(result: dict[str, Any] | None, run_root: Path) -> dict[str, Any]:
    result = result or {}
    result_pass = str(result.get("decisive_status") or "").upper() == "PASS" or (
        result.get("exit_code") == 0 and result.get("all_lanes_authorized") is True
    )
    terminal = _load_json(run_root / "terminal_ret_packet.json")
    terminal_payload = terminal.get("payload") if isinstance(terminal.get("payload"), dict) else {}
    exhaust = _load_json(run_root / "runtime_exhaust_bundle.json")
    exhaust_payload = exhaust.get("payload") if isinstance(exhaust.get("payload"), dict) else {}
    proof_gate = _load_json(run_root / "integrated_product_proof_gate_result.json")
    terminal_fault = "" if result_pass else str(terminal_payload.get("l2_fault") or "")
    x3_disposition = (
        result.get("x3_disposition")
        or ("X3_ALLOW" if result_pass else "")
        or terminal_payload.get("x3_disposition")
        or exhaust_payload.get("x3_disposition")
        or ""
    )
    fault = result.get("fault") or (terminal_fault if not result_pass else "")
    completion_status = str(result.get("completion_status") or "").upper()
    if not completion_status:
        completion_status = "PASS" if result_pass else "BLOCKED" if fault else "UNKNOWN"
    exit_status = result.get("exit_status") or (
        "success" if result_pass else "error" if terminal_fault else "unknown"
    )
    execution_completed = str(exit_status).strip().lower() == "success"
    return {
        "exit_status": exit_status,
        "execution_status": result.get("execution_status")
        or (
            "completed"
            if result_pass or execution_completed
            else "failed"
            if terminal_fault
            else "unknown"
        ),
        "outcome_authorized": bool(result.get("outcome_authorized") or result_pass),
        "decisive_status": result.get("decisive_status") or "",
        "all_lanes_authorized": result.get("all_lanes_authorized"),
        "x3_disposition": x3_disposition,
        "completion_disposition": result.get("completion_disposition") or x3_disposition,
        "completion_status": completion_status,
        "completion_fault": result.get("completion_fault") or "",
        "fault": fault,
        "run_id": result.get("run_id") or terminal_payload.get("run_id") or "",
        "request_id": result.get("request_id") or terminal_payload.get("request_id") or "",
        "proof_gate_status": proof_gate.get("status") or "",
        "proof_classification": proof_gate.get("proof_classification") or "",
        "decisive_reason": proof_gate.get("decisive_reason") or result.get("failure_reason") or "",
        "operational_failure": (
            dict(result.get("operational_failure") or {})
            if isinstance(result.get("operational_failure"), dict)
            else {}
        ),
        "research_artifact_dir": result.get("research_artifact_dir") or "",
        "research_briefing_path": result.get("research_briefing_path") or "",
        "research_company_brief_path": result.get("research_company_brief_path") or "",
        "research_handoff_v2_path": result.get("research_handoff_v2_path") or "",
        "apps_eval_record_ref": result.get("apps_eval_record_ref") or "",
        "l6_shadow_bridge_ref": result.get("l6_shadow_bridge_ref") or "",
        "l7_audit_status": result.get("l7_audit_status") or "",
    }


def _final_resume_output_required(run_root: Path, summary: dict[str, Any]) -> bool:
    return True


def build_mandatory_run_output(
    run_root: Path,
    *,
    repo_root: Path | None = None,
    result: dict[str, Any] | None = None,
    section_id: str | None = None,
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    repo = (repo_root or find_repo_root(root)).resolve()
    sections = _collect_section_records(root, repo_root=repo, section_id=section_id)
    result_summary = _result_summary(result, root)
    operational_failure = result_summary.get("operational_failure")
    operational_failure = operational_failure if isinstance(operational_failure, dict) else {}
    if operational_failure and not (
        (root / "lanes").is_dir() or (root / "modular_r4" / "sections").is_dir()
    ):
        sections = []
    operational_forensics: dict[str, Any] = {}
    display_sections = list(sections)
    if operational_failure:
        from apps_rg.runtime.e2e_operational_failure import (
            build_operational_failure_forensics,
        )

        baseline_ref = Path(
            str(operational_failure.get("baseline_ref") or os.environ.get("APPS_RG_E2E_BASELINE_REF") or "")
        )
        operational_forensics = build_operational_failure_forensics(
            run_root=root,
            repo_root=repo,
            failure=operational_failure,
            baseline_ref=baseline_ref,
        )
        section_record = operational_forensics.get("section_record")
        if isinstance(section_record, dict):
            display_sections.append(section_record)
    final_required = _final_resume_output_required(root, result_summary)
    final_output = _load_json(root / FINAL_RESUME_OUTPUT_JSON)
    if not final_output:
        final_output = build_final_resume_output_contract(root, repo_root=repo, required=final_required)
    section_lane_table = _build_section_lane_table(root, display_sections, repo_root=repo)
    section_failure_forensics = emit_section_failure_forensics(
        root,
        repo_root=repo,
        sections=sections,
        result=None if operational_failure and not sections else result_summary,
    )
    output_bisect_sections = _output_bisect_sections(
        root, section_failure_forensics
    )
    operational_bisect = operational_forensics.get("output_bisect")
    if isinstance(operational_bisect, dict):
        output_bisect_sections.insert(0, operational_bisect)
    rca_findings = _top_rca_sections(sections)
    operational_rca = operational_forensics.get("rca_finding")
    if isinstance(operational_rca, dict):
        rca_findings.insert(0, operational_rca)
    doc = {
        "schema_version": "apps_rg.mandatory_run_output.v1",
        "generated_at_utc": _utc_now(),
        "run_root_abs": str(root),
        "run_root": _repo_rel(root, repo),
        "result_summary": result_summary,
        "section_counts": _count_sections(display_sections),
        "sections": display_sections,
        "section_lane_table": section_lane_table,
        "final_resume_output": final_output,
        "rca_findings": rca_findings,
        "section_failure_forensics": section_failure_forensics,
        "operational_failure_forensics": operational_forensics,
        "output_bisect": {
            "required": bool(
                section_failure_forensics.get("required")
                or operational_forensics.get("required")
            ),
            "sections": output_bisect_sections,
        },
        "mandatory_artifacts": {
            "bcg_executive_output_md": BCG_EXECUTIVE_OUTPUT_MD,
            "output_bisect_md": OUTPUT_BISECT_MD,
            "mandatory_run_output_md": MANDATORY_RUN_OUTPUT_MD,
            "mandatory_run_output_json": MANDATORY_RUN_OUTPUT_JSON,
            "section_failure_forensics_dir": SECTION_FAILURE_FORENSICS_DIR,
            "final_resume_output_txt": FINAL_RESUME_OUTPUT_TXT,
            "final_resume_output_json": FINAL_RESUME_OUTPUT_JSON,
            "final_resume_docx": FINAL_RESUME_DOCX_RELPATH,
            "canonical_final_resume_json": FINAL_RESUME_ASSEMBLY_JSON_RELPATH,
        },
    }
    doc["inline_required_output"] = _build_inline_required_output(doc)
    doc["mandatory_inline_output_gates"] = _inline_output_gates(doc)
    return doc

