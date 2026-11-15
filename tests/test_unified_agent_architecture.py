#!/usr/bin/env python3
"""Unit tests for Unified Agent Architecture governance, delegation, and returns."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from tools.unified_agent_architecture import (
    MANDATORY_DELEGATION_FIELDS,
    MANDATORY_RETURN_FIELDS,
    CrossCuttingConcern,
    HookTiming,
    LifecycleStep,
    RuleType,
    SkillStatePosture,
    validate_delegation_contract,
    validate_subagent_return,
    validate_unified_architecture_governance,
)


def test_taxonomy_enums() -> None:
    """Verify enum invariants for 5 pillars and 7 lifecycle steps."""
    assert SkillStatePosture.STATELESS.value == "stateless"
    assert HookTiming.PRE.value == "pre"
    assert CrossCuttingConcern.GUARDRAILS.value == "guardrails"
    assert RuleType.INVARIANT.value == "invariant"
    assert len(LifecycleStep) == 7
    assert LifecycleStep.STEP_1_GOAL_AND_RULE_VERIFICATION == 1
    assert LifecycleStep.STEP_7_UPSTREAM_SYNTHESIS == 7


def test_validate_delegation_contract_success() -> None:
    """A fully specified 10-field contract passes validation."""
    valid_contract = {
        "task_id": "subtask-101",
        "parent_task_id": "wave-4",
        "objective": "Lint and verify documentation",
        "scope_in": ["docs/architecture/"],
        "scope_out": ["agentic_core/", "apps_rg/"],
        "allowed_tools": ["view_file", "run_command"],
        "deliverable": "Markdown lint report",
        "definition_of_done": "Zero lint errors reported",
        "budget": {"max_turns": 10, "timeout_seconds": 120},
        "escalation_rule": "Escalate to orchestrator on file write error",
    }
    errors = validate_delegation_contract(valid_contract)
    assert errors == []


def test_validate_delegation_contract_missing_and_null_fields() -> None:
    """Missing or null fields in delegation contract are rejected."""
    # Non-dict
    errors = validate_delegation_contract("invalid")  # type: ignore[arg-type]
    assert any("DELEGATION_VIOLATION_NOT_A_DICT" in e for e in errors)

    # Missing fields
    contract = {
        "task_id": "subtask-102",
        "parent_task_id": "wave-4",
        # missing other 8 fields
    }
    errors = validate_delegation_contract(contract)
    assert len(errors) == 8
    assert any("objective" in e for e in errors)

    # Null field
    contract_with_null = {f: "dummy" for f in MANDATORY_DELEGATION_FIELDS}
    contract_with_null["budget"] = None
    errors = validate_delegation_contract(contract_with_null)
    assert any("DELEGATION_VIOLATION_NULL_FIELD" in e for e in errors)


def test_validate_delegation_contract_budget_and_scope_overlap() -> None:
    """Vague budget and scope contradictions are rejected."""
    # Vague budget dictionary
    bad_budget = {f: "dummy" for f in MANDATORY_DELEGATION_FIELDS}
    bad_budget["budget"] = {"unbounded": True}
    errors = validate_delegation_contract(bad_budget)
    assert any("DELEGATION_VIOLATION_VAGUE_BUDGET" in e for e in errors)

    # Overlapping scope
    overlap_contract = {f: "dummy" for f in MANDATORY_DELEGATION_FIELDS}
    overlap_contract["budget"] = 5
    overlap_contract["scope_in"] = ["agentic_core/runtime", "docs/"]
    overlap_contract["scope_out"] = ["agentic_core/runtime", "tests/"]
    errors = validate_delegation_contract(overlap_contract)
    assert any("DELEGATION_VIOLATION_SCOPE_OVERLAP" in e for e in errors)


def test_validate_subagent_return_protocol() -> None:
    """Structured subagent return payload validation."""
    valid_return = {
        "task_id": "subtask-101",
        "status": "SUCCESS",
        "deliverable": "artifacts/report.md",
        "evidence_refs": ["artifacts/receipt.json"],
        "metrics": {"turns": 4, "duration_s": 12.5},
    }
    assert validate_subagent_return(valid_return) == []

    # Non-dict
    assert any("RETURN_VIOLATION_NOT_A_DICT" in e for e in validate_subagent_return([]))  # type: ignore[arg-type]

    # Missing field
    partial_return = {"task_id": "subtask-101", "status": "SUCCESS"}
    errors = validate_subagent_return(partial_return)
    assert len(errors) == 3

    # Invalid status
    invalid_status = dict(valid_return)
    invalid_status["status"] = "MAYBE"
    errors = validate_subagent_return(invalid_status)
    assert any("RETURN_VIOLATION_INVALID_STATUS" in e for e in errors)


def test_validate_unified_architecture_governance_on_repo() -> None:
    """Current repo structure complies with unified architecture governance."""
    errors = validate_unified_architecture_governance()
    assert errors == []


def test_validate_unified_architecture_governance_tampered(tmp_path: Path) -> None:
    """Governance validation catches missing hooks, rules, or skills."""
    # Empty dir
    errors = validate_unified_architecture_governance(tmp_path)
    assert len(errors) >= 3
    assert any("Missing hooks" in e for e in errors)
    assert any("Rules directory" in e for e in errors)
    assert any("Skills directory" in e for e in errors)


def test_validate_unified_architecture_governance_requires_canonical_plan_guard(tmp_path: Path) -> None:
    """Governance expects agents-implementation-plan-guard (not removed duplicate agents-pre-edit-plan-guard)."""
    agents_dir = tmp_path / ".agents"
    rules_dir = agents_dir / "rules"
    skills_dir = agents_dir / "skills"
    rules_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    (rules_dir / "core.md").write_text("# Rule\n", encoding="utf-8")

    (agents_dir / "hooks.json").write_text(
        json.dumps(
            {
                "agents-pre-edit-plan-guard": {},
                "agents-pytest-scope-guard": {},
                "agents-hitl-atomic-guard": {},
            }
        ),
        encoding="utf-8",
    )
    errors = validate_unified_architecture_governance(tmp_path)
    assert any("agents-implementation-plan-guard" in err for err in errors)

    repo_hooks = json.loads((Path(__file__).resolve().parents[1] / ".agents" / "hooks.json").read_text(encoding="utf-8"))
    assert "agents-implementation-plan-guard" in repo_hooks
    assert "agents-pre-edit-plan-guard" not in repo_hooks


def test_wave3_subagent_config_and_swarm_capabilities() -> None:
    """Verify 10-field contract projection to SubagentConfig and swarm CapabilitiesConfig."""
    from agents.orchestration.services.swarm_challenger import SwarmChallenger
    from apps_lic.runtime.outreach_swarm_challenger import OutreachSwarmChallenger
    from apps_research.reasoning.research_multi_agent import ResearchOrchestrator
    from apps_rg.runtime.resume_swarm_challenger import ResumeSwarmChallenger
    from tools.unified_agent_architecture import BuiltinTools, contract_to_subagent_config

    contract = {
        "task_id": "subtask-301",
        "parent_task_id": "wave-3",
        "objective": "Verify subagent config mapping",
        "scope_in": ["tools/"],
        "scope_out": ["resume_graph_engine/"],
        "allowed_tools": [BuiltinTools.VIEW_FILE.value],
        "deliverable": "SubagentConfig",
        "definition_of_done": "Valid SubagentConfig",
        "budget": {"max_turns": 3, "timeout_seconds": 60},
        "escalation_rule": "Escalate on failure",
    }
    cfg = contract_to_subagent_config(contract)
    assert cfg.name == "subtask-301"
    assert BuiltinTools.START_SUBAGENT.value in cfg.allowed_tools

    for cls in (SwarmChallenger, OutreachSwarmChallenger, ResumeSwarmChallenger, ResearchOrchestrator):
        sub_cfgs = cls.build_subagent_configs()
        cap_cfg = cls.build_capabilities_config()
        assert len(sub_cfgs) >= 3
        assert cap_cfg["enable_subagents"] is True
        assert cap_cfg["max_subagent_depth"] == 2
        assert len(cap_cfg["allowed_subagents"]) == len(sub_cfgs)


def test_wave3_structured_output_multimodal_toolcontext_and_cancel(tmp_path: Path) -> None:
    """Verify structured_output(), TemplatedSystemInstructions, Document.from_file, ToolContext, and cancel()."""
    import asyncio
    from agents.orchestration.primitives import AntigravityCancelledError, ToolContext, cancel_antigravity_response
    from apps_lic.pipeline.compiler import PromptCompiler
    from apps_research.engines.company_brief.synthesis import _CompanyBriefSynthesisMixin
    from apps_research.integrations.apps_rg_handoff import build_handoff_judge_agent_config
    from apps_research.integrations.pdf_ingest import load_multimodal_document, load_multimodal_image
    from apps_rg.l2_recipe.raw_text_json_unwrap import unwrap_structured_response_async
    from apps_rg.runtime.providers.external_provider import build_external_system_instructions
    from apps_rg.runtime.providers.wallclock_http_guard import cancel_antigravity_response_async

    class _FakeResponse:
        async def structured_output(self) -> dict[str, str]:
            return {"headline": "SVP AI", "status": "ok"}

        async def cancel(self) -> None:
            raise AntigravityCancelledError("stream cancelled")

    parsed, receipt = asyncio.run(unwrap_structured_response_async(_FakeResponse()))
    assert parsed == {"headline": "SVP AI", "status": "ok"}
    assert receipt["repair_type"] == "NATIVE_STRUCTURED_OUTPUT"

    assert issubclass(AntigravityCancelledError, BaseException)
    assert asyncio.run(cancel_antigravity_response(_FakeResponse())) is True
    assert asyncio.run(cancel_antigravity_response_async(_FakeResponse())) is True

    ctx = ToolContext({"counter": 1})
    assert ctx.get_state("counter") == 1
    ctx.set_state("counter", 2)
    assert ctx.get_state("counter") == 2

    doc_file = tmp_path / "sample.pdf"
    doc_file.write_bytes(b"%PDF-1.4 sample")
    img_file = tmp_path / "chart.png"
    img_file.write_bytes(b"\x89PNG\r\n")
    doc = load_multimodal_document(doc_file)
    img = load_multimodal_image(img_file)
    assert getattr(doc, "mime_type", "") == "application/pdf"
    assert getattr(img, "mime_type", "") == "image/png"

    assert _CompanyBriefSynthesisMixin.build_structured_agent_config({"type": "object"})["response_schema"] == {"type": "object"}
    assert build_handoff_judge_agent_config({"type": "object"})["response_schema"] == {"type": "object"}
    assert PromptCompiler.build_templated_system_instructions({"candidate_name": "Alex", "tone": "direct"}).communication_style == "direct"
    assert build_external_system_instructions("Strict JSON", identity="Reviewer").identity == "Reviewer"
