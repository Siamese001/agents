"""W5 evaluator-card registry and human-criterion validity gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any, Mapping, Sequence


REGISTRY_VERSION = "apps_rg.evaluator_validity_registry.v1"
SUMMARY_VERSION = "apps_rg.evaluator_validity_registry_summary.v1"
DEFAULT_REGISTRY_PATH = Path(__file__).with_name("evaluator_validity_registry.v1.json")
REQUIRED_GRADERS = (
    "G1_RETRIEVAL", "G2_BINDING", "G3_GROUNDING", "G4_SECTION_QUALITY",
    "G4_WHOLE_RESUME", "G5_REPEATABILITY", "ATS_DOCUMENT", "APPS_RESEARCH_U0",
    "PRIVACY", "FAIRNESS", "OPERATIONAL", "EXECUTIVE_POSITIONING_JUDGE",
    "MATERIAL_CLAIM_RECONCILIATION", "BENCHMARK_COHORT_DESIGN",
    "PIPELINE_MEASUREMENT_COVERAGE", "P1_BLIND_REVIEW_LEDGER",
    "P2_PIPELINE_ATTEMPT_LEDGER",
)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def wilson_upper_bound(*, errors: int, observations: int, confidence_level: float) -> float:
    if observations <= 0 or errors < 0 or errors > observations or not 0 < confidence_level < 1:
        raise ValueError("invalid Wilson interval inputs")
    z = NormalDist().inv_cdf((1 + confidence_level) / 2)
    proportion = errors / observations
    denominator = 1 + z * z / observations
    center = proportion + z * z / (2 * observations)
    radius = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * observations)) / observations)
    return (center + radius) / denominator


def _load_registry(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("evaluator registry must be a JSON object")
    return value


def _card_result(card: Any) -> tuple[dict[str, Any], set[str], set[str], set[str]]:
    blocking: set[str] = set()
    failures: set[str] = set()
    not_measured: set[str] = set()
    if not isinstance(card, Mapping):
        return {"grader_id": "", "status": "BLOCKED"}, {"EVALUATOR_CARD_INVALID"}, failures, not_measured
    grader_id = str(card.get("grader_id") or "")
    result: dict[str, Any] = {"grader_id": grader_id, "status": "NOT_MEASURED", "metrics": {}}
    if not grader_id or not str(card.get("version") or "") or not str(card.get("scope") or ""):
        blocking.add("EVALUATOR_CARD_IDENTITY_INVALID")
    if not isinstance(card.get("slices"), list) or not card["slices"]:
        blocking.add("EVALUATOR_CARD_SLICES_INVALID")
    mutation = card.get("mutation_suite")
    pilot = card.get("human_pilot")
    thresholds = card.get("thresholds")
    if not isinstance(mutation, Mapping) or not isinstance(pilot, Mapping) or not isinstance(thresholds, Mapping):
        blocking.add("EVALUATOR_CARD_FIELDS_INVALID")
        result["status"] = "BLOCKED"
        return result, blocking, failures, not_measured
    if pilot.get("synthetic_human_labels_created") is not False:
        blocking.add("EVALUATOR_SYNTHETIC_HUMAN_LABELS_FORBIDDEN")
    status = card.get("validation_status")
    if status == "NOT_MEASURED":
        not_measured.add(f"EVALUATOR_NOT_VALIDATED_{grader_id}")
    elif status != "VALIDATED":
        blocking.add("EVALUATOR_VALIDATION_STATUS_INVALID")
    else:
        if mutation.get("status") != "COMPLETE" or not str(mutation.get("version") or ""):
            not_measured.add(f"EVALUATOR_MUTATION_SUITE_INCOMPLETE_{grader_id}")
        if pilot.get("status") != "COMPLETE" or not str(pilot.get("receipt_digest") or ""):
            not_measured.add(f"EVALUATOR_HUMAN_PILOT_INCOMPLETE_{grader_id}")
        sample_count = pilot.get("sample_count")
        false_passes = pilot.get("false_pass_count")
        false_fails = pilot.get("false_fail_count")
        confidence = thresholds.get("confidence_level")
        false_pass_max = thresholds.get("critical_false_pass_upper_bound_max")
        false_fail_max = thresholds.get("false_fail_upper_bound_max")
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (confidence, false_pass_max, false_fail_max)):
            not_measured.add(f"EVALUATOR_THRESHOLDS_NOT_PREREGISTERED_{grader_id}")
        elif not isinstance(sample_count, int) or not isinstance(false_passes, int) or not isinstance(false_fails, int):
            blocking.add("EVALUATOR_PILOT_COUNTS_INVALID")
        else:
            try:
                false_pass_upper = wilson_upper_bound(errors=false_passes, observations=sample_count, confidence_level=float(confidence))
                false_fail_upper = wilson_upper_bound(errors=false_fails, observations=sample_count, confidence_level=float(confidence))
            except ValueError:
                blocking.add("EVALUATOR_PILOT_COUNTS_INVALID")
            else:
                result["metrics"] = {"critical_false_pass_upper_bound": false_pass_upper, "false_fail_upper_bound": false_fail_upper}
                if false_pass_upper > float(false_pass_max):
                    failures.add(f"EVALUATOR_FALSE_PASS_BOUND_FAILED_{grader_id}")
                if false_fail_upper > float(false_fail_max):
                    failures.add(f"EVALUATOR_FALSE_FAIL_BOUND_FAILED_{grader_id}")
    result["status"] = "BLOCKED" if blocking else "FAIL" if failures else "NOT_MEASURED" if not_measured else "PASS"
    return result, blocking, failures, not_measured


def validate_evaluator_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    try:
        registry = _load_registry(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        registry = {}
        blocking = {"EVALUATOR_REGISTRY_UNREADABLE"}
    else:
        blocking: set[str] = set()
    failures: set[str] = set()
    not_measured: set[str] = set()
    if registry.get("schema_version") != REGISTRY_VERSION or not str(registry.get("registry_id") or ""):
        blocking.add("EVALUATOR_REGISTRY_SCHEMA_INVALID")
    cards = registry.get("cards") if isinstance(registry.get("cards"), list) else []
    card_ids = [str(card.get("grader_id") or "") for card in cards if isinstance(card, Mapping)]
    if tuple(card_ids) != REQUIRED_GRADERS or len(set(card_ids)) != len(REQUIRED_GRADERS):
        blocking.add("EVALUATOR_REGISTRY_COVERAGE_INVALID")
    results: list[dict[str, Any]] = []
    for card in cards:
        result, card_blocking, card_failures, card_not_measured = _card_result(card)
        results.append(result)
        blocking.update(card_blocking)
        failures.update(card_failures)
        not_measured.update(card_not_measured)
    status = "BLOCKED" if blocking else "FAIL" if failures else "NOT_MEASURED" if not_measured else "PASS"
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "registry_id": str(registry.get("registry_id") or path.stem),
        "status": status,
        "grader_results": results,
        "authority": {"human_qualified": False, "release_authorizing": False, "production_authorizing": False},
        "blocking_reasons": sorted(blocking),
        "failure_reasons": sorted(failures),
        "not_measured_reasons": sorted(not_measured),
    }
    summary["record_digest"] = canonical_digest(summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apps RG W5 evaluator cards")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    args = parser.parse_args(argv)
    summary = validate_evaluator_registry(args.registry)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 2
