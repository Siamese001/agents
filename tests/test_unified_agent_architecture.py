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
