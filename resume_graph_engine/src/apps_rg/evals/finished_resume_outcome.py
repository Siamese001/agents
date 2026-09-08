"""W4 P1 finished-resume outcome contract and fail-closed validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.evals.whole_resume.p1_blind_utility import (
    file_sha256 as review_ledger_file_sha256,
    validate_p1_blind_review_ledger,
)


OUTCOME_VERSION = "apps_rg.finished_resume_outcome.v1"
SUMMARY_VERSION = "apps_rg.finished_resume_outcome_summary.v1"
DEFAULT_OUTCOME_PATH = Path(__file__).with_name("finished_resume_outcome.v1.json")
REPO_ROOT = Path(__file__).resolve().parents[3]
LANE_CONTRACT_PATH = REPO_ROOT / "src/apps_eval/registries/apps_rg_lane_contract.json"
GUARDRAIL_DIMENSIONS = (
    "authenticity",
    "grounding",
    "ats",
    "readability",
    "concision",
    "target_relevance",
)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def runtime_lanes() -> tuple[str, ...]:
    contract = json.loads(LANE_CONTRACT_PATH.read_text(encoding="utf-8"))
    lanes = contract.get("generated_lanes") if isinstance(contract, Mapping) else None
    if not isinstance(lanes, list) or not lanes or any(not isinstance(lane, str) for lane in lanes):
        raise ValueError("runtime lane contract is invalid")
    return tuple(lanes)


def _load_outcome(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("outcome manifest must be a JSON object")
    return value


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len("sha256:") + 64
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _review_ledger_errors(
    evidence: Mapping[str, Any], *, outcome_path: Path
) -> tuple[list[str], dict[str, Any]]:
    reference = evidence.get("blind_review_ledger_path")
    expected_file_digest = evidence.get("blind_review_ledger_file_sha256")
    if not isinstance(reference, str) or not reference or not _valid_digest(
        expected_file_digest
    ):
        return ["P1_BLIND_REVIEW_LEDGER_REFERENCE_REQUIRED"], {}
    relative_path = Path(reference)
    if relative_path.is_absolute():
        return ["P1_BLIND_REVIEW_LEDGER_PATH_INVALID"], {}
    root = outcome_path.parent.resolve()
    ledger_path = (root / relative_path).resolve()
    try:
        ledger_path.relative_to(root)
    except ValueError:
        return ["P1_BLIND_REVIEW_LEDGER_PATH_INVALID"], {}
    if ledger_path.is_symlink():
        return ["P1_BLIND_REVIEW_LEDGER_SYMLINK_FORBIDDEN"], {}
    try:
        actual_file_digest = review_ledger_file_sha256(ledger_path)
    except OSError:
        return ["P1_BLIND_REVIEW_LEDGER_UNREADABLE"], {}
    if actual_file_digest != expected_file_digest:
        return ["P1_BLIND_REVIEW_LEDGER_STALE_OR_TAMPERED"], {}
    ledger = validate_p1_blind_review_ledger(ledger_path)
    if ledger.get("status") != "PASS":
        return ["P1_BLIND_REVIEW_LEDGER_NOT_COMPLETE"], ledger
    errors: list[str] = []
    if evidence.get("completed_review_receipt_digest") != ledger.get("record_digest"):
        errors.append("P1_COMPLETED_REVIEW_RECEIPT_MISMATCH")
    for evidence_field, ledger_field, reason in (
        ("pair_count", "pair_count", "P1_PAIR_DENOMINATOR_LEDGER_MISMATCH"),
        (
            "primary_review_count",
            "primary_review_count",
            "P1_PRIMARY_REVIEW_QUORUM_LEDGER_MISMATCH",
        ),
        (
            "adjudication_count",
            "adjudication_count",
            "P1_ADJUDICATION_QUORUM_LEDGER_MISMATCH",
        ),
        (
            "candidate_preference_count",
            "candidate_preference_count",
            "P1_CANDIDATE_PREFERENCE_LEDGER_MISMATCH",
        ),
        (
            "baseline_preference_count",
            "baseline_preference_count",
            "P1_BASELINE_PREFERENCE_LEDGER_MISMATCH",
        ),
    ):
        if evidence.get(evidence_field) != ledger.get(ledger_field):
            errors.append(reason)
    effect = evidence.get("utility_effect")
    ledger_effect = ledger.get("candidate_preference_margin")
    if (
        isinstance(effect, (int, float))
        and not isinstance(effect, bool)
        and isinstance(ledger_effect, (int, float))
        and not isinstance(ledger_effect, bool)
        and not math.isclose(float(effect), float(ledger_effect), rel_tol=0.0, abs_tol=1e-12)
    ):
        errors.append("P1_UTILITY_EFFECT_LEDGER_MISMATCH")
    if ledger.get("candidate_material_regression_count") not in (0, None):
        errors.append("P1_BLIND_REVIEW_MATERIAL_REGRESSION")
    return errors, ledger


def validate_finished_resume_outcome(
    path: Path = DEFAULT_OUTCOME_PATH,
) -> dict[str, Any]:
    """Validate P1 evidence without elevating a technical check to authority."""
    try:
        outcome = _load_outcome(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        outcome = {}
        blocking = {"P1_OUTCOME_MANIFEST_UNREADABLE"}
    else:
        blocking: set[str] = set()
    not_measured: set[str] = set()
    failures: set[str] = set()
    if outcome.get("schema_version") != OUTCOME_VERSION or outcome.get("outcome_id") != "P1":
        blocking.add("P1_OUTCOME_SCHEMA_INVALID")
    try:
        lanes = runtime_lanes()
    except (OSError, ValueError, json.JSONDecodeError):
        lanes = ()
        blocking.add("P1_RUNTIME_LANE_CONTRACT_UNREADABLE")
    if tuple(outcome.get("required_lanes") or ()) != lanes:
        blocking.add("P1_ALL_RUNTIME_LANES_REQUIRED")
    protocol = outcome.get("review_protocol")
    expected_protocol = {
        "blinded": True,
        "independent_primary_reviewers_per_pair": 2,
        "independent_adjudicators_per_pair": 1,
        "frozen_baseline_required": True,
        "candidate_preference_required": True,
        "utility_superiority_required": True,
    }
    if protocol != expected_protocol:
        blocking.add("P1_BLINDED_REVIEW_PROTOCOL_INVALID")
    margins = outcome.get("noninferiority_margins")
    if not isinstance(margins, Mapping) or set(margins) != set(GUARDRAIL_DIMENSIONS):
        blocking.add("P1_GUARDRAIL_MARGIN_SET_INVALID")
        margins = {}
    elif any(
        value is not None
        and (not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0)
        for value in margins.values()
    ):
        blocking.add("P1_GUARDRAIL_MARGIN_INVALID")
    elif any(value is None for value in margins.values()):
        not_measured.add("P1_NONINFERIORITY_MARGINS_NOT_PREREGISTERED")
    evidence = outcome.get("p1_evidence")
    if not isinstance(evidence, Mapping):
        blocking.add("P1_EVIDENCE_INVALID")
        evidence = {}
    if evidence.get("synthetic_grades_created") is not False:
        blocking.add("P1_SYNTHETIC_GRADES_FORBIDDEN")
    evidence_status = evidence.get("status")
    if evidence_status == "PENDING":
        if any(
            evidence.get(field) not in (0, "", None, {})
            for field in (
                "pair_count",
                "primary_review_count",
                "adjudication_count",
                "external_authority_receipt_sha256",
                "completed_review_receipt_digest",
                "utility_effect",
                "utility_ci_lower",
                "candidate_preference_count",
                "baseline_preference_count",
                "dimension_ci_lowers",
                "blind_review_ledger_path",
                "blind_review_ledger_file_sha256",
            )
        ):
            blocking.add("P1_PENDING_EVIDENCE_MUST_BE_EMPTY")
        not_measured.add("P1_HUMAN_REVIEW_PENDING")
    elif evidence_status != "COMPLETE":
        blocking.add("P1_EVIDENCE_STATUS_INVALID")
    else:
        pair_count = evidence.get("pair_count")
        primary_count = evidence.get("primary_review_count")
        adjudication_count = evidence.get("adjudication_count")
        if not isinstance(pair_count, int) or pair_count < 1:
            blocking.add("P1_PAIR_DENOMINATOR_INVALID")
        if not isinstance(primary_count, int) or primary_count != pair_count * 2:
            blocking.add("P1_PRIMARY_REVIEW_QUORUM_INVALID")
        if not isinstance(adjudication_count, int) or adjudication_count != pair_count:
            blocking.add("P1_ADJUDICATION_QUORUM_INVALID")
        review_ledger_errors, _ = _review_ledger_errors(
            evidence, outcome_path=path
        )
        blocking.update(review_ledger_errors)
        if not _valid_digest(evidence.get("external_authority_receipt_sha256")):
            not_measured.add("P1_EXTERNAL_HUMAN_AUTHORITY_RECEIPT_MISSING")
        effect = evidence.get("utility_effect")
        ci_lower = evidence.get("utility_ci_lower")
        if not isinstance(effect, (int, float)) or isinstance(effect, bool) or not isinstance(
            ci_lower, (int, float)
        ) or isinstance(ci_lower, bool):
            not_measured.add("P1_UTILITY_EFFECT_OR_INTERVAL_MISSING")
        elif effect <= 0 or ci_lower <= 0:
            failures.add("P1_STRICT_UTILITY_SUPERIORITY_NOT_MET")
        candidate_preferences = evidence.get("candidate_preference_count")
        baseline_preferences = evidence.get("baseline_preference_count")
        if not isinstance(candidate_preferences, int) or not isinstance(baseline_preferences, int):
            not_measured.add("P1_CANDIDATE_PREFERENCE_MISSING")
        elif candidate_preferences <= baseline_preferences:
            failures.add("P1_TIE_OR_BASELINE_PREFERENCE_CANNOT_ESTABLISH_SUPERIORITY")
        dimension_lowers = evidence.get("dimension_ci_lowers")
        if not isinstance(dimension_lowers, Mapping) or set(dimension_lowers) != set(
            GUARDRAIL_DIMENSIONS
        ):
            not_measured.add("P1_DIMENSION_GUARDRAIL_INTERVALS_MISSING")
        elif all(value is not None for value in margins.values()):
            for dimension in GUARDRAIL_DIMENSIONS:
                lower = dimension_lowers.get(dimension)
                if not isinstance(lower, (int, float)) or isinstance(lower, bool):
                    not_measured.add("P1_DIMENSION_GUARDRAIL_INTERVALS_MISSING")
                    break
                if lower < -float(margins[dimension]):
                    failures.add(f"P1_NONINFERIORITY_GUARDRAIL_FAILED_{dimension}")
    if outcome.get("owner_solo_status") not in {"NOT_SUPPLIED", "PRESENT_COMPLEMENTARY"}:
        blocking.add("P1_OWNER_SOLO_STATUS_INVALID")
    status = (
        "BLOCKED"
        if blocking
        else "FAIL"
        if failures
        else "NOT_MEASURED"
        if not_measured
        else "PASS"
    )
    result: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "status": status,
        "required_lanes": list(lanes),
        "owner_solo_status": outcome.get("owner_solo_status"),
        "authority": {
            "technical_validation": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
        },
        "blocking_reasons": sorted(blocking),
        "failure_reasons": sorted(failures),
        "not_measured_reasons": sorted(not_measured),
    }
    result["record_digest"] = canonical_digest(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apps RG W4 P1 outcome evidence")
    parser.add_argument("--outcome", type=Path, default=DEFAULT_OUTCOME_PATH)
    args = parser.parse_args(argv)
    result = validate_finished_resume_outcome(args.outcome)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2
