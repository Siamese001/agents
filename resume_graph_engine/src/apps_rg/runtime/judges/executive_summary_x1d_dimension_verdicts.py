"""SSOT for executive_summary X1D rubric dimension verdicts and operator matrix."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any, Callable

from apps_rg.runtime.validators.executive_summary_x2 import (
    EXEC_SUMMARY_MAX_CHARS,
    EXEC_SUMMARY_MAX_SENTENCES,
    EXEC_SUMMARY_MAX_WORDS,
    EXEC_SUMMARY_MIN_CHARS,
    EXEC_SUMMARY_MIN_SENTENCES,
)

EXEC_SUMMARY_RUBRIC_DIMENSION_IDS: tuple[str, ...] = (
    "immediate_call_conviction",
    "spoken_executive_authenticity",
    "differentiated_edge",
    "six_second_scannability",
    "strategic_mandate_resonance",
    "factual_truth_and_non_exaggeration",
)

EXEC_SUMMARY_STRICT_ZERO_DEFECT_DIMENSIONS: frozenset[str] = frozenset(
    {
        "immediate_call_conviction",
        "spoken_executive_authenticity",
    }
)

VALID_SEVERITIES: frozenset[str] = frozenset({"none", "minor", "major"})

# Stable codes for matrix/regen (subset; models may emit these in verdict.codes).
DIMENSION_VERDICT_CODES: frozenset[str] = frozenset(
    {
        "not_immediate_call", "generic_peer_interchangeable", "weak_executive_hook",
        "ai_bridge_crutch", "abstract_noun_soup", "stiff_essay_cadence", "machine_generated_voice",
        "bullet_stack_prose", "weak_differentiation", "flat_sentence_rhythm", "overlong_sentence",
        "weak_domain_targeting", "target_mandate_divergence", "off_domain_clutter", "jd_as_proof_risk",
        "unsupported_claim", "metric_exaggeration", "cross_fact_conflation", "recruiter_filler",
        "generic_ai_prose", "head_of_talent_acquisition_screen", "ai_authenticity_failure",
        "buzzword_soup", "em_dash_usage", "template_phrasing", "thin_closing_sentence",
        "metric_inventory", "repeated_metric_surface", "residual_executive_clarity",
        "residual_narrative_coherence", "residual_commercial_fit",
    }
)

_FLAG_TO_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "bullet_stack_prose": ("six_second_scannability", "spoken_executive_authenticity"),
    "weak_domain_targeting": ("strategic_mandate_resonance",),
    "target_mandate_divergence": ("strategic_mandate_resonance", "immediate_call_conviction"),
    "thin_closing_sentence": ("immediate_call_conviction", "strategic_mandate_resonance"),
    "s1_s2_redundancy": ("six_second_scannability",),
    "metric_inventory": ("six_second_scannability", "spoken_executive_authenticity"),
    "ai_bridge_crutch": ("spoken_executive_authenticity",),
    "abstract_noun_soup": ("spoken_executive_authenticity", "six_second_scannability"),
}

_TEXT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "factual_truth_and_non_exaggeration",
        ("unsupported", "exaggerat", "inflat", "fabricat", "ledger", "source_fact", "proof boundary", "jd-as-proof", "target company as experience"),
    ),
    (
        "immediate_call_conviction",
        ("immediate", "interview", "call", "ordinary", "interchangeable", "peer", "compelling", "conviction", "generic hook", "bland"),
    ),
    (
        "spoken_executive_authenticity",
        (
            "robotic",
            "ai-sounding",
            "ai sounding",
            "bridge crutch",
            "in parallel",
            "building on that",
            "abstract noun",
            "noun soup",
            "recruiter",
            "filler",
            "generic ai prose",
            "machine-generated",
            "machine generated",
            "template phrasing",
            "buzzword soup",
            "stiff",
            "em dash",
        ),
    ),
    (
        "differentiated_edge",
        ("differenti", "generic", "could belong to", "commodity", "unique", "rare", "standout", "distinctive"),
    ),
    (
        "six_second_scannability",
        ("scan", "dense", "cluttered", "sentence length", "rhythm", "cadence", "bullet stack", "comma-stack", "metric inventory", "repeated metric", "wall of text"),
    ),
    (
        "strategic_mandate_resonance",
        (
            "mandate",
            "role fit",
            "strategic",
            "targeting",
            "divergence",
            "off-domain",
            "company dna",
            "clutter",
            "irrelevant",
            "jd",
        ),
    ),
)


def dimension_verdicts_json_schema_fragment(
    dimension_ids: Sequence[str] = EXEC_SUMMARY_RUBRIC_DIMENSION_IDS,
) -> dict[str, Any]:
    """Strict provider schema fragment for a section's dimension verdicts."""
    verdict_props = {
        "pass": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["none", "minor", "major"]},
        "codes": {"type": "array", "items": {"type": "string"}},
    }
    dimensions = tuple(str(dim) for dim in dimension_ids)
    dim_props = {
        dim: {
            "type": "object",
            "properties": verdict_props,
            "required": list(verdict_props),
            "additionalProperties": False,
        }
        for dim in dimensions
    }
    return {
        "type": "object",
        "properties": dim_props,
        "required": list(dimensions),
        "additionalProperties": False,
    }


_EXEC_SUMMARY_RUBRIC_DIMENSION_PROSE: dict[str, str] = {
    "immediate_call_conviction": (
        "Does this sound like a rare, high-caliber executive we MUST speak to immediately? "
        "Fail if the paragraph feels safe, solid-but-ordinary, or interchangeable with 50 other senior applicants."
    ),
    "spoken_executive_authenticity": (
        "Does this read like a confident, articulate human executive speaking plainly to a hiring committee, "
        "rather than LLM prose? Fail on AI transition crutches ('In parallel,', 'Building on that', 'That governed...'), "
        "abstract noun soup ('operating-model framing', 'governed activation', 'durable economics'), recruiter cliches, or stiff essay cadence."
    ),
    "differentiated_edge": (
        "Does the summary foreground a sharp, unmistakable combination of proof (scale, commercial/platform outcomes, "
        "regulated rigor) that clearly separates this candidate from generic peers?"
    ),
    "six_second_scannability": (
        "Can a busy executive absorb the core value proposition in a six-second skim? Reward crisp visual rhythm, "
        "varied sentence lengths, concrete outcomes woven directly into prose, and zero comma-stacked inventories."
    ),
    "strategic_mandate_resonance": (
        "Does the candidate's proven track record naturally solve the target role's core mandate without keyword "
        "stuffing, JD mirroring, or off-domain clutter?"
    ),
    "factual_truth_and_non_exaggeration": (
        "Is every displayed claim, number, and scope faithfully backed by the allowed_fact_packet without "
        "inflation, unsupported extrapolation, cross-fact conflation, or treating JD/briefing/target company as experience?"
    ),
}


def build_executive_summary_x1d_rubric_text(*, include_score_schema: str = "") -> str:
    """Canonical six-dimension blind human hiring-committee rubric for exec-summary X1D judges."""
    lines = [
        "You are a skeptical executive hiring committee (CTO / SVP Engineering / Head of Talent Acquisition) evaluating "
        "one executive resume **executive summary paragraph** produced under ``executive_summary.generate_scratch_v1``.",
        "Core question: **Does this sound like a rare, high-caliber executive we must speak to immediately?**",
        "Strict frontier-lab grader separation: deterministic code graders ALREADY checked formatting, character/word "
        "bounds, and syntax. Do NOT re-count words or characters or audit code compliance — focus 100% on human hiring "
        "conviction, spoken authenticity, differentiated edge, six-second scannability, mandate resonance, and factual "
        "truth grounded in ``claim_ledger`` and ``source_fact_ids``.",
        "Write your concise `rationale` FIRST before choosing `score`. Be strictly calibrated and resist score inflation:",
        "- <= 3.8: Generic, robotic, AI-cadence, cluttered, or factually inflated (FAIL).",
        "- 3.9 to 4.3: Solid and professional, but ordinary / interchangeable with peers (FAIL).",
        "- 4.4 to 4.6: Strong executive summary, but not yet an immediate-call standout (FAIL).",
        "- 4.7 to 5.0: Unmistakable, human-voiced, high-caliber executive we must call today (PASS; threshold >= 4.7).",
        "Return JSON only with: rationale, score_scale, score, threshold, pass, decisive_failure, "
        "findings, cited_sentence_indexes, remediation_suggestions, dimension_verdicts. "
        "cited_sentence_indexes MUST list every 1-based sentence (S1=1 ... S4=4) you want improved.",
    ]
    if include_score_schema.strip():
        lines.extend(["", include_score_schema.strip()])
    lines.extend(["", "Rubric dimensions (all 6 required):"])
    for idx, dim in enumerate(EXEC_SUMMARY_RUBRIC_DIMENSION_IDS, start=1):
        prose = _EXEC_SUMMARY_RUBRIC_DIMENSION_PROSE[dim]
        lines.append(f"{idx}. {dim}: {prose}")
    lines.extend(
        [
            "",
            f"**Visual layout context:** concise {EXEC_SUMMARY_MIN_SENTENCES}-to-{EXEC_SUMMARY_MAX_SENTENCES} sentence "
            f"executive paragraph (~{EXEC_SUMMARY_MIN_CHARS}-{EXEC_SUMMARY_MAX_CHARS} chars, max {EXEC_SUMMARY_MAX_WORDS} words overflow cap). "
            "Judge impact and human clarity, not word count.",
            "",
            "Decisive failure triggers:",
            "- unsupported or exaggerated business metric, scope, or credential",
            "- target company presented as candidate experience or JD/briefing used as proof",
            "- obvious AI-generated cadence, stacked transition crutches, abstract noun soup, or recruiter fluff",
            "- off-domain clutter that diverges sharply from the target role mandate",
            "- internal codebase micro-plumbing laundry lists or mechanical bullet-stack prose",
        ]
    )
    return "\n".join(lines)


def required_judge_output_dimension_block() -> str:
    """Prompt appendix for REQUIRED_JUDGE_OUTPUT_SCHEMA."""
    dims = ", ".join(EXEC_SUMMARY_RUBRIC_DIMENSION_IDS)
    return (
        '"dimension_verdicts": {'
        + ", ".join(
            f'"{d}": {{"pass": true, "severity": "none", "codes": []}}' for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS
        )
        + "}"
        f"\nAll six keys required: {dims}. "
        "Passing requires score >= 4.7 (0_to_5), decisive_failure=false, ALL six dimensions pass=true, "
        "AND severity='none' on both immediate_call_conviction and spoken_executive_authenticity. "
        "Use severity major when a dimension blocks an immediate call; minor for a noticeable polish gap; none when crisp and human."
    )


def executive_summary_human_dimension_floor_passes(
    dimension_verdicts: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Enforce the 6-dimension human hiring-committee pass floor.

    Requires:
      1. All 6 EXEC_SUMMARY_RUBRIC_DIMENSION_IDS present with ``pass is True``.
      2. ``severity == "none"`` on both ``immediate_call_conviction`` and
         ``spoken_executive_authenticity`` (no minor or major dings tolerated).
    """
    if not isinstance(dimension_verdicts, dict):
        return False, ["dimension_verdicts missing for executive_summary human judge floor"]
    reasons: list[str] = []
    for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
        entry = dimension_verdicts.get(dim)
        if not isinstance(entry, dict):
            reasons.append(f"human_judge_floor_missing_dimension:{dim}")
            continue
        if entry.get("pass") is not True:
            reasons.append(f"human_judge_floor_dimension_failed:{dim}")
            continue
        sev = str(entry.get("severity") or "none").strip().lower()
        if dim in EXEC_SUMMARY_STRICT_ZERO_DEFECT_DIMENSIONS and sev != "none":
            reasons.append(f"human_judge_floor_nonzero_severity:{dim}={sev}")
    return (len(reasons) == 0), reasons


def _all_x2_gates_pass(gate_summary: dict[str, Any] | None) -> bool:
    if not gate_summary:
        return False
    for val in gate_summary.values():
        if isinstance(val, dict) and val.get("pass") is False:
            return False
    return bool(gate_summary)


def _empty_verdict(*, pass_: bool = True, severity: str = "none") -> dict[str, Any]:
    return {"pass": pass_, "severity": severity, "codes": []}


def _default_verdicts(*, headline_pass: bool) -> dict[str, dict[str, Any]]:
    severity = "none" if headline_pass else "major"
    out: dict[str, dict[str, Any]] = {}
    for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
        out[dim] = _empty_verdict(pass_=headline_pass, severity=severity)
    return out


def _coerce_verdict_entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    pass_raw = raw.get("pass")
    if not isinstance(pass_raw, bool):
        return None
    severity = str(raw.get("severity") or ("none" if pass_raw else "major")).strip().lower()
    if severity not in VALID_SEVERITIES:
        severity = "none" if pass_raw else "major"
    codes_raw = raw.get("codes") or []
    codes: list[str] = []
    if isinstance(codes_raw, list):
        for c in codes_raw:
            s = str(c).strip()
            if s:
                codes.append(s)
    return {"pass": pass_raw, "severity": severity, "codes": codes}


def infer_dimension_verdicts_from_judge_blob(
    result: dict[str, Any],
    *,
    deterministic_gate_summary: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build dimension_verdicts from legacy judge fields when models omit the block."""
    headline_pass = bool(result.get("pass"))
    if result.get("decisive_failure"):
        headline_pass = False
    verdicts = _default_verdicts(headline_pass=headline_pass)

    blob_parts: list[str] = []
    for key in ("findings", "fail_reasons", "quality_flags", "remediation_suggestions"):
        val = result.get(key)
        if isinstance(val, list):
            blob_parts.extend(str(x) for x in val)
        elif val:
            blob_parts.append(str(val))
    if result.get("rationale"):
        blob_parts.append(str(result.get("rationale")))
    blob = " ".join(blob_parts).lower()

    failed_dims: set[str] = set()
    codes_by_dim: dict[str, list[str]] = {d: [] for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS}

    for flag in result.get("quality_flags") or []:
        flag_s = str(flag).strip()
        for dim in _FLAG_TO_DIMENSIONS.get(flag_s, ()):
            failed_dims.add(dim)
            codes_by_dim[dim].append(flag_s)

    for dim, hints in _TEXT_HINTS:
        if dim == "factual_truth_and_non_exaggeration":
            if not any(h in blob for h in ("unsupported", "exaggerat", "inflat", "fabricat", "ledger", "source_fact")):
                continue
        elif not any(h in blob for h in hints):
            continue
        failed_dims.add(dim)

    if not headline_pass and not failed_dims:
        failed_dims.update({"immediate_call_conviction", "spoken_executive_authenticity"})

    for dim in failed_dims:
        verdicts[dim] = {
            "pass": False,
            "severity": "major",
            "codes": codes_by_dim.get(dim) or ["inferred_from_findings"],
        }

    if headline_pass:
        for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
            if dim not in failed_dims:
                verdicts[dim] = _empty_verdict(pass_=True)

    return verdicts


def enforce_deterministic_alignment_verdict(
    verdicts: dict[str, dict[str, Any]],
    deterministic_gate_summary: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Compat no-op: frontier-lab grader separation keeps LLM judge verdicts blind to X2 pass flags."""
    _ = deterministic_gate_summary
    return dict(verdicts)


def ensure_dimension_verdicts(
    result: dict[str, Any],
    *,
    deterministic_gate_summary: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Validate or infer 6-dimension human verdicts; return (result, inferred_flag)."""
    _ = deterministic_gate_summary
    inferred = False
    raw = result.get("dimension_verdicts")
    verdicts: dict[str, dict[str, Any]] | None = None
    if isinstance(raw, dict) and raw:
        parsed: dict[str, dict[str, Any]] = {}
        ok = True
        for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
            entry = _coerce_verdict_entry(raw.get(dim))
            if entry is None:
                ok = False
                break
            parsed[dim] = entry
        if ok:
            verdicts = parsed
    if verdicts is None:
        verdicts = infer_dimension_verdicts_from_judge_blob(result, deterministic_gate_summary=None)
        inferred = True
    out = dict(result)
    out["dimension_verdicts"] = verdicts
    out["dimension_verdicts_inferred"] = inferred
    return out, inferred


def build_x1d_dimension_matrix(judges: list[Any]) -> dict[str, Any]:
    """Operator matrix: dimension × judge pass/fail + 2/3 consensus."""
    from apps_rg.runtime.sections.executive_summary_judge_remediation import _coerce_judge_dict

    norm = [_coerce_judge_dict(j) for j in judges]
    provider_rows: list[dict[str, Any]] = []
    by_dimension: dict[str, dict[str, Any]] = {}

    for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
        by_dimension[dim] = {"judges": {}, "fail_count": 0, "pass_count": 0, "consensus_fail": False}

    for j in norm:
        if j.get("evaluator_mode") != "MODEL_BACKED":
            continue
        pk = str(j.get("provider_key") or j.get("judge_id") or "unknown")
        dv = j.get("dimension_verdicts") or {}
        row = {
            "provider_key": pk,
            "provider_name": j.get("provider_name"),
            "score": j.get("score"),
            "pass": j.get("pass"),
            "provider_status": j.get("provider_status"),
            "dimension_verdicts_inferred": j.get("dimension_verdicts_inferred"),
            "dimensions": {},
        }
        for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
            entry = dv.get(dim) if isinstance(dv, dict) else None
            if isinstance(entry, dict):
                passed = bool(entry.get("pass"))
                severity = entry.get("severity")
                codes = list(entry.get("codes") or [])
            else:
                passed = None
                severity = None
                codes = []
            row["dimensions"][dim] = {"pass": passed, "severity": severity, "codes": codes}
            if passed is False:
                by_dimension[dim]["judges"][pk] = False
                by_dimension[dim]["fail_count"] += 1
            elif passed is True:
                by_dimension[dim]["judges"][pk] = True
                by_dimension[dim]["pass_count"] += 1
        provider_rows.append(row)

    # Panel-relative consensus. The hardcoded ">= 2" assumed a 3-provider panel; with the recalibrated
    # Claude-base panels (1 or 2 cross-provider judges) a dimension fails when the panel does not
    # unanimously pass it (<=2 judges) or a majority fails it (>=3). Prevents a 1-judge panel from
    # becoming non-gating (a single fail must still fail). Recalibrated 2026-06-08.
    n_judges = len(provider_rows)
    fail_threshold = 1 if n_judges <= 2 else (n_judges // 2 + 1)
    for dim, agg in by_dimension.items():
        agg["consensus_fail"] = agg["fail_count"] >= fail_threshold

    return {
        "schema": "executive_summary_x1d_dimension_matrix_v1",
        "dimension_ids": list(EXEC_SUMMARY_RUBRIC_DIMENSION_IDS),
        "providers": provider_rows,
        "by_dimension": by_dimension,
    }


def write_x1d_dimension_matrix_artifact(path: Any, judges: list[Any]) -> str:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = build_x1d_dimension_matrix(judges)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, ensure_ascii=False, default=str)
    return str(p)


DIMENSION_REGEN_FIX_INSTRUCTIONS: dict[str, str] = {
    "immediate_call_conviction": (
        "immediate_call_conviction: sharpen S1 and flagship proof sentences so a skeptical hiring committee "
        "sees rare executive scale and concrete outcomes immediately — eliminate safe, generic phrasing."
    ),
    "spoken_executive_authenticity": (
        "spoken_executive_authenticity: write in crisp, spoken boardroom English; remove ALL AI bridge crutches "
        "('In parallel,', 'Building on that', 'Across enterprise programs,', 'That governed...'), abstract noun soup "
        "('operating-model framing', 'governed activation', 'durable economics'), and stiff essay cadence."
    ),
    "differentiated_edge": (
        "differentiated_edge: foreground the candidate's unmistakable rare combination of technical platform build, "
        "commercial/revenue scale, and regulated governance rigor using concrete allowed metrics."
    ),
    "six_second_scannability": (
        "six_second_scannability: tighten to 3 to 4 crisp sentences (420 to 680 chars, max 210 chars/sentence) "
        "with varied sentence lengths (>= 4 word spread), distinct openers, and zero comma-stacked inventories."
    ),
    "strategic_mandate_resonance": (
        "strategic_mandate_resonance: frame proven capabilities directly toward the target role's core mandate "
        "without copying JD phrasing, keyword stuffing, or leaving off-domain clutter."
    ),
    "factual_truth_and_non_exaggeration": (
        "factual_truth_and_non_exaggeration: ensure every claim and metric maps faithfully to allowed source_fact_ids "
        "with zero inflation, cross-fact conflation, or JD/target-company-as-proof."
    ),
}


def dimension_major_fail_on_judge(judge: dict[str, Any], dimension_id: str) -> bool:
    """True when a judge marked the dimension failed with major severity."""
    dv = judge.get("dimension_verdicts") if isinstance(judge.get("dimension_verdicts"), dict) else {}
    row = dv.get(dimension_id) if isinstance(dv, dict) else None
    if not isinstance(row, dict):
        return False
    return row.get("pass") is False and str(row.get("severity") or "").lower() == "major"


def major_dimension_fail_count(judge: dict[str, Any]) -> int:
    """Count rubric dimensions with major fail on this judge."""
    dv = judge.get("dimension_verdicts") if isinstance(judge.get("dimension_verdicts"), dict) else {}
    keys = list(EXEC_SUMMARY_RUBRIC_DIMENSION_IDS)
    for k in dv:
        if k not in keys:
            keys.append(k)
    return sum(1 for dim in keys if dimension_major_fail_on_judge(judge, dim))


def major_failed_dimension_ids_from_judges(
    judges: list[dict[str, Any]],
    *,
    judge_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> list[str]:
    """Ordered dimension ids with major fail on at least one filtered judge."""
    failed: list[str] = []
    seen: set[str] = set()
    for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
        for j in judges:
            if judge_filter is not None and not judge_filter(j):
                continue
            if dimension_major_fail_on_judge(j, dim) and dim not in seen:
                seen.add(dim)
                failed.append(dim)
                break
    for j in judges:
        if judge_filter is not None and not judge_filter(j):
            continue
        dv = j.get("dimension_verdicts")
        if not isinstance(dv, dict):
            continue
        for dim in dv:
            if dim not in seen and dimension_major_fail_on_judge(j, dim):
                seen.add(dim)
                failed.append(dim)
    return failed


def collect_dimension_focused_regen_delta_lines(
    soft_judges: list[dict[str, Any]],
) -> list[str]:
    """Compact, dimension-only delta lines for same-authority regen (512-token budget)."""
    lines: list[str] = []
    for dim in major_failed_dimension_ids_from_judges(soft_judges):
        fix = DIMENSION_REGEN_FIX_INSTRUCTIONS.get(dim)
        if fix:
            lines.append(fix)
    return lines


def collect_dimension_remediation_lines(
    x1d_judges: list[dict[str, Any]],
    *,
    min_fail_count: int = 1,
) -> list[str]:
    """Dimension-tagged lines for judge regen user message."""
    matrix = build_x1d_dimension_matrix(x1d_judges)
    lines: list[str] = []
    seen: set[str] = set()
    for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
        agg = matrix["by_dimension"].get(dim) or {}
        if int(agg.get("fail_count") or 0) < min_fail_count:
            continue
        judge_bits: list[str] = []
        for pk, passed in (agg.get("judges") or {}).items():
            if passed is False:
                judge_bits.append(pk)
        codes: list[str] = []
        for prow in matrix.get("providers") or []:
            if prow.get("provider_key") not in judge_bits:
                continue
            ent = (prow.get("dimensions") or {}).get(dim) or {}
            codes.extend(str(c) for c in (ent.get("codes") or []) if str(c).strip())
        code_s = ", ".join(sorted(set(codes))[:6]) or "see_findings"
        line = f"{dim} ({agg.get('fail_count')}/{len(judge_bits) or 3} judges FAIL): {code_s}"
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if len(lines) >= 8:
            break
    return lines
