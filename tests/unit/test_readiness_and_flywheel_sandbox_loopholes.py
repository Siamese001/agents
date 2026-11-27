"""Wave 5 unmocked regression tests for readiness dry-run/missing-stage gates, flywheel sandbox locks/drift, and guardian registry."""

from __future__ import annotations

import json
from pathlib import Path

from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.longitudinal import LongitudinalEvalEntry, LongitudinalEvaluationTracker
from tools.run_eval_flywheel_cycle import run_eval_flywheel_cycle
from tools.verify_commit import _analyze_single_python_file
from tools.verify_main_readiness import _load_prior_passing_stages, verify_main_readiness


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_readiness_dry_run_never_writes_live_receipt_and_missing_stage_fails_closed(tmp_path: Path) -> None:
    """Prove `--dry-run` cannot forge a reusable PASS receipt and missing stage targets fail closed (LH-10)."""
    # 1. Missing mandatory stage files in tmp_path must fail closed (rc == 1) even under --dry-run
    rc_missing = verify_main_readiness(tmp_path, branch="feat/missing-stages", dry_run=True, full=True)
    assert rc_missing == 1
    assert not (tmp_path / "reports" / "readiness" / "local_main_readiness_feat_missing_stages_receipt.json").exists()

    # 2. _load_prior_passing_stages must reject dry_run=True receipts
    forged = tmp_path / "forged_dry_run_receipt.json"
    forged.write_text(
        json.dumps(
            {
                "branch": "feat/x",
                "dry_run": True,
                "terminal_outcome": "DRY_RUN_PREVIEW",
                "stages": [{"stage_name": "1. Tier 1 Structural Governance", "status": "PASS"}],
            }
        ),
        encoding="utf-8",
    )
    assert _load_prior_passing_stages(forged) == set()


def test_flywheel_sandbox_preserves_rollback_locks_and_longitudinal_drift(tmp_path: Path) -> None:
    """Prove `--sandbox` snapshots live learning_ledger.sqlite locks and evaluates evidence_manifest.json drift (LH-09)."""
    src = tmp_path / "artifacts" / "learning"
    out = tmp_path / "sandbox_out"
    src.mkdir(parents=True)

    # 1. Seed a live learning_ledger.sqlite with an active rollback lock
    live_ledger = SqliteLearningLedgerStore(src / "learning_ledger.sqlite")
    try:
        live_ledger.set_rollback_lock(
            target_path="config/governance/auto_apply_policy.yaml",
            target_key="bounded.test_threshold",
            proposal_id="prop_rb_001",
            lock_days=7,
            reason="Simulated canary regression lock",
        )
    finally:
        live_ledger.close()

    # 2. Seed longitudinal baseline + regressed latest evidence_manifest.json
    seed_tracker = LongitudinalEvaluationTracker(src / "longitudinal_eval_ledger.json")
    seed_tracker.record_entry(
        LongitudinalEvalEntry(
            run_id="anchor_001",
            timestamp="2026-11-01T00:00:00Z",
            pipeline_version="git:aaa111:cfg001",
            rubric_version="rubric.v1",
            benchmark_suite="apps_lic.dev.outreach_message",
            model_id="local-deterministic",
            reasoning_effort="low",
            metrics={"score": 0.96, "grader_pass_rate": 0.96},
            gates={"suite_passed": True},
            git_commit="aaa111",
        )
    )
    harness_latest = tmp_path / "artifacts" / "eval_harness" / "latest"
    harness_latest.mkdir(parents=True)
    (harness_latest / "evidence_manifest.json").write_text(
        json.dumps(
            {
                "git_sha": "bbb222",
                "rubric_version": "rubric.v1",
                "suite_receipts": {
                    "apps_lic.dev.outreach_message": {
                        "record_id": "regressed_002",
                        "score": 0.50,
                        "finding_count": 10,
                        "passed_findings": 5,
                        "suite_passed": False,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    code, receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src,
        output_root=out,
        sandbox=True,
        active_rubric_version="rubric.v1",
    )

    # Sandbox ledger must contain the snapshotted rollback lock!
    sandbox_ledger = SqliteLearningLedgerStore(out / "learning_ledger.sqlite")
    try:
        lock = sandbox_ledger.get_active_rollback_lock(
            target_path="config/governance/auto_apply_policy.yaml",
            target_key="bounded.test_threshold",
        )
        assert lock is not None
        assert lock["proposal_id"] == "prop_rb_001"
    finally:
        sandbox_ledger.close()

    # Sandbox preflight must detect longitudinal drift (exit code 2)!
    assert code == 2
    assert len(receipt["drift_alerts"]) >= 1


def test_verify_commit_blocks_malformed_or_unregistered_guardian_comments(tmp_path: Path) -> None:
    """Prove Tier 1 `verify_commit` rejects malformed and unregistered `# guardian:` tags in production code (LH-12)."""
    reg_dir = tmp_path / "config" / "governance"
    reg_dir.mkdir(parents=True)
    (reg_dir / "guardian_exemption_registry.yaml").write_text(
        "schema_version: '1.0.0'\nsyntax_contract:\n  min_justification_chars: 8\nallowed_exemption_types:\n  - allow-silent-swallow\n",
        encoding="utf-8",
    )

    bad_prod = tmp_path / "agents" / "bad_guardian.py"
    bad_prod.parent.mkdir(parents=True)
    bad_prod.write_text(
        "def f() -> int:\n"
        "    try:\n"
        "        return 1\n"
        "    except ValueError:  # guardian: allow-fake-invented-type -- invented tag\n"
        "        return 0\n",
        encoding="utf-8",
    )

    _h, gov_errs, _p = _analyze_single_python_file(bad_prod, tmp_path)
    assert any("UNREGISTERED_GUARDIAN_EXEMPTION_TYPE" in e for e in gov_errs), gov_errs

    # String literal mentioning `# guardian:` must NOT trigger false positive
    clean_scanner = tmp_path / "tools" / "sample_scanner.py"
    clean_scanner.parent.mkdir(parents=True)
    clean_scanner.write_text(
        'def msg() -> str:\n    return "File contains \'# guardian:\' without rationale"\n',
        encoding="utf-8",
    )
    _h2, gov_errs2, _p2 = _analyze_single_python_file(clean_scanner, tmp_path)
    assert not any("Guardian Registry" in e for e in gov_errs2), gov_errs2
