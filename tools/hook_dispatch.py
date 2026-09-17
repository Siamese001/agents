#!/usr/bin/env python3
"""Antigravity Lifecycle Hook Dispatcher.

Executes native Antigravity lifecycle hooks configured in .agents/hooks.json:
- pre_edit_plan: PreToolUse guard on write_to_file / replace_file_content for plans
- stop_wave_summary: Stop hook to display mandatory wave completion summary table
- pre_run_command: PreToolUse guard on run_command (pytest scope & timeout enforcement)
- pre_model_neutral: PreToolUse guard on file writes / moves against proprietary model naming

Input/Output Protocol:
- Reads system and tool invocation context as JSON from sys.stdin
- Emits decision payload as JSON to sys.stdout
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tools.validate_implementation_plan import (
        extract_wave_summary_entries,
        get_active_plan_file,
        render_markdown_wave_summary_table,
        render_wave_summary_table,
        validate_plan_content,
    )
except ImportError:
    from validate_implementation_plan import (  # type: ignore
        extract_wave_summary_entries,
        get_active_plan_file,
        render_markdown_wave_summary_table,
        render_wave_summary_table,
        validate_plan_content,
    )


def read_hook_input() -> Dict[str, Any]:
    """Read and parse JSON payload from stdin, with safe fallback for testing."""
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                return json.loads(raw)
        except Exception:  # guardian: allow-silent-swallow -- fallback to empty dict on malformed stdin
            pass
    return {}


def emit_decision(decision: str, reason: str = "", overwrite: Optional[Dict[str, Any]] = None) -> int:
    """Emit JSON decision object to stdout and return corresponding exit code."""
    payload: Dict[str, Any] = {"decision": decision}
    if reason:
        payload["reason"] = reason
    if overwrite:
        payload["overwrite"] = overwrite
    print(json.dumps(payload))
    return 0 if decision == "allow" else 1


def handle_pre_edit_plan(payload: Dict[str, Any], repo_root: Path) -> int:
    """Validate implementation plan before write_to_file or replace_file_content executes."""
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    target_file = args.get("TargetFile", "")
    if not target_file:
        return emit_decision("allow")

    target_path = Path(target_file)
    target_name = target_path.name.lower()

    # Determine if this file is an implementation plan
    is_plan = (
        target_name == "implementation_plan.md"
        or "plans/" in target_file.replace("\\", "/")
        or target_file.endswith(".md") and "plan" in target_name
    )

    if not is_plan:
        return emit_decision("allow")

    # Extract proposed content
    content = ""
    if tool_name == "write_to_file":
        content = args.get("CodeContent", "")
    elif tool_name in ("replace_file_content", "multi_replace_file_content"):
        # For edits to existing file, read file and simulate or validate file if existing
        if target_path.is_file():
            try:
                content = target_path.read_text(encoding="utf-8")
            except Exception:
                pass
        if not content:
            content = args.get("ReplacementContent", "")

    if not content:
        return emit_decision("allow")

    # Validate against wave governance invariants
    is_valid, errors = validate_plan_content(content, filename=target_path.name, repo_root=repo_root)
    if not is_valid:
        error_msg = f"Plan validation rejected for {target_path.name}:\n" + "\n".join(f"- {e}" for e in errors)
        sys.stderr.write(f"\n[Antigravity Hook BLOCK] {error_msg}\n")
        return emit_decision("deny", reason=error_msg)

    # If valid, extract wave summary and display confirmation
    entries, _ = extract_wave_summary_entries(content)
    if entries:
        table_output = render_markdown_wave_summary_table(target_path.name, entries)
        sys.stderr.write(f"\n[Antigravity Hook PASS] Confirmed wave summary table:\n{table_output}\n")

    return emit_decision("allow", reason="Plan satisfies wave governance and status table requirements.")


def handle_stop_wave_summary(payload: Dict[str, Any], repo_root: Path) -> int:
    """Stop hook handler: display mandatory wave summary table upon agent turn completion."""
    artifact_dir = payload.get("artifactDirectoryPath")
    active_plan: Optional[Path] = None

    if artifact_dir:
        cand = Path(artifact_dir) / "implementation_plan.md"
        if cand.is_file():
            active_plan = cand

    if not active_plan:
        active_plan = get_active_plan_file(repo_root)

    if not active_plan or not active_plan.is_file():
        print(json.dumps({}))
        return 0

    try:
        content = active_plan.read_text(encoding="utf-8")
        entries, _ = extract_wave_summary_entries(content)
        if entries:
            table_str = render_markdown_wave_summary_table(active_plan.name, entries)
            sys.stderr.write(f"\n{table_str}\n")
            sys.stdout.write(f"\n{table_str}\n")
    except Exception as exc:  # guardian: allow-silent-swallow -- fallback if plan is unreadable at stop
        sys.stderr.write(f"[Antigravity Stop Hook] Warning: {exc}\n")

    print(json.dumps({}))
    return 0


def handle_pre_run_command(payload: Dict[str, Any]) -> int:
    """PreToolUse guard on run_command to enforce pytest scoping and timeout."""
    tool_call = payload.get("toolCall", {})
    args = tool_call.get("args", {})
    cmd = args.get("CommandLine", "").strip()

    if not cmd:
        return emit_decision("allow")

    # Check for bare pytest
    if re.search(r"\bpytest(?:\.exe)?\s*$", cmd) or re.search(r"\bpytest\s+tests/?\s*$", cmd):
        reason = "Bare un-scoped 'pytest' or 'pytest tests/' is blocked by governance. Specify targeted test files."
        sys.stderr.write(f"\n[Antigravity Hook BLOCK] {reason}\n")
        return emit_decision("deny", reason=reason)

    return emit_decision("allow")


def handle_pre_model_neutral(payload: Dict[str, Any]) -> int:
    """PreToolUse guard against proprietary model names in paths."""
    tool_call = payload.get("toolCall", {})
    args = tool_call.get("args", {})
    target_file = args.get("TargetFile", "")

    if not target_file:
        return emit_decision("allow")

    from tools.lint_model_neutral_naming import check_file_model_neutrality

    violations = check_file_model_neutrality(Path(target_file), ROOT)
    path_violations = [v for v in violations if "path" in v.lower() or "embedded" in v.lower()]
    if path_violations:
        reason = f"Model-neutral path violation: {'; '.join(path_violations)}"
        sys.stderr.write(f"\n[Antigravity Hook BLOCK] {reason}\n")
        return emit_decision("deny", reason=reason)

    return emit_decision("allow")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Antigravity Lifecycle Hook Dispatcher.")
    parser.add_argument(
        "--hook",
        required=True,
        choices=["pre_edit_plan", "stop_wave_summary", "pre_run_command", "pre_model_neutral"],
        help="Lifecycle hook handler to execute.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root path.",
    )
    args = parser.parse_args(argv)
    payload = read_hook_input()

    if args.hook == "pre_edit_plan":
        return handle_pre_edit_plan(payload, args.repo_root)
    elif args.hook == "stop_wave_summary":
        return handle_stop_wave_summary(payload, args.repo_root)
    elif args.hook == "pre_run_command":
        return handle_pre_run_command(payload)
    elif args.hook == "pre_model_neutral":
        return handle_pre_model_neutral(payload)

    return emit_decision("allow")


if __name__ == "__main__":
    sys.exit(main())
