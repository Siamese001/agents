from __future__ import annotations

import copy
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
from apps_rg.runtime.contracts.plan_execution_receipt import (
    PLAN_EXECUTION_RECEIPT_SCHEMA_VERSION,
    PlanExecutionReceiptError,
    build_plan_execution_receipt,
    failure_taxonomy_by_code,
    load_failure_taxonomy,
    receipt_digest,
    validate_plan_execution_receipt,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "fixtures"
    / "apps_rg"
    / "l1_plan_execution_receipt_matrix.v1.json"
)


def _fixture_cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


def _payload(*, blocked: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "generation_mode": "strategic_tailor",
        "target_company": "ExampleCo",
        "target_role": "VP Product",
        "target_level": "VP",
        "source_resume_text": "Evidence-backed product experience.",
    }
    if not blocked:
        payload["job_description_text"] = "Own product strategy and execution."
    return payload


def _capsule(*, blocked: bool = False) -> dict:
    return build_apps_rg_l1_planning_capsule(
        app_payload=_payload(blocked=blocked),
        request_id="w0-request",
        run_id="w0-run",
        trace_id="w0-trace",
        replay_key="w0-replay",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )


def _outcomes(capsule: dict, case: dict[str, object]) -> list[dict[str, object]]:
    disposition = str(case["disposition"])
    failure_code = str(case["failure_code"])
    attempted = bool(case["attempted"])
    rows: list[dict[str, object]] = []
    for unit in capsule["work_units"]:
        unit_id = str(unit["unit_id"])
        rows.append(
            {
                "unit_id": unit_id,
                "disposition": disposition,
                "attempted": attempted,
                "failure_code": failure_code,
                "artifact_refs": [f"artifacts/{unit_id}/outcome.json"]
                if disposition == "COMPLETED"
                else [],
                "control_receipt_refs": [],
            }
        )
    return rows


@pytest.mark.parametrize("case", _fixture_cases(), ids=lambda row: str(row["case_id"]))
def test_w0_fixture_matrix_builds_complete_digest_bound_receipts(
    case: dict[str, object],
) -> None:
    capsule = _capsule(blocked=case["plan_status"] == "BLOCKED")
    assert capsule["planning_status"] == case["plan_status"]

    receipt = build_plan_execution_receipt(
        request_id="w0-request",
        run_id="w0-run",
        plan_capsule=capsule,
        unit_outcomes=_outcomes(capsule, case),
    )

    assert receipt["schema_version"] == PLAN_EXECUTION_RECEIPT_SCHEMA_VERSION
    assert receipt["authority_class"] == "OBSERVABILITY_ONLY_W0"
    assert receipt["summary"]["all_planned_units_reconciled"] is True
    assert receipt["summary"]["reconciled_unit_count"] == len(capsule["work_units"])
    assert receipt["plan"]["planning_status"] == case["plan_status"]
    assert all(
        row["failure_class"] == case["expected_failure_class"]
        for row in receipt["unit_outcomes"]
    )
    validate_plan_execution_receipt(receipt)


def test_w0_taxonomy_is_explicit_and_declares_only_future_replan_hints() -> None:
    taxonomy = load_failure_taxonomy()
    codes = failure_taxonomy_by_code(taxonomy)

    assert set(codes) >= {
        "L1_PLAN_BLOCKED",
        "REQUIRED_PROOF_ABSENT",
        "RETRIEVAL_FAILED",
        "GENERATION_FAILED",
        "POLICY_BLOCKED",
    }
    assert codes["REQUIRED_PROOF_ABSENT"]["w2_replan_hint"] == "REPLAN_EVIDENCE"
    assert codes["RETRIEVAL_FAILED"]["w2_replan_hint"] == "REPLAN_RETRIEVAL"
    assert codes["GENERATION_FAILED"]["w2_replan_hint"] == "REPAIR_OR_RETRY_GENERATION"
    assert codes["POLICY_BLOCKED"]["w2_replan_hint"] == "TERMINAL_BLOCK"


def test_w0_rejects_missing_or_duplicate_planned_unit_outcomes() -> None:
    capsule = _capsule()
    case = _fixture_cases()[0]
    outcomes = _outcomes(capsule, case)

    with pytest.raises(PlanExecutionReceiptError, match="no outcome for planned units"):
        build_plan_execution_receipt(
            request_id="w0-request",
            run_id="w0-run",
            plan_capsule=capsule,
            unit_outcomes=outcomes[:-1],
        )
    with pytest.raises(PlanExecutionReceiptError, match="duplicate execution outcome"):
        build_plan_execution_receipt(
            request_id="w0-request",
            run_id="w0-run",
            plan_capsule=capsule,
            unit_outcomes=outcomes + [outcomes[0]],
        )


def test_w0_rejects_tampering_and_unclassified_failure_codes() -> None:
    capsule = _capsule()
    case = _fixture_cases()[2]
    receipt = build_plan_execution_receipt(
        request_id="w0-request",
        run_id="w0-run",
        plan_capsule=capsule,
        unit_outcomes=_outcomes(capsule, case),
    )
    tampered = copy.deepcopy(receipt)
    tampered["unit_outcomes"][0]["failure_code"] = "UNKNOWN_FAILURE"
    with pytest.raises(PlanExecutionReceiptError, match="digest mismatch"):
        validate_plan_execution_receipt(tampered)

    taxonomy_tampered = copy.deepcopy(receipt)
    taxonomy_tampered["taxonomy_digest"] = "sha256:" + "0" * 64
    taxonomy_tampered["receipt_digest"] = receipt_digest(taxonomy_tampered)
    with pytest.raises(PlanExecutionReceiptError, match="taxonomy digest mismatch"):
        validate_plan_execution_receipt(taxonomy_tampered)

    with pytest.raises(PlanExecutionReceiptError, match="unclassified failure_code"):
        build_plan_execution_receipt(
            request_id="w0-request",
            run_id="w0-run",
            plan_capsule=capsule,
            unit_outcomes=[
                {
                    **row,
                    "failure_code": "UNKNOWN_FAILURE",
                }
                for row in _outcomes(capsule, case)
            ],
        )
