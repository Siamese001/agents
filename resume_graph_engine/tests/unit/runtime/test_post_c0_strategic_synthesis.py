"""Unit tests for Wave 3: Post-C0 Strategic Thesis Unification & PA Binding."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from resume_engine.cli import _build_parser
from apps_rg.prompt_assembly.contracts import EvidenceSource, PromptAssemblyInput
from apps_rg.runtime.bindings.l1_cognitive_consumption import (
    build_l1_cognitive_consumer_advisory_from_cognitive_plan,
    build_l1_cognitive_revision_advisory,
)
from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import build_l1_cognitive_plan_v3
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    build_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.bindings.section_prompt_adapter import compile_section_prompt
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.l1_cognitive_c0_outcome_receipt import (
    build_l1_cognitive_c0_outcome_receipt,
    build_l1_cognitive_revision_from_c0_outcome,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    build_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.dispatch.unify_ibm_pa_common import load_w7_shell_slot_bodies
from apps_rg.runtime.reasoning.CareerThesisAlignmentAgent import (
    CareerThesisAlignmentAgent,
    execute_career_thesis_alignment,
)


def _payload() -> dict[str, Any]:
    return {
        "target_company": "Acme Corp",
        "target_role": "VP Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": (
            "Requirements\n"
            "- Must have 10+ years of AI platform leadership.\n"
            "- Must lead distributed systems engineering."
        ),
        "source_resume_text": "Built governed AI infrastructure and distributed systems.",
        "generation_mode": "strategic_tailor",
        "task_spec": {"generation_mode": "strategic_tailor"},
        "query_spec": {"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        "support_expectation": {},
        "output_expectation": {},
        "user_constraints": {},
        "output_preferences": {},
    }


def _assembly_input() -> PromptAssemblyInput:
    slots = load_w7_shell_slot_bodies()
    return PromptAssemblyInput(
        template_id="strategic_tailor_v1",
        request_id="wave3-req",
        run_id="wave3-run",
        trace_root="wave3-trace",
        s0_system_preamble=slots["S0"],
        d0_fences=slots["D0"],
        e0_examples=slots["E0"],
        y0_style_preferences=slots["Y0"],
        i0_instructions="Use only C0 candidate facts for claims.",
        c0_candidate_facts=EvidenceSource(
            source_type="candidate_facts",
            source_tag="candidate_facts",
            content="Candidate has platform leadership evidence.",
        ),
        c0_jd_requirements=EvidenceSource(
            source_type="jd_requirements",
            source_tag="jd_requirements",
            content="Targeting only; not claim proof.",
            confidence=0.0,
        ),
        u0_user_task="Create one grounded employment bullet.",
        r0_response_schema='{"type":"object"}',
    )


def test_cli_default_l1_cognitive_treatment_arm_is_v3() -> None:
    parser = _build_parser()
    args = parser.parse_args(["run"])
    assert args.l1_cognitive_treatment_arm == "l1_v3_treatment"


def test_career_thesis_agent_resolves_post_c0_strategist_and_supports_model_synthesizer() -> None:
    agent = CareerThesisAlignmentAgent()
    assert agent.role_key == "reasoning.l1_post_c0_strategist"
    assert agent.model_name
    assert agent.provider

    def _custom_synthesizer(ctx: dict[str, Any]) -> dict[str, Any]:
        assert ctx["role_key"] == "reasoning.l1_post_c0_strategist"
        return {
            "career_thesis": {
                "primary_positioning": "VP of Agentic AI & Distributed Platform Engineering",
                "executive_summary_anchor": "Proven scaling of high-assurance AI systems.",
                "narrative_arc": "Platform architect to enterprise executive.",
                "key_themes": ["Agentic AI Governance", "Distributed Systems Scale"],
            },
            "evidence_gaps": [
                {
                    "requirement_text": "10+ years of AI platform leadership",
                    "gap_status": "ADJACENT_PIVOT",
                    "pivot_strategy": "Bridge from 12 years of distributed systems leadership.",
                    "matched_evidence_ids": ["bul_unify_001"],
                }
            ],
            "thematic_allocation": {
                "headline_focus": ["Agentic AI Governance"],
                "executive_summary_focus": ["Agentic AI Governance", "Distributed Systems Scale"],
                "competencies_focus": ["Python", "Kubernetes"],
                "bullet_lanes_focus": {
                    "unify_bullets": ["Agentic AI orchestration and runtime reliability"],
                    "ibm_bullets": ["Enterprise governance and revenue growth"],
                },
            },
        }

    plan = agent.synthesize(
        target_company="Acme Corp",
        target_role="VP Engineering",
        target_level="VP",
        c0_evidence_items=[
            {
                "assertion_id": "bul_unify_001",
                "text": "Led distributed platform architecture.",
                "matched_skills": ["Python", "Kubernetes"],
                "section_id": "unify_bullets",
            }
        ],
        model_synthesizer=_custom_synthesizer,
    )
    assert plan.career_thesis.primary_positioning == "VP of Agentic AI & Distributed Platform Engineering"
    assert plan.evidence_gaps[0].gap_status == "ADJACENT_PIVOT"
    assert plan.thematic_allocation.bullet_lanes_focus["unify_bullets"] == [
        "Agentic AI orchestration and runtime reliability"
    ]
    assert plan.digest.startswith("sha256:")


def test_post_c0_revision_and_compile_section_prompt_inject_unified_career_thesis(
    tmp_path: Path,
) -> None:
    cognitive = dict(
        build_l1_cognitive_plan_v3(
            app_payload=_payload(),
            request_id="wave3-req",
            run_id="wave3-run",
            trace_id="wave3-trace",
            replay_key="wave3-replay",
            planning_profile_ref=l1_planning_profile_ref(),
            planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
        )
    )
    v2 = dict(
        build_apps_rg_l1_planning_capsule_v2(
            app_payload=_payload(),
            request_id="wave3-req",
            run_id="wave3-run",
            trace_id="wave3-trace",
            replay_key="wave3-replay",
            planning_profile_ref=l1_planning_profile_ref(),
            planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
        )
    )
    c0_receipt = build_l1_evidence_obligation_receipt(
        capsule=v2,
        request_id="wave3-req",
        run_id="wave3-run",
        trace_id="wave3-trace",
        final_evidence_digest="sha256:" + "8" * 64,
        evidence_items=[],
    )
    outcome = build_l1_cognitive_c0_outcome_receipt(
        cognitive_plan=cognitive,
        v2_capsule=v2,
        c0_obligation_receipt=c0_receipt,
    )
    thesis_plan = execute_career_thesis_alignment(
        tmp_path,
        target_company="Acme Corp",
        target_role="VP Engineering",
        target_level="VP",
        jd_requirements=[
            {"id": "req_1", "text": "Must have 10+ years of AI platform leadership"},
            {"id": "req_2", "text": "Quantum Sovereign Hardware Foundry Operations"},
        ],
        c0_evidence_items=[
            {
                "assertion_id": "bul_unify_001",
                "text": "Led AI platform leadership and distributed systems.",
                "matched_skills": ["AI Platform", "Distributed Systems"],
                "section_id": "unify_bullets",
                "domain": "Agentic AI Platform",
            }
        ],
    )
    revision = build_l1_cognitive_revision_from_c0_outcome(
        cognitive_plan=cognitive,
        outcome_receipt=outcome,
        outcome_receipt_ref="l1_cognitive_c0_outcome_receipt.json",
        v2_capsule=v2,
        c0_obligation_receipt=c0_receipt,
        career_thesis_plan=thesis_plan,
    )
    assert "career_thesis_alignment" in revision
    assert revision["career_thesis_alignment"]["plan_digest"] == thesis_plan.digest

    advisory = build_l1_cognitive_consumer_advisory_from_cognitive_plan(cognitive)
    revision_advisory = build_l1_cognitive_revision_advisory(
        cognitive_plan=cognitive,
        revision=revision,
        c0_outcome_receipt_digest=outcome["receipt_digest"],
    )

    compiled = compile_section_prompt(
        _assembly_input(),
        section_id="unify_bullets",
        l1_cognitive_advisory=advisory,
        l1_cognitive_plan=cognitive,
        l1_cognitive_revision=revision,
        l1_cognitive_revision_advisory=revision_advisory,
    )
    rendered = "\n".join(
        str(msg.get("content") or "") for msg in compiled.artifact.messages
    )
    assert "<L1_COGNITIVE_C0_REVISION>" in rendered
    assert "L1 post-C0 career thesis positioning:" in rendered
    assert "VP Engineering" in rendered
    assert "L1 post-C0 gap mitigation [DIRECT_MATCH]" in rendered
    assert "L1 post-C0 gap mitigation [ADJACENT_PIVOT]" in rendered
    assert "L1 post-C0 section allocation [unify_bullets]:" in rendered
    assert "Agentic AI Platform" in rendered
