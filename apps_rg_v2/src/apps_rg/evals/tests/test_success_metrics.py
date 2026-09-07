from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from apps_rg.evals.success_metrics import (
    APPS_RESEARCH_HANDOFF_RECEIPT_VERSION,
    CONTRACT_VERSION,
    RECEIPT_VERSION,
    build_w0_success_metric_receipt,
    canonical_digest,
    evaluate_apps_research_u0_prerequisite,
    load_success_metric_contract,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "success_metric_receipt.v1.schema.json"


def _handoff_receipt(*, valid: bool = True, status: str = "PASS") -> dict[str, object]:
    return {
        "schema_version": APPS_RESEARCH_HANDOFF_RECEIPT_VERSION,
        "observed": True,
        "valid": valid,
        "status": status,
    }


def _receipt_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_w0_contract_defines_outcomes_authority_and_diagnostic_roles() -> None:
    contract = load_success_metric_contract()

    assert contract["schema_version"] == CONTRACT_VERSION
    assert contract["principles"] == {
        "no_blended_overall_score": True,
        "missing_evidence_is_pass": False,
        "diagnostic_gate_pass_is_outcome_success": False,
        "technical_validation_is_human_qualification": False,
        "human_qualification_is_release_authorization": False,
        "release_authorization_is_production_authorization": False,
        "runtime_execution_or_mutation": "forbidden",
    }
    assert tuple(contract["primary_outcomes"]) == ("P1", "P2")
    assert contract["primary_outcomes"]["P1"]["implementation_status"] == "NOT_MEASURED"
    assert contract["primary_outcomes"]["P2"]["implementation_status"] == "NOT_MEASURED"
    assert set(contract["authority_tiers"]) == {
        "technical_validation",
        "human_qualified",
        "release_authorized",
        "production_authorized",
    }
    assert all(
        role == {"role": "diagnostic", "may_authorize_outcome": False}
        for role in contract["diagnostic_gate_roles"].values()
    )
    assert contract["threshold_and_promotion_rules"]["promotion_scope"] == "future_runs_only"


@pytest.mark.parametrize(
    ("handoff_receipt", "expected_status", "expected_reason"),
    (
        (None, "UNKNOWN", "APPS_RESEARCH_HANDOFF_RECEIPT_MISSING"),
        ({"schema_version": "wrong"}, "UNKNOWN", "APPS_RESEARCH_HANDOFF_RECEIPT_SCHEMA_INVALID"),
        (
            {
                "schema_version": APPS_RESEARCH_HANDOFF_RECEIPT_VERSION,
                "observed": False,
                "valid": False,
            },
            "UNKNOWN",
            "APPS_RESEARCH_HANDOFF_NOT_OBSERVED",
        ),
        (_handoff_receipt(valid=False, status="BLOCKED"), "FAIL", "APPS_RESEARCH_HANDOFF_VALIDATION_FAILED"),
    ),
)
def test_apps_research_to_u0_prerequisite_fails_closed(
    handoff_receipt: dict[str, object] | None,
    expected_status: str,
    expected_reason: str,
) -> None:
    result = evaluate_apps_research_u0_prerequisite(handoff_receipt)

    assert result["status"] == expected_status
    assert result["reason_codes"] == [expected_reason]


def test_validated_apps_research_handoff_is_required_but_not_outcome_success() -> None:
    receipt = build_w0_success_metric_receipt(
        evaluation_id="w0-fixture",
        apps_research_handoff_receipt=_handoff_receipt(),
    )

    _receipt_validator().validate(receipt)
    assert receipt["schema_version"] == RECEIPT_VERSION
    assert receipt["hard_prerequisites"]["apps_research_to_u0"]["status"] == "PASS"
    assert receipt["outcomes"]["P1"]["status"] == "NOT_MEASURED"
    assert receipt["outcomes"]["P2"]["status"] == "NOT_MEASURED"
    assert receipt["promotion_eligible"] is False
    assert receipt["authority"]["release_authorizing"] is False
    assert receipt["record_digest"] == canonical_digest(
        {key: value for key, value in receipt.items() if key != "record_digest"}
    )


def test_invalid_observed_handoff_blocks_w0_receipt_and_never_promotes() -> None:
    receipt = build_w0_success_metric_receipt(
        evaluation_id="w0-invalid-handoff",
        apps_research_handoff_receipt=_handoff_receipt(valid=False, status="BLOCKED"),
    )

    _receipt_validator().validate(receipt)
    assert receipt["hard_prerequisites"]["apps_research_to_u0"]["status"] == "FAIL"
    assert "APPS_RESEARCH_TO_U0_PREREQUISITE_NOT_PASS" in receipt["blocking_reasons"]
    assert receipt["promotion_eligible"] is False


def test_direct_validator_receipt_without_status_remains_usable() -> None:
    result = evaluate_apps_research_u0_prerequisite(
        {
            "schema_version": APPS_RESEARCH_HANDOFF_RECEIPT_VERSION,
            "observed": True,
            "valid": True,
            "reason": "ok",
        }
    )

    assert result == {
        "status": "PASS",
        "observed": True,
        "valid": True,
        "reason_codes": [],
    }
