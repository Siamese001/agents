"""Priority-weighted multi-lens blind judge panel with single-lens veto, score caps, and spread escalation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal, Mapping, Sequence


@dataclass(frozen=True)
class LensSpec:
    lens_id: str
    weight: float
    min_floor: float = 8.0


@dataclass(frozen=True)
class LensVerdict:
    lens_id: str
    score: float
    judge_model_family: str
    hard_veto_defects: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass(frozen=True)
class MultiLensPanelVerdict:
    weighted_score: float
    persona_score_spread: float
    model_family_score_spread: float
    effective_lens_scores: dict[str, float]
    applied_deterministic_caps: dict[str, float]
    veto_reasons: list[str]
    verdict: Literal["PASS", "FAIL", "HITL_ESCALATE"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dec(val: float) -> Decimal:
    return Decimal(str(val))


def evaluate_multi_lens_panel(
    specs: Sequence[LensSpec],
    verdicts: Sequence[LensVerdict],
    *,
    deterministic_score_caps: Mapping[str, float] | None = None,
    pass_threshold: float = 9.0,
    max_disagreement_spread: float = 0.5,
) -> MultiLensPanelVerdict:
    """Evaluate weighted multi-lens verdicts using Decimal math, single-lens vetoes, and spread escalation."""
    if not specs or not verdicts:
        return MultiLensPanelVerdict(
            weighted_score=0.0,
            persona_score_spread=0.0,
            model_family_score_spread=0.0,
            effective_lens_scores={},
            applied_deterministic_caps={},
            veto_reasons=["EMPTY_PANEL_OR_SPECS"],
            verdict="FAIL",
        )

    spec_map = {s.lens_id: s for s in specs}
    caps = dict(deterministic_score_caps or {})
    effective_scores: dict[str, float] = {}
    applied_caps: dict[str, float] = {}
    veto_reasons: list[str] = []
    by_family: dict[str, list[Decimal]] = {}

    weighted_sum = Decimal("0")
    total_weight = Decimal("0")

    for v in verdicts:
        if v.lens_id not in spec_map:
            veto_reasons.append(f"UNKNOWN_LENS:{v.lens_id}")
            continue
        spec = spec_map[v.lens_id]
        raw_score = float(v.score)
        eff_score = raw_score
        if v.lens_id in caps and eff_score > float(caps[v.lens_id]):
            eff_score = float(caps[v.lens_id])
            applied_caps[v.lens_id] = eff_score

        effective_scores[v.lens_id] = round(eff_score, 4)
        by_family.setdefault(v.judge_model_family, []).append(_dec(eff_score))

        if v.hard_veto_defects:
            veto_reasons.append(f"HARD_VETO_DEFECT:{v.lens_id}:{','.join(v.hard_veto_defects)}")
        if eff_score < spec.min_floor:
            veto_reasons.append(f"SINGLE_LENS_FLOOR_VETO:{v.lens_id}:{eff_score:.2f}<{spec.min_floor:.2f}")

        w = _dec(spec.weight)
        weighted_sum += _dec(eff_score) * w
        total_weight += w

    missing_lenses = sorted(set(spec_map.keys()) - set(effective_scores.keys()))
    for missing in missing_lenses:
        veto_reasons.append(f"MISSING_REQUIRED_LENS:{missing}")

    if total_weight <= Decimal("0"):
        weighted = Decimal("0")
    else:
        weighted = (weighted_sum / total_weight).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    score_vals = [_dec(s) for s in effective_scores.values()]
    persona_spread = float((max(score_vals) - min(score_vals))) if len(score_vals) >= 2 else 0.0

    fam_means = [sum(vals) / Decimal(len(vals)) for vals in by_family.values() if vals]
    family_spread = float((max(fam_means) - min(fam_means))) if len(fam_means) >= 2 else 0.0

    if veto_reasons or float(weighted) < pass_threshold:
        final_verdict: Literal["PASS", "FAIL", "HITL_ESCALATE"] = "FAIL"
    elif persona_spread > max_disagreement_spread or family_spread > max_disagreement_spread:
        final_verdict = "HITL_ESCALATE"
    else:
        final_verdict = "PASS"

    return MultiLensPanelVerdict(
        weighted_score=float(weighted),
        persona_score_spread=round(persona_spread, 4),
        model_family_score_spread=round(family_spread, 4),
        effective_lens_scores=effective_scores,
        applied_deterministic_caps=applied_caps,
        veto_reasons=veto_reasons,
        verdict=final_verdict,
    )
