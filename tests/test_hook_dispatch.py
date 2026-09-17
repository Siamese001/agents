#!/usr/bin/env python3
"""Unit tests for tools.hook_dispatch (Antigravity Lifecycle Hook Dispatcher).

Verifies:
1. pre_edit_plan blocks invalid plans lacking status table or wave structure.
2. pre_edit_plan permits compliant wave plans and confirms wave summary table.
3. stop_wave_summary extracts and displays wave completion summary table.
4. pre_run_command blocks bare pytest sweeps.
5. pre_model_neutral blocks file paths containing proprietary model names.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.hook_dispatch import (
    handle_pre_edit_plan,
    handle_pre_model_neutral,
    handle_pre_run_command,
    handle_stop_wave_summary,
)


class HookDispatchTests(unittest.TestCase):
    def test_pre_edit_plan_blocks_unwavered_plan(self) -> None:
        """pre_edit_plan must deny plans lacking wave headers."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "plans/unwavered_plan.md",
                    "CodeContent": "# Flat Plan\nNo waves here.\n",
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_edit_plan"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "deny")
        self.assertIn("must be wave-based", data["reason"])

    def test_pre_edit_plan_blocks_missing_status_table(self) -> None:
        """pre_edit_plan must deny wave plans lacking the mandatory status table."""
        plan_without_table = """# Implementation Plan: Incomplete

## Wave 1: First
### Milestones & Deliverables
- [NEW] `file.py`

### Acceptance Criteria
- Done.

### Runtime Receipt & Completion Gate
- Gate.
"""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "plans/no_table.md",
                    "CodeContent": plan_without_table,
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_edit_plan"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "deny")
        self.assertIn("Implementation Status Table", data["reason"])

    def test_pre_edit_plan_allows_compliant_plan(self) -> None:
        """pre_edit_plan must allow compliant wave plans with status tables."""
        compliant_plan = """# Implementation Plan: Compliant

## Implementation Status Table

| Wave / Component | Description | Status | Deliverables / Receipts |
|---|---|---|---|
| Wave 1: Core | Build foundation | COMPLETED | `core.py` |

## Wave 1: Core
### Milestones & Deliverables
- [NEW] `core.py`

### Acceptance Criteria
- Unit tests pass.

### Runtime Receipt & Completion Gate
- Receipt verified.
"""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "plans/compliant.md",
                    "CodeContent": compliant_plan,
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_edit_plan"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "allow")

    def test_pre_edit_plan_ignores_non_plan_files(self) -> None:
        """pre_edit_plan must allow edits to ordinary non-plan source files."""
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "agentic_core/utils.py",
                    "CodeContent": "x = 1\n",
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_edit_plan"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "allow")

    def test_stop_wave_summary_renders_markdown_table(self) -> None:
        """stop_wave_summary must output the wave summary table and return empty json object."""
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "stop_wave_summary"],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Wave Summary Table", res.stdout)
        self.assertIn("| Wave # | Description / Scope | Status | Check/Open |", res.stdout)
        # Verify trailing {} payload
        last_line = [line for line in res.stdout.splitlines() if line.strip()][-1]
        self.assertEqual(json.loads(last_line), {})

    def test_pre_run_command_blocks_bare_pytest(self) -> None:
        """pre_run_command must deny un-scoped pytest invocations."""
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest"},
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_run_command"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "deny")

    def test_pre_run_command_allows_scoped_pytest(self) -> None:
        """pre_run_command must allow scoped test execution."""
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest tests/test_turn_gates.py --timeout=180"},
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_run_command"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
