"""2D longitudinal evaluation tracker (pipeline_version x rubric_version), anchor-peak/rolling drift, and counterfactual self-probe."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.contracts.digests import canonical_sha256
from apps_eval.contracts.schemas import utc_now_iso

LONGITUDINAL_CONTRACT_ID = "urn:agents:eval:longitudinal-eval-ledger:1.0.0"


def _validate_ledger_path(path: Path) -> None:
    resolved = Path(path).resolve()
    if "output" in [p.lower() for p in resolved.parts]:
        raise ValueError(f"Refusing to write longitudinal eval ledger under production output/: {resolved}")


@dataclass(frozen=True)
class LongitudinalEvalEntry:
    run_id: str
    timestamp: str
    pipeline_version: str
    rubric_version: str
    benchmark_suite: str
    model_id: str
    reasoning_effort: str
    metrics: dict[str, float]
    gates: dict[str, bool]
    git_commit: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for k, v in self.metrics.items():
            if isinstance(v, bool) or not math.isfinite(float(v)):
                raise ValueError(f"Non-finite longitudinal metric {k}={v!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LongitudinalEvalEntry:
        return cls(
            run_id=str(data["run_id"]),
            timestamp=str(data["timestamp"]),
            pipeline_version=str(data["pipeline_version"]),
            rubric_version=str(data["rubric_version"]),
            benchmark_suite=str(data["benchmark_suite"]),
            model_id=str(data["model_id"]),
            reasoning_effort=str(data["reasoning_effort"]),
            metrics={str(k): float(v) for k, v in (data.get("metrics") or {}).items()},
            gates={str(k): bool(v) for k, v in (data.get("gates") or {}).items()},
            git_commit=str(data.get("git_commit") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


class LongitudinalEvaluationTracker:
    """Persists and analyzes longitudinal benchmark series with 2D attribution and anchor-peak drift detection."""

    def __init__(self, ledger_path: Path) -> None:
        _validate_ledger_path(ledger_path)
        self.ledger_path = Path(ledger_path).resolve()
        self._entries: list[LongitudinalEvalEntry] = []
        if self.ledger_path.is_file():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        entries = raw.get("entries") or []
        self._entries = [LongitudinalEvalEntry.from_dict(e) for e in entries]

    def _save(self) -> None:
        _validate_ledger_path(self.ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [e.to_dict() for e in self._entries]
        payload = {
            "contract_id": LONGITUDINAL_CONTRACT_ID,
            "schema_version": "1.0.0",
            "updated_at_utc": utc_now_iso(),
            "entry_count": len(serialized),
            "ledger_digest": canonical_sha256(serialized),
            "entries": serialized,
        }
        tmp = self.ledger_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.ledger_path)

    @property
    def entries(self) -> list[LongitudinalEvalEntry]:
        return list(self._entries)

    def record_entry(self, entry: LongitudinalEvalEntry, *, allow_overwrite_seed: bool = False) -> None:
        if any(e.run_id == entry.run_id for e in self._entries) and not allow_overwrite_seed:
            raise ValueError(f"Refusing to overwrite existing longitudinal entry run_id={entry.run_id}")
        self._entries.append(entry)
        self._save()

    def compute_two_dimensional_attribution(
        self,
        *,
        benchmark_suite: str,
        metric_name: str,
        baseline_pipeline: str,
        target_pipeline: str,
        baseline_rubric: str,
        target_rubric: str,
        strict_model_pinning: bool = True,
    ) -> dict[str, Any]:
        """Decompose Delta_Total = Delta_Pipeline(R_fixed) + Delta_Rubric(P_fixed) + Epsilon."""
        scoped = [e for e in self._entries if e.benchmark_suite == benchmark_suite and metric_name in e.metrics]
        cells: dict[tuple[str, str], list[LongitudinalEvalEntry]] = {
            (baseline_pipeline, baseline_rubric): [],
            (target_pipeline, baseline_rubric): [],
            (baseline_pipeline, target_rubric): [],
            (target_pipeline, target_rubric): [],
        }
        for e in scoped:
            key = (e.pipeline_version, e.rubric_version)
            if key in cells:
                cells[key].append(e)

        missing = [k for k, v in cells.items() if not v]
        if missing:
            return {"status": "INCOMPLETE_MATRIX", "missing_cells": [f"{p}|{r}" for p, r in missing]}

        resolved: dict[tuple[str, str], tuple[float, str, str]] = {}
        for key, items in cells.items():
            models = {(i.model_id, i.reasoning_effort) for i in items}
            vals = [float(i.metrics[metric_name]) for i in items]
            if len(models) > 1 or (max(vals) - min(vals)) > 1e-6:
                return {"status": "AMBIGUOUS_CELL", "cell": f"{key[0]}|{key[1]}"}
            m_id, effort = next(iter(models))
            resolved[key] = (vals[0], m_id, effort)

        base_r0 = resolved[(baseline_pipeline, baseline_rubric)]
        base_r1 = resolved[(baseline_pipeline, target_rubric)]
        targ_r0 = resolved[(target_pipeline, baseline_rubric)]
        targ_r1 = resolved[(target_pipeline, target_rubric)]

        if (base_r0[1], base_r0[2]) != (base_r1[1], base_r1[2]):
            return {"status": "CONFOUNDED_BASELINE", "reason": "baseline_model_or_effort_mismatch_across_rubrics"}
        if strict_model_pinning and (targ_r0[1], targ_r0[2]) != (targ_r1[1], targ_r1[2]):
            return {"status": "CONFOUNDED_BASELINE", "reason": "target_model_or_effort_mismatch_across_rubrics"}

        delta_total = targ_r1[0] - base_r0[0]
        delta_pipeline = targ_r0[0] - base_r0[0]
        delta_rubric = base_r1[0] - base_r0[0]
        epsilon = delta_total - (delta_pipeline + delta_rubric)
        return {
            "status": "OK",
            "delta_total": round(delta_total, 6),
            "delta_pipeline": round(delta_pipeline, 6),
            "delta_rubric": round(delta_rubric, 6),
            "interaction_epsilon": round(epsilon, 6),
        }

    def detect_cumulative_merge_drift(
        self,
        *,
        benchmark_suite: str,
        metric_name: str,
        active_rubric_version: str,
        max_drop_pct: float = 2.0,
    ) -> dict[str, Any]:
        """Compare latest score against full-history anchor peak under active_rubric_version."""
        series = [
            e
            for e in self._entries
            if e.benchmark_suite == benchmark_suite
            and e.rubric_version == active_rubric_version
            and metric_name in e.metrics
        ]
        if len(series) < 2:
            return {"status": "INSUFFICIENT_HISTORY", "samples": len(series)}

        latest = series[-1]
        latest_score = float(latest.metrics[metric_name])
        anchor_peak = max(float(e.metrics[metric_name]) for e in series[:-1])
        failed_gates = sorted(k for k, v in latest.gates.items() if not v)

        pct_change = (
            ((latest_score - anchor_peak) / abs(anchor_peak)) * 100.0
            if anchor_peak != 0.0
            else (0.0 if latest_score == 0.0 else -100.0)
        )
        drift = (pct_change < -max_drop_pct) or bool(failed_gates)
        return {
            "status": "DRIFT_ALERT" if drift else "STABLE",
            "benchmark_suite": benchmark_suite,
            "metric_name": metric_name,
            "active_rubric_version": active_rubric_version,
            "anchor_peak": round(anchor_peak, 4),
            "latest_score": round(latest_score, 4),
            "signed_change_pct": round(pct_change, 2),
            "failed_gates": failed_gates,
        }

    def detect_rolling_window_drift(
        self,
        *,
        benchmark_suite: str,
        metric_name: str,
        active_rubric_version: str,
        baseline_window: int = 5,
        trailing_window: int = 5,
        max_drop_pct: float = 5.0,
        verified_watermark_utc: str | None = None,
        peak_erosion_pct: float = 2.0,
    ) -> dict[str, Any]:
        """Compare trailing window mean vs dual-anchor post-fix baseline and 2.0% peak floor."""
        from apps_eval._core_governance_bridge import select_post_fix_baseline_scores

        series = [
            e
            for e in self._entries
            if e.benchmark_suite == benchmark_suite
            and e.rubric_version == active_rubric_version
            and metric_name in e.metrics
        ]
        needed = baseline_window + trailing_window
        if len(series) < needed:
            return {"status": "INSUFFICIENT_HISTORY", "samples": len(series), "needed": needed}

        base_scores, advanced = select_post_fix_baseline_scores(
            series, base_n=baseline_window, verified_watermark_utc=verified_watermark_utc, metric_name=metric_name
        )
        trail_slice = series[-trailing_window:]
        base_mean = sum(base_scores) / float(max(1, len(base_scores)))
        trail_mean = sum(float(e.metrics[metric_name]) for e in trail_slice) / float(trailing_window)
        peak_score = max(float(e.metrics[metric_name]) for e in series)
        trail_gate_failures = sorted({k for e in trail_slice for k, v in e.gates.items() if not v})
        pct_change = ((trail_mean - base_mean) / abs(base_mean)) * 100.0 if base_mean != 0.0 else 0.0
        peak_drop_pct = max(0.0, ((peak_score - trail_mean) / abs(peak_score)) * 100.0) if peak_score != 0.0 else 0.0
        peak_breached = peak_drop_pct > abs(float(peak_erosion_pct))
        drift = (pct_change < -max_drop_pct) or peak_breached or bool(trail_gate_failures)
        return {
            "status": "DRIFT_ALERT" if drift else "STABLE",
            "benchmark_suite": benchmark_suite,
            "metric_name": metric_name,
            "baseline_mean": round(base_mean, 4),
            "trailing_mean": round(trail_mean, 4),
            "historical_peak": round(peak_score, 4),
            "peak_floor_breached": peak_breached,
            "baseline_advanced_post_fix": advanced,
            "signed_change_pct": round(pct_change, 2),
            "trailing_failed_gates": trail_gate_failures,
        }


def run_asymmetric_fault_injection_probe() -> dict[str, Any]:
    """Counterfactual self-probe verifying all 6 longitudinal guard modes in an isolated temp dir."""
    results: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="agents-longitudinal-probe-") as td:
        root = Path(td)
        tracker = LongitudinalEvaluationTracker(root / "ledger.json")

        # 1. Plateau erosion from anchor peak (100 -> 99 -> 98 -> 97.5: 2.5% drop > 2%).
        for idx, val in enumerate((100.0, 99.0, 98.0, 97.5)):
            tracker.record_entry(
                LongitudinalEvalEntry(
                    run_id=f"erosion-{idx}",
                    timestamp=f"2026-11-0{idx+1}T00:00:00Z",
                    pipeline_version=f"p{idx}",
                    rubric_version="r1",
                    benchmark_suite="suite_erosion",
                    model_id="local-deterministic",
                    reasoning_effort="low",
                    metrics={"composite": val},
                    gates={"g1": True},
                )
            )
        d1 = tracker.detect_cumulative_merge_drift(
            benchmark_suite="suite_erosion", metric_name="composite", active_rubric_version="r1", max_drop_pct=2.0
        )
        results["plateau_erosion_caught"] = d1["status"] == "DRIFT_ALERT"

        # 2. Gate failure even at 100% score triggers DRIFT_ALERT.
        tracker.record_entry(
            LongitudinalEvalEntry(
                run_id="gate-drop-1",
                timestamp="2026-11-10T00:00:00Z",
                pipeline_version="p1",
                rubric_version="r1",
                benchmark_suite="suite_gate",
                model_id="local-deterministic",
                reasoning_effort="low",
                metrics={"composite": 100.0},
                gates={"g1": True},
            )
        )
        tracker.record_entry(
            LongitudinalEvalEntry(
                run_id="gate-drop-2",
                timestamp="2026-11-11T00:00:00Z",
                pipeline_version="p2",
                rubric_version="r1",
                benchmark_suite="suite_gate",
                model_id="local-deterministic",
                reasoning_effort="low",
                metrics={"composite": 100.0},
                gates={"g1": False},
            )
        )
        d2 = tracker.detect_cumulative_merge_drift(
            benchmark_suite="suite_gate", metric_name="composite", active_rubric_version="r1"
        )
        results["gate_drop_at_100pct_caught"] = d2["status"] == "DRIFT_ALERT"

        # 3. Ambiguous cell caught.
        for rid, p, r, val in (
            ("a1", "p1", "r1", 80.0),
            ("a1b", "p1", "r1", 85.0),
            ("a2", "p2", "r1", 88.0),
            ("a3", "p1", "r2", 82.0),
            ("a4", "p2", "r2", 90.0),
        ):
            tracker.record_entry(
                LongitudinalEvalEntry(rid, "2026-11-12T00:00:00Z", p, r, "suite_ambig", "m1", "low", {"s": val}, {})
            )
        d3 = tracker.compute_two_dimensional_attribution(
            benchmark_suite="suite_ambig",
            metric_name="s",
            baseline_pipeline="p1",
            target_pipeline="p2",
            baseline_rubric="r1",
            target_rubric="r2",
        )
        results["ambiguous_cell_caught"] = d3["status"] == "AMBIGUOUS_CELL"

        # 4. Baseline confounder caught.
        for rid, p, r, m, val in (
            ("c1", "p1", "r1", "m1", 80.0),
            ("c2", "p2", "r1", "m1", 88.0),
            ("c3", "p1", "r2", "m2", 82.0),
            ("c4", "p2", "r2", "m1", 90.0),
        ):
            tracker.record_entry(
                LongitudinalEvalEntry(rid, "2026-11-12T00:00:00Z", p, r, "suite_conf", m, "low", {"s": val}, {})
            )
        d4 = tracker.compute_two_dimensional_attribution(
            benchmark_suite="suite_conf",
            metric_name="s",
            baseline_pipeline="p1",
            target_pipeline="p2",
            baseline_rubric="r1",
            target_rubric="r2",
        )
        results["baseline_confounder_caught"] = d4["status"] == "CONFOUNDED_BASELINE"

        # 5. Seed overwrite blocked.
        overwrite_blocked = False
        try:
            tracker.record_entry(tracker.entries[0])
        except ValueError:
            overwrite_blocked = True
        results["seed_overwrite_blocked"] = overwrite_blocked

        # 6. Production output/ path write blocked.
        output_blocked = False
        try:
            LongitudinalEvaluationTracker(root / "output" / "ledger.json")
        except ValueError:
            output_blocked = True
        results["output_path_write_blocked"] = output_blocked

    return {
        "passed": all(results.values()),
        "checks": results,
    }
