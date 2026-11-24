"""Wave 5 tests for fail-closed promotion gate (apps_rg G5/G6 + IDE judge drift verification)."""

from __future__ import annotations

import json
from pathlib import Path

from apps_eval.harness_orchestrator import EVIDENCE_MANIFEST_SCHEMA_VERSION
from apps_eval.promotion_gate import verify_promotion_evidence

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_base_manifest() -> dict:
    return {
        "schema_version": EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "app_filter": "apps_rg",
        "fast_dev": False,
        "suite_receipts": {
            "apps_rg.dev.resume_generation": {
                "finding_count": 4,
                "passed_findings": 4,
                "verdict": "pass",
                "suite_passed": True,
                "score": 1.0,
                "baseline_comparison": {"compared": True, "delta": 0.0, "verdict": "pass"},
            },
            "apps_rg.holdout.resume_generation": {
                "finding_count": 4,
                "passed_findings": 4,
                "verdict": "pass",
                "suite_passed": True,
                "score": 1.0,
                "baseline_comparison": {"compared": True, "delta": 0.0, "verdict": "pass"},
            },
        },
        "l6_shadow_handoff_receipts": {
            "apps_rg.dev.resume_generation": {"present": True, "sha256": "a" * 64},
            "apps_rg.holdout.resume_generation": {"present": True, "sha256": "b" * 64},
        },
        "apps_rg_e2e_receipt": {"status": "PASS"},
        "apps_rg_g5_g6_receipt": {
            "status": "PASS",
            "g5": {"passed": True, "max_std": 0.0},
            "g6": {
                "passed": True,
                "corpus_size": 96,
                "spearman_rho": 0.937893,
                "cohens_kappa": 1.0,
                "fpr": 0.0,
                "tpr": 1.0,
            },
        },
        "release_gate_receipt": {"status": "pass"},
    }


def test_promotion_gate_requires_apps_rg_g5_g6_and_blocks_on_planted_defect_slip(tmp_path: Path) -> None:
    manifest_path = tmp_path / "evidence_manifest.json"
    good_manifest = _make_base_manifest()
    manifest_path.write_text(json.dumps(good_manifest, indent=2), encoding="utf-8")

    res_ok = verify_promotion_evidence(manifest_path, repo_root=REPO_ROOT)
    assert res_ok.passed is True
    assert res_ok.checks.get("apps_rg_g5_g6") is True
    assert res_ok.metrics["rg_g6"]["corpus_size"] == 96
    assert res_ok.metrics["rg_g6"]["fpr"] == 0.0
    assert res_ok.metrics["rg_g6"]["tpr"] == 1.0

    # If a planted defect slips through (e.g. clean FPR > 0 or defect TPR < 0.90), promotion fails closed
    bad_manifest = _make_base_manifest()
    bad_manifest["apps_rg_g5_g6_receipt"]["g6"]["tpr"] = 0.75
    manifest_path.write_text(json.dumps(bad_manifest, indent=2), encoding="utf-8")
    res_bad = verify_promotion_evidence(manifest_path, repo_root=REPO_ROOT)
    assert res_bad.passed is False
    assert res_bad.status == "BLOCKED"
    assert res_bad.checks.get("apps_rg_g5_g6") is False


def test_promotion_gate_fails_closed_when_ide_judge_drift_required_and_missing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(_make_base_manifest(), indent=2), encoding="utf-8")
    missing_drift = tmp_path / "missing_drift_receipt.json"
    res = verify_promotion_evidence(
        manifest_path,
        require_ide_judge_drift=True,
        ide_judge_drift_receipt_path=missing_drift,
        repo_root=REPO_ROOT,
    )
    assert res.passed is False
    assert res.status == "BLOCKED"
    assert res.checks.get("ide_judge_drift") is False

    receipt_path = REPO_ROOT / "reports" / "wave5_fail_closed_promotion_gate_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "wave": "W5",
                "apps_rg_g5_g6_enforced": True,
                "planted_defect_slip_blocked": True,
                "missing_ide_judge_drift_blocked": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
