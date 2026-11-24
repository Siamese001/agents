"""Fail-closed promotion evidence verifier for the unified Resume & Outreach eval harness.

Pure JSON/filesystem module (zero SQLite imports). Verifies a sealed
``evidence_manifest.json`` emitted by ``apps_eval.harness_orchestrator`` and returns
a structured ``PromotionGateResult`` with distinct exit codes:

- ``0``: PASS
- ``1``: BLOCKED (missing receipt, schema error, failed probe, or threshold failure)
- ``2``: REGRESSION (score drop exceeding ``max_score_drop`` or baseline regression verdict)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps_eval.bootstrap_baselines import SNAPSHOT_GRADER_ONLY_SUITES
from apps_eval.harness_orchestrator import EVIDENCE_MANIFEST_SCHEMA_VERSION

MIN_G6_SPEARMAN_RHO = 0.70
MIN_G6_COHENS_KAPPA = 0.65
MAX_G6_CLEAN_FPR = 0.0
MIN_G6_DEFECT_TPR = 0.90
MAX_G5_STD_CEILING = 0.02


@dataclass(frozen=True)
class PromotionGateResult:
    """Structured verdict from the fail-closed promotion evidence gate."""

    status: str  # PASS | BLOCKED | REGRESSION
    exit_code: int  # 0 | 1 | 2
    manifest_path: str
    checks: dict[str, bool] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    regression_reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "manifest_path": self.manifest_path,
            "checks": dict(self.checks),
            "blocking_reasons": list(self.blocking_reasons),
            "regression_reasons": list(self.regression_reasons),
            "metrics": dict(self.metrics),
        }


def _required_suites_for_manifest(app_filter: str, require_holdout: bool) -> list[str]:
    required: list[str] = []
    if app_filter in ("all", "apps_rg"):
        required.append("apps_rg.dev.resume_generation")
        if require_holdout:
            required.append("apps_rg.holdout.resume_generation")
    if app_filter in ("all", "apps_lic"):
        required.append("apps_lic.dev.outreach_message")
        if require_holdout:
            required.append("apps_lic.holdout.outreach_message")
    return required


def verify_promotion_evidence(
    manifest_path: str | Path,
    *,
    require_holdout: bool = True,
    require_engine_probes: bool = True,
    max_score_drop: float = 0.05,
    ide_judge_drift_receipt_path: str | Path | None = None,
    require_ide_judge_drift: bool = False,
    repo_root: str | Path | None = None,
) -> PromotionGateResult:
    """Verify sealed promotion evidence manifest fail-closed."""
    path = Path(manifest_path).resolve()
    if not path.is_file():
        return PromotionGateResult(
            status="BLOCKED",
            exit_code=1,
            manifest_path=path.as_posix(),
            checks={"manifest_present": False},
            blocking_reasons=[f"manifest not found: {path.as_posix()}"],
        )

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return PromotionGateResult(
            status="BLOCKED",
            exit_code=1,
            manifest_path=path.as_posix(),
            checks={"manifest_valid_json": False},
            blocking_reasons=[f"invalid manifest JSON: {exc}"],
        )

    if not isinstance(manifest, dict):
        return PromotionGateResult(
            status="BLOCKED",
            exit_code=1,
            manifest_path=path.as_posix(),
            checks={"manifest_object": False},
            blocking_reasons=["manifest root must be a JSON object"],
        )

    blocking: list[str] = []
    regressions: list[str] = []
    checks: dict[str, bool] = {}

    schema_ok = manifest.get("schema_version") == EVIDENCE_MANIFEST_SCHEMA_VERSION
    checks["schema_version"] = schema_ok
    if not schema_ok:
        blocking.append(
            f"unexpected schema_version: {manifest.get('schema_version')!r} != {EVIDENCE_MANIFEST_SCHEMA_VERSION!r}"
        )

    app_filter = str(manifest.get("app_filter") or "all")
    fast_dev = bool(manifest.get("fast_dev", False))
    eff_require_holdout = require_holdout and not fast_dev
    eff_require_probes = require_engine_probes and not fast_dev

    suite_receipts = manifest.get("suite_receipts")
    if not isinstance(suite_receipts, dict):
        suite_receipts = {}
    l6_receipts = manifest.get("l6_shadow_handoff_receipts")
    if not isinstance(l6_receipts, dict):
        l6_receipts = {}

    required_suites = _required_suites_for_manifest(app_filter, eff_require_holdout)
    suite_scores: dict[str, float] = {}
    for suite_id in required_suites:
        rec = suite_receipts.get(suite_id)
        if not isinstance(rec, dict):
            checks[f"suite:{suite_id}"] = False
            blocking.append(f"missing suite receipt: {suite_id}")
            continue

        finding_count = int(rec.get("finding_count", 0))
        passed_findings = int(rec.get("passed_findings", 0))
        graders_ok = finding_count > 0 and passed_findings == finding_count
        verdict_ok = suite_id in SNAPSHOT_GRADER_ONLY_SUITES or str(rec.get("verdict", "")) == "pass"
        suite_ok = graders_ok and verdict_ok and bool(rec.get("suite_passed", False))
        checks[f"suite:{suite_id}"] = suite_ok
        suite_scores[suite_id] = float(rec.get("score", 0.0))
        if not suite_ok:
            blocking.append(
                f"suite failed: {suite_id} (passed_findings={passed_findings}/{finding_count}, verdict={rec.get('verdict')!r})"
            )

        # Baseline non-regression check
        bcmp = rec.get("baseline_comparison")
        if not isinstance(bcmp, dict) or not bcmp.get("compared"):
            checks[f"baseline:{suite_id}"] = False
            blocking.append(f"missing baseline comparison for {suite_id}")
        else:
            delta = float(bcmp.get("delta", 0.0))
            cmp_verdict = str(bcmp.get("verdict", ""))
            regressed = cmp_verdict == "regression" or delta < (-abs(max_score_drop) - 1e-9)
            checks[f"baseline:{suite_id}"] = not regressed
            if regressed:
                regressions.append(
                    f"baseline regression on {suite_id}: delta={delta:.6f}, verdict={cmp_verdict!r}"
                )

        # L6 shadow handoff receipt presence
        l6_rec = l6_receipts.get(suite_id)
        l6_ok = isinstance(l6_rec, dict) and bool(l6_rec.get("present")) and bool(l6_rec.get("sha256"))
        checks[f"l6_shadow:{suite_id}"] = l6_ok
        if not l6_ok:
            blocking.append(f"missing L6 shadow handoff receipt for {suite_id}")

    # Resume Engine offline E2E receipt & G5/G6 Planted-Defect Meta-Eval receipt
    rg_g6_metrics: dict[str, Any] = {}
    if app_filter in ("all", "apps_rg"):
        if eff_require_probes:
            rg_e2e = manifest.get("apps_rg_e2e_receipt")
            rg_ok = isinstance(rg_e2e, dict) and str(rg_e2e.get("status", "")) == "PASS"
            checks["apps_rg_e2e"] = rg_ok
            if not rg_ok:
                blocking.append(f"apps_rg E2E receipt failed or missing: {rg_e2e}")

        if eff_require_probes or "apps_rg_g5_g6_receipt" in manifest:
            rg_g56 = manifest.get("apps_rg_g5_g6_receipt")
            if not isinstance(rg_g56, dict) or str(rg_g56.get("status", "")) != "PASS":
                checks["apps_rg_g5_g6"] = False
                blocking.append(f"apps_rg G5/G6 receipt failed or missing: {rg_g56}")
            else:
                rg_g6 = rg_g56.get("g6") or {}
                rg_g5 = rg_g56.get("g5") or {}
                rg_rho = float(rg_g6.get("spearman_rho", 0.0))
                rg_kappa = float(rg_g6.get("cohens_kappa", 0.0))
                rg_fpr = float(rg_g6.get("fpr", 1.0))
                rg_tpr = float(rg_g6.get("tpr", 0.0))
                rg_max_std = float(rg_g5.get("max_std", 1.0))
                rg_g6_metrics = {
                    "corpus_size": int(rg_g6.get("corpus_size", 0)),
                    "spearman_rho": rg_rho,
                    "cohens_kappa": rg_kappa,
                    "fpr": rg_fpr,
                    "tpr": rg_tpr,
                    "g5_max_std": rg_max_std,
                }
                rg_cal_ok = (
                    bool(rg_g6.get("passed"))
                    and bool(rg_g5.get("passed"))
                    and rg_rho >= MIN_G6_SPEARMAN_RHO
                    and rg_kappa >= MIN_G6_COHENS_KAPPA
                    and rg_fpr <= MAX_G6_CLEAN_FPR
                    and rg_tpr >= MIN_G6_DEFECT_TPR
                    and rg_max_std <= MAX_G5_STD_CEILING
                )
                checks["apps_rg_g5_g6"] = rg_cal_ok
                if not rg_cal_ok:
                    blocking.append(
                        f"apps_rg G5/G6 calibration below threshold: rho={rg_rho}, kappa={rg_kappa}, fpr={rg_fpr}, tpr={rg_tpr}, max_std={rg_max_std}"
                    )

    # Outreach Engine G5 repeatability + G6 meta-eval calibration receipt
    g6_metrics: dict[str, Any] = {}
    if app_filter in ("all", "apps_lic"):
        g56 = manifest.get("apps_lic_g5_g6_receipt")
        if not isinstance(g56, dict) or str(g56.get("status", "")) != "PASS":
            checks["apps_lic_g5_g6"] = False
            blocking.append(f"apps_lic G5/G6 receipt failed or missing: {g56}")
        else:
            g6 = g56.get("g6") or {}
            g5 = g56.get("g5") or {}
            rho = float(g6.get("spearman_rho", 0.0))
            kappa = float(g6.get("cohens_kappa", 0.0))
            fpr = float(g6.get("fpr", 1.0))
            tpr = float(g6.get("tpr", 0.0))
            max_std = float(g5.get("max_std", 1.0))
            g6_metrics = {
                "corpus_size": int(g6.get("corpus_size", 0)),
                "spearman_rho": rho,
                "cohens_kappa": kappa,
                "fpr": fpr,
                "tpr": tpr,
                "g5_max_std": max_std,
            }
            cal_ok = (
                bool(g6.get("passed"))
                and bool(g5.get("passed"))
                and rho >= MIN_G6_SPEARMAN_RHO
                and kappa >= MIN_G6_COHENS_KAPPA
                and fpr <= MAX_G6_CLEAN_FPR
                and tpr >= MIN_G6_DEFECT_TPR
                and max_std <= MAX_G5_STD_CEILING
            )
            checks["apps_lic_g5_g6"] = cal_ok
            if not cal_ok:
                blocking.append(
                    f"apps_lic G5/G6 calibration below threshold: rho={rho}, kappa={kappa}, fpr={fpr}, tpr={tpr}, max_std={max_std}"
                )

        if eff_require_probes:
            bundle = manifest.get("apps_lic_bundle_receipt")
            bundle_ok = isinstance(bundle, dict) and str(bundle.get("status", "")) == "PASS"
            checks["apps_lic_bundle"] = bundle_ok
            if not bundle_ok:
                blocking.append(f"apps_lic sealed disk-JSON bundle verification failed or missing: {bundle}")

    # Release gate receipt check
    rg_gate = manifest.get("release_gate_receipt")
    if not isinstance(rg_gate, dict):
        checks["release_gate"] = False
        blocking.append("missing release_gate_receipt")
    else:
        gate_status = str(rg_gate.get("status", ""))
        if gate_status == "regression":
            checks["release_gate"] = False
            regressions.append("release_gate_receipt reported regression")
        elif gate_status != "pass":
            checks["release_gate"] = False
            blocking.append(f"release_gate_receipt status is {gate_status!r}, expected 'pass'")
        else:
            checks["release_gate"] = True

    # Golden flywheel shadow-to-blocking receipt check (OPEN cases shadow-run; VERIFIED cases block on regression)
    golden_metrics: dict[str, Any] = {}
    golden_rec = manifest.get("golden_flywheel_receipt")
    if isinstance(golden_rec, dict):
        golden_metrics = dict(golden_rec)
        blocking_failures = list(golden_rec.get("blocking_failures") or [])
        golden_ok = bool(golden_rec.get("passed", True)) and len(blocking_failures) == 0
        checks["golden_flywheel_blocking"] = golden_ok
        if not golden_ok:
            failed_ids = [str(f.get("case_id") or "") for f in blocking_failures if isinstance(f, dict)]
            regressions.append(
                f"verified golden flywheel case regression ({len(blocking_failures)} failed): {failed_ids}"
            )

    # IDE LLM-as-a-Judge human calibration & drift receipt gate (fast offline verification)
    drift_metrics: dict[str, Any] = {}
    drift_ref = ide_judge_drift_receipt_path or (
        manifest.get("ide_judge_drift_receipt_path")
        if isinstance(manifest.get("ide_judge_drift_receipt_path"), str)
        else None
    )
    if require_ide_judge_drift or drift_ref is not None:
        from apps_eval.graders.judge.drift_monitor import verify_ide_judge_drift_receipt

        eff_root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[1]
        resolved_drift = (
            Path(drift_ref)
            if drift_ref is not None
            else (eff_root / "artifacts" / "eval_harness" / "ide_judge_drift_receipt.json")
        )
        drift_ok, drift_viols, drift_metrics = verify_ide_judge_drift_receipt(
            resolved_drift, repo_root=eff_root
        )
        checks["ide_judge_drift"] = drift_ok
        if not drift_ok:
            blocking.extend(drift_viols)

    if regressions:
        status, exit_code = "REGRESSION", 2
    elif blocking:
        status, exit_code = "BLOCKED", 1
    else:
        status, exit_code = "PASS", 0

    return PromotionGateResult(
        status=status,
        exit_code=exit_code,
        manifest_path=path.as_posix(),
        checks=checks,
        blocking_reasons=blocking,
        regression_reasons=regressions,
        metrics={
            "suite_scores": suite_scores,
            "g6": g6_metrics,
            "rg_g6": rg_g6_metrics,
            "golden_flywheel": golden_metrics,
            "ide_judge_drift": drift_metrics,
            "elapsed_s": manifest.get("elapsed_s", 0.0),
        },
    )
