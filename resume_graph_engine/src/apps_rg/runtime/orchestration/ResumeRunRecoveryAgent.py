"""Resume Run Recovery Agent: bounded whole-run recovery for non-authorizing lanes."""

from __future__ import annotations

from apps_rg.config.runtime_env import get_runtime_env_str
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
    val = get_runtime_env_str("APPS_RG_X3_RECOVERY_ENABLED", "1").strip().lower()
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

    def _load_assembly_coherence_failures(self) -> tuple[set[str], dict[str, str]]:
        """Inspect final_resume_assembly X2, review policy, and 12th-stage coherence outputs for implicated lanes."""
        from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES

        implicated: set[str] = set()
        notes: dict[str, str] = {}
        asm_dir = self.artifact_dir / "modular_r4" / "final_resume_assembly"
        if not asm_dir.is_dir():
            return implicated, notes

        valid_lanes = set(GENERATED_LANES)
        emp_aliases = {
            "executive_summary": ("executive summary", "executive_summary", "summary", "target_mandate", "jd_resonance", "unsupported_jd_proof"),
            "headline": ("headline",),
            "competencies": ("competencies", "core competencies", "competenc", "credential"),
            "slalom_narrative": ("slalom narrative", "slalom_narrative"),
            "slalom_bullets": ("slalom bullet", "slalom_bullets"),
            "unify_narrative": ("unify narrative", "unify_narrative"),
            "unify_bullets": ("unify bullet", "unify_bullets"),
            "ibm_narrative": ("ibm narrative", "ibm_narrative"),
            "ibm_bullets": ("ibm bullet", "ibm_bullets"),
            "insurtech_narrative": ("insurtech narrative", "insurtech_narrative"),
            "insurtech_bullets": ("insurtech bullet", "insurtech_bullets"),
        }

        def _match_aliases(text_blob: str) -> list[str]:
            lowered = text_blob.lower()
            return [ln for ln, toks in emp_aliases.items() if any(tok in lowered for tok in toks)]

        x2_path = asm_dir / "final_resume_x2_gate_outputs.json"
        if x2_path.is_file():
            try:
                x2_doc = json.loads(x2_path.read_text(encoding="utf-8"))
                gates = x2_doc.get("gates") if isinstance(x2_doc, Mapping) else x2_doc
                for g in gates if isinstance(gates, list) else []:
                    if not isinstance(g, Mapping) or bool(g.get("pass", True)):
                        continue
                    gid = str(g.get("gate_id") or "")
                    reason = str(g.get("failure_reason") or gid)
                    obs = g.get("observed_value")
                    obs_blob = json.dumps(obs, default=str) if obs is not None else ""
                    matched = [
                        ln
                        for ln in GENERATED_LANES
                        if ln in gid or ln in reason or ln in obs_blob
                    ]
                    if gid == "x2_full_resume_llm_coherence_aggregation" and isinstance(obs, Mapping):
                        for nl in obs.get("non_allow_lanes") or []:
                            nl_s = str(nl).strip()
                            if nl_s in valid_lanes and nl_s not in matched:
                                matched.append(nl_s)
                        blockers_blob = json.dumps(obs.get("blockers") or [], default=str)
                        for ln in _match_aliases(blockers_blob):
                            if ln not in matched:
                                matched.append(ln)
                    for ln in matched:
                        implicated.add(ln)
                        notes.setdefault(ln, f"Failed final_resume X2 gate {gid}: {reason[:160]}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        cross_path = asm_dir / "cross_section_x2_gate_outputs.json"
        if cross_path.is_file():
            try:
                cross_doc = json.loads(cross_path.read_text(encoding="utf-8"))
                gates = cross_doc.get("gates") if isinstance(cross_doc, Mapping) else []
                for g in gates if isinstance(gates, list) else []:
                    if not isinstance(g, Mapping):
                        continue
                    verdict = str(g.get("verdict") or "").strip().upper()
                    failed_cross = verdict in {"FAIL", "UNKNOWN"} or (not verdict and g.get("pass") is False)
                    if not failed_cross:
                        continue
                    gid = str(g.get("gate_id") or "")
                    reason = str(g.get("decisive_reason") or g.get("failure_reason") or gid)
                    obs_blob = json.dumps(g.get("observed"), default=str) if g.get("observed") is not None else ""
                    for ln in GENERATED_LANES:
                        if ln in gid or ln in reason or ln in obs_blob:
                            implicated.add(ln)
                            notes.setdefault(ln, f"Failed cross-section X2 gate {gid}: {reason[:160]}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        rp_path = asm_dir / "review_lane_policy.json"
        if rp_path.is_file():
            try:
                rp_doc = json.loads(rp_path.read_text(encoding="utf-8"))
                if isinstance(rp_doc, Mapping):
                    rp_sum = rp_doc.get("summary") if isinstance(rp_doc.get("summary"), Mapping) else {}
                    for bucket_key in ("review_lanes", "blocked_lanes", "mock_plumbing_lanes"):
                        for ln in rp_sum.get(bucket_key) or []:
                            ln_s = str(ln).strip()
                            if ln_s in valid_lanes:
                                implicated.add(ln_s)
                                notes.setdefault(ln_s, f"review_lane_policy {bucket_key}")
                    for row in rp_doc.get("per_lane") or []:
                        if not isinstance(row, Mapping):
                            continue
                        ln_s = str(row.get("lane") or "").strip()
                        disp = str(row.get("disposition_class") or "").strip()
                        x3c = str(row.get("x3_code") or "").strip()
                        if ln_s in valid_lanes and (disp != "ALLOW" or x3c != "X3_ALLOW"):
                            implicated.add(ln_s)
                            notes.setdefault(ln_s, f"review_lane_policy mismatch ({disp}:{x3c})")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        final_path = asm_dir / "final_resume.json"
        if final_path.is_file():
            try:
                final_doc = json.loads(final_path.read_text(encoding="utf-8"))
                for sec in final_doc.get("sections") or []:
                    if not isinstance(sec, Mapping):
                        continue
                    ln_s = str(sec.get("section_id") or "").strip()
                    snap = sec.get("l2_output_snapshot")
                    if ln_s in valid_lanes and isinstance(snap, Mapping) and snap.get("assembly_gap") is True:
                        implicated.add(ln_s)
                        reason_gap = str(snap.get("assembly_gap_reason") or "assembly_gap")
                        notes.setdefault(ln_s, f"Assembly gap placeholder: {reason_gap[:160]}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        coh_triggered = False
        coh_findings: list[str] = []
        for coh_name in ("full_resume_llm_coherence_review.json", "x1d_full_resume_judge_outputs.json"):
            coh_path = asm_dir / coh_name
            if not coh_path.is_file():
                continue
            try:
                coh_doc = json.loads(coh_path.read_text(encoding="utf-8"))
                if not isinstance(coh_doc, Mapping):
                    continue
                agg = coh_doc.get("aggregation") if isinstance(coh_doc.get("aggregation"), Mapping) else {}
                coh_pass = coh_doc.get("full_resume_coherence_pass")
                if coh_pass is None:
                    coh_pass = agg.get("full_resume_coherence_pass")
                quorum_met = coh_doc.get("quorum_met")
                if quorum_met is None:
                    quorum_met = agg.get("quorum_met")
                decisive = str(coh_doc.get("decisive_reason") or agg.get("decisive_reason") or "").strip()
                is_fail = (
                    coh_pass is False
                    or quorum_met is False
                    or decisive in {
                        "quorum_not_met",
                        "judge_blockers",
                        "deterministic_blocker",
                        "skipped_upstream_lanes_not_x3_allow",
                    }
                )
                if not is_fail:
                    continue
                coh_triggered = True
                for ln in (
                    list(coh_doc.get("non_allow_lanes") or [])
                    + list(agg.get("non_allow_lanes") or [])
                    + list(coh_doc.get("review_lanes") or [])
                ):
                    ln_s = str(ln).strip()
                    if ln_s in valid_lanes:
                        implicated.add(ln_s)
                        notes.setdefault(ln_s, f"12th-stage coherence skipped/blocked ({decisive or 'non_allow'})")
                judges_raw = coh_doc.get("judges")
                if not isinstance(judges_raw, list):
                    judges_raw = coh_doc.get("judge_verdicts")
                judges = judges_raw if isinstance(judges_raw, list) else []
                for j in judges:
                    if not isinstance(j, Mapping):
                        continue
                    j_status = str(j.get("provider_status") or "").upper()
                    j_failed = (
                        not bool(j.get("pass", True))
                        or bool(j.get("decisive_failure"))
                        or j_status.endswith(("FAIL", "BLOCKED", "ERROR"))
                        or bool(j.get("exact_provider_error"))
                    )
                    if not j_failed:
                        continue
                    for field_key in (
                        "findings",
                        "remediation_suggestions",
                        "unsupported_claims",
                        "rationale",
                        "exact_provider_error",
                        "decisive_failure_reason",
                    ):
                        val = j.get(field_key)
                        if isinstance(val, list):
                            coh_findings.extend(str(item) for item in val if str(item).strip())
                        elif isinstance(val, str) and val.strip():
                            coh_findings.append(val.strip())
                for blk in list(coh_doc.get("blockers") or []) + list(agg.get("blockers") or []):
                    if str(blk).strip():
                        coh_findings.append(str(blk).strip())
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        if coh_triggered:
            blob = " ".join(coh_findings)
            coh_matched = _match_aliases(blob) if blob else []
            if not coh_matched and not implicated:
                coh_matched = ["executive_summary"]
            critique = "; ".join(coh_findings[:4]) or "12th-stage full_resume_llm_coherence failed"
            for ln in coh_matched:
                implicated.add(ln)
                notes.setdefault(ln, f"12th-stage coherence critique: {critique[:200]}")

        return implicated, notes

    def _call_diagnostic_agent(self, lanes: list[str], exit_data: dict[str, Any]) -> dict[str, Any]:
        """Execute Agent A: Forensic Diagnostic over whole-run exit signals and lane rows."""
        signals = exit_data.get("signals") if isinstance(exit_data.get("signals"), Mapping) else {}
        lane_rows = signals.get("lane_rows") if isinstance(signals.get("lane_rows"), list) else []
        row_by_lane = {
            str(r.get("lane") or "").strip(): r
            for r in lane_rows
            if isinstance(r, Mapping) and str(r.get("lane") or "").strip()
        }
        _asm_lanes, asm_notes = self._load_assembly_coherence_failures()
        exec_cert_note = ""
        if "executive_summary" in lanes:
            try:
                from apps_rg.runtime.executive_summary_certification import (
                    executive_summary_certification_block,
                )

                cert_block = executive_summary_certification_block(self.artifact_dir)
                if isinstance(cert_block, Mapping) and cert_block.get("blocked"):
                    judges = [str(j) for j in (cert_block.get("blocking_judge_ids") or []) if str(j).strip()]
                    pub = str(cert_block.get("publish_disposition") or "").strip()
                    exec_cert_note = (
                        f"Executive summary judge certification blocked"
                        f"{f' (publish_disposition={pub})' if pub else ''}"
                        f"{f': blocking judges {chr(44).join(judges)}' if judges else ''}"
                    )
            except (ImportError, OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        failing_diagnostics: dict[str, str] = {}
        root_causes: set[str] = set()
        for lane in lanes:
            row = row_by_lane.get(lane, {})
            x2_failed = int(row.get("x2_failed") or 0)
            x3_code = str(row.get("x3_code") or "X3A_DENY_REROUTE")
            if x2_failed > 0:
                failing_diagnostics[lane] = f"Failed X2 deterministic gate ({x2_failed} violations)"
                root_causes.add("X2_SHAPE_OR_GROUNDING_VIOLATION")
            elif lane in asm_notes:
                failing_diagnostics[lane] = asm_notes[lane]
                root_causes.add("WHOLE_RESUME_COHERENCE_OR_CROSS_SECTION_VIOLATION")
            elif lane == "executive_summary" and exec_cert_note:
                failing_diagnostics[lane] = exec_cert_note
                root_causes.add("EXECUTIVE_SUMMARY_JUDGE_CERTIFICATION_BLOCK")
            else:
                failing_diagnostics[lane] = f"Non-authorizing X3 disposition ({x3_code})"
                root_causes.add("EVIDENCE_DEFICIT")

        return {
            "root_cause_identified": sorted(root_causes)[0] if root_causes else "EVIDENCE_DEFICIT",
            "failing_lanes_diagnostics": failing_diagnostics,
        }

    def _call_strategy_re_planner(self, diagnostics: dict[str, Any]) -> dict[str, Any]:
        """Execute Agent B: Strategy Re-Planner producing lane-scoped dispatch overrides."""
        # Respect per-section recipe temperature ranges (ibm_narrative: 0.30-0.45;
        # executive_summary, unify_bullets, unify_narrative, ibm_bullets: 0.35-0.55)
        # so recovery dispatch never crashes with SECTION_SCOPE_RECIPE_FAILED::temperature_range.
        lane_diag = diagnostics.get("failing_lanes_diagnostics") or {}
        lane_overrides: dict[str, dict[str, Any]] = {}
        for lane, diag_msg in lane_diag.items():
            is_x2 = "X2" in str(diag_msg)
            if lane == "ibm_narrative":
                temp = 0.35 if is_x2 else 0.45
            else:
                temp = 0.40 if is_x2 else 0.50
            lane_overrides[lane] = {
                "temperature": temp,
                "force_new_seed": True,
                "reasoning_effort": "low",
                "diagnostic_focus": str(diag_msg),
            }
        return {
            "remediation_strategy": "Surgical lane re-dispatch with bounded temperature and seed diversification.",
            "lane_overrides": lane_overrides,
        }

    def identify_failing_lanes(
        self,
        whole_run_exit: Mapping[str, Any],
        exec_summary_block: Mapping[str, Any] | None = None,
    ) -> list[str]:
        """Identify which lanes failed or contributed to the non-authorizing disposition."""
        from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES

        failing: set[str] = set()
        valid_lanes = set(GENERATED_LANES)

        signals = whole_run_exit.get("signals")
        final_asm_failed: list[Any] = []
        final_out_failed: list[Any] = []
        if isinstance(signals, Mapping):
            for key in (
                "core_x3_non_authorizing_lanes",
                "authoritative_lane_contract_failed_lanes",
                "final_materialized_acceptance_failed_lanes",
                "judge_execution_incomplete_lanes",
                "l2_handoff_failed_lanes",
                "l2_spine_failed_lanes",
                "mirror_authority_violation_lanes",
            ):
                lanes = signals.get(key)
                if isinstance(lanes, (list, tuple)):
                    for lane in lanes:
                        if isinstance(lane, str) and lane.strip():
                            failing.add(lane.strip())

            for row_key in ("lane_rows", "lane_authority_rows"):
                lane_rows = signals.get(row_key)
                if isinstance(lane_rows, list):
                    for row in lane_rows:
                        if isinstance(row, Mapping):
                            lane = str(row.get("lane") or "").strip()
                            if not lane:
                                continue
                            x3_code = str(
                                row.get("x3_code") or row.get("authoritative_x3_code") or ""
                            ).strip()
                            x2_failed = int(row.get("x2_failed") or 0)
                            prod_status = str(row.get("product_quality_status") or "").strip().upper()
                            if row.get("authorized") is False:
                                failing.add(lane)
                            elif x3_code and x3_code not in AUTHORIZING_X3_CODES:
                                failing.add(lane)
                            elif x2_failed > 0:
                                failing.add(lane)
                            elif prod_status not in {"", "PASS"}:
                                failing.add(lane)

            raw_asm_failed = signals.get("final_assembly_authority_failed_checks")
            if isinstance(raw_asm_failed, (list, tuple)):
                final_asm_failed = [str(c).strip() for c in raw_asm_failed if str(c).strip()]
            raw_out_failed = signals.get("final_resume_output_failed_gate_ids")
            if isinstance(raw_out_failed, (list, tuple)):
                final_out_failed = [str(c).strip() for c in raw_out_failed if str(c).strip()]

        agg = whole_run_exit.get("aggregated_from_lane_x3")
        if isinstance(agg, list):
            for entry in agg:
                if isinstance(entry, Mapping):
                    lane = str(entry.get("lane") or "").strip()
                    x3 = str(entry.get("x3_code") or "").strip()
                    if lane and x3 and x3 not in AUTHORIZING_X3_CODES:
                        failing.add(lane)

        resolved_exec_block = exec_summary_block
        if resolved_exec_block is None:
            embedded_block = whole_run_exit.get("executive_summary_certification_block")
            if isinstance(embedded_block, Mapping):
                resolved_exec_block = embedded_block
            else:
                try:
                    from apps_rg.runtime.executive_summary_certification import (
                        executive_summary_certification_block,
                    )

                    resolved_exec_block = executive_summary_certification_block(self.artifact_dir)
                except (ImportError, OSError, ValueError, TypeError, json.JSONDecodeError):
                    resolved_exec_block = None

        if resolved_exec_block and bool(resolved_exec_block.get("blocked")):
            failing.add("executive_summary")

        exit_x3 = str(whole_run_exit.get("x3_disposition") or "").strip()
        exit_status = str(whole_run_exit.get("status") or "").strip().upper()
        signals_map = signals if isinstance(signals, Mapping) else {}
        x1d_overall = str(signals_map.get("x1d_overall") or "").strip().upper()
        assembly_or_coherence_flagged = (
            (exit_x3 and exit_x3 not in AUTHORIZING_X3_CODES)
            or (exit_status and exit_status != "PASS")
            or bool(final_asm_failed)
            or bool(final_out_failed)
            or signals_map.get("final_assembly_product_release_eligible") is False
            or signals_map.get("final_resume_x2_all_pass") is False
            or signals_map.get("judge_quorum_satisfied") is False
            or (x1d_overall not in {"", "PASS"})
        )
        if assembly_or_coherence_flagged:
            asm_lanes, _ = self._load_assembly_coherence_failures()
            failing.update(asm_lanes)

        if final_out_failed:
            for out_base in (
                self.artifact_dir,
                self.artifact_dir / "modular_r4" / "final_resume_assembly",
            ):
                out_json = out_base / "FINAL_RESUME_OUTPUT.json"
                if out_json.is_file():
                    try:
                        odoc = json.loads(out_json.read_text(encoding="utf-8"))
                        for gate in odoc.get("gates") or []:
                            if not isinstance(gate, Mapping) or bool(gate.get("pass", True)):
                                continue
                            blob = json.dumps(gate, default=str)
                            for ln in GENERATED_LANES:
                                if ln in blob:
                                    failing.add(ln)
                    except (OSError, json.JSONDecodeError, TypeError, ValueError):
                        pass
                out_txt = out_base / "FINAL_RESUME_OUTPUT.txt"
                if out_txt.is_file():
                    try:
                        txt = out_txt.read_text(encoding="utf-8")
                        for ln in GENERATED_LANES:
                            if f"[NOT COMPLETED: {ln}]" in txt:
                                failing.add(ln)
                    except OSError:
                        pass

        if (final_asm_failed or final_out_failed) and not (failing & valid_lanes):
            failing.add("executive_summary")

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

        from apps_rg.runtime.providers.wallclock_http_guard import remaining_whole_run_budget_s

        rem_budget = remaining_whole_run_budget_s()
        if rem_budget is not None and rem_budget < 25.0:
            logger.warning(
                "Resume run recovery skipped: insufficient whole-run wall-clock budget remaining (%.1fs < 25.0s).",
                rem_budget,
            )
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
            asm_forced_lanes, _ = self._load_assembly_coherence_failures()
            if exec_summary_blocked:
                asm_forced_lanes.add("executive_summary")
            try:
                from apps_rg.runtime.orchestration.patch_run import classify_all_lane_states
                from apps_rg.runtime.runtime_proof_layout import find_repo_root

                repo = find_repo_root(self.artifact_dir)
                lane_states = classify_all_lane_states(repo, self.artifact_dir)
                target_failing = [
                    lane for lane in failing_lanes
                    if lane in asm_forced_lanes or not bool(lane_states.get(lane, {}).get("authorized"))
                ]
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                pass

            if not target_failing:
                logger.info("ResumeRunRecoveryAgent: No unauthorized failing lanes to re-dispatch.")
                return whole_run_exit, prior_x3, exec_summary_blocked

            plan = build_patch_plan(
                self.artifact_dir,
                sections_csv=",".join(target_failing),
                force_lanes_csv=",".join(target_failing),
            )
            receipt.lanes_re_dispatched = list(plan.target_lanes)

            from apps_rg.runtime.c0.c0_perf_sync_helpers import (
                RECOVERY_SEALED_C0_MANIFEST_ENV,
                RECOVERY_SEALED_C0_MANIFEST_FILENAME,
                collect_sealed_c0_manifest_for_lanes,
            )
            from apps_rg.runtime.env_bootstrap import temporary_env_override

            sealed_c0_lanes = collect_sealed_c0_manifest_for_lanes(
                self.artifact_dir,
                plan.target_lanes,
                raw_request=raw_request,
            )
            env_updates: dict[str, str | None] = {}
            if sealed_c0_lanes:
                manifest_path = self.artifact_dir / RECOVERY_SEALED_C0_MANIFEST_FILENAME
                manifest_path.write_text(
                    json.dumps({"schema_version": 1, "lanes": sealed_c0_lanes}, indent=2) + "\n",
                    encoding="utf-8",
                )
                env_updates[RECOVERY_SEALED_C0_MANIFEST_ENV] = str(manifest_path)
            if isinstance(recovery_directives, Mapping) and recovery_directives.get("lane_overrides"):
                env_updates["APPS_RG_RECOVERY_DIRECTIVES_JSON"] = json.dumps(recovery_directives)
            details["reused_sealed_c0_lanes"] = sorted(sealed_c0_lanes.keys())

            with temporary_env_override(env_updates):
                try:
                    patch_result = execute_patch_run(
                        plan,
                        dispatch_fn=self.dispatch_fn,
                        aggregate_fn=self.aggregate_fn,
                        recovery_directives=recovery_directives,
                        close_product_run=False,
                    )
                except TypeError:
                    patch_result = execute_patch_run(
                        plan,
                        dispatch_fn=self.dispatch_fn,
                        aggregate_fn=self.aggregate_fn,
                    )
            details["patch_result"] = {
                "exit_code": patch_result.get("exit_code"),
                "target_lanes": patch_result.get("target_lanes"),
                "lane_overrides_bound": bool(recovery_directives.get("lane_overrides")),
            }
            dispatch_success = patch_result.get("exit_code") == 0
        except Exception as exc:  # guardian: allow-broad-exception -- recovery agent logs and records dispatch error in receipt
            logger.warning("ResumeRunRecoveryAgent patch dispatch error: %s", exc)
            details["error"] = f"{type(exc).__name__}:{exc}"

        # Re-derive whole_run_exit packet
        try:
            from apps_rg.runtime.orchestration.core_runtime_authority import emit_core_runtime_authority
            from apps_rg.runtime.orchestration.patch_product_closeout import (
                refresh_root_spine_bundle_after_patch,
            )

            if dispatch_success:
                try:
                    refresh_root_spine_bundle_after_patch(self.artifact_dir)
                except Exception:  # guardian: allow-silent-swallow -- best-effort root spine bundle refresh during recovery
                    pass
            try:
                emit_core_runtime_authority(self.artifact_dir)
            except Exception:  # guardian: allow-silent-swallow -- best-effort core runtime authority refresh before exit packet
                pass
            updated_whole_run_exit = emit_whole_run_exit_review_packet(
                artifact_dir=self.artifact_dir,
                identity=whole_run_exit_identity,
            )
        except Exception as exc:  # guardian: allow-broad-exception -- recovery agent logs and falls back to prior exit packet
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
