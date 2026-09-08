from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.pipeline_attempt_evaluation import (
    MANIFEST_VERSION,
    current_source_identity,
    expected_element_evidence,
    measurement_authority_requirements,
    required_slice_keys,
    validate_pipeline_attempt_evaluation,
)
from apps_rg.evals.pipeline_measurement_coverage import (
    DEFAULT_CONTRACT_PATH,
    GUARDRAILS,
    load_pipeline_measurement_coverage,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "pipeline_attempt_evaluation.v1.schema.json"
DEFAULT_MANIFEST_PATH = EVALS_ROOT / "pipeline_attempt_evaluation.v1.json"


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _contract() -> dict[str, object]:
    return load_pipeline_measurement_coverage(DEFAULT_CONTRACT_PATH)


def _manifest(member_ids: list[str]) -> dict[str, object]:
    return {
        "schema_version": MANIFEST_VERSION,
        "evaluation_id": "pipeline-attempt-test",
        "source_identity": current_source_identity(),
        "cohort": {
            "status": "FROZEN",
            "cohort_id": "frozen-test-cohort",
            "data_split": "calibration",
            "frozen_member_ids": member_ids,
            "frozen_member_ids_digest": _digest("wrong-placeholder"),
        },
        "attempts": [],
    }


def _freeze_manifest(manifest: dict[str, object]) -> None:
    cohort = manifest["cohort"]
    assert isinstance(cohort, dict)
    members = cohort["frozen_member_ids"]
    assert isinstance(members, list)
    import apps_rg.evals.pipeline_attempt_evaluation as attempt_module

    cohort["frozen_member_ids_digest"] = attempt_module.canonical_digest(members)


def _evidence(
    terminal_status: str,
    terminal_stage: str | None,
    *,
    optional_trace_status: str = "PASS",
) -> list[dict[str, object]]:
    contract = _contract()
    expected = expected_element_evidence(contract)
    stage_order = (
        "apps_research",
        "U0",
        "L1",
        "L0",
        "C0",
        "PA",
        "L2",
        "X2",
        "X1D",
        "X3",
        "EXIT",
        "UWG",
        "L6",
        "PACKAGE",
        "REGRESSION",
    )
    terminal_index = stage_order.index(terminal_stage) if terminal_stage else -1
    rows: list[dict[str, object]] = []
    for (element_id, lane_id), row in expected.items():
        stage_id = row["stage_id"]
        assert isinstance(stage_id, str)
        if terminal_status == "COMPLETE":
            status = (
                optional_trace_status
                if element_id == "cross_run_l6_trace"
                else "PASS"
            )
        elif terminal_status in {"FAILED", "ABSTAINED"}:
            stage_index = stage_order.index(stage_id)
            if stage_index < terminal_index:
                status = "PASS"
            elif stage_id == terminal_stage:
                status = "FAIL" if terminal_status == "FAILED" else "ABSTAINED"
            else:
                status = "NOT_RUN"
        else:
            status = "FAIL" if stage_id == "apps_research" else "NOT_RUN"
        roles = row["artifact_roles"]
        assert isinstance(roles, list)
        rows.append(
            {
                "element_id": element_id,
                "scope": row["scope"],
                "stage_id": stage_id,
                "lane_id": lane_id,
                "status": status,
                "artifact_digests": {
                    role: _digest(f"{element_id}:{lane_id}:{role}")
                    for role in roles
                }
                if status == "PASS"
                else {},
                "reason_codes": [] if status == "PASS" else [f"{status}_{stage_id}"],
            }
        )
    return rows


def _diagnostics(status: str = "PASS") -> dict[str, dict[str, object]]:
    authorities, _ = measurement_authority_requirements(_contract())
    return {
        gate: {
            "status": status,
            "record_digest": _digest(gate) if status != "NOT_MEASURED" else "",
            "authority_tier": authorities[gate],
        }
        for gate in authorities
    }


def _guardrails(status: str = "PASS") -> dict[str, dict[str, object]]:
    _, authorities = measurement_authority_requirements(_contract())
    return {
        guardrail: {
            "status": status,
            "count": 0 if status == "PASS" else None,
            "record_digest": _digest(guardrail) if status != "NOT_MEASURED" else "",
            "authority_tier": authorities[guardrail],
        }
        for guardrail in GUARDRAILS
    }


def _attempt(
    member_id: str,
    terminal_status: str,
    terminal_stage: str | None = None,
    *,
    optional_trace_status: str = "PASS",
) -> dict[str, object]:
    is_excluded = terminal_status == "NOT_STARTED"
    if terminal_status == "COMPLETE":
        terminal_stage = "EXIT"
    elif terminal_status in {"FAILED", "ABSTAINED"}:
        terminal_stage = terminal_stage or "C0"
    contract = _contract()
    slices = {
        key: f"{key}-value" for key in required_slice_keys(contract)
    }
    slices.update(
        {
            "data_split": "calibration",
            "provider": "NOT_APPLICABLE" if is_excluded else "test-provider",
            "model": "NOT_APPLICABLE" if is_excluded else "test-model",
            "cache_mode": "NOT_APPLICABLE" if is_excluded else "COLD",
            "runtime_configuration": "NOT_APPLICABLE"
            if is_excluded
            else _digest("runtime-config"),
        }
    )
    return {
        "attempt_id": f"attempt-{member_id}",
        "cohort_member_id": member_id,
        "input_digest": _digest(f"input-{member_id}"),
        "population_status": "EXCLUDED" if is_excluded else "ELIGIBLE",
        "exclusion_reason": "research-handoff-failed" if is_excluded else None,
        "apps_research_to_u0": {
            "observed": not is_excluded,
            "valid": not is_excluded,
            "status": "FAIL" if is_excluded else "PASS",
            "receipt_digest": "" if is_excluded else _digest(f"handoff-{member_id}"),
        },
        "runtime": None
        if is_excluded
        else {
            "provider": "test-provider",
            "model": "test-model",
            "configuration_digest": _digest("runtime-config"),
            "cache_mode": "COLD",
        },
        "terminal_status": terminal_status,
        "terminal_stage": None if is_excluded else terminal_stage,
        "terminal_reason": None
        if terminal_status == "COMPLETE" or is_excluded
        else f"{terminal_status.lower()}-at-{terminal_stage}",
        "slice_values": slices,
        "element_evidence": _evidence(
            terminal_status,
            terminal_stage,
            optional_trace_status=optional_trace_status,
        ),
        "diagnostic_receipts": _diagnostics(
            "NOT_MEASURED" if is_excluded else "PASS"
        ),
        "guardrails": _guardrails("NOT_MEASURED" if is_excluded else "PASS"),
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_schema_and_tracked_manifest_remain_pending_without_authority() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    tracked = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(tracked)

    result = validate_pipeline_attempt_evaluation()

    assert result["status"] == "NOT_MEASURED"
    assert result["cohort"]["status"] == "PENDING"
    assert result["authority"]["human_qualified"] is False
    assert result["authority"]["release_authorizing"] is False


def test_complete_attempt_uses_frozen_cohort_and_allows_optional_trace_absence(
    tmp_path: Path,
) -> None:
    manifest = _manifest(["complete"])
    _freeze_manifest(manifest)
    attempts = manifest["attempts"]
    assert isinstance(attempts, list)
    attempts.append(
        _attempt("complete", "COMPLETE", optional_trace_status="NOT_RUN")
    )
    path = tmp_path / "complete.json"
    _write(path, manifest)

    result = validate_pipeline_attempt_evaluation(path)

    assert result["status"] == "PASS"
    assert result["population_metrics"] == {
        "eligible_attempt_count": 1,
        "excluded_attempt_count": 0,
        "complete_attempt_count": 1,
        "failed_attempt_count": 0,
        "abstained_attempt_count": 0,
        "grounded_decision_ready_completion_rate": 1.0,
    }
    assert result["outcomes"]["P2"]["status"] == "NOT_MEASURED"
    assert result["authority"]["human_qualified"] is False


def test_failures_abstentions_and_exclusions_preserve_the_frozen_denominator(
    tmp_path: Path,
) -> None:
    members = ["complete", "failed", "abstained", "excluded"]
    manifest = _manifest(members)
    _freeze_manifest(manifest)
    attempts = manifest["attempts"]
    assert isinstance(attempts, list)
    attempts.extend(
        [
            _attempt("complete", "COMPLETE"),
            _attempt("failed", "FAILED", "C0"),
            _attempt("abstained", "ABSTAINED", "C0"),
            _attempt("excluded", "NOT_STARTED"),
        ]
    )
    path = tmp_path / "denominator.json"
    _write(path, manifest)

    result = validate_pipeline_attempt_evaluation(path)

    assert result["status"] == "PASS"
    metrics = result["population_metrics"]
    assert metrics["eligible_attempt_count"] == 3
    assert metrics["complete_attempt_count"] == 1
    assert metrics["failed_attempt_count"] == 1
    assert metrics["abstained_attempt_count"] == 1
    assert metrics["excluded_attempt_count"] == 1
    assert metrics["grounded_decision_ready_completion_rate"] == 1 / 3


def test_terminal_stage_must_match_the_failed_or_abstained_evidence(
    tmp_path: Path,
) -> None:
    manifest = _manifest(["failed"])
    _freeze_manifest(manifest)
    attempts = manifest["attempts"]
    assert isinstance(attempts, list)
    failed = _attempt("failed", "FAILED", "C0")
    failed["terminal_stage"] = "L0"
    attempts.append(failed)
    path = tmp_path / "wrong-terminal-stage.json"
    _write(path, manifest)

    result = validate_pipeline_attempt_evaluation(path)

    assert result["status"] == "BLOCKED"
    assert "INCOMPLETE_ATTEMPT_TERMINAL_EVIDENCE_MISSING" in result[
        "blocking_reasons"
    ]


def test_stale_source_identity_or_wrong_authority_cannot_qualify_an_attempt(
    tmp_path: Path,
) -> None:
    manifest = _manifest(["complete"])
    _freeze_manifest(manifest)
    attempts = manifest["attempts"]
    assert isinstance(attempts, list)
    attempts.append(_attempt("complete", "COMPLETE"))
    source_identity = manifest["source_identity"]
    assert isinstance(source_identity, dict)
    source_identity["coverage_contract_digest"] = _digest("stale")
    path = tmp_path / "stale-source.json"
    _write(path, manifest)

    stale = validate_pipeline_attempt_evaluation(path)
    assert stale["status"] == "BLOCKED"
    assert "PIPELINE_COVERAGE_CONTRACT_STALE" in stale["blocking_reasons"]

    authority = copy.deepcopy(_manifest(["complete"]))
    _freeze_manifest(authority)
    authority_attempts = authority["attempts"]
    assert isinstance(authority_attempts, list)
    invalid_attempt = _attempt("complete", "COMPLETE")
    diagnostics = invalid_attempt["diagnostic_receipts"]
    assert isinstance(diagnostics, dict)
    g1 = diagnostics["G1"]
    assert isinstance(g1, dict)
    g1["authority_tier"] = "technical_validation"
    guardrails = invalid_attempt["guardrails"]
    assert isinstance(guardrails, dict)
    claims = guardrails["unsupported_material_claim_count"]
    assert isinstance(claims, dict)
    claims["authority_tier"] = "technical_validation"
    authority_attempts.append(invalid_attempt)
    authority_path = tmp_path / "wrong-authority.json"
    _write(authority_path, authority)

    invalid = validate_pipeline_attempt_evaluation(authority_path)
    assert invalid["status"] == "BLOCKED"
    assert "ATTEMPT_DIAGNOSTIC_AUTHORITY_INVALID" in invalid["blocking_reasons"]
    assert "ATTEMPT_GUARDRAIL_AUTHORITY_INVALID" in invalid["blocking_reasons"]


def test_slice_values_must_bind_to_the_frozen_split_and_runtime_identity(
    tmp_path: Path,
) -> None:
    manifest = _manifest(["complete"])
    _freeze_manifest(manifest)
    attempts = manifest["attempts"]
    assert isinstance(attempts, list)
    attempt = _attempt("complete", "COMPLETE")
    slices = attempt["slice_values"]
    assert isinstance(slices, dict)
    slices["provider"] = "wrong-provider"
    slices["data_split"] = "holdout"
    attempts.append(attempt)
    path = tmp_path / "mismatched-slices.json"
    _write(path, manifest)

    result = validate_pipeline_attempt_evaluation(path)

    assert result["status"] == "BLOCKED"
    assert "ATTEMPT_SLICE_RUNTIME_MISMATCH" in result["blocking_reasons"]
    assert "ATTEMPT_SLICE_DATA_SPLIT_MISMATCH" in result["blocking_reasons"]
