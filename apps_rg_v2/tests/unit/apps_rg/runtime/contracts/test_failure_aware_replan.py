from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.runtime.bindings.l1_planning_capsule import (
    build_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.failure_aware_replan import (
    FAILURE_AWARE_REPLAN_SCHEMA_VERSION,
    FailureAwareReplanError,
    build_failure_aware_replan,
    emit_failure_aware_replan,
    validate_failure_aware_replan,
)
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    build_plan_execution_reconciliation,
)
from apps_rg.runtime.contracts.plan_execution_receipt import receipt_digest
from apps_rg.runtime.dispatch.spine_stage_receipts import FILENAME_PLAN_REPLAN_DECISION


def _capsule(*, blocked: bool = False) -> dict:
    payload: dict[str, str] = {
        "generation_mode": "strategic_tailor",
        "target_company": "ExampleCo",
        "target_role": "VP Product",
        "source_resume_text": "Evidence-backed product experience.",
    }
    if not blocked:
        payload["job_description_text"] = "Own product strategy and execution."
    return build_apps_rg_l1_planning_capsule(
        app_payload=payload,
        request_id="w2-request",
        run_id="w2-run",
        trace_id="w2-trace",
        replay_key="w2-replay",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def _w1_receipt(tmp_path: Path, *, fault: str = "", executed: bool = True) -> tuple[dict, dict]:
    capsule = _capsule()
    _write(tmp_path / "runtime_execution_witness.json")
    receipt = build_plan_execution_reconciliation(
        request_id="w2-request",
        run_id="w2-run",
        plan_capsule=capsule,
        artifact_dir=tmp_path,
        execution_witness={"l2": {"executed": executed, "fault": fault}},
    )
    return capsule, receipt


def test_w2_evidence_gap_replan_is_digest_bound_and_prohibits_generation_retry(
    tmp_path: Path,
) -> None:
    capsule, receipt = _w1_receipt(tmp_path)

    decision = build_failure_aware_replan(
        plan_capsule=capsule,
        parent_plan_ref="l1_planning_capsule.json",
        plan_execution_receipt=receipt,
        trigger_receipt_ref="plan_execution_receipt.json",
    )

    assert decision["schema_version"] == FAILURE_AWARE_REPLAN_SCHEMA_VERSION
    assert decision["replan_status"] == "REPLAN_PROPOSED"
    assert decision["replan_revision"]["parent_plan_capsule_digest"] == capsule["capsule_digest"]
    assert decision["replan_revision"]["trigger_receipt_digest"] == receipt["receipt_digest"]
    assert {row["strategy"] for row in decision["replan_actions"]} == {"REPLAN_EVIDENCE"}
    assert all(row["generation_retry_prohibited"] is True for row in decision["replan_actions"])
    assert all(row["automatic_execution"] is False for row in decision["replan_actions"])
    validate_failure_aware_replan(
        decision,
        plan_capsule=capsule,
        plan_execution_receipt=receipt,
    )


def test_w2_generation_failure_proposes_governed_repair_without_executing_it(
    tmp_path: Path,
) -> None:
    capsule, receipt = _w1_receipt(tmp_path, fault="L2_EXECUTION_ERROR:RuntimeError:boom")

    decision = build_failure_aware_replan(
        plan_capsule=capsule,
        parent_plan_ref="l1_planning_capsule.json",
        plan_execution_receipt=receipt,
        trigger_receipt_ref="plan_execution_receipt.json",
    )

    assert {row["strategy"] for row in decision["replan_actions"]} == {
        "REPAIR_OR_RETRY_GENERATION"
    }
    assert all(row["next_governed_owner"] == "L2" for row in decision["replan_actions"])
    assert all(row["requires_new_governed_generation"] is True for row in decision["replan_actions"])
    assert all(row["automatic_retry"] is False for row in decision["replan_actions"])


def test_w2_uses_the_frozen_retrieval_hint_instead_of_a_generation_retry(
    tmp_path: Path,
) -> None:
    capsule, receipt = _w1_receipt(tmp_path)
    target = receipt["unit_outcomes"][0]["unit_id"]
    receipt = copy.deepcopy(receipt)
    for row in receipt["unit_outcomes"]:
        if row["unit_id"] == target:
            row.update(
                {
                    "disposition": "FAILED",
                    "attempted": True,
                    "failure_code": "RETRIEVAL_FAILED",
                    "failure_class": "RETRIEVAL",
                    "w2_replan_hint": "REPLAN_RETRIEVAL",
                }
            )
    for row in receipt["unit_observations"]:
        if row["unit_id"] == target:
            row.update({"disposition": "FAILED", "attempted": True})
    by_disposition = {name: 0 for name in ("BLOCKED", "COMPLETED", "FAILED", "SKIPPED")}
    failure_counts: dict[str, int] = {}
    for row in receipt["unit_outcomes"]:
        by_disposition[row["disposition"]] += 1
        if row["failure_code"]:
            failure_counts[row["failure_code"]] = failure_counts.get(row["failure_code"], 0) + 1
    receipt["summary"]["by_disposition"] = by_disposition
    receipt["summary"]["failure_code_counts"] = failure_counts
    receipt["receipt_digest"] = receipt_digest(receipt)

    decision = build_failure_aware_replan(
        plan_capsule=capsule,
        parent_plan_ref="l1_planning_capsule.json",
        plan_execution_receipt=receipt,
        trigger_receipt_ref="plan_execution_receipt.json",
    )

    action = next(row for row in decision["replan_actions"] if row["unit_id"] == target)
    assert action["strategy"] == "REPLAN_RETRIEVAL"
    assert action["next_governed_owner"] == "C0"
    assert action["generation_retry_prohibited"] is True


def test_w2_terminal_block_emits_a_decision_without_a_replan_revision(tmp_path: Path) -> None:
    capsule, receipt = _w1_receipt(tmp_path, executed=False)

    decision = build_failure_aware_replan(
        plan_capsule=capsule,
        parent_plan_ref="l1_planning_capsule.json",
        plan_execution_receipt=receipt,
        trigger_receipt_ref="plan_execution_receipt.json",
    )

    assert decision["replan_status"] == "NO_ACTIONABLE_REPLAN"
    assert decision["replan_actions"] == []
    assert decision["replan_revision"] is None
    assert {row["classification"] for row in decision["failure_classifications"]} == {
        "TERMINAL_BLOCKED"
    }


def test_w2_rejects_tampered_retry_strategy_even_when_redigested(tmp_path: Path) -> None:
    capsule, receipt = _w1_receipt(tmp_path)
    decision = build_failure_aware_replan(
        plan_capsule=capsule,
        parent_plan_ref="l1_planning_capsule.json",
        plan_execution_receipt=receipt,
        trigger_receipt_ref="plan_execution_receipt.json",
    )
    tampered = copy.deepcopy(decision)
    tampered["replan_actions"][0]["strategy"] = "REPAIR_OR_RETRY_GENERATION"
    body = dict(tampered)
    body.pop("decision_digest", None)
    tampered["decision_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(FailureAwareReplanError, match="replan actions do not match"):
        validate_failure_aware_replan(
            tampered,
            plan_capsule=capsule,
            plan_execution_receipt=receipt,
        )


def test_w2_emits_a_decision_bound_to_the_w1_artifact(tmp_path: Path) -> None:
    capsule, receipt = _w1_receipt(tmp_path)
    parent_path = tmp_path / "l1_planning_capsule.json"
    parent_path.write_text(json.dumps(capsule), encoding="utf-8")
    w1_path = tmp_path / "plan_execution_receipt.json"
    w1_path.write_text(json.dumps(receipt), encoding="utf-8")

    path = emit_failure_aware_replan(
        parent_plan_capsule_path=parent_path,
        plan_execution_receipt_path=w1_path,
        artifact_dir=tmp_path,
    )

    assert path == tmp_path / FILENAME_PLAN_REPLAN_DECISION
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["trigger_receipt"]["receipt_ref"] == "plan_execution_receipt.json"
    assert persisted["replan_revision"]["trigger_receipt_digest"] == receipt["receipt_digest"]
