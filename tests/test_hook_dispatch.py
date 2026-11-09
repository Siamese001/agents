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

    def test_pre_ask_question_blocks_bundled_questions(self) -> None:
        """pre_ask_question must deny multi-question batched payloads."""
        payload = {
            "toolCall": {
                "name": "ask_question",
                "args": {
                    "questions": [
                        {"question": "First choice?", "options": ["Option A (70%)", "Option B (60%)"]},
                        {"question": "Second choice?", "options": ["Option X (70%)", "Option Y (60%)"]},
                    ]
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_ask_question"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "deny")
        self.assertIn("HITL_VIOLATION_BULK_DECISION", data["reason"])

    def test_pre_ask_question_enforces_margin_bypass_when_spread_exceeds_20(self) -> None:
        """pre_ask_question must deny non-mandatory questions with spread > 20% and top >= 65%."""
        payload = {
            "toolCall": {
                "name": "ask_question",
                "args": {
                    "questions": [
                        {
                            "question": "Which storage caching approach should we use?",
                            "options": [
                                "(Recommended) Memory cache (Confidence: HIGH (88%))",
                                "Disk cache fallback (Confidence: LOW (40%))",
                            ],
                        }
                    ]
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_ask_question"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "deny")
        self.assertIn("HITL_MARGIN_BYPASS_REQUIRED", data["reason"])

    def test_pre_ask_question_allows_ambiguous_or_mandatory_questions(self) -> None:
        """pre_ask_question must allow questions with <= 20% spread or mandatory merge authorization."""
        ambiguous_payload = {
            "toolCall": {
                "name": "ask_question",
                "args": {
                    "questions": [
                        {
                            "question": "Which retry policy should we apply?",
                            "options": [
                                "(Recommended) Exponential backoff (Confidence: MEDIUM (68%))",
                                "Fixed interval retry (Confidence: MEDIUM (55%))",
                            ],
                        }
                    ]
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_ask_question"],
            input=json.dumps(ambiguous_payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        self.assertEqual(json.loads(res.stdout.strip())["decision"], "allow")

    def test_pre_ask_question_blocks_oversized_truncated_or_jargon_payloads(self) -> None:
        """pre_ask_question must reject >300-char questions, >250-char options, ellipses, and technical jargon."""
        bad_cases = [
            {
                "question": "Which option should we choose for this step? " + ("More context words " * 16),
                "options": [
                    "(Recommended) First plain choice (Confidence: MEDIUM (68%))",
                    "Second plain choice (Confidence: MEDIUM (55%))",
                ],
                "expected_code": "HITL_VIOLATION_QUESTION_LENGTH",
            },
            {
                "question": "Which schedule should we choose?",
                "options": [
                    "(Recommended) First plain choice with extra words " + ("padding text " * 18) + "(Confidence: MEDIUM (68%))",
                    "Second plain choice (Confidence: MEDIUM (55%))",
                ],
                "expected_code": "HITL_VIOLATION_OPTION_LENGTH",
            },
            {
                "question": "Should we continue with the truncated option...?",
                "options": [
                    "(Recommended) First plain choice (Confidence: MEDIUM (68%))",
                    "Second plain choice (Confidence: MEDIUM (55%))",
                ],
                "expected_code": "HITL_VIOLATION_TRUNCATION",
            },
            {
                "question": "Should we run O2 A2A voice repair in tools/hook_dispatch.py?",
                "options": [
                    "(Recommended) Run O2 repair (Confidence: MEDIUM (68%))",
                    "Skip repair (Confidence: MEDIUM (55%))",
                ],
                "expected_code": "HITL_VIOLATION_JARGON_IN_QUESTION",
            },
            {
                "question": "Which delivery order should we follow?",
                "options": [
                    "(Recommended) Run ExecutiveVoiceRepairAgent with blast radius check (Confidence: MEDIUM (68%))",
                    "Wait for review (Confidence: MEDIUM (55%))",
                ],
                "expected_code": "HITL_VIOLATION_JARGON_IN_OPTION",
            },
        ]
        for case in bad_cases:
            payload = {
                "toolCall": {
                    "name": "ask_question",
                    "args": {
                        "questions": [
                            {
                                "question": case["question"],
                                "options": case["options"],
                            }
                        ]
                    },
                }
            }
            res = subprocess.run(
                [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_ask_question"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=ROOT,
                timeout=10,
            )
            self.assertEqual(res.returncode, 1, msg=f"Expected deny for {case['expected_code']}")
            data = json.loads(res.stdout.strip())
            self.assertEqual(data["decision"], "deny")
            self.assertIn(case["expected_code"], data["reason"])

    def test_post_ask_question_records_operator_decision(self) -> None:
        """post_ask_question must persist operator answers into HITLDecisionStore."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "hitl.sqlite"
            payload = {
                "toolCall": {
                    "name": "ask_question",
                    "args": {
                        "questions": [
                            {
                                "question": "Approve merge of feature branch into local main?",
                                "options": [
                                    "(Recommended) Approve merge (Confidence: HIGH (92%))",
                                    "Hold merge (Confidence: LOW (25%))",
                                ],
                            }
                        ]
                    },
                },
                "toolResult": "A1: (Recommended) Approve merge (Confidence: HIGH (92%))",
            }
            env = dict(**__import__("os").environ, HITL_STORE_PATH=str(db_file))
            res = subprocess.run(
                [sys.executable, "tools/hook_dispatch.py", "--hook", "post_ask_question"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                cwd=ROOT,
                env=env,
                timeout=10,
            )
            self.assertEqual(res.returncode, 0)
            out = json.loads(res.stdout.strip())
            self.assertEqual(out["status"], "STORED")
            self.assertEqual(out["category"], "pr_merge_authorization")
            self.assertEqual(out["operator_action"], "APPROVED")

    def test_pre_subagent_delegation_validates_contract(self) -> None:
        """pre_subagent_delegation must reject incomplete 10-field delegation contracts."""
        bad_payload = {
            "toolCall": {
                "name": "invoke_subagent",
                "args": {
                    "delegation_contract": {
                        "task_id": "t1",
                        "objective": "Missing fields",
                    }
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_subagent_delegation"],
            input=json.dumps(bad_payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 1)
        self.assertEqual(json.loads(res.stdout.strip())["decision"], "deny")

    def test_post_invocation_intercepts_disjunctive_prose_and_unpromoted_edits(self) -> None:
        """post_invocation must emit force_continue when turn ends with disjunctive fence-sitting or unpromoted edits."""
        disjunctive_payload = {
            "candidate_response": "Ready for next direction: we can address the caching layer, or proceed with testing."
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "post_invocation"],
            input=json.dumps(disjunctive_payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data.get("terminationBehavior"), "force_continue")
        self.assertTrue(len(data.get("injectSteps", [])) > 0)

    def test_post_invocation_loads_transcript_path_and_intercepts_plaintext_questionnaire(self) -> None:
        """post_invocation must load current turn steps from transcriptPath when inline steps/candidate_response are absent."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_file = Path(tmpdir) / "transcript.jsonl"
            lines = [
                json.dumps({"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "Why are large files not modularized? /teamwork"}),
                json.dumps(
                    {
                        "type": "PLANNER_RESPONSE",
                        "source": "MODEL",
                        "content": (
                            "To prepare the task prompt, please answer the following questions:\n\n"
                            "1. What should the team deliver?\n"
                            "   (a) An explanatory analysis\n"
                            "   (b) Active refactoring\n"
                        ),
                    }
                ),
            ]
            transcript_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

            res = subprocess.run(
                [sys.executable, "tools/hook_dispatch.py", "--hook", "post_invocation"],
                input=json.dumps({"transcriptPath": str(transcript_file)}),
                capture_output=True,
                text=True,
                cwd=ROOT,
                timeout=10,
            )
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout.strip())
            self.assertEqual(data.get("terminationBehavior"), "force_continue")
            injected = data.get("injectSteps", [])
            self.assertEqual(len(injected), 1)
            self.assertIn("INV-DECISIVE-RECOMMENDATION", injected[0].get("userMessage", ""))

            # Mid-turn GENERIC tool output step must NOT trigger post_invocation intercept
            mid_turn_file = Path(tmpdir) / "mid_turn.jsonl"
            mid_turn_file.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "Inspect file"}),
                        json.dumps({"type": "PLANNER_RESPONSE", "source": "MODEL", "tool_calls": [{"name": "view_file", "args": {}}], "content": ""}),
                        json.dumps({"type": "GENERIC", "source": "MODEL", "content": "def helper_func():\n    return None\n"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            res_mid = subprocess.run(
                [sys.executable, "tools/hook_dispatch.py", "--hook", "post_invocation"],
                input=json.dumps({"transcriptPath": str(mid_turn_file)}),
                capture_output=True,
                text=True,
                cwd=ROOT,
                timeout=10,
            )
            self.assertEqual(res_mid.returncode, 0)
            self.assertEqual(json.loads(res_mid.stdout.strip()).get("injectSteps"), [])

            # Denied ask_question followed by plain-text questionnaire MUST still be intercepted
            denied_file = Path(tmpdir) / "denied_turn.jsonl"
            denied_file.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "Run /teamwork"}),
                        json.dumps({"type": "PLANNER_RESPONSE", "source": "MODEL", "tool_calls": [{"name": "ask_question", "args": {"questions": []}}], "content": ""}),
                        json.dumps({"type": "GENERIC", "source": "MODEL", "content": "Encountered error in step execution: tool call denied by pre-tool hook: PRE_OUTPUT_LAYMAN_GUARD"}),
                        json.dumps(
                            {
                                "type": "PLANNER_RESPONSE",
                                "source": "MODEL",
                                "content": "To prepare the task prompt, please answer the following questions:\n1. What should the team deliver?\n(a) Analysis\n(b) Refactor\n",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            res_denied = subprocess.run(
                [sys.executable, "tools/hook_dispatch.py", "--hook", "post_invocation"],
                input=json.dumps({"transcriptPath": str(denied_file)}),
                capture_output=True,
                text=True,
                cwd=ROOT,
                timeout=10,
            )
            self.assertEqual(res_denied.returncode, 0)
            data_denied = json.loads(res_denied.stdout.strip())
            self.assertEqual(data_denied.get("terminationBehavior"), "force_continue")
            self.assertIn("INV-DECISIVE-RECOMMENDATION", data_denied["injectSteps"][0].get("userMessage", ""))

    def test_pre_ask_question_deny_includes_anti_plaintext_fallback_directive(self) -> None:
        """pre_ask_question deny reason must instruct agent never to fall back to printing plain-text questions."""
        jargon_payload = {
            "toolCall": {
                "name": "ask_question",
                "args": {
                    "questions": [
                        {
                            "question": "Should we refactor executive_summary_voice_repair.py now?",
                            "options": [
                                "(Recommended) Refactor executive_summary_voice_repair.py (Confidence: MEDIUM (70%))",
                                "Keep current file (Confidence: MEDIUM (58%))",
                            ],
                        }
                    ]
                },
            }
        }
        res = subprocess.run(
            [sys.executable, "tools/hook_dispatch.py", "--hook", "pre_ask_question"],
            input=json.dumps(jargon_payload),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(res.returncode, 1)
        data = json.loads(res.stdout.strip())
        self.assertEqual(data["decision"], "deny")
        self.assertIn(
            "NEVER fall back to printing questions or options as plain text in chat; immediately invoke ask_question again with ONE atomic plain-English question at a time (<= 120 chars per option, Confidence: TIER (N%)).",
            data["reason"],
        )


if __name__ == "__main__":
    unittest.main()
