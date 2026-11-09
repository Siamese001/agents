"""Unit tests for Wave 1 L1 Pre-L0 governed model decomposition and dual-mode role registry."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from apps_rg.runtime.bindings.l1_binding import l1_plan_apps_rg
from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import (
    L1CognitivePlanError,
    build_l1_cognitive_plan_v3,
    cognitive_plan_digest,
    validate_l1_cognitive_plan_v3,
)
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V3_CANDIDATE_ARM,
    build_l1_cognitive_treatment,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.model_registry import ModelResolutionError, resolve
from apps_rg.runtime.spine_contracts import ValidatedRequest


def _profile_manifest() -> dict[str, str]:
    return {
        "l1_planning_profile_ref": l1_planning_profile_ref(),
        "l1_planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
        "manifest_digest": "f" * 64,
    }


def _build_payload(
    jd_text: str,
    *,
    decomposer: Any = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "non_product_certified": True,
        "target_company": "Acme Cloud Systems",
        "target_role": "VP of AI Platform Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": jd_text,
        "source_resume_text": "Led 120-person AI platform organization and governed multi-region infrastructure.",
        "generation_mode": "strategic_tailor",
        "task_spec": {
            "generation_mode": "strategic_tailor",
            "task_class": "resume_generation",
            "l1_cognitive_treatment": build_l1_cognitive_treatment(
                L1_COGNITIVE_V3_CANDIDATE_ARM,
                assignment_origin="U0_VALIDATED_INGRESS",
            ),
        },
        "query_spec": {"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        "support_expectation": {},
        "output_expectation": {},
        "profile_manifest": _profile_manifest(),
        "user_constraints": {"output_format": "executive_resume"},
        "output_preferences": {},
    }
    if decomposer is not None:
        payload["l1_model_decomposer"] = decomposer
    if extra_fields:
        payload.update(extra_fields)
    return payload


def test_l1_reasoning_roles_resolve_in_registry_and_provider_profiles() -> None:
    planner = resolve("reasoning.l1_cognitive_planner")
    strategist = resolve("reasoning.l1_post_c0_strategist")
    reviewer = resolve("reasoning.l1_post_l2_reviewer")

    assert planner.role == "reasoning.l1_cognitive_planner"
    assert strategist.role == "reasoning.l1_post_c0_strategist"
    assert reviewer.role == "reasoning.l1_post_l2_reviewer"

    # Cross-family orthogonality between planner/strategist and post-L2 reviewer
    assert reviewer.provider != planner.provider
    assert reviewer.params.get("reasoning_effort") == "low"

    repo_root = Path(__file__).resolve().parents[4]
    profiles_path = repo_root / "config" / "provider_profiles.yaml"
    profiles_data = yaml.safe_load(profiles_path.read_text(encoding="utf-8"))
    reasoning_models = profiles_data.get("reasoning_models", {})
    for role_key in (
        "reasoning.l1_cognitive_planner",
        "reasoning.l1_post_c0_strategist",
        "reasoning.l1_post_l2_reviewer",
    ):
        assert role_key in reasoning_models
        assert reasoning_models[role_key].get("ide_dual_mode_role") in {
            "high_reasoning_roles",
            "medium_reasoning_roles",
        }


def test_l1_plan_apps_rg_emits_model_derived_subgoals_and_governed_assertions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "l1-wave1-test-secret")
    jd_text = (
        "Requirements\n"
        "- Must lead AI platform strategy and own cloud infrastructure governance.\n"
        "- Must build distributed ML serving pipelines."
    )

    def _mock_decomposer(request_ctx: dict[str, Any]) -> str:
        req_ids = request_ctx["requirement_ids"]
        return json.dumps(
            {
                "provider": request_ctx["provider"],
                "model": request_ctx["model"],
                "subgoals": [
                    {
                        "requirement_id": req_id,
                        "weight": round(1.0 / len(req_ids), 4),
                        "rationale": f"Model-decomposed strategic obligation for {req_id} with executive scope.",
                        "semantic_query": f"executive leadership and platform delivery evidence for {req_id}",
                    }
                    for req_id in req_ids
                ],
            }
        )

    payload = _build_payload(jd_text, decomposer=_mock_decomposer)
    validated = ValidatedRequest(
        request_id="req-wave1-model-decomp",
        run_id="run-wave1-model-decomp",
        app_id="apps_rg",
        task_class="resume_generation",
        payload_digest="e" * 64,
        authority_validation_receipt=SimpleNamespace(
            validation_timestamp="2026-11-09T00:00:00+00:00"
        ),
        trace_id="trace-wave1-model-decomp",
        tenant_id="tenant-wave1",
        replay_key="replay-wave1-model-decomp",
        l5_certification_ref="test:valid:wave1",
        app_payload=payload,
    )

    contract = l1_plan_apps_rg(validated)
    assert contract.non_authority_assertion["no_unapproved_model_call"] is True
    assert contract.non_authority_assertion["no_direct_state_mutation"] is True

    cognitive = contract.task_spec["apps_rg_cognitive_v3_plan"]
    assert cognitive["plan_digest"] == cognitive_plan_digest(cognitive)
    assert cognitive["validation"]["no_unapproved_model_call"] is True
    assert cognitive["validation"]["no_direct_state_mutation"] is True
    assert cognitive["validation"]["no_model_call"] is False

    decomp = cognitive["goal_decomposition_ledger"]
    assert decomp["model_provenance"]["role"] == "reasoning.l1_cognitive_planner"
    assert len(decomp["subgoals"]) == len(
        cognitive["atomic_requirement_graph"]["requirements"]
    )
    assert all(
        "Model-decomposed strategic obligation" in sg["rationale"]
        for sg in decomp["subgoals"]
    )
    assert len(decomp["semantic_sub_queries"]) == len(decomp["subgoals"])
    assert decomp["competency_weights"]
    validate_l1_cognitive_plan_v3(cognitive)


def test_l1_cognitive_planner_fails_closed_on_unapproved_model_or_role() -> None:
    jd_text = "Requirements\n- Must lead platform engineering."
    with pytest.raises(L1CognitivePlanError, match="Unapproved model override"):
        build_l1_cognitive_plan_v3(
            app_payload=_build_payload(
                jd_text,
                extra_fields={"l1_model_override": "unapproved-rogue-model-v9"},
            ),
            request_id="req-wave1-rogue",
            run_id="run-wave1-rogue",
            trace_id="trace-wave1-rogue",
            replay_key="replay-wave1-rogue",
            planning_profile_ref=l1_planning_profile_ref(),
            planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
        )

    with pytest.raises(ModelResolutionError):
        resolve("reasoning.unregistered_l1_role")
