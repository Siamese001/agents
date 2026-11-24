"""Closed-Loop Evaluation Flywheel for Resume (apps_rg) and Outreach (apps_lic) Engines.

Bridges sealed evaluation manifests and completed product runs into persistent
platform learning stores while preserving strict architectural boundaries:

1. Failure Harvester -> FeedbackLearningStore (SQLite)
2. Passing Trajectory Miner -> TrajectoryLearningEngine (persisted JSON)
3. Judge Calibration & Drift Tracker -> JudgeCalibrator + calibration history JSON
4. ADR-040 Triage Promoter & Capability-to-Regression Graduation Tracker
   (stages review packets under data/eval/triage/; never auto-mutates suites)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from agents.observability.trajectory_learning import (
    DEFAULT_TRAJECTORY_STORE_PATH,
    TrajectoryExemplar,
    TrajectoryLearningEngine,
)
from agents.orchestration.failure_taxonomy import FailureKind
from agents.orchestration.learning_store import (
    DEFAULT_LEARNING_STORE_PATH,
    FeedbackLearningStore,
    compute_failure_signature,
    resolve_primary_repo_root,
)
from agents.telemetry.calibration import JudgeCalibrator

DEFAULT_LEARNING_DIR = resolve_primary_repo_root() / "artifacts" / "learning"
DEFAULT_CALIBRATION_HISTORY_PATH = DEFAULT_LEARNING_DIR / "judge_calibration_history.json"
DEFAULT_GRADUATION_STATE_PATH = DEFAULT_LEARNING_DIR / "capability_graduation_state.json"
DEFAULT_TRIAGE_ROOT = resolve_primary_repo_root() / "data" / "eval" / "triage"

logger = logging.getLogger(__name__)

GRADUATION_CONSECUTIVE_PASS_TARGET = 10
CAPABILITY_MIN_PASS_RATE = 0.50
REGRESSION_MIN_PASS_RATE = 0.98

_RG_STAGE_SEQUENCE: tuple[str, ...] = ("U0", "D0", "C0", "PA", "L2", "X2", "X1D", "X3", "L6")
_LIC_STAGE_SEQUENCE: tuple[str, ...] = ("U0", "D0", "C0", "PA", "X1A", "X1B", "X1C", "X2", "X1D", "X3")

_DEFAULT_REPAIR_HINTS: dict[str, str] = {
    "policy.forbidden_content_detected": "Strip prohibited terms, fabricated familiarity, and unsafe directives before X3 exit.",
    "policy.x3_disposition_mismatch": "Align terminal X3 disposition with grounding and safety gate preconditions.",
    "grounding.ungrounded_claim": "Bind every claim to verified C0 evidence references; drop unsupported assertions.",
    "grounding.missing_provenance": "Emit complete evidence_refs and required C0 namespaces for every output claim.",
    "contract.schema.required_output_keys_missing": "Emit all required output keys defined by the engine schema contract.",
    "contract.artifact.required_artifacts_missing": "Materialize all required sealed bundle artifacts before closing the run.",
    "g6_defect_miss": "Strengthen outreach X2/judge checks to catch planted defect classes with zero clean false positives.",
    "repeatability_hotspot": "Stabilize deterministic prompt/rubric variance below the G5 0.02 std-dev ceiling.",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load JSON artifact at %s: %s", path, exc)
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def map_failure_mode_to_kind(failure_mode: str) -> FailureKind:
    """Map an apps_eval or engine failure mode identifier to a canonical FailureKind."""
    low = str(failure_mode or "").lower()
    if any(tok in low for tok in ("policy", "safety", "privacy", "forbidden", "escalat", "x3")):
        return FailureKind.POLICY
    if any(tok in low for tok in ("ground", "provenance", "hallucin", "fabricat", "fact", "launder")):
        return FailureKind.FACTUAL_CONFLICT
    if any(tok in low for tok in ("schema", "artifact", "contract", "manifest")):
        return FailureKind.SCHEMA
    if any(tok in low for tok in ("provider", "quota", "rate_limit")):
        return FailureKind.PROVIDER
    if any(tok in low for tok in ("timeout", "transport", "network")):
        return FailureKind.TRANSPORT
    return FailureKind.DETERMINISTIC_QUALITY


def classify_adr040_route(signal: str) -> str:
    """Route an ADR-040 promotion candidate signal to its canonical dataset category."""
    low = str(signal or "").lower()
    if any(tok in low for tok in ("safety", "policy", "privacy", "forbidden")):
        return "safety"
    if any(tok in low for tok in ("trajectory", "stage", "sequence")):
        return "trajectory"
    if any(tok in low for tok in ("ground", "provenance", "rag", "fact")):
        return "rag"
    if any(tok in low for tok in ("quality", "fail", "defect", "regression", "repeatability")):
        return "quality"
    return "triage"


class EvalFlywheelEngine:
    """Coordinates closed-loop failure harvesting, trajectory mining, drift tracking, and ADR-040 triage."""

    def __init__(
        self,
        *,
        learning_db_path: str | Path | None = None,
        trajectory_store_path: str | Path | None = None,
        calibration_history_path: str | Path | None = None,
        graduation_state_path: str | Path | None = None,
        triage_root: str | Path | None = None,
    ) -> None:
        self.learning_db_path = Path(learning_db_path or DEFAULT_LEARNING_STORE_PATH)
        self.trajectory_store_path = Path(trajectory_store_path or DEFAULT_TRAJECTORY_STORE_PATH)
        self.calibration_history_path = Path(calibration_history_path or DEFAULT_CALIBRATION_HISTORY_PATH)
        self.graduation_state_path = Path(graduation_state_path or DEFAULT_GRADUATION_STATE_PATH)
        self.triage_root = Path(triage_root or DEFAULT_TRIAGE_ROOT)

    def _open_feedback_store(self) -> FeedbackLearningStore:
        return FeedbackLearningStore(self.learning_db_path)

    def _open_trajectory_engine(self) -> TrajectoryLearningEngine:
        return TrajectoryLearningEngine(min_efficiency=0.80, store_path=self.trajectory_store_path)

    def _stage_triage_candidate(
        self,
        *,
        app_id: str,
        trigger_signal: str,
        failure_mode: str,
        run_id: str,
        description: str,
        input_summary: str = "",
        expected_x3: str = "X3B_ESCALATE_HITL",
        metadata: Mapping[str, Any] | None = None,
    ) -> Path:
        raw_key = f"{app_id}:{trigger_signal}:{failure_mode}:{run_id}"
        short_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]
        candidate_id = f"{app_id}_{classify_adr040_route(trigger_signal)}_{short_hash}"
        packet_path = self.triage_root / app_id / f"{candidate_id}.json"
        if packet_path.is_file():
            existing = _load_json(packet_path)
            if str(existing.get("status") or "").upper() in {"PROMOTED", "RESOLVED", "ARCHIVED"}:
                return packet_path
        packet = {
            "schema_version": "agents.eval_flywheel.triage_candidate.v1",
            "candidate_id": candidate_id,
            "app_id": app_id,
            "status": "PENDING_REVIEW",
            "trigger_signal": trigger_signal,
            "trigger_reason": failure_mode or trigger_signal,
            "target_category": classify_adr040_route(f"{trigger_signal}:{failure_mode}"),
            "run_id": run_id,
            "description": description,
            "input_summary": input_summary or description,
            "expected_x3": expected_x3,
            "staged_at": _utc_now(),
            "metadata": dict(metadata or {}),
        }
        _write_json(packet_path, packet)
        return packet_path

    def _update_calibration_history(self, observations: Sequence[tuple[str, float, str]]) -> dict[str, Any]:
        history = _load_json(self.calibration_history_path)
        series: dict[str, list[dict[str, Any]]] = dict(history.get("series") or {})
        now = _utc_now()
        for criterion, score, source_run in observations:
            bucket = list(series.get(criterion) or [])
            bucket.append({"score": round(float(score), 6), "run_id": source_run, "recorded_at": now})
            if len(bucket) > 200:
                bucket = bucket[-200:]
            series[criterion] = bucket

        calibrator = JudgeCalibrator()
        drift_summary: dict[str, Any] = {}
        alerts: list[str] = []
        for criterion, rows in sorted(series.items()):
            for row in rows[:-1]:
                calibrator.drift_detector.record(criterion, float(row["score"]))
            latest = float(rows[-1]["score"]) if rows else 0.0
            drift_info = calibrator.drift_detector.detect_drift(criterion, latest)
            calibrator.drift_detector.record(criterion, latest)
            stats = calibrator.drift_detector.get_stats(criterion)
            hard_floor_breach = (
                (criterion == "g6_cohens_kappa" and latest < 0.65)
                or (criterion == "g6_spearman_rho" and latest < 0.70)
                or (criterion == "g6_clean_fpr" and latest > 0.0)
                or (criterion == "g6_defect_tpr" and latest < 0.90)
            )
            drift_detected = bool(drift_info.get("drift_detected")) or hard_floor_breach
            if drift_detected:
                alerts.append(
                    f"{criterion}: latest={latest:.4f}, z={drift_info.get('z_score', 0.0)}, floor_breach={hard_floor_breach}"
                )
            drift_summary[criterion] = {
                "latest": latest,
                "stats": stats,
                "drift_detected": drift_detected,
                "z_score": drift_info.get("z_score", 0.0),
                "hard_floor_breach": hard_floor_breach,
            }

        payload = {
            "schema_version": "agents.judge_calibration_history.v1",
            "updated_at": now,
            "series": series,
            "drift_summary": drift_summary,
            "alerts": alerts,
        }
        _write_json(self.calibration_history_path, payload)
        return payload

    def _update_graduation_streaks(
        self,
        suite_pass_rates: Mapping[str, float],
        *,
        consecutive_target: int = GRADUATION_CONSECUTIVE_PASS_TARGET,
    ) -> dict[str, Any]:
        state = _load_json(self.graduation_state_path)
        streaks: dict[str, dict[str, Any]] = dict(state.get("suites") or {})
        now = _utc_now()
        ready_list: list[str] = []
        for suite_id, pass_rate in sorted(suite_pass_rates.items()):
            rec = dict(streaks.get(suite_id) or {"consecutive_passes": 0, "stage": "capability"})
            if pass_rate >= CAPABILITY_MIN_PASS_RATE:
                rec["consecutive_passes"] = int(rec.get("consecutive_passes", 0)) + 1
            else:
                rec["consecutive_passes"] = 0
            rec["last_pass_rate"] = round(float(pass_rate), 6)
            rec["updated_at"] = now
            rec["graduation_ready"] = int(rec["consecutive_passes"]) >= consecutive_target
            if rec["graduation_ready"]:
                ready_list.append(suite_id)
            streaks[suite_id] = rec
        payload = {
            "schema_version": "agents.capability_graduation_state.v1",
            "updated_at": now,
            "consecutive_target": consecutive_target,
            "capability_min_pass_rate": CAPABILITY_MIN_PASS_RATE,
            "regression_min_pass_rate": REGRESSION_MIN_PASS_RATE,
            "graduation_ready_suites": ready_list,
            "suites": streaks,
        }
        _write_json(self.graduation_state_path, payload)
        return payload

    def ingest_manifest(self, manifest: Mapping[str, Any] | str | Path) -> dict[str, Any]:
        """Ingest a unified evidence_manifest.json into all four closed-loop flywheel stores."""
        data = _load_json(Path(manifest).resolve()) if isinstance(manifest, (str, Path)) else dict(manifest)
        run_ts = str(data.get("generated_at") or _utc_now())
        suite_receipts = data.get("suite_receipts") or {}

        fb_store = self._open_feedback_store()
        traj_engine = self._open_trajectory_engine()

        harvested_failures: list[dict[str, Any]] = []
        recorded_resolutions: list[str] = []
        mined_exemplars: list[str] = []
        staged_candidates: list[str] = []
        cal_observations: list[tuple[str, float, str]] = []
        suite_pass_rates: dict[str, float] = {}

        try:
            existing_sigs = {row["signature_hash"]: row for row in fb_store.get_failure_statistics()}

            for suite_id, rec in sorted(suite_receipts.items()):
                if not isinstance(rec, dict):
                    continue
                app_id = str(rec.get("app_id") or ("apps_rg" if suite_id.startswith("apps_rg") else "apps_lic"))
                record_id = str(rec.get("record_id") or suite_id)
                finding_count = int(rec.get("finding_count", 0))
                passed_findings = int(rec.get("passed_findings", 0))
                pass_rate = (passed_findings / float(finding_count)) if finding_count > 0 else 0.0
                suite_pass_rates[suite_id] = pass_rate

                cal_observations.append((f"{suite_id}:grader_pass_rate", pass_rate, record_id))
                cal_observations.append((f"{app_id}:suite_score", float(rec.get("score", 0.0)), record_id))

                suite_passed = bool(rec.get("suite_passed", False))
                bcmp = rec.get("baseline_comparison") or {}
                regressed = str(bcmp.get("verdict", "")) == "regression" or float(bcmp.get("delta", 0.0)) < -0.05

                if suite_passed and not regressed:
                    steps = _RG_STAGE_SEQUENCE if app_id == "apps_rg" else _LIC_STAGE_SEQUENCE
                    ex_id = f"ex_{hashlib.sha256(f'{app_id}:{suite_id}:{record_id}'.encode()).hexdigest()[:10]}"
                    ex = TrajectoryExemplar(
                        exemplar_id=ex_id,
                        run_id=record_id,
                        task_type=app_id,
                        efficiency_score=round(max(0.80, pass_rate), 4),
                        step_sequence=steps,
                        key_decisions=("ACCEPT", "PROMOTION_PASS"),
                        summary_text=f"Verified passing eval suite {suite_id} ({passed_findings}/{finding_count} graders).",
                        metadata={"suite_id": suite_id, "score": float(rec.get("score", 0.0))},
                        created_at=time.time(),
                    )
                    if traj_engine.record_exemplar(ex):
                        mined_exemplars.append(ex_id)

                    # Auto-resolve any previously recorded failures for this suite prefix
                    for sig_hash, row in existing_sigs.items():
                        constraint = str(row.get("normalized_constraint", ""))
                        if constraint.startswith(f"{suite_id.lower()}:"):
                            hint = _DEFAULT_REPAIR_HINTS.get(
                                constraint.split(":", 1)[1],
                                f"Resolved on passing eval suite {suite_id}.",
                            )
                            fb_store.record_resolution(
                                sig_hash,
                                run_id=record_id,
                                action_taken="EVAL_FLYWHEEL_VERIFIED_FIX",
                                repair_hint=hint,
                                outcome="SUCCESS",
                            )
                            recorded_resolutions.append(sig_hash)
                    self.resolve_triage_candidates(app_id=app_id, resolved_by_run_id=record_id)
                else:
                    fw = rec.get("regression_flywheel") or {}
                    fm_counts = fw.get("failure_mode_counts") or {}
                    modes = list(fm_counts.keys()) or (["baseline_regression"] if regressed else ["suite_verdict_fail"])
                    for mode_name in modes:
                        kind = map_failure_mode_to_kind(mode_name)
                        constraint = f"{suite_id}:{mode_name}"
                        sig_hash = fb_store.record_failure(kind, constraint, run_id=record_id)
                        default_hint = _DEFAULT_REPAIR_HINTS.get(
                            mode_name,
                            f"Remediate {mode_name} in {app_id} before promoting to main.",
                        )
                        fb_store.record_resolution(
                            sig_hash,
                            run_id=record_id,
                            action_taken="EVAL_FLYWHEEL_DIAGNOSTIC_HINT",
                            repair_hint=default_hint,
                            outcome="PENDING_VERIFICATION",
                            event_id=f"hint_{sig_hash}",
                        )
                        harvested_failures.append({"signature_hash": sig_hash, "kind": kind.value, "constraint": constraint})
                        pkt = self._stage_triage_candidate(
                            app_id=app_id,
                            trigger_signal="quality.verdict==fail" if not regressed else "baseline_regression",
                            failure_mode=mode_name,
                            run_id=record_id,
                            description=f"Eval failure harvested from {suite_id}: {mode_name}",
                            metadata={"suite_id": suite_id, "delta": bcmp.get("delta", 0.0)},
                        )
                        staged_candidates.append(pkt.as_posix())

            # Ingest G5/G6 outreach calibration metrics & violations
            g56 = data.get("apps_lic_g5_g6_receipt")
            if isinstance(g56, dict) and g56.get("g6"):
                g6 = g56["g6"]
                g5 = g56.get("g5") or {}
                cal_observations.extend(
                    [
                        ("g6_spearman_rho", float(g6.get("spearman_rho", 0.0)), run_ts),
                        ("g6_cohens_kappa", float(g6.get("cohens_kappa", 0.0)), run_ts),
                        ("g6_clean_fpr", float(g6.get("fpr", 0.0)), run_ts),
                        ("g6_defect_tpr", float(g6.get("tpr", 0.0)), run_ts),
                        ("g5_max_std", float(g5.get("max_std", 0.0)), run_ts),
                    ]
                )
                for viol in list(g6.get("violations") or []) + list(g5.get("violations") or []):
                    sig_hash = fb_store.record_failure(
                        FailureKind.DETERMINISTIC_QUALITY,
                        f"apps_lic:g5_g6:{viol}",
                        run_id=run_ts,
                    )
                    harvested_failures.append({"signature_hash": sig_hash, "constraint": str(viol)})
                    pkt = self._stage_triage_candidate(
                        app_id="apps_lic",
                        trigger_signal="g6_defect_miss",
                        failure_mode="g6_defect_miss",
                        run_id=run_ts,
                        description=f"Outreach G5/G6 calibration violation: {viol}",
                    )
                    staged_candidates.append(pkt.as_posix())

            # Ingest Resume Engine E2E failure if any
            rg_e2e = data.get("apps_rg_e2e_receipt")
            if isinstance(rg_e2e, dict) and not rg_e2e.get("skipped") and rg_e2e.get("status") != "PASS":
                err_txt = str(rg_e2e.get("error") or rg_e2e.get("eval_status") or "apps_rg_e2e_failed")
                sig_hash = fb_store.record_failure(FailureKind.POLICY, f"apps_rg:e2e:{err_txt[:120]}", run_id=run_ts)
                harvested_failures.append({"signature_hash": sig_hash, "constraint": err_txt[:120]})
                pkt = self._stage_triage_candidate(
                    app_id="apps_rg",
                    trigger_signal="quality.verdict==fail",
                    failure_mode="apps_rg_e2e_failed",
                    run_id=run_ts,
                    description=f"Resume deterministic E2E failure: {err_txt[:200]}",
                )
                staged_candidates.append(pkt.as_posix())

            fb_summary = fb_store.get_summary()
        finally:
            fb_store.close()

        cal_payload = self._update_calibration_history(cal_observations)
        grad_payload = self._update_graduation_streaks(suite_pass_rates)

        return {
            "status": "INGESTED",
            "ingested_at": _utc_now(),
            "harvested_failures": harvested_failures,
            "recorded_resolutions": recorded_resolutions,
            "mined_exemplars": mined_exemplars,
            "staged_triage_candidates": staged_candidates,
            "calibration_alerts": cal_payload.get("alerts", []),
            "graduation_ready_suites": grad_payload.get("graduation_ready_suites", []),
            "feedback_summary": fb_summary,
            "trajectory_summary": traj_engine.export_summary(),
        }

    def ingest_product_run(
        self,
        *,
        app_id: str,
        run_id: str,
        x3_disposition: str,
        passed: bool,
        failure_reasons: Sequence[str] = (),
        score: float = 1.0,
        scenario_fingerprint: str = "",
        is_smoke_or_demo: bool = False,
    ) -> dict[str, Any]:
        """Observer-only ingestion of a completed Resume or Outreach product run."""
        fb_store = self._open_feedback_store()
        traj_engine = self._open_trajectory_engine()
        staged: list[str] = []
        harvested: list[str] = []
        norm_scen = str(scenario_fingerprint or "").strip()
        eff_smoke = bool(is_smoke_or_demo or norm_scen.endswith("::smoke_or_demo"))
        try:
            if not passed or x3_disposition in ("X3B_ESCALATE_HITL", "X3E_SAFE_ABSTAIN"):
                reasons = list(failure_reasons) or [f"x3:{x3_disposition}"]
                for reason in reasons:
                    kind = map_failure_mode_to_kind(reason)
                    constraint_key = (
                        f"{app_id}:{norm_scen}:{reason}" if norm_scen else f"{app_id}:{reason}"
                    )
                    sig_hash = fb_store.record_failure(kind, constraint_key, run_id=run_id)
                    harvested.append(sig_hash)
                    pkt = self._stage_triage_candidate(
                        app_id=app_id,
                        trigger_signal="escalate_hitl" if "ESCALATE" in x3_disposition else "quality.verdict==fail",
                        failure_mode=str(reason)[:120],
                        run_id=run_id,
                        description=f"Product run observation ({app_id}/{run_id}): {reason}",
                        expected_x3=x3_disposition or "X3B_ESCALATE_HITL",
                        metadata={
                            "scenario_fingerprint": norm_scen,
                            "is_smoke_or_demo": eff_smoke,
                        },
                    )
                    staged.append(pkt.as_posix())
            elif score >= 0.80:
                steps = _RG_STAGE_SEQUENCE if app_id == "apps_rg" else _LIC_STAGE_SEQUENCE
                ex = TrajectoryExemplar(
                    exemplar_id=f"ex_{hashlib.sha256(f'{app_id}:{run_id}'.encode()).hexdigest()[:10]}",
                    run_id=run_id,
                    task_type=app_id,
                    efficiency_score=round(min(1.0, float(score)), 4),
                    step_sequence=steps,
                    key_decisions=("ACCEPT", x3_disposition or "X3D_ALLOW_FINISH"),
                    summary_text=f"Observed passing product run {run_id} for {app_id}.",
                    metadata={
                        "x3_disposition": x3_disposition,
                        "source": "product_run_observer",
                        "scenario_fingerprint": norm_scen,
                        "is_smoke_or_demo": eff_smoke,
                    },
                )
                traj_engine.record_exemplar(ex)
                if not eff_smoke:
                    for row in fb_store.get_failure_statistics():
                        constraint = str(row.get("normalized_constraint") or "")
                        if not constraint.startswith(f"{app_id.lower()}:") or float(row.get("success_rate") or 0.0) >= 1.0:
                            continue
                        if norm_scen:
                            # Scope auto-resolution strictly to matching scenario fingerprint or unscoped legacy app signatures.
                            rest = constraint[len(f"{app_id.lower()}:") :]
                            if "::" in rest and not rest.startswith(f"{norm_scen.lower()}:"):
                                continue
                        fb_store.record_resolution(
                            str(row["signature_hash"]),
                            run_id=run_id,
                            action_taken="PRODUCT_RUN_VERIFIED_PASS",
                            repair_hint=f"Verified passing product run {run_id} for {app_id}.",
                            outcome="SUCCESS",
                        )
                    self.resolve_triage_candidates(
                        app_id=app_id,
                        resolved_by_run_id=run_id,
                        scenario_fingerprint=norm_scen or None,
                    )
        finally:
            fb_store.close()
        self._update_calibration_history([(f"{app_id}:product_run_score", float(score), run_id)])
        return {
            "status": "OBSERVED",
            "app_id": app_id,
            "run_id": run_id,
            "scenario_fingerprint": norm_scen,
            "is_smoke_or_demo": eff_smoke,
            "harvested_signatures": harvested,
            "staged_candidates": staged,
        }

    def resolve_triage_candidates(
        self,
        *,
        app_id: str,
        resolved_by_run_id: str = "",
        failure_mode_filter: str | None = None,
        scenario_fingerprint: str | None = None,
    ) -> list[str]:
        """Transition PENDING_REVIEW triage packets for app_id to RESOLVED once verified."""
        app_dir = self.triage_root / app_id
        if not app_dir.is_dir():
            return []
        now = _utc_now()
        resolved_paths: list[str] = []
        for path in sorted(app_dir.glob("*.json")):
            pkt = _load_json(path)
            if not pkt or str(pkt.get("status") or "").upper() != "PENDING_REVIEW":
                continue
            if failure_mode_filter is not None:
                pkt_mode = str(pkt.get("trigger_reason") or pkt.get("trigger_signal") or "")
                if failure_mode_filter not in pkt_mode:
                    continue
            if scenario_fingerprint is not None:
                pkt_meta = pkt.get("metadata") if isinstance(pkt.get("metadata"), Mapping) else {}
                pkt_scen = str(pkt_meta.get("scenario_fingerprint") or "").strip()
                if pkt_scen and pkt_scen != scenario_fingerprint:
                    continue
            pkt["status"] = "RESOLVED"
            pkt["resolved_at"] = now
            if resolved_by_run_id:
                pkt["resolved_by_run_id"] = resolved_by_run_id
            _write_json(path, pkt)
            resolved_paths.append(path.as_posix())
        return resolved_paths

    def list_triage_candidates(self, *, app_filter: str = "all", pending_only: bool = True) -> list[dict[str, Any]]:
        """List ADR-040 staged triage packets."""
        if not self.triage_root.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.triage_root.rglob("*.json")):
            pkt = _load_json(path)
            if not pkt:
                continue
            if app_filter != "all" and pkt.get("app_id") != app_filter:
                continue
            if pending_only and pkt.get("status") != "PENDING_REVIEW":
                continue
            pkt["_path"] = path.as_posix()
            items.append(pkt)
        return items

    def get_calibration_status(self) -> dict[str, Any]:
        """Return persisted judge calibration history and drift alerts."""
        data = _load_json(self.calibration_history_path)
        if not data:
            return {
                "status": "NO_HISTORY",
                "alerts": [],
                "drift_summary": {},
                "history_path": self.calibration_history_path.as_posix(),
            }
        alerts = list(data.get("alerts") or [])
        return {
            "status": "DRIFT_ALERT" if alerts else "CALIBRATED",
            "updated_at": data.get("updated_at", ""),
            "alerts": alerts,
            "drift_summary": data.get("drift_summary") or {},
            "history_path": self.calibration_history_path.as_posix(),
        }

    def get_graduation_status(self) -> dict[str, Any]:
        """Return capability-to-regression graduation streak status."""
        data = _load_json(self.graduation_state_path)
        if not data:
            return {
                "consecutive_target": GRADUATION_CONSECUTIVE_PASS_TARGET,
                "graduation_ready_suites": [],
                "suites": {},
            }
        return data
