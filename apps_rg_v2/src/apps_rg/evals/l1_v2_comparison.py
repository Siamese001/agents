"""W6 technical comparison and human-review readiness for L1 v1 versus v2.

This module evaluates only frozen synthetic fixtures.  It deliberately keeps
protected-holdout inputs external, never generates human judgments, and never
authorizes a product-visible v2-only gate or production promotion.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_planning_capsule import (
    PlanningCapsuleIntegrityError,
    build_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    L1PlanningV2IntegrityError,
    build_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    L1EvidenceObligationReceiptError,
    build_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_V2_DEVELOPMENT_CORPUS_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_v2_comparison_development_corpus.v1"
)
L1_V2_PROTECTED_HOLDOUT_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_v2_protected_holdout_commitment.v1"
)
L1_V2_COMPARISON_SCHEMA_VERSION: Final[str] = "apps_rg.l1_v2_comparison.v1"
L1_V2_REVIEW_PACKET_SCHEMA_VERSION: Final[str] = "apps_rg.l1_v2_review_packet.v1"
L1_V2_PROMOTION_READINESS_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_v2_promotion_readiness.v1"
)
L1_V2_COMPARISON_AUTHORITY: Final[str] = "TECHNICAL_EVALUATION_ONLY"
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_EMITTER: Final[str] = "apps_rg.evals.l1_v2_comparison"
_FIXTURE_DIR: Final[Path] = Path(__file__).resolve().parent / "fixtures"
_DEVELOPMENT_CORPUS_PATH: Final[Path] = (
    _FIXTURE_DIR / "l1_v2_comparison_development_corpus.v1.json"
)
_PROTECTED_HOLDOUT_PATH: Final[Path] = (
    _FIXTURE_DIR / "l1_v2_protected_holdout_commitment.v1.json"
)
_REVIEW_FORBIDDEN_FIELDS: Final[frozenset[str]] = frozenset(
    {"grade", "label", "score", "verdict", "adjudication", "approval"}
)


class L1V2ComparisonError(ValueError):
    """Raised when frozen W6 input, metric, or readiness evidence is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _digest_without(value: Mapping[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return _sha256(body)


def comparison_digest(receipt: Mapping[str, Any]) -> str:
    """Return the stable comparison digest excluding its self-reference."""

    return _digest_without(receipt, "comparison_digest")


def review_packet_digest(packet: Mapping[str, Any]) -> str:
    """Return the stable reviewer-packet digest excluding its self-reference."""

    return _digest_without(packet, "packet_digest")


def promotion_readiness_digest(receipt: Mapping[str, Any]) -> str:
    """Return the stable W6 promotion-readiness digest excluding itself."""

    return _digest_without(receipt, "readiness_digest")


def development_corpus_path() -> Path:
    """Return the tracked synthetic development-corpus path."""

    return _DEVELOPMENT_CORPUS_PATH


def protected_holdout_commitment_path() -> Path:
    """Return the tracked, opaque protected-holdout commitment path."""

    return _PROTECTED_HOLDOUT_PATH


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise L1V2ComparisonError(f"{field} must be a sequence")
    return list(value)


def _required_string(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1V2ComparisonError(f"{field} is required")
    return normalized


def _fixture_input(case: Mapping[str, Any]) -> dict[str, Any]:
    fixture_id = _required_string(case.get("fixture_id"), field="fixture_id")
    scenario = _required_string(case.get("scenario"), field="scenario")
    conditions = case.get("fixture_conditions")
    payload = case.get("app_payload")
    evidence_items = case.get("c0_evidence_items")
    if not isinstance(conditions, Mapping):
        raise L1V2ComparisonError("fixture_conditions must be a mapping")
    if not isinstance(payload, Mapping):
        raise L1V2ComparisonError("app_payload must be a mapping")
    if not isinstance(evidence_items, Sequence) or isinstance(
        evidence_items, (str, bytes)
    ):
        raise L1V2ComparisonError("c0_evidence_items must be a sequence")
    return {
        "fixture_id": fixture_id,
        "scenario": scenario,
        "fixture_conditions": copy.deepcopy(dict(conditions)),
        "app_payload": copy.deepcopy(dict(payload)),
        "c0_evidence_items": copy.deepcopy(list(evidence_items)),
    }


def fixture_input_digest(case: Mapping[str, Any]) -> str:
    """Return the source-input commitment for one synthetic fixture."""

    return _sha256(_fixture_input(case))


def _nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise L1V2ComparisonError(f"{field} must be a non-negative integer")
    return value


def _expected_deterministic_plan(case: Mapping[str, Any]) -> dict[str, Any]:
    expected = case.get("expected_deterministic_plan")
    if not isinstance(expected, Mapping):
        raise L1V2ComparisonError("expected_deterministic_plan must be a mapping")
    type_counts = expected.get("v2_requirement_type_counts")
    if not isinstance(type_counts, Mapping) or not type_counts:
        raise L1V2ComparisonError("v2_requirement_type_counts must be a mapping")
    normalized_counts: dict[str, int] = {}
    for requirement_type, count in type_counts.items():
        normalized_type = _required_string(
            requirement_type, field="v2 requirement type"
        )
        normalized_counts[normalized_type] = _nonnegative_int(
            count, field="v2 requirement type count"
        )
    v2_requirement_count = _nonnegative_int(
        expected.get("v2_requirement_count"), field="v2_requirement_count"
    )
    if sum(normalized_counts.values()) != v2_requirement_count:
        raise L1V2ComparisonError(
            "v2 requirement type counts must equal v2 requirement count"
        )
    return {
        "v1_requirement_count": _nonnegative_int(
            expected.get("v1_requirement_count"), field="v1_requirement_count"
        ),
        "v2_requirement_count": v2_requirement_count,
        "v2_requirement_type_counts": normalized_counts,
    }


def _development_corpus_body(corpus: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(corpus)
    body.pop("corpus_source_digest", None)
    return body


def _validate_development_corpus(corpus: Mapping[str, Any]) -> None:
    if not isinstance(corpus, Mapping):
        raise L1V2ComparisonError("development corpus must be a mapping")
    if corpus.get("schema_version") != L1_V2_DEVELOPMENT_CORPUS_SCHEMA_VERSION:
        raise L1V2ComparisonError("development corpus schema_version is invalid")
    if corpus.get("app_scope") != _APP_SCOPE:
        raise L1V2ComparisonError("development corpus app scope is invalid")
    cases = _sequence(corpus.get("cases"), field="development corpus cases")
    if not cases:
        raise L1V2ComparisonError("development corpus cannot be empty")
    seen: set[str] = set()
    scenarios: set[str] = set()
    for raw in cases:
        if not isinstance(raw, Mapping):
            raise L1V2ComparisonError("development corpus case is invalid")
        fixture_id = _required_string(raw.get("fixture_id"), field="fixture_id")
        if fixture_id in seen:
            raise L1V2ComparisonError("development fixture IDs must be unique")
        seen.add(fixture_id)
        scenarios.add(_required_string(raw.get("scenario"), field="scenario"))
        _expected_deterministic_plan(raw)
        if raw.get("source_input_digest") != fixture_input_digest(raw):
            raise L1V2ComparisonError("development fixture source digest mismatch")
    required_scenarios = {"STRAIGHTFORWARD", "COMPOUND", "CROSS_CUTTING", "UNKNOWN"}
    if not required_scenarios <= scenarios:
        raise L1V2ComparisonError("development corpus scenario coverage is incomplete")
    thresholds = corpus.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise L1V2ComparisonError("development thresholds are invalid")
    for field in (
        "promotion_requires_measured_false_broad_mapping",
        "promotion_requires_measured_escalation_precision",
        "promotion_requires_runtime_completion_cost_latency",
    ):
        if thresholds.get(field) is not True:
            raise L1V2ComparisonError("development promotion threshold is invalid")
    if corpus.get("corpus_source_digest") != _sha256(_development_corpus_body(corpus)):
        raise L1V2ComparisonError("development corpus digest mismatch")


def load_development_corpus(path: Path | None = None) -> dict[str, Any]:
    """Load the tracked, source-bound W6 development corpus."""

    source = Path(path or _DEVELOPMENT_CORPUS_PATH)
    try:
        corpus = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1V2ComparisonError("development corpus is unreadable") from exc
    if not isinstance(corpus, Mapping):
        raise L1V2ComparisonError("development corpus must decode to a mapping")
    value = dict(corpus)
    _validate_development_corpus(value)
    return value


def _protected_commitment_body(commitment: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(commitment)
    body.pop("commitment_digest", None)
    return body


def _validate_protected_holdout_commitment(commitment: Mapping[str, Any]) -> None:
    if not isinstance(commitment, Mapping):
        raise L1V2ComparisonError("protected holdout commitment must be a mapping")
    if commitment.get("schema_version") != L1_V2_PROTECTED_HOLDOUT_SCHEMA_VERSION:
        raise L1V2ComparisonError("protected holdout schema_version is invalid")
    if commitment.get("app_scope") != _APP_SCOPE:
        raise L1V2ComparisonError("protected holdout app scope is invalid")
    if commitment.get("development_access") != "DENIED":
        raise L1V2ComparisonError("protected holdout must deny development access")
    if (
        commitment.get("external_seal_required") is not True
        or commitment.get("promotion_requires_external_holdout_results") is not True
    ):
        raise L1V2ComparisonError("protected holdout authority boundary is invalid")
    rows = _sequence(commitment.get("commitments"), field="holdout commitments")
    scenarios: set[str] = set()
    fixture_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise L1V2ComparisonError("protected holdout commitment row is invalid")
        fixture_id = _required_string(row.get("fixture_id"), field="holdout fixture_id")
        if fixture_id in fixture_ids:
            raise L1V2ComparisonError("protected holdout fixture IDs must be unique")
        fixture_ids.add(fixture_id)
        scenarios.add(_required_string(row.get("scenario"), field="holdout scenario"))
        digest = _required_string(
            row.get("source_input_digest"), field="holdout source_input_digest"
        )
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise L1V2ComparisonError("protected holdout source digest is invalid")
        if any(
            field in row
            for field in ("app_payload", "fixture_conditions", "c0_evidence_items")
        ):
            raise L1V2ComparisonError("protected holdout inputs must not be committed")
    required_scenarios = {
        "STALE_BRIEF",
        "CONFLICTING_CONSTRAINT",
        "ABSENT_CANDIDATE_EVIDENCE",
    }
    if scenarios != required_scenarios:
        raise L1V2ComparisonError("protected holdout scenario coverage is invalid")
    if commitment.get("commitment_digest") != _sha256(
        _protected_commitment_body(commitment)
    ):
        raise L1V2ComparisonError("protected holdout commitment digest mismatch")


def load_protected_holdout_commitment(path: Path | None = None) -> dict[str, Any]:
    """Load opaque holdout commitments without loading any holdout inputs."""

    source = Path(path or _PROTECTED_HOLDOUT_PATH)
    try:
        commitment = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1V2ComparisonError("protected holdout commitment is unreadable") from exc
    if not isinstance(commitment, Mapping):
        raise L1V2ComparisonError("protected holdout must decode to a mapping")
    value = dict(commitment)
    _validate_protected_holdout_commitment(value)
    return value


def validate_external_protected_holdout(
    cases: Sequence[Mapping[str, Any]], *, commitment: Mapping[str, Any]
) -> None:
    """Validate externally supplied cases against opaque committed identities.

    This accepts only a controlled caller's inputs. It does not run, label, or
    expose them, and it does not accept an unsealed development substitute.
    """

    _validate_protected_holdout_commitment(commitment)
    expected = {
        str(row["fixture_id"]): str(row["source_input_digest"])
        for row in commitment["commitments"]
        if isinstance(row, Mapping)
    }
    observed: dict[str, str] = {}
    for case in cases:
        if not isinstance(case, Mapping):
            raise L1V2ComparisonError("external protected holdout case is invalid")
        fixture_id = _required_string(case.get("fixture_id"), field="fixture_id")
        if fixture_id in observed:
            raise L1V2ComparisonError("external protected holdout fixture is duplicate")
        observed[fixture_id] = fixture_input_digest(case)
    if observed != expected:
        raise L1V2ComparisonError("external protected holdout does not match commitment")


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _case_result(case: Mapping[str, Any]) -> dict[str, Any]:
    fixture = _fixture_input(case)
    fixture_id = str(fixture["fixture_id"])
    expected_plan = _expected_deterministic_plan(case)
    kwargs = {
        "app_payload": fixture["app_payload"],
        "request_id": f"w6-{fixture_id}",
        "run_id": f"w6-{fixture_id}",
        "trace_id": f"w6-{fixture_id}",
        "replay_key": f"w6-{fixture_id}",
        "planning_profile_ref": l1_planning_profile_ref(),
        "planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
    }
    try:
        v1 = build_apps_rg_l1_planning_capsule(**kwargs)
        v2 = build_apps_rg_l1_planning_capsule_v2(**kwargs)
    except (PlanningCapsuleIntegrityError, L1PlanningV2IntegrityError) as exc:
        raise L1V2ComparisonError("frozen fixture planning capsule is invalid") from exc
    try:
        c0 = build_l1_evidence_obligation_receipt(
            capsule=v2,
            request_id=str(kwargs["request_id"]),
            run_id=str(kwargs["run_id"]),
            trace_id=str(kwargs["trace_id"]),
            final_evidence_digest=_sha256(
                {
                    "fixture_id": fixture_id,
                    "evidence_items": fixture["c0_evidence_items"],
                }
            ),
            evidence_items=fixture["c0_evidence_items"],
        )
    except L1EvidenceObligationReceiptError as exc:
        raise L1V2ComparisonError("frozen fixture C0 receipt is invalid") from exc
    v1_obligations = list(_mapping(v1.get("jd_obligation_plan")).get("obligations") or ())
    v2_requirements = list(v2.get("requirements") or ())
    c0_dispositions = list(c0.get("obligation_dispositions") or ())
    observed_v2_type_counts: dict[str, int] = {}
    for requirement in v2_requirements:
        requirement_type = str(_mapping(requirement).get("requirement_type") or "")
        observed_v2_type_counts[requirement_type] = (
            observed_v2_type_counts.get(requirement_type, 0) + 1
        )
    v1_critical = [
        row for row in v1_obligations if _mapping(row).get("criticality") == "CRITICAL"
    ]
    v2_critical = [
        row for row in v2_requirements if _mapping(row).get("criticality") == "CRITICAL"
    ]
    v1_critical_covered = sum(
        bool(_mapping(row).get("mapped_unit_ids"))
        or _mapping(row).get("coverage_status") == "ESCALATED"
        for row in v1_critical
    )
    v2_critical_covered = sum(
        _mapping(row).get("coverage_status") in {"MAPPED", "ESCALATED"}
        for row in v2_critical
    )
    unresolved = sum(
        _mapping(row).get("support_disposition") in {"INSUFFICIENT", "CONTRADICTED"}
        for row in c0_dispositions
    )
    return {
        "fixture_id": fixture_id,
        "scenario": fixture["scenario"],
        "fixture_input_digest": fixture_input_digest(case),
        "fixture_conditions_digest": _sha256(fixture["fixture_conditions"]),
        "deterministic_requirement_checks": {
            "v1_requirement_count_matches": len(v1_obligations)
            == expected_plan["v1_requirement_count"],
            "v2_requirement_count_matches": len(v2_requirements)
            == expected_plan["v2_requirement_count"],
            "v2_requirement_types_match": observed_v2_type_counts
            == expected_plan["v2_requirement_type_counts"],
        },
        "v1": {
            "planning_status": str(v1.get("planning_status") or ""),
            "requirement_count": len(v1_obligations),
            "critical_requirement_count": len(v1_critical),
            "critical_requirement_coverage": _safe_rate(
                v1_critical_covered, len(v1_critical)
            ),
            "broad_target_mapping_count": sum(
                len(_mapping(row).get("mapped_unit_ids") or ()) > 1
                for row in v1_obligations
            ),
        },
        "v2": {
            "planning_status": str(v2.get("planning_status") or ""),
            "requirement_count": len(v2_requirements),
            "typed_requirement_count": sum(
                _mapping(row).get("requirement_type") != "UNKNOWN"
                for row in v2_requirements
            ),
            "critical_requirement_count": len(v2_critical),
            "critical_requirement_coverage": _safe_rate(
                v2_critical_covered, len(v2_critical)
            ),
            "escalated_requirement_count": sum(
                _mapping(row).get("coverage_status") == "ESCALATED"
                for row in v2_requirements
            ),
            "broad_target_mapping_count": sum(
                len(_mapping(row).get("target_unit_ids") or ()) > 1
                for row in v2_requirements
            ),
        },
        "c0": {
            "planned_obligation_count": len(c0_dispositions),
            "reconciled_obligation_count": len(c0_dispositions),
            "all_obligations_disposed": _mapping(c0.get("coverage")).get(
                "all_obligations_disposed"
            )
            is True,
            "unsupported_claim_block_candidate_count": unresolved,
            "receipt_digest": str(c0.get("receipt_digest") or ""),
        },
    }


def _comparison_body(corpus: Mapping[str, Any]) -> dict[str, Any]:
    _validate_development_corpus(corpus)
    cases = sorted(
        (_case_result(case) for case in corpus["cases"] if isinstance(case, Mapping)),
        key=lambda row: str(row["fixture_id"]),
    )
    if len(cases) != len(corpus["cases"]):
        raise L1V2ComparisonError("development corpus case is invalid")
    v1_critical_total = sum(int(row["v1"]["critical_requirement_count"]) for row in cases)
    v2_critical_total = sum(int(row["v2"]["critical_requirement_count"]) for row in cases)
    v1_critical_covered = sum(
        int(row["v1"]["critical_requirement_count"])
        if row["v1"]["critical_requirement_coverage"] == 1.0
        else 0
        for row in cases
    )
    v2_critical_covered = sum(
        int(row["v2"]["critical_requirement_count"])
        if row["v2"]["critical_requirement_coverage"] == 1.0
        else 0
        for row in cases
    )
    c0_planned = sum(int(row["c0"]["planned_obligation_count"]) for row in cases)
    c0_reconciled = sum(int(row["c0"]["reconciled_obligation_count"]) for row in cases)
    v2_broad = sum(int(row["v2"]["broad_target_mapping_count"]) for row in cases)
    deterministic_requirement_checks_match = all(
        all(bool(result) for result in row["deterministic_requirement_checks"].values())
        for row in cases
    )
    thresholds = _mapping(corpus.get("thresholds"))
    v1_coverage = _safe_rate(v1_critical_covered, v1_critical_total)
    v2_coverage = _safe_rate(v2_critical_covered, v2_critical_total)
    coverage_delta = (
        None if v1_coverage is None or v2_coverage is None else v2_coverage - v1_coverage
    )
    c0_rate = _safe_rate(c0_reconciled, c0_planned)
    technical_thresholds_met = (
        coverage_delta is not None
        and coverage_delta >= float(thresholds["minimum_critical_requirement_coverage_delta"])
        and c0_rate is not None
        and c0_rate >= float(thresholds["minimum_c0_obligation_reconciliation_rate"])
        and _safe_rate(v2_broad, len(cases))
        <= float(thresholds["maximum_v2_broad_target_mapping_rate"])
        and deterministic_requirement_checks_match
    )
    return {
        "schema_version": L1_V2_COMPARISON_SCHEMA_VERSION,
        "authority_class": L1_V2_COMPARISON_AUTHORITY,
        "app_scope": _APP_SCOPE,
        "development_corpus": {
            "corpus_id": str(corpus.get("corpus_id") or ""),
            "corpus_source_digest": str(corpus.get("corpus_source_digest") or ""),
            "fixture_count": len(cases),
        },
        "protected_holdout": {
            "commitment_ref": "apps_rg/evals/fixtures/l1_v2_protected_holdout_commitment.v1.json",
            "results_present": False,
            "development_access": "DENIED",
        },
        "case_results": cases,
        "metrics": {
            "requirement_extraction_and_typing": {
                "measurement_status": "SOURCE_BOUND_DETERMINISTIC_FIXTURE_ASSERTIONS",
                "v1_requirement_count": sum(int(row["v1"]["requirement_count"]) for row in cases),
                "v2_requirement_count": sum(int(row["v2"]["requirement_count"]) for row in cases),
                "v2_typed_requirement_count": sum(
                    int(row["v2"]["typed_requirement_count"]) for row in cases
                ),
                "all_fixture_assertions_match": deterministic_requirement_checks_match,
            },
            "critical_requirement_coverage": {
                "v1_rate": v1_coverage,
                "v2_rate": v2_coverage,
                "delta": coverage_delta,
            },
            "false_broad_mapping": {
                "measurement_status": "PROXY_ONLY_HUMAN_GROUND_TRUTH_REQUIRED",
                "v2_broad_target_mapping_rate": _safe_rate(v2_broad, len(cases)),
            },
            "escalation_precision": {
                "measurement_status": "HUMAN_ADJUDICATION_REQUIRED",
                "v2_escalation_count": sum(
                    int(row["v2"]["escalated_requirement_count"]) for row in cases
                ),
            },
            "c0_obligation_reconciliation": {
                "rate": c0_rate,
                "all_dispositions_observed": all(
                    row["c0"]["all_obligations_disposed"] for row in cases
                ),
            },
            "unsupported_claim_blocks": {
                "measurement_status": "C0_BLOCK_CANDIDATE_ONLY",
                "candidate_count": sum(
                    int(row["c0"]["unsupported_claim_block_candidate_count"])
                    for row in cases
                ),
            },
            "completion_cost_latency": {
                "measurement_status": "RUNTIME_EXECUTION_NOT_MEASURED",
                "completion_rate": None,
                "cost": None,
                "latency_ms": None,
            },
        },
        "thresholds": copy.deepcopy(thresholds),
        "technical_thresholds_met": technical_thresholds_met,
        "promotion_authority": {
            "human_review_completed": False,
            "protected_holdout_results_present": False,
            "signed_promotion_decision_present": False,
            "critical_requirement_fail_closed_enforcement_enabled": False,
            "production_promotion_authorized": False,
        },
        "authority_assertions": {
            "development_fixtures_are_not_human_labels": True,
            "does_not_create_human_grades": True,
            "does_not_authorize_product_promotion": True,
            "does_not_change_c0_or_l2_runtime_authority": True,
        },
        "emitter": _EMITTER,
    }


def build_l1_v2_comparison(corpus: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compare v1 and v2 deterministically on tracked development fixtures."""

    source = load_development_corpus() if corpus is None else dict(corpus)
    receipt = _comparison_body(source)
    receipt["comparison_digest"] = comparison_digest(receipt)
    validate_l1_v2_comparison(receipt, corpus=source)
    return receipt


def validate_l1_v2_comparison(
    receipt: Mapping[str, Any], *, corpus: Mapping[str, Any] | None = None
) -> None:
    """Fail closed unless a comparison is exactly source-bound and non-promoting."""

    if not isinstance(receipt, Mapping):
        raise L1V2ComparisonError("comparison receipt must be a mapping")
    if receipt.get("schema_version") != L1_V2_COMPARISON_SCHEMA_VERSION:
        raise L1V2ComparisonError("comparison receipt schema_version is invalid")
    if receipt.get("authority_class") != L1_V2_COMPARISON_AUTHORITY:
        raise L1V2ComparisonError("comparison receipt authority is invalid")
    if receipt.get("comparison_digest") != comparison_digest(receipt):
        raise L1V2ComparisonError("comparison receipt digest mismatch")
    source = load_development_corpus() if corpus is None else dict(corpus)
    expected = _comparison_body(source)
    body = dict(receipt)
    body.pop("comparison_digest", None)
    if body != expected:
        raise L1V2ComparisonError("comparison receipt does not match frozen corpus")


def _review_item(case: Mapping[str, Any]) -> dict[str, Any]:
    fixture_id = str(case["fixture_id"])
    body = {
        "fixture_id": fixture_id,
        "scenario": str(case["scenario"]),
        "review_questions": [
            "Is semantic requirement segmentation faithful to the source condition?",
            "Is the recorded escalation or targeting boundary appropriate?",
        ],
        "human_judgment_required": True,
        "no_prepopulated_grade": True,
    }
    return {
        "review_item_id": "w6review-"
        + hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()[:16],
        **body,
    }


def _review_packet_body(comparison: Mapping[str, Any]) -> dict[str, Any]:
    if (
        comparison.get("schema_version") != L1_V2_COMPARISON_SCHEMA_VERSION
        or comparison.get("comparison_digest") != comparison_digest(comparison)
    ):
        raise L1V2ComparisonError("comparison is invalid for review packet")
    cases = _sequence(comparison.get("case_results"), field="comparison case_results")
    items = [
        _review_item(case)
        for case in cases
        if isinstance(case, Mapping)
        and (
            str(case.get("scenario") or "")
            in {"COMPOUND", "CROSS_CUTTING", "UNKNOWN"}
            or int(_mapping(case.get("v2")).get("escalated_requirement_count") or 0) > 0
        )
    ]
    items.sort(key=lambda row: str(row["review_item_id"]))
    return {
        "schema_version": L1_V2_REVIEW_PACKET_SCHEMA_VERSION,
        "authority_class": "HUMAN_REVIEW_INTAKE_ONLY",
        "app_scope": _APP_SCOPE,
        "comparison": {
            "comparison_digest": str(comparison["comparison_digest"]),
            "development_fixture_count": len(cases),
        },
        "review_items": items,
        "human_review_authority": {
            "human_review_required": True,
            "named_reviewers": [],
            "human_grades_present": False,
            "adjudication_present": False,
            "signed_promotion_decision_present": False,
            "production_promotion_authorized": False,
        },
        "authority_assertions": {
            "does_not_prefill_human_grades": True,
            "does_not_select_reviewers": True,
            "does_not_authorize_promotion": True,
        },
        "emitter": _EMITTER,
    }


def _assert_no_prefilled_review_judgment(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in _REVIEW_FORBIDDEN_FIELDS:
                raise L1V2ComparisonError("review packet contains a prefilled judgment")
            _assert_no_prefilled_review_judgment(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _assert_no_prefilled_review_judgment(item)


def build_l1_v2_review_packet(comparison: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare ambiguity items without creating human grades or reviewers."""

    packet = _review_packet_body(comparison)
    packet["packet_digest"] = review_packet_digest(packet)
    validate_l1_v2_review_packet(packet, comparison=comparison)
    return packet


def validate_l1_v2_review_packet(
    packet: Mapping[str, Any], *, comparison: Mapping[str, Any]
) -> None:
    """Reject reviewer packets that smuggle labels, approval, or promotion."""

    if not isinstance(packet, Mapping):
        raise L1V2ComparisonError("review packet must be a mapping")
    if packet.get("schema_version") != L1_V2_REVIEW_PACKET_SCHEMA_VERSION:
        raise L1V2ComparisonError("review packet schema_version is invalid")
    if packet.get("authority_class") != "HUMAN_REVIEW_INTAKE_ONLY":
        raise L1V2ComparisonError("review packet authority is invalid")
    if packet.get("packet_digest") != review_packet_digest(packet):
        raise L1V2ComparisonError("review packet digest mismatch")
    expected = _review_packet_body(comparison)
    body = dict(packet)
    body.pop("packet_digest", None)
    if body != expected:
        raise L1V2ComparisonError("review packet does not match comparison receipt")
    _assert_no_prefilled_review_judgment(packet.get("review_items"))


def _promotion_readiness_body(
    comparison: Mapping[str, Any], review_packet: Mapping[str, Any]
) -> dict[str, Any]:
    validate_l1_v2_review_packet(review_packet, comparison=comparison)
    return {
        "schema_version": L1_V2_PROMOTION_READINESS_SCHEMA_VERSION,
        "authority_class": "PROMOTION_READINESS_ONLY",
        "app_scope": _APP_SCOPE,
        "comparison_digest": str(comparison["comparison_digest"]),
        "review_packet_digest": str(review_packet["packet_digest"]),
        "technical_thresholds_met": comparison.get("technical_thresholds_met") is True,
        "status": "NOT_AUTHORIZED",
        "blockers": [
            "PROTECTED_HOLDOUT_RESULTS_MISSING",
            "ADJUDICATED_HUMAN_REVIEW_MISSING",
            "SIGNED_PROMOTION_DECISION_MISSING",
            "RUNTIME_COMPLETION_COST_LATENCY_MISSING",
        ],
        "promotion_authority": {
            "protected_holdout_results_present": False,
            "human_review_completed": False,
            "signed_promotion_decision_present": False,
            "critical_requirement_fail_closed_enforcement_enabled": False,
            "production_promotion_authorized": False,
        },
        "authority_assertions": {
            "technical_comparison_is_not_human_qualification": True,
            "review_readiness_is_not_release_authorization": True,
            "does_not_enable_v2_only_runtime_gate": True,
        },
        "emitter": _EMITTER,
    }


def build_l1_v2_promotion_readiness(
    comparison: Mapping[str, Any], review_packet: Mapping[str, Any]
) -> dict[str, Any]:
    """Record the intentionally blocked W6 promotion boundary."""

    receipt = _promotion_readiness_body(comparison, review_packet)
    receipt["readiness_digest"] = promotion_readiness_digest(receipt)
    validate_l1_v2_promotion_readiness(
        receipt, comparison=comparison, review_packet=review_packet
    )
    return receipt


def validate_l1_v2_promotion_readiness(
    receipt: Mapping[str, Any],
    *,
    comparison: Mapping[str, Any],
    review_packet: Mapping[str, Any],
) -> None:
    """Fail closed: W6 technical work may never claim promotion authority."""

    if not isinstance(receipt, Mapping):
        raise L1V2ComparisonError("promotion readiness must be a mapping")
    if receipt.get("schema_version") != L1_V2_PROMOTION_READINESS_SCHEMA_VERSION:
        raise L1V2ComparisonError("promotion readiness schema_version is invalid")
    if receipt.get("authority_class") != "PROMOTION_READINESS_ONLY":
        raise L1V2ComparisonError("promotion readiness authority is invalid")
    if receipt.get("readiness_digest") != promotion_readiness_digest(receipt):
        raise L1V2ComparisonError("promotion readiness digest mismatch")
    expected = _promotion_readiness_body(comparison, review_packet)
    body = dict(receipt)
    body.pop("readiness_digest", None)
    if body != expected:
        raise L1V2ComparisonError("promotion readiness does not match W6 evidence")


def write_l1_v2_comparison(
    *, output_path: Path, receipt: Mapping[str, Any], corpus: Mapping[str, Any]
) -> Path:
    """Validate and write one caller-owned technical comparison receipt."""

    validate_l1_v2_comparison(receipt, corpus=corpus)
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


def write_l1_v2_review_packet(
    *, output_path: Path, packet: Mapping[str, Any], comparison: Mapping[str, Any]
) -> Path:
    """Validate and write one caller-owned review-readiness packet."""

    validate_l1_v2_review_packet(packet, comparison=comparison)
    path = Path(output_path)
    sr.write_stage_receipt(path, packet)
    return path


def write_l1_v2_promotion_readiness(
    *,
    output_path: Path,
    receipt: Mapping[str, Any],
    comparison: Mapping[str, Any],
    review_packet: Mapping[str, Any],
) -> Path:
    """Validate and write one caller-owned blocked promotion-readiness receipt."""

    validate_l1_v2_promotion_readiness(
        receipt, comparison=comparison, review_packet=review_packet
    )
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


__all__ = [
    "L1V2ComparisonError",
    "L1_V2_COMPARISON_SCHEMA_VERSION",
    "L1_V2_PROMOTION_READINESS_SCHEMA_VERSION",
    "L1_V2_REVIEW_PACKET_SCHEMA_VERSION",
    "build_l1_v2_comparison",
    "build_l1_v2_promotion_readiness",
    "build_l1_v2_review_packet",
    "comparison_digest",
    "development_corpus_path",
    "fixture_input_digest",
    "load_development_corpus",
    "load_protected_holdout_commitment",
    "promotion_readiness_digest",
    "protected_holdout_commitment_path",
    "review_packet_digest",
    "validate_external_protected_holdout",
    "validate_l1_v2_comparison",
    "validate_l1_v2_promotion_readiness",
    "validate_l1_v2_review_packet",
    "write_l1_v2_comparison",
    "write_l1_v2_promotion_readiness",
    "write_l1_v2_review_packet",
]
