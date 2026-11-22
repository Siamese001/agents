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

    def test_attempt_recovery_redispatches_soft_fail_lane_end_to_end(self) -> None:
        from apps_rg.runtime.orchestration.patch_run import GENERATED_LANES

        repo = (self.artifact_dir / "repo").resolve()
        run_dir = repo / "artifacts" / "apps_rg" / "e2e_soft_fail" / "attempt_1"
        sections_root = run_dir / "modular_r4" / "sections"
        (repo / "config").mkdir(parents=True, exist_ok=True)
        (repo / "config" / "jd.txt").write_text("Lead AI platform architecture.", encoding="utf-8")
        (repo / "config" / "brief.md").write_text("Executive briefing.", encoding="utf-8")
        (run_dir / "ingress_raw.json").parent.mkdir(parents=True, exist_ok=True)
        (run_dir / "ingress_raw.json").write_text(
            json.dumps(
                {
                    "target_company": "Anthropic",
                    "target_role": "Manager",
                    "generation_mode": "strategic_tailor",
                    "manual_brief": "config/brief.md",
                }
            ),
            encoding="utf-8",
        )

        def _write_lane(lane: str, x3_code: str) -> None:
            rd = sections_root / lane / "real" / f"{lane}_run1"
            rd.mkdir(parents=True, exist_ok=True)
            (rd / "l2_output.json").write_text(
                json.dumps(
                    {
                        "section_id": lane,
                        "runtime_generation_status": "REAL_LLM",
                        "product_quality_status": "PASS",
                    }
                ),
                encoding="utf-8",
            )
            (rd / "x3_disposition.json").write_text(json.dumps({"x3_code": x3_code}), encoding="utf-8")
            (rd / "x2_gate_outputs.json").write_text(
                json.dumps({"x2_passed": 1, "x2_failed": 0, "total_x2_gates": 1, "failed_gates": []}),
                encoding="utf-8",
            )
            (rd / "provider_request.json").write_text(
                json.dumps({"provider_requested": "external_claude", "provider_attempted": True}),
                encoding="utf-8",
            )
            (rd / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": f"{lane}_run1",
                        "section_id": lane,
                        "provider_requested": "external_claude",
                        "provider_attempted": True,
                        "runtime_generation_status": "REAL_LLM",
                        "command": f"--target-company Anthropic --target-role Manager --jd config/jd.txt --manual-brief config/brief.md --artifact-dir {run_dir}",
                    }
                ),
                encoding="utf-8",
            )
            ptr = {"run_id": f"{lane}_run1", "run_dir": rd.relative_to(repo).as_posix(), "section_id": lane}
            (sections_root / lane / "latest_real_run.json").write_text(json.dumps(ptr), encoding="utf-8")
            (sections_root / lane / "latest_successful_real_run.json").write_text(json.dumps(ptr), encoding="utf-8")

        for lane in GENERATED_LANES:
            _write_lane(lane, "X3_REVIEW_JUDGE_SOFT_FAIL" if lane == "headline" else "X3_ALLOW")

        dispatched: list[str] = []

        def _dispatch(*, plan: object, lane: str, lane_provider: str, **kw: object) -> dict[str, object]:
            dispatched.append(lane)
            _write_lane(lane, "X3_ALLOW")
            return {"exit_status": "success", "x3_disposition": "X3_ALLOW"}

        agent = ResumeRunRecoveryAgent(
            artifact_dir=run_dir,
            dispatch_fn=_dispatch,
            aggregate_fn=lambda *a, **k: {
                "decisive_status": "PASS",
                "failure_reason": "",
                "full_success_eligibility": {"eligible": True, "reasons": []},
            },
        )
        mock_exit = {
            "x3_disposition": "X3A_DENY_REROUTE",
            "status": "BLOCKED",
            "signals": {"core_x3_non_authorizing_lanes": ["headline"]},
            "aggregated_from_lane_x3": [{"lane": "headline", "x3_code": "X3_REVIEW_JUDGE_SOFT_FAIL"}],
        }
        updated_exit = {"x3_disposition": "X3D_ALLOW_FINISH", "status": "PASS", "signals": {}}
        with patch(
            "apps_rg.runtime.orchestration.patch_run.find_repo_root",
            return_value=repo,
        ), patch(
            "apps_rg.runtime.embedding_settings.bootstrap_apps_rg_embedding_env",
            return_value={},
        ), patch(
            "apps_rg.runtime.embedding_settings.apply_apps_rg_embedding_env_guards",
            return_value=object(),
        ), patch(
            "apps_rg.runtime.embedding_settings.write_embedding_settings_receipt",
            return_value=None,
        ), patch.dict(
            os.environ,
            {
                "APPS_RG_ROUTE_HMAC_SECRET": "a" * 64,
                "APPS_RG_ROUTE_HMAC_KEY_ID": "test-key",
            },
        ), patch(
            "apps_rg.runtime.whole_run_exit.emit_whole_run_exit_review_packet",
            return_value=updated_exit,
        ), patch(
            "apps_rg.runtime.executive_summary_certification.executive_summary_certification_block",
            return_value={"blocked": False, "x3_disposition": "X3D_ALLOW_FINISH"},
        ):
            _, effective_x3, exec_blocked = agent.attempt_recovery(
                whole_run_exit=mock_exit,
                whole_run_exit_identity={"run_id": "attempt_1"},
                raw_request={},
            )
        self.assertEqual(dispatched, ["headline"])
        self.assertEqual(effective_x3, "X3D_ALLOW_FINISH")
        self.assertFalse(exec_blocked)

    def test_identify_failing_lanes_covers_all_assembly_coherence_and_exit_signals(self) -> None:
        asm_dir = self.artifact_dir / "modular_r4" / "final_resume_assembly"
        asm_dir.mkdir(parents=True, exist_ok=True)

        # 1. full_resume_llm_coherence_review.json with judge_verdicts
        (asm_dir / "full_resume_llm_coherence_review.json").write_text(
            json.dumps(
                {
                    "full_resume_coherence_pass": False,
                    "decisive_reason": "judge_blockers",
                    "judge_verdicts": [
                        {
                            "pass": False,
                            "provider_status": "MODEL_BACKED_FAIL",
                            "findings": ["IBM narrative lacks concrete architecture details."],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        # 2. Real-shaped nested x1d_full_resume_judge_outputs.json with quorum_not_met
        (asm_dir / "x1d_full_resume_judge_outputs.json").write_text(
            json.dumps(
                {
                    "judges": [],
                    "aggregation": {
                        "full_resume_coherence_pass": False,
                        "quorum_met": False,
                        "decisive_reason": "quorum_not_met",
                        "blockers": ["credential_duplication_in_competencies:aws"],
                    },
                }
            ),
            encoding="utf-8",
        )
        # 3. final_resume_x2_gate_outputs.json with lane only in observed_value
        (asm_dir / "final_resume_x2_gate_outputs.json").write_text(
            json.dumps(
                {
                    "all_pass": False,
                    "gates": [
                        {
                            "gate_id": "x2_generated_sections_from_latest_successful_real",
                            "pass": False,
                            "observed_value": ["unify_bullets"],
                            "failure_reason": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        # 4. review_lane_policy.json with review_lanes
        (asm_dir / "review_lane_policy.json").write_text(
            json.dumps(
                {
                    "summary": {"review_lanes": ["slalom_narrative"], "product_allow_claimed": False},
                    "per_lane": [{"lane": "slalom_narrative", "disposition_class": "REVIEW", "x3_code": "X3_REVIEW_JUDGE_SOFT_FAIL"}],
                }
            ),
            encoding="utf-8",
        )

        agent = ResumeRunRecoveryAgent(artifact_dir=self.artifact_dir)
        failing = agent.identify_failing_lanes(
            {
                "x3_disposition": "X3A_DENY_REROUTE",
                "status": "BLOCKED",
                "signals": {
                    "mirror_authority_violation_lanes": ["headline"],
                    "lane_authority_rows": [
                        {"lane": "insurtech_bullets", "authorized": False, "authoritative_x3_code": "X3_BLOCK"}
                    ],
                    "final_assembly_authority_failed_checks": ["review_policy_product_allow_claimed"],
                    "final_resume_output_failed_gate_ids": ["final_resume_no_gap_markers"],
                },
            }
        )
        for expected in ("competencies", "unify_bullets", "ibm_narrative", "slalom_narrative", "insurtech_bullets", "headline"):
            self.assertIn(expected, failing)

    def test_identify_failing_lanes_probes_exec_summary_cert_when_none_and_handles_generic_quorum_fail(self) -> None:
        asm_dir = self.artifact_dir / "modular_r4" / "final_resume_assembly"
        asm_dir.mkdir(parents=True, exist_ok=True)
        (asm_dir / "x1d_full_resume_judge_outputs.json").write_text(
            json.dumps(
                {
                    "judges": [],
                    "aggregation": {
                        "full_resume_coherence_pass": False,
                        "quorum_met": False,
                        "decisive_reason": "quorum_not_met",
                        "blockers": ["judge_quorum_insufficient"],
                    },
                }
            ),
            encoding="utf-8",
        )
        agent = ResumeRunRecoveryAgent(artifact_dir=self.artifact_dir)
        with patch(
            "apps_rg.runtime.executive_summary_certification.executive_summary_certification_block",
            return_value={"blocked": True, "blocking_judge_ids": ["gemini_pro"], "publish_disposition": "judge_certification_required"},
        ):
            failing = agent.identify_failing_lanes(
                {
                    "signals": {
                        "judge_quorum_satisfied": False,
                        "x1d_overall": "BLOCKED",
                        "final_assembly_authority_failed_checks": ["assembly_product_release_eligible"],
                    }
                },
                exec_summary_block=None,
            )
        self.assertEqual(failing, ["executive_summary"])

    def test_default_dispatch_lane_honors_cancel_event_and_forwards_all_recovery_directives(self) -> None:
        import threading
        from apps_rg.runtime.orchestration.patch_run import _default_dispatch_lane
        from apps_rg.runtime.providers.wallclock_http_guard import current_cancel_event

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
        pre_cancelled = threading.Event()
        pre_cancelled.set()
        res_cancelled = _default_dispatch_lane(
            plan=fake_plan,
            lane="headline",
            lane_provider="external_claude",
            cancel_event=pre_cancelled,
        )
        self.assertEqual(res_cancelled["fault"], "cancelled")
        self.assertEqual(res_cancelled["exit_status"], "error")

        active_ev = threading.Event()
        observed_tls_ev: list[Any] = []
        directives = {
            "lane_overrides": {
                "headline": {
                    "temperature": 0.44,
                    "force_new_seed": True,
                    "reasoning_effort": "medium",
                    "diagnostic_focus": "Avoid third-person opener.",
                }
            }
        }

        def _capture_primitives(**kw: Any) -> dict[str, Any]:
            observed_tls_ev.append(current_cancel_event())
            return {"exit_status": "success", "captured": kw}

        with patch.dict(
            os.environ,
            {"APPS_RG_RECOVERY_DIRECTIVES_JSON": json.dumps(directives)},
        ), patch(
            "apps_rg.runtime.orchestration.canonical_dispatch.run_canonical_apps_rg_from_cli_primitives",
            side_effect=_capture_primitives,
        ):
            res_ok = _default_dispatch_lane(
                plan=fake_plan,
                lane="headline",
                lane_provider="external_claude",
                cancel_event=active_ev,
            )
        self.assertEqual(observed_tls_ev, [active_ev])
        kw = res_ok["captured"]
        self.assertAlmostEqual(kw["lane_temperature"], 0.44)
        self.assertEqual(kw["diagnostic_focus"], "Avoid third-person opener.")
        self.assertTrue(kw["force_new_seed"])
        self.assertEqual(kw["reasoning_effort"], "medium")

    def test_identify_failing_lanes_ignores_cross_section_warn_and_catches_fail(self) -> None:
        asm_dir = self.artifact_dir / "modular_r4" / "final_resume_assembly"
        asm_dir.mkdir(parents=True, exist_ok=True)
        cross_path = asm_dir / "cross_section_x2_gate_outputs.json"

        # 1. Advisory WARN gate emits pass=False in CrossSectionGateResult.to_dict(), must NOT implicate healthy lanes
        cross_path.write_text(
            json.dumps(
                {
                    "gates": [
                        {
                            "gate_id": "x2_cross_section_section_intent_conflict",
                            "verdict": "WARN",
                            "observed": ["executive_summary_vs_slalom_bullets_cosine(S1_vs_B1=0.38>0.35)"],
                            "pass": False,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        agent = ResumeRunRecoveryAgent(artifact_dir=self.artifact_dir)
        mock_exit = {
            "x3_disposition": "X3A_DENY_REROUTE",
            "status": "BLOCKED",
            "signals": {"core_x3_non_authorizing_lanes": ["headline"]},
        }
        failing_warn = agent.identify_failing_lanes(mock_exit, exec_summary_block={"blocked": False})
        self.assertEqual(failing_warn, ["headline"])

        # 2. Blocking FAIL and UNKNOWN verdicts MUST implicate the referenced lane
        cross_path.write_text(
            json.dumps(
                {
                    "gates": [
                        {
                            "gate_id": "x2_cross_section_section_intent_conflict",
                            "verdict": "WARN",
                            "observed": ["executive_summary_vs_ibm_bullets_cosine(S1_vs_B1=0.38>0.35)"],
                            "pass": False,
                        },
                        {
                            "gate_id": "x2_cross_section_duplicate_claim",
                            "verdict": "FAIL",
                            "observed": ["slalom_bullets"],
                            "pass": False,
                        },
                        {
                            "gate_id": "x2_cross_section_metric_consistency",
                            "verdict": "UNKNOWN",
                            "observed": ["unify_bullets"],
                            "pass": False,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        failing_fail = agent.identify_failing_lanes(mock_exit, exec_summary_block={"blocked": False})
        self.assertEqual(failing_fail, ["slalom_bullets", "unify_bullets", "headline"])


if __name__ == "__main__":
    unittest.main()


