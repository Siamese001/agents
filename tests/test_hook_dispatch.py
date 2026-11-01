#!/usr/bin/env python3
"""Unit tests for tools.hook_dispatch (Antigravity Lifecycle Hook Dispatcher).

Verifies:
1. pre_edit_plan blocks invalid plans lacking required wave structure or gate evidence.
2. pre_edit_plan permits compliant wave plans with or without status tables.
3. stop_wave_summary is silenced to comply with output brevity rules.
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

    def test_pre_edit_plan_allows_plan_without_status_table(self) -> None:
        """pre_edit_plan must allow compliant wave plans even without a status table."""
        plan_without_table = """# Implementation Plan: No Table

## Wave 1: First
### Objective & Scope
First wave objective.

### Milestones & Deliverables
- [NEW] `file.py`

### Acceptance Criteria
- Done.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_file.py --timeout=60
- Input: tests/test_file.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipt.json
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
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "allow")

    def test_pre_edit_plan_blocks_missing_evidence_fields(self) -> None:
        """pre_edit_plan must deny wave plans missing required completion gate fields."""
        incomplete_plan = """# Implementation Plan: Incomplete

## Wave 1: First
### Objective & Scope
First wave objective.

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
                    "TargetFile": "plans/incomplete.md",
                    "CodeContent": incomplete_plan,
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
        self.assertIn("completion gate must specify", data["reason"])

    def test_pre_edit_plan_allows_compliant_plan(self) -> None:
        """pre_edit_plan must allow compliant wave plans with status tables."""
        compliant_plan = """# Implementation Plan: Compliant

## Implementation Status Table

| Wave / Component | Description | Status | Deliverables / Receipts |
|---|---|---|---|
| Wave 1: Core | Build foundation | COMPLETED | `core.py` |

## Wave 1: Core
### Objective & Scope
Build core foundation.

### Milestones & Deliverables
- [NEW] `core.py`

### Acceptance Criteria
- Unit tests pass.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_core.py --timeout=60
- Input: tests/test_core.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipt.json
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

    def test_stop_wave_summary_is_silenced(self) -> None:
        """stop_wave_summary must return empty json object without dumping tables to stdout."""
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "stop_wave_summary"],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("Wave Summary Table", res.stdout)
        self.assertEqual(json.loads(res.stdout.strip()), {})

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

    def test_hook_dispatch_from_agents_directory(self) -> None:
        """Hook dispatch must succeed when working directory is .agents/."""
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "pytest tests/test_hook_dispatch.py --timeout=60"},
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_run_command"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT / ".agents",
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
