"""Resume Run Recovery Agent: bounded whole-run recovery for non-authorizing lanes."""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

RESUME_RUN_RECOVERY_RECEIPT_SCHEMA = "apps_rg_x3_lane_recovery_receipt_v1"
RESUME_RUN_RECOVERY_RECEIPT_FILENAME = "x3_lane_recovery_receipt.json"

AUTHORIZING_X3_CODES = frozenset({"X3_ALLOW", "X3D_ALLOW_FINISH", "X3A_ALLOW_REROUTE"})


def is_resume_run_recovery_enabled() -> bool:
    """Return whether Resume Run Recovery agent is globally enabled."""
    val = os.environ.get("APPS_RG_X3_RECOVERY_ENABLED", "1").strip().lower()
    return val in {"1", "true", "yes", "on"}


@dataclass
class ResumeRunRecoveryReceipt:
    schema_version: str = RESUME_RUN_RECOVERY_RECEIPT_SCHEMA
    generated_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    recovery_attempt: int = 1
    max_recovery_attempts: int = 1
    recovery_triggered: bool = False
    trigger_x3_disposition: str = ""
    failed_lanes_identified: list[str] = field(default_factory=list)
    lanes_re_dispatched: list[str] = field(default_factory=list)
    prior_exit_status: str = ""
    post_recovery_x3_disposition: str = ""
    post_recovery_exit_status: str = ""
    recovered_successfully: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    digest: str = ""

    def compute_digest(self) -> str:
        body = asdict(self)
        body.pop("digest", None)
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def persist(self, artifact_dir: Path | str) -> Path:
        self.digest = self.compute_digest()
        path = Path(artifact_dir) / RESUME_RUN_RECOVERY_RECEIPT_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        return path


class ResumeRunRecoveryAgent:
    """Agent that detects non-authorizing exit lanes and orchestrates surgical recovery.

    Adheres strictly to the adversarial debate consensus:
    - Bounded: Max 1 recovery pass. Second failure terminates closed.
    - Surgical: Re-dispatches only failing lanes, leaving banked passing lanes intact.
    - Preserves audit authority: Emits a fresh whole_run_exit_review_packet and
      x3_lane_recovery_receipt.json.
    """

    def __init__(
        self,
        artifact_dir: Path | str,
        repo_root: Path | str | None = None,
        max_attempts: int = 1,
        dispatch_fn: Callable[..., dict[str, Any]] | None = None,
        aggregate_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir).resolve()
        self.repo_root = Path(repo_root).resolve() if repo_root else self._find_repo(self.artifact_dir)
        self.max_attempts = max(1, max_attempts)
        self.dispatch_fn = dispatch_fn
        self.aggregate_fn = aggregate_fn

    @staticmethod
    def _find_repo(start: Path) -> Path:
        cur = start.resolve()
        for parent in [cur, *cur.parents]:
            if (parent / ".git").is_dir() or (parent / "pyproject.toml").is_file():
                return parent
        return cur

    def _prior_receipt_path(self) -> Path:
        return self.artifact_dir / RESUME_RUN_RECOVERY_RECEIPT_FILENAME

    def _execute_rca_diagnostic_loop(self, failing_lanes: list[str], whole_run_exit: dict[str, Any]) -> dict[str, Any]:
        """O4: Forensic RCA Re-Planner (A2A Loop).
        
        Agent A (Forensic Diagnostic): Dissects root cause.
        Agent B (Strategy Re-Planner): Generates targeted dispatch directives.
        """
        # Turn 1a: Diagnostic Agent
        diagnostic_findings = self._call_diagnostic_agent(failing_lanes, whole_run_exit)
        
        # Turn 1b: Strategy Re-Planner
        directives = self._call_strategy_re_planner(diagnostic_findings)
        return directives

    def _call_diagnostic_agent(self, lanes: list[str], exit_data: dict[str, Any]) -> dict[str, Any]:
        """Simulate Agent A: Forensic Diagnostic."""
        return {
            "root_cause_identified": "EVIDENCE_DEFICIT",
            "failing_lanes_diagnostics": {lane: "Failed X2 density floor" for lane in lanes}
        }

    def _call_strategy_re_planner(self, diagnostics: dict[str, Any]) -> dict[str, Any]:
        """Simulate Agent B: Strategy Re-Planner."""
        return {
            "remediation_strategy": "Increase variance and relax temperature to 0.8 to force broader C0 fact exploration.",
            "lane_overrides": {lane: {"temperature": 0.8, "force_new_seed": True} for lane in diagnostics.get("failing_lanes_diagnostics", {})}
        }

    def identify_failing_lanes(
        self,
        whole_run_exit: Mapping[str, Any],
        exec_summary_block: Mapping[str, Any] | None = None,
    ) -> list[str]:
        """Identify which lanes failed or contributed to the non-authorizing disposition."""
        failing: set[str] = set()

        signals = whole_run_exit.get("signals")
        if isinstance(signals, Mapping):
            for key in (
                "core_x3_non_authorizing_lanes",
                "authoritative_lane_contract_failed_lanes",
                "final_materialized_acceptance_failed_lanes",
                "judge_execution_incomplete_lanes",
                "l2_handoff_failed_lanes",
                "l2_spine_failed_lanes",
            ):
                lanes = signals.get(key)
                if isinstance(lanes, (list, tuple)):
                    for lane in lanes:
                        if isinstance(lane, str) and lane.strip():
                            failing.add(lane.strip())

            lane_rows = signals.get("lane_rows")
            if isinstance(lane_rows, list):
                for row in lane_rows:
                    if isinstance(row, Mapping):
                        lane = str(row.get("lane") or "").strip()
                        if not lane:
                            continue
                        x3_code = str(row.get("x3_code") or "").strip()
                        x2_failed = int(row.get("x2_failed") or 0)
                        prod_status = str(row.get("product_quality_status") or "").strip().upper()
                        if x3_code and x3_code not in AUTHORIZING_X3_CODES:
                            failing.add(lane)
                        elif x2_failed > 0:
                            failing.add(lane)
                        elif prod_status not in {"", "PASS"}:
                            failing.add(lane)

        agg = whole_run_exit.get("aggregated_from_lane_x3")
        if isinstance(agg, list):
            for entry in agg:
                if isinstance(entry, Mapping):
                    lane = str(entry.get("lane") or "").strip()
                    x3 = str(entry.get("x3_code") or "").strip()
                    if lane and x3 and x3 not in AUTHORIZING_X3_CODES:
                        failing.add(lane)

        if exec_summary_block and bool(exec_summary_block.get("blocked")):
            failing.add("executive_summary")

        # Canonical ordering
        from apps_rg.l2_recipe.modular_resume_generation import GENERATED_LANES
        return [lane for lane in GENERATED_LANES if lane in failing]

    def can_attempt_recovery(
        self,
        whole_run_exit: Mapping[str, Any],
        exec_summary_block: Mapping[str, Any] | None = None,
    ) -> bool:
        """Evaluate if bounded recovery can proceed."""
        if not is_resume_run_recovery_enabled():
            logger.info("Resume run recovery agent is disabled via APPS_RG_X3_RECOVERY_ENABLED.")
            return False

        receipt_path = self._prior_receipt_path()
        if receipt_path.is_file():
            try:
                prior = json.loads(receipt_path.read_text(encoding="utf-8"))
                attempt = int(prior.get("recovery_attempt") or 1)
                if attempt >= self.max_attempts:
                    logger.info("Resume run recovery exhausted (%s/%s attempts executed).", attempt, self.max_attempts)
                    return False
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                return False

        failing = self.identify_failing_lanes(whole_run_exit, exec_summary_block)
        if not failing:
            logger.info("No failing lanes identified for recovery.")
            return False

        return True

    def attempt_recovery(
        self,
        *,
        whole_run_exit: dict[str, Any],
        whole_run_exit_identity: Mapping[str, Any],
        raw_request: Mapping[str, Any],
        validated_request: Any = None,
    ) -> tuple[dict[str, Any], str, bool]:
        """Perform surgical re-dispatch of failing lanes and refresh the exit review packet.

        Returns:
            (updated_whole_run_exit, updated_effective_x3, updated_exec_summary_blocked)
        """
        from apps_rg.runtime.executive_summary_certification import (
            EXECUTIVE_SUMMARY_JUDGE_REVIEW_X3,
            executive_summary_certification_block,
        )
        from apps_rg.runtime.whole_run_exit import (
            emit_whole_run_exit_review_packet,
        )

        exec_summary_block = executive_summary_certification_block(self.artifact_dir)
        exec_summary_blocked = bool(exec_summary_block.get("blocked"))
        failing_lanes = self.identify_failing_lanes(whole_run_exit, exec_summary_block)
        prior_x3 = str(whole_run_exit.get("x3_disposition") or "X3A_DENY_REROUTE")
        prior_status = str(whole_run_exit.get("status") or "BLOCKED")

        receipt = ResumeRunRecoveryReceipt(
            recovery_triggered=True,
            trigger_x3_disposition=prior_x3,
            failed_lanes_identified=failing_lanes,
            prior_exit_status=prior_status,
            max_recovery_attempts=self.max_attempts,
        )

        logger.info(
            "ResumeRunRecoveryAgent: Initiating recovery attempt for failing lanes: %s",
            failing_lanes,
        )

        dispatch_success = False
        details: dict[str, Any] = {}

        try:
            from apps_rg.runtime.orchestration.patch_run import (
                build_patch_plan,
                execute_patch_run,
            )

            # O4: Forensic RCA Re-Planner (A2A Loop)
            # Turn 1: Diagnostic -> Strategy Re-Planner
            recovery_directives = self._execute_rca_diagnostic_loop(failing_lanes, whole_run_exit)
            details["rca_diagnostic_loop"] = recovery_directives

            target_failing = failing_lanes
            try:
                from apps_rg.runtime.orchestration.patch_run import classify_all_lane_states
                from apps_rg.runtime.runtime_proof_layout import find_repo_root

                repo = find_repo_root(self.artifact_dir)
                lane_states = classify_all_lane_states(repo, self.artifact_dir)
                target_failing = [
                    lane for lane in failing_lanes
                    if not bool(lane_states.get(lane, {}).get("authorized"))
                ]
            except Exception:
                pass

            if not target_failing:
                logger.info("ResumeRunRecoveryAgent: No unauthorized failing lanes to re-dispatch.")
                return whole_run_exit, prior_x3, exec_summary_blocked

            plan = build_patch_plan(
                self.artifact_dir,
                sections_csv=",".join(target_failing),
            )
            receipt.lanes_re_dispatched = list(plan.target_lanes)

            patch_result = execute_patch_run(
                plan,
                dispatch_fn=self.dispatch_fn,
                aggregate_fn=self.aggregate_fn,
            )
            details["patch_result"] = {
                "exit_code": patch_result.get("exit_code"),
                "target_lanes": patch_result.get("target_lanes"),
            }
            dispatch_success = patch_result.get("exit_code") == 0
        except Exception as exc:
            logger.warning("ResumeRunRecoveryAgent patch dispatch error: %s", exc)
            details["error"] = f"{type(exc).__name__}:{exc}"

        # Re-derive whole_run_exit packet
        try:
            updated_whole_run_exit = emit_whole_run_exit_review_packet(
                artifact_dir=self.artifact_dir,
                identity=whole_run_exit_identity,
            )
        except Exception as exc:
            logger.error("Failed to re-emit whole run exit packet after recovery: %s", exc)
            updated_whole_run_exit = dict(whole_run_exit)
            details["exit_reemit_error"] = str(exc)

        updated_exec_summary_block = executive_summary_certification_block(self.artifact_dir)
        updated_exec_summary_blocked = bool(updated_exec_summary_block.get("blocked"))
        updated_effective_x3 = (
            str(updated_exec_summary_block.get("x3_disposition") or EXECUTIVE_SUMMARY_JUDGE_REVIEW_X3)
            if updated_exec_summary_blocked
            else str(updated_whole_run_exit.get("x3_disposition") or "X3A_DENY_REROUTE")
        )
        post_status = str(updated_whole_run_exit.get("status") or "BLOCKED")

        from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import _product_x3_authorizes
        recovered = (
            not updated_exec_summary_blocked
            and _product_x3_authorizes(updated_effective_x3)
            and post_status == "PASS"
        )

        receipt.post_recovery_x3_disposition = updated_effective_x3
        receipt.post_recovery_exit_status = post_status
        receipt.recovered_successfully = recovered
        receipt.details = details
        receipt.persist(self.artifact_dir)

        logger.info(
            "ResumeRunRecoveryAgent: Recovery finished. Disposition: %s -> %s, Recovered: %s",
            prior_x3,
            updated_effective_x3,
            recovered,
        )

        return updated_whole_run_exit, updated_effective_x3, updated_exec_summary_blocked


# Backward compatibility aliases
X3LaneRecoveryAgent = ResumeRunRecoveryAgent
X3RecoveryReceipt = ResumeRunRecoveryReceipt
is_x3_recovery_enabled = is_resume_run_recovery_enabled
X3_RECOVERY_RECEIPT_SCHEMA = RESUME_RUN_RECOVERY_RECEIPT_SCHEMA
X3_RECOVERY_RECEIPT_FILENAME = RESUME_RUN_RECOVERY_RECEIPT_FILENAME

__all__ = [
    "ResumeRunRecoveryAgent",
    "ResumeRunRecoveryReceipt",
    "is_resume_run_recovery_enabled",
    "RESUME_RUN_RECOVERY_RECEIPT_SCHEMA",
    "RESUME_RUN_RECOVERY_RECEIPT_FILENAME",
    "AUTHORIZING_X3_CODES",
    # Aliases
    "X3LaneRecoveryAgent",
    "X3RecoveryReceipt",
    "is_x3_recovery_enabled",
    "X3_RECOVERY_RECEIPT_SCHEMA",
    "X3_RECOVERY_RECEIPT_FILENAME",
]
