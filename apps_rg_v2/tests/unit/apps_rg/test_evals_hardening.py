"""Unit tests verifying hardened evaluations subsystem (V2 Wave Plan).

Covers:
1. 4-plane decision derivation with strict Wave 5 precedence (ERROR > INVALID > PRODUCT_FAIL > PASS).
2. Post-X3 completion gate enforcement (fail-closed when L6 integrity or row binding fails).
3. Candidate evaluation manifest flexible path resolution and Windows normalization.
4. Governed CLI exit code mapping from evaluation decision.
5. Resolver lane identity preservation under run_root_file fallback.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from apps_rg.runtime.cli_exit_codes import (
    EXIT_E2E_PASS,
    EXIT_EVALUATION_INVALID,
    EXIT_EXECUTION_OR_EVALUATOR_ERROR,
    EXIT_GENERIC_FAILURE,
    EXIT_PRODUCT_FAIL_OR_REVIEW_REQUIRED,
    exit_code_from_evaluation_decision,
)
from apps_rg.runtime.evaluation_assurance import (
    derive_evaluation_decision,
    run_l6_evaluation_audit,
)
from apps_rg.runtime.evaluation_manifest import (
    EXPECTED_LANES,
    _LANE_ARTIFACTS,
    _ROOT_ARTIFACTS,
    build_candidate_evaluation_manifest,
    emit_candidate_evaluation_manifest,
    validate_candidate_evaluation_manifest,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _seed_minimal_candidate_tree(root: Path, *, legacy_layout: bool = False) -> None:
    """Create a candidate directory tree satisfying candidate manifest requirements."""
    _write_json(
        root / "runtime_identity_envelope.json",
        {
            "payload": {
                "parent_run_id": "parent-100",
                "child_run_id": "child-100",
                "runtime_exhaust_bundle_id": "reb-100",
            }
        },
    )
    _write_json(
        root / "FINAL_RESUME_OUTPUT.json",
        {
            "final_resume_json": {
                "relpath": "outputs/final_resume.json"
            }
        },
    )
    _write_json(root / "outputs" / "final_resume.json", {"sections": []})
    _write_json(root / "FINAL_RESUME_OUTPUT.txt", {})
    _write_json(root / "RUN_BUNDLE_INDEX.json", {"status": "PASS"})
    _write_json(root / "runtime_exhaust_bundle.json", {"status": "PASS"})
    _write_json(root / "e2e_preflight_product_entry_receipt.json", {"status": "PASS"})
    _write_json(root / "apps_rg_product_authorization_receipt.json", {"authorized": True})
    _write_json(root / "apps_rg_whole_run_exit_review_packet.json", {"x3_disposition": "X3D_ALLOW_FINISH"})
    _write_json(root / "x3_disposition_receipt.json", {"x3_disposition": "X3D_ALLOW_FINISH"})
    _write_json(root / "u0_receipt.json", {"status": "PASS"})
    _write_json(root / "route_contract.json", {"status": "PASS"})
    _write_json(root / "full_run_section_status.json", {"status": "PASS"})
    _write_json(root / "commit_request.json", {"status": "PASS"})
    _write_json(root / "uwg_validation_receipt.json", {"status": "PASS"})
    _write_json(root / "uwg_commit_receipt.json", {"status": "PASS"})

    # Assembly outputs: test flexible path (root vs modular_r4)
    if legacy_layout:
        _write_json(root / "modular_r4" / "final_resume_assembly" / "cross_section_x2_gate_outputs.json", {"gates": []})
        _write_json(root / "modular_r4" / "final_resume_assembly" / "final_resume_x2_gate_outputs.json", {"gates": []})
    else:
        _write_json(root / "cross_section_x2_gate_outputs.json", {"gates": []})
        _write_json(root / "final_resume_x2_gate_outputs.json", {"gates": []})

    for lane_id in EXPECTED_LANES:
        lane_dir = root / "lanes" / lane_id
        for _role, filename, required in _LANE_ARTIFACTS:
            if required:
                _write_json(
                    lane_dir / filename,
                    {
                        "section_id": lane_id,
                        "parent_run_id": "parent-100",
                        "child_run_id": f"child-100:{lane_id}:attempt-1",
                        "section_attempt_id": "attempt-1",
                        "runtime_exhaust_bundle_id": "reb-100",
                        "status": "PASS",
                    },
                )


class TestDeriveEvaluationDecision(unittest.TestCase):
    """Tests 4-plane decision derivation and strict Wave 5 precedence."""

    def test_clean_evaluation_yields_pass(self) -> None:
        eval_record = SimpleNamespace(
            record_id="eval-clean",
            eval_execution_complete=True,
            scorecard=SimpleNamespace(
                coverage_summary={"coverage_complete": True},
                scorecard_rows=[
                    {"required": True, "verdict": "PASS", "failure_mode": "", "score": 1.0},
                    {"required": False, "verdict": "PASS", "failure_mode": "", "score": 1.0},
                ],
            ),
        )
        l6_audit = {
            "l6_integrity_status": "PASS",
            "checks": {"eval_package_seal_present": True},
        }

        decision = derive_evaluation_decision(eval_record=eval_record, l6_audit=l6_audit)
        self.assertEqual(decision["execution_status"], "PASS")
        self.assertEqual(decision["package_integrity_status"], "PASS")
        self.assertEqual(decision["evaluation_validity"], "PASS")
        self.assertEqual(decision["deterministic_product_status"], "PASS")
        self.assertEqual(decision["evaluation_status"], "PASS")
        self.assertTrue(decision["pipeline_complete"])
        self.assertEqual(decision["invalid_row_count"], 0)
        self.assertEqual(decision["product_failure_row_count"], 0)
        self.assertEqual(decision["advisory_row_count"], 1)

    def test_execution_incomplete_yields_evaluation_error(self) -> None:
        eval_record = SimpleNamespace(
            record_id="eval-incomplete",
            eval_execution_complete=False,
            scorecard=SimpleNamespace(
                coverage_summary={"coverage_complete": False},
                scorecard_rows=[],
            ),
        )
        l6_audit = {"l6_integrity_status": "INVALID", "checks": {}}

        decision = derive_evaluation_decision(eval_record=eval_record, l6_audit=l6_audit)
        self.assertEqual(decision["execution_status"], "ERROR")
        self.assertEqual(decision["evaluation_status"], "EVALUATION_ERROR")
        self.assertFalse(decision["pipeline_complete"])
        self.assertIn("incomplete", decision["decisive_reason"])

    def test_invalid_evidence_yields_evaluation_invalid(self) -> None:
        eval_record = SimpleNamespace(
            record_id="eval-invalid",
            eval_execution_complete=True,
            scorecard=SimpleNamespace(
                coverage_summary={"coverage_complete": True},
                scorecard_rows=[
                    {
                        "required": True,
                        "verdict": "FAIL",
                        "failure_mode": "evidence.source_identity_missing",
                    }
                ],
            ),
        )
        l6_audit = {
            "l6_integrity_status": "PASS",
            "checks": {"eval_package_seal_present": True},
        }

        decision = derive_evaluation_decision(eval_record=eval_record, l6_audit=l6_audit)
        self.assertEqual(decision["evaluation_validity"], "INVALID")
        self.assertEqual(decision["evaluation_status"], "EVALUATION_INVALID")
        self.assertFalse(decision["pipeline_complete"])
        self.assertEqual(decision["invalid_row_count"], 1)
        self.assertEqual(decision["product_failure_row_count"], 0)

    def test_l6_integrity_failure_yields_evaluation_invalid(self) -> None:
        eval_record = SimpleNamespace(
            record_id="eval-l6-fail",
            eval_execution_complete=True,
            scorecard=SimpleNamespace(
                coverage_summary={"coverage_complete": True},
                scorecard_rows=[{"required": True, "verdict": "PASS", "failure_mode": ""}],
            ),
        )
        l6_audit = {
            "l6_integrity_status": "FAIL",
            "checks": {"eval_package_seal_present": True},
        }

        decision = derive_evaluation_decision(eval_record=eval_record, l6_audit=l6_audit)
        self.assertEqual(decision["evaluation_validity"], "INVALID")
        self.assertEqual(decision["evaluation_status"], "EVALUATION_INVALID")
        self.assertFalse(decision["pipeline_complete"])
        self.assertEqual(decision["decisive_reason"], "l6_integrity_audit_failed")

    def test_product_gate_failure_yields_product_fail(self) -> None:
        eval_record = SimpleNamespace(
            record_id="eval-prod-fail",
            eval_execution_complete=True,
            scorecard=SimpleNamespace(
                coverage_summary={"coverage_complete": True},
                scorecard_rows=[
                    {
                        "required": True,
                        "verdict": "FAIL",
                        "failure_mode": "microstep.x2_gates_pass",
                    }
                ],
            ),
        )
        l6_audit = {
            "l6_integrity_status": "PASS",
            "checks": {"eval_package_seal_present": True},
        }

        decision = derive_evaluation_decision(eval_record=eval_record, l6_audit=l6_audit)
        self.assertEqual(decision["evaluation_validity"], "PASS")
        self.assertEqual(decision["deterministic_product_status"], "FAIL")
        self.assertEqual(decision["evaluation_status"], "PRODUCT_FAIL")
        self.assertFalse(decision["pipeline_complete"])
        self.assertEqual(decision["product_failure_row_count"], 1)
        self.assertEqual(decision["invalid_row_count"], 0)


class TestCandidateEvaluationManifestFlexiblePaths(unittest.TestCase):
    """Tests candidate evaluation manifest resolution across modern and legacy paths."""

    def test_manifest_resolves_modern_clean_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _seed_minimal_candidate_tree(root, legacy_layout=False)

            manifest_path = emit_candidate_evaluation_manifest(root)
            self.assertTrue(manifest_path.is_file())

            manifest, errors = validate_candidate_evaluation_manifest(root)
            self.assertEqual(errors, [])
            bindings = {b["role"]: b["artifact_ref"] for b in manifest["artifact_bindings"]}
            self.assertEqual(bindings["cross_section_x2_gate_outputs"], "cross_section_x2_gate_outputs.json")
            self.assertEqual(bindings["final_resume_x2_gate_outputs"], "final_resume_x2_gate_outputs.json")

    def test_manifest_resolves_legacy_modular_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _seed_minimal_candidate_tree(root, legacy_layout=True)

            manifest_path = emit_candidate_evaluation_manifest(root)
            self.assertTrue(manifest_path.is_file())

            manifest, errors = validate_candidate_evaluation_manifest(root)
            self.assertEqual(errors, [])
            bindings = {b["role"]: b["artifact_ref"] for b in manifest["artifact_bindings"]}
            self.assertEqual(
                bindings["cross_section_x2_gate_outputs"],
                "modular_r4/final_resume_assembly/cross_section_x2_gate_outputs.json",
            )

    def test_manifest_detects_tampered_byte(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _seed_minimal_candidate_tree(root, legacy_layout=False)
            emit_candidate_evaluation_manifest(root)

            # Mutate one file on disk
            (root / "cross_section_x2_gate_outputs.json").write_text('{"tampered":true}\n', encoding="utf-8")

            manifest, errors = validate_candidate_evaluation_manifest(root)
            self.assertTrue(any("candidate_evaluation_binding_digest_mismatch" in e for e in errors))


class TestCliExitCodeMapping(unittest.TestCase):
    """Tests canonical exit code mapping from evaluation decision."""

    def test_exit_e2e_pass(self) -> None:
        decision = {
            "evaluation_status": "PASS",
            "execution_status": "PASS",
            "evaluation_validity": "PASS",
            "deterministic_product_status": "PASS",
            "pipeline_complete": True,
        }
        self.assertEqual(exit_code_from_evaluation_decision(decision), EXIT_E2E_PASS)

    def test_exit_product_fail(self) -> None:
        decision = {
            "evaluation_status": "PRODUCT_FAIL",
            "execution_status": "PASS",
            "evaluation_validity": "PASS",
            "deterministic_product_status": "FAIL",
            "pipeline_complete": False,
        }
        self.assertEqual(exit_code_from_evaluation_decision(decision), EXIT_PRODUCT_FAIL_OR_REVIEW_REQUIRED)

    def test_exit_evaluation_invalid(self) -> None:
        decision = {
            "evaluation_status": "EVALUATION_INVALID",
            "execution_status": "PASS",
            "evaluation_validity": "INVALID",
            "pipeline_complete": False,
        }
        self.assertEqual(exit_code_from_evaluation_decision(decision), EXIT_EVALUATION_INVALID)

    def test_exit_execution_error(self) -> None:
        decision = {
            "evaluation_status": "EVALUATION_ERROR",
            "execution_status": "ERROR",
            "pipeline_complete": False,
        }
        self.assertEqual(exit_code_from_evaluation_decision(decision), EXIT_EXECUTION_OR_EVALUATOR_ERROR)

    def test_exit_fallback_on_invalid_payload(self) -> None:
        self.assertEqual(exit_code_from_evaluation_decision(None), EXIT_GENERIC_FAILURE)
        self.assertEqual(exit_code_from_evaluation_decision("not-a-dict"), EXIT_GENERIC_FAILURE)


class TestPublicCliEvaluationReport(unittest.TestCase):
    """Tests _evaluate_product_run in src/apps_rg/__main__.py."""

    def test_evaluate_product_run_passes_on_complete_package(self) -> None:
        from apps_rg.__main__ import _evaluate_product_run

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _seed_minimal_candidate_tree(root, legacy_layout=False)
            emit_candidate_evaluation_manifest(root)
            _write_json(
                root / "apps_eval" / "eval-1" / "eval_record.json",
                {"record_id": "eval-1", "verdict": "pass", "status": "pass"},
            )
            _write_json(
                root / "apps_rg_pipeline_completion_receipt.json",
                {
                    "pipeline_complete": True,
                    "evaluation_decision": {
                        "evaluation_status": "PASS",
                        "evaluation_validity": "PASS",
                        "deterministic_product_status": "PASS",
                        "execution_status": "PASS",
                        "package_integrity_status": "PASS",
                        "l6_integrity_status": "PASS",
                    },
                },
            )
            _write_json(root / "apps_rg_product_authorization_receipt.json", {"authorized": True})
            _write_json(root / "x3_disposition_receipt.json", {"x3_disposition": "X3D_ALLOW_FINISH"})

            report = _evaluate_product_run(root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["evaluation_status"], "PASS")
            self.assertEqual(report["exit_code"], 0)
            self.assertTrue(report["pipeline_complete"])
            self.assertTrue(report["product_authorized"])

    def test_evaluate_product_run_blocks_on_tampered_candidate_manifest(self) -> None:
        from apps_rg.__main__ import _evaluate_product_run

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _seed_minimal_candidate_tree(root, legacy_layout=False)
            emit_candidate_evaluation_manifest(root)
            _write_json(
                root / "apps_eval" / "eval-1" / "eval_record.json",
                {"record_id": "eval-1", "verdict": "pass", "status": "pass"},
            )
            # Tamper with file
            (root / "cross_section_x2_gate_outputs.json").write_text(
                '{"tampered":true}\n', encoding="utf-8"
            )
            _write_json(
                root / "apps_rg_pipeline_completion_receipt.json",
                {
                    "pipeline_complete": True,
                    "evaluation_decision": {
                        "evaluation_status": "PASS",
                        "evaluation_validity": "PASS",
                        "deterministic_product_status": "PASS",
                    },
                },
            )
            _write_json(root / "apps_rg_product_authorization_receipt.json", {"authorized": True})
            _write_json(root / "x3_disposition_receipt.json", {"x3_disposition": "X3D_ALLOW_FINISH"})

            report = _evaluate_product_run(root)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["evaluation_status"], "EVALUATION_INVALID")
            self.assertEqual(report["exit_code"], 3)
            self.assertTrue(len(report["candidate_manifest_errors"]) > 0)


class TestResolverIdentityPreservation(unittest.TestCase):
    """Tests lane identity preservation during fallback in apps_rg_resolver."""

    def test_run_root_fallback_preserves_sibling_lane_identity(self) -> None:
        from apps_eval.artifacts.apps_rg_resolver import resolve_apps_rg_artifact
        from apps_eval.contracts import AppOutputSnapshot

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            lane_dir = root / "lanes" / "headline"
            lane_dir.mkdir(parents=True)
            (lane_dir / "l2_output.json").write_text('{"text":"headline text"}', encoding="utf-8")
            (lane_dir / "apps_rg_section_runtime_exhaust_bundle.json").write_text(
                json.dumps(
                    {
                        "section_id": "headline",
                        "parent_run_id": "p-1",
                        "child_run_id": "c-1",
                        "section_attempt_id": "att-1",
                        "runtime_exhaust_bundle_id": "reb-1",
                    }
                ),
                encoding="utf-8",
            )

            snapshot = AppOutputSnapshot(
                app_id="apps_rg",
                scenario_id="sc-1",
                x3_disposition="X3D_ALLOW_FINISH",
                output={},
                run_root=str(root),
                artifact_index={},
            )
            artifact_contract = {
                "artifact_roles": {
                    "lane_l2_output": {
                        "relative_paths": ["lanes/{lane}/l2_output.json"],
                        "source_artifact_schema": "apps_rg.l2_output.v1",
                    }
                }
            }
            resolved = resolve_apps_rg_artifact(
                snapshot=snapshot,
                role="lane_l2_output",
                lane_id="headline",
                artifact_contract=artifact_contract,
            )
            self.assertTrue(resolved.found)
            self.assertIsInstance(resolved.payload, dict)
            identity = resolved.payload.get("source_identity")
            self.assertIsInstance(identity, dict)
            self.assertEqual(identity.get("parent_run_id"), "p-1")
            self.assertEqual(identity.get("section_attempt_id"), "att-1")
            self.assertEqual(identity.get("runtime_exhaust_bundle_id"), "reb-1")


if __name__ == "__main__":
    unittest.main()

