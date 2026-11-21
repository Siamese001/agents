"""Multi-objective Pareto frontier (quality max, latency min, cost min) and regression gating."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence


@dataclass(frozen=True)
class ParetoPoint:
    config_id: str
    quality_score: float
    latency_ms: float
    cost_usd: float
    reasoning_effort: str = "medium"
    is_pareto_optimal: bool = False
    dominated_by: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name, val in (
            ("quality_score", self.quality_score),
            ("latency_ms", self.latency_ms),
            ("cost_usd", self.cost_usd),
        ):
            if not math.isfinite(float(val)):
                raise ValueError(f"INVALID_NON_FINITE:{name}={val!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParetoRegressionVerdict:
    candidate_id: str
    baseline_id: str
    is_regression: bool
    quality_delta_pct: float
    latency_delta_pct: float
    cost_delta_pct: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pct_change(baseline: float, candidate: float) -> float:
    if baseline == 0.0:
        if candidate == 0.0:
            return 0.0
        return 100.0 if candidate > 0.0 else -100.0
    return ((candidate - baseline) / abs(baseline)) * 100.0


class ParetoFrontierAnalyzer:
    """Identifies non-dominated configurations and enforces simultaneous quality/latency/cost guardrails."""

    def __init__(
        self,
        *,
        max_quality_drop_pct: float = 5.0,
        max_latency_spike_pct: float = 25.0,
        max_cost_spike_pct: float = 25.0,
    ) -> None:
        self.max_quality_drop_pct = max_quality_drop_pct
        self.max_latency_spike_pct = max_latency_spike_pct
        self.max_cost_spike_pct = max_cost_spike_pct

    @staticmethod
    def _dominates(a: ParetoPoint, b: ParetoPoint) -> bool:
        better_or_eq = (
            a.quality_score >= b.quality_score
            and a.latency_ms <= b.latency_ms
            and a.cost_usd <= b.cost_usd
        )
        strictly_better = (
            a.quality_score > b.quality_score
            or a.latency_ms < b.latency_ms
            or a.cost_usd < b.cost_usd
        )
        return better_or_eq and strictly_better

    def compute_frontier(self, points: Sequence[ParetoPoint]) -> list[ParetoPoint]:
        out: list[ParetoPoint] = []
        for p in points:
            doms = [
                other.config_id
                for other in points
                if other.config_id != p.config_id and self._dominates(other, p)
            ]
            out.append(
                ParetoPoint(
                    config_id=p.config_id,
                    quality_score=p.quality_score,
                    latency_ms=p.latency_ms,
                    cost_usd=p.cost_usd,
                    reasoning_effort=p.reasoning_effort,
                    is_pareto_optimal=(len(doms) == 0),
                    dominated_by=sorted(doms),
                )
            )
        return out

    def evaluate_regression(
        self,
        candidate: ParetoPoint,
        baseline: ParetoPoint,
    ) -> ParetoRegressionVerdict:
        q_delta_pct = _pct_change(baseline.quality_score, candidate.quality_score)
        l_delta_pct = _pct_change(baseline.latency_ms, candidate.latency_ms)
        c_delta_pct = _pct_change(baseline.cost_usd, candidate.cost_usd)

        reasons: list[str] = []
        if q_delta_pct < -self.max_quality_drop_pct:
            reasons.append(f"QUALITY_DROP:{q_delta_pct:.2f}%<-{self.max_quality_drop_pct:.2f}%")
        if l_delta_pct > self.max_latency_spike_pct:
            reasons.append(f"LATENCY_SPIKE:{l_delta_pct:.2f}%>{self.max_latency_spike_pct:.2f}%")
        if c_delta_pct > self.max_cost_spike_pct:
            reasons.append(f"COST_SPIKE:{c_delta_pct:.2f}%>{self.max_cost_spike_pct:.2f}%")

        return ParetoRegressionVerdict(
            candidate_id=candidate.config_id,
            baseline_id=baseline.config_id,
            is_regression=(len(reasons) > 0),
            quality_delta_pct=round(q_delta_pct, 2),
            latency_delta_pct=round(l_delta_pct, 2),
            cost_delta_pct=round(c_delta_pct, 2),
            reasons=reasons,
        )
