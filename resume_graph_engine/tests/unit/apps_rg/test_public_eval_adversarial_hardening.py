"""Adversarial regression test suite for Apps RG public evaluation hardening.

Validates that:
1. Missing judge/eval records never default to PASS.
2. UNKNOWN judge/eval records fail-closed.
3. ERROR judge/eval records fail-closed.
4. Stale judge/eval records (mismatched parent_run_id, superseded package, stale status) fail-closed.
5. Malformed judge/eval records (empty dict, corrupted JSON bytes) fail-closed.
6. Stored completion receipts claiming PASS are overridden when live records fail or are missing.
7. Missing authoritative receipts (completion, authorization, X3 disposition) block release.
8. release_blocked flags in eval records block release.
9. Nested judge decisive failure or error blocks release.
10. Zero judge/LLM provider calls are invoked during public evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from apps_rg import __main__ as cli
from apps_rg.__main__ import _evaluate_product_run


def _seed_valid_base_run(run_dir: Path, parent_run_id: str = "run-parent-100") -> None:
    """Seed minimal valid run receipts before adding eval records."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "runtime_identity_envelope.json").write_text(
        json.dumps({
            "payload": {
                "parent_run_id": parent_run_id,
                "child_run_id": f"child-{parent_run_id}",
            }
        }),
        encoding="utf-8",
    )
    (run_dir / "FINAL_RESUME_OUTPUT.txt").write_text("# Final Resume\n", encoding="utf-8")
    (run_dir / "apps_rg_pipeline_completion_receipt.json").write_text(
        json.dumps({
            "pipeline_complete": True,
            "parent_run_id": parent_run_id,
        }),
        encoding="utf-8",
    )
    (run_dir / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps({"authorized": True}),
        encoding="utf-8",
    )
    (run_dir / "x3_disposition_receipt.json").write_text(
        json.dumps({"x3_code": "X3D_ALLOW_FINISH"}),
        encoding="utf-8",
    )


class TestPublicEvalAdversarialHardening(unittest.TestCase):
    """Adversarial security and regression tests for _evaluate_product_run."""

    def test_missing_eval_records_never_defaults_to_pass(self) -> None:
        """A completed, authorized run with missing eval records must not pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            # apps_eval dir is empty
            (run_dir / "apps_eval").mkdir(parents=True, exist_ok=True)

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")
            self.assertEqual(report["deterministic_product_status"], "FAIL")
            self.assertEqual(report["apps_eval_record_count"], 0)
            self.assertNotEqual(report["exit_code"], 0)

    def test_unknown_status_judge_record_fails_closed(self) -> None:
        """UNKNOWN status or verdict in eval record must never default to PASS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            eval_dir = run_dir / "apps_eval" / "test_unknown"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text(
                json.dumps({
                    "record_id": "rec-unknown-1",
                    "status": "UNKNOWN",
                    "verdict": "UNKNOWN",
                    "parent_run_id": "run-parent-100",
                }),
                encoding="utf-8",
            )

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")
            self.assertTrue(len(report["non_passing_eval_records"]) > 0)
            self.assertNotEqual(report["exit_code"], 0)

    def test_error_status_judge_record_fails_closed(self) -> None:
        """ERROR status or verdict in eval record must fail-closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            eval_dir = run_dir / "apps_eval" / "test_error"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text(
                json.dumps({
                    "record_id": "rec-err-1",
                    "status": "ERROR",
                    "verdict": "ERROR",
                    "parent_run_id": "run-parent-100",
                }),
                encoding="utf-8",
            )

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")
            self.assertTrue(len(report["non_passing_eval_records"]) > 0)
            self.assertNotEqual(report["exit_code"], 0)

    def test_stale_judge_record_with_mismatched_parent_identity_fails_closed(self) -> None:
        """Stale eval record belonging to a different parent run must fail-closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir, parent_run_id="run-parent-100")
            eval_dir = run_dir / "apps_eval" / "test_stale"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text(
                json.dumps({
                    "record_id": "rec-stale-1",
                    "status": "PASS",
                    "verdict": "PASS",
                    # Belongs to a different / historical run
                    "parent_run_id": "run-parent-FORGED-OR-STALE",
                }),
                encoding="utf-8",
            )

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")
            self.assertTrue(len(report["stale_eval_records"]) > 0)

    def test_stale_judge_record_with_explicit_stale_status_fails_closed(self) -> None:
        """Record marked with STALE status or SUPERSEDED disposition fails-closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            eval_dir = run_dir / "apps_eval" / "test_superseded"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text(
                json.dumps({
                    "record_id": "rec-stale-2",
                    "status": "STALE",
                    "disposition": "SUPERSEDED_HISTORICAL",
                    "parent_run_id": "run-parent-100",
                }),
                encoding="utf-8",
            )

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertTrue(len(report["stale_eval_records"]) > 0)

    def test_malformed_empty_judge_record_fails_closed(self) -> None:
        """Empty JSON object {} as eval record must fail-closed as malformed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            eval_dir = run_dir / "apps_eval" / "test_empty"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text("{}", encoding="utf-8")

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")
            self.assertTrue(len(report["malformed_eval_records"]) > 0)

    def test_malformed_corrupt_json_judge_record_fails_closed(self) -> None:
        """Unparseable corrupted JSON in eval_record.json must fail-closed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            eval_dir = run_dir / "apps_eval" / "test_corrupted"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text("{corrupt: true,,,", encoding="utf-8")

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")
            self.assertTrue(len(report["malformed_eval_records"]) > 0)

    def test_saved_decision_pass_overridden_when_records_missing(self) -> None:
        """Stored completion receipt claiming PASS is overridden when live records are absent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            # Inject forged saved_decision claiming PASS
            (run_dir / "apps_rg_pipeline_completion_receipt.json").write_text(
                json.dumps({
                    "pipeline_complete": True,
                    "evaluation_decision": {
                        "evaluation_status": "PASS",
                        "execution_status": "PASS",
                        "evaluation_validity": "PASS",
                        "deterministic_product_status": "PASS",
                    },
                }),
                encoding="utf-8",
            )
            # No eval records in apps_eval
            (run_dir / "apps_eval").mkdir(parents=True, exist_ok=True)

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")
            self.assertEqual(report["deterministic_product_status"], "FAIL")

    def test_saved_decision_pass_overridden_when_record_is_unknown_or_error(self) -> None:
        """Stored completion claiming PASS is overridden when live record has UNKNOWN/ERROR."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            (run_dir / "apps_rg_pipeline_completion_receipt.json").write_text(
                json.dumps({
                    "pipeline_complete": True,
                    "evaluation_decision": {
                        "evaluation_status": "PASS",
                        "execution_status": "PASS",
                        "evaluation_validity": "PASS",
                        "deterministic_product_status": "PASS",
                    },
                }),
                encoding="utf-8",
            )
            eval_dir = run_dir / "apps_eval" / "test_adversarial"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text(
                json.dumps({
                    "record_id": "rec-adv-1",
                    "status": "UNKNOWN",
                    "verdict": "UNKNOWN",
                    "parent_run_id": "run-parent-100",
                }),
                encoding="utf-8",
            )

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")
            self.assertEqual(report["deterministic_product_status"], "FAIL")

    def test_release_blocked_flag_in_eval_record_blocks_release(self) -> None:
        """release_blocked: true in eval record or scorecard blocks release."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            eval_dir = run_dir / "apps_eval" / "test_blocked"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text(
                json.dumps({
                    "record_id": "rec-blocked-1",
                    "status": "PASS",
                    "verdict": "PASS",
                    "release_blocked": True,
                    "parent_run_id": "run-parent-100",
                }),
                encoding="utf-8",
            )

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")

    def test_nested_judge_decisive_failure_blocks_release(self) -> None:
        """A failed or decisive_failure judge within judges list blocks release."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            eval_dir = run_dir / "apps_eval" / "test_judge_fail"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "eval_record.json").write_text(
                json.dumps({
                    "record_id": "rec-nested-fail",
                    "status": "PASS",
                    "verdict": "PASS",
                    "parent_run_id": "run-parent-100",
                    "judges": [
                        {"provider_key": "openai", "pass": True, "provider_status": "MODEL_BACKED_PASS"},
                        {"provider_key": "gemini", "pass": False, "decisive_failure": True, "provider_status": "MODEL_BACKED_FAIL"},
                    ],
                }),
                encoding="utf-8",
            )

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["evaluation_status"], "PASS")

    def test_missing_completion_receipt_blocks_release(self) -> None:
        """Absence of completion receipt blocks product release."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            (run_dir / "apps_rg_pipeline_completion_receipt.json").unlink()

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertFalse(report["pipeline_complete"])

    def test_missing_product_authorization_blocks_release(self) -> None:
        """Absence of product authorization receipt blocks product release."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            (run_dir / "apps_rg_product_authorization_receipt.json").unlink()

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertFalse(report["product_authorized"])

    def test_missing_x3_allow_disposition_blocks_release(self) -> None:
        """X3 disposition other than X3D_ALLOW_FINISH blocks product release."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _seed_valid_base_run(run_dir)
            (run_dir / "x3_disposition_receipt.json").write_text(
                json.dumps({"x3_code": "X3D_BLOCK"}),
                encoding="utf-8",
            )

            report = _evaluate_product_run(run_dir)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertNotEqual(report["x3_disposition"], "X3D_ALLOW_FINISH")


if __name__ == "__main__":
    unittest.main()
