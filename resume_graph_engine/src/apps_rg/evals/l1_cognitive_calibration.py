"""Development-calibration and protected-holdout separation for L1 v3.

This is a technical readiness control.  It records deterministic development
QA and proves that its inputs do not overlap the sealed protected-holdout
commitment.  It does not create human labels, estimate user utility, or
authorize promotion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.evals.l1_cognitive_baseline import (
    L1CognitiveBaselineError,
    build_l1_cognitive_development_baseline_receipt,
    validate_l1_cognitive_development_baseline_receipt,
)
from apps_rg.evals.l1_cognitive_qa import (
    fixture_input_digest,
    load_development_corpus,
    run_l1_cognitive_technical_qa,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_COGNITIVE_DEVELOPMENT_CALIBRATION_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_development_calibration.v2"
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_HOLDOUT_COMMITMENT_PATH: Final[Path] = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "l1_v2_protected_holdout_commitment.v1.json"
)


class L1CognitiveCalibrationError(ValueError):
    """Raised when development calibration is not safely isolated from holdout."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def development_calibration_digest(receipt: Mapping[str, Any]) -> str:
    """Return the canonical digest excluding the receipt's self digest."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return _sha256(body)


def holdout_commitment_path() -> Path:
    """Return the tracked opaque protected-holdout commitment."""

    return _HOLDOUT_COMMITMENT_PATH


def _validate_holdout_commitment(value: Any) -> dict[str, Any]:
    """Validate opaque holdout metadata without opening any holdout fixture."""

    if not isinstance(value, Mapping):
        raise L1CognitiveCalibrationError("protected holdout commitment is invalid")
    commitment = dict(value)
    if (
        commitment.get("schema_version")
        != "apps_rg.l1_v2_protected_holdout_commitment.v1"
    ):
        raise L1CognitiveCalibrationError(
            "protected holdout commitment schema is invalid"
        )
    if commitment.get("app_scope") != _APP_SCOPE:
        raise L1CognitiveCalibrationError(
            "protected holdout commitment scope is invalid"
        )
    if commitment.get("development_access") != "DENIED":
        raise L1CognitiveCalibrationError(
            "protected holdout must deny development access"
        )
    if commitment.get("external_seal_required") is not True:
        raise L1CognitiveCalibrationError("protected holdout external seal is invalid")
    cases = commitment.get("commitments")
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not cases:
        raise L1CognitiveCalibrationError("protected holdout commitments are invalid")
    normalized_cases: list[dict[str, str]] = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise L1CognitiveCalibrationError("protected holdout case is invalid")
        fixture_id = str(case.get("fixture_id") or "").strip()
        source_input_digest = str(case.get("source_input_digest") or "").strip()
        if not fixture_id or not source_input_digest.startswith("sha256:"):
            raise L1CognitiveCalibrationError(
                "protected holdout case identity is invalid"
            )
        normalized_cases.append(
            {"fixture_id": fixture_id, "source_input_digest": source_input_digest}
        )
    expected_digest = _sha256(
        {key: value for key, value in commitment.items() if key != "commitment_digest"}
    )
    if commitment.get("commitment_digest") != expected_digest:
        raise L1CognitiveCalibrationError(
            "protected holdout commitment digest is invalid"
        )
    return commitment


def _load_holdout_commitment(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1CognitiveCalibrationError(
            "protected holdout commitment is unreadable"
        ) from exc
    return _validate_holdout_commitment(value)


def _receipt_body(
    *,
    corpus: Mapping[str, Any],
    technical_qa: Mapping[str, Any],
    holdout_commitment: Mapping[str, Any],
    baseline_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    cases = corpus.get("cases")
    results = technical_qa.get("results")
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise L1CognitiveCalibrationError("development corpus cases are invalid")
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise L1CognitiveCalibrationError("development QA results are invalid")
    development = sorted(
        {
            (str(case.get("fixture_id") or ""), fixture_input_digest(case))
            for case in cases
            if isinstance(case, Mapping)
        }
    )
    if not development or any(not fixture_id for fixture_id, _digest in development):
        raise L1CognitiveCalibrationError("development fixture identity is invalid")
    holdout_cases = holdout_commitment.get("commitments")
    if not isinstance(holdout_cases, Sequence):
        raise L1CognitiveCalibrationError("protected holdout commitments are invalid")
    holdout_digests = {
        str(case.get("source_input_digest") or "")
        for case in holdout_cases
        if isinstance(case, Mapping)
    }
    development_digests = {digest for _fixture_id, digest in development}
    overlap = sorted(development_digests & holdout_digests)
    result_by_id = {
        str(row.get("fixture_id") or ""): row
        for row in results
        if isinstance(row, Mapping)
    }
    expected_ids = {fixture_id for fixture_id, _digest in development}
    if set(result_by_id) != expected_ids:
        raise L1CognitiveCalibrationError("development QA result coverage is invalid")
    technical_pass = technical_qa.get("technical_status") == "PASS" and all(
        row.get("passed") is True for row in result_by_id.values()
    )
    try:
        validate_l1_cognitive_development_baseline_receipt(
            baseline_receipt,
            corpus=corpus,
        )
    except L1CognitiveBaselineError as exc:
        raise L1CognitiveCalibrationError(
            "development baseline receipt is invalid"
        ) from exc
    baseline_summary = baseline_receipt.get("summary")
    if not isinstance(baseline_summary, Mapping):
        raise L1CognitiveCalibrationError("development baseline summary is invalid")
    baseline_runs = baseline_summary.get("baseline_runs_by_version")
    expected_baseline_runs = {"v1": len(development), "v2": len(development)}
    if baseline_runs != expected_baseline_runs:
        raise L1CognitiveCalibrationError("development baseline run count is invalid")
    dominant_failure_slice = str(
        baseline_summary.get("dominant_failure_slice") or ""
    ).strip()
    if not dominant_failure_slice:
        raise L1CognitiveCalibrationError(
            "development baseline priority slice is invalid"
        )
    return {
        "schema_version": L1_COGNITIVE_DEVELOPMENT_CALIBRATION_SCHEMA_VERSION,
        "authority_class": "TECHNICAL_DEVELOPMENT_CALIBRATION_ONLY",
        "app_scope": _APP_SCOPE,
        "development": {
            "corpus_ref": "apps_rg/evals/fixtures/l1_cognitive_qa_development.v1.json",
            "corpus_digest": str(corpus["corpus_source_digest"]),
            "fixture_count": len(development),
            "fixture_input_digests": [
                {"fixture_id": fixture_id, "source_input_digest": digest}
                for fixture_id, digest in development
            ],
            "technical_qa_receipt_digest": str(technical_qa["receipt_digest"]),
            "technical_status": "PASS" if technical_pass else "FAIL",
            "v1_v2_baseline_receipt_digest": str(baseline_receipt["receipt_digest"]),
            "v1_v2_baseline_runs_by_version": dict(baseline_runs),
            "w1_priority_failure_slice": dominant_failure_slice,
        },
        "protected_holdout": {
            "commitment_ref": "apps_rg/evals/fixtures/l1_v2_protected_holdout_commitment.v1.json",
            "commitment_digest": str(holdout_commitment["commitment_digest"]),
            "development_access": "DENIED",
            "external_seal_required": True,
            "input_digest_overlap_count": len(overlap),
            "input_digest_overlap": overlap,
        },
        "human_outcome_calibration": {
            "status": "NOT_MEASURED",
            "reason_codes": ["BLINDED_HUMAN_REVIEW_REQUIRED"],
        },
        "authority": {
            "technical_validation": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
            "automatic_promotion": False,
        },
        "assertions": {
            "does_not_access_protected_holdout": True,
            "does_not_create_human_labels": True,
            "does_not_measure_P1_or_P2": True,
        },
    }


def build_l1_cognitive_development_calibration_receipt(
    *,
    corpus: Mapping[str, Any] | None = None,
    technical_qa: Mapping[str, Any] | None = None,
    holdout_commitment: Mapping[str, Any] | None = None,
    baseline_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce an opaque split proof from development QA and holdout commitment."""

    source_corpus = load_development_corpus() if corpus is None else dict(corpus)
    source_qa = (
        run_l1_cognitive_technical_qa(source_corpus)
        if technical_qa is None
        else dict(technical_qa)
    )
    source_holdout = (
        _load_holdout_commitment(_HOLDOUT_COMMITMENT_PATH)
        if holdout_commitment is None
        else _validate_holdout_commitment(holdout_commitment)
    )
    source_baseline = (
        build_l1_cognitive_development_baseline_receipt(corpus=source_corpus)
        if baseline_receipt is None
        else dict(baseline_receipt)
    )
    receipt = _receipt_body(
        corpus=source_corpus,
        technical_qa=source_qa,
        holdout_commitment=source_holdout,
        baseline_receipt=source_baseline,
    )
    receipt["receipt_digest"] = development_calibration_digest(receipt)
    validate_l1_cognitive_development_calibration_receipt(
        receipt,
        corpus=source_corpus,
        technical_qa=source_qa,
        holdout_commitment=source_holdout,
        baseline_receipt=source_baseline,
    )
    return receipt


def validate_l1_cognitive_development_calibration_receipt(
    receipt: Mapping[str, Any],
    *,
    corpus: Mapping[str, Any],
    technical_qa: Mapping[str, Any],
    holdout_commitment: Mapping[str, Any],
    baseline_receipt: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed unless calibration evidence exactly preserves the split proof."""

    if not isinstance(receipt, Mapping):
        raise L1CognitiveCalibrationError("development calibration receipt is invalid")
    if (
        receipt.get("schema_version")
        != L1_COGNITIVE_DEVELOPMENT_CALIBRATION_SCHEMA_VERSION
    ):
        raise L1CognitiveCalibrationError("development calibration schema is invalid")
    if receipt.get("authority_class") != "TECHNICAL_DEVELOPMENT_CALIBRATION_ONLY":
        raise L1CognitiveCalibrationError(
            "development calibration authority is invalid"
        )
    if receipt.get("app_scope") != _APP_SCOPE:
        raise L1CognitiveCalibrationError("development calibration scope is invalid")
    if receipt.get("receipt_digest") != development_calibration_digest(receipt):
        raise L1CognitiveCalibrationError("development calibration digest is invalid")
    source_baseline = (
        build_l1_cognitive_development_baseline_receipt(corpus=corpus)
        if baseline_receipt is None
        else dict(baseline_receipt)
    )
    expected = _receipt_body(
        corpus=corpus,
        technical_qa=technical_qa,
        holdout_commitment=_validate_holdout_commitment(holdout_commitment),
        baseline_receipt=source_baseline,
    )
    actual = dict(receipt)
    actual.pop("receipt_digest", None)
    if actual != expected:
        raise L1CognitiveCalibrationError(
            "development calibration receipt does not match its sources"
        )
    if receipt["protected_holdout"]["input_digest_overlap_count"] != 0:
        raise L1CognitiveCalibrationError(
            "development calibration overlaps the protected holdout"
        )


def write_l1_cognitive_development_calibration_receipt(
    *,
    output_path: Path,
    receipt: Mapping[str, Any],
    corpus: Mapping[str, Any],
    technical_qa: Mapping[str, Any],
    holdout_commitment: Mapping[str, Any],
    baseline_receipt: Mapping[str, Any] | None = None,
) -> Path:
    """Validate and write a development-only calibration receipt."""

    validate_l1_cognitive_development_calibration_receipt(
        receipt,
        corpus=corpus,
        technical_qa=technical_qa,
        holdout_commitment=holdout_commitment,
        baseline_receipt=baseline_receipt,
    )
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


__all__ = [
    "L1CognitiveCalibrationError",
    "L1_COGNITIVE_DEVELOPMENT_CALIBRATION_SCHEMA_VERSION",
    "build_l1_cognitive_development_calibration_receipt",
    "development_calibration_digest",
    "holdout_commitment_path",
    "validate_l1_cognitive_development_calibration_receipt",
    "write_l1_cognitive_development_calibration_receipt",
]
