"""Markdown rendering for mandatory outputs and BCG executive readouts."""
from __future__ import annotations

import html
import json
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

__all__ = ['_render_causal_allocation_lines', '_wide_markdown_code_cell', '_render_section_lane_table_lines', '_render_resume_inline_lines', '_render_mandatory_markdown', '_render_bcg_markdown', '_render_bcg_markdown_locked']

def _render_causal_allocation_lines(finding: dict[str, Any], *, indent: str) -> list[str]:
    allocation = _validated_causal_allocation(finding)
    if allocation is None:
        return [
            f"{indent}- **RCA format gap:** missing causal allocation with concrete root-cause-linked rows."
        ]
    lines = [
        f"{indent}- Causal allocation:",
        f"{indent}  - Dominant cause: {allocation['dominant_cause']}",
        (
            f"{indent}  - Retry recoverability: `{allocation['retry_recoverability']}` - "
            f"{allocation['retry_recoverability_reason']}"
        ),
        f"{indent}  - Allocation rows:",
    ]
    for row in allocation["allocation"]:
        evidence = ", ".join(str(ref) for ref in row.get("evidence_refs") or [])
        lines.append(
            f"{indent}    - `{row['domain']}` / `{row['causal_role']}` / "
            f"`{row['work_share']}`: {row['root_cause_link']} "
            f"Evidence: `{_markdown_table_escape(evidence)}`. "
            f"Required work: {row['required_work']}"
        )
    return lines


def _wide_markdown_code_cell(value: Any, *, min_width_ch: int = 32) -> str:
    text = html.escape(str(value if value is not None else "-"), quote=False)
    text = text.replace("|", "&#124;").replace("\n", " ")
    for marker in ("; blocker=", "; reason=", "; ref=", "; target="):
        text = text.replace(marker, marker.replace("; ", ";<br>"))
    return (
        f'<span style="display:inline-block; min-width:{min_width_ch}ch; '
        f'white-space:normal"><code>{text}</code></span>'
    )


def _render_section_lane_table_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Section Lane Summary Table",
        "",
        "| # | Section | Research source class | R1A | R1B | Lane record | Provider call attempted | Primary provider | Primary model observed | Pooling selector LLM | Secondary provider | Secondary model observed | Generation status | Judges run | Judge models / scores | Judge retry / fallback | <span style=\"display:inline-block; min-width:32ch\">X2</span> | <span style=\"display:inline-block; min-width:32ch\">X3</span> | <span style=\"display:inline-block; min-width:44ch\">Past fail / blocker</span> | Display output | L6 evidence |",
        "|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    if not rows:
        lines.append("| 0 | `NO_ROWS` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NO` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NO` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `NOT_OBSERVED` | `mandatory section lane table missing` | `MISSING` | `NOT_OBSERVED` |")
        return lines
    for row in rows:
        lines.append(
            "| "
            f"{row.get('order')} | "
            f"`{_markdown_table_escape(row.get('section'))}` | "
            f"`{_markdown_table_escape(row.get('research_source_class'))}` | "
            f"`{_markdown_table_escape(row.get('r1a'))}` | "
            f"`{_markdown_table_escape(row.get('r1b'))}` | "
            f"`{_markdown_table_escape(row.get('lane_record'))}` | "
            f"`{_markdown_table_escape(row.get('provider_call_attempted'))}` | "
            f"`{_markdown_table_escape(row.get('primary_provider'))}` | "
            f"`{_markdown_table_escape(row.get('primary_model_observed'))}` | "
            f"`{_markdown_table_escape(row.get('pooling_selector_llm'))}` | "
            f"`{_markdown_table_escape(row.get('secondary_provider'))}` | "
            f"`{_markdown_table_escape(row.get('secondary_model_observed'))}` | "
            f"`{_markdown_table_escape(row.get('generation_status'))}` | "
            f"`{_markdown_table_escape(row.get('judges_run'))}` | "
            f"`{_markdown_table_escape(row.get('judge_models_scores'))}` | "
            f"`{_markdown_table_escape(row.get('judge_retry_fallback'))}` | "
            f"{_wide_markdown_code_cell(row.get('x2'))} | "
            f"{_wide_markdown_code_cell(row.get('x3'))} | "
            f"{_wide_markdown_code_cell(row.get('past_fail_blocker'), min_width_ch=44)} | "
            f"`{_markdown_table_escape(row.get('display_output'))}` | "
            f"`{_markdown_table_escape(row.get('l6_evidence'))}` |"
        )
    return lines


def _render_resume_inline_lines(doc: dict[str, Any]) -> list[str]:
    inline = doc.get("inline_required_output") if isinstance(doc.get("inline_required_output"), dict) else {}
    resume = (
        inline.get("resume_docx_full_version_inline")
        if isinstance(inline.get("resume_docx_full_version_inline"), dict)
        else {}
    )
    source = str(resume.get("source") or "No inline resume source observed.")
    text = str(resume.get("text") or "").rstrip()
    return [
        "## Resume DOCX Full Version Inline",
        "",
        f"Source: `{source}`",
        "",
        "```text",
        text or "[MANDATORY_OUTPUT_MISSING: resume_docx_full_version_inline.text]",
        "```",
    ]


def _render_mandatory_markdown(doc: dict[str, Any]) -> str:
    summary = doc["result_summary"]
    sections = doc["sections"]
    counts = doc["section_counts"]
    rca = doc["rca_findings"]
    final_out = doc.get("final_resume_output") if isinstance(doc.get("final_resume_output"), dict) else {}
    lane_table = doc.get("section_lane_table") if isinstance(doc.get("section_lane_table"), list) else []
    inline_gates = doc.get("mandatory_inline_output_gates") if isinstance(doc.get("mandatory_inline_output_gates"), list) else []
    lines = [
        "# apps_rg Mandatory Run Output",
        "",
        f"Generated: `{doc['generated_at_utc']}`",
        f"Run root: `@{doc['run_root_abs']}`",
        "",
        "## Outcome",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Exit status | `{summary.get('exit_status') or '-'}` |",
        f"| Execution status | `{summary.get('execution_status') or '-'}` |",
        f"| Outcome authorized | `{summary.get('outcome_authorized')}` |",
        f"| X3 disposition | `{summary.get('x3_disposition') or '-'}` |",
        f"| Fault | `{_markdown_table_escape(summary.get('fault') or '-')}` |",
        f"| Integrated proof gate | `{summary.get('proof_gate_status') or '-'}` `{summary.get('proof_classification') or '-'}` |",
        f"| Final resume output gate | `{final_out.get('status') or 'UNKNOWN'}` |",
        "",
        "## Mandatory Inline Output Gates",
        "",
        "| Gate | Status | Observed |",
        "|---|---|---|",
    ]
    for gate in inline_gates:
        if not isinstance(gate, dict):
            continue
        lines.append(
            "| "
            f"`{gate.get('gate_id')}` | "
            f"`{'PASS' if gate.get('pass') is True else 'FAIL'}` | "
            f"`{_markdown_table_escape(gate.get('observed_value'))}` |"
        )
    lines.extend(
        [
            "",
        "## Section Counts",
        "",
        "| Total | Real LLM | X3 allow | X3 block | Pre-run blocked | Not run | Unknown/other |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| {counts['total']} | {counts['ran_real_llm']} | {counts['allowed']} | "
            f"{counts['blocked']} | {counts['pre_run_blocked']} | {counts['not_run']} | "
            f"{counts['unknown']} |"
        ),
        "",
        ]
    )
    lines.extend(_render_section_lane_table_lines(lane_table))
    lines.extend(
        [
            "",
        "## Section Execution Ledger",
        "",
        "| Section | Ran status | X3 | X2 | Product | Runtime | Failed gates | Display |",
        "|---|---|---|---|---|---|---|---|",
        ]
    )
    for section in sections:
        failed = ", ".join(
            str(g.get("gate_id"))
            for g in section.get("failed_gates") or []
            if isinstance(g, dict)
        )
        lines.append(
            "| "
            f"`{section.get('section')}` | `{section.get('status_bucket')}` | "
            f"`{section.get('x3_code')}` | `{section.get('x2_pass')}` | "
            f"`{section.get('product_quality_status')}` | "
            f"`{section.get('runtime_generation_status')}` | "
            f"`{_markdown_table_escape(failed or '-')}` | "
            f"`{_markdown_table_escape(section.get('display_txt_relpath') or '-')}` |"
        )
    lines.extend(
        [
            "",
            "## Final Resume Product Outputs",
            "",
            "| Artifact | Path | Status | Bytes | SHA256 |",
            "|---|---|---|---:|---|",
        ]
    )
    final_artifacts = (
        ("Canonical final resume JSON", final_out.get("final_resume_json")),
        ("Rendered final resume text", final_out.get("rendered_resume_text")),
        ("Final resume DOCX", final_out.get("resume_docx")),
    )
    resume_inline_authorized, _resume_inline_blockers = _resume_inline_authorization(doc)
    for label, art in final_artifacts:
        art = art if isinstance(art, dict) else {}
        exists = (
            "PASS"
            if art.get("exists") and resume_inline_authorized
            else "EXISTS_UNAUTHORIZED"
            if art.get("exists")
            else "MISSING"
        )
        lines.append(
            "| "
            f"{label} | `{_markdown_table_escape(art.get('relpath') or '-')}` | "
            f"`{exists}` | {int(art.get('bytes') or 0)} | "
            f"`{_markdown_table_escape(art.get('sha256') or '-')}` |"
        )
    failed_final = final_out.get("failed_gate_ids") if isinstance(final_out.get("failed_gate_ids"), list) else []
    lines.extend(
        [
            "",
            "| Gate | Status | Observed |",
            "|---|---|---|",
        ]
    )
    for gate in final_out.get("gates") or []:
        if not isinstance(gate, dict):
            continue
        lines.append(
            "| "
            f"`{gate.get('gate_id')}` | "
            f"`{'PASS' if gate.get('pass') is True else 'FAIL'}` | "
            f"`{_markdown_table_escape(gate.get('observed_value'))}` |"
        )
    if failed_final:
        lines.append("")
        lines.append(f"Final resume output failed gates: `{_markdown_table_escape(', '.join(str(g) for g in failed_final))}`")
    lines.extend(["", "## Judge Execution Ledger", ""])
    lines.append("| Section | Judge | Model | Status | Score | Threshold | Pass | Issues |")
    lines.append("|---|---|---|---|---:|---:|---|---|")
    for section in sections:
        judges = section.get("judges") or []
        issues = section.get("judge_issue_summary") or {}
        issue_text = ", ".join(
            f"{key}={','.join(str(x) for x in val)}"
            for key, val in issues.items()
            if isinstance(val, list) and val
        )
        if not judges:
            reason = "section_not_run" if section.get("status_bucket") in {"not_run", "pre_run_blocked"} else "no_judge_rows_observed"
            lines.append(
                f"| `{section.get('section')}` | `-` | `-` | `{reason}` |  |  | `UNKNOWN` | `{_markdown_table_escape(issue_text or '-')}` |"
            )
            continue
        for judge in judges:
            passed = "PASS" if judge.get("pass") is True else "FAIL" if judge.get("pass") is False else "UNKNOWN"
            lines.append(
                "| "
                f"`{section.get('section')}` | `{_markdown_table_escape(judge.get('provider'))}` | "
                f"`{_markdown_table_escape(judge.get('model') or '-')}` | "
                f"`{_markdown_table_escape(judge.get('provider_status') or '-')}` | "
                f"{_score_text(judge.get('score'))} | {_score_text(judge.get('threshold'))} | "
                f"`{passed}` | `{_markdown_table_escape(issue_text or '-')}` |"
            )
    lines.extend(["", "## RCA Findings", ""])
    if not rca:
        lines.append("- No blocking RCA findings recorded.")
    else:
        for idx, finding in enumerate(rca, 1):
            lines.append(f"{idx}. `{finding['section']}` - {finding['classification']}")
            lines.append(f"   - Root cause: {finding.get('root_cause') or '-'}")
            lines.append(
                f"   - Evidence: `{_markdown_table_escape(finding.get('evidence') or '-')}`"
            )
            lines.extend(_render_causal_allocation_lines(finding, indent="   "))
            lines.append("   - Required implementation plan:")
            for item in _validated_plan_items(finding):
                lines.append(f"     - {item}")
    forensics = (
        doc.get("section_failure_forensics")
        if isinstance(doc.get("section_failure_forensics"), dict)
        else {}
    )
    lines.extend(["", "## Section Failure Forensics", ""])
    lines.append(
        f"Gate `{forensics.get('gate_id') or E2E_SECTION_FORENSICS_GATE_ID}`: "
        f"`{'PASS' if forensics.get('pass', True) else 'FAIL'}`"
    )
    lines.append(f"- Required: `{bool(forensics.get('required'))}`")
    lines.append(f"- Failed section count: `{forensics.get('failed_section_count') or 0}`")
    lines.append(f"- Artifact directory: `{forensics.get('artifact_dir') or '-'}`")
    lines.append(f"- Baseline confidence: `{forensics.get('baseline_confidence') or '-'}`")
    artifacts = forensics.get("artifacts") if isinstance(forensics.get("artifacts"), list) else []
    if artifacts:
        lines.extend(
            [
                "",
                "| Section | Failure type | Complete | Comparison | JSON | MD |",
                "|---|---|---:|---:|---|---|",
            ]
        )
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            section_id = str(artifact.get("section_id") or "unknown")
            comparison = _load_json(
                Path(str(doc.get("run_root_abs") or ""))
                / SECTION_FAILURE_FORENSICS_DIR
                / f"{section_id}.json"
            )
            lines.append(
                "| "
                f"`{section_id}` | "
                f"`{artifact.get('failure_type')}` | "
                f"`{artifact.get('complete')}` | "
                f"`{comparison.get('comparison_complete')}` | "
                f"`{artifact.get('json_path')}` | "
                f"`{artifact.get('md_path')}` |"
            )
    lines.extend(["", "## L6 Shadow Observability", ""])
    lines.append("| Section | L6 files | Authority |")
    lines.append("|---|---:|---|")
    for section in sections:
        l6 = section.get("l6") or {}
        lines.append(
            f"| `{section.get('section')}` | {int(l6.get('file_count') or 0)} | `{l6.get('product_authority') or '-'}` |"
        )
    lines.extend([""])
    lines.extend(_render_resume_inline_lines(doc))
    return "\n".join(lines)


def _render_bcg_markdown(doc: dict[str, Any]) -> str:
    summary = doc["result_summary"]
    sections = doc["sections"]
    counts = doc["section_counts"]
    rca = doc["rca_findings"]
    final_out = doc.get("final_resume_output") if isinstance(doc.get("final_resume_output"), dict) else {}
    failed_count = counts["blocked"] + counts["pre_run_blocked"] + counts["not_run"]
    final_status = str(final_out.get("status") or "UNKNOWN")
    final_gate_blocks = final_status == "FAIL"
    authorized = bool(summary.get("outcome_authorized")) and not final_gate_blocks
    blocker_text = (
        "final resume output gate failed"
        if final_gate_blocks
        else summary.get("fault") or summary.get("decisive_reason") or "section gates / aggregation"
    )
    if authorized:
        answer = "The run reached an authorized product outcome. Preserve the generated outputs and review the run ledger for section and judge proof."
    elif failed_count:
        answer = (
            "The run did not fail because every section was unusable. It failed because "
            f"{failed_count} section or aggregation surfaces were not product-authorized, "
            "so final assembly was correctly blocked."
        )
    else:
        answer = "The run was not product-authorized, but no section-level blocker was classified; inspect terminal fault and proof-gate evidence."
    lines = [
        "# BCG Executive Output - apps_rg Run",
        "",
        f"Generated: `{doc['generated_at_utc']}`",
        f"Run root: `@{doc['run_root_abs']}`",
        "",
        "## Executive Answer",
        "",
        answer,
        "",
        "## Board-Level Readout",
        "",
        "| Question | Answer |",
        "|---|---|",
        f"| Did real generation run? | `{counts['ran_real_llm']}` section(s) reported `REAL_LLM`. |",
        f"| Was a final product authorized? | `{summary.get('outcome_authorized')}` |",
        f"| What blocked the run? | `{_markdown_table_escape('None - all required sections, final aggregation, and product outputs are authorized' if authorized else blocker_text)}` |",
        f"| Final resume output gate | `{final_out.get('status') or 'UNKNOWN'}` |",
        f"| Primary decision | `{_markdown_table_escape('Preserve outputs and review evidence ledgers; no blocker remediation required.' if authorized else 'Fix targeted blockers and rerun; do not weaken X2/X3 gates.')}` |",
        "",
        "## Run Scorecard",
        "",
        "| Section | Result | Interpretation | Required fix |",
        "|---|---|---|---|",
    ]
    for section in sections:
        x3 = str(section.get("x3_code") or "")
        bucket = str(section.get("status_bucket") or "")
        if x3 == "X3_ALLOW":
            interp = (
                "Authorized final assembly output."
                if section.get("section") == "final_resume_aggregation"
                else "Usable candidate content; product-authorized for this run."
            )
        elif bucket == "pre_run_blocked":
            interp = "Did not become eligible because an upstream dependency failed."
        elif bucket == "not_run":
            interp = "Did not run in this execution path."
        else:
            interp = str(section.get("failure_classification") or "Requires review.")
        if x3 == "X3_ALLOW":
            required_fix = "No blocker; preserve section evidence for assembly."
        else:
            required_fix = "See root-cause implementation plan in Issue Tree."
        lines.append(
            f"| `{section.get('section')}` | `{x3 or bucket}` | "
            f"{_markdown_table_escape(interp)} | {_markdown_table_escape(required_fix)} |"
        )
    lines.extend(["", "## Issue Tree", ""])
    if not rca:
        lines.append("- No blocking issue tree was generated from section evidence.")
    else:
        for finding in rca:
            lines.append(
                f"- `{finding['section']}`: {finding['classification']} "
                f"({finding['evidence']})."
            )
            lines.append(f"  - Root cause: {finding.get('root_cause') or '-'}")
            lines.extend(_render_causal_allocation_lines(finding, indent="  "))
            lines.append("  - Required implementation plan:")
            for item in _validated_plan_items(finding):
                lines.append(f"    - {item}")
    lines.extend(["", "## Recommended Next Move", ""])
    if authorized:
        lines.append("1. Preserve the generated output package and run evidence.")
        lines.append("2. Review the mandatory ledger and section-status table for audit details.")
        lines.append("3. Treat future edits as new changes requiring the same X2/X3 gates.")
    elif final_gate_blocks:
        lines.append("1. Fix the final resume output gates before treating the run as product-ready.")
        lines.append("2. Regenerate the mandatory final resume text and DOCX from the canonical spine.")
        lines.append("3. Re-render the mandatory ledger and summary after the product outputs pass.")
    else:
        lines.append("1. Fix the P0 blocker sections named above.")
        lines.append("2. Rerun the integrated apps_rg path with the same JD and briefing.")
        lines.append("3. Treat final assembly as valid only when every required section is product-authorized.")
    lines.extend(["", "## Evidence Map", ""])
    lines.append(f"- Mandatory run ledger: `@{doc['run_root_abs']}\\{MANDATORY_RUN_OUTPUT_MD}`")
    lines.append(f"- Machine-readable ledger: `@{doc['run_root_abs']}\\{MANDATORY_RUN_OUTPUT_JSON}`")
    lines.append(f"- Rendered final resume: `@{doc['run_root_abs']}\\{FINAL_RESUME_OUTPUT_TXT}`")
    lines.append(f"- Final resume output contract: `@{doc['run_root_abs']}\\{FINAL_RESUME_OUTPUT_JSON}`")
    lines.append(f"- Resume DOCX: `@{doc['run_root_abs']}\\{FINAL_RESUME_DOCX_RELPATH}`")
    lines.append(f"- Section status: `@{doc['run_root_abs']}\\{FULL_RUN_SECTION_STATUS_JSON}`")
    lines.append(f"- Review bundle: `@{doc['run_root_abs']}\\{REVIEW_BUNDLE_FILENAME}`")
    return "\n".join(lines)


def _render_bcg_markdown_locked(doc: dict[str, Any]) -> str:
    inline = doc.get("inline_required_output") if isinstance(doc.get("inline_required_output"), dict) else {}
    if inline:
        return _render_locked_bcg_from_inline(inline, doc)
    summary = doc["result_summary"]
    counts = doc["section_counts"]
    rca = doc["rca_findings"]
    final_out = doc.get("final_resume_output") if isinstance(doc.get("final_resume_output"), dict) else {}
    final_status = str(final_out.get("status") or "UNKNOWN")
    authorized = bool(summary.get("outcome_authorized")) and final_status == "PASS"
    blocked_count = counts["blocked"] + counts["pre_run_blocked"] + counts["not_run"]
    status = "AUTHORIZED" if authorized else "BLOCKED"
    business_read = (
        "Final resume package is authorized; preserve the generated product and evidence ledgers."
        if authorized
        else (
            "No final resume can be authorized until mandatory generated-section gaps and "
            "final product gates are resolved. Locked base-resume fields are still rendered inline for review."
        )
    )
    technical_read = (
        f"Sections total={counts['total']}, REAL_LLM={counts['ran_real_llm']}, "
        f"X3 allow={counts['allowed']}, blocked/pre-run/not-run={blocked_count}, "
        f"final_resume_output_gate={final_status}."
    )
    priority_rows: list[dict[str, str]] = []
    failed_final = final_out.get("failed_gate_ids") if isinstance(final_out.get("failed_gate_ids"), list) else []
    if final_status != "PASS":
        priority_rows.append(
            {
                "priority": "P0",
                "finding": "Final resume product output gate is not PASS.",
                "evidence": ", ".join(str(x) for x in failed_final) or final_status,
                "required_action": "Keep final output blocked while preserving mandatory inline resume, JSON spine, and DOCX evidence.",
            }
        )
    for finding in rca[:6]:
        if not isinstance(finding, dict):
            continue
        priority_rows.append(
            {
                "priority": "P0" if not authorized else "P1",
                "finding": f"{finding.get('section')}: {finding.get('classification')}",
                "evidence": str(finding.get("evidence") or "-"),
                "required_action": str(finding.get("action") or "Apply the root-cause implementation plan."),
            }
        )
    if not priority_rows:
        priority_rows.append(
            {
                "priority": "P1",
                "finding": "No blocking section RCA rows were emitted.",
                "evidence": "mandatory ledger",
                "required_action": "Preserve gates and continue rendering BCG, lane table, and full resume inline after each run.",
            }
        )

    lines = [
        "# BCG Executive Brief",
        "",
        f"Generated: `{doc['generated_at_utc']}`",
        f"Run root: `@{doc['run_root_abs']}`",
        "",
        "North star: Produce a complete, auditable resume output package with real generation provenance, judge evidence, final resume text, and DOCX output visible inline.",
        f"Decision status: `{status}`",
        f"Business read: {business_read}",
        f"Technical evidence: {technical_read}",
        "Priority rule: Fix P0 product-output and lane-authorization blockers before rerun; treat P1 rows as hardening opportunities after P0 clears.",
        "",
        "## Decision Gates",
        "",
        "| Gate | Status | Evidence |",
        "|---|---|---|",
        f"| Outcome authorization | `{'PASS' if authorized else 'FAIL'}` | `outcome_authorized={summary.get('outcome_authorized')}` |",
        f"| Real generation observed | `{'PASS' if counts['ran_real_llm'] else 'FAIL'}` | `{counts['ran_real_llm']}` REAL_LLM section(s) |",
        f"| Final resume output | `{'PASS' if final_status == 'PASS' else 'FAIL'}` | `{final_status}` |",
        "| Inline output contract | `PASS` | BCG, section lane table, and resume text are mandatory surfaces |",
        "",
        "## P0-P1 Opportunities",
        "",
        "| Priority | Finding | Evidence | Required action |",
        "|---|---|---|---|",
    ]
    for row in priority_rows:
        lines.append(
            "| "
            f"`{row['priority']}` | "
            f"{_markdown_table_escape(row['finding'])} | "
            f"`{_markdown_table_escape(row['evidence'])}` | "
            f"{_markdown_table_escape(row['required_action'])} |"
        )
    lines.extend(["", "## Issue Tree", ""])
    if not rca:
        lines.append("- No blocking issue tree was generated from section evidence.")
    else:
        for finding in rca:
            lines.append(
                f"- `{finding['section']}`: {finding['classification']} "
                f"({finding['evidence']})."
            )
            lines.append(f"  - Root cause: {finding.get('root_cause') or '-'}")
            lines.extend(_render_causal_allocation_lines(finding, indent="  "))
            lines.append("  - Required implementation plan:")
            for item in _validated_plan_items(finding):
                lines.append(f"    - {item}")
    lines.extend(["", "## Next Step", ""])
    if authorized:
        lines.append("1. Preserve the generated output package and run evidence.")
        lines.append("2. Review the mandatory ledger and section-status table for audit details.")
        lines.append("3. Treat future edits as new changes requiring the same X2/X3 gates.")
    else:
        lines.append("1. Fix the P0 blocker rows above.")
        lines.append("2. Rerun the integrated apps_rg path with the same JD and briefing.")
        lines.append("3. Treat final assembly as valid only when every required section and product output is product-authorized.")
    lines.extend(["", "## Evidence Map", ""])
    lines.append(f"- Mandatory run ledger: `@{doc['run_root_abs']}\\{MANDATORY_RUN_OUTPUT_MD}`")
    lines.append(f"- Machine-readable ledger: `@{doc['run_root_abs']}\\{MANDATORY_RUN_OUTPUT_JSON}`")
    lines.append(f"- Rendered final resume: `@{doc['run_root_abs']}\\{FINAL_RESUME_OUTPUT_TXT}`")
    lines.append(f"- Final resume output contract: `@{doc['run_root_abs']}\\{FINAL_RESUME_OUTPUT_JSON}`")
    lines.append(f"- Resume DOCX: `@{doc['run_root_abs']}\\{FINAL_RESUME_DOCX_RELPATH}`")
    lines.append(f"- Section status: `@{doc['run_root_abs']}\\{FULL_RUN_SECTION_STATUS_JSON}`")
    lines.append(f"- Review bundle: `@{doc['run_root_abs']}\\{REVIEW_BUNDLE_FILENAME}`")
    return "\n".join(lines)

