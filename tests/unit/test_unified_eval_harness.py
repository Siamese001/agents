"""Wave 2 verification tests for the unified Resume & Outreach eval harness and promotion gate."""

from __future__ import annotations

import json
from pathlib import Path

from apps_eval.harness_orchestrator import run_unified_eval_harness
from apps_eval.promotion_gate import verify_promotion_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_unified_eval_harness_passes_end_to_end_and_fails_closed_on_mutations(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_out"
    manifest = run_unified_eval_harness(
        REPO_ROOT,
        app="all",
        mode="offline",
        include_holdout=True,
        out_dir=out_dir,
    )
    manifest_path = Path(manifest["manifest_path"])
    assert manifest_path.is_file()

    # 1. Clean manifest passes promotion gate
    gate_ok = verify_promotion_evidence(manifest_path, require_holdout=True, require_engine_probes=True)
    assert gate_ok.passed, f"unexpected failure: {gate_ok.to_dict()}"
    assert gate_ok.exit_code == 0
    assert gate_ok.status == "PASS"
    assert gate_ok.metrics["g6"]["corpus_size"] == 80
    assert gate_ok.metrics["g6"]["spearman_rho"] >= 0.70
    assert gate_ok.metrics["g6"]["cohens_kappa"] >= 0.65
    assert gate_ok.metrics["g6"]["fpr"] == 0.0
    assert gate_ok.metrics["g6"]["tpr"] >= 0.90

    # 2. Missing receipt fails closed with exit code 1 (BLOCKED)
    missing_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing_payload.pop("apps_rg_e2e_receipt", None)
    missing_path = tmp_path / "missing_receipt_manifest.json"
    missing_path.write_text(json.dumps(missing_payload, indent=2), encoding="utf-8")
    gate_blocked = verify_promotion_evidence(missing_path, require_holdout=True, require_engine_probes=True)
    assert not gate_blocked.passed
    assert gate_blocked.status == "BLOCKED"
    assert gate_blocked.exit_code == 1

    # 3. Baseline score regression fails closed with exit code 2 (REGRESSION)
    regressed_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    regressed_payload["suite_receipts"]["apps_lic.dev.outreach_message"]["baseline_comparison"]["delta"] = -0.15
    regressed_payload["suite_receipts"]["apps_lic.dev.outreach_message"]["baseline_comparison"]["verdict"] = "regression"
    regressed_path = tmp_path / "regressed_manifest.json"
    regressed_path.write_text(json.dumps(regressed_payload, indent=2), encoding="utf-8")
    gate_reg = verify_promotion_evidence(regressed_path, require_holdout=True, require_engine_probes=True)
    assert not gate_reg.passed
    assert gate_reg.status == "REGRESSION"
    assert gate_reg.exit_code == 2


def test_unified_eval_harness_fast_dev_mode(tmp_path: Path) -> None:
    manifest = run_unified_eval_harness(
        REPO_ROOT,
        app="all",
        mode="offline",
        include_holdout=False,
        fast_dev=True,
        out_dir=tmp_path / "fast_dev",
    )
    gate = verify_promotion_evidence(manifest["manifest_path"])
    assert gate.passed, f"fast_dev gate failed: {gate.to_dict()}"
    assert gate.exit_code == 0
