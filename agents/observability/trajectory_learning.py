"""Event-Sourced Trajectory Learning and Golden Exemplar Mining.

Part of Sovereign Agentic Platform System Learning Rigor (Wave 3).
Mines append-only event streams from SqliteEventStore to identify high-efficiency
execution trajectories, evaluate recovery costs, and extract reusable golden exemplars
for prompt grounding and few-shot reasoning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from agents.observability.events import AgentEventEnvelope, AgentEventType
from agents.orchestration.learning_store import resolve_primary_repo_root
from agents.persistence.ports import EventStore

DEFAULT_TRAJECTORY_STORE_PATH = (
    resolve_primary_repo_root() / "artifacts" / "learning" / "trajectory_exemplars.json"
)


@dataclass(frozen=True, slots=True)
class TrajectoryExemplar:
    """An immutable, curated golden execution trajectory exemplar."""

    exemplar_id: str
    run_id: str
    task_type: str
    efficiency_score: float
    step_sequence: tuple[str, ...]
    key_decisions: tuple[str, ...]
    summary_text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize exemplar to dictionary."""
        return {
            "exemplar_id": self.exemplar_id,
            "run_id": self.run_id,
            "task_type": self.task_type,
            "efficiency_score": round(self.efficiency_score, 4),
            "step_sequence": list(self.step_sequence),
            "key_decisions": list(self.key_decisions),
            "summary_text": self.summary_text,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


class TrajectoryLearningEngine:
    """Mines execution event logs to extract efficiency patterns and golden exemplars."""

    def __init__(
        self,
        min_efficiency: float = 0.80,
        store_path: str | Path | None = None,
    ) -> None:
        self.min_efficiency = min_efficiency
        self.store_path: Path | None = Path(store_path).resolve() if store_path is not None else None
        self._indexed_exemplars: dict[str, list[TrajectoryExemplar]] = {}
        if self.store_path is not None and self.store_path.is_file():
            self.load_from_disk(self.store_path)

    def load_from_disk(self, path: str | Path) -> int:
        """Load persisted trajectory exemplars from JSON."""
        src = Path(path).resolve()
        if not src.is_file():
            return 0
        try:
            raw = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        items = raw.get("exemplars", []) if isinstance(raw, dict) else []
        loaded = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            ex = TrajectoryExemplar(
                exemplar_id=str(item.get("exemplar_id", "")),
                run_id=str(item.get("run_id", "")),
                task_type=str(item.get("task_type", "general")),
                efficiency_score=float(item.get("efficiency_score", 0.0)),
                step_sequence=tuple(str(s) for s in (item.get("step_sequence") or ())),
                key_decisions=tuple(str(d) for d in (item.get("key_decisions") or ())),
                summary_text=str(item.get("summary_text", "")),
                metadata=dict(item.get("metadata") or {}),
                created_at=float(item.get("created_at", time.time())),
            )
            if not ex.exemplar_id:
                continue
            bucket = self._indexed_exemplars.setdefault(ex.task_type, [])
            if all(existing.exemplar_id != ex.exemplar_id for existing in bucket):
                bucket.append(ex)
                loaded += 1
        return loaded

    def save_to_disk(self, path: str | Path | None = None) -> Path | None:
        """Persist indexed trajectory exemplars to JSON."""
        target = Path(path).resolve() if path is not None else self.store_path
        if target is None:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        flat = [
            ex.to_dict()
            for bucket in self._indexed_exemplars.values()
            for ex in bucket
        ]
        payload = {
            "schema_version": "agents.trajectory_exemplars.v1",
            "total_exemplars": len(flat),
            "exemplars": flat,
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return target

    def record_exemplar(self, exemplar: TrajectoryExemplar) -> bool:
        """Record an exemplar idempotently (deduplicated by exemplar_id) and persist if configured."""
        if exemplar.efficiency_score < self.min_efficiency:
            return False
        bucket = self._indexed_exemplars.setdefault(exemplar.task_type, [])
        if any(existing.exemplar_id == exemplar.exemplar_id for existing in bucket):
            return False
        bucket.append(exemplar)
        if self.store_path is not None:
            self.save_to_disk(self.store_path)
        return True

    def score_run_events(
        self,
        events: Sequence[AgentEventEnvelope],
    ) -> dict[str, Any]:
        """Compute execution efficiency metrics and trajectory statistics for a run."""
        if not events:
            return {
                "run_id": "unknown",
                "efficiency_score": 0.0,
                "is_golden": False,
                "step_count": 0,
                "recovery_count": 0,
                "evaluation_mean": 0.0,
            }

        run_id = events[0].run_id
        steps: list[str] = []
        decisions: list[str] = []
        eval_scores: list[float] = []
        recovery_count = 0
        has_fatal_escalation = False
        task_type = "general"

        for ev in events:
            p = ev.payload
            if ev.event_type == AgentEventType.PHASE_TRANSITION:
                step_name = p.get("step_name") or p.get("phase") or "step"
                steps.append(str(step_name))
                if "task_type" in p:
                    task_type = str(p["task_type"])
            elif ev.event_type == AgentEventType.FEEDBACK_DECISION:
                action = p.get("action", "")
                decisions.append(action)
                if "TERMINAL" in action or "ESCALATION" in action:
                    has_fatal_escalation = True
                elif "REVISION" in action or "RETRY" in action or "RECOVERY" in action:
                    recovery_count += 1
                if "score" in p:
                    try:
                        eval_scores.append(float(p["score"]))
                    except (ValueError, TypeError):  # guardian: allow-silent-swallow -- ignore unparseable score field in telemetry event
                        pass

        eval_mean = sum(eval_scores) / max(1, len(eval_scores)) if eval_scores else 0.85
        if has_fatal_escalation:
            efficiency = 0.0
        else:
            # Efficiency penalizes repeated retries and rewards high evaluation scores
            penalty = 1.0 + (0.15 * recovery_count)
            efficiency = round(max(0.0, min(1.0, eval_mean / penalty)), 4)

        is_golden = (efficiency >= self.min_efficiency) and not has_fatal_escalation

        return {
            "run_id": run_id,
            "task_type": task_type,
            "efficiency_score": efficiency,
            "is_golden": is_golden,
            "step_count": len(steps),
            "step_sequence": steps,
            "key_decisions": decisions,
            "recovery_count": recovery_count,
            "evaluation_mean": round(eval_mean, 4),
            "has_fatal_escalation": has_fatal_escalation,
        }

    def mine_from_events(
        self,
        events: Sequence[AgentEventEnvelope],
    ) -> TrajectoryExemplar | None:
        """Extract a golden exemplar from a run event sequence if criteria are met."""
        metrics = self.score_run_events(events)
        if not metrics["is_golden"]:
            return None

        run_id = metrics["run_id"]
        task_type = metrics["task_type"]
        summary = (
            f"Run {run_id} executed {metrics['step_count']} steps "
            f"with {metrics['recovery_count']} recoveries and mean score {metrics['evaluation_mean']:.2f}."
        )

        exemplar_id = f"ex_{hashlib.sha256(f'{run_id}:{metrics['efficiency_score']}'.encode()).hexdigest()[:10]}"
        exemplar = TrajectoryExemplar(
            exemplar_id=exemplar_id,
            run_id=run_id,
            task_type=task_type,
            efficiency_score=metrics["efficiency_score"],
            step_sequence=tuple(metrics["step_sequence"]),
            key_decisions=tuple(metrics["key_decisions"]),
            summary_text=summary,
            metadata={"evaluation_mean": metrics["evaluation_mean"], "recovery_count": metrics["recovery_count"]},
        )

        if task_type not in self._indexed_exemplars:
            self._indexed_exemplars[task_type] = []
        self._indexed_exemplars[task_type].append(exemplar)

        return exemplar

    def mine_store(self, store: EventStore) -> list[TrajectoryExemplar]:
        """Mine all distinct runs from an EventStore implementation."""
        # For SqliteEventStore, query distinct runs
        exemplars: list[TrajectoryExemplar] = []
        if hasattr(store, "_conn"):
            with store._conn:
                cursor = store._conn.execute("SELECT DISTINCT run_id FROM agent_events")
                run_ids = [r[0] for r in cursor.fetchall()]

            for r_id in run_ids:
                run_events = store.get_by_run(r_id)
                ex = self.mine_from_events(run_events)
                if ex:
                    exemplars.append(ex)
        return exemplars

    def get_exemplars_for_task(self, task_type: str, limit: int = 3) -> list[TrajectoryExemplar]:
        """Retrieve highest-efficiency exemplars for a specific task category."""
        candidates = self._indexed_exemplars.get(task_type, [])
        sorted_candidates = sorted(candidates, key=lambda e: e.efficiency_score, reverse=True)
        return sorted_candidates[:limit]

    def export_summary(self) -> dict[str, Any]:
        """Return aggregate trajectory learning metrics."""
        total = sum(len(exs) for exs in self._indexed_exemplars.values())
        categories = {k: len(v) for k, v in self._indexed_exemplars.items()}
        avg_eff = (
            sum(e.efficiency_score for exs in self._indexed_exemplars.values() for e in exs) / max(1, total)
        )
        return {
            "total_golden_trajectories": total,
            "categories": categories,
            "mean_golden_efficiency": round(avg_eff, 4),
            "min_efficiency_threshold": self.min_efficiency,
        }


__all__ = [
    "DEFAULT_TRAJECTORY_STORE_PATH",
    "TrajectoryExemplar",
    "TrajectoryLearningEngine",
]
