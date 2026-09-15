"""Release Policy for modular resume generation.

Handles:
- Evaluation of release criteria against fail-closed policy.
- Qualification of Phase 1 direct lane outputs vs. Phase 0 synthetic runs.
- Derivation of decisive status and failure explanations.
"""

from __future__ import annotations

from typing import Any

from apps_rg.runtime.product_output_policy import product_fail_closed_runtime


class ReleasePolicy:
    """Encapsulates release gating, qualification verdicts, and fail-closed rules."""

    @staticmethod
    def is_product_fail_closed() -> bool:
        """Query if product fail-closed mode is active in the runtime."""
        return product_fail_closed_runtime()

    @classmethod
    def evaluate_phase1_release(
        cls,
        *,
        rollup_blob: dict[str, Any] | None,
        assembly_gates_ok: bool | None,
        lane_load_errors: dict[str, str],
        build_ok: bool,
        merged_err: str,
        recipe_lane_policy: dict[str, Any],
    ) -> tuple[str, str, str]:
        """Evaluate Phase 1 release qualification.

        Returns (decisive_status, failure_reason, pass_source).
        """
        if rollup_blob is None:
            decisive = "FAIL"
            failure = "phase1_incomplete_lane_artifacts"
            pass_source = ""
        elif assembly_gates_ok is False:
            decisive = "FAIL"
            failure = "deterministic_assembly_gates_failed"
            pass_source = ""
        elif lane_load_errors:
            decisive = "FAIL"
            failure = "lane_l2_load_errors:" + ";".join(
                f"{k}={v}" for k, v in sorted(lane_load_errors.items())
            )
            pass_source = ""
        elif build_ok:
            decisive = "PASS"
            failure = ""
            pass_source = "merged_rg_output_direct_lanes"
        elif assembly_gates_ok is True:
            decisive = "FAIL"
            failure = merged_err or "modular_rg_output_merge_failed"
            pass_source = "none"
        else:
            decisive = "FAIL"
            failure = "deterministic_assembly_failed_unknown"
            pass_source = ""

        # Fatal lane policy overrides PASS if any fatal lane failure was recorded
        if recipe_lane_policy.get("fatal_lane_failures"):
            decisive = "FAIL"
            failure = "fatal_lane_recipe_policy:" + "; ".join(
                f'{f["section_lane"]}:{f.get("decisive_reason_code") or ""}'
                for f in recipe_lane_policy["fatal_lane_failures"][:8]
            )
            pass_source = ""

        return decisive, failure, pass_source

    @classmethod
    def evaluate_phase0_synthetic_release(
        cls,
        *,
        phase0_blocked_on_product_fail_closed: bool,
        run_phase0_synthetic_assembly: bool,
        assembly_gates_ok: bool | None,
        validate_rg_output_fixture: bool,
        has_fixture_path: bool,
        fixture_ok: bool,
        fixture_err: str,
        fixture_candidate: dict[str, Any] | None,
    ) -> tuple[str, str, str, dict[str, Any] | None]:
        """Evaluate Phase 0 synthetic release qualification.

        Returns (decisive_status, failure_reason, pass_source, gen_resume).
        """
        gen_resume: dict[str, Any] | None = None
        pass_source = ""

        if phase0_blocked_on_product_fail_closed:
            return (
                "FAIL",
                "phase0_synthetic_not_permitted_on_product_fail_closed_path",
                "none",
                None,
            )

        if not run_phase0_synthetic_assembly:
            return (
                "FAIL",
                "phase0_synthetic_assembly_disabled",
                "",
                None,
            )

        if assembly_gates_ok is False:
            return (
                "FAIL",
                "deterministic_assembly_gates_failed",
                "",
                None,
            )

        if assembly_gates_ok is True:
            if validate_rg_output_fixture and has_fixture_path:
                if fixture_ok and fixture_candidate is not None:
                    return (
                        "PASS",
                        "",
                        "fixture_rg_output",
                        fixture_candidate,
                    )
                if cls.is_product_fail_closed():
                    decisive = "FAIL"
                else:
                    decisive = "PARTIAL"
                return decisive, fixture_err, "", None
            # Fixture validation not configured or fixture path missing
            failure = (
                "rg_output_fixture_validation_skipped"
                if not validate_rg_output_fixture
                else "rg_output_fixture_path_missing"
            )
            decisive = "FAIL" if cls.is_product_fail_closed() else "PARTIAL"
            return decisive, failure, "", None

        return (
            "FAIL",
            "deterministic_assembly_failed_unknown",
            "",
            None,
        )


__all__ = ["ReleasePolicy"]
