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
            self.assertIn("headline", receipt_data["details"]["rca_diagnostic_loop"]["lane_overrides"])
            self.assertTrue(receipt_data["details"]["patch_result"]["lane_overrides_bound"])
            _, kwargs = mock_exec.call_args
            self.assertIn("recovery_directives", kwargs)
            self.assertIn("headline", kwargs["recovery_directives"]["lane_overrides"])

    def test_patch_run_default_dispatch_lane_applies_recovery_directive_temperature(self) -> None:
        from apps_rg.runtime.orchestration.patch_run import _default_dispatch_lane

        fake_plan = MagicMock()
        fake_plan.run_dir = self.artifact_dir
        fake_plan.targeting = MagicMock(
            target_company="Anthropic",
            target_role="SVP Engineering",
            target_level="SVP",
            job_description_ref="",
            job_description_text="Lead distributed systems.",
            manual_brief="",
            generation_mode="strategic_tailor",
        )
        directives = {"lane_overrides": {"headline": {"temperature": 0.42}}}

        with patch.dict(
            os.environ,
            {"APPS_RG_RECOVERY_DIRECTIVES_JSON": json.dumps(directives)},
        ), patch(
            "apps_rg.runtime.orchestration.canonical_dispatch.run_canonical_apps_rg_from_cli_primitives",
            return_value={"exit_status": "success"},
        ) as mock_canonical:
            res = _default_dispatch_lane(plan=fake_plan, lane="headline", lane_provider="external_claude")
            self.assertEqual( res["exit_status"], "success")
            _, call_kw = mock_canonical.call_args
            self.assertAlmostEqual(call_kw["lane_temperature"], 0.42)

    def test_rewind_product_stage_ledger_to_l0_refuses_pre_l0_or_failed_l0(self) -> None:
        from apps_rg.runtime.e2e_stage_ledger import (
            E2E_STAGE_LEDGER_FILENAME,
            E2E_STAGE_LEDGER_V2_SCHEMA_VERSION,
            StageTransitionError,
        )
        from apps_rg.runtime.orchestration.patch_product_closeout import (
            _rewind_product_stage_ledger_to_l0,
        )

        ledger_path = self.artifact_dir / E2E_STAGE_LEDGER_FILENAME
        # Case 1: Ledger failed at FRESH_PREFLIGHT and never reached APPS_RG_L0
        ledger_path.write_text(
            json.dumps(
                {
                    "schema_version": E2E_STAGE_LEDGER_V2_SCHEMA_VERSION,
                    "entries": [
                        {"sequence": 0, "stage_id": "FRESH_PREFLIGHT", "status": "FAIL"},
                        {"sequence": 1, "stage_id": "TERMINAL_NON_PRODUCT", "status": "PASS"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(StageTransitionError) as ctx:
            _rewind_product_stage_ledger_to_l0(self.artifact_dir)
        self.assertIn("APPS_RG_L0 stage not reached", str(ctx.exception))

        # Case 2: Ledger reached APPS_RG_L0 but APPS_RG_L0 failed
        ledger_path.write_text(
            json.dumps(
                {
                    "schema_version": E2E_STAGE_LEDGER_V2_SCHEMA_VERSION,
                    "entries": [
                        {"sequence": 0, "stage_id": "FRESH_PREFLIGHT", "status": "PASS"},
                        {"sequence": 1, "stage_id": "APPS_RG_L0", "status": "FAIL"},
                        {"sequence": 2, "stage_id": "TERMINAL_NON_PRODUCT", "status": "PASS"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(StageTransitionError) as ctx2:
            _rewind_product_stage_ledger_to_l0(self.artifact_dir)
        self.assertIn("APPS_RG_L0 did not PASS", str(ctx2.exception))

        # Case 3: Non-v2 ledger
        ledger_path.write_text(
            json.dumps({"schema_version": "apps_rg.e2e_stage_ledger.v1", "entries": []}),
            encoding="utf-8",
        )
        with self.assertRaises(StageTransitionError) as ctx3:
            _rewind_product_stage_ledger_to_l0(self.artifact_dir)
        self.assertIn("cannot rewind non-v2 stage ledger", str(ctx3.exception))

    def test_rebind_preflight_if_needed_detects_corrupted_consumption_signature(self) -> None:
        from apps_rg.runtime.e2e_preflight import (
            E2E_PREFLIGHT_CONTINUATION_CONSUMPTION_FILENAME,
            E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME,
            E2E_PREFLIGHT_PRODUCT_ENTRY_RECEIPT_FILENAME,
            E2E_PREFLIGHT_RECEIPT_FILENAME,
            _continuation_body,
            _payload_digest,
            _sha256_bytes,
            _signature,
        )
        from apps_rg.runtime.orchestration.patch_product_closeout import (
            _rebind_preflight_if_needed,
        )

        secret = "a" * 64
        key_id = "session-key-test1234"
        identity = {
            "producer_app_id": "apps_research",
            "consumer_app_id": "apps_rg",
            "parent_run_id": "run-1",
            "child_run_id": "child-1",
            "request_id": "req-1",
            "trace_root": "trace-1",
            "tenant_id": "default",
            "target_company": "Brown & Brown",
            "target_role": "SVP IT Strategy",
            "jd_sha256": "sha256:" + "1" * 64,
            "brief_sha256": "sha256:" + "2" * 64,
            "policy_hash": "sha256:" + "3" * 64,
            "blueprint_hash": "sha256:" + "4" * 64,
            "schema_version": "apps_research_rg_run_identity.v1",
        }
        cont_body = {
            "schema_version": "apps_rg.e2e_preflight.v1",
            "status": "PASS",
            "e2e_run_id": "run-1",
            "route_signing_key_id": key_id,
        }
        cont = {
            **cont_body,
            "continuation_payload_digest": _payload_digest(cont_body),
            "continuation_signature": _signature(secret, cont_body),
        }
        cont_path = self.artifact_dir / E2E_PREFLIGHT_CONTINUATION_RECEIPT_FILENAME
        cont_path.write_text(json.dumps(cont, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (self.artifact_dir / E2E_PREFLIGHT_RECEIPT_FILENAME).write_text("{}", encoding="utf-8")

        cons_body = {
            "schema_version": "apps_rg.e2e_preflight_consumption.v1",
            "e2e_run_id": "run-1",
            "consumer_id": "apps_rg.whole_run.primary",
            "continuation_ref": cont_path.name,
            "continuation_sha256": _sha256_bytes(cont_path.read_bytes()),
            "continuation_payload_digest": cont["continuation_payload_digest"],
        }
        # Valid continuation signature, but corrupted consumption signature
        cons = {**cons_body, "consumption_signature": "hmac-sha256:corrupted"}
        cons_path = self.artifact_dir / E2E_PREFLIGHT_CONTINUATION_CONSUMPTION_FILENAME
        cons_path.write_text(json.dumps(cons, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        entry_path = self.artifact_dir / E2E_PREFLIGHT_PRODUCT_ENTRY_RECEIPT_FILENAME
        entry_path.write_text(json.dumps({"created_at_utc": "2026-11-12T00:00:00Z"}), encoding="utf-8")

        with patch.dict(
            os.environ,
            {"APPS_RG_ROUTE_HMAC_SECRET": secret, "APPS_RG_ROUTE_HMAC_KEY_ID": key_id},
        ):
            rebound = _rebind_preflight_if_needed(self.artifact_dir, identity)
            self.assertTrue(rebound)
            updated_cons = json.loads(cons_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_cons["consumption_signature"], _signature(secret, cons_body))
            # Second call with valid signatures returns False
            self.assertFalse(_rebind_preflight_if_needed(self.artifact_dir, identity))

    def test_apply_route_signing_posture_repairs_corrupted_hmac_file(self) -> None:
        from apps_rg.runtime.env_bootstrap import apply_route_signing_posture

        gov_dir = self.artifact_dir / ".local" / "governance"
        gov_dir.mkdir(parents=True, exist_ok=True)
        key_file = gov_dir / "ephemeral_dev_route_hmac.json"
        key_file.write_text("{corrupted_json", encoding="utf-8")

        with patch(
            "apps_rg.runtime.worktree_path_resolution._git_common_checkout_root_str",
            return_value=str(self.artifact_dir),
        ), patch.dict(
            os.environ,
            {"APPS_RG_ROUTE_SIGNING_POSTURE": "ephemeral_dev"},
            clear=False,
        ):
            os.environ.pop("APPS_RG_ROUTE_HMAC_SECRET", None)
            os.environ.pop("APPS_RG_ROUTE_HMAC_KEY_ID", None)
            posture = apply_route_signing_posture(repo_root=self.artifact_dir)
            self.assertEqual(posture, "ephemeral_dev")
            repaired = json.loads(key_file.read_text(encoding="utf-8"))
            self.assertEqual(repaired["secret"], os.environ["APPS_RG_ROUTE_HMAC_SECRET"])
            self.assertEqual(repaired["key_id"], os.environ["APPS_RG_ROUTE_HMAC_KEY_ID"])


if __name__ == "__main__":
    unittest.main()


