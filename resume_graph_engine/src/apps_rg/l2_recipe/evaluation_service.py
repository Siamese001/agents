"""Evaluation Service for modular recipe generation.

Handles:
- Classification of pre-run blockers and dispatch status.
- JSON Schema and fixture candidate validation.
- Summarization of lane recipe policy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_rg.l2_recipe.modular_lane_recipe_policy import summarize_modular_lane_recipe_policy
from apps_rg.l2_recipe.rg_output_jsonschema_validate import validate_rg_output_object


class EvaluationService:
    """Encapsulates evaluation, blocker classification, and policy assessment."""

    @staticmethod
    def derive_pre_run_blocker(dispatch: dict[str, Any] | None) -> str:
        """Classify a lane's pre-run blocker from its dispatch_result, most-specific first.

        A lane that ran to an X3 verdict but failed the product bar (e.g. competencies
        X3_BLOCK) must NOT be mislabeled ``LANE_DISPATCH_EXIT_ERROR`` -- it executed.
        Precedence: executed-to-X3 > prior-abort > transport fault > dispatch exit error >
        no run dir (apps_rg E2E remediation, E2E-05).
        """
        res = dispatch if isinstance(dispatch, dict) else {}
        x3 = str(res.get("x3_disposition") or "").strip()
        if x3:
            return f"EXECUTED_{x3}"
        if res.get("prior_abort"):
            return "MISSING_NOT_ATTEMPTED"
        fault = str(res.get("fault") or "").strip()
        if fault:
            return fault
        if str(res.get("exit_status") or "").lower() == "error":
            return "LANE_DISPATCH_EXIT_ERROR"
        return "PHASE1_NO_RUN_DIR"

    @staticmethod
    def phase1_lane_dispatch_status(result: dict[str, Any] | None) -> str:
        """Summarize in-process lane dispatch for ``phase1_lane_inventory``."""
        res = result if isinstance(result, dict) else {}
        fault = str(res.get("fault") or "").strip()
        exit_st = str(res.get("exit_status") or "").strip().lower()
        if fault == "temperature_range":
            return "exit_2"
        if fault:
            return f"dispatch_error:{fault}"
        if exit_st == "error":
            return "dispatch_error:lane_exit_error"
        if exit_st == "success":
            return "ok"
        return f"dispatch_status:{exit_st or 'unknown'}"

    @staticmethod
    def validate_rg_output_fixture(
        fixture_path: Path | None,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Validate an optional RG output fixture candidate against the JSON schema."""
        if fixture_path is None:
            return False, "no_fixture_provided", None
        if not fixture_path.is_file():
            return False, "rg_output_fixture_path_not_found", None
        try:
            raw_txt = fixture_path.read_text(encoding="utf-8")
            candidate = json.loads(raw_txt)
            ok, err = validate_rg_output_object(candidate)
            return ok, err, candidate
        except (OSError, json.JSONDecodeError) as exc:
            return False, f"fixture_read_error:{exc}", None

    @staticmethod
    def summarize_recipe_lane_policy(
        section_call_records: list[dict[str, Any]],
        *,
        enforce_product_lane_requirements: bool,
    ) -> dict[str, Any]:
        """Evaluate and summarize recipe lane policy across recorded section calls."""
        return summarize_modular_lane_recipe_policy(
            section_call_records,
            enforce_product_lane_requirements=enforce_product_lane_requirements,
        )


__all__ = ["EvaluationService"]
