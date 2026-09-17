"""Resume inline authorization and output gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .section_lane_tables import *

__all__ = ['_resume_inline_authorization', '_blocked_resume_inline_text', '_resume_inline_source', '_authorized_resume_inline_text', '_resume_inline_text', '_inline_output_gates']

def _resume_inline_authorization(doc: dict[str, Any]) -> tuple[bool, list[str]]:
    summary = doc.get("result_summary") if isinstance(doc.get("result_summary"), dict) else {}
    final_out = doc.get("final_resume_output") if isinstance(doc.get("final_resume_output"), dict) else {}
    rendered = final_out.get("rendered_resume_text") if isinstance(final_out.get("rendered_resume_text"), dict) else {}
    docx = final_out.get("resume_docx") if isinstance(final_out.get("resume_docx"), dict) else {}
    spine = final_out.get("final_resume_json") if isinstance(final_out.get("final_resume_json"), dict) else {}
    reasons: list[str] = []
    if summary.get("outcome_authorized") is not True:
        reasons.append("outcome_authorized_false")
    if str(final_out.get("status") or "") != "PASS":
        reasons.append(f"final_resume_output_status={final_out.get('status') or 'UNKNOWN'}")
    failed_gates = final_out.get("failed_gate_ids")
    if isinstance(failed_gates, list) and failed_gates:
        reasons.append("failed_final_resume_gates=" + ",".join(str(gate) for gate in failed_gates))
    for artifact_label, artifact in (
        ("final_resume_json", spine),
        ("rendered_resume_text", rendered),
        ("resume_docx", docx),
    ):
        if not artifact.get("exists") or int(artifact.get("bytes") or 0) <= 0:
            reasons.append(f"{artifact_label}_missing_or_empty")
    for label, sections in _non_authorized_section_ids(doc).items():
        if sections:
            reasons.append(f"{label}=" + ",".join(sections))
    return not reasons, reasons


def _blocked_resume_inline_text(doc: dict[str, Any], reasons: list[str]) -> str:
    return "\n".join(
        [
            "NO_AUTHORIZED_RESUME_OUTPUT",
            "source_of_truth=current_e2e_run_artifacts_only",
            f"run_root={doc.get('run_root_abs') or 'UNKNOWN'}",
            "status=BLOCKED",
            "reason=" + ("; ".join(reasons) if reasons else "unknown_blocker"),
            "policy=do_not_inline_FINAL_RESUME_OUTPUT_txt_unless_current_run_authorized",
        ]
    )


def _resume_inline_source(doc: dict[str, Any], authorized: bool) -> str:
    if authorized:
        return (
            "FINAL_RESUME_OUTPUT.txt rendered from the current E2E run final-resume spine "
            "used for outputs/resume.docx."
        )
    return (
        "No authorized resume text emitted; this block is derived only from the current E2E "
        "run ledger and final-resume output contract."
    )


def _authorized_resume_inline_text(doc: dict[str, Any]) -> str:
    run_root = Path(str(doc.get("run_root_abs") or ""))
    resume_path = run_root / FINAL_RESUME_OUTPUT_TXT
    if not resume_path.is_file():
        return "[MANDATORY_OUTPUT_MISSING: FINAL_RESUME_OUTPUT.txt]"
    try:
        return resume_path.read_text(encoding="utf-8").rstrip() or "[MANDATORY_OUTPUT_EMPTY: FINAL_RESUME_OUTPUT.txt]"
    except OSError:
        return "[MANDATORY_OUTPUT_UNREADABLE: FINAL_RESUME_OUTPUT.txt]"


def _resume_inline_text(doc: dict[str, Any]) -> str:
    authorized, reasons = _resume_inline_authorization(doc)
    if not authorized:
        return _blocked_resume_inline_text(doc, reasons)
    return _authorized_resume_inline_text(doc)


def _inline_output_gates(doc: dict[str, Any]) -> list[dict[str, Any]]:
    from .bcg_forensics import _bcg_truth_errors
    from .proof_verifier import _inline_required_output_shape_errors
    final_out = doc.get("final_resume_output") if isinstance(doc.get("final_resume_output"), dict) else {}
    rendered = final_out.get("rendered_resume_text") if isinstance(final_out.get("rendered_resume_text"), dict) else {}
    docx = final_out.get("resume_docx") if isinstance(final_out.get("resume_docx"), dict) else {}
    spine = final_out.get("final_resume_json") if isinstance(final_out.get("final_resume_json"), dict) else {}
    lane_table = doc.get("section_lane_table") if isinstance(doc.get("section_lane_table"), list) else []
    inline = doc.get("inline_required_output") if isinstance(doc.get("inline_required_output"), dict) else {}
    bcg = inline.get("bcg") if isinstance(inline.get("bcg"), dict) else {}
    recs = bcg.get("p0_p1_px_recommendations") if isinstance(bcg.get("p0_p1_px_recommendations"), dict) else {}
    rec_rows = recs.get("rows") if isinstance(recs.get("rows"), list) else []
    rec_priorities = {str(row.get("priority") or "") for row in rec_rows if isinstance(row, dict)}
    next_moves = bcg.get("recommended_next_move") if isinstance(bcg.get("recommended_next_move"), list) else []
    bcg_truth_errors = _bcg_truth_errors(
        doc,
        [row for row in rec_rows if isinstance(row, dict)],
        [str(item) for item in next_moves],
    )
    row0 = lane_table[0] if lane_table and isinstance(lane_table[0], dict) else {}
    resume_inline = (
        inline.get("resume_docx_full_version_inline")
        if isinstance(inline.get("resume_docx_full_version_inline"), dict)
        else {}
    )
    resume_inline_authorized, resume_inline_blockers = _resume_inline_authorization(doc)
    shape_errors = _inline_required_output_shape_errors(inline)
    forensics = (
        doc.get("section_failure_forensics")
        if isinstance(doc.get("section_failure_forensics"), dict)
        else {}
    )
    gates = [
        {
            "gate_id": "mandatory_bcg_inline_output_present",
            "pass": True,
            "observed_value": BCG_EXECUTIVE_OUTPUT_MD,
            "threshold": "BCG executive markdown rendered inline",
        },
        {
            "gate_id": "mandatory_section_lane_table_inline_present",
            "pass": bool(lane_table),
            "observed_value": len(lane_table),
            "threshold": ">=1 lane table row",
        },
        {
            "gate_id": "mandatory_resume_text_inline_present",
            "pass": resume_inline_authorized
            and bool(rendered.get("exists"))
            and int(rendered.get("bytes") or 0) > 0,
            "observed_value": {
                "artifact": rendered,
                "current_run_authorized": resume_inline_authorized,
                "blockers": resume_inline_blockers,
            },
            "threshold": "current-run authorized nonempty FINAL_RESUME_OUTPUT.txt",
        },
        {
            "gate_id": "mandatory_final_resume_json_present",
            "pass": resume_inline_authorized
            and bool(spine.get("exists"))
            and int(spine.get("bytes") or 0) > 0,
            "observed_value": {
                "artifact": spine,
                "current_run_authorized": resume_inline_authorized,
                "blockers": resume_inline_blockers,
            },
            "threshold": f"current-run authorized {FINAL_RESUME_ASSEMBLY_JSON_RELPATH}",
        },
        {
            "gate_id": "mandatory_resume_docx_present",
            "pass": resume_inline_authorized
            and bool(docx.get("exists"))
            and int(docx.get("bytes") or 0) > 0,
            "observed_value": {
                "artifact": docx,
                "current_run_authorized": resume_inline_authorized,
                "blockers": resume_inline_blockers,
            },
            "threshold": f"current-run authorized {FINAL_RESUME_DOCX_RELPATH}",
        },
        {
            "gate_id": "mandatory_inline_required_json_shape_locked",
            "pass": not shape_errors,
            "observed_value": {
                "schema_version": inline.get("schema_version"),
                "immutable_section_order": inline.get("immutable_section_order"),
                "shape_errors": shape_errors,
            },
            "threshold": {
                "schema_version": INLINE_REQUIRED_OUTPUT_SCHEMA_VERSION,
                "immutable_section_order": list(INLINE_REQUIRED_OUTPUT_SECTION_ORDER),
                "top_level_keys": list(INLINE_REQUIRED_OUTPUT_TOP_LEVEL_KEYS),
            },
        },
        {
            "gate_id": "mandatory_bcg_p0_p1_px_recommendations_locked",
            "pass": (
                bcg.get("title") == "BCG Executive Output - apps_rg Run"
                and bcg.get("section_order") == list(BCG_LOCKED_SECTION_ORDER)
                and not bcg_truth_errors
            ),
            "observed_value": {
                "title": bcg.get("title"),
                "section_order": bcg.get("section_order"),
                "priorities": sorted(rec_priorities),
                "truth_errors": bcg_truth_errors,
            },
            "threshold": "BCG title + section order + evidence-backed recommendations and next moves",
        },
        {
            "gate_id": "mandatory_research_briefing_input_row0_locked",
            "pass": row0.get("order") == 0 and row0.get("section") == "research_briefing_input",
            "observed_value": {
                "order": row0.get("order"),
                "section": row0.get("section"),
                "generation_status": row0.get("generation_status"),
            },
            "threshold": "row 0 research_briefing_input",
        },
        {
            "gate_id": "mandatory_apps_research_row0_x1_x2_x3_gates_locked",
            "pass": (
                row0.get("order") == 0
                and row0.get("section") == "research_briefing_input"
                and str(row0.get("research_source_class") or "") not in {"", "NOT_OBSERVED"}
                and str(row0.get("x2") or "") not in {"", "NOT_OBSERVED"}
                and str(row0.get("x3") or "") not in {"", "NOT_OBSERVED"}
            ),
            "observed_value": {
                "research_source_class": row0.get("research_source_class"),
                "x2": row0.get("x2"),
                "x3": row0.get("x3"),
            },
            "threshold": "row 0 research_source_class plus compact X2/X3 handoff cells",
        },
        {
            "gate_id": "mandatory_resume_docx_inline_json_present",
            "pass": resume_inline_authorized
            and bool(str(resume_inline.get("text") or "").strip())
            and "NO_AUTHORIZED_RESUME_OUTPUT" not in str(resume_inline.get("text") or ""),
            "observed_value": {
                "title": resume_inline.get("title"),
                "text_chars": len(str(resume_inline.get("text") or "")),
                "current_run_authorized": resume_inline_authorized,
                "blockers": resume_inline_blockers,
            },
            "threshold": "resume_docx_full_version_inline.text is current-run authorized resume content",
        },
        {
            "gate_id": E2E_SECTION_FORENSICS_GATE_ID,
            "pass": bool(forensics.get("pass", True)),
            "observed_value": {
                "required": bool(forensics.get("required")),
                "failed_section_count": forensics.get("failed_section_count"),
                "artifact_dir": forensics.get("artifact_dir"),
                "missing_or_incomplete": forensics.get("missing_or_incomplete") or [],
            },
            "threshold": (
                "every non-X3_ALLOW, cascaded, or aggregation-failed section has complete "
                "section_failure_forensics/<section>.json and .md"
            ),
        },
    ]
    for gate in gates:
        gate["failure_reason"] = (
            ""
            if gate["pass"]
            else (
                E2E_SECTION_FORENSICS_GATE_ID
                if gate["gate_id"] == E2E_SECTION_FORENSICS_GATE_ID
                else "mandatory post-run inline output missing"
            )
        )
    return gates

