"""Runtime Precedent Bridge and Ambiguity Gating Interface.

Part of Sovereign Agentic Platform System Learning Rigor (Wave 4).
Bridges runtime agents and orchestration controllers with persistent HITL decision
precedents, Bayesian learning aggregate adjustments, and calibrated ambiguity gating.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Mapping, Sequence

_log = logging.getLogger(__name__)


class RuntimePrecedentBridge:
    """Runtime bridge connecting agent execution pipelines with Bayesian precedent store."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = db_path
        self._store: Any = None
        self._init_store()

    def _init_store(self) -> None:
        try:
            from tools.hitl_governance import HITLDecisionStore

            self._store = HITLDecisionStore(db_path=self.db_path)
        except (ImportError, OSError, RuntimeError, ValueError):
            self._store = None

    def is_healthy(self) -> bool:
        """Check if persistent precedent store is available."""
        return self._store is not None

    def get_category_learning_factor(self, category: str, option_label: str = "") -> float:
        """Retrieve historical Bayesian learning adjustment factor for a decision category."""
        if not self._store:
            return 0.0
        factor = 0.0
        try:
            factor = float(self._store.query_learning_adjustment(category, option_label))
        except (sqlite3.Error, ValueError, TypeError, AttributeError, RuntimeError, OSError) as exc:
            _log.warning("Precedent learning factor lookup failed for %s: %s", category, exc)
        return factor

    def evaluate_runtime_ambiguity(
        self,
        options: Sequence[Mapping[str, Any] | str],
        *,
        category: str | None = None,
        margin_threshold: float = 0.20,
    ) -> dict[str, Any]:
        """Evaluate candidate runtime options against the calibrated 20% ambiguity margin rule."""
        if not self._store:
            # Fallback simple evaluator if store unavailable
            scored: list[tuple[float, Any]] = []
            for opt in options:
                score = 0.50
                if isinstance(opt, Mapping):
                    score = float(opt.get("confidence_score", opt.get("confidence", 0.50)))
                scored.append((score, opt))
            scored.sort(key=lambda x: x[0], reverse=True)
            top_s, top_o = scored[0] if scored else (0.0, None)
            second_s = scored[1][0] if len(scored) > 1 else 0.0
            margin = round(top_s - second_s, 4)
            should_surface = margin <= margin_threshold
            return {
                "should_surface": should_surface,
                "margin": margin,
                "margin_threshold": margin_threshold,
                "top_option": top_o,
                "top_score": top_s,
                "second_score": second_s,
                "action": "SURFACE_HITL_ATOMIC" if should_surface else "PROCEED_AUTONOMOUSLY",
                "reason": "Evaluated via fallback in-process gate.",
            }

        try:
            from tools.hitl_governance import evaluate_hitl_surfacing_gate

            return evaluate_hitl_surfacing_gate(
                options=options,
                margin_threshold=margin_threshold,
                store=self._store,
                category=category,
            )
        except Exception as exc:  # guardian: allow-broad-exception -- fail closed on any gate error
            _log.warning("Runtime ambiguity gate failed closed: %s", exc)
            return {
                "should_surface": True,
                "margin": 0.0,
                "margin_threshold": margin_threshold,
                "top_option": options[0] if options else None,
                "top_score": 0.0,
                "second_score": 0.0,
                "action": "SURFACE_HITL_ATOMIC",
                "reason": f"Fail-closed gate error: {exc}",
            }

    def record_runtime_decision(
        self,
        decision_id: str,
        category: str,
        options: Sequence[Any],
        selected_option: str,
        *,
        task_id: str = "runtime_execution",
        operator_action: str = "PROCEED_AUTONOMOUSLY",
        margin: float = 0.25,
        calibrated_confidence: float = 0.85,
        context_summary: str = "",
        outcome: str = "SUCCESS",
    ) -> dict[str, Any]:
        """Record an autonomous or operator-approved decision into persistent store."""
        if not self._store:
            return {"decision_id": decision_id, "status": "NO_OP_FALLBACK"}
        try:
            return self._store.record_decision(
                decision_id=decision_id,
                task_id=task_id,
                category=category,
                options=options,
                selected_option=selected_option,
                operator_action=operator_action,
                margin=margin,
                calibrated_confidence=calibrated_confidence,
                context_summary=context_summary,
                outcome=outcome,
            )
        except Exception as exc:
            return {"decision_id": decision_id, "status": "ERROR", "error": str(exc)}

    def close(self) -> None:
        """Close precedent store connection."""
        if self._store and hasattr(self._store, "close"):
            try:
                self._store.close()
            except (OSError, RuntimeError, ValueError):  # guardian: allow-silent-swallow -- store cleanup on close is best-effort
                pass
            self._store = None


__all__ = [
    "RuntimePrecedentBridge",
]
