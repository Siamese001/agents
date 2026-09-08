"""Contract tests for the apps_rg-only L1 v2 decision-model capsule."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest

from apps_rg.runtime.bindings.l0_binding import l0_route_apps_rg
from apps_rg.runtime.bindings.l1_binding import l1_plan_apps_rg
from apps_rg.runtime.bindings.l1_planning_capsule import (
    build_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    L1PlanningV2IntegrityError,
    build_apps_rg_l1_planning_capsule_v2,
    stable_l1_v2_capsule_digest,
    verify_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.spine_contracts import ValidatedRequest


def _profile_manifest() -> dict[str, str]:
    return {
        "l1_planning_profile_ref": l1_planning_profile_ref(),
        "l1_planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
        "manifest_digest": "f" * 64,
    }


def _payload(
    jd_text: str = (
        "Responsibilities\n"
        "- Lead a multi-region AI platform organization.\n"
        "Requirements\n"
        "- Must have 10+ years of AI platform leadership.\n"
        "- Bachelor's degree in Computer Science."
    ),
) -> dict[str, Any]:
    return {
        "non_product_certified": True,
        "target_company": "Acme Corp",
        "target_role": "VP Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": jd_text,
        "source_resume_text": "Built governed AI infrastructure.",
        "generation_mode": "strategic_tailor",
        "task_spec": {
            "generation_mode": "strategic_tailor",
            "task_class": "resume_generation",
        },
        "query_spec": {
            "jd_hash": "a" * 64,
            "resume_hash": "b" * 64,
        },
        "support_expectation": {},
        "output_expectation": {},
        "profile_manifest": _profile_manifest(),
    }


def _v2(jd_text: str | None = None) -> Mapping[str, Any]:
    return build_apps_rg_l1_planning_capsule_v2(
        app_payload=_payload() if jd_text is None else _payload(jd_text),
        request_id="req-l1-v2",
        run_id="run-l1-v2",
        trace_id="trace-l1-v2",
        replay_key="replay-l1-v2",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _digest(value: Mapping[str, Any], digest_field: str) -> str:
    body = dict(value)
    body.pop(digest_field, None)
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _refresh_capsule(capsule: dict[str, Any]) -> None:
    capsule["decision_ledger"]["ledger_digest"] = _digest(
        capsule["decision_ledger"], "ledger_digest"
    )
    capsule["evidence_obligation_ledger"]["ledger_digest"] = _digest(
        capsule["evidence_obligation_ledger"], "ledger_digest"
    )
    capsule["work_dag"]["dag_digest"] = _digest(capsule["work_dag"], "dag_digest")
    capsule["capsule_digest"] = stable_l1_v2_capsule_digest(capsule)


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        keys = set(value)
        for item in value.values():
            keys.update(_walk_keys(item))
        return keys
    if isinstance(value, (list, tuple)):
        keys: set[str] = set()
        for item in value:
            keys.update(_walk_keys(item))
        return keys
    return set()


def test_v2_is_byte_stable_span_bound_and_keeps_raw_jd_out_of_the_capsule() -> None:
    first = _v2()
    second = _v2()

    assert first == second
    assert first["schema_version"] == "apps_rg_l1_planning_capsule.v2"
    assert first["capsule_digest"] == second["capsule_digest"]
    assert first["source_binding"]["source_class"] == "U0_VALIDATED_JD_PAYLOAD"
    assert first["requirements"]
    assert all(
        "obligation_text" not in requirement for requirement in first["requirements"]
    )
    for requirement in first["requirements"]:
        span = requirement["source_span"]
        assert span["source_field"] == "job_description_text"
        assert span["start_offset"] <= span["end_offset"]
        assert span["text_digest"].startswith("sha256:")
        assert span["span_digest"].startswith("sha256:")
    serialized = json.dumps(first, sort_keys=True)
    assert "Bachelor's degree in Computer Science" not in serialized
    verify_apps_rg_l1_planning_capsule_v2(first)
    merge_edges = [
        edge
        for edge in first["work_dag"]["edges"]
        if edge["relation"] == "MERGE_AFTER"
    ]
    assert {"node_id": "merge:final_resume", "node_type": "MERGE"} in first[
        "work_dag"
    ]["nodes"]
    assert len(merge_edges) == len(first["work_unit_ids"])
    assert {edge["to"] for edge in merge_edges} == {"merge:final_resume"}


def test_v2_escalates_critical_compound_and_unknown_requirements() -> None:
    capsule = _v2(
        "Requirements\n"
        "- Must lead AI platform strategy and own quantum-superiority governance.\n"
        "- Quantum-superiority governance."
    )
    requirements = capsule["requirements"]

    compound = requirements[0]
    unknown = requirements[1]
    assert compound["compound"] is True
    assert compound["criticality"] == "CRITICAL"
    assert compound["coverage_status"] == "ESCALATED"
    assert compound["target_unit_ids"] == []
    assert unknown["requirement_type"] == "UNKNOWN"
    assert unknown["coverage_status"] == "ESCALATED"
    decision_codes = {
        decision["code"] for decision in capsule["decision_ledger"]["decisions"]
    }
    assert {
        "COMPOUND_REQUIREMENT",
        "UNKNOWN_REQUIREMENT_TYPE",
        "CRITICAL_TARGETING_ESCALATION",
    }.issubset(decision_codes)
    assert capsule["evidence_obligation_ledger"]["obligations"] == []


def test_v2_detects_duplicate_requirements_without_silently_deduplicating() -> None:
    capsule = _v2(
        "Requirements\n"
        "- Must have 8 years of platform leadership.\n"
        "- Must have 8 years of platform leadership."
    )

    assert len(capsule["requirements"]) == 2
    assert len({row["requirement_id"] for row in capsule["requirements"]}) == 2
    duplicate_decisions = [
        row
        for row in capsule["decision_ledger"]["decisions"]
        if row["code"] == "DUPLICATE_REQUIREMENT"
    ]
    assert len(duplicate_decisions) == 1
    assert len(duplicate_decisions[0]["affected_requirement_ids"]) == 2
    verify_apps_rg_l1_planning_capsule_v2(capsule)


def test_v2_validator_rejects_invalid_and_orphaned_work_graphs() -> None:
    cyclic = _thaw(_v2())
    mapped_target = next(
        requirement["target_unit_ids"][0]
        for requirement in cyclic["requirements"]
        if requirement["coverage_status"] == "MAPPED"
    )
    cyclic["work_dag"]["edges"].append(
        {
            "from": f"validation:{mapped_target}",
            "to": "u0:validated_jd",
            "relation": "INVALID_CYCLE",
        }
    )
    _refresh_capsule(cyclic)
    with pytest.raises(L1PlanningV2IntegrityError, match="edge is invalid"):
        verify_apps_rg_l1_planning_capsule_v2(cyclic)

    orphaned = _thaw(_v2())
    orphaned["work_dag"]["nodes"].append(
        {"node_id": "unit:orphaned", "node_type": "WORK_UNIT"}
    )
    _refresh_capsule(orphaned)
    with pytest.raises(L1PlanningV2IntegrityError, match="orphaned"):
        verify_apps_rg_l1_planning_capsule_v2(orphaned)


def test_v2_validator_rejects_rewired_merge_after_edge() -> None:
    rewired = _thaw(_v2())
    merge_edge = next(
        edge
        for edge in rewired["work_dag"]["edges"]
        if edge["relation"] == "MERGE_AFTER"
    )
    merge_edge["from"] = "u0:validated_resume"
    _refresh_capsule(rewired)

    with pytest.raises(L1PlanningV2IntegrityError, match="edge is invalid"):
        verify_apps_rg_l1_planning_capsule_v2(rewired)


def test_v2_is_parallel_to_v1_and_l0_signs_only_advisory_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_payload = _payload()
    v1 = build_apps_rg_l1_planning_capsule(
        app_payload=app_payload,
        request_id="req-l1-v2",
        run_id="run-l1-v2",
        trace_id="trace-l1-v2",
        replay_key="replay-l1-v2",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )
    assert v1["schema_version"] == "apps_rg_l1_planning_capsule.v1"
    assert "decision_ledger" not in v1

    validated = ValidatedRequest(
        request_id="req-l1-v2-binding",
        run_id="run-l1-v2-binding",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-08-10T00:00:00+00:00"
        ),
        trace_id="trace-l1-v2-binding",
        tenant_id="tenant-l1-v2",
        replay_key="replay-l1-v2-binding",
        l5_certification_ref="test:valid:w6",
        app_payload=app_payload,
    )
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "l1-v2-test-secret")
    plan = l1_plan_apps_rg(validated)
    v2 = plan.task_spec["apps_rg_planning_v2_capsule"]
    route = l0_route_apps_rg(plan)

    assert (
        plan.task_spec["apps_rg_planning_capsule"]["schema_version"]
        == "apps_rg_l1_planning_capsule.v1"
    )
    assert v2["schema_version"] == "apps_rg_l1_planning_capsule.v2"
    assert (
        plan.support_expectation["apps_rg_v2_evidence_obligation_ledger_ref"]
        == v2["evidence_obligation_ledger"]["ledger_digest"]
    )
    assert (
        plan.output_expectation["apps_rg_v2_work_dag_ref"]
        == v2["work_dag"]["dag_digest"]
    )
    assert any(ref.startswith("l1_v2_capsule_digest:") for ref in route.reason_codes)
    assert any(
        ref.startswith("l1_v2_evidence_obligation_ledger:")
        for ref in route.reason_codes
    )
    assert any(ref.startswith("l1_v2_work_dag:") for ref in route.snapshot_refs)
    assert "route_id" not in _walk_keys(v2)
    assert "evidence_items" not in _walk_keys(v2)
    assert v2["validation"]["no_candidate_evidence_claim"] is True

    reference_only_payload = _payload("")
    reference_only_payload["job_description_ref"] = "artifacts/run/job_description.txt"
    reference_only = ValidatedRequest(
        request_id="req-l1-v2-reference-only",
        run_id="run-l1-v2-reference-only",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-08-10T00:00:00+00:00"
        ),
        trace_id="trace-l1-v2-reference-only",
        tenant_id="tenant-l1-v2",
        replay_key="replay-l1-v2-reference-only",
        l5_certification_ref="test:valid:w6",
        app_payload=reference_only_payload,
    )
    reference_plan = l1_plan_apps_rg(reference_only)
    reference_route = l0_route_apps_rg(reference_plan)

    assert (
        reference_plan.task_spec["apps_rg_planning_capsule"]["planning_status"]
        == "READY"
    )
    assert (
        reference_plan.task_spec["apps_rg_planning_v2_capsule"]["planning_status"]
        == "BLOCKED"
    )
    assert reference_route.route_digest
    assert "l1_v2_planning_status:BLOCKED" in reference_route.reason_codes
