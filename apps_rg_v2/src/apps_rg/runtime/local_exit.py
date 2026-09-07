"""Apps RG-owned exit disposition adapter."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ExitDisposition:
    value: str
    outcome_authorized: bool
    c0_blocking: bool


@dataclass(frozen=True, slots=True)
class ExitEvaluation:
    disposition: ExitDisposition
    x3_packet: Any
    receipts: Mapping[str, Any]


class ExitEvalPipeline:
    """Translate Apps RG exit receipts into a deterministic disposition."""

    def run(self, receipts: Mapping[str, Any]) -> ExitEvaluation:
        terminal_class = str(receipts.get("terminal_class") or "failure")
        x3_code = str(receipts.get("x3_code") or "UNKNOWN")
        c0_blocking = bool(receipts.get("c0_blocking", False)) or str(
            receipts.get("fec_support_status") or ""
        ).upper() == "BLOCKED"
        authorized = terminal_class in {"success", "success_with_review"} and not c0_blocking
        if authorized:
            value = "X3D_ALLOW_FINISH" if terminal_class == "success" else "X3_REVIEW"
        else:
            value = "X3_BLOCK"
        return ExitEvaluation(
            disposition=ExitDisposition(
                value=value,
                outcome_authorized=authorized,
                c0_blocking=c0_blocking,
            ),
            x3_packet=SimpleNamespace(x3_code=x3_code, disposition_code=value),
            receipts=dict(receipts),
        )


__all__ = ["ExitDisposition", "ExitEvaluation", "ExitEvalPipeline"]
