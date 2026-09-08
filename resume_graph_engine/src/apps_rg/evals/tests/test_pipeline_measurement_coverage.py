from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from apps_rg.evals.pipeline_measurement_coverage import (
    COVERAGE_VERSION,
    DEFAULT_CONTRACT_PATH,
    expected_pipeline_elements,
    runtime_lanes,
    validate_pipeline_measurement_coverage,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "pipeline_measurement_coverage.v1.schema.json"


def _contract() -> dict[str, object]:
    value = yaml.safe_load(DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_schema_and_tracked_coverage_contract_cover_current_runtime() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    contract = _contract()
    Draft202012Validator(schema).validate(contract)

    result = validate_pipeline_measurement_coverage()

    assert contract["schema_version"] == COVERAGE_VERSION
    assert result["status"] == "PASS"
    assert result["runtime_lanes"] == list(runtime_lanes())
    assert result["expected_element_count"] == len(expected_pipeline_elements())
    assert result["declared_element_count"] == len(expected_pipeline_elements())
    assert result["authority"]["human_qualified"] is False
    assert result["authority"]["release_authorizing"] is False


def test_missing_runtime_element_fails_closed(tmp_path: Path) -> None:
    contract = copy.deepcopy(_contract())
    coverage = contract["coverage"]
    assert isinstance(coverage, list)
    contract["coverage"] = [
        row
        for row in coverage
        if not (
            isinstance(row, dict)
            and row.get("scope") == "lane"
            and row.get("stage_id") == "X3"
        )
    ]
    path = tmp_path / "missing-lane-stage.yaml"
    _write(path, contract)

    result = validate_pipeline_measurement_coverage(path)

    assert result["status"] == "BLOCKED"
    assert "COVERAGE_RUNTIME_ELEMENTS_MISSING" in result["blocking_reasons"]


def test_incomplete_artifact_roles_and_regression_authority_fail_closed(
    tmp_path: Path,
) -> None:
    contract = copy.deepcopy(_contract())
    coverage = contract["coverage"]
    assert isinstance(coverage, list)
    lane_l2 = next(
        row
        for row in coverage
        if isinstance(row, dict)
        and row.get("scope") == "lane"
        and row.get("stage_id") == "L2"
    )
    assert isinstance(lane_l2, dict)
    lane_l2["artifact_roles"] = ["lane_l2_output"]
    regression = next(
        row
        for row in coverage
        if isinstance(row, dict)
        and row.get("scope") == "cross_run"
        and row.get("stage_id") == "REGRESSION"
    )
    assert isinstance(regression, dict)
    links = regression["metric_links"]
    assert isinstance(links, list) and isinstance(links[0], dict)
    links[0]["role"] = "outcome"
    links[0]["authority_required"] = "human_qualified"
    path = tmp_path / "invalid-coverage.yaml"
    _write(path, contract)

    result = validate_pipeline_measurement_coverage(path)

    assert result["status"] == "BLOCKED"
    assert "COVERAGE_ROW_ARTIFACT_ROLES_INCOMPLETE" in result["blocking_reasons"]
    assert "REGRESSION_LINK_AUTHORITY_INVALID" in result["blocking_reasons"]


def test_primary_outcomes_require_a_direct_outcome_link(tmp_path: Path) -> None:
    contract = copy.deepcopy(_contract())
    coverage = contract["coverage"]
    assert isinstance(coverage, list)
    for row in coverage:
        if not isinstance(row, dict):
            continue
        links = row.get("metric_links")
        if not isinstance(links, list):
            continue
        for link in links:
            if isinstance(link, dict) and link.get("metric_id") == "P1":
                link["role"] = "prerequisite"
    path = tmp_path / "p1-not-outcome.yaml"
    _write(path, contract)

    result = validate_pipeline_measurement_coverage(path)

    assert result["status"] == "BLOCKED"
    assert "COVERAGE_PRIMARY_OUTCOME_LINKS_MISSING" in result[
        "blocking_reasons"
    ]
