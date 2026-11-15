"""Programmatic Google Antigravity SDK hook and sandbox policy helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List


def build_antigravity_sandbox_config(enable_sandbox: bool = True) -> Dict[str, Any]:
    """Build an Antigravity RunCommandConfig-compatible sandbox policy object."""
    try:
        from google.antigravity import types as ag_types  # type: ignore

        return {"run_command": ag_types.RunCommandConfig(enable_sandbox=enable_sandbox)}
    except ImportError:
        return {
            "type": "RunCommandConfig",
            "enable_sandbox": enable_sandbox,
        }


def build_antigravity_sdk_hooks(repo_root: Path) -> Dict[str, Any]:
    """Construct programmatic google.antigravity.hooks and policy presets for LocalAgentConfig."""
    file_write_tools = (
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
        "write_file",
        "edit_file",
        "create_file",
    )
    subagent_tools = ("invoke_subagent", "browser_subagent", "start_subagent")

    try:
        from google.antigravity import hooks as ag_hooks  # type: ignore
        from google.antigravity.hooks import policy as ag_policy  # type: ignore

        sdk_available = True
    except ImportError:
        ag_hooks = None
        ag_policy = None
        sdk_available = False

    policies: List[Dict[str, Any]] = [
        {"preset": "policy.workspace_only", "tools": list(file_write_tools)},
        {"preset": "policy.allow", "tools": ["read_file", "view_file", "grep_search", "find_by_name"]},
        {"preset": "policy.ask_user", "tools": ["run_command"], "when": "destructive_or_unscoped"},
    ]
    if sdk_available and ag_policy is not None:
        try:
            policies.append({"sdk_policy": ag_policy.workspace_only()})
        except Exception:  # guardian: allow-silent-swallow -- optional SDK runtime policy binding
            pass

    return {
        "sdk_available": sdk_available,
        "repo_root": str(repo_root),
        "guarded_file_write_tools": list(file_write_tools),
        "guarded_subagent_tools": list(subagent_tools),
        "sandbox_config": build_antigravity_sandbox_config(enable_sandbox=True),
        "policies": policies,
        "hook_bindings": [
            "pre_tool_call_decide",
            "post_tool_call",
            "stop",
            "on_interaction",
            "pre_turn",
            "post_turn",
            "on_tool_error",
            "on_compaction",
        ],
    }
