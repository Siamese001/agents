"""Modular executive summary X2 validation package."""

from __future__ import annotations

from apps_rg.runtime.validators.exec_summary_x2.constants import X2GateResult
from apps_rg.runtime.validators.exec_summary_x2.gate_runner_tail import (
    failed_gate_ids,
    gates_pass,
)

__all__ = [
    "X2GateResult",
    "failed_gate_ids",
    "gates_pass",
]
