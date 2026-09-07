"""C0-to-L1 v3 outcome and bounded-revision contract tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import build_l1_cognitive_plan_v3
from apps_rg.runtime.bindings.l1_binding import l1_plan_apps_rg
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V3_CANDIDATE_ARM,
    build_l1_cognitive_treatment,
)
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import build_apps_rg_l1_planning_capsule_v2
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.l1_cognitive_c0_outcome_receipt import (
    L1CognitiveC0OutcomeError,
    build_l1_cognitive_c0_outcome_receipt,
    build_l1_cognitive_revision_from_c0_outcome,
    cognitive_c0_outcome_digest,
    validate_l1_cognitive_c0_outcome_receipt,
    write_l1_cognitive_c0_outcome_receipt,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    build_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr
from apps_rg.runtime.spine_contracts import ValidatedRequest


def _payload() -> dict[str, Any]:
    return {
        "non_product_certified": True,
        "target_company": "Acme Corp",
        "target_role": "VP Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": (
            "Requirements\n"
            "- Must have 10+ years of AI platform leadership.\n"
            "- Bachelor's degree in Computer Science."
        ),
        "source_resume_text": "Built governed AI infrastructure.",
        "generation_mode": "strategic_tailor",
        "task_spec": {
            "generation_mode": "strategic_tailor",
            "task_class": "resume_generation",
        },
        "query_spec": {"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        "support_expectation": {},
        "output_expectation": {},
        "profile_manifest": {
            "l1_planning_profile_ref": l1_planning_profile_ref(),
            "l1_planning_profile_digest": l1_planning_profile_digest(
                allow_missing=False
            ),
            "manifest_digest": "f" * 64,
        },
    }


def _candidate_payload() -> dict[str, Any]:
    payload = _payload()
    payload["task_spec"]["l1_cognitive_treatment"] = build_l1_cognitive_treatment(
        L1_COGNITIVE_V3_CANDIDATE_ARM,
        assignment_origin="U0_VALIDATED_INGRESS",
    )
    return payload


def _plans() -> tuple[dict[str, Any], dict[str, Any]]:
    kwargs = {
        "app_payload": _payload(),
        "request_id": "cognitive-outcome-request",
        "run_id": "cognitive-outcome-run",
        "trace_id": "cognitive-outcome-trace",
        "replay_key": "cognitive-outcome-replay",
        "planning_profile_ref": l1_planning_profile_ref(),
        "planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
    }
    return (
        dict(build_l1_cognitive_plan_v3(**kwargs)),
        dict(build_apps_rg_l1_planning_capsule_v2(**kwargs)),
    )


def _receipt(*, contradiction: bool) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cognitive, v2 = _plans()
    obligations = list(v2["evidence_obligation_ledger"]["obligations"])
    assert len(obligations) >= 2
    evidence: list[dict[str, Any]] = [
        {
            "source": "fact_vectors",
            "source_type": "fact_vectors",
            "content_digest": "sha256:" + "1" * 64,
            "l1_obligation_ids": [obligations[0]["obligation_id"]],
            "l1_obligation_disposition": "SUPPORTED",
        }
    ]
    if contradiction:
        evidence.append(
            {
                "source": "fact_vectors",
                "source_type": "fact_vectors",
                "content_digest": "sha256:" + "2" * 64,
                "l1_obligation_ids": [obligations[1]["obligation_id"]],
                "contradiction_status": "CONTRADICTED",
            }
        )
    c0 = build_l1_evidence_obligation_receipt(
        capsule=v2,
        request_id="cognitive-outcome-request",
        run_id="cognitive-outcome-run",
        trace_id="cognitive-outcome-trace",
        final_evidence_digest="sha256:" + "c" * 64,
        evidence_items=evidence,
    )
    return cognitive, v2, c0


def test_c0_outcomes_cover_every_atomic_requirement_and_bound_revision() -> None:
    cognitive, v2, c0 = _receipt(contradiction=True)
    outcome = build_l1_cognitive_c0_outcome_receipt(
        cognitive_plan=cognitive,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )

    assert outcome["summary"]["all_requirements_observed_or_escalated"] is True
    assert outcome["summary"]["c0_remains_evidence_authority"] is True
    assert outcome["summary"]["revision_eligible_count"] >= 1
    assert any(
        row["outcome"] == "C0_CONTRADICTED"
        for row in outcome["requirement_outcomes"]
    )
    revision = build_l1_cognitive_revision_from_c0_outcome(
        cognitive_plan=cognitive,
        outcome_receipt=outcome,
        outcome_receipt_ref="l1_cognitive_c0_outcome_receipt.json",
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )
    assert revision["status"] == "PROPOSED"
    assert revision["c0_outcome_receipt_digest"] == outcome["receipt_digest"]
    assert revision["assertions"]["does_not_execute"] is True
    assert all(change["automatic_retry"] is False for change in revision["changes"])


def test_unbound_atomic_parent_becomes_explicit_c0_insufficiency_not_a_crash() -> None:
    payload = _payload()
    payload["job_description_text"] = (
        "Requirements\n- Must lead AI strategy and own platform governance."
    )
    kwargs = {
        "app_payload": payload,
        "request_id": "cognitive-unbound-request",
        "run_id": "cognitive-unbound-run",
        "trace_id": "cognitive-unbound-trace",
        "replay_key": "cognitive-unbound-replay",
        "planning_profile_ref": l1_planning_profile_ref(),
        "planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
    }
    cognitive = dict(build_l1_cognitive_plan_v3(**kwargs))
    v2 = dict(build_apps_rg_l1_planning_capsule_v2(**kwargs))
    assert v2["evidence_obligation_ledger"]["obligations"] == []
    assert all(
        row["parent_c0_obligation_eligible"] is False
        for row in cognitive["atomic_requirement_graph"]["requirements"]
    )
    c0 = build_l1_evidence_obligation_receipt(
        capsule=v2,
        request_id=kwargs["request_id"],
        run_id=kwargs["run_id"],
        trace_id=kwargs["trace_id"],
        final_evidence_digest="sha256:" + "d" * 64,
        evidence_items=(),
    )

    outcome = build_l1_cognitive_c0_outcome_receipt(
        cognitive_plan=cognitive,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )

    assert {row["outcome"] for row in outcome["requirement_outcomes"]} == {
        "C0_INSUFFICIENT"
    }
    assert {
        row["reason_code"] for row in outcome["requirement_outcomes"]
    } == {"C0_PARENT_OBLIGATION_MISSING"}
    assert all(not row["c0_obligation_ids"] for row in outcome["requirement_outcomes"])
    revision = build_l1_cognitive_revision_from_c0_outcome(
        cognitive_plan=cognitive,
        outcome_receipt=outcome,
        outcome_receipt_ref=sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )
    assert revision["status"] == "PROPOSED"


def test_outcome_rejects_redigested_tampering_and_writes_verified_receipt(
    tmp_path: Path,
) -> None:
    cognitive, v2, c0 = _receipt(contradiction=False)
    outcome = build_l1_cognitive_c0_outcome_receipt(
        cognitive_plan=cognitive,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )
    path = write_l1_cognitive_c0_outcome_receipt(
        output_path=tmp_path / "l1_cognitive_c0_outcome_receipt.json",
        receipt=outcome,
        cognitive_plan=cognitive,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )
    assert json.loads(path.read_text(encoding="utf-8")) == outcome
    validate_l1_cognitive_c0_outcome_receipt(
        outcome,
        cognitive_plan=cognitive,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )

    tampered = copy.deepcopy(outcome)
    tampered["requirement_outcomes"][0]["outcome"] = "C0_SUPPORTED"
    tampered["receipt_digest"] = cognitive_c0_outcome_digest(tampered)
    with pytest.raises(L1CognitiveC0OutcomeError, match="not source-bound"):
        build_l1_cognitive_revision_from_c0_outcome(
            cognitive_plan=cognitive,
            outcome_receipt=tampered,
            outcome_receipt_ref="l1_cognitive_c0_outcome_receipt.json",
            v2_capsule=v2,
            c0_obligation_receipt=c0,
        )


def test_c0_core_emits_the_cognitive_outcome_receipt_for_a_real_l1_contract(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.bindings.c0_binding import _l1_evidence_plan_receipts

    request = ValidatedRequest(
        request_id="cognitive-core-request",
        run_id="cognitive-core-run",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-08-11T00:00:00+00:00"
        ),
        trace_id="cognitive-core-trace",
        tenant_id="cognitive-core-tenant",
        replay_key="cognitive-core-replay",
        l5_certification_ref="test:valid:cognitive-core",
        app_payload=_candidate_payload(),
    )
    l1_plan = l1_plan_apps_rg(request)
    _ref, audit_refs = _l1_evidence_plan_receipts(
        l1_plan,
        request_id=request.request_id,
        run_id=request.run_id,
        trace_id=request.trace_id,
        final_evidence_digest="sha256:" + "d" * 64,
        obligation_receipt_artifact_dir=tmp_path,
    )

    assert any(
        ref.startswith("l1_cognitive_c0_outcome_receipt_digest:")
        for ref in audit_refs
    )
    assert (
        "l1_cognitive_c0_outcome_receipt_ref:"
        + sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT
    ) in audit_refs
    outcome = json.loads(
        (tmp_path / sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT).read_text(
            encoding="utf-8"
        )
    )
    c0_receipt = json.loads(
        (tmp_path / sr.FILENAME_L1_EVIDENCE_OBLIGATION_RECEIPT).read_text(
            encoding="utf-8"
        )
    )
    validate_l1_cognitive_c0_outcome_receipt(
        outcome,
        cognitive_plan=l1_plan.task_spec["apps_rg_cognitive_v3_plan"],
        v2_capsule=l1_plan.task_spec["apps_rg_planning_v2_capsule"],
        c0_obligation_receipt=c0_receipt,
    )


def test_section_runtime_attaches_the_c0_bound_revision_before_pa(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.bindings.c0_binding import _l1_evidence_plan_receipts
    from apps_rg.runtime.spine.c0_fec_compose import (
        _attach_l1_cognitive_c0_revision,
        pa_consumption_receipt_fields,
    )

    request = ValidatedRequest(
        request_id="cognitive-revision-request",
        run_id="cognitive-revision-run",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-08-11T00:00:00+00:00"
        ),
        trace_id="cognitive-revision-trace",
        tenant_id="cognitive-revision-tenant",
        replay_key="cognitive-revision-replay",
        l5_certification_ref="test:valid:cognitive-revision",
        app_payload=_candidate_payload(),
    )
    l1_plan = l1_plan_apps_rg(request)
    _l1_evidence_plan_receipts(
        l1_plan,
        request_id=request.request_id,
        run_id=request.run_id,
        trace_id=request.trace_id,
        final_evidence_digest="sha256:" + "e" * 64,
        obligation_receipt_artifact_dir=tmp_path,
    )
    runtime_payload: dict[str, Any] = {}
    _attach_l1_cognitive_c0_revision(
        artifact_dir=tmp_path,
        front_spine=SimpleNamespace(l1_plan=l1_plan),
        runtime_payload=runtime_payload,
        c0_required=True,
    )

    revision = runtime_payload["l1_cognitive_revision"]
    revision_advisory = runtime_payload["l1_cognitive_revision_advisory"]
    assert revision["status"] == "PROPOSED"
    assert revision_advisory["revision_digest"] == revision["revision_digest"]
    assert (tmp_path / sr.FILENAME_L1_COGNITIVE_REVISION).is_file()
    assert (tmp_path / sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY).is_file()
    compiled_observation = pa_consumption_receipt_fields(runtime_payload)
    assert compiled_observation["l1_cognitive_revision_ref"] == (
        sr.FILENAME_L1_COGNITIVE_REVISION
    )
    assert compiled_observation["l1_cognitive_revision_digest"] == revision[
        "revision_digest"
    ]
    assert compiled_observation["l1_cognitive_revision_advisory_ref"] == (
        sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY
    )
    assert compiled_observation["l1_cognitive_c0_outcome_receipt_digest"] == (
        json.loads(
            (tmp_path / sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT).read_text(
                encoding="utf-8"
            )
        )["receipt_digest"]
    )
