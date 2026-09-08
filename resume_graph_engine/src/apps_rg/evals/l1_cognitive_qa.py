"""Technical QA for the L1 v3 cognitive-plan capability contract.

This verifies deterministic, source-bound development behavior only.  It never
creates human semantic labels and always records that protected-holdout and
human qualification remain required.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import (
    L1CognitivePlanError,
    build_l1_cognitive_plan_v3,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)


L1_COGNITIVE_QA_DEVELOPMENT_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_qa_development.v1"
)
L1_COGNITIVE_QA_RECEIPT_SCHEMA_VERSION: Final[str] = "apps_rg.l1_cognitive_qa.v1"
_FIXTURE_PATH: Final[Path] = (
    Path(__file__).resolve().parent / "fixtures" / "l1_cognitive_qa_development.v1.json"
)


class L1CognitiveQaError(ValueError):
    """Raised when technical cognitive QA input or output is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def _required_string(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1CognitiveQaError(f"{field} is required")
    return normalized


def _fixture_input(case: Mapping[str, Any]) -> dict[str, Any]:
    payload = case.get("app_payload")
    expectations = case.get("expectations")
    if not isinstance(payload, Mapping) or not isinstance(expectations, Mapping):
        raise L1CognitiveQaError("QA fixture case is invalid")
    return {
        "fixture_id": _required_string(case.get("fixture_id"), field="fixture_id"),
        "app_payload": copy.deepcopy(dict(payload)),
        "expectations": copy.deepcopy(dict(expectations)),
    }


def fixture_input_digest(case: Mapping[str, Any]) -> str:
    """Return the source-bound QA fixture input digest."""

    return _sha256(_fixture_input(case))


def development_fixture_path() -> Path:
    """Return the tracked technical QA fixture path."""

    return _FIXTURE_PATH


def _validate_corpus(corpus: Mapping[str, Any]) -> None:
    if corpus.get("schema_version") != L1_COGNITIVE_QA_DEVELOPMENT_SCHEMA_VERSION:
        raise L1CognitiveQaError("QA corpus schema_version is invalid")
    if corpus.get("app_scope") != "APPS_RG_V2_ONLY":
        raise L1CognitiveQaError("QA corpus app scope is invalid")
    if corpus.get("human_semantic_qualification") != "HUMAN_REVIEW_REQUIRED":
        raise L1CognitiveQaError("QA corpus human authority boundary is invalid")
    cases = corpus.get("cases")
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not cases:
        raise L1CognitiveQaError("QA corpus cases are invalid")
    identifiers: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise L1CognitiveQaError("QA corpus case is invalid")
        fixture_id = _required_string(case.get("fixture_id"), field="fixture_id")
        if fixture_id in identifiers:
            raise L1CognitiveQaError("QA fixture IDs must be unique")
        identifiers.add(fixture_id)
        if case.get("source_input_digest") != fixture_input_digest(case):
            raise L1CognitiveQaError("QA fixture source digest mismatch")
        if any(key in case for key in ("human_grade", "human_label", "adjudication")):
            raise L1CognitiveQaError("QA corpus cannot prefill human judgment")
    body = dict(corpus)
    body.pop("corpus_source_digest", None)
    if corpus.get("corpus_source_digest") != _sha256(body):
        raise L1CognitiveQaError("QA corpus digest mismatch")


def load_development_corpus(path: Path | None = None) -> dict[str, Any]:
    """Load the frozen technical QA development corpus."""

    source = Path(path or _FIXTURE_PATH)
    try:
        corpus = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1CognitiveQaError("QA corpus is unreadable") from exc
    if not isinstance(corpus, Mapping):
        raise L1CognitiveQaError("QA corpus must decode to a mapping")
    value = dict(corpus)
    _validate_corpus(value)
    return value


def validate_l1_cognitive_development_corpus(corpus: Mapping[str, Any]) -> None:
    """Validate an in-memory development corpus without creating a fixture file."""

    _validate_corpus(corpus)


def _case_result(case: Mapping[str, Any]) -> dict[str, Any]:
    fixture = _fixture_input(case)
    fixture_id = str(fixture["fixture_id"])
    try:
        plan = build_l1_cognitive_plan_v3(
            app_payload=fixture["app_payload"],
            request_id=f"qa-{fixture_id}",
            run_id=f"qa-{fixture_id}",
            trace_id=f"qa-{fixture_id}",
            replay_key=f"qa-{fixture_id}",
            planning_profile_ref=l1_planning_profile_ref(),
            planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
        )
    except L1CognitivePlanError as exc:
        raise L1CognitiveQaError("QA cognitive plan is invalid") from exc
    graph = plan["atomic_requirement_graph"]
    expectations = fixture["expectations"]
    requirements = list(graph["requirements"])
    relations = list(graph["relations"])
    critique_codes = {
        str(row.get("code") or "") for row in plan["critique_ledger"]["findings"]
    }
    checks = {
        "minimum_atomic_requirement_count": len(requirements)
        >= int(expectations.get("minimum_atomic_requirement_count") or 0),
        "required_relation": (
            not expectations.get("required_relation")
            or str(expectations["required_relation"])
            in {str(row.get("relation") or "") for row in relations}
        ),
        "required_requirement_type": (
            not expectations.get("required_requirement_type")
            or str(expectations["required_requirement_type"])
            in {str(row.get("requirement_type") or "") for row in requirements}
        ),
        "required_critique_code": (
            not expectations.get("required_critique_code")
            or str(expectations["required_critique_code"]) in critique_codes
        ),
        "required_planning_status": plan["planning_status"]
        == str(expectations.get("required_planning_status") or ""),
    }
    return {
        "fixture_id": fixture_id,
        "fixture_input_digest": fixture_input_digest(case),
        "atomic_requirement_count": len(requirements),
        "relation_types": sorted({str(row.get("relation") or "") for row in relations}),
        "requirement_types": sorted(
            {str(row.get("requirement_type") or "") for row in requirements}
        ),
        "planning_status": str(plan["planning_status"]),
        "critique_codes": sorted(critique_codes),
        "checks": checks,
        "passed": all(checks.values()),
    }


def run_l1_cognitive_technical_qa(
    corpus: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run source-bound technical QA without claiming semantic qualification."""

    source = load_development_corpus() if corpus is None else dict(corpus)
    _validate_corpus(source)
    results = sorted(
        (_case_result(case) for case in source["cases"] if isinstance(case, Mapping)),
        key=lambda row: str(row["fixture_id"]),
    )
    receipt = {
        "schema_version": L1_COGNITIVE_QA_RECEIPT_SCHEMA_VERSION,
        "authority_class": "TECHNICAL_QA_ONLY",
        "app_scope": "APPS_RG_V2_ONLY",
        "development_corpus_digest": str(source["corpus_source_digest"]),
        "results": results,
        "technical_status": "PASS" if all(row["passed"] for row in results) else "FAIL",
        "semantic_qualification_status": "HUMAN_REVIEW_REQUIRED",
        "promotion_authorized": False,
        "assertions": {
            "does_not_create_human_labels": True,
            "does_not_access_protected_holdout": True,
            "does_not_authorize_product_promotion": True,
        },
    }
    receipt["receipt_digest"] = _sha256(receipt)
    return receipt


__all__ = [
    "L1CognitiveQaError",
    "development_fixture_path",
    "fixture_input_digest",
    "load_development_corpus",
    "run_l1_cognitive_technical_qa",
    "validate_l1_cognitive_development_corpus",
]
