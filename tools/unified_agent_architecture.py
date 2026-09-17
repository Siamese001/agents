#!/usr/bin/env python3
"""Unified Architecture for Skills, Agents, Sub-Agents, Hooks & Rules.

Implements the five architectural pillars, four shared foundations,
seven-step lifecycle flow, and ten-field delegation contract enforcement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Sequence, Union

ROOT = Path(__file__).resolve().parents[1]

MANDATORY_DELEGATION_FIELDS = (
    "task_id",
    "parent_task_id",
    "objective",
    "scope_in",
    "scope_out",
    "allowed_tools",
    "deliverable",
    "definition_of_done",
    "budget",
    "escalation_rule",
)

MANDATORY_RETURN_FIELDS = (
    "task_id",
    "status",
    "deliverable",
    "evidence_refs",
    "metrics",
)


class SkillStatePosture(str, Enum):
    STATELESS = "stateless"
    STATEFUL = "stateful"


class HookTiming(str, Enum):
    PRE = "pre"
    POST = "post"
    AROUND = "around"


class CrossCuttingConcern(str, Enum):
    LOGGING = "logging"
    METRICS = "metrics"
    CACHING = "caching"
    NOTIFICATIONS = "notifications"
    GUARDRAILS = "guardrails"
    MODERATION = "moderation"


class RuleType(str, Enum):
    PRE_CONDITION = "pre_condition"
    POST_CONDITION = "post_condition"
    INVARIANT = "invariant"
    ROUTING = "routing"
    SAFETY = "safety"


class LifecycleStep(int, Enum):
    STEP_1_GOAL_AND_RULE_VERIFICATION = 1
    STEP_2_PLANNING_AND_SKILL_SELECTION = 2
    STEP_3_SUBAGENT_DELEGATION = 3
    STEP_4_SKILL_EXECUTION = 4
    STEP_5_HOOK_TRIGGERS = 5
    STEP_6_CONTINUOUS_RULE_VALIDATION = 6
    STEP_7_UPSTREAM_SYNTHESIS = 7


@dataclass
class SkillDefinition:
    id: str
    name: str
    description: str
    state_posture: SkillStatePosture = SkillStatePosture.STATELESS
    model_agnostic: bool = True
    tool_agnostic: bool = True
    discoverable: bool = True
    composable: bool = True


@dataclass
class AgentDefinition:
    id: str
    role_name: str
    description: str
    goal_driven: bool = True
    owns_strategy_and_control: bool = True
    maintains_context_and_state: bool = True
    can_delegate: bool = True


@dataclass
class SubAgentDefinition:
    id: str
    parent_agent_id: str
    domain_focus: str
    lightweight_autonomy: bool = True
    can_have_sub_agents: bool = True
    returns_results_upstream: bool = True
    assigned_skills: list[str] = field(default_factory=list)


@dataclass
class HookDefinition:
    id: str
    event: str
    timing: HookTiming
    cross_cutting_concern: CrossCuttingConcern
    non_intrusive: bool = True
    description: str = ""


@dataclass
class RuleDefinition:
    id: str
    rule_type: RuleType
    description: str
    immutable: bool = True
    enforcement_surface: str = "all"


def validate_delegation_contract(payload: dict[str, Any]) -> list[str]:
    """Validate a sub-agent task delegation contract against the 10 required fields."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["DELEGATION_VIOLATION_NOT_A_DICT: Contract must be a JSON dictionary."]

    for required_field in MANDATORY_DELEGATION_FIELDS:
        if required_field not in payload:
            errors.append(f"DELEGATION_VIOLATION_MISSING_FIELD: Missing required field '{required_field}'.")
        elif payload[required_field] is None:
            errors.append(f"DELEGATION_VIOLATION_NULL_FIELD: Field '{required_field}' cannot be null.")

    # Validate budget has concrete bounds
    budget = payload.get("budget")
    if isinstance(budget, dict):
        if not any(k in budget for k in ("max_turns", "timeout_seconds", "token_limit", "cost_limit")):
            errors.append("DELEGATION_VIOLATION_VAGUE_BUDGET: Budget dictionary must declare concrete limits.")
    elif budget is not None and not isinstance(budget, (int, float, str)):
        errors.append("DELEGATION_VIOLATION_INVALID_BUDGET: Budget must be a numeric limit or bounded object.")

    # Validate scope separation
    scope_in = payload.get("scope_in")
    scope_out = payload.get("scope_out")
    if isinstance(scope_in, (list, tuple)) and isinstance(scope_out, (list, tuple)):
        overlap = set(scope_in).intersection(set(scope_out))
        if overlap:
            errors.append(f"DELEGATION_VIOLATION_SCOPE_OVERLAP: Contradictory overlap between scope_in and scope_out: {overlap}")

    return errors


def validate_subagent_return(payload: dict[str, Any]) -> list[str]:
    """Validate structured return payload from sub-agent to orchestrator."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["RETURN_VIOLATION_NOT_A_DICT: Return payload must be a JSON dictionary."]

    for field_name in MANDATORY_RETURN_FIELDS:
        if field_name not in payload:
            errors.append(f"RETURN_VIOLATION_MISSING_FIELD: Missing required return field '{field_name}'.")

    status = payload.get("status")
    if status not in ("SUCCESS", "FAILED", "BLOCKED", "DELEGATED"):
        errors.append(f"RETURN_VIOLATION_INVALID_STATUS: Status '{status}' must be SUCCESS, FAILED, BLOCKED, or DELEGATED.")

    return errors


def validate_unified_architecture_governance(repo_root: Path | None = None) -> list[str]:
    """Validate that repository configuration complies with unified architecture governance."""
    root = Path(repo_root or ROOT).resolve()
    errors: list[str] = []

    # 1. Hooks configuration
    hooks_file = root / ".agents" / "hooks.json"
    if not hooks_file.is_file():
        errors.append(f"Missing hooks configuration: {hooks_file}")
    else:
        try:
            data = json.loads(hooks_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "hooks" in data and isinstance(data["hooks"], list):
                hook_ids = {h.get("id") for h in data["hooks"] if isinstance(h, dict)}
            elif isinstance(data, dict):
                hook_ids = set(data.keys())
            else:
                hook_ids = set()
            expected_essential = {"agents-pre-edit-plan-guard", "agents-pytest-scope-guard", "agents-hitl-atomic-guard"}
            missing_hooks = expected_essential - hook_ids
            if missing_hooks:
                errors.append(f"Missing essential hooks in .agents/hooks.json: {missing_hooks}")
        except Exception as exc:
            errors.append(f"Invalid .agents/hooks.json: {exc}")

    # 2. Rules directory
    rules_dir = root / ".agents" / "rules"
    if not rules_dir.is_dir() or not any(rules_dir.glob("*.md")):
        errors.append(f"Rules directory missing or empty: {rules_dir}")

    # 3. Skills directory
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.is_dir():
        errors.append(f"Skills directory missing: {skills_dir}")

    return errors
