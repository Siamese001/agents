from __future__ import annotations

import json
import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.benchmark_design import (
    MANIFEST_VERSION,
    required_pairs,
    runtime_lanes,
    validate_benchmark_manifest,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "benchmark_case_manifest.v1.schema.json"


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _research_receipt(index: int) -> dict[str, object]:
    return {
        "schema_version": "apps_rg.apps_research_handoff_validation_receipt.v2",
        "observed": True,
        "valid": True,
        "status": "PASS",
        "receipt_digest": _digest(f"research-{index}"),
    }


def _case(index: int, lane: str) -> dict[str, object]:
    return {
        "case_id": f"calibration-{index}",
        "source_bundle_digest": _digest(f"source-{index}"),
        "source_family_digest": _digest(f"source-family-{index}"),
        "profile_digest": _digest(f"profile-{index}"),
        "job_description_digest": _digest(f"job-description-{index}"),
        "target_request_digest": _digest(f"request-{index}"),
        "research_handoff_digest": _digest(f"research-{index}"),
        "baseline_output_digest": _digest(f"baseline-{index}"),
        "expected_output_digest": _digest(f"output-{index}"),
        "prompt_configuration_digest": _digest("prompt-config"),
        "runtime_configuration_digest": _digest("runtime-config"),
        "lanes": [lane],
        "role_family": "executive_leadership" if index % 2 else "technical_leadership",
        "employer": f"employer-{index}",
        "target_profile": "strategic_partnerships" if index % 2 else "industrial_ai",
        "evidence_density": "sparse" if index % 2 else "rich",
        "hard_negative": bool(index % 2),
        "binding_challenges": ["date", "number"],
        "protected_risk_slices": ["privacy", "counterfactual"],
        "apps_research_u0": _research_receipt(index),
    }


def _manifest() -> dict[str, object]:
    lanes = runtime_lanes()
    cases = [_case(index, lane) for index, lane in enumerate(lanes * 2, start=1)]
    minimum_pairs = required_pairs(
        alpha=0.05,
        power=0.8,
        minimum_detectable_effect=0.5,
        baseline_variance=0.25,
    )
    return {
        "schema_version": MANIFEST_VERSION,
        "benchmark_id": "w2-fixture",
        "minimum_cases_per_lane": 2,
        "minimum_cases_per_required_slice": 2,
        "slice_policy": {
            "role_family": ["executive_leadership", "technical_leadership"],
            "target_profile": ["strategic_partnerships", "industrial_ai"],
            "evidence_density": ["sparse", "rich"],
            "hard_negative": [True, False],
            "binding_challenge": ["date", "number"],
            "protected_risk_slice": ["privacy", "counterfactual"],
        },
        "power_plan": {
            "method": "paired_normal_approximation",
            "alpha": 0.05,
            "power": 0.8,
            "minimum_detectable_effect": 0.5,
            "baseline_variance": 0.25,
            "minimum_pairs": minimum_pairs,
        },
        "calibration_cases": cases,
        "holdout_commitment": {
            "status": "SEALED",
            "external_authority_ref": "authority://holdout-custodian",
            "sealed_index_digest": "sha256:external-holdout-index",
            "case_count": len(cases),
            "development_access": "external_authority_only",
        },
    }


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def test_schema_is_valid_and_default_manifest_is_explicitly_not_measured() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_manifest())
    summary = validate_benchmark_manifest()

    assert summary["status"] == "NOT_MEASURED"
    assert summary["authority"]["release_authorizing"] is False
    assert "HOLDOUT_COMMITMENT_NOT_SEALED" in summary["not_measured_reasons"]
    assert "POWER_PLAN_MINIMUM_PAIRS_MISSING" in summary["not_measured_reasons"]


def test_complete_case_manifest_covers_runtime_lanes_slices_and_apps_research_u0(
    tmp_path: Path,
) -> None:
    path = tmp_path / "benchmark.json"
    _write_manifest(path, _manifest())

    summary = validate_benchmark_manifest(path)

    assert summary["status"] == "PASS"
    assert set(summary["runtime_lanes"]) == set(runtime_lanes())
    assert set(summary["calibration_lane_counts"].values()) == {2}
    assert summary["holdout_access"] == {
        "development_access": "external_authority_only",
        "case_ids_exposed": False,
        "status": "SEALED",
    }
    assert summary["authority"] == {
        "technical_validation": True,
        "human_qualified": False,
        "release_authorizing": False,
        "production_authorizing": False,
    }


def test_duplicate_requests_and_exposed_holdout_identities_fail_closed(tmp_path: Path) -> None:
    duplicate = _manifest()
    duplicate_cases = duplicate["calibration_cases"]
    assert isinstance(duplicate_cases, list)
    duplicate_cases[1]["target_request_digest"] = duplicate_cases[0]["target_request_digest"]
    duplicate_path = tmp_path / "duplicate.json"
    _write_manifest(duplicate_path, duplicate)
    duplicate_summary = validate_benchmark_manifest(duplicate_path)
    assert duplicate_summary["status"] == "BLOCKED"
    assert "BENCHMARK_TARGET_REQUEST_DUPLICATE" in duplicate_summary["blocking_reasons"]

    exposed = _manifest()
    holdout = exposed["holdout_commitment"]
    assert isinstance(holdout, dict)
    holdout["case_ids"] = ["holdout-1"]
    exposed_path = tmp_path / "exposed.json"
    _write_manifest(exposed_path, exposed)
    exposed_summary = validate_benchmark_manifest(exposed_path)
    assert exposed_summary["status"] == "BLOCKED"
    assert "HOLDOUT_IDENTITIES_EXPOSED_TO_DEVELOPMENT" in exposed_summary[
        "blocking_reasons"
    ]


def test_source_profile_job_and_research_identities_are_complete_and_distinct(
    tmp_path: Path,
) -> None:
    duplicate = _manifest()
    cases = duplicate["calibration_cases"]
    assert isinstance(cases, list)
    cases[1]["profile_digest"] = cases[0]["profile_digest"]
    cases[2]["research_handoff_digest"] = _digest("different-research")
    path = tmp_path / "identity-errors.json"
    _write_manifest(path, duplicate)

    result = validate_benchmark_manifest(path)

    assert result["status"] == "BLOCKED"
    assert "BENCHMARK_PROFILE_DUPLICATE" in result["blocking_reasons"]
    assert "BENCHMARK_CASE_RESEARCH_HANDOFF_DIGEST_MISMATCH" in result[
        "blocking_reasons"
    ]


def test_missing_apps_research_u0_or_underpowered_plan_never_passes(tmp_path: Path) -> None:
    missing_research = _manifest()
    cases = missing_research["calibration_cases"]
    assert isinstance(cases, list)
    cases[0]["apps_research_u0"] = {}
    missing_path = tmp_path / "missing-research.json"
    _write_manifest(missing_path, missing_research)
    missing_summary = validate_benchmark_manifest(missing_path)
    assert missing_summary["status"] == "NOT_MEASURED"
    assert "APPS_RESEARCH_TO_U0_EVIDENCE_MISSING" in missing_summary[
        "not_measured_reasons"
    ]

    underpowered = _manifest()
    power_plan = underpowered["power_plan"]
    assert isinstance(power_plan, dict)
    power_plan["minimum_pairs"] = 1
    underpowered_path = tmp_path / "underpowered.json"
    _write_manifest(underpowered_path, underpowered)
    underpowered_summary = validate_benchmark_manifest(underpowered_path)
    assert underpowered_summary["status"] == "BLOCKED"
    assert "POWER_PLAN_UNDERPOWERED" in underpowered_summary["blocking_reasons"]
