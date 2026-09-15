#!/usr/bin/env python3
"""Unit tests for tools.validate_turn_gates.

Verifies mechanical pre-turn and post-turn gate enforcement:
1. Pre-turn gate evaluation across hooks, operating contract, runtime boundary, and Tier 1 tools.
2. HITL 25% ambiguity margin gating (autonomous proceed vs. atomic surfacing).
3. Operating contract memory bound (<= 200 lines).
4. Post-turn gate integration and scratchpad transparency validation.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.validate_turn_gates import (
    evaluate_hitl_ambiguity,
    validate_agent_operating_contract,
    validate_post_turn_gate,
    validate_pre_turn_gate,
    validate_scratchpad_transparency,
)

ROOT = Path(__file__).resolve().parents[1]


class TurnGatesValidationTests(unittest.TestCase):
    def test_pre_turn_gate_passes_on_current_repository(self) -> None:
        """Verify that the repository satisfies all pre-turn gate checks."""
        result = validate_pre_turn_gate(ROOT)
        self.assertEqual(
            result["status"],
            "PASS",
            f"Pre-turn gate failed with issues: {result['issues']}",
        )
        checks = result["checks"]
        self.assertEqual(checks["hooks_configuration"]["status"], "PASS")
        self.assertEqual(checks["operating_contract"]["status"], "PASS")
        self.assertEqual(checks["runtime_boundary"]["status"], "PASS")
        self.assertEqual(checks["tier1_tools"]["status"], "PASS")
        self.assertEqual(checks["conformance_map"]["status"], "PASS")

    def test_hitl_ambiguity_autonomous_proceed_when_delta_gt_20(self) -> None:
        """When delta > 20%, the gate must select PROCEED_AUTONOMOUSLY."""
        options = [
            {"label": "Option A (Recommended)", "confidence_score": 0.85},
            {"label": "Option B", "confidence_score": 0.55},
        ]
        # Delta = 0.85 - 0.55 = 0.30 > 0.20
        eval_result = evaluate_hitl_ambiguity(options)
        self.assertFalse(eval_result["requires_hitl"])
        self.assertEqual(eval_result["action"], "PROCEED_AUTONOMOUSLY")
        self.assertAlmostEqual(eval_result["margin"], 0.30)
        self.assertEqual(eval_result["top_option"]["label"], "Option A (Recommended)")

    def test_hitl_ambiguity_surface_atomic_when_delta_le_20(self) -> None:
        """When delta <= 20%, the gate must require SURFACE_HITL_ATOMIC."""
        options = [
            {"label": "Option A", "confidence_score": 0.70},
            {"label": "Option B", "confidence_score": 0.60},
        ]
        # Delta = 0.70 - 0.60 = 0.10 <= 0.20
        eval_result = evaluate_hitl_ambiguity(options)
        self.assertTrue(eval_result["requires_hitl"])
        self.assertEqual(eval_result["action"], "SURFACE_HITL_ATOMIC")
        self.assertAlmostEqual(eval_result["margin"], 0.10)

    def test_post_turn_gate_rejects_unnecessary_hitl_interruption(self) -> None:
        """Post-turn gate fails if a turn surfaced HITL when delta was > 20%."""
        options = [
            {"label": "Option A (Strong)", "confidence_score": 0.90},
            {"label": "Option B (Weak)", "confidence_score": 0.50},
        ]
        response_with_unnecessary_hitl = "### HITL Decision: Please choose Option A or Option B."
        result = validate_post_turn_gate(
            repo_root=ROOT,
            candidate_response=response_with_unnecessary_hitl,
            candidate_options=options,
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("Must proceed autonomously" in issue for issue in result["issues"]))

    def test_post_turn_gate_passes_on_compliant_autonomous_resolution(self) -> None:
        """Post-turn gate passes when delta > 20% and agent proceeded autonomously."""
        options = [
            {"label": "Option A (Strong)", "confidence_score": 0.90},
            {"label": "Option B (Weak)", "confidence_score": 0.50},
        ]
        response_autonomous = "Proceeded autonomously with Option A under audit receipt."
        result = validate_post_turn_gate(
            repo_root=ROOT,
            candidate_response=response_autonomous,
            candidate_options=options,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["issues"], [])

    def test_agent_operating_contract_concise_memory_bound(self) -> None:
        """Verify AGENTS.md adheres to concise memory guidance (<= 200 lines) and contains core invariants."""
        result = validate_agent_operating_contract(ROOT)
        self.assertEqual(result["status"], "PASS", f"Operating contract issues: {result['issues']}")
        self.assertLessEqual(result["line_count"], 200, "AGENTS.md must stay under 200 lines per memory guidance.")
        self.assertGreater(result["line_count"], 50)

    def test_scratchpad_transparency_validation_passes_on_compliant_response(self) -> None:
        """Verify that a compliant scratchpad response passes post-turn validation."""
        sample_response = """
### 🧠 Agent Reasoning Scratchpad & Execution Telemetry
- **Active Model & Provider**: gpt-5.6-luna (medium) | Antigravity Runtime | Tier: FRONTIER_HIGH_REASONING
- **Invocation Role**: Governance SSOT Integration
- **Cognitive Breakdown & Thinking**:
  - *Context & Constraints*: Enforce strict lifecycle hooks.
  - *Hypotheses & Evaluation*: Tested hook matches.
  - *Risk & Failure Modes*: Checked AGENTS.md line count boundary.
- **Reasoning Steps**:
  1. Register lifecycle hooks in .agents/hooks.json.
  2. Validate test suite execution.
- **API & Tool Invocations**:
  - Tool: `run_command` | Args: `pytest` | Status: `SUCCESS` | Outcome: `All tests passed`

Response content delivered cleanly.
"""
        eval_result = validate_scratchpad_transparency(sample_response)
        self.assertEqual(eval_result["status"], "PASS")
        self.assertTrue(eval_result["has_header"])
        self.assertTrue(eval_result["has_model_telemetry"])
        self.assertTrue(eval_result["has_cognitive_thinking"])
        self.assertTrue(eval_result["has_reasoning_steps"])
        self.assertTrue(eval_result["has_tool_invocations"])
        self.assertEqual(eval_result["issues"], [])

    def test_scratchpad_transparency_validation_fails_when_pillars_missing(self) -> None:
        """Verify that omitting required pillars fails post-turn scratchpad validation."""
        incomplete_response = """
### 🧠 Agent Reasoning Scratchpad & Execution Telemetry
- **Reasoning Steps**:
  1. Do something without thinking or model telemetry.
"""
        eval_result = validate_scratchpad_transparency(incomplete_response)
        self.assertEqual(eval_result["status"], "FAIL")
        self.assertFalse(eval_result["has_model_telemetry"])
        self.assertFalse(eval_result["has_cognitive_thinking"])
        self.assertFalse(eval_result["has_tool_invocations"])
        self.assertTrue(any("Pillar 1" in issue for issue in eval_result["issues"]))
        self.assertTrue(any("Pillar 2" in issue for issue in eval_result["issues"]))
        self.assertTrue(any("Pillar 4" in issue for issue in eval_result["issues"]))


if __name__ == "__main__":
    unittest.main()
