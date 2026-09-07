"""Contract tests for W3 JD-specific L1 obligation planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.bindings.l1_planning_capsule import (
    PlanningCapsuleIntegrityError,
    build_apps_rg_l1_planning_capsule,
    stable_capsule_digest,
    verify_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)


REPO_ROOT = Path(__file__).resolve().parents[5]


def _payload(jd_text: str) -> dict[str, Any]:
    return {
        "target_company": "Anthropic",
        "target_role": "Manager of Applied AI Architecture, Partnerships",
        "target_level": "MANAGER",
        "job_description_text": jd_text,
        "source_resume_text": "Built partner architecture teams and AI platforms.",
        "generation_mode": "strategic_tailor",
        "task_spec": {"generation_mode": "strategic_tailor"},
        "query_spec": {
            "jd_hash": "a" * 64,
            "resume_hash": "b" * 64,
            "target": {
                "company": "Anthropic",
                "role": "Manager of Applied AI Architecture, Partnerships",
                "level": "MANAGER",
            },
        },
    }


def _capsule(jd_text: str) -> Any:
    return build_apps_rg_l1_planning_capsule(
        app_payload=_payload(jd_text),
        request_id="req-w3",
        run_id="run-w3",
        trace_id="trace-w3",
        replay_key="replay-w3",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def test_w3_extracts_fixture_obligations_and_binds_each_section_plan() -> None:
    fixture = REPO_ROOT / "src/apps_rg/config/targeting/jd_anthropic_partnerships_2026.json"
    jd_text = json.loads(fixture.read_text(encoding="utf-8"))["jd_text"]

    capsule = _capsule(jd_text)
    obligation_plan = capsule["jd_obligation_plan"]
    obligations = obligation_plan["obligations"]

    assert obligation_plan["schema_version"] == "apps_rg.jd_obligation_plan.v1"
    assert obligation_plan["source_binding"]["source_class"] == "U0_VALIDATED_JD_PAYLOAD"
    assert obligation_plan["source_binding"]["jd_hash"] == "a" * 64
    assert obligation_plan["validation"] == {
        "jd_is_targeting_input_not_candidate_evidence": True,
        "no_evidence_retrieval": True,
        "no_claim_generation": True,
        "no_execution_path_selection": True,
    }
    assert obligation_plan["coverage"]["critical_count"] > 0
    assert obligation_plan["coverage"]["all_critical_obligations_resolved"] is True

    leadership = next(
        obligation
        for obligation in obligations
        if obligation["obligation_text"].startswith("Team Leadership & Development")
    )
    assert leadership["coverage_status"] == "MAPPED"
    assert {"executive_summary", "experience_block"}.issubset(
        leadership["mapped_unit_ids"]
    )

    expected_by_unit = {
        unit["unit_id"]: set() for unit in capsule["work_units"]
    }
    for obligation in obligations:
        for unit_id in obligation["mapped_unit_ids"]:
            expected_by_unit[unit_id].add(obligation["obligation_id"])
    actual_by_unit = {
        row["unit_id"]: set(row["jd_obligation_ids"])
        for row in capsule["evidence_plan"]
    }
    assert actual_by_unit == expected_by_unit
    assert all(row["jd_obligation_targeting_only"] is True for row in capsule["evidence_plan"])


def test_w3_escalates_unmappable_critical_obligation_without_inventing_evidence() -> None:
    capsule = _capsule("Requirements\n- Must demonstrate quantum-superiority governance.")
    obligation = capsule["jd_obligation_plan"]["obligations"][0]

    assert obligation["criticality"] == "CRITICAL"
    assert obligation["mapped_unit_ids"] == []
    assert obligation["coverage_status"] == "ESCALATED"
    assert obligation["escalation_reason"] == "HITL_OR_UPSTREAM_EVIDENCE_REVIEW_REQUIRED"
    assert capsule["jd_obligation_plan"]["coverage"] == {
        "obligation_count": 1,
        "critical_count": 1,
        "critical_mapped_count": 0,
        "critical_escalated_count": 1,
        "all_critical_obligations_resolved": True,
    }


def test_w3_rejects_recomputed_capsule_with_unresolved_critical_obligation() -> None:
    capsule = _thaw(
        _capsule("Requirements\n- Must demonstrate quantum-superiority governance.")
    )
    obligation_plan = capsule["jd_obligation_plan"]
    obligation_plan["obligations"][0]["coverage_status"] = "UNMAPPED"
    obligation_plan["obligations"][0]["escalation_reason"] = ""
    obligation_plan["coverage"] = {
        "obligation_count": 1,
        "critical_count": 0,
        "critical_mapped_count": 0,
        "critical_escalated_count": 0,
        "all_critical_obligations_resolved": True,
    }
    from apps_rg.runtime.bindings.l1_planning_capsule import _stable_jd_obligation_plan_digest

    obligation_plan["obligation_plan_digest"] = _stable_jd_obligation_plan_digest(
        obligation_plan
    )
    capsule["capsule_digest"] = stable_capsule_digest(capsule)

    with pytest.raises(
        PlanningCapsuleIntegrityError,
        match="critical jd obligation must be mapped or escalated",
    ):
        verify_apps_rg_l1_planning_capsule(capsule)
