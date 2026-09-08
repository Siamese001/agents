"""Unit tests for the Resume Run Recovery Agent."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apps_rg.runtime.orchestration.ResumeRunRecoveryAgent import (
    RESUME_RUN_RECOVERY_RECEIPT_FILENAME,
    ResumeRunRecoveryAgent,
    ResumeRunRecoveryReceipt,
    is_resume_run_recovery_enabled,
)


class TestResumeRunRecoveryAgent(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.artifact_dir = Path(self.tmp_dir.name)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_identify_failing_lanes_from_signals_and_lane_rows(self) -> None:
        agent = ResumeRunRecoveryAgent(artifact_dir=self.artifact_dir)

        mock_exit = {
            "signals": {
                "core_x3_non_authorizing_lanes": ["headline"],
                "authoritative_lane_contract_failed_lanes": ["competencies"],
                "lane_rows": [
                    {
                        "lane": "unify_bullets",
                        "x3_code": "X3A_DENY_REROUTE",
                        "x2_failed": 1,
                        "product_quality_status": "BLOCKED",
                    },
                    {
                        "lane": "ibm_bullets",
                        "x3_code": "X3D_ALLOW_FINISH",
                        "x2_failed": 0,
                        "product_quality_status": "PASS",
                    },
                ],
            },
            "aggregated_from_lane_x3": [
                {"lane": "headline", "x3_code": "X3A_DENY_REROUTE"},
                {"lane": "competencies", "x3_code": "X3A_DENY_REROUTE"},
                {"lane": "unify_bullets", "x3_code": "X3A_DENY_REROUTE"},
                {"lane": "ibm_bullets", "x3_code": "X3D_ALLOW_FINISH"},
            ],
        }

        failing = agent.identify_failing_lanes(mock_exit)
        self.assertIn("headline", failing)
        self.assertIn("competencies", failing)
        self.assertIn("unify_bullets", failing)
        self.assertNotIn("ibm_bullets", failing)

    def test_identify_failing_lanes_with_exec_summary_blocked(self) -> None:
        agent = ResumeRunRecoveryAgent(artifact_dir=self.artifact_dir)
        mock_exit = {"signals": {}, "aggregated_from_lane_x3": []}
        exec_block = {"blocked": True, "x3_disposition": "X3A_DENY_REROUTE"}

        failing = agent.identify_failing_lanes(mock_exit, exec_summary_block=exec_block)
        self.assertIn("executive_summary", failing)

    def test_can_attempt_recovery_disabled_via_env(self) -> None:
        agent = ResumeRunRecoveryAgent(artifact_dir=self.artifact_dir)
        mock_exit = {
            "signals": {"core_x3_non_authorizing_lanes": ["headline"]},
        }

        with patch.dict(os.environ, {"APPS_RG_X3_RECOVERY_ENABLED": "0"}):
            self.assertFalse(agent.can_attempt_recovery(mock_exit))

        with patch.dict(os.environ, {"APPS_RG_X3_RECOVERY_ENABLED": "1"}):
            self.assertTrue(agent.can_attempt_recovery(mock_exit))

    def test_can_attempt_recovery_exhausted(self) -> None:
        agent = ResumeRunRecoveryAgent(artifact_dir=self.artifact_dir, max_attempts=1)
        receipt = ResumeRunRecoveryReceipt(recovery_attempt=1, max_recovery_attempts=1)
        receipt.persist(self.artifact_dir)

        mock_exit = {
            "signals": {"core_x3_non_authorizing_lanes": ["headline"]},
        }
        self.assertFalse(agent.can_attempt_recovery(mock_exit))

    def test_recovery_receipt_digest_and_persistence(self) -> None:
        receipt = ResumeRunRecoveryReceipt(
            recovery_triggered=True,
            trigger_x3_disposition="X3A_DENY_REROUTE",
            failed_lanes_identified=["headline", "competencies"],
            recovered_successfully=True,
        )
        saved_path = receipt.persist(self.artifact_dir)
        self.assertTrue(saved_path.is_file())

        data = json.loads(saved_path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], "apps_rg_x3_lane_recovery_receipt_v1")
        self.assertEqual(data["failed_lanes_identified"], ["headline", "competencies"])
        self.assertTrue(data["recovered_successfully"])
        self.assertTrue(data["digest"].startswith("sha256:"))

    def test_attempt_recovery_orchestration(self) -> None:
        agent = ResumeRunRecoveryAgent(
            artifact_dir=self.artifact_dir,
            dispatch_fn=lambda **kwargs: {"exit_status": "success"},
            aggregate_fn=lambda *args, **kwargs: {"decisive_status": "PASS"},
        )

        mock_exit = {
            "x3_disposition": "X3A_DENY_REROUTE",
            "status": "BLOCKED",
            "signals": {"core_x3_non_authorizing_lanes": ["headline"]},
            "aggregated_from_lane_x3": [{"lane": "headline", "x3_code": "X3A_DENY_REROUTE"}],
        }

        updated_exit = {
            "x3_disposition": "X3D_ALLOW_FINISH",
            "status": "PASS",
            "signals": {},
        }

        with patch(
            "apps_rg.runtime.orchestration.patch_run.build_patch_plan"
        ) as mock_plan, patch(
            "apps_rg.runtime.orchestration.patch_run.execute_patch_run"
        ) as mock_exec, patch(
            "apps_rg.runtime.whole_run_exit.emit_whole_run_exit_review_packet"
        ) as mock_emit, patch(
            "apps_rg.runtime.executive_summary_certification.executive_summary_certification_block"
        ) as mock_exec_summary:

            mock_plan.return_value = MagicMock(target_lanes=["headline"])
            mock_exec.return_value = {"exit_code": 0, "target_lanes": ["headline"]}
            mock_emit.return_value = updated_exit
            mock_exec_summary.return_value = {"blocked": False, "x3_disposition": "X3D_ALLOW_FINISH"}

            out_exit, effective_x3, exec_blocked = agent.attempt_recovery(
                whole_run_exit=mock_exit,
                whole_run_exit_identity={"run_id": "test_run"},
                raw_request={},
            )

            self.assertEqual(effective_x3, "X3D_ALLOW_FINISH")
            self.assertFalse(exec_blocked)
            self.assertEqual(out_exit["status"], "PASS")

            receipt_file = self.artifact_dir / RESUME_RUN_RECOVERY_RECEIPT_FILENAME
            self.assertTrue(receipt_file.is_file())
            receipt_data = json.loads(receipt_file.read_text(encoding="utf-8"))
            self.assertTrue(receipt_data["recovered_successfully"])
            self.assertEqual(receipt_data["lanes_re_dispatched"], ["headline"])


if __name__ == "__main__":
    unittest.main()
