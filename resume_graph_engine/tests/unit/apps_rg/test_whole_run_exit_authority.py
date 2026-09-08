from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.product_stage_authority import (
    emit_runtime_stage_authority_receipts,
)
from apps_rg.runtime.package.apps_rg_full_resume_x3_eligibility import (
    evaluate_apps_rg_product_authority_eligibility,
)
from apps_rg.runtime.authority_reconciliation import (
    emit_w1_authority_reconciliation,
)
from apps_rg.runtime.post_runtime_replay import build_source_manifest
from apps_rg.runtime.whole_run_exit import (
    build_whole_run_exit_signals,
    compute_whole_run_exit,
    emit_whole_run_exit_review_packet,
    verify_whole_run_exit_review_packet,
)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _identity() -> dict[str, str]:
    digest = "sha256:" + "a" * 64
    return {
        "producer_app_id": "apps_research",
        "consumer_app_id": "apps_rg",
        "parent_run_id": "parent-001",
        "child_run_id": "child-001",
        "request_id": "request-001",
        "trace_root": "trace-001",
        "tenant_id": "tenant-001",
        "target_company": "Anthropic",
        "target_role": "Partnerships leader",
        "jd_sha256": digest,
        "brief_sha256": digest,
        "policy_hash": digest,
        "blueprint_hash": digest,
        "schema_version": "apps_research_rg_run_identity.v1",
    }


def _build_all_pass_run(root: Path, *, flat_lane_layout: bool = False) -> None:
    status_rows: list[dict[str, Any]] = []
    for lane in GENERATED_LANES:
        status_rows.append(
            {
                "lane": lane,
                "executed": True,
                "x3_code": "X3_ALLOW",
                "x2_pass": "PASS",
                "x2_failed_gate_ids": "",
                "runtime_generation_status": "REAL_LLM",
                "product_quality_status": "PASS",
                "judges": [
                    {
                        "pass": True,
                        "provider_status": "MODEL_BACKED_PASS",
                    }
                ],
            }
        )
        lane_root = (
            root / "lanes" / lane
            if flat_lane_layout
            else root / "modular_r4" / "sections" / lane
        )
        _write(
            lane_root / "c0_metrics.json",
            {
                "support_status": "PASS",
                "support_target_met": True,
                "evidence_counts": {"total": 1},
            },
        )
        _write(
            lane_root / "compiled_prompt_artifact.json",
            {
                "section_id": lane,
                "pa_prompt_hash": f"prompt-{lane}",
                "fec_bridge_ref": "final_evidence_contract.json",
                "final_evidence_contract_ref": "final_evidence_contract.json",
                "c0_fec_bridge_receipt_ref": "c0_fec_compose_receipt.json",
                "evidence_contract_consumed": True,
                "raw_proof_pool_direct_to_pa": False,
            },
        )
        _write(
            lane_root / "c0_fec_compose_receipt.json",
            {
                "fec_bridge_status": "PASS",
                "precondition_status": "PASS",
                "support_status": "PASS",
                "pa_entry_allowed": True,
                "raw_proof_pool_direct_to_pa": False,
            },
        )
        _write(
            lane_root / "x2_gate_outputs.json",
            {
                "gates": [{"gate_id": "x2_no_silent_mock_fallback", "pass": True}],
                "failed_gates": [],
                "x2_failed": 0,
            },
        )
        _write(
            lane_root / "x3_disposition.json",
            {
                "x3_code": "X3_ALLOW",
                "final_materialized_acceptance_ok": True,
                "section_x3_authoritative": False,
                "section_x3_mirror_only": True,
                "spine_x3_claimed": False,
                "core_exit_authority_ref": "x3_disposition_receipt.json",
            },
        )
        _write(
            lane_root / "exit_disposition_receipt.json",
            {
                "section_x3_authoritative": False,
                "section_x3_mirror_only": True,
                "spine_x3_claimed": False,
                "canonical_exit_claimed": False,
                "x3_disposition": {"x3_code": "X3_ALLOW"},
            },
        )
        handoff_checks = {
            "artifact_bytes_match": True,
            "canonical_receipt_bundle_required": True,
            "grounded_output": True,
            "model_id_matches": True,
            "packet_signature_verified": True,
            "provider_lane_matches": True,
            "replay_key_matches": True,
            "token_budget_pass": True,
            "token_usage_observed": True,
        }
        _write(
            lane_root / "l2_handoff_receipt.json",
            {
                "schema_version": "apps_rg_l2_handoff_receipt_v2",
                "section_id": lane,
                "handoff_status": "PASS",
                "checks": handoff_checks,
                "model_id_used": "claude-" + "sonnet-5",
                "provider_lane_used": "anthropic",
                "tokens_emitted": 100,
                "budget_ceiling": 4096,
            },
        )
        _write(
            lane_root / "l2_spine_receipt.json",
            {
                "schema_version": "l2_spine_receipt_v2",
                "section_id": lane,
                "l2_spine_status": "PASS",
                "precondition_status": "PASS",
                "direct_l4_write_allowed": False,
            },
        )
        core_payload = {
            "x3_disposition": "X3D_ALLOW_FINISH",
            "disposition": "X3D",
        }
        _write(
            lane_root / "x3_disposition_receipt.json",
            {
                "producer_component": (
                    "apps_rg.runtime.entrypoints."
                    "integrated_single_action_spine_run"
                ),
                "artifact_hash": _digest(core_payload),
                "payload": core_payload,
            },
        )
        core_authority = {
            "schema_version": "apps_rg.core_runtime_authority.v1",
            "source_artifact_bindings": [
                {
                    "artifact_ref": "x3_disposition_receipt.json",
                    "present": True,
                    "hash_matches": True,
                }
            ],
            "normalized_contract": {
                "valid": True,
                "x3": {"x3_disposition": "X3D_ALLOW_FINISH"},
                "spine_proof": {"success": True},
            },
            "status": "PASS",
            "outcome_authorized": True,
        }
        core_authority["deterministic_digest"] = _digest(core_authority)
        _write(lane_root / "apps_rg_core_runtime_authority.json", core_authority)

    _write(root / "full_run_section_status.json", {"lanes": status_rows})
    _write(
        root / "FINAL_RESUME_OUTPUT.json",
        {
            "status": "PASS",
            "failed_gate_ids": [],
            "gates": [
                {"gate_id": "final_resume_base_role_headers_preserved", "pass": True},
                {"gate_id": "final_resume_education_copied_from_base", "pass": True},
                {
                    "gate_id": "final_resume_certifications_copied_from_base",
                    "pass": True,
                },
            ],
        },
    )
    assembly = root / "modular_r4" / "final_resume_assembly"
    _write(
        assembly / "final_resume.json",
        {
            "sections": [{"section_id": lane} for lane in GENERATED_LANES]
            + [
                {"section_id": "early_career"},
                {"section_id": "education"},
                {"section_id": "certifications"},
            ],
            "locked_copy_invariants": {"dates": {"section_hash": "abc"}},
        },
    )
    _write(
        assembly / "final_resume_x2_gate_outputs.json",
        {
            "all_pass": True,
            "failed_gate_ids": [],
            "gates": [{"gate_id": "x2_all_required_sections_present", "pass": True}],
        },
    )
    _write(
        assembly / "x1d_full_resume_judge_outputs.json",
        {
            "judges": [{"pass": True}, {"pass": True}],
            "aggregation": {
                "quorum_required": 2,
                "full_resume_coherence_pass": True,
                "blockers": [],
            },
        },
    )
    _write(
        assembly / "final_resume_receipt.json",
        {
            "gates_all_pass": True,
            "structural_x2_all_pass": True,
            "cross_section_x2_all_pass": True,
            "cross_section_x2_product_pass": True,
            "whole_resume_graph_evidence_release_pass": True,
            "review_lane_policy_summary": {"product_allow_claimed": True},
            "assembly_proof_semantics": {"product_release_eligible": True},
        },
    )


def _write_outer_core_transport(root: Path, identity: dict[str, str]) -> None:
    common = {
        "run_id": identity["parent_run_id"],
        "request_id": identity["request_id"],
        "trace_root": identity["trace_root"],
    }
    _write(
        root / "runtime_execution_witness.json",
        {
            "payload": {
                **common,
                "c0": {"status": "BYPASSED_PRELOADED_CONTEXT"},
                "l2": {"executed": True, "status": "PASS", "fault": ""},
                "x1": {"status": "EXECUTED"},
                "x2": {
                    "status": "EXECUTED",
                    "x3_disposition": "X3A_DENY_REROUTE",
                },
                "x3": {
                    "status": "EMITTED",
                    "x3_disposition": "X3A_DENY_REROUTE",
                },
            }
        },
    )
    _write(root / "terminal_ret_packet.json", {"payload": {**common, "l2_fault": ""}})
    _write(root / "prompt_assembly_bypass_receipt.json", {"payload": common})


def _write_product_entry(root: Path, identity: dict[str, str]) -> dict[str, Any]:
    _write(
        root / "e2e_preflight_product_entry_receipt.json",
        {"status": "PASS", "identity": identity},
    )
    _write(root / "u0_receipt.json", {"status": "PASS", "identity": identity})
    research = root / "apps_research" / "runs" / "research-001"
    _write(research / "exit_disposition_receipt.json", {"x3_code": "X3D_ALLOW_FINISH"})
    _write(
        research / "apps_research_apps_rg_handoff_v2.json",
        {
            "schema_version": "apps_research.apps_rg_handoff.v2",
            "identity": identity,
        },
    )
    ledger = root / "e2e_ledger_receipts"
    _write(
        ledger / "0006_apps_rg_l1.json",
        {
            "status": "PASS",
            "work_shape": "full_resume_generation",
            "identity": identity,
        },
    )
    _write(
        ledger / "0007_apps_rg_l0.json",
        {
            "status": "PASS",
            "execution_form": "MANAGED_WORKFLOW",
            "identity": identity,
        },
    )
    _write(root / "outputs" / "generated_resume.json", {"sections": []})
    (root / "outputs" / "resume.docx").write_bytes(b"test-docx")
    manifest = {
        "apps_rg_generation_status": "REAL_RESUME",
        "resume_shape": "REAL_RESUME",
        "full_resume_generated": True,
        "docx_output_required": True,
        "docx_verified": True,
        "generated_resume_json_relpath": "outputs/generated_resume.json",
        "resume_docx_relpath": "outputs/resume.docx",
        "required_artifacts": {
            "generated_resume_json": "verified",
            "resume_docx": "verified",
            "docx_verified": True,
        },
    }
    _write(root / "apps_rg_output_manifest.json", manifest)
    return manifest


def _replace_with_sealed_lane_contracts(
    root: Path,
    *,
    flat_lane_layout: bool,
) -> None:
    """Make the fixture match the public CLI's current section-lane receipts."""

    for lane in GENERATED_LANES:
        lane_root = (
            root / "lanes" / lane
            if flat_lane_layout
            else root / "modular_r4" / "sections" / lane
        )
        (lane_root / "apps_rg_core_runtime_authority.json").unlink()
        payload = {"x3_disposition": "X3_ALLOW", "run_id": f"run-{lane}"}
        _write(
            lane_root / "x3_disposition_receipt.json",
            {
                "producer_component": (
                    "apps_rg.runtime.orchestration.app_single_action_spine"
                ),
                "artifact_hash": _digest(payload),
                "payload": payload,
            },
        )
        _write(
            lane_root / "final_materialized_acceptance_contract.json",
            {
                "section_id": lane,
                "pass": True,
                "x3_authorizes": True,
                "x2_final_materialized_binding_pass": True,
            },
        )
        _write(
            lane_root / "one_spine_certification_receipt.json",
            {
                "certification_status": "PASS",
                "required_chain_complete": True,
                "all_required_artifacts_present": True,
                "all_required_refs_valid": True,
            },
        )
        _write(
            lane_root / "product_certification_receipt.json",
            {
                "product_certification": "ONE_SPINE_SECTION_CERTIFIED",
                "proof_eligible": True,
                "x3_code": "X3_ALLOW",
            },
        )


def test_whole_run_exit_authorizes_complete_app_artifacts(tmp_path: Path) -> None:
    _build_all_pass_run(tmp_path)
    identity = _identity()

    packet = emit_whole_run_exit_review_packet(
        artifact_dir=tmp_path,
        identity=identity,
    )
    valid, errors = verify_whole_run_exit_review_packet(
        tmp_path,
        expected_identity=identity,
    )

    assert packet["status"] == "PASS"
    assert packet["x3_disposition"] == "X3D_ALLOW_FINISH"
    assert packet["signals"]["observed_lane_ids"] == sorted(GENERATED_LANES)
    assert packet["signals"]["judge_quorum_satisfied"] is True
    assert packet["signals"]["final_resume_x2_all_pass"] is True
    assert valid is True
    assert errors == ()


def test_whole_run_exit_authorizes_flat_whole_resume_lane_layout(tmp_path: Path) -> None:
    """The public whole-resume CLI stores authoritative lane receipts in lanes/.

    Whole-run exit must resolve that layout rather than look for a second,
    nonexistent modular_r4/sections copy of the same live evidence.
    """
    _build_all_pass_run(tmp_path, flat_lane_layout=True)

    packet = emit_whole_run_exit_review_packet(
        artifact_dir=tmp_path,
        identity=_identity(),
    )

    assert packet["status"] == "PASS"
    assert packet["x3_disposition"] == "X3D_ALLOW_FINISH"
    assert not any("modular_r4/sections" in reason for reason in packet["blockers"])
    assert any(
        binding["artifact_ref"] == "lanes/executive_summary/x2_gate_outputs.json"
        and binding["present"] is True
        for binding in packet["source_bindings"]
    )


def test_whole_run_exit_authorizes_current_sealed_lane_contracts(
    tmp_path: Path,
) -> None:
    """Only the whole run may emit X3D; current lane receipts emit X3_ALLOW."""

    _build_all_pass_run(tmp_path, flat_lane_layout=True)
    _replace_with_sealed_lane_contracts(tmp_path, flat_lane_layout=True)

    packet = emit_whole_run_exit_review_packet(
        artifact_dir=tmp_path,
        identity=_identity(),
    )

    assert packet["status"] == "PASS"
    assert packet["x3_disposition"] == "X3D_ALLOW_FINISH"
    assert {
        row["x3_code"] for row in packet["signals"]["lane_rows"]
    } == {"X3_ALLOW"}
    assert not any(
        binding["artifact_ref"].endswith("apps_rg_core_runtime_authority.json")
        for binding in packet["source_bindings"]
    )


def test_whole_run_exit_detects_source_tamper_and_reemits_blocked(
    tmp_path: Path,
) -> None:
    _build_all_pass_run(tmp_path)
    identity = _identity()
    emit_whole_run_exit_review_packet(artifact_dir=tmp_path, identity=identity)
    final_x2 = (
        tmp_path
        / "modular_r4"
        / "final_resume_assembly"
        / "final_resume_x2_gate_outputs.json"
    )
    _write(
        final_x2,
        {
            "all_pass": False,
            "failed_gate_ids": ["x2_controlled_negative"],
            "gates": [{"gate_id": "x2_controlled_negative", "pass": False}],
        },
    )

    valid, errors = verify_whole_run_exit_review_packet(tmp_path)
    blocked = emit_whole_run_exit_review_packet(
        artifact_dir=tmp_path,
        identity=identity,
    )

    assert valid is False
    assert "WHOLE_RUN_EXIT_SIGNAL_DERIVATION_MISMATCH" in errors
    assert "WHOLE_RUN_EXIT_SOURCE_BINDING_MISMATCH" in errors
    assert blocked["status"] == "BLOCKED"
    assert blocked["x3_disposition"] == "X3A_DENY_REROUTE"


def test_whole_run_exit_names_exact_missing_lane_artifact(tmp_path: Path) -> None:
    _build_all_pass_run(tmp_path)
    missing = (
        tmp_path / "modular_r4" / "sections" / "unify_narrative" / "c0_metrics.json"
    )
    missing.unlink()

    packet = emit_whole_run_exit_review_packet(
        artifact_dir=tmp_path,
        identity=_identity(),
    )

    assert packet["status"] == "BLOCKED"
    assert (
        "UNREADABLE_JSON:modular_r4/sections/unify_narrative/c0_metrics.json:"
        "FileNotFoundError"
    ) in packet["blockers"]


def test_model_backed_quality_fail_is_not_mislabeled_as_mock_or_l4_bypass(
    tmp_path: Path,
) -> None:
    _build_all_pass_run(tmp_path)
    status_path = tmp_path / "full_run_section_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    competency = next(row for row in status["lanes"] if row["lane"] == "competencies")
    competency["judges"] = [
        {
            "pass": False,
            "provider_status": "MODEL_BACKED_FAIL",
        }
    ]
    competency["x3_code"] = "X3_BLOCK_FINAL_MATERIALIZED_ACCEPTANCE"
    _write(status_path, status)
    _write(
        tmp_path / "modular_r4" / "sections" / "competencies" / "x3_disposition.json",
        {
            "x3_code": "X3_BLOCK_FINAL_MATERIALIZED_ACCEPTANCE",
            "final_materialized_acceptance_ok": False,
        },
    )

    signals, _sources, _errors = build_whole_run_exit_signals(tmp_path)
    decision = compute_whole_run_exit(signals)

    assert signals["mock_provider_pass"] is False
    assert signals["direct_l4_write_bypass"] is False
    assert signals["final_materialized_acceptance_failed_lanes"] == ["competencies"]
    assert any(
        "final materialized acceptance failed for lanes [competencies]" in blocker
        for blocker in decision["blockers"]
    )


def test_upstream_x2_failure_is_not_mislabeled_as_malformed_judge_policy(
    tmp_path: Path,
) -> None:
    _build_all_pass_run(tmp_path)
    status_path = tmp_path / "full_run_section_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    executive = next(
        row for row in status["lanes"] if row["lane"] == "executive_summary"
    )
    executive.update(
        {
            "x2_pass": "FAIL",
            "x2_failed_gate_ids": "x2_exec_summary_speculative_capstone_zero",
            "x3_code": "X3_BLOCK",
            "product_quality_status": "FAIL",
            "judges": [],
        }
    )
    _write(status_path, status)
    _write(
        tmp_path / "FINAL_RESUME_OUTPUT.json",
        {
            "status": "FAIL",
            "failed_gate_ids": ["final_resume_no_gap_markers"],
            "gates": [{"gate_id": "final_resume_no_gap_markers", "pass": False}],
        },
    )
    assembly = tmp_path / "modular_r4" / "final_resume_assembly"
    (assembly / "final_resume.json").unlink()
    (assembly / "final_resume_x2_gate_outputs.json").unlink()
    (assembly / "x1d_full_resume_judge_outputs.json").unlink()

    packet = emit_whole_run_exit_review_packet(
        artifact_dir=tmp_path,
        identity=_identity(),
    )

    assert packet["signals"]["x1d_policy_valid"] is True
    assert packet["signals"]["mock_provider_pass"] is False
    assert "X1D_POLICY_MALFORMED" not in packet["decisive_reason"]
    assert any(
        blocker == "lane executive_summary: deterministic X2 failed "
        "[x2_exec_summary_speculative_capstone_zero]"
        for blocker in packet["blockers"]
    )
    assert (
        "FINAL_RESUME_OUTPUT status=FAIL failed_gates=[final_resume_no_gap_markers]"
    ) in packet["blockers"]


def test_stage_authority_uses_canonical_whole_exit_not_outer_c0_receipt(
    tmp_path: Path,
) -> None:
    _build_all_pass_run(tmp_path)
    identity = _identity()
    _write_outer_core_transport(tmp_path, identity)
    witness_path = tmp_path / "runtime_execution_witness.json"
    witness = json.loads(witness_path.read_text(encoding="utf-8"))
    witness["payload"].pop("c0")
    witness["payload"]["run_id"] = "apps-rg-inner-runtime"
    witness["payload"]["request_id"] = "apps-rg-inner-request"
    _write(witness_path, witness)
    terminal_path = tmp_path / "terminal_ret_packet.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["payload"]["run_id"] = "apps-rg-inner-runtime"
    _write(terminal_path, terminal)
    emit_whole_run_exit_review_packet(artifact_dir=tmp_path, identity=identity)

    receipts = emit_runtime_stage_authority_receipts(
        artifact_dir=tmp_path,
        identity=identity,
    )
    statuses = {
        stage: json.loads(path.read_text(encoding="utf-8"))["status"]
        for stage, path in receipts.items()
    }

    assert statuses == {
        "APPS_RG_C0": "PASS",
        "APPS_RG_PA": "PASS",
        "APPS_RG_L2": "PASS",
        "X1_REVIEW": "PASS",
        "X2_AGGREGATION": "PASS",
        "X3_DISPOSITION": "PASS",
    }
    c0_receipt = json.loads(receipts["APPS_RG_C0"].read_text(encoding="utf-8"))
    assert "outer_runtime_c0_receipt_present" not in c0_receipt["checks"]
    assert c0_receipt["source_bindings"] == [
        {
            "artifact_ref": "apps_rg_whole_run_exit_review_packet.json",
            "byte_length": (tmp_path / "apps_rg_whole_run_exit_review_packet.json").stat().st_size,
            "sha256": "sha256:" + hashlib.sha256(
                (tmp_path / "apps_rg_whole_run_exit_review_packet.json").read_bytes()
            ).hexdigest(),
        }
    ]


def test_stage_authority_accepts_single_runtime_witness_shape(tmp_path: Path) -> None:
    """Whole-run evidence is authoritative over retired outer-core witness fields."""

    _build_all_pass_run(tmp_path)
    identity = _identity()
    _write(
        tmp_path / "runtime_execution_witness.json",
        {
            "payload": {
                "run_id": "apps-rg-local-run",
                "request_id": "apps-rg-local-run",
                "trace_root": identity["trace_root"],
                "c0": {"status": "OBSERVED"},
                "l2": {"executed": True, "status": "PASS", "fault": ""},
                "x2": {"disposition": "OBSERVED"},
            }
        },
    )
    _write(
        tmp_path / "terminal_ret_packet.json",
        {
            "payload": {
                "run_id": "apps-rg-local-run",
                "status": "PASS",
                "fault": "",
            }
        },
    )
    _write(tmp_path / "prompt_assembly_bypass_receipt.json", {"status": "OBSERVED"})
    emit_whole_run_exit_review_packet(artifact_dir=tmp_path, identity=identity)

    receipts = emit_runtime_stage_authority_receipts(
        artifact_dir=tmp_path,
        identity=identity,
    )

    assert all(
        json.loads(path.read_text(encoding="utf-8"))["status"] == "PASS"
        for path in receipts.values()
    )


def test_producer_core_x3_denial_overrides_allowing_app_mirror(
    tmp_path: Path,
) -> None:
    _build_all_pass_run(tmp_path)
    lane_root = tmp_path / "modular_r4" / "sections" / "headline"
    core_payload = {
        "x3_disposition": "X3A_DENY_REROUTE",
        "disposition": "X3A",
    }
    _write(
        lane_root / "x3_disposition_receipt.json",
        {
            "producer_component": (
                "apps_rg.runtime.entrypoints.integrated_single_action_spine_run"
            ),
            "artifact_hash": _digest(core_payload),
            "payload": core_payload,
        },
    )
    core_authority = {
        "schema_version": "apps_rg.core_runtime_authority.v1",
        "source_artifact_bindings": [
            {
                "artifact_ref": "x3_disposition_receipt.json",
                "present": True,
                "hash_matches": True,
            }
        ],
        "normalized_contract": {
            "valid": True,
            "x3": {"x3_disposition": "X3A_DENY_REROUTE"},
            "spine_proof": {"success": False},
        },
        "status": "BLOCKED",
        "outcome_authorized": False,
    }
    core_authority["deterministic_digest"] = _digest(core_authority)
    _write(lane_root / "apps_rg_core_runtime_authority.json", core_authority)

    packet = emit_whole_run_exit_review_packet(
        artifact_dir=tmp_path,
        identity=_identity(),
    )

    assert packet["status"] == "BLOCKED"
    assert packet["x3_disposition"] == "X3A_DENY_REROUTE"
    assert packet["signals"]["core_x3_non_authorizing_lanes"] == ["headline"]
    headline = next(
        row for row in packet["signals"]["lane_rows"] if row["lane"] == "headline"
    )
    assert headline["x3_code"] == "X3A_DENY_REROUTE"
    assert headline["mirror_x3_code"] == "X3_ALLOW"


def test_product_eligibility_requires_verified_authority_and_final_release(
    tmp_path: Path,
) -> None:
    _build_all_pass_run(tmp_path)
    identity = _identity()
    manifest = _write_product_entry(tmp_path, identity)
    emit_whole_run_exit_review_packet(artifact_dir=tmp_path, identity=identity)

    eligible, reasons = evaluate_apps_rg_product_authority_eligibility(
        manifest=manifest,
        run_root=tmp_path,
    )
    assert eligible is True
    assert reasons == []

    receipt_path = (
        tmp_path / "modular_r4" / "final_resume_assembly" / "final_resume_receipt.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["cross_section_x2_product_pass"] = False
    receipt["assembly_proof_semantics"]["product_release_eligible"] = False
    _write(receipt_path, receipt)

    eligible, reasons = evaluate_apps_rg_product_authority_eligibility(
        manifest=manifest,
        run_root=tmp_path,
    )
    assert eligible is False
    assert "final_assembly:cross_section_x2_product_pass" in reasons
    assert any(reason.startswith("whole_run_exit_verification:") for reason in reasons)


def test_w1_emits_additive_correction_and_parallel_replay_proof(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "derived"
    _build_all_pass_run(source)
    identity = _identity()
    _write_product_entry(source, identity)
    emit_whole_run_exit_review_packet(artifact_dir=source, identity=identity)
    _write(
        source / "apps_rg_product_authorization_receipt.json",
        {
            "schema_version": "apps_rg.product_authorization_receipt.v1",
            "status": "AUTHORIZED",
            "authorized": True,
            "identity": identity,
        },
    )

    lane_root = source / "modular_r4" / "sections" / "headline"
    handoff_path = lane_root / "l2_handoff_receipt.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["handoff_status"] = "FAIL"
    handoff["checks"]["model_id_matches"] = False
    _write(handoff_path, handoff)
    core_payload = {
        "x3_disposition": "X3A_DENY_REROUTE",
        "disposition": "X3A",
    }
    _write(
        lane_root / "x3_disposition_receipt.json",
        {
            "producer_component": (
                    "apps_rg.runtime.entrypoints.integrated_single_action_spine_run"
            ),
            "artifact_hash": _digest(core_payload),
            "payload": core_payload,
        },
    )
    core_authority = {
        "schema_version": "apps_rg.core_runtime_authority.v1",
        "source_artifact_bindings": [
            {
                "artifact_ref": "x3_disposition_receipt.json",
                "present": True,
                "hash_matches": True,
            }
        ],
        "normalized_contract": {
            "valid": True,
            "x3": {"x3_disposition": "X3A_DENY_REROUTE"},
            "spine_proof": {"success": False},
        },
        "status": "BLOCKED",
        "outcome_authorized": False,
    }
    core_authority["deterministic_digest"] = _digest(core_authority)
    _write(lane_root / "apps_rg_core_runtime_authority.json", core_authority)
    before = build_source_manifest(source)
    repo_root = Path(__file__).resolve().parents[3]

    result = emit_w1_authority_reconciliation(
        source_run=source,
        output_dir=output,
        dag_manifest_path=(
            repo_root / "src/apps_rg/config/domain_contract/"
            "workflow_manifest.resume_sections.v1.yaml"
        ),
    )
    after = build_source_manifest(source)

    assert before["content_sha256"] == after["content_sha256"]
    assert result["reconciliation"]["entry_authority"]["status"] == "PASS"
    assert result["reconciliation"]["blocked_lane_count"] == 1
    assert result["reconciliation"]["product_authorized"] is False
    assert result["correction"]["status"] == "PASS"
    assert result["correction"]["correction_disposition"] == (
        "SUPERSEDED_INVALID_AUTHORITY"
    )
    assert result["parallel_replay"]["status"] == "PASS"
    assert result["parallel_replay"]["parallel_overlap_proven"] is True
    assert result["parallel_replay"]["max_active_workers_observed"] >= 2
    assert result["completion"]["scope_complete"] is True
