"""Judge output parsers and normalization for mandatory run outputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *

__all__ = ['_judge_rows_from_blob', '_normalize_judge_record', '_judge_failure_records', '_failed_dimension_codes', '_judge_failure_text_from_judges', '_judge_failure_evidence', '_resolve_display', '_load_provider_call_records', '_cache_preflight', '_judge_model_score_cell', '_judge_retry_fallback_cell', '_provider_cell', '_pooling_selector_cell', '_secondary_provider_cell', '_section_lane_abs_dir', '_lane_provider_proof', '_lane_provider_attempted', '_lane_primary_provider', '_lane_primary_model', '_lane_generation_status', '_generation_ordered_section_ids']

def _judge_rows_from_blob(blob: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for judge in _as_list(blob.get("judges")):
        if not isinstance(judge, dict):
            continue
        provider = str(judge.get("provider_name") or judge.get("provider_key") or "judge")
        rows.append(
            {
                "provider": provider,
                "provider_key": judge.get("provider_key"),
                "model": judge.get("model_name") or judge.get("model_actual"),
                "score": judge.get("score"),
                "threshold": judge.get("threshold"),
                "pass": judge.get("pass"),
                "provider_status": judge.get("provider_status") or judge.get("mode"),
                "decisive_failure": judge.get("decisive_failure"),
                "soft_fail": judge.get("soft_fail"),
                "blocked": judge.get("blocked"),
                "mocked": judge.get("mocked"),
                "error": judge.get("error"),
                "findings": _as_list(judge.get("findings")),
                "remediation_suggestions": _as_list(judge.get("remediation_suggestions")),
                "dimension_verdicts": (
                    judge.get("dimension_verdicts")
                    if isinstance(judge.get("dimension_verdicts"), dict)
                    else {}
                ),
            }
        )
    return rows


def _normalize_judge_record(judge: dict[str, Any]) -> dict[str, Any]:
    provider = str(
        judge.get("provider")
        or judge.get("provider_name")
        or judge.get("provider_key")
        or "judge"
    )
    return {
        "provider": provider,
        "provider_key": judge.get("provider_key"),
        "model": judge.get("model") or judge.get("model_name") or judge.get("model_actual"),
        "score": judge.get("score"),
        "threshold": judge.get("threshold"),
        "pass": judge.get("pass"),
        "provider_status": judge.get("provider_status") or judge.get("mode"),
        "decisive_failure": judge.get("decisive_failure"),
        "soft_fail": judge.get("soft_fail"),
        "blocked": judge.get("blocked"),
        "mocked": judge.get("mocked"),
        "error": judge.get("error"),
        "findings": _as_list(judge.get("findings")),
        "remediation_suggestions": _as_list(judge.get("remediation_suggestions")),
        "dimension_verdicts": (
            judge.get("dimension_verdicts")
            if isinstance(judge.get("dimension_verdicts"), dict)
            else {}
        ),
    }


def _judge_failure_records(judges: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for judge in _as_list(judges):
        if not isinstance(judge, dict):
            continue
        status = str(judge.get("provider_status") or "").upper()
        if (
            judge.get("decisive_failure") is True
            or judge.get("pass") is False
            or status.endswith("_FAIL")
        ):
            rows.append(judge)
    return rows


def _failed_dimension_codes(judge: dict[str, Any]) -> list[str]:
    dims = judge.get("dimension_verdicts")
    if not isinstance(dims, dict):
        return []
    out: list[str] = []
    for name, verdict in dims.items():
        if not isinstance(verdict, dict) or verdict.get("pass") is not False:
            continue
        codes = ",".join(str(code) for code in _as_list(verdict.get("codes")) if str(code))
        severity = str(verdict.get("severity") or "").strip()
        detail = codes or severity or "failed"
        out.append(f"{name}:{detail}")
    return out


def _judge_failure_text_from_judges(judges: Any) -> str:
    pieces: list[str] = []
    for judge in _judge_failure_records(judges):
        provider = str(judge.get("provider") or judge.get("provider_key") or "judge")
        model = str(judge.get("model") or "").strip()
        status = str(judge.get("provider_status") or "").strip()
        score = _score_text(judge.get("score"))
        threshold = _score_text(judge.get("threshold"))
        findings = [str(x) for x in _as_list(judge.get("findings")) if str(x).strip()]
        dims = _failed_dimension_codes(judge)
        bits = [provider]
        if model:
            bits.append(model)
        if status:
            bits.append(status)
        if score != "-" or threshold != "-":
            bits.append(f"score={score}/{threshold}")
        if dims:
            bits.append("dimensions=" + ",".join(dims[:3]))
        if findings:
            bits.append("findings=" + " ; ".join(findings[:2]))
        pieces.append(" | ".join(bits))
    return " || ".join(pieces)


def _judge_failure_evidence(section: dict[str, Any]) -> str:
    judge_text = _judge_failure_text_from_judges(section.get("judges"))
    if judge_text:
        return judge_text
    summary = section.get("judge_issue_summary")
    if isinstance(summary, dict):
        decisive = [str(x) for x in _as_list(summary.get("decisive_judge_failures")) if str(x)]
        if decisive:
            return "decisive_judge_failures=" + ",".join(decisive)
    return ""


def _resolve_display(root: Path, section_id: str) -> tuple[str | None, str | None]:
    for name in LANE_DISPLAY_TXT_CANDIDATES.get(section_id, ("command_output.txt",)):
        candidate = root / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            return name, str(candidate.resolve())
    return None, None


def _load_provider_call_records(run_root: Path) -> dict[str, dict[str, Any]]:
    candidates = (
        run_root / "modular_r4" / "section_provider_calls.json",
        run_root / "section_provider_calls.json",
    )
    for path in candidates:
        doc = _load_json(path)
        records = doc.get("records")
        if not isinstance(records, list):
            continue
        out: dict[str, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            lane = str(record.get("section_lane") or record.get("lane") or "").strip()
            if lane:
                out[lane] = record
        if out:
            return out
    return {}


def _cache_preflight(run_root: Path) -> dict[str, str]:
    doc = _load_json(run_root / "whole_run_cache_preflight.json")
    return {
        "r1a": str(doc.get("r1a_preflight_status") or "NOT_OBSERVED"),
        "r1b": str(doc.get("r1b_preflight_status") or "NOT_OBSERVED"),
    }


def _judge_model_score_cell(section: dict[str, Any]) -> str:
    judges = section.get("judges") if isinstance(section.get("judges"), list) else []
    cells: list[str] = []
    for judge in judges:
        if not isinstance(judge, dict):
            continue
        provider = str(judge.get("provider") or judge.get("provider_key") or "judge")
        model = str(judge.get("model") or "NOT_OBSERVED")
        score = _score_text(judge.get("score"))
        threshold = _score_text(judge.get("threshold"))
        passed = "PASS" if judge.get("pass") is True else "FAIL" if judge.get("pass") is False else "UNKNOWN"
        cells.append(f"{provider} / {model}: {score} vs {threshold} {passed}")
    return "; ".join(cells) if cells else "NOT_OBSERVED"


def _judge_retry_fallback_cell(section: dict[str, Any]) -> str:
    issues = section.get("judge_issue_summary") if isinstance(section.get("judge_issue_summary"), dict) else {}
    cells: list[str] = []
    for key in ("blocked_judges", "mocked_judges", "soft_failed_judges", "decisive_judge_failures"):
        values = issues.get(key)
        if isinstance(values, list) and values:
            cells.append(f"{key}={','.join(str(v) for v in values)}")
    return "; ".join(cells) if cells else "NOT_OBSERVED"


def _provider_cell(record: dict[str, Any], key: str, *, default: str = "NOT_OBSERVED") -> str:
    value = str(record.get(key) or "").strip()
    return value or default


def _pooling_selector_cell(section_id: str) -> str:
    if section_id == "competencies" or section_id.endswith("_bullets"):
        return "NOT_OBSERVED"
    return "N/A"


def _secondary_provider_cell(record: dict[str, Any]) -> str:
    provider = _provider_cell(record, "secondary_provider", default="")
    return provider or "NOT_OBSERVED"


def _section_lane_abs_dir(section: dict[str, Any], *, repo_root: Path) -> Path | None:
    lane_dir = str(section.get("lane_dir") or "").strip()
    if lane_dir:
        path = Path(lane_dir)
        return path if path.is_absolute() else repo_root / path
    display = str(section.get("display_txt_path") or "").strip()
    if display:
        return Path(display).parent
    return None


def _lane_provider_proof(section: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    lane_dir = _section_lane_abs_dir(section, repo_root=repo_root)
    if lane_dir is None:
        return {}
    provider_request = _load_json(lane_dir / "provider_request.json")
    provider_response = _load_json(lane_dir / "provider_response.json")
    run_manifest = _load_json(lane_dir / "run_manifest.json")
    l2_output = _load_json(lane_dir / "l2_output.json")
    return {
        "provider_request": provider_request,
        "provider_response": provider_response,
        "run_manifest": run_manifest,
        "l2_output": l2_output,
        "has_lane_proof": any((provider_request, provider_response, run_manifest, l2_output)),
    }


def _lane_provider_attempted(record: dict[str, Any], proof: dict[str, Any]) -> Any:
    request = proof.get("provider_request") if isinstance(proof.get("provider_request"), dict) else {}
    if "provider_attempted" in request:
        return request.get("provider_attempted")
    if request.get("provider_requested") or request.get("model"):
        return True
    if "provider_call_attempted" in record:
        return record.get("provider_call_attempted")
    return "NOT_OBSERVED"


def _lane_primary_provider(record: dict[str, Any], proof: dict[str, Any]) -> str:
    request = proof.get("provider_request") if isinstance(proof.get("provider_request"), dict) else {}
    response = proof.get("provider_response") if isinstance(proof.get("provider_response"), dict) else {}
    l2_output = proof.get("l2_output") if isinstance(proof.get("l2_output"), dict) else {}
    return _first_nonempty(
        request.get("provider_requested"),
        response.get("provider_requested"),
        response.get("provider"),
        l2_output.get("provider_requested"),
        record.get("provider_profile"),
    ) or "NOT_OBSERVED"


def _lane_primary_model(record: dict[str, Any], proof: dict[str, Any]) -> str:
    request = proof.get("provider_request") if isinstance(proof.get("provider_request"), dict) else {}
    response = proof.get("provider_response") if isinstance(proof.get("provider_response"), dict) else {}
    l2_output = proof.get("l2_output") if isinstance(proof.get("l2_output"), dict) else {}
    return _first_nonempty(
        record.get("model_id"),
        response.get("model_id"),
        response.get("model"),
        response.get("model_name"),
        request.get("model"),
        request.get("model_id"),
        l2_output.get("model_id"),
        l2_output.get("model"),
        l2_output.get("model_name"),
    ) or "NOT_OBSERVED"


def _lane_generation_status(
    record: dict[str, Any],
    section: dict[str, Any],
    proof: dict[str, Any],
) -> str:
    manifest = proof.get("run_manifest") if isinstance(proof.get("run_manifest"), dict) else {}
    l2_output = proof.get("l2_output") if isinstance(proof.get("l2_output"), dict) else {}
    return _first_nonempty(
        section.get("runtime_generation_status"),
        manifest.get("runtime_generation_status"),
        l2_output.get("runtime_generation_status"),
        record.get("generation_status"),
    ) or "NOT_OBSERVED"


def _generation_ordered_section_ids(
    sections: list[dict[str, Any]],
    provider_records: dict[str, dict[str, Any]],
) -> list[str]:
    def candidate_index(lane: str) -> int:
        raw = provider_records[lane].get("candidate_index")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 999

    ordered = sorted(
        provider_records,
        key=candidate_index,
    )
    for section in sections:
        lane = str(section.get("section") or "")
        if lane and lane not in ordered:
            ordered.append(lane)
    return ordered

