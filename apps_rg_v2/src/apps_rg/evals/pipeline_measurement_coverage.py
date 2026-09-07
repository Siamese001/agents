"""Validate that Apps RG measures every declared runtime element intentionally."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


COVERAGE_VERSION = "apps_rg.pipeline_measurement_coverage.v1"
SUMMARY_VERSION = "apps_rg.pipeline_measurement_coverage_summary.v1"
DEFAULT_CONTRACT_PATH = (
    Path(__file__).with_name("contracts") / "pipeline_measurement_coverage.v1.yaml"
)
REPO_ROOT = Path(__file__).resolve().parents[3]
LANE_CONTRACT_RELATIVE_PATH = "src/apps_eval/registries/apps_rg_lane_contract.json"
STAGE_CONTRACT_RELATIVE_PATH = (
    "src/apps_eval/registries/apps_rg_stage_microstep_contract.json"
)
SUCCESS_CONTRACT_RELATIVE_PATH = (
    "src/apps_rg/evals/contracts/success_metric_contract.v1.yaml"
)
SOURCE_CONTRACT_PATHS = {
    "lane_contract": LANE_CONTRACT_RELATIVE_PATH,
    "stage_microstep_contract": STAGE_CONTRACT_RELATIVE_PATH,
    "success_metric_contract": SUCCESS_CONTRACT_RELATIVE_PATH,
}
PRIMARY_OUTCOMES = ("P1", "P2")
DIAGNOSTIC_GATES = ("G1", "G2", "G3", "G4", "G5", "G6")
GUARDRAILS = (
    "unsupported_material_claim_count",
    "critical_binding_error_count",
    "critical_run_divergence_count",
)
REGRESSION_METRIC = "apps_eval_regression"
METRIC_IDS = {
    *PRIMARY_OUTCOMES,
    *DIAGNOSTIC_GATES,
    *GUARDRAILS,
    REGRESSION_METRIC,
}
AUTHORITY_TIERS = {
    "technical_validation",
    "human_qualified",
    "release_authorized",
    "production_authorized",
    "regression_diagnostic",
}
SCOPES = {"prerequisite", "global", "lane", "cross_run"}


def canonical_digest(value: Any) -> str:
    """Return a stable digest for a data structure."""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a YAML mapping")
    return value


def _source_path(relative_path: str) -> Path:
    return REPO_ROOT / relative_path


def _runtime_contracts() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        _load_json(_source_path(LANE_CONTRACT_RELATIVE_PATH)),
        _load_json(_source_path(STAGE_CONTRACT_RELATIVE_PATH)),
    )


def runtime_lanes() -> tuple[str, ...]:
    lane_contract, _ = _runtime_contracts()
    lanes = lane_contract.get("generated_lanes")
    if (
        not isinstance(lanes, list)
        or not lanes
        or any(not isinstance(lane, str) or not lane for lane in lanes)
    ):
        raise ValueError("runtime lane contract has no valid generated lanes")
    return tuple(lanes)


def _stage_roles(
    records: Any, *, required_only: bool = False
) -> dict[str, tuple[set[str], bool]]:
    if not isinstance(records, list):
        raise ValueError("stage records must be a list")
    grouped_roles: dict[str, set[str]] = defaultdict(set)
    grouped_required: dict[str, bool] = defaultdict(bool)
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("stage record must be an object")
        stage_id = record.get("stage_id")
        artifact_role = record.get("artifact_role")
        required = record.get("required")
        if not isinstance(stage_id, str) or not stage_id:
            raise ValueError("stage record has invalid stage_id")
        if not isinstance(artifact_role, str) or not artifact_role:
            raise ValueError("stage record has invalid artifact_role")
        if not isinstance(required, bool):
            raise ValueError("stage record has invalid required value")
        if not required_only or required:
            grouped_roles[stage_id].add(artifact_role)
        grouped_required[stage_id] = grouped_required[stage_id] or required
    return {
        stage_id: (roles, grouped_required[stage_id])
        for stage_id, roles in grouped_roles.items()
    }


def expected_pipeline_elements() -> dict[tuple[str, str], tuple[set[str], bool]]:
    """Derive all expected measurement elements from the live runtime contracts."""

    lane_contract, stage_contract = _runtime_contracts()
    expected: dict[tuple[str, str], tuple[set[str], bool]] = {
        (
            "prerequisite",
            "apps_research",
        ): ({"apps_research_handoff_validation_receipt"}, True)
    }
    for stage_id, data in _stage_roles(stage_contract.get("global_microsteps")).items():
        expected[("global", stage_id)] = data
    lane_roles = lane_contract.get("required_lane_artifact_roles")
    if not isinstance(lane_roles, Mapping):
        raise ValueError("lane contract has no required lane artifact roles")
    for stage_id, roles in lane_roles.items():
        if (
            not isinstance(stage_id, str)
            or not isinstance(roles, list)
            or not roles
            or any(not isinstance(role, str) or not role for role in roles)
        ):
            raise ValueError("lane contract contains an invalid stage role")
        expected[("lane", stage_id)] = (set(roles), True)
    for stage_id, data in _stage_roles(
        stage_contract.get("cross_run_microsteps")
    ).items():
        expected[("cross_run", stage_id)] = data
    return expected


def _is_string_list(value: Any, *, nonempty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) if nonempty else True)
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def _metric_link_errors(link: Any) -> list[str]:
    if not isinstance(link, Mapping):
        return ["MEASUREMENT_LINK_NOT_OBJECT"]
    metric_id = link.get("metric_id")
    role = link.get("role")
    authority = link.get("authority_required")
    errors: list[str] = []
    if metric_id not in METRIC_IDS:
        errors.append("MEASUREMENT_LINK_METRIC_INVALID")
    if authority not in AUTHORITY_TIERS:
        errors.append("MEASUREMENT_LINK_AUTHORITY_INVALID")
    if metric_id in PRIMARY_OUTCOMES:
        if role not in {"outcome", "prerequisite"}:
            errors.append("PRIMARY_OUTCOME_LINK_ROLE_INVALID")
        if authority != "human_qualified":
            errors.append("PRIMARY_OUTCOME_AUTHORITY_INVALID")
    elif metric_id in DIAGNOSTIC_GATES:
        if role != "diagnostic":
            errors.append("DIAGNOSTIC_LINK_ROLE_INVALID")
        if authority == "regression_diagnostic":
            errors.append("DIAGNOSTIC_AUTHORITY_INVALID")
    elif metric_id in GUARDRAILS:
        if role != "guardrail":
            errors.append("GUARDRAIL_LINK_ROLE_INVALID")
        if authority == "regression_diagnostic":
            errors.append("GUARDRAIL_AUTHORITY_INVALID")
    elif metric_id == REGRESSION_METRIC:
        if role != "regression" or authority != "regression_diagnostic":
            errors.append("REGRESSION_LINK_AUTHORITY_INVALID")
    return errors


def _contract_errors(contract: Any) -> list[str]:
    if not isinstance(contract, Mapping):
        return ["COVERAGE_CONTRACT_NOT_OBJECT"]
    errors: list[str] = []
    if contract.get("schema_version") != COVERAGE_VERSION:
        errors.append("COVERAGE_CONTRACT_SCHEMA_INVALID")
    if not isinstance(contract.get("title"), str) or not contract["title"].strip():
        errors.append("COVERAGE_CONTRACT_TITLE_INVALID")
    if contract.get("source_contracts") != SOURCE_CONTRACT_PATHS:
        errors.append("COVERAGE_SOURCE_CONTRACT_BINDINGS_INVALID")
    coverage = contract.get("coverage")
    if not isinstance(coverage, list) or not coverage:
        return [*errors, "COVERAGE_ROWS_INVALID"]
    try:
        expected = expected_pipeline_elements()
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return [*errors, "COVERAGE_RUNTIME_CONTRACT_UNREADABLE"]
    seen_ids: set[str] = set()
    seen_elements: set[tuple[str, str]] = set()
    linked_metrics: set[str] = set()
    direct_outcomes: set[str] = set()
    for row in coverage:
        if not isinstance(row, Mapping):
            errors.append("COVERAGE_ROW_NOT_OBJECT")
            continue
        element_id = row.get("element_id")
        scope = row.get("scope")
        stage_id = row.get("stage_id")
        if not isinstance(element_id, str) or not element_id:
            errors.append("COVERAGE_ROW_ID_INVALID")
        elif element_id in seen_ids:
            errors.append("COVERAGE_ROW_ID_DUPLICATE")
        else:
            seen_ids.add(element_id)
        if scope not in SCOPES or not isinstance(stage_id, str) or not stage_id:
            errors.append("COVERAGE_ROW_STAGE_INVALID")
            continue
        key = (scope, stage_id)
        if key not in expected:
            errors.append("COVERAGE_ROW_STAGE_NOT_IN_RUNTIME_CONTRACT")
            continue
        if key in seen_elements:
            errors.append("COVERAGE_ROW_STAGE_DUPLICATE")
        seen_elements.add(key)
        expected_roles, expected_required = expected[key]
        artifact_roles = row.get("artifact_roles")
        if not _is_string_list(artifact_roles):
            errors.append("COVERAGE_ROW_ARTIFACT_ROLES_INVALID")
        elif set(artifact_roles) != expected_roles:
            errors.append("COVERAGE_ROW_ARTIFACT_ROLES_INCOMPLETE")
        if row.get("required") is not expected_required:
            errors.append("COVERAGE_ROW_REQUIRED_STATE_INVALID")
        if not _is_string_list(row.get("slice_keys")):
            errors.append("COVERAGE_ROW_SLICE_KEYS_INVALID")
        if not _is_string_list(row.get("recertification_triggers")):
            errors.append("COVERAGE_ROW_RECERTIFICATION_TRIGGERS_INVALID")
        links = row.get("metric_links")
        if not isinstance(links, list) or not links:
            errors.append("COVERAGE_ROW_METRIC_LINKS_INVALID")
            continue
        row_links: set[tuple[str, str]] = set()
        for link in links:
            errors.extend(_metric_link_errors(link))
            if isinstance(link, Mapping):
                metric_id = link.get("metric_id")
                role = link.get("role")
                if isinstance(metric_id, str):
                    linked_metrics.add(metric_id)
                    if role == "outcome" and metric_id in PRIMARY_OUTCOMES:
                        direct_outcomes.add(metric_id)
                pair = (str(metric_id), str(role))
                if pair in row_links:
                    errors.append("COVERAGE_ROW_METRIC_LINK_DUPLICATE")
                row_links.add(pair)
    missing_elements = sorted(set(expected) - seen_elements)
    if missing_elements:
        errors.append("COVERAGE_RUNTIME_ELEMENTS_MISSING")
    missing_metrics = sorted(METRIC_IDS - linked_metrics)
    if missing_metrics:
        errors.append("COVERAGE_METRIC_LINKS_MISSING")
    if set(PRIMARY_OUTCOMES) != direct_outcomes:
        errors.append("COVERAGE_PRIMARY_OUTCOME_LINKS_MISSING")
    return sorted(set(errors))


def load_pipeline_measurement_coverage(
    path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    """Load the versioned coverage contract without writing runtime state."""

    contract = _load_yaml(path)
    errors = _contract_errors(contract)
    if errors:
        raise ValueError(";".join(errors))
    return contract


def source_contract_digests() -> dict[str, str]:
    return {
        name: file_sha256(_source_path(relative_path))
        for name, relative_path in SOURCE_CONTRACT_PATHS.items()
    }


def validate_pipeline_measurement_coverage(
    path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    """Fail closed when a declared pipeline element lacks a valid measurement map."""

    try:
        contract = _load_yaml(path)
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        contract = {}
        errors = ["COVERAGE_CONTRACT_UNREADABLE"]
    else:
        errors = _contract_errors(contract)
    try:
        lanes = runtime_lanes()
        expected = expected_pipeline_elements()
        digests = source_contract_digests()
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        lanes = ()
        expected = {}
        digests = {}
        errors = [*errors, "COVERAGE_RUNTIME_CONTRACT_UNREADABLE"]
    status = "BLOCKED" if errors else "PASS"
    result: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "status": status,
        "coverage_contract_digest": canonical_digest(contract),
        "source_contract_digests": digests,
        "runtime_lanes": list(lanes),
        "expected_element_count": len(expected),
        "declared_element_count": len(contract.get("coverage", []))
        if isinstance(contract.get("coverage"), list)
        else 0,
        "authority": {
            "technical_validation": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
        },
        "blocking_reasons": sorted(set(errors)),
    }
    result["record_digest"] = canonical_digest(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Apps RG pipeline measurement coverage"
    )
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    args = parser.parse_args(argv)
    result = validate_pipeline_measurement_coverage(args.contract)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2
