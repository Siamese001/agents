"""Judge v3 Check-to-Dimension Verdicts Projector (`<= 180L`, zero `_TEXT_HINTS` regex synthesis)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.runtime.judges.v3_section_judge import (
    get_apps_rg_v3_profile,
    render_section_v3_rubric,
)

EXEC_SUMMARY_RUBRIC_DIMENSION_IDS: tuple[str, ...] = tuple(
    c.id for c in get_apps_rg_v3_profile("executive_summary").checks
)
EXEC_SUMMARY_STRICT_ZERO_DEFECT_DIMENSIONS: frozenset[str] = frozenset(
    c.id for c in get_apps_rg_v3_profile("executive_summary").checks if c.critical
)
VALID_SEVERITIES: frozenset[str] = frozenset({"none", "minor", "major"})
_HARD_VETO_SUBSTRINGS: tuple[str, ...] = (
    "MINOR_ALLOCATED_METRIC_OVERLAP",
    "REPEAT",
    "ECHO",
    "FABRICAT",
    "HALLUCINAT",
    "INANIMATE",
    "UNSUPPORTED",
)


def section_rubric_dimension_ids(section_id: str | None = None) -> tuple[str, ...]:
    """Resolve exact Judge v3 atomic check IDs for `section_id` fail-closed."""
    sid = "executive_summary" if section_id in (None, "") else str(section_id)
    return tuple(c.id for c in get_apps_rg_v3_profile(sid).checks)


def dimension_verdicts_json_schema_fragment(
    dimension_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    dims = tuple(dimension_ids) if dimension_ids is not None else EXEC_SUMMARY_RUBRIC_DIMENSION_IDS
    item_schema = {
        "type": "object",
        "properties": {
            "pass": {"type": "boolean"},
            "severity": {"type": "string", "enum": ["none", "minor", "major"]},
            "codes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["pass", "severity", "codes"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {d: item_schema for d in dims},
        "required": list(dims),
        "additionalProperties": False,
    }


def required_judge_output_dimension_block(section_id: str | None = None) -> str:
    dims = section_rubric_dimension_ids(section_id)
    inner = ", ".join(f'"{d}":{{"pass":true,"severity":"none","codes":[]}}' for d in dims)
    return f'"dimension_verdicts":{{{inner}}}'


def build_executive_summary_x1d_rubric_text(*, include_score_schema: str = "") -> str:
    base = render_section_v3_rubric("executive_summary")
    return f"{base}\n\n{include_score_schema}".strip() if include_score_schema else base


def section_dimension_veto_passes(dimension_verdicts: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    """Fail closed whenever any dimension fails, has major/critical severity, or carries overlap/fabrication codes."""
    if not isinstance(dimension_verdicts, Mapping) or not dimension_verdicts:
        return True, []
    reasons: list[str] = []
    for dim_key, entry in dimension_verdicts.items():
        if not isinstance(entry, Mapping):
            continue
        passed = bool(entry.get("pass", True))
        sev = str(entry.get("severity") or "none").strip().lower()
        codes = [str(c) for c in (entry.get("codes") or ()) if str(c).strip()]
        if not passed:
            reasons.append(f"dimension_failed:{dim_key}")
        if sev in {"major", "critical"}:
            reasons.append(f"dimension_major_severity:{dim_key}")
        for code in codes:
            up = code.upper()
            if any(tok in up for tok in _HARD_VETO_SUBSTRINGS):
                reasons.append(f"section_judge_veto_code:{dim_key}:{code}")
    return len(reasons) == 0, reasons


def executive_summary_human_dimension_floor_passes(
    dimension_verdicts: Mapping[str, Any] | None,
) -> tuple[bool, list[str]]:
    return section_dimension_veto_passes(dimension_verdicts)


def infer_dimension_verdicts_from_judge_blob(
    result: Mapping[str, Any],
    *,
    section_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Project explicit Judge v3 checks without post-hoc prose regex guessing."""
    raw_dv = result.get("dimension_verdicts")
    if isinstance(raw_dv, Mapping) and raw_dv:
        return {str(k): dict(v) for k, v in raw_dv.items() if isinstance(v, Mapping)}
    dims = section_rubric_dimension_ids(section_id)
    overall_pass = bool(result.get("pass", True))
    return {
        d: {
            "pass": overall_pass,
            "severity": "none" if overall_pass else "major",
            "codes": [] if overall_pass else ["JUDGE_V3_FAILED"],
        }
        for d in dims
    }


def ensure_dimension_verdicts(
    result: Mapping[str, Any],
    *,
    deterministic_gate_summary: Mapping[str, Any] | None = None,
    section_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Preserve explicit dimension_verdicts intact (`inferred=False`) with zero post-hoc regex synthesis."""
    _ = deterministic_gate_summary
    out = dict(result)
    raw_dv = out.get("dimension_verdicts")
    if isinstance(raw_dv, Mapping) and raw_dv:
        out["dimension_verdicts"] = {str(k): dict(v) for k, v in raw_dv.items() if isinstance(v, Mapping)}
        out["dimension_verdicts_inferred"] = False
        return out, False
    out["dimension_verdicts"] = infer_dimension_verdicts_from_judge_blob(out, section_id=section_id)
    out["dimension_verdicts_inferred"] = True
    return out, True


def build_x1d_dimension_matrix(
    judge_outputs: Sequence[Any],
    *,
    section_id: str | None = None,
) -> dict[str, Any]:
    dims = section_rubric_dimension_ids(section_id)
    rows: list[dict[str, Any]] = []
    for item in judge_outputs:
        d = item.to_dict() if hasattr(item, "to_dict") else (dict(item) if isinstance(item, Mapping) else {})
        rows.append(
            {
                "judge_id": d.get("judge_id", ""),
                "model_name": d.get("model_name", ""),
                "pass": bool(d.get("pass", False)),
                "dimension_verdicts": d.get("dimension_verdicts") or {},
            }
        )
    by_dim: dict[str, dict[str, Any]] = {}
    for dim in dims:
        fails = sum(1 for r in rows if not bool(((r.get("dimension_verdicts") or {}).get(dim) or {}).get("pass", True)))
        by_dim[dim] = {"fail_count": fails, "consensus_fail": fails >= 2}
    return {
        "schema": "executive_summary_x1d_dimension_matrix_v3",
        "section_id": section_id or "executive_summary",
        "dimensions": list(dims),
        "by_dimension": by_dim,
        "judges": rows,
    }


def write_x1d_dimension_matrix_artifact(
    artifact_base: Path,
    judge_outputs: Sequence[Any],
    *,
    section_id: str | None = None,
) -> Path:
    base = Path(artifact_base)
    target = base if base.suffix == ".json" else (base / "x1d_dimension_matrix.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    matrix = build_x1d_dimension_matrix(judge_outputs, section_id=section_id)
    target.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
