"""BCG inline output builder and locked section formatter."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .research_context import *
from .section_lane_tables import *
from .resume_inline import *
from .causal_plan import *
from .causal_allocation import *
from .bcg_forensics import *

__all__ = ['_build_bcg_issue_tree', '_build_inline_required_output', '_render_locked_bcg_from_inline']

def _build_bcg_issue_tree(doc: dict[str, Any]) -> list[dict[str, Any]]:
    issue_rows: list[dict[str, Any]] = []
    research = _research_row(doc)
    if research.get("generation_status") == "P0_STATIC_MANUAL_BRIEF_USED":
        issue_rows.append(
            {
                "section": "research_briefing_input",
                "classification": "P0_STATIC_MANUAL_BRIEF_USED",
                "root_cause": "The run carried auto_research_internal=True but did not execute apps_research delegation.",
                "evidence": [
                    "research_delegation_executed=False",
                    str(research.get("past_fail_blocker") or ""),
                ],
                "causal_allocation": {},
                "required_implementation_plan": [
                    "Add a fail-closed gate requiring research_delegation_executed=True when auto_research_internal=True.",
                    "Require a fresh apps_research artifact path and run receipt before apps_rg consumes briefing content.",
                    "Render briefing source, freshness date, and apps_research execution status in row 0.",
                    "Block resume lane execution unless research is explicitly skipped or freshly completed.",
                ],
            }
        )
    for finding in doc.get("rca_findings", []):
        if not isinstance(finding, dict):
            continue
        section_id = str(finding.get("section") or "")
        artifact = _forensic_artifact_by_section(doc).get(section_id)
        evidence = [str(finding.get("evidence") or "")]
        if isinstance(artifact, dict):
            evidence.extend(
                [
                    f"forensics_json={artifact.get('json_path') or ''}",
                    f"forensics_md={artifact.get('md_path') or ''}",
                    f"forensics_complete={artifact.get('complete')}",
                ]
            )
        issue_rows.append(
            {
                "section": section_id,
                "classification": str(finding.get("classification") or ""),
                "root_cause": str(finding.get("root_cause") or ""),
                "evidence": evidence,
                "causal_allocation": finding.get("causal_allocation"),
                "required_implementation_plan": _validated_plan_items(finding),
            }
        )
    return issue_rows


def _build_inline_required_output(doc: dict[str, Any]) -> dict[str, Any]:
    summary = doc["result_summary"]
    counts = doc["section_counts"]
    research = _research_row(doc)
    final_out = doc.get("final_resume_output") if isinstance(doc.get("final_resume_output"), dict) else {}
    final_status = str(final_out.get("status") or "UNKNOWN")
    authorized = bool(summary.get("outcome_authorized")) and final_status == "PASS"
    resume_inline_authorized, _resume_inline_blockers = _resume_inline_authorization(doc)
    research_status = str(research.get("generation_status") or "NOT_OBSERVED")
    if research_status == "P0_STATIC_MANUAL_BRIEF_USED":
        executive_answer = (
            "The run is blocked and must not authorize a final resume. The first P0 failure is that "
            "research was expected but apps_research did not run; the run consumed a static manual "
            "brief instead. Resume generation also failed to produce authorized content: "
            f"{counts['ran_real_llm']} sections reported REAL_LLM, {counts['pre_run_blocked']} lanes "
            "were pre-run blocked, and final resume assembly contains gap markers."
        )
    elif authorized:
        executive_answer = "The run reached an authorized product outcome. Preserve the generated outputs and review the run ledger for section and judge proof."
    else:
        completion_status = str(summary.get("completion_status") or "UNKNOWN")
        completion_fault = str(summary.get("completion_fault") or summary.get("fault") or "NOT_OBSERVED")
        x3_disposition = str(summary.get("x3_disposition") or "NOT_OBSERVED")
        executive_answer = (
            "The run is blocked and must not authorize a final resume. Required generation and/or "
            "final product gates did not clear. "
            f"The source X3 decision was {x3_disposition}, but completion ended {completion_status} "
            f"because {completion_fault}. Use the P0/P1/PX recommendations below as the repair order."
        )
    recommendations = _build_bcg_recommendations(doc)
    next_moves = _build_bcg_recommended_next_moves(doc, recommendations)
    primary_p0 = next((row for row in recommendations if row.get("priority") == "P0"), None)
    primary_blocker = (
        f"{primary_p0.get('recommendation')} Evidence: {primary_p0.get('evidence')}"
        if isinstance(primary_p0, dict)
        else str(research.get("generation_status") or summary.get("fault") or "NOT_OBSERVED")
    )
    board_rows = [
        {"question": "Did apps_research run?", "answer": "Yes" if research.get("provider_call_attempted") is True else "No"},
        {"question": "Research source class", "answer": str(research.get("research_source_class") or "NOT_OBSERVED")},
        {"question": "Research input used", "answer": str(research.get("primary_provider") or "NOT_OBSERVED")},
        {"question": "Briefing evidence", "answer": str(research.get("past_fail_blocker") or "NOT_OBSERVED")},
        {"question": "Did resume generation run?", "answer": f"{counts['ran_real_llm']} REAL_LLM section(s)"},
        {"question": "Source X3 decision", "answer": str(summary.get("x3_disposition") or "NOT_OBSERVED")},
        {"question": "Completion status", "answer": str(summary.get("completion_status") or "UNKNOWN")},
        {"question": "Completion fault", "answer": str(summary.get("completion_fault") or "NONE")},
        {"question": "Final product authorized?", "answer": str(summary.get("outcome_authorized"))},
        {"question": "Primary blocker", "answer": primary_blocker},
        {"question": "Decision", "answer": "Do not authorize; fix P0 gates first." if not authorized else "Authorized; preserve evidence."},
    ]
    evidence_map = [
        {"label": "Mandatory run ledger", "path": f"@{doc['run_root_abs']}\\{MANDATORY_RUN_OUTPUT_MD}"},
        {"label": "Machine-readable ledger", "path": f"@{doc['run_root_abs']}\\{MANDATORY_RUN_OUTPUT_JSON}"},
        {"label": "Final resume text", "path": f"@{doc['run_root_abs']}\\{FINAL_RESUME_OUTPUT_TXT}"},
        {"label": "Final resume output contract", "path": f"@{doc['run_root_abs']}\\{FINAL_RESUME_OUTPUT_JSON}"},
        {"label": "Resume DOCX", "path": f"@{doc['run_root_abs']}\\{FINAL_RESUME_DOCX_RELPATH}"},
    ]
    evidence_map.extend(_forensic_evidence_map_rows(doc))
    return {
        "schema_version": INLINE_REQUIRED_OUTPUT_SCHEMA_VERSION,
        "immutable_section_order": list(INLINE_REQUIRED_OUTPUT_SECTION_ORDER),
        "bcg": {
            "title": "BCG Executive Output - apps_rg Run",
            "section_order": list(BCG_LOCKED_SECTION_ORDER),
            "executive_answer": executive_answer,
            "p0_p1_px_recommendations": {
                "columns": list(BCG_RECOMMENDATION_COLUMNS),
                "rows": recommendations,
            },
            "board_level_readout": {
                "columns": list(BCG_BOARD_READOUT_COLUMNS),
                "rows": board_rows,
            },
            "issue_tree": _build_bcg_issue_tree(doc),
            "recommended_next_move": next_moves,
            "evidence_map": evidence_map,
        },
        "section_lane_summary_table": {
            "title": "Section Lane Summary Table",
            "columns": list(SECTION_LANE_TABLE_COLUMNS),
            "rows": doc.get("section_lane_table") if isinstance(doc.get("section_lane_table"), list) else [],
        },
        "resume_docx_full_version_inline": {
            "title": "Resume DOCX Full Version Inline",
            "source": _resume_inline_source(doc, resume_inline_authorized),
            "text": _resume_inline_text(doc),
        },
    }


def _render_locked_bcg_from_inline(inline: dict[str, Any], doc: dict[str, Any]) -> str:
    bcg = inline.get("bcg") if isinstance(inline.get("bcg"), dict) else {}
    recs = bcg.get("p0_p1_px_recommendations") if isinstance(bcg.get("p0_p1_px_recommendations"), dict) else {}
    board = bcg.get("board_level_readout") if isinstance(bcg.get("board_level_readout"), dict) else {}
    lines = [
        f"# {bcg.get('title') or 'BCG Executive Output - apps_rg Run'}",
        "",
        f"Generated: `{doc['generated_at_utc']}`",
        f"Run root: `@{doc['run_root_abs']}`",
        "",
        "## Executive Answer",
        "",
        str(bcg.get("executive_answer") or ""),
        "",
        "## P0/P1/PX Recommendations",
        "",
        "| Priority | Recommendation | Evidence | Gate / Outcome |",
        "|---|---|---|---|",
    ]
    for row in recs.get("rows") if isinstance(recs.get("rows"), list) else []:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"`{_markdown_table_escape(row.get('priority'))}` | "
            f"{_markdown_table_escape(row.get('recommendation'))} | "
            f"`{_markdown_table_escape(row.get('evidence'))}` | "
            f"{_markdown_table_escape(row.get('gate_outcome'))} |"
        )
    lines.extend(
        [
            "",
            "## Board-Level Readout",
            "",
            "| Question | Answer |",
            "|---|---|",
        ]
    )
    for row in board.get("rows") if isinstance(board.get("rows"), list) else []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {_markdown_table_escape(row.get('question'))} | `{_markdown_table_escape(row.get('answer'))}` |"
        )
    lines.extend(["", "## Issue Tree", ""])
    issue_tree = bcg.get("issue_tree") if isinstance(bcg.get("issue_tree"), list) else []
    if not issue_tree:
        lines.append("- No blocking issue tree was generated from section evidence.")
    for issue in issue_tree:
        if not isinstance(issue, dict):
            continue
        lines.append(
            f"- `{issue.get('section')}`: {issue.get('classification')}"
        )
        lines.append(f"  - Root cause: {issue.get('root_cause') or '-'}")
        evidence = issue.get("evidence") if isinstance(issue.get("evidence"), list) else []
        for item in evidence:
            if str(item).strip():
                lines.append(f"  - Evidence: `{_markdown_table_escape(item)}`")
        allocation = issue.get("causal_allocation") if isinstance(issue.get("causal_allocation"), dict) else {}
        if allocation:
            lines.append("  - Causal allocation:")
            lines.append(f"    - Dominant cause: {allocation.get('dominant_cause') or '-'}")
            if allocation.get("retry_recoverability") or allocation.get("retry_recoverability_reason"):
                lines.append(
                    "    - Retry recoverability: "
                    f"`{allocation.get('retry_recoverability') or '-'}` - "
                    f"{allocation.get('retry_recoverability_reason') or '-'}"
                )
            alloc_rows = allocation.get("allocation") if isinstance(allocation.get("allocation"), list) else []
            for row in alloc_rows:
                if not isinstance(row, dict):
                    continue
                evidence_refs = ", ".join(str(ref) for ref in row.get("evidence_refs") or [])
                lines.append(
                    "    - "
                    f"`{row.get('domain')}` / `{row.get('causal_role')}` / "
                    f"`{row.get('work_share')}`: {row.get('root_cause_link')} "
                    f"Evidence: `{_markdown_table_escape(evidence_refs)}`. "
                    f"Required work: {row.get('required_work')}"
                )
        plan = (
            issue.get("required_implementation_plan")
            if isinstance(issue.get("required_implementation_plan"), list)
            else issue.get("implementation_plan")
            if isinstance(issue.get("implementation_plan"), list)
            else []
        )
        if plan:
            lines.append("  - Required implementation plan:")
            for item in plan:
                lines.append(f"    - {item}")
    forensics = doc.get("section_failure_forensics")
    forensics = forensics if isinstance(forensics, dict) else {}
    forensic_artifacts = forensics.get("artifacts")
    forensic_artifacts = forensic_artifacts if isinstance(forensic_artifacts, list) else []
    if forensic_artifacts:
        lines.extend(
            [
                "",
                "## Prior Working Revision Comparison",
                "",
                "| Section | Prior PR / commit | Current commit | Inputs match | Provider request match | Output match | Gate delta | Complete |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        run_root = Path(str(doc.get("run_root_abs") or ""))
        for artifact in forensic_artifacts:
            if not isinstance(artifact, dict):
                continue
            section_id = str(artifact.get("section_id") or "unknown")
            comparison = _load_json(
                run_root / SECTION_FAILURE_FORENSICS_DIR / f"{section_id}.json"
            )
            revisions = comparison.get("revision_comparison")
            revisions = revisions if isinstance(revisions, dict) else {}
            baseline_revision = revisions.get("baseline")
            baseline_revision = baseline_revision if isinstance(baseline_revision, dict) else {}
            current_revision = revisions.get("current")
            current_revision = current_revision if isinstance(current_revision, dict) else {}
            differences = comparison.get("difference_summary")
            differences = differences if isinstance(differences, dict) else {}
            prior_identity = (
                f"PR #{baseline_revision.get('pr_number')} / {baseline_revision.get('git_commit')}"
                if baseline_revision.get("pr_number")
                else str(baseline_revision.get("git_commit") or baseline_revision.get("status") or "NOT_OBSERVED")
            )
            gate_delta = (
                f"{differences.get('baseline_x2')}/{differences.get('baseline_x3')} -> "
                f"{differences.get('current_x2')}/{differences.get('current_x3')}"
            )
            lines.append(
                "| "
                f"`{section_id}` | `{_markdown_table_escape(prior_identity)}` | "
                f"`{_markdown_table_escape(current_revision.get('git_commit') or 'NOT_OBSERVED')}` | "
                f"`{differences.get('inputs_match')}` | "
                f"`{differences.get('provider_request_match')}` | "
                f"`{differences.get('materialized_output_match')}` | "
                f"`{_markdown_table_escape(gate_delta)}` | "
                f"`{comparison.get('comparison_complete')}` |"
            )
        lines.extend(
            [
                "",
                "## Layperson Retry And Root-Cause Explanation",
                "",
            ]
        )
        for comparison in _output_bisect_sections(run_root, forensics):
            lines.append(f"### {comparison.get('section_id') or 'unknown'}")
            lines.append("")
            for sentence in comparison.get("layperson_explanation") or []:
                lines.append(str(sentence))
                lines.append("")
            first_observed = comparison.get("first_observed_divergence")
            first_observed = first_observed if isinstance(first_observed, dict) else {}
            first_causal = comparison.get("first_causally_relevant_divergence")
            first_causal = first_causal if isinstance(first_causal, dict) else {}
            lines.append(
                f"- First observed divergence: `{first_observed.get('stage') or 'NOT_ISOLATED'}`"
            )
            lines.append(
                f"- First causally relevant divergence: `{first_causal.get('stage') or 'NOT_ISOLATED'}`"
            )
            lines.append(
                f"- Code cause status: `{comparison.get('code_cause_status') or 'CODE_CAUSE_NOT_ISOLATED'}`"
            )
            lines.append("")
    lines.extend(["", "## Recommended Next Move", ""])
    for idx, item in enumerate(bcg.get("recommended_next_move") if isinstance(bcg.get("recommended_next_move"), list) else [], 1):
        lines.append(f"{idx}. {item}")
    lines.extend(["", "## Evidence Map", ""])
    for item in bcg.get("evidence_map") if isinstance(bcg.get("evidence_map"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(f"- {item.get('label')}: `{item.get('path')}`")
    return "\n".join(lines)

