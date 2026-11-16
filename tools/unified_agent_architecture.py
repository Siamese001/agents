#!/usr/bin/env python3
"""Unified Architecture for Skills, Agents, Sub-Agents, Hooks & Rules.

Implements the five architectural pillars, four shared foundations,
seven-step lifecycle flow, and ten-field delegation contract enforcement.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Sequence, Union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
class SubagentCapabilities:
    max_subagent_depth: int = 5
    allowed_subagents: list[str] = field(default_factory=list)


@dataclass
class SubagentConfig:
    name: str
    description: str
    system_instructions: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    capabilities: SubagentCapabilities = field(default_factory=SubagentCapabilities)
    budget: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "system_instructions": self.system_instructions,
            "allowed_tools": list(self.allowed_tools),
            "capabilities": {
                "max_subagent_depth": self.capabilities.max_subagent_depth,
                "allowed_subagents": list(self.capabilities.allowed_subagents),
            },
            "budget": dict(self.budget),
            "metadata": dict(self.metadata),
        }


@dataclass
class CapabilitiesConfig:
    enable_subagents: bool = True
    max_subagent_depth: int = 5
    allowed_subagents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enable_subagents": self.enable_subagents,
            "max_subagent_depth": self.max_subagent_depth,
            "allowed_subagents": list(self.allowed_subagents),
        }


class BuiltinTools(str, Enum):
    START_SUBAGENT = "start_subagent"
    CREATE_FILE = "create_file"
    EDIT_FILE = "edit_file"
    RUN_COMMAND = "run_command"
    VIEW_FILE = "view_file"


@dataclass
class TemplatedSystemInstructions:
    identity: str = ""
    guidelines: str = ""
    communication_style: str = ""


@dataclass
class CustomSystemInstructions:
    text: str = ""


@dataclass
class Document:
    path: str
    mime_type: str = "application/pdf"
    content_bytes: bytes = b""

    @classmethod
    def from_file(cls, file_path: str | Path) -> Document:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Document file not found: {p}")
        suffix = p.suffix.lower()
        mime = "application/pdf" if suffix == ".pdf" else "text/plain"
        return cls(path=str(p), mime_type=mime, content_bytes=p.read_bytes())


@dataclass
class Image:
    path: str
    mime_type: str = "image/png"
    content_bytes: bytes = b""

    @classmethod
    def from_file(cls, file_path: str | Path) -> Image:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Image file not found: {p}")
        return cls(path=str(p), mime_type="image/png", content_bytes=p.read_bytes())


class ToolContext:
    """Typed Antigravity SDK ToolContext for stateful tool execution."""

    def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
        self._state: dict[str, Any] = dict(initial_state or {})

    def get_state(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._state)


try:
    from google.antigravity.errors import AntigravityCancelledError  # type: ignore[import-not-found]
except ImportError:
    class AntigravityCancelledError(BaseException):
        """Raised when an Antigravity SDK response stream is cancelled."""


@dataclass
class SubAgentDefinition:
    id: str
    parent_agent_id: str
    domain_focus: str
    lightweight_autonomy: bool = True
    can_have_sub_agents: bool = True
    returns_results_upstream: bool = True
    assigned_skills: list[str] = field(default_factory=list)

    def to_antigravity_subagent_config(
        self,
        contract: dict[str, Any] | None = None,
        *,
        allowed_subagents: list[str] | None = None,
    ) -> SubagentConfig:
        """Project SubAgentDefinition and optional 10-field contract into SubagentConfig."""
        if contract is not None:
            errs = validate_delegation_contract(contract)
            if errs:
                raise ValueError(f"Invalid delegation contract: {errs}")
            tools = [str(t) for t in contract.get("allowed_tools", [])]
            budget_raw = contract.get("budget")
            budget_dict = dict(budget_raw) if isinstance(budget_raw, dict) else {"limit": budget_raw}
            objective = str(contract.get("objective", self.domain_focus))
            meta = {
                "task_id": contract.get("task_id"),
                "parent_task_id": contract.get("parent_task_id"),
                "scope_in": list(contract.get("scope_in", [])),
                "scope_out": list(contract.get("scope_out", [])),
                "deliverable": contract.get("deliverable"),
                "definition_of_done": contract.get("definition_of_done"),
                "escalation_rule": contract.get("escalation_rule"),
            }
        else:
            tools = [t.value for t in BuiltinTools]
            budget_dict = {"max_turns": 50, "timeout_seconds": 1800}
            objective = self.domain_focus
            meta = {"parent_agent_id": self.parent_agent_id, "assigned_skills": list(self.assigned_skills)}

        if self.can_have_sub_agents and BuiltinTools.START_SUBAGENT.value not in tools:
            tools.append(BuiltinTools.START_SUBAGENT.value)

        return SubagentConfig(
            name=self.id,
            description=objective,
            system_instructions=f"Domain focus: {self.domain_focus}. Return structured output upstream to {self.parent_agent_id}.",
            allowed_tools=tools,
            capabilities=SubagentCapabilities(
                max_subagent_depth=5 if self.can_have_sub_agents else 0,
                allowed_subagents=list(allowed_subagents or []),
            ),
            budget=budget_dict,
            metadata=meta,
        )


def contract_to_subagent_config(contract: dict[str, Any]) -> SubagentConfig:
    """Validate a 10-field delegation contract and project it to an Antigravity SubagentConfig."""
    errs = validate_delegation_contract(contract)
    if errs:
        raise ValueError(f"Invalid delegation contract: {errs}")
    sub_def = SubAgentDefinition(
        id=str(contract["task_id"]),
        parent_agent_id=str(contract["parent_task_id"]),
        domain_focus=str(contract["objective"]),
    )
    return sub_def.to_antigravity_subagent_config(contract)


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

    # Validate scope separation (prefix-aware across subdirectories and normalization variants)
    scope_in = payload.get("scope_in")
    scope_out = payload.get("scope_out")
    if isinstance(scope_in, (list, tuple)) and isinstance(scope_out, (list, tuple)):
        from tools.prompt_scope_isolation import paths_overlap

        overlaps = sorted({
            f"{pin} <-> {pout}"
            for pin in scope_in
            for pout in scope_out
            if str(pin).strip() and str(pout).strip() and paths_overlap(str(pin), str(pout))
        })
        if overlaps:
            errors.append(f"DELEGATION_VIOLATION_SCOPE_OVERLAP: Contradictory overlap between scope_in and scope_out: {overlaps}")

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
            expected_essential = {"agents-implementation-plan-guard", "agents-pytest-scope-guard", "agents-hitl-atomic-guard"}
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


if __name__ == "__main__":
    sample_contract = {
        "task_id": "subtask-verify-01",
        "parent_task_id": "wave-3",
        "objective": "Verify Antigravity SubagentConfig projection",
        "scope_in": ["tools/"],
        "scope_out": ["resume_graph_engine/"],
        "allowed_tools": [BuiltinTools.VIEW_FILE.value, BuiltinTools.START_SUBAGENT.value],
        "deliverable": "Serialized SubagentConfig JSON",
        "definition_of_done": "Zero governance errors and valid SubagentConfig",
        "budget": {"max_turns": 3, "timeout_seconds": 60},
        "escalation_rule": "Escalate on contract violation",
    }
    cfg = contract_to_subagent_config(sample_contract)
    gov_errors = validate_unified_architecture_governance()
    print(json.dumps({"subagent_config": cfg.to_dict(), "governance_errors": gov_errors}, indent=2))
    raise SystemExit(1 if gov_errors else 0)
