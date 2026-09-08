"""W2 benchmark-manifest validation without exposing protected holdout cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any, Mapping, Sequence


MANIFEST_VERSION = "apps_rg.benchmark_case_manifest.v1"
SUMMARY_VERSION = "apps_rg.benchmark_design_summary.v1"
APPS_RESEARCH_RECEIPT_VERSION = "apps_rg.apps_research_handoff_validation_receipt.v2"
REPO_ROOT = Path(__file__).resolve().parents[3]
LANE_CONTRACT_PATH = REPO_ROOT / "src/apps_eval/registries/apps_rg_lane_contract.json"
DEFAULT_MANIFEST_PATH = Path(__file__).with_name("benchmark_case_manifest.v1.json")
SLICE_DIMENSIONS = (
    "role_family",
    "target_profile",
    "evidence_density",
    "hard_negative",
    "binding_challenge",
    "protected_risk_slice",
)
CASE_IDENTITY_DIGEST_FIELDS = (
    "source_bundle_digest",
    "source_family_digest",
    "profile_digest",
    "job_description_digest",
    "target_request_digest",
    "research_handoff_digest",
    "baseline_output_digest",
    "expected_output_digest",
    "prompt_configuration_digest",
    "runtime_configuration_digest",
)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def runtime_lanes() -> tuple[str, ...]:
    value = json.loads(LANE_CONTRACT_PATH.read_text(encoding="utf-8"))
    lanes = value.get("generated_lanes") if isinstance(value, Mapping) else None
    if not isinstance(lanes, list) or not lanes or any(
        not isinstance(lane, str) or not lane for lane in lanes
    ):
        raise ValueError("runtime lane contract is invalid")
    return tuple(lanes)


def required_pairs(
    *,
    alpha: float,
    power: float,
    minimum_detectable_effect: float,
    baseline_variance: float,
) -> int:
    """Conservative normal-approximation planning count for paired outcomes."""
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("alpha and power must be within (0, 1)")
    if minimum_detectable_effect <= 0 or baseline_variance <= 0:
        raise ValueError("effect and variance must be positive")
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha / 2)
    z_power = normal.inv_cdf(power)
    return math.ceil(((z_alpha + z_power) ** 2 * 2 * baseline_variance) / (minimum_detectable_effect**2))


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("benchmark manifest must be a JSON object")
    return value


def _manifest_errors(manifest: Any) -> list[str]:
    if not isinstance(manifest, Mapping):
        return ["BENCHMARK_MANIFEST_NOT_OBJECT"]
    errors: list[str] = []
    if manifest.get("schema_version") != MANIFEST_VERSION:
        errors.append("BENCHMARK_MANIFEST_SCHEMA_INVALID")
    if not isinstance(manifest.get("benchmark_id"), str) or not manifest["benchmark_id"]:
        errors.append("BENCHMARK_ID_INVALID")
    for field in ("minimum_cases_per_lane", "minimum_cases_per_required_slice"):
        if not isinstance(manifest.get(field), int) or manifest[field] < 1:
            errors.append(f"BENCHMARK_{field.upper()}_INVALID")
    if not isinstance(manifest.get("slice_policy"), Mapping):
        errors.append("BENCHMARK_SLICE_POLICY_INVALID")
    if not isinstance(manifest.get("power_plan"), Mapping):
        errors.append("BENCHMARK_POWER_PLAN_INVALID")
    if not isinstance(manifest.get("calibration_cases"), list):
        errors.append("BENCHMARK_CALIBRATION_CASES_INVALID")
    if not isinstance(manifest.get("holdout_commitment"), Mapping):
        errors.append("BENCHMARK_HOLDOUT_COMMITMENT_INVALID")
    return errors


def _case_errors(case: Any, lanes: set[str]) -> list[str]:
    if not isinstance(case, Mapping):
        return ["BENCHMARK_CASE_NOT_OBJECT"]
    required_fields = (
        "case_id",
        *CASE_IDENTITY_DIGEST_FIELDS,
        "role_family",
        "employer",
        "target_profile",
    )
    errors = [
        f"BENCHMARK_CASE_{field.upper()}_MISSING"
        for field in required_fields
        if not str(case.get(field) or "").strip()
    ]
    for field in CASE_IDENTITY_DIGEST_FIELDS:
        digest = case.get(field)
        if not isinstance(digest, str) or not digest.startswith("sha256:") or len(
            digest
        ) != 71 or any(character not in "0123456789abcdef" for character in digest[7:]):
            errors.append(f"BENCHMARK_CASE_{field.upper()}_INVALID")
    case_lanes = case.get("lanes")
    if not isinstance(case_lanes, list) or not case_lanes:
        errors.append("BENCHMARK_CASE_LANES_INVALID")
    elif len(case_lanes) != len(set(case_lanes)) or not set(case_lanes).issubset(lanes):
        errors.append("BENCHMARK_CASE_LANES_INVALID")
    if case.get("evidence_density") not in {"sparse", "rich"}:
        errors.append("BENCHMARK_CASE_EVIDENCE_DENSITY_INVALID")
    if not isinstance(case.get("hard_negative"), bool):
        errors.append("BENCHMARK_CASE_HARD_NEGATIVE_INVALID")
    if not isinstance(case.get("binding_challenges"), list) or not set(
        case.get("binding_challenges") or []
    ).issubset({"date", "number"}):
        errors.append("BENCHMARK_CASE_BINDING_CHALLENGES_INVALID")
    if not isinstance(case.get("protected_risk_slices"), list) or not set(
        case.get("protected_risk_slices") or []
    ).issubset({"privacy", "counterfactual"}):
        errors.append("BENCHMARK_CASE_PROTECTED_RISK_SLICES_INVALID")
    research = case.get("apps_research_u0")
    if not isinstance(research, Mapping):
        errors.append("BENCHMARK_CASE_APPS_RESEARCH_U0_MISSING")
    elif (
        _research_status(research) == "PASS"
        and research.get("receipt_digest") != case.get("research_handoff_digest")
    ):
        errors.append("BENCHMARK_CASE_RESEARCH_HANDOFF_DIGEST_MISMATCH")
    return errors


def _research_status(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "UNKNOWN"
    if value.get("schema_version") != APPS_RESEARCH_RECEIPT_VERSION:
        return "UNKNOWN"
    if value.get("observed") is not True:
        return "UNKNOWN"
    if value.get("valid") is True and value.get("status") == "PASS":
        return "PASS"
    return "FAIL"


def validate_benchmark_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    """Evaluate W2 readiness; this never loads protected holdout case identities."""
    try:
        manifest = _load_manifest(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        manifest = {}
        errors = ["BENCHMARK_MANIFEST_UNREADABLE"]
    else:
        errors = _manifest_errors(manifest)
    try:
        lanes = runtime_lanes()
    except (OSError, ValueError, json.JSONDecodeError):
        lanes = ()
        errors.append("RUNTIME_LANE_CONTRACT_UNREADABLE")
    cases = manifest.get("calibration_cases") if isinstance(manifest.get("calibration_cases"), list) else []
    lane_counts = {lane: 0 for lane in lanes}
    slice_counts: dict[str, dict[str, int]] = {dimension: {} for dimension in SLICE_DIMENSIONS}
    source_digests: set[str] = set()
    source_family_digests: set[str] = set()
    profile_digests: set[str] = set()
    job_description_digests: set[str] = set()
    request_digests: set[str] = set()
    research_digests: set[str] = set()
    baseline_output_digests: set[str] = set()
    output_digests: set[str] = set()
    case_ids: set[str] = set()
    not_measured: set[str] = set()
    for case in cases:
        errors.extend(_case_errors(case, set(lanes)))
        if not isinstance(case, Mapping):
            continue
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in case_ids:
            errors.append("BENCHMARK_CASE_ID_DUPLICATE_OR_INVALID")
        case_ids.add(case_id)
        for field, observed, error in (
            ("source_bundle_digest", source_digests, "BENCHMARK_SOURCE_BUNDLE_DUPLICATE"),
            ("source_family_digest", source_family_digests, "BENCHMARK_SOURCE_FAMILY_DUPLICATE"),
            ("profile_digest", profile_digests, "BENCHMARK_PROFILE_DUPLICATE"),
            (
                "job_description_digest",
                job_description_digests,
                "BENCHMARK_JOB_DESCRIPTION_DUPLICATE",
            ),
            ("target_request_digest", request_digests, "BENCHMARK_TARGET_REQUEST_DUPLICATE"),
            (
                "research_handoff_digest",
                research_digests,
                "BENCHMARK_RESEARCH_HANDOFF_DUPLICATE",
            ),
            (
                "baseline_output_digest",
                baseline_output_digests,
                "BENCHMARK_BASELINE_OUTPUT_DUPLICATE",
            ),
            ("expected_output_digest", output_digests, "BENCHMARK_EXPECTED_OUTPUT_DUPLICATE"),
        ):
            digest = str(case.get(field) or "")
            if digest in observed:
                errors.append(error)
            observed.add(digest)
        for lane in case.get("lanes") or []:
            if lane in lane_counts:
                lane_counts[lane] += 1
        observed_slices = {
            "role_family": [case.get("role_family")],
            "target_profile": [case.get("target_profile")],
            "evidence_density": [case.get("evidence_density")],
            "hard_negative": [case.get("hard_negative")],
            "binding_challenge": case.get("binding_challenges") or [],
            "protected_risk_slice": case.get("protected_risk_slices") or [],
        }
        for dimension, values in observed_slices.items():
            for value in values:
                key = str(value).lower() if isinstance(value, bool) else str(value)
                slice_counts[dimension][key] = slice_counts[dimension].get(key, 0) + 1
        research_status = _research_status(case.get("apps_research_u0"))
        if research_status == "UNKNOWN":
            not_measured.add("APPS_RESEARCH_TO_U0_EVIDENCE_MISSING")
        elif research_status == "FAIL":
            errors.append("APPS_RESEARCH_TO_U0_VALIDATION_FAILED")
    minimum_per_lane = manifest.get("minimum_cases_per_lane") if isinstance(manifest.get("minimum_cases_per_lane"), int) else 1
    for lane, count in lane_counts.items():
        if count < minimum_per_lane:
            not_measured.add(f"LANE_COVERAGE_INSUFFICIENT_{lane}")
    policy = manifest.get("slice_policy") if isinstance(manifest.get("slice_policy"), Mapping) else {}
    minimum_per_slice = manifest.get("minimum_cases_per_required_slice") if isinstance(manifest.get("minimum_cases_per_required_slice"), int) else 1
    for dimension in SLICE_DIMENSIONS:
        values = policy.get(dimension) if isinstance(policy.get(dimension), list) else []
        if not values:
            errors.append(f"SLICE_POLICY_{dimension.upper()}_INVALID")
        for value in values:
            key = str(value).lower() if isinstance(value, bool) else str(value)
            if slice_counts[dimension].get(key, 0) < minimum_per_slice:
                not_measured.add(f"SLICE_COVERAGE_INSUFFICIENT_{dimension}_{key}")
    holdout = manifest.get("holdout_commitment") if isinstance(manifest.get("holdout_commitment"), Mapping) else {}
    if set(holdout) - {"status", "external_authority_ref", "sealed_index_digest", "case_count", "development_access"}:
        errors.append("HOLDOUT_IDENTITIES_EXPOSED_TO_DEVELOPMENT")
    if holdout.get("development_access") != "external_authority_only":
        errors.append("HOLDOUT_DEVELOPMENT_ACCESS_INVALID")
    if holdout.get("status") != "SEALED" or not str(holdout.get("external_authority_ref") or "") or not str(holdout.get("sealed_index_digest") or ""):
        not_measured.add("HOLDOUT_COMMITMENT_NOT_SEALED")
    elif not isinstance(holdout.get("case_count"), int) or holdout["case_count"] < minimum_per_lane * len(lanes):
        not_measured.add("HOLDOUT_CASE_COUNT_INSUFFICIENT")
    power_plan = manifest.get("power_plan") if isinstance(manifest.get("power_plan"), Mapping) else {}
    try:
        recommended_pairs = required_pairs(
            alpha=float(power_plan["alpha"]),
            power=float(power_plan["power"]),
            minimum_detectable_effect=float(power_plan["minimum_detectable_effect"]),
            baseline_variance=float(power_plan["baseline_variance"]),
        )
    except (KeyError, TypeError, ValueError):
        recommended_pairs = None
        not_measured.add("POWER_PLAN_NOT_PREREGISTERED")
    else:
        declared_pairs = power_plan.get("minimum_pairs")
        if not isinstance(declared_pairs, int):
            not_measured.add("POWER_PLAN_MINIMUM_PAIRS_MISSING")
        elif declared_pairs < recommended_pairs:
            errors.append("POWER_PLAN_UNDERPOWERED")
    status = "BLOCKED" if errors else "NOT_MEASURED" if not_measured else "PASS"
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "benchmark_id": str(manifest.get("benchmark_id") or path.stem),
        "status": status,
        "runtime_lanes": list(lanes),
        "calibration_lane_counts": lane_counts,
        "slice_counts": slice_counts,
        "holdout_access": {
            "development_access": holdout.get("development_access"),
            "case_ids_exposed": "case_ids" in holdout,
            "status": holdout.get("status"),
        },
        "power_plan": {
            "recommended_minimum_pairs": recommended_pairs,
            "declared_minimum_pairs": power_plan.get("minimum_pairs"),
        },
        "authority": {
            "technical_validation": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
        },
        "blocking_reasons": sorted(set(errors)),
        "not_measured_reasons": sorted(not_measured),
    }
    summary["record_digest"] = canonical_digest(summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apps RG W2 benchmark design")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)
    summary = validate_benchmark_manifest(args.manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 2
