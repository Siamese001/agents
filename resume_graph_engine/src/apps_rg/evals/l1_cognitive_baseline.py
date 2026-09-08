"""Source-bound W0 baseline for the Apps RG L1 cognition roadmap.

The baseline is intentionally technical and development-only.  It runs the
existing v1 and v2 planners exactly once for each frozen development fixture,
then records structural limitations with source-span digests.  It neither
labels semantic quality nor claims that v3 is better; those remain protected
holdout and human-review questions.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.evals.l1_cognitive_qa import (
    fixture_input_digest,
    load_development_corpus,
    validate_l1_cognitive_development_corpus,
)
from apps_rg.runtime.bindings.l1_planning_capsule import (
    build_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    build_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_COGNITIVE_DEVELOPMENT_BASELINE_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_development_baseline.v1"
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_BASELINE_VERSIONS: Final[tuple[str, str]] = ("v1", "v2")
_RELATION_TYPES: Final[frozenset[str]] = frozenset({"AND", "OR", "NOT", "EXCEPTION"})
_SLICE_PRIORITY: Final[tuple[str, ...]] = (
    "COMPOUND_AND_RELATION_DECOMPOSITION",
    "BROAD_TARGETING",
    "UNTYPED_SEMANTIC_INTERPRETATION",
    "PREEXECUTION_CRITIQUE_GAP",
    "OBSERVED_OUTCOME_REVISION_GAP",
)


class L1CognitiveBaselineError(ValueError):
    """Raised when a W0 development baseline is invalid or not source-bound."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def development_baseline_digest(receipt: Mapping[str, Any]) -> str:
    """Return the canonical digest excluding the receipt self-reference."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return _sha256(body)


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise L1CognitiveBaselineError(f"{label} is invalid")
    return dict(value)


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise L1CognitiveBaselineError(f"{label} is invalid")
    return list(value)


def _required_string(value: Any, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1CognitiveBaselineError(f"{label} is required")
    return normalized


def _digest(value: Any, *, label: str) -> str:
    normalized = _required_string(value, label=label)
    if not normalized.startswith("sha256:") or len(normalized) != 71:
        raise L1CognitiveBaselineError(f"{label} is invalid")
    return normalized


def _case_expectations(case: Mapping[str, Any]) -> tuple[int, str]:
    expectations = _mapping(case.get("expectations"), label="baseline expectations")
    expected_count = expectations.get("minimum_atomic_requirement_count")
    if isinstance(expected_count, bool) or not isinstance(expected_count, int):
        raise L1CognitiveBaselineError("baseline atomic expectation is invalid")
    if expected_count < 1:
        raise L1CognitiveBaselineError("baseline atomic expectation is invalid")
    relation = str(expectations.get("required_relation") or "").strip()
    if relation and relation not in _RELATION_TYPES:
        raise L1CognitiveBaselineError("baseline relation expectation is invalid")
    return expected_count, relation


def _planner_kwargs(case: Mapping[str, Any]) -> dict[str, Any]:
    fixture_id = _required_string(case.get("fixture_id"), label="baseline fixture_id")
    payload = _mapping(case.get("app_payload"), label="baseline app_payload")
    return {
        "app_payload": copy.deepcopy(payload),
        "request_id": f"w0-baseline-{fixture_id}",
        "run_id": f"w0-baseline-{fixture_id}",
        "trace_id": f"w0-baseline-{fixture_id}",
        "replay_key": f"w0-baseline-{fixture_id}",
        "planning_profile_ref": l1_planning_profile_ref(),
        "planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
    }


def _source_span_digests(v2_capsule: Mapping[str, Any]) -> list[str]:
    requirements = _sequence(
        v2_capsule.get("requirements"), label="v2 baseline requirements"
    )
    spans: list[str] = []
    for requirement in requirements:
        row = _mapping(requirement, label="v2 baseline requirement")
        span = _mapping(row.get("source_span"), label="v2 baseline source span")
        spans.append(_digest(span.get("span_digest"), label="v2 source span digest"))
    if not spans:
        raise L1CognitiveBaselineError("v2 baseline lacks source-span examples")
    return sorted(set(spans))


def _observation(
    *,
    category: str,
    code: str,
    baseline_versions: Sequence[str],
    source_span_digests: Sequence[str],
) -> dict[str, Any]:
    return {
        "category": category,
        "code": code,
        "baseline_versions": list(baseline_versions),
        "source_span_digests": sorted(set(source_span_digests)),
    }


def _priority_slice(
    *, observations: Sequence[Mapping[str, Any]], expected_relation: str
) -> str:
    codes = {str(row.get("code") or "") for row in observations}
    if expected_relation and (
        "V1_OBLIGATION_COALESCES_EXPECTED_ATOMS" in codes
        or "V2_PARENT_COALESCES_EXPECTED_ATOMS" in codes
        or "V1_V2_NO_EXPLICIT_RELATION_LEDGER" in codes
    ):
        return "COMPOUND_AND_RELATION_DECOMPOSITION"
    if "V1_BROAD_MULTI_UNIT_TARGETING" in codes:
        return "BROAD_TARGETING"
    if "V1_NO_TYPED_REQUIREMENT_SEMANTICS" in codes:
        return "UNTYPED_SEMANTIC_INTERPRETATION"
    if "V1_V2_NO_PREEXECUTION_CRITIQUE_LEDGER" in codes:
        return "PREEXECUTION_CRITIQUE_GAP"
    return "OBSERVED_OUTCOME_REVISION_GAP"


def _case_baseline(case: Mapping[str, Any]) -> dict[str, Any]:
    fixture_id = _required_string(case.get("fixture_id"), label="baseline fixture_id")
    expected_atoms, expected_relation = _case_expectations(case)
    kwargs = _planner_kwargs(case)
    try:
        v1 = dict(build_apps_rg_l1_planning_capsule(**kwargs))
        v2 = dict(build_apps_rg_l1_planning_capsule_v2(**kwargs))
    except ValueError as exc:
        raise L1CognitiveBaselineError("baseline planner invocation failed") from exc

    v1_obligations = _sequence(
        _mapping(v1.get("jd_obligation_plan"), label="v1 baseline obligation plan").get(
            "obligations"
        ),
        label="v1 baseline obligations",
    )
    v2_requirements = _sequence(
        v2.get("requirements"), label="v2 baseline requirements"
    )
    span_digests = _source_span_digests(v2)
    observations: list[dict[str, Any]] = []
    if len(v1_obligations) < expected_atoms:
        observations.append(
            _observation(
                category="DECOMPOSITION",
                code="V1_OBLIGATION_COALESCES_EXPECTED_ATOMS",
                baseline_versions=("v1",),
                source_span_digests=span_digests,
            )
        )
    if len(v2_requirements) < expected_atoms:
        observations.append(
            _observation(
                category="DECOMPOSITION",
                code="V2_PARENT_COALESCES_EXPECTED_ATOMS",
                baseline_versions=("v2",),
                source_span_digests=span_digests,
            )
        )
    if expected_relation and "relations" not in v1 and "relations" not in v2:
        observations.append(
            _observation(
                category="RELATION_SCOPE",
                code="V1_V2_NO_EXPLICIT_RELATION_LEDGER",
                baseline_versions=_BASELINE_VERSIONS,
                source_span_digests=span_digests,
            )
        )
    if all(
        "requirement_type" not in _mapping(obligation, label="v1 baseline obligation")
        for obligation in v1_obligations
    ):
        observations.append(
            _observation(
                category="SEMANTICS",
                code="V1_NO_TYPED_REQUIREMENT_SEMANTICS",
                baseline_versions=("v1",),
                source_span_digests=span_digests,
            )
        )
    if any(
        len(
            _sequence(
                _mapping(obligation, label="v1 baseline obligation").get(
                    "mapped_unit_ids"
                ),
                label="v1 baseline mapped units",
            )
        )
        > 1
        for obligation in v1_obligations
    ):
        observations.append(
            _observation(
                category="TARGETING",
                code="V1_BROAD_MULTI_UNIT_TARGETING",
                baseline_versions=("v1",),
                source_span_digests=span_digests,
            )
        )
    if "critique_ledger" not in v1 and "critique_ledger" not in v2:
        observations.append(
            _observation(
                category="CRITIQUE",
                code="V1_V2_NO_PREEXECUTION_CRITIQUE_LEDGER",
                baseline_versions=_BASELINE_VERSIONS,
                source_span_digests=span_digests,
            )
        )
    if "revision_ledger" not in v1 and "revision_ledger" not in v2:
        observations.append(
            _observation(
                category="REVISION",
                code="V1_V2_NO_OBSERVED_OUTCOME_REVISION_LEDGER",
                baseline_versions=_BASELINE_VERSIONS,
                source_span_digests=span_digests,
            )
        )
    observations.sort(key=lambda row: (str(row["category"]), str(row["code"])))
    priority_slice = _priority_slice(
        observations=observations,
        expected_relation=expected_relation,
    )
    return {
        "fixture_id": fixture_id,
        "fixture_input_digest": fixture_input_digest(case),
        "v1_capsule_digest": _digest(v1.get("capsule_digest"), label="v1 capsule"),
        "v2_capsule_digest": _digest(v2.get("capsule_digest"), label="v2 capsule"),
        "expected_atomic_requirement_count": expected_atoms,
        "expected_relation": expected_relation,
        "source_span_digests": span_digests,
        "observations": observations,
        "priority_failure_slice": priority_slice,
    }


def _dominant_failure_slice(
    cases: Sequence[Mapping[str, Any]],
) -> tuple[str, dict[str, int]]:
    counts = Counter(str(case.get("priority_failure_slice") or "") for case in cases)
    if not counts or any(slice_name not in _SLICE_PRIORITY for slice_name in counts):
        raise L1CognitiveBaselineError("baseline priority slices are invalid")
    priority_order = {
        slice_name: index for index, slice_name in enumerate(_SLICE_PRIORITY)
    }
    dominant = min(
        counts,
        key=lambda slice_name: (-counts[slice_name], priority_order[slice_name]),
    )
    return dominant, {slice_name: counts[slice_name] for slice_name in sorted(counts)}


def _receipt_body(corpus: Mapping[str, Any]) -> dict[str, Any]:
    cases = _sequence(corpus.get("cases"), label="development baseline cases")
    results = sorted(
        (
            _case_baseline(_mapping(case, label="development baseline case"))
            for case in cases
        ),
        key=lambda row: str(row["fixture_id"]),
    )
    fixture_ids = [str(row["fixture_id"]) for row in results]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise L1CognitiveBaselineError("development baseline fixture IDs are invalid")
    dominant, counts = _dominant_failure_slice(results)
    return {
        "schema_version": L1_COGNITIVE_DEVELOPMENT_BASELINE_SCHEMA_VERSION,
        "authority_class": "TECHNICAL_DEVELOPMENT_BASELINE_ONLY",
        "app_scope": _APP_SCOPE,
        "development_corpus_digest": _digest(
            corpus.get("corpus_source_digest"), label="development corpus digest"
        ),
        "baseline_versions": list(_BASELINE_VERSIONS),
        "cases": results,
        "summary": {
            "fixture_count": len(results),
            "baseline_runs_by_version": {"v1": len(results), "v2": len(results)},
            "priority_failure_slice_counts": counts,
            "dominant_failure_slice": dominant,
            "source_span_example_count": sum(
                len(row["source_span_digests"]) for row in results
            ),
        },
        "scoring_guide": {
            "source_span_examples_required": True,
            "structural_baseline_only": True,
            "human_semantic_qualification": "HUMAN_REVIEW_REQUIRED",
            "priority_selection": "COUNT_DESCENDING_THEN_DECLARED_COGNITIVE_RISK_ORDER",
        },
        "authority": {
            "technical_baseline": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
            "automatic_promotion": False,
        },
        "assertions": {
            "runs_v1_and_v2_once_per_frozen_fixture": True,
            "does_not_create_human_labels": True,
            "does_not_access_protected_holdout": True,
            "does_not_measure_candidate_quality": True,
        },
    }


def build_l1_cognitive_development_baseline_receipt(
    *, corpus: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Run the W0 v1/v2 development baseline and return its frozen receipt."""

    source = load_development_corpus() if corpus is None else dict(corpus)
    # The corpus loader validates the source digest and human-label boundary.
    if corpus is not None:
        source = load_development_corpus_from_mapping(source)
    receipt = _receipt_body(source)
    receipt["receipt_digest"] = development_baseline_digest(receipt)
    validate_l1_cognitive_development_baseline_receipt(receipt, corpus=source)
    return receipt


def load_development_corpus_from_mapping(corpus: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an in-memory development corpus through its tracked QA contract."""

    source = dict(corpus)
    try:
        validate_l1_cognitive_development_corpus(source)
    except ValueError as exc:
        raise L1CognitiveBaselineError("development corpus is invalid") from exc
    return source


def validate_l1_cognitive_development_baseline_receipt(
    receipt: Mapping[str, Any], *, corpus: Mapping[str, Any]
) -> None:
    """Fail closed unless a W0 baseline exactly re-derives from frozen inputs."""

    if not isinstance(receipt, Mapping):
        raise L1CognitiveBaselineError("development baseline receipt is invalid")
    if (
        receipt.get("schema_version")
        != L1_COGNITIVE_DEVELOPMENT_BASELINE_SCHEMA_VERSION
    ):
        raise L1CognitiveBaselineError("development baseline schema is invalid")
    if receipt.get("authority_class") != "TECHNICAL_DEVELOPMENT_BASELINE_ONLY":
        raise L1CognitiveBaselineError("development baseline authority is invalid")
    if receipt.get("app_scope") != _APP_SCOPE:
        raise L1CognitiveBaselineError("development baseline scope is invalid")
    if receipt.get("receipt_digest") != development_baseline_digest(receipt):
        raise L1CognitiveBaselineError("development baseline digest is invalid")
    source = load_development_corpus_from_mapping(corpus)
    expected = _receipt_body(source)
    actual = dict(receipt)
    actual.pop("receipt_digest", None)
    if actual != expected:
        raise L1CognitiveBaselineError(
            "development baseline receipt does not match its frozen sources"
        )


def write_l1_cognitive_development_baseline_receipt(
    *, output_path: Path, receipt: Mapping[str, Any], corpus: Mapping[str, Any]
) -> Path:
    """Validate and write a technical-only W0 baseline receipt."""

    validate_l1_cognitive_development_baseline_receipt(receipt, corpus=corpus)
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


__all__ = [
    "L1CognitiveBaselineError",
    "L1_COGNITIVE_DEVELOPMENT_BASELINE_SCHEMA_VERSION",
    "build_l1_cognitive_development_baseline_receipt",
    "development_baseline_digest",
    "load_development_corpus_from_mapping",
    "validate_l1_cognitive_development_baseline_receipt",
    "write_l1_cognitive_development_baseline_receipt",
]
