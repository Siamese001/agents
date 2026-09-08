from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.bindings.l1_planning_capsule import (
    build_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.failure_aware_replan import (
    build_failure_aware_replan,
)
from apps_rg.runtime.contracts.l1_reasoning_baseline import (
    L1_REASONING_BASELINE_APP_SCOPE,
    L1_REASONING_BASELINE_AUTHORITY,
    L1_REASONING_BASELINE_SCHEMA_VERSION,
    L1ReasoningBaselineError,
    baseline_digest,
    build_l1_reasoning_baseline,
    compare_l1_reasoning_baseline,
    emit_l1_reasoning_baseline,
    validate_l1_reasoning_baseline,
)
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    build_plan_execution_reconciliation,
)
from apps_rg.runtime.dispatch.spine_stage_receipts import (
    FILENAME_L1_REASONING_BASELINE,
)


_LANES = (
    "headline",
    "executive_summary",
    "competencies",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "ey_bullets",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
    "ey_narrative",
)
_FROZEN_W0_BASELINE_DIGEST = (
    "sha256:6345bcf3569b8502ce51ccdc94ca2e49f385bc4192bf27f8a6cc58cec4c78016"
)


def _capsule() -> dict[str, Any]:
    return build_apps_rg_l1_planning_capsule(
        app_payload={
            "generation_mode": "strategic_tailor",
            "target_company": "ExampleCo",
            "target_role": "VP Partnerships",
            "target_level": "VP",
            "source_resume_text": "Led partner programs and applied AI delivery.",
            "job_description_text": (
                "Responsibilities\n"
                "- Lead partner strategy and revenue programs.\n"
                "Requirements\n"
                "- Must demonstrate ten years of enterprise leadership.\n"
                "- Must demonstrate quantum-superiority governance."
            ),
        },
        request_id="w0-baseline-request",
        run_id="w0-baseline-run",
        trace_id="w0-baseline-trace",
        replay_key="w0-baseline-replay",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def _w1_w2(
    tmp_path: Path, capsule: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    lane_refs: dict[str, str] = {}
    for lane in _LANES:
        ref = f"modular_r4/sections/{lane}/l2_output.json"
        _write(tmp_path / ref)
        lane_refs[lane] = ref
    _write(tmp_path / "modular_r4/locked_copy/locked_copy_manifest.json")
    _write(tmp_path / "modular_r4/section_provider_calls.json")
    _write(tmp_path / "runtime_execution_witness.json")

    w1 = build_plan_execution_reconciliation(
        request_id=str(capsule["request_id"]),
        run_id=str(capsule["run_id"]),
        plan_capsule=capsule,
        artifact_dir=tmp_path,
        execution_witness={"l2": {"executed": True, "fault": ""}},
        l2_result={"section_output_refs": lane_refs},
    )
    w2 = build_failure_aware_replan(
        plan_capsule=capsule,
        parent_plan_ref="l1_planning_capsule.json",
        plan_execution_receipt=w1,
        trigger_receipt_ref="plan_execution_receipt.json",
    )
    return w1, w2


def _baseline(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    capsule = _capsule()
    w1, w2 = _w1_w2(tmp_path, capsule)
    baseline = build_l1_reasoning_baseline(
        baseline_id="w0-strategic-tailor-v1",
        capsule=capsule,
        route={
            "request_id": "w0-baseline-request",
            "run_id": "w0-baseline-run",
            "trace_id": "w0-baseline-trace",
            "route_id": "R4_FULL",
            "route_family": "FULL",
            "execution_form": "MANAGED",
            "route_digest": "route-digest",
            "route_gate_receipts": [
                {"gate_id": "G_L1_PLAN_READY", "verdict": "PASS", "score": 1.0}
            ],
        },
        final_evidence_contract={
            "request_id": "w0-baseline-request",
            "run_id": "w0-baseline-run",
            "trace_id": "w0-baseline-trace",
            "support_status": "PASS",
            "support_target_met": True,
            "final_evidence_digest": "fec-digest",
            "retrieval_plan_ref": "l1_evidence_plan:test",
            "audit_refs": ["l1_capsule_digest:test"],
            "evidence_items": [{"evidence_id": "fixture-evidence"}],
        },
        prompt_artifact={
            "request_id": "w0-baseline-request",
            "run_id": "w0-baseline-run",
            "trace_id": "w0-baseline-trace",
            "component_hash_map": {"l1_planning_capsule": "component-digest"},
            "slot_lineage_map": {"l1_planning_capsule": "L1_PLAN_PROJECTIONS"},
            "compiled_prompt_digest": "prompt-digest",
        },
        l2_receipts=[
            {
                "lane_id": "executive_summary",
                "status": "COMPLETED",
                "artifact_ref": "modular_r4/sections/executive_summary/l2_output.json",
                "reasoning_execution_receipt_ref": (
                    "modular_r4/sections/executive_summary/reasoning_receipt.json"
                ),
                "reasoning_execution_receipt": {"aggregate_blocked": False},
            }
        ],
        plan_execution_receipt=w1,
        replan_decision=w2,
    )
    return capsule, baseline


def test_w0_baseline_captures_all_existing_stage_observations(
    tmp_path: Path,
) -> None:
    capsule, baseline = _baseline(tmp_path)

    assert baseline["schema_version"] == L1_REASONING_BASELINE_SCHEMA_VERSION
    assert baseline["authority_class"] == L1_REASONING_BASELINE_AUTHORITY
    assert baseline["app_scope"] == L1_REASONING_BASELINE_APP_SCOPE
    assert baseline["baseline_digest"] == _FROZEN_W0_BASELINE_DIGEST
    assert baseline["stage_presence"] == {
        "l0": True,
        "c0": True,
        "pa": True,
        "l2": True,
        "w1": True,
        "w2": True,
    }
    assert baseline["plan"]["capsule_digest"] == capsule["capsule_digest"]
    assert (
        baseline["stage_observations"]["w1"]["summary"]["all_planned_units_reconciled"]
        is True
    )
    assert baseline["stage_observations"]["w2"]["replan_status"] == (
        "REPLAN_PROPOSED"
    )
    validate_l1_reasoning_baseline(baseline)
    compare_l1_reasoning_baseline(baseline, capsule=capsule)


def test_w0_baseline_does_not_persist_raw_jd_or_resume_text(tmp_path: Path) -> None:
    _capsule_value, baseline = _baseline(tmp_path)
    encoded = json.dumps(baseline, ensure_ascii=False)

    assert "quantum-superiority governance" not in encoded
    assert "Led partner programs and applied AI delivery." not in encoded
    obligation = baseline["plan"]["jd_obligation_plan"]["obligations"][-1]
    assert obligation["obligation_text_digest"].startswith("sha256:")


def test_w0_baseline_detects_current_plan_semantic_drift(tmp_path: Path) -> None:
    capsule, baseline = _baseline(tmp_path)
    tampered = copy.deepcopy(baseline)
    tampered["plan"]["cognition_plan"][0]["tier"] = "T9_INVALID"
    tampered["baseline_digest"] = baseline_digest(tampered)

    validate_l1_reasoning_baseline(tampered)
    with pytest.raises(
        L1ReasoningBaselineError,
        match="current L1 planning semantics differ",
    ):
        compare_l1_reasoning_baseline(tampered, capsule=capsule)


def test_w0_baseline_rejects_w1_receipt_for_another_plan(tmp_path: Path) -> None:
    capsule = _capsule()
    other = build_apps_rg_l1_planning_capsule(
        app_payload={
            "generation_mode": "strategic_tailor",
            "target_company": "OtherCo",
            "target_role": "VP Partnerships",
            "target_level": "VP",
            "source_resume_text": "Evidence-backed experience.",
            "job_description_text": "Requirements\n- Must demonstrate leadership.",
        },
        request_id="other-request",
        run_id="other-run",
        trace_id="other-trace",
        replay_key="other-replay",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )
    w1, _w2 = _w1_w2(tmp_path, other)

    with pytest.raises(L1ReasoningBaselineError, match="w1.request_id"):
        build_l1_reasoning_baseline(
            baseline_id="wrong-w1",
            capsule=capsule,
            plan_execution_receipt=w1,
        )


def test_w0_baseline_writes_the_canonical_stage_artifact(tmp_path: Path) -> None:
    _capsule_value, baseline = _baseline(tmp_path)

    path = emit_l1_reasoning_baseline(artifact_dir=tmp_path / "run", baseline=baseline)

    assert path == tmp_path / "run" / FILENAME_L1_REASONING_BASELINE
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted == baseline
    validate_l1_reasoning_baseline(persisted)


def test_w0_baseline_rejects_absolute_l2_artifact_reference(tmp_path: Path) -> None:
    capsule = _capsule()

    with pytest.raises(L1ReasoningBaselineError, match="relative artifact"):
        build_l1_reasoning_baseline(
            baseline_id="absolute-ref",
            capsule=capsule,
            l2_receipts=[
                {
                    "lane_id": "headline",
                    "artifact_ref": str(tmp_path / "outside.json"),
                }
            ],
        )
