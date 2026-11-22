"""Unmocked Wave 2 E2E verification for flywheel Tier A auto-apply and atomic ask_question defect remediation.

Zero unittest.mock, MagicMock, patch, or monkeypatch imports or calls are permitted in this file.
Covers:
1. Full closed-loop E2E (RunTrace -> OnlineGrader -> FindingsQueue -> Tier A Auto-Apply + Tier C ask_question -> Human Approval Receipt -> Finding Transition & Worktree Fix Packet).
2. Degraded LP5 canary rollback recovery and 7-day anti-oscillation cooldown lock.
3. Close-margin (<= 0.20) Tier A escalation to atomic ask_question and post-approval commit execution.
4. Adversarial digest tampering and synthetic supervisor approval bypass rejection.
5. Empty boundary payload and CLI --sandbox subprocess contract.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agents.learning.eligibility import validate_learning_approval_origin
from agents.learning.flywheel_hitl_dispatcher import (
    execute_approved_tier_b_commit,
    record_remediation_decision,
)
from agents.learning.merkle_seal import verify_merkle_seal
from agents.observability.trace_collector import RunTraceCollector, build_run_trace
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.digests import sha256_file
from apps_eval.contracts.schemas import EvalCase, ImprovementProposal
from apps_eval.holdout_replay import evaluate_proposal_in_shadow
from tools.hitl_governance import (
    MAX_OPTION_LENGTH,
    MAX_QUESTION_LENGTH,
    HITLDecisionStore,
    evaluate_hitl_surfacing_gate,
    scan_question_jargon,
    validate_hitl_presentation,
)
from tools.hook_dispatch import handle_pre_ask_question
from tools.run_eval_flywheel_cycle import run_eval_flywheel_cycle

REPO_ROOT = Path(__file__).resolve().parents[2]


def _seed_agents_core_calibration_cases() -> list[dict[str, object]]:
    """Deterministic unlabeled_view development + holdout seeds for routing calibration replay."""
    dev = [
        {
            "case_id": f"e2e-w2-dev-{i}",
            "app_id": "agents_core",
            "split": "development",
            "unlabeled_input": {"score": 0.73},
            "expected_contract": {"reference_label": "PASS"},
        }
        for i in range(3)
    ]
    holdout = [
        {
            "case_id": f"e2e-w2-hold-{i}",
            "app_id": "agents_core",
            "split": "holdout",
            "unlabeled_input": {"score": 0.73 if i < 2 else 0.86},
            "expected_contract": {"reference_label": "PASS"},
        }
        for i in range(5)
    ]
    return dev + holdout


def _write_routing_corrections(src_dir: Path, count: int = 4) -> None:
    rows = [
        json.dumps(
            {
                "correction_id": f"w2-corr-{i}",
                "category": "routing",
                "app_id": "agents_core",
                "source_identifier": "surface_threshold_072",
                "corrected_identifier": "surface_threshold_075",
                "operator_id": "operator",
                "session_id": f"w2-corr-sess-{i}",
                "recorded_at": f"2026-11-21T0{i}:10:00Z",
            }
        )
        for i in range(1, count + 1)
    ]
    (src_dir / "operator_corrections.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _init_empty_hitl_db(src_dir: Path) -> Path:
    db_path = src_dir / "hitl_decisions.sqlite"
    store = HITLDecisionStore(db_path)
    store.close()
    return db_path


def test_full_flywheel_cycle_auto_applies_tier_a_and_routes_tier_c_ask_question_approval_e2e(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    src_dir = tmp_path / "src_learning"
    out_dir = tmp_path / "out_learning"
    src_dir.mkdir()
    hitl_db = _init_empty_hitl_db(src_dir)

    collector = RunTraceCollector(
        traces_path=src_dir / "run_traces.jsonl",
        cursor_path=src_dir / "cursor.json",
    )
    # High-impact Tier C code defect cluster (apps_rg, 4 occurrences across 4 sessions).
    for idx in range(1, 5):
        collector.emit(
            build_run_trace(
                app_id="apps_rg",
                run_id=f"w2-rg-run-{idx}",
                session_id=f"w2-rg-sess-{idx}",
                terminal_status="FAIL",
                raw_input={
                    "jd": f"VP AI Architecture {idx}",
                    "email": f"applicant{idx}@example.test",
                },
                gate_outcomes={"x2_gates": {"grounding": False}},
                telemetry={"latency_ms": 1800.0, "cost_usd": 0.0},
                finished_at_utc=f"2026-11-21T0{idx}:00:00Z",
            )
        )
    # Lower-impact Tier C code defect (apps_lic, 2 occurrences) to verify strict one-at-a-time ranking.
    for idx in range(1, 3):
        collector.emit(
            build_run_trace(
                app_id="apps_lic",
                run_id=f"w2-lic-run-{idx}",
                session_id=f"w2-lic-sess-{idx}",
                terminal_status="FAIL",
                raw_input={"prospect": f"Prospect {idx}"},
                gate_outcomes={"x2_gates": {"tone_guard": False}},
                telemetry={"latency_ms": 950.0, "cost_usd": 0.0},
                finished_at_utc=f"2026-11-21T0{idx}:30:00Z",
            )
        )
    # Tier A bounded calibration cluster (agents_core, 4 recurring routing corrections).
    _write_routing_corrections(src_dir, count=4)

    live_routing_cfg = REPO_ROOT / "config" / "routing_calibration.yaml"
    live_cfg_sha_before = sha256_file(live_routing_cfg)

    exit_code, receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src_dir,
        output_root=out_dir,
        sandbox=True,
        emit_next_hitl_question=True,
        confidence_margin=0.35,
        curated_holdout_seeds=_seed_agents_core_calibration_cases(),
        hitl_db_path=hitl_db,
    )

    assert exit_code == 0, receipt
    assert receipt["marginal_api_cost_usd"] == 0.0
    assert sha256_file(live_routing_cfg) == live_cfg_sha_before
    assert "example.test" not in (out_dir / "golden_eval_cases.json").read_text(encoding="utf-8")

    # Verify Tier A bounded threshold auto-applied in sandbox and sealed LP0..LP5.
    dispatch = receipt["auto_apply_dispatch"]
    assert dispatch["auto_applied_count"] == 1, dispatch
    assert dispatch["rolled_back_count"] == 0
    assert dispatch["pending_hitl_count"] == 2

    seal_path = Path(dispatch["auto_applied"][0]["seal_path"])
    assert seal_path.is_file()
    seal_doc = json.loads(seal_path.read_text(encoding="utf-8"))
    assert verify_merkle_seal(seal_doc) is True

    staged_cfg = out_dir / "sandbox_targets" / "config" / "routing_calibration.yaml"
    assert staged_cfg.is_file()
    assert sha256_file(staged_cfg) != live_cfg_sha_before

    # Verify next_ask_question_payload surfaces strictly 1 plain-English question for highest-impact Tier C defect.
    q_payload = receipt["next_ask_question_payload"]
    assert q_payload is not None
    assert len(q_payload["questions"]) == 1
    q_item = q_payload["questions"][0]
    assert len(q_item["question"]) <= MAX_QUESTION_LENGTH
    assert len(q_item["options"]) == 3
    assert all(len(opt) <= MAX_OPTION_LENGTH for opt in q_item["options"])
    assert scan_question_jargon(q_item["question"]) == []
    assert validate_hitl_presentation(q_payload, enforce_visibility_and_jargon=True) == []

    rc_hook = handle_pre_ask_question({"toolCall": {"args": {"questions": q_payload["questions"]}}}, REPO_ROOT)
    assert rc_hook == 0
    assert '"allow"' in capsys.readouterr().out

    # Verify independent database state and post-approval transition + worktree fix packet.
    q_store = SqliteFindingsQueueStore(out_dir / "remediation_queue.sqlite")
    h_store = HITLDecisionStore(hitl_db)
    try:
        verified_findings = q_store.list_findings(status="VERIFIED")
        assert len(verified_findings) == 1
        assert verified_findings[0].track == "TRACK_1_CALIBRATION"

        open_findings = q_store.list_findings(status="OPEN")
        assert len(open_findings) == 2
        top_open = open_findings[0]
        assert top_open.app_id == "apps_rg"
        assert top_open.impact_score > open_findings[1].impact_score
        assert q_payload["metadata"]["finding_id"] == top_open.finding_id
        assert q_payload["metadata"]["finding_digest"] == top_open.finding_digest

        tier_c_raw = next(
            p
            for p in receipt["synthesized_proposals"]
            if p["proposal_id"] == q_payload["metadata"]["proposal_id"]
        )
        tier_c_prop = ImprovementProposal(**tier_c_raw)
        assert tier_c_prop.autonomy_tier == "TIER_C_PR_ONLY"

        action = record_remediation_decision(
            top_open.finding_id,
            tier_c_prop,
            q_item["options"][0],
            q_store,
            h_store,
            approved_by="operator_human",
            expected_finding_digest=q_payload["metadata"]["finding_digest"],
            expected_proposal_digest=q_payload["metadata"]["proposal_digest"],
            question_payload=q_payload,
            repo_root=REPO_ROOT,
        )
        assert action.action == "EXECUTE_TIER_C_FIX_AND_PROMOTE"
        assert action.finding_status == "IN_PROGRESS"
        assert action.approval_receipt is not None
        ok_origin, origin_msg = validate_learning_approval_origin(action.approval_receipt)
        assert ok_origin is True, origin_msg

        pkt = action.worktree_execution_packet
        assert pkt is not None
        assert pkt["owner_subsystem"] == "resume_graph_engine"
        assert "apps_eval/suites/pinned_fix_regressions.json" in pkt["required_regression_pins"]
        assert any("pr_governance.py promote" in cmd for cmd in pkt["verification_commands"])

        events = q_store.list_events(top_open.finding_id)
        transitions = [(e["from_status"], e["to_status"]) for e in events]
        assert ("OPEN", "APPROVED") in transitions
        assert ("APPROVED", "IN_PROGRESS") in transitions
        assert h_store.get_calibration_metrics()["total_decisions"] == 1
    finally:
        h_store.close()
        q_store.close()


def test_flywheel_cycle_degraded_canary_triggers_exact_rollback_and_blocks_reapply_e2e(tmp_path: Path) -> None:
    src_dir = tmp_path / "src_rb"
    out_dir = tmp_path / "out_rb"
    src_dir.mkdir()
    hitl_db = _init_empty_hitl_db(src_dir)
    _write_routing_corrections(src_dir, count=4)

    # First run without auto-apply to discover the deterministic synthesized Tier A proposal_id.
    _, preview = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src_dir,
        output_root=tmp_path / "preview_rb",
        sandbox=True,
        auto_apply_tier_a=False,
        emit_next_hitl_question=False,
        curated_holdout_seeds=_seed_agents_core_calibration_cases(),
        hitl_db_path=hitl_db,
    )
    tier_a_id = preview["synthesized_proposals"][0]["proposal_id"]

    live_cfg_sha = sha256_file(REPO_ROOT / "config" / "routing_calibration.yaml")
    exit_code, receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src_dir,
        output_root=out_dir,
        sandbox=True,
        confidence_margin=0.35,
        curated_holdout_seeds=_seed_agents_core_calibration_cases(),
        canary_metrics_by_proposal={
            tier_a_id: {
                "quality_score": 0.50,
                "veto_defects": 1,
                "latency_ms": 90.0,
                "pinned_regressions_passed": False,
            }
        },
        baseline_metrics_by_proposal={tier_a_id: {"quality_score": 0.90}},
        hitl_db_path=hitl_db,
    )
    assert exit_code == 0
    dispatch = receipt["auto_apply_dispatch"]
    assert dispatch["auto_applied_count"] == 0
    assert dispatch["rolled_back_count"] == 1
    rb_entry = dispatch["rolled_back"][0]
    assert rb_entry["rollback"]["exact_pre_apply_sha_match"] is True

    staged_cfg = out_dir / "sandbox_targets" / "config" / "routing_calibration.yaml"
    assert sha256_file(staged_cfg) == live_cfg_sha

    # Re-running against the same learning_ledger.sqlite must block re-apply under 7-day rollback cooldown.
    _, second_receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src_dir,
        output_root=tmp_path / "out_rb_retry",
        sandbox=True,
        confidence_margin=0.35,
        curated_holdout_seeds=_seed_agents_core_calibration_cases(),
        hitl_db_path=hitl_db,
        ledger_db_path=out_dir / "learning_ledger.sqlite",
    )
    second_dispatch = second_receipt["auto_apply_dispatch"]
    assert second_dispatch["auto_applied_count"] == 0
    blocking_reasons = second_dispatch["policy_decisions"][0]["blocking_reasons"]
    assert any("POST_ROLLBACK_LOCK_ACTIVE_UNTIL:" in r for r in blocking_reasons)


def test_close_margin_tier_a_escalates_to_atomic_ask_question_and_applies_after_approval_e2e(
    tmp_path: Path,
) -> None:
    src_dir = tmp_path / "src_margin"
    out_dir = tmp_path / "out_margin"
    src_dir.mkdir()
    hitl_db = _init_empty_hitl_db(src_dir)
    _write_routing_corrections(src_dir, count=4)

    exit_code, receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src_dir,
        output_root=out_dir,
        sandbox=True,
        emit_next_hitl_question=True,
        confidence_margin=0.12,
        curated_holdout_seeds=_seed_agents_core_calibration_cases(),
        hitl_db_path=hitl_db,
    )
    assert exit_code == 0
    dispatch = receipt["auto_apply_dispatch"]
    assert dispatch["auto_applied_count"] == 0
    assert dispatch["pending_hitl_count"] == 1

    q_payload = receipt["next_ask_question_payload"]
    assert q_payload is not None
    assert q_payload["metadata"]["effective_mode"] == "TIER_A_ESCALATED"
    assert validate_hitl_presentation(q_payload, enforce_visibility_and_jargon=True) == []
    gate = evaluate_hitl_surfacing_gate(q_payload["questions"][0]["options"])
    assert gate["should_surface"] is True
    assert gate["margin"] <= 0.20

    prop = ImprovementProposal(**receipt["synthesized_proposals"][0])
    seeds = _seed_agents_core_calibration_cases()
    dev_cases = [
        EvalCase(
            case_id=str(s["case_id"]),
            suite_id="agents_core.golden.v1",
            app_id="agents_core",
            split="development",
            execution_mode="snapshot",
            source_kind="curated",
            grounding_tier="OFFLINE_BENCHMARK_GROUNDED",
            unlabeled_input=dict(s["unlabeled_input"]),  # type: ignore[arg-type]
            expected_contract=dict(s["expected_contract"]),  # type: ignore[arg-type]
        )
        for s in seeds
        if s["split"] == "development"
    ]
    hold_cases = [
        EvalCase(
            case_id=str(s["case_id"]),
            suite_id="agents_core.golden.v1",
            app_id="agents_core",
            split="holdout",
            execution_mode="snapshot",
            source_kind="curated",
            grounding_tier="OFFLINE_BENCHMARK_GROUNDED",
            unlabeled_input=dict(s["unlabeled_input"]),  # type: ignore[arg-type]
            expected_contract=dict(s["expected_contract"]),  # type: ignore[arg-type]
        )
        for s in seeds
        if s["split"] == "holdout"
    ]
    verdict = evaluate_proposal_in_shadow(
        proposal=prop,
        target_cluster_cases=dev_cases,
        holdout_cases=hold_cases,
        dataset_digest=receipt["golden_promotion"]["dataset_digest"] or "d" * 64,
        candidate_runner=lambda view, val: {
            "label": "PASS" if float(val) > 0.72 else "FAIL",
            "latency_ms": 35.0,
            "cost_usd": 0.0,
        },
    )
    assert verdict.verdict == "PASS"

    cfg_copy = tmp_path / "routing_calibration_copy.yaml"
    cfg_copy.write_text((REPO_ROOT / "config" / "routing_calibration.yaml").read_text(encoding="utf-8"), encoding="utf-8")

    q_store = SqliteFindingsQueueStore(out_dir / "remediation_queue.sqlite")
    h_store = HITLDecisionStore(hitl_db)
    ledger = SqliteLearningLedgerStore(out_dir / "learning_ledger.sqlite")
    try:
        finding_id = q_payload["metadata"]["finding_id"]
        action = record_remediation_decision(
            finding_id,
            prop,
            q_payload["questions"][0]["options"][0],
            q_store,
            h_store,
            approved_by="operator_human",
            expected_finding_digest=q_payload["metadata"]["finding_digest"],
            expected_proposal_digest=q_payload["metadata"]["proposal_digest"],
            confidence_margin=0.12,
            question_payload=q_payload,
            repo_root=REPO_ROOT,
        )
        assert action.action == "EXECUTE_TIER_B_COMMIT"
        commit_res = execute_approved_tier_b_commit(
            action=action,
            proposal=prop,
            holdout_verdict=verdict,
            repo_root=REPO_ROOT,
            ledger_store=ledger,
            queue_store=q_store,
            hitl_store=h_store,
            rollback_dir=out_dir / "rollbacks",
            seals_dir=out_dir / "seals",
            canary_metrics={
                "quality_score": 0.96,
                "veto_defects": 0,
                "latency_ms": 40.0,
                "pinned_regressions_passed": True,
            },
            baseline_metrics={"quality_score": 0.85},
            target_file_override=cfg_copy,
            confidence_margin=0.12,
        )
        assert commit_res["canary"]["status"] == "APPLIED_AND_SEALED"
        assert verify_merkle_seal(commit_res["canary"]["merkle_seal"]) is True
        updated = q_store.get_finding(finding_id)
        assert updated is not None and updated.status == "VERIFIED"
        assert h_store.get_calibration_metrics()["outcomes"].get("SUCCESS") == 1
    finally:
        ledger.close()
        h_store.close()
        q_store.close()


def test_adversarial_digest_tampering_and_synthetic_supervisor_bypass_rejected_e2e(tmp_path: Path) -> None:
    src_dir = tmp_path / "src_adv"
    out_dir = tmp_path / "out_adv"
    src_dir.mkdir()
    hitl_db = _init_empty_hitl_db(src_dir)

    collector = RunTraceCollector(
        traces_path=src_dir / "run_traces.jsonl",
        cursor_path=src_dir / "cursor.json",
    )
    for idx in range(1, 4):
        collector.emit(
            build_run_trace(
                app_id="apps_rg",
                run_id=f"adv-run-{idx}",
                session_id=f"adv-sess-{idx}",
                terminal_status="FAIL",
                raw_input={"jd": f"Role {idx}"},
                gate_outcomes={"x2_gates": {"grounding": False}},
                telemetry={"latency_ms": 1100.0, "cost_usd": 0.0},
                finished_at_utc=f"2026-11-21T0{idx}:00:00Z",
            )
        )

    _, receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src_dir,
        output_root=out_dir,
        sandbox=True,
        hitl_db_path=hitl_db,
    )
    q_payload = receipt["next_ask_question_payload"]
    assert q_payload is not None
    prop = ImprovementProposal(**receipt["synthesized_proposals"][0])
    fid = q_payload["metadata"]["finding_id"]

    q_store = SqliteFindingsQueueStore(out_dir / "remediation_queue.sqlite")
    h_store = HITLDecisionStore(hitl_db)
    try:
        with pytest.raises(ValueError, match="FINDING_DIGEST_MISMATCH"):
            record_remediation_decision(
                fid,
                prop,
                q_payload["questions"][0]["options"][0],
                q_store,
                h_store,
                approved_by="operator_human",
                expected_finding_digest="f" * 64,
                repo_root=REPO_ROOT,
            )

        with pytest.raises(ValueError, match="PROPOSAL_DIGEST_MISMATCH"):
            record_remediation_decision(
                fid,
                prop,
                q_payload["questions"][0]["options"][0],
                q_store,
                h_store,
                approved_by="operator_human",
                expected_proposal_digest="0" * 64,
                repo_root=REPO_ROOT,
            )

        with pytest.raises(ValueError, match="SYNTHETIC_"):
            record_remediation_decision(
                fid,
                prop,
                q_payload["questions"][0]["options"][0],
                q_store,
                h_store,
                approved_by="autonomous_policy_supervisor",
                repo_root=REPO_ROOT,
            )

        with pytest.raises(ValueError, match="SYNTHETIC_"):
            record_remediation_decision(
                fid,
                prop,
                "Auto-approved by autonomous policy supervisor",
                q_store,
                h_store,
                approved_by="operator_human",
                repo_root=REPO_ROOT,
            )

        unchanged = q_store.get_finding(fid)
        assert unchanged is not None and unchanged.status == "OPEN"
    finally:
        h_store.close()
        q_store.close()


def test_empty_boundary_and_cli_sandbox_subprocess_contract_e2e(tmp_path: Path) -> None:
    empty_src = tmp_path / "empty_src"
    empty_out = tmp_path / "empty_out"
    empty_src.mkdir()
    hitl_db = _init_empty_hitl_db(empty_src)

    code_empty, receipt_empty = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=empty_src,
        output_root=empty_out,
        sandbox=True,
        hitl_db_path=hitl_db,
    )
    assert code_empty == 0
    assert receipt_empty["auto_apply_dispatch"]["auto_applied_count"] == 0
    assert receipt_empty["next_ask_question_payload"] is None

    cli_src = tmp_path / "cli_src"
    cli_src.mkdir()
    _init_empty_hitl_db(cli_src)
    collector = RunTraceCollector(
        traces_path=cli_src / "run_traces.jsonl",
        cursor_path=cli_src / "cursor.json",
    )
    for idx in range(1, 4):
        collector.emit(
            build_run_trace(
                app_id="apps_research",
                run_id=f"cli-run-{idx}",
                session_id=f"cli-sess-{idx}",
                terminal_status="FAIL",
                raw_input={"company": f"Example Corp {idx}"},
                gate_outcomes={"x2_gates": {"citation_grounding": False}},
                telemetry={"latency_ms": 1400.0, "cost_usd": 0.0},
                finished_at_utc=f"2026-11-21T0{idx}:00:00Z",
            )
        )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "run_eval_flywheel_cycle.py"),
            "--repo-root",
            str(REPO_ROOT),
            "--source-root",
            str(cli_src),
            "--sandbox",
            "--emit-next-hitl-question",
            "--json",
        ],
        shell=False,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    cli_receipt = json.loads(proc.stdout)
    assert cli_receipt["sandbox"] is True
    assert cli_receipt["emit_next_hitl_question"] is True
    cli_q = cli_receipt["next_ask_question_payload"]
    assert cli_q is not None
    assert len(cli_q["questions"]) == 1
    assert validate_hitl_presentation(cli_q, enforce_visibility_and_jargon=True) == []


def test_product_run_flywheel_records_specific_failure_reasons_and_auto_resolves_on_pass_e2e(
    tmp_path: Path,
) -> None:
    """Pinned unmocked regression for find-ac2635ccc0df (no generic x3b_escalate_hitl masking + pass auto-resolution)."""
    rg_src = str((REPO_ROOT / "resume_graph_engine" / "src").resolve())
    if rg_src not in sys.path:
        sys.path.insert(0, rg_src)

    from agents.observability.eval_flywheel import EvalFlywheelEngine
    from apps_rg.__main__ import _evaluate_product_run

    run_dir = tmp_path / "full_resume_pin_ac26"
    (run_dir / "section_failure_forensics").mkdir(parents=True)
    (run_dir / "x3_disposition_receipt.json").write_text(
        json.dumps({"payload": {"x3_disposition": "X3A_DENY_REROUTE"}}),
        encoding="utf-8",
    )
    (run_dir / "FINAL_RESUME_OUTPUT.json").write_text(
        json.dumps({"status": "FAIL", "failed_gate_ids": ["final_resume_no_gap_markers"]}),
        encoding="utf-8",
    )
    (run_dir / "section_failure_forensics" / "index.json").write_text(
        json.dumps(
            {"artifacts": [{"section_id": "ibm_narrative", "failure_type": "independent_failure"}]}
        ),
        encoding="utf-8",
    )
    (run_dir / "section_failure_forensics" / "ibm_narrative.json").write_text(
        json.dumps(
            {"failed_gate_ids": ["x2_ibm_narrative_mechanisms_supported_by_cited_companion_bullets"]}
        ),
        encoding="utf-8",
    )

    report = _evaluate_product_run(run_dir)
    assert report["status"] == "BLOCKED"
    assert report["x3_disposition"] == "X3A_DENY_REROUTE"
    reasons = list(report["failure_reasons"])
    assert "x3_disposition:X3A_DENY_REROUTE" in reasons
    assert "section:ibm_narrative:x2_ibm_narrative_mechanisms_supported_by_cited_companion_bullets" in reasons

    fw = EvalFlywheelEngine(
        learning_db_path=tmp_path / "learning" / "feedback.sqlite",
        trajectory_store_path=tmp_path / "learning" / "traj.json",
        calibration_history_path=tmp_path / "learning" / "cal.json",
        graduation_state_path=tmp_path / "learning" / "grad.json",
        triage_root=tmp_path / "triage",
    )
    obs_fail = fw.ingest_product_run(
        app_id="apps_rg",
        run_id="full_resume_pin_ac26",
        x3_disposition=report["x3_disposition"],
        passed=False,
        failure_reasons=reasons,
        score=0.0,
    )
    assert len(obs_fail["harvested_signatures"]) >= 3

    fb = fw._open_feedback_store()
    try:
        stats_before = fb.get_failure_statistics()
        constraints = {r["normalized_constraint"] for r in stats_before}
        assert "apps_rg:x3:x3b_escalate_hitl" not in constraints
        assert any("section:ibm_narrative:" in c for c in constraints)
        assert all(float(r["success_rate"]) == 0.0 for r in stats_before)
    finally:
        fb.close()

    fw.ingest_product_run(
        app_id="apps_rg",
        run_id="full_resume_pin_ac26_pass",
        x3_disposition="X3D_ALLOW_FINISH",
        passed=True,
        failure_reasons=(),
        score=1.0,
    )
    fb2 = fw._open_feedback_store()
    try:
        stats_after = fb2.get_failure_statistics()
        assert all(float(r["success_rate"]) == 1.0 for r in stats_after)
    finally:
        fb2.close()

    assert fw.list_triage_candidates(app_filter="apps_rg", pending_only=True) == []
    all_triage = fw.list_triage_candidates(app_filter="apps_rg", pending_only=False)
    assert len(all_triage) >= 3
    assert all(pkt.get("status") == "RESOLVED" for pkt in all_triage)

    from agents.observability.findings_consolidator import consolidate_all_findings

    consol = consolidate_all_findings(
        source_root=tmp_path / "learning",
        output_root=tmp_path / "consol_out",
        triage_root=tmp_path / "triage",
    )
    assert consol["ingested_by_surface"]["eval_harness"] == 0
    assert consol["total_findings"] == 0

