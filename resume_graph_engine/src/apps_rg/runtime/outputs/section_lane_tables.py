"""Section lane tables and section records collection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .research_context import *

__all__ = ['_row_from_single_section', '_status_bucket', '_classify_failure', '_section_record_from_row', '_collect_section_records', '_count_sections', '_section_by_id', '_build_section_lane_table', '_non_authorized_section_ids']

def _row_from_single_section(
    run_root: Path,
    *,
    section_id: str,
    repo_root: Path,
) -> LaneSectionStatusRow:
    x3 = _load_json(run_root / "x3_disposition.json")
    x2_pass, failed = _x2_summary_doc(_load_json(run_root / "x2_gate_outputs.json"))
    manifest = _load_json(run_root / "run_manifest.json")
    l2 = _load_json(run_root / "l2_output.json")
    display_name, display_abs = _resolve_display(run_root, section_id)
    judges = _judge_rows_from_blob(_load_json(run_root / "x1d_llm_judge_outputs.json"))
    judge_summary = "; ".join(
        (
            f"{j['provider']}"
            f"{' `' + str(j['model']) + '`' if j.get('model') else ''}: "
            f"{_score_text(j.get('score'))}/5 vs {_score_text(j.get('threshold'))} "
            f"{'PASS' if j.get('pass') is True else 'FAIL' if j.get('pass') is False else 'UNKNOWN'}"
        )
        for j in judges
    )
    return LaneSectionStatusRow(
        lane=section_id,
        lane_dir=_repo_rel(run_root, repo_root),
        display_txt_rel=display_name,
        display_txt_abs=display_abs,
        x3_code=str(x3.get("x3_code") or x3.get("disposition") or "UNKNOWN"),
        product_quality=str(x3.get("product_quality_status") or "UNKNOWN"),
        x2_pass=x2_pass,
        x2_failed_gate_ids=", ".join(str(g.get("gate_id")) for g in failed),
        runtime_generation_status=str(
            manifest.get("runtime_generation_status")
            or l2.get("runtime_generation_status")
            or x3.get("runtime_generation_status")
            or "UNKNOWN"
        ),
        executed=True,
        judge_summary=judge_summary,
        judge_details=tuple(judges),
    )


def _status_bucket(row: LaneSectionStatusRow, pre_run: dict[str, Any]) -> str:
    x3 = str(row.x3_code or "")
    runtime = str(row.runtime_generation_status or "")
    if not row.executed or x3 == "NOT_RUN":
        return "not_run"
    if runtime == "REAL_LLM":
        return "ran_real_llm"
    if runtime == "ASSEMBLED":
        return "assembled"
    if x3.startswith("PRE_RUN:") or pre_run:
        return "pre_run_blocked"
    return "ran_unknown_runtime"


def _classify_failure(
    section_id: str,
    failed_gates: list[dict[str, Any]],
    pre_run: dict[str, Any],
    *,
    x3_code: str = "",
    judges: Any = None,
) -> str:
    blocker = str(pre_run.get("blocker") or pre_run.get("lane_exec_status") or "").strip()
    lane_status = str(pre_run.get("lane_exec_status") or "").strip()
    pre_run_text = f"{blocker} {lane_status}".lower()
    if "temperature" in pre_run_text and "deprecated" in pre_run_text:
        return "Provider capability failure: Anthropic rejected deprecated temperature for the selected model."
    if "poolselectorunavailableerror" in pre_run_text and "selector_timeout" in pre_run_text:
        return (
            "Provider selector timeout: the competencies pool selector exceeded its bounded "
            "provider budget before returning a selection."
        )
    if pre_run and not failed_gates and blocker != "EXECUTED_X3_BLOCK":
        detail = blocker
        if lane_status and lane_status != blocker:
            detail = f"{blocker}; {lane_status}"
        return f"Pre-run dependency blocked execution: {detail}"
    judge_text = _judge_failure_text_from_judges(judges)
    if not failed_gates and str(x3_code or "").startswith("X3_BLOCK") and judge_text:
        judge_text_l = judge_text.lower()
        if (
            "factual_support" in judge_text_l
            or "unsupported_claim" in judge_text_l
            or "missing_citation" in judge_text_l
            or "source_fact" in judge_text_l
            or "claim ledger" in judge_text_l
        ):
            return (
                "X1D decisive judge failure: model-backed judge rejected factual support "
                "or claim-ledger source binding."
            )
        return "X1D decisive judge failure: model-backed judge rejected section product quality."
    gate_ids = " ".join(str(g.get("gate_id") or "") for g in failed_gates).lower()
    reasons = " ".join(str(g.get("failure_reason") or "") for g in failed_gates).lower()
    observed = " ".join(
        json.dumps(g.get("observed_value"), sort_keys=True, default=str)
        for g in failed_gates
        if isinstance(g, dict) and g.get("observed_value") not in (None, "", [], {})
    ).lower()
    combined = f"{gate_ids} {reasons} {observed}"
    if "competenc" in section_id:
        return "Evidence mapping failure: visible content was not fully backed by source facts or graph lineage."
    if section_id == "executive_summary" and (
        "x2_exec_summary" in combined or "x2_executive_summary_synthesis_quality" in combined
    ):
        return (
            "Executive summary synthesis contract failure: deterministic producer repair did "
            "not satisfy brushstroke coverage, attribution density, and transition-quality gates."
        )
    if section_id == "headline" and (
        "x2_headline_executive_abstraction_floor" in combined
        or "x2_headline_vendor_terms_proof_only" in combined
    ):
        return (
            "Headline executive positioning contract failure: vendor/tool proof terms reached "
            "display without an executive abstraction segment."
        )
    if "claim_ledger" in combined or "bullet_count" in combined or "parse" in combined:
        return "Output contract failure: parsed content or claim ledger did not satisfy section schema."
    if "technical_specificity" in combined:
        return "Deterministic specificity failure: generated text missed required mechanism/technology signal."
    if "source_fact" in combined or "graph" in combined:
        return "Evidence mapping failure: visible content was not fully backed by source facts or graph lineage."
    if section_id == FINAL_AGGREGATION_LANE:
        if "judge_quorum_insufficient" in combined or "quorum_not_met" in combined:
            return (
                "Final resume aggregation provider quorum failure: the full-resume "
                "coherence judge panel did not reach the required model-backed quorum."
            )
        if "resolution not accepted" in combined or "judge_certification_required" in combined:
            return (
                "Final resume aggregation upstream certification failure: a required section "
                "was review-only or non-certified, so latest-successful-real resolution was refused."
            )
        return "Final resume aggregation failure: full-resume coherence or product release gate did not pass."
    if failed_gates:
        return "Deterministic gate failure."
    return "No section-level failure recorded."


def _section_record_from_row(row: LaneSectionStatusRow, *, repo_root: Path) -> dict[str, Any]:
    lane_dir = Path(row.lane_dir) if row.lane_dir else None
    if lane_dir and not lane_dir.is_absolute():
        lane_dir = repo_root / lane_dir
    if lane_dir is None and row.display_txt_abs:
        lane_dir = Path(row.display_txt_abs).parent
    x3 = _load_json(lane_dir / "x3_disposition.json") if lane_dir is not None else {}
    x2_artifact_name = (
        "final_resume_x2_gate_outputs.json"
        if row.lane == FINAL_AGGREGATION_LANE
        else "x2_gate_outputs.json"
    )
    x2_status, failed_gates = (
        _x2_summary_doc(_load_json(lane_dir / x2_artifact_name))
        if lane_dir is not None
        else (row.x2_pass, [])
    )
    if not failed_gates and str(row.x2_failed_gate_ids or "").strip():
        failed_gates = [
            {
                "gate_id": gate_id.strip(),
                "failure_reason": "",
                "observed_value": None,
                "threshold": None,
            }
            for gate_id in str(row.x2_failed_gate_ids).split(",")
            if gate_id.strip()
        ]
    if x2_status == "UNKNOWN" and row.x2_pass in {"PASS", "FAIL"}:
        x2_status = row.x2_pass
    pre_run = (
        _load_json(lane_dir / "integrated_lane_pre_run_failure.json")
        if lane_dir is not None
        else {}
    )
    judges = (
        [_normalize_judge_record(j) for j in row.judge_details]
        if row.judge_details
        else _judge_rows_from_blob(
            _load_json(lane_dir / "x1d_llm_judge_outputs.json") if lane_dir is not None else {}
        )
    )
    l6_files: list[str] = []
    if lane_dir is not None and lane_dir.is_dir():
        l6_files = sorted(
            _repo_rel(p, repo_root)
            for p in lane_dir.glob("l6*")
            if p.is_file()
        )
        post_runtime = lane_dir / "post_runtime"
        if post_runtime.is_dir():
            l6_files.extend(
                sorted(_repo_rel(p, repo_root) for p in post_runtime.glob("l6*") if p.is_file())
            )
    status = _status_bucket(row, pre_run)
    return {
        "section": row.lane,
        "status_bucket": status,
        "executed": row.executed,
        "lane_dir": row.lane_dir,
        "display_txt_relpath": row.display_txt_rel,
        "display_txt_path": row.display_txt_abs,
        "x3_code": row.x3_code,
        "x2_pass": x2_status or row.x2_pass,
        "product_quality_status": row.product_quality,
        "runtime_generation_status": row.runtime_generation_status,
        "failed_gates": failed_gates,
        "failure_classification": _classify_failure(
            row.lane,
            failed_gates,
            pre_run,
            x3_code=row.x3_code,
            judges=judges,
        ),
        "pre_run_failure": pre_run,
        "judges": judges,
        "judge_summary": row.judge_summary,
        "judge_issue_summary": {
            "blocked_judges": _as_list(x3.get("blocked_judges")),
            "mocked_judges": _as_list(x3.get("mocked_judges")),
            "soft_failed_judges": _as_list(x3.get("soft_failed_judges")),
            "decisive_judge_failures": _as_list(x3.get("decisive_judge_failures")),
            "model_backed_pass_provider_keys": _as_list(x3.get("model_backed_pass_provider_keys")),
        },
        "l6": {
            "file_count": len(l6_files),
            "files": l6_files,
            "product_authority": "future_run_advisory_only" if l6_files else "not_observed",
        },
    }


def _collect_section_records(
    run_root: Path,
    *,
    repo_root: Path,
    section_id: str | None,
) -> list[dict[str, Any]]:
    if (run_root / "lanes").is_dir() or (run_root / "modular_r4" / "sections").is_dir():
        rows = collect_full_run_section_status(run_root, repo_root=repo_root)
    elif (run_root / "x3_disposition.json").is_file() or section_id:
        rows = [
            _row_from_single_section(
                run_root,
                section_id=section_id or run_root.name,
                repo_root=repo_root,
            )
        ]
    else:
        rows = []
    return [_section_record_from_row(row, repo_root=repo_root) for row in rows]


def _count_sections(sections: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "total": len(sections),
        "ran_real_llm": 0,
        "allowed": 0,
        "blocked": 0,
        "pre_run_blocked": 0,
        "not_run": 0,
        "unknown": 0,
    }
    for section in sections:
        bucket = str(section.get("status_bucket") or "")
        x3 = str(section.get("x3_code") or "")
        if bucket == "ran_real_llm":
            counts["ran_real_llm"] += 1
        if x3 == "X3_ALLOW":
            counts["allowed"] += 1
        elif x3.startswith("X3_BLOCK"):
            counts["blocked"] += 1
        elif bucket == "pre_run_blocked":
            counts["pre_run_blocked"] += 1
        elif bucket == "not_run":
            counts["not_run"] += 1
        else:
            counts["unknown"] += 1
    return counts


def _section_by_id(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(section.get("section") or ""): section for section in sections}


def _build_section_lane_table(
    run_root: Path,
    sections: list[dict[str, Any]],
    *,
    repo_root: Path,
) -> list[dict[str, Any]]:
    provider_records = _load_provider_call_records(run_root)
    cache = _cache_preflight(run_root)
    by_id = _section_by_id(sections)
    rows: list[dict[str, Any]] = [_research_briefing_row(run_root, repo_root=repo_root, cache=cache)]
    for idx, section_id in enumerate(_generation_ordered_section_ids(sections, provider_records), 1):
        section = by_id.get(section_id, {})
        record = provider_records.get(section_id, {})
        provider_proof = _lane_provider_proof(section, repo_root=repo_root)
        l6 = section.get("l6") if isinstance(section.get("l6"), dict) else {}
        rows.append(
            {
                "order": idx,
                "section": section_id,
                "research_source_class": "N/A",
                "r1a": cache["r1a"],
                "r1b": cache["r1b"],
                "lane_record": "YES" if record or section or provider_proof.get("has_lane_proof") else "NO",
                "provider_call_attempted": _lane_provider_attempted(record, provider_proof),
                "primary_provider": _lane_primary_provider(record, provider_proof),
                "primary_model_observed": _lane_primary_model(record, provider_proof),
                "pooling_selector_llm": _pooling_selector_cell(section_id),
                "secondary_provider": _secondary_provider_cell(record),
                "secondary_model_observed": _provider_cell(record, "secondary_model_id"),
                "generation_status": _lane_generation_status(record, section, provider_proof),
                "judges_run": "YES" if section.get("judges") else "NO",
                "judge_models_scores": _judge_model_score_cell(section),
                "judge_retry_fallback": _judge_retry_fallback_cell(section),
                "x2": str(section.get("x2_pass") or "NOT_OBSERVED"),
                "x3": str(section.get("x3_code") or record.get("decisive_reason_code") or "NOT_OBSERVED"),
                "past_fail_blocker": str(
                    section.get("failure_classification")
                    or record.get("decisive_reason_code")
                    or "NOT_OBSERVED"
                ),
                "display_output": str(section.get("display_txt_relpath") or "MISSING"),
                "l6_evidence": str(l6.get("product_authority") or "NOT_OBSERVED"),
            }
        )
    return rows


def _non_authorized_section_ids(doc: dict[str, Any]) -> dict[str, list[str]]:
    blocked: dict[str, list[str]] = {
        "x3_blocked": [],
        "pre_run_blocked": [],
        "not_run": [],
        "unknown": [],
    }
    for section in doc.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section") or "").strip()
        if not section_id:
            continue
        x3_code = str(section.get("x3_code") or "")
        bucket = str(section.get("status_bucket") or "")
        if x3_code.startswith("X3_BLOCK"):
            blocked["x3_blocked"].append(section_id)
        elif section_id == FINAL_AGGREGATION_LANE and x3_code.startswith("X3_REVIEW_AGGREGATION"):
            blocked["x3_blocked"].append(section_id)
        elif bucket == "pre_run_blocked" or x3_code.startswith("PRE_RUN:"):
            blocked["pre_run_blocked"].append(section_id)
        elif bucket == "not_run" or x3_code == "NOT_RUN":
            blocked["not_run"].append(section_id)
        elif x3_code not in {"X3_ALLOW", "X3_REVIEW_JUDGE_SOFT_FAIL"}:
            blocked["unknown"].append(section_id)
    return blocked

