#!/usr/bin/env python3
"""HITL Governance and Ambiguity Gating Engine.

Enforces:
1. Atomic HITL decision presentation (one at a time, interactive options).
2. Calibrated confidence scoring (tiers, percentages, floats).
3. 25% Ambiguity Margin Rule:
   - Delta = c_top - c_second
   - When Delta >= 25%: Decisively resolved; agent proceeds autonomously under audit receipt.
   - When Delta < 25%: Genuinely ambiguous; agent surfaces atomic question to operator.
4. Synthetic stop-hook auto-approval rejection.
"""
from __future__ import annotations

import re
from typing import Any, Sequence

SYNTHETIC_APPROVAL_MARKERS = (
    "<system_message>",
    "stop hook",
    "stop_hook",
    "automatically approved the artifact",
    "through their review policy",
    "proceed to execution",
    "autonomous policy",
    "pre-approved",
)


def parse_confidence_score(val: Any) -> float:
    """Robustly parse confidence score into a 0.0 - 1.0 float."""
    if isinstance(val, (int, float)):
        num = float(val)
        return num / 100.0 if num > 1.0 else max(0.0, min(1.0, num))

    if isinstance(val, dict):
        if "confidence_score" in val:
            return parse_confidence_score(val["confidence_score"])
        if "confidence" in val:
            return parse_confidence_score(val["confidence"])
        if "confidence_level" in val:
            return parse_confidence_score(val["confidence_level"])

    if isinstance(val, str):
        cleaned = val.strip()
        # Check percentage string e.g. "85%", "95.5%"
        pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", cleaned)
        if pct_match:
            return float(pct_match.group(1)) / 100.0

        # Check explicit tier names
        upper = cleaned.upper()
        if "HIGH" in upper:
            return 0.90
        if "MEDIUM" in upper:
            return 0.60
        if "LOW" in upper:
            return 0.25

        # Check raw number in string
        num_match = re.search(r"\b(0(?:\.\d+)?|1(?:\.0+)?)\b", cleaned)
        if num_match:
            return float(num_match.group(1))

    return 0.50


def evaluate_hitl_surfacing_gate(
    options: Sequence[Any],
    margin_threshold: float = 0.25,
) -> dict[str, Any]:
    """Evaluate candidate HITL options against the 25% ambiguity margin rule.

    Returns:
        Structured evaluation dict indicating whether to surface HITL or proceed autonomously.
    """
    if not options:
        return {
            "should_surface": False,
            "margin": 0.0,
            "margin_threshold": margin_threshold,
            "top_option": None,
            "top_score": 0.0,
            "second_score": 0.0,
            "action": "EMPTY_OPTIONS",
            "reason": "No options provided to evaluate.",
        }

    scored: list[tuple[float, Any]] = []
    for opt in options:
        score = parse_confidence_score(opt)
        scored.append((score, opt))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_opt = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = round(top_score - second_score, 4)

    should_surface = margin < margin_threshold
    action = "SURFACE_HITL_ATOMIC" if should_surface else "PROCEED_AUTONOMOUSLY"

    if should_surface:
        reason = (
            f"Margin Delta = {margin:.2%} is strictly under the 25% threshold "
            f"({margin_threshold:.0%}): genuine ambiguity requires operator input."
        )
    else:
        reason = (
            f"Margin Delta = {margin:.2%} meets or exceeds the 25% threshold "
            f"({margin_threshold:.0%}): proceed autonomously with top option."
        )

    return {
        "should_surface": should_surface,
        "margin": margin,
        "margin_threshold": margin_threshold,
        "top_option": top_opt,
        "top_score": top_score,
        "second_score": second_score,
        "action": action,
        "reason": reason,
    }


def validate_hitl_presentation(payload: Any) -> list[str]:
    """Validate that a candidate HITL payload adheres to atomic presentation controls."""
    errors: list[str] = []

    # 1. Reject bulk / batched decisions
    if isinstance(payload, list) and len(payload) > 1:
        errors.append(
            "HITL_VIOLATION_BULK_DECISION: Presenting multiple decisions simultaneously violates atomic presentation. Present one at a time."
        )
        return errors

    if isinstance(payload, dict) and "questions" in payload:
        if isinstance(payload["questions"], list) and len(payload["questions"]) > 1:
            errors.append(
                "HITL_VIOLATION_BULK_DECISION: Batched questions detected. Present strictly one decision at a time."
            )
            return errors

    item = payload[0] if isinstance(payload, list) and len(payload) == 1 else payload

    if not isinstance(item, dict):
        errors.append("HITL_VIOLATION_INVALID_PAYLOAD: Decision payload must be a dictionary.")
        return errors

    options = item.get("options", [])
    if not isinstance(options, (list, tuple)) or len(options) < 2:
        errors.append(
            "HITL_VIOLATION_INSUFFICIENT_OPTIONS: Decision must provide at least 2 distinct options."
        )
        return errors

    for idx, opt in enumerate(options):
        has_conf = False
        if isinstance(opt, dict):
            has_conf = any(k in opt for k in ("confidence", "confidence_level", "confidence_score"))
        elif isinstance(opt, str):
            has_conf = any(k in opt.lower() for k in ("confidence", "conf:", "high", "medium", "low", "%"))

        if not has_conf:
            errors.append(
                f"HITL_VIOLATION_MISSING_CONFIDENCE: Option {idx + 1} lacks an explicit calibrated confidence level."
            )

    return errors


def validate_approval_origin(text: str) -> tuple[bool, str]:
    """Validate whether an approval message originates from an authentic human operator."""
    lower = text.lower()
    for marker in SYNTHETIC_APPROVAL_MARKERS:
        if marker in lower:
            return False, f"SYNTHETIC_APPROVAL_DETECTED: Matched synthetic marker '{marker}'."

    return True, "AUTHENTIC_HUMAN_APPROVAL"


PLAN_ONLY_TRIGGERS = (
    "plan only",
    "no implement",
    "plan only stop",
    "do not implement",
    "stop before executing",
)


def validate_plan_only_firewall(
    user_prompt: str,
    artifact_metadata: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Validate that when user requests plan-only, RequestFeedback is false to prevent auto-proceed triggers."""
    lower = user_prompt.lower()
    is_plan_only = any(t in lower for t in PLAN_ONLY_TRIGGERS)
    if not is_plan_only:
        return True, "STANDARD_EXECUTION_ALLOWED"

    if artifact_metadata and artifact_metadata.get("RequestFeedback") is True:
        return False, "PLAN_ONLY_FIREWALL_VIOLATION: User requested plan-only mode; RequestFeedback must be false to prevent auto-execution."

    return True, "PLAN_ONLY_FIREWALL_SATISFIED"

