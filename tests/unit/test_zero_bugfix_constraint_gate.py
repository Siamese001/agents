"""Unit tests for tools/zero_bugfix_constraint_gate.py (INV-ZERO-BUGFIX-BLAST-RADIUS-CAP)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.validate_turn_gates import validate_pre_turn_gate
from tools.zero_bugfix_constraint_gate import ROOT, validate_zero_bugfix_constraint_floor


class TestZeroBugfixConstraintGate(unittest.TestCase):
    """Verify mechanical anti-regression checks for zero bug-fix and blast-radius caps."""

    def test_live_repository_passes_zero_bugfix_constraint_floor(self) -> None:
        res = validate_zero_bugfix_constraint_floor(ROOT)
        self.assertEqual(res["status"], "PASS", f"Unexpected issues: {res['issues']}")
        self.assertEqual(res["issues"], [])

        pre = validate_pre_turn_gate(ROOT)
        self.assertIn("zero_bugfix_constraints", pre["checks"])
        self.assertEqual(pre["checks"]["zero_bugfix_constraints"]["status"], "PASS")

    def test_detects_reintroduced_plan_word_cap_ghost_hook_and_deferral_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            gov_dir = tmp_root / "config" / "governance"
            rules_dir = tmp_root / ".agents" / "rules"
            gov_dir.mkdir(parents=True)
            rules_dir.mkdir(parents=True)

            (gov_dir / "policy_registry.yaml").write_text(
                "policies:\n"
                "  - id: INV-WAVE-PLAN-MAX-WORDS\n"
                "    threshold: 1000\n"
                "  - id: INV-ZERO-BUGFIX-BLAST-RADIUS-CAP\n"
                "    threshold: 1\n",
                encoding="utf-8",
            )
            (tmp_root / "AGENTS.md").write_text("# Agent Guidance\nLegacy T2/T3 cap only.\n", encoding="utf-8")
            (rules_dir / "work-item-classification.md").write_text(
                "| `BUG_DEFERRED` | T2 | Multi-file | spawn_task |\n",
                encoding="utf-8",
            )
            (rules_dir / "constitutional.md").write_text(
                "Audit: post_agent_adg_audit.py\n- `grep_search` permitted only to confirm literals\n",
                encoding="utf-8",
            )

            res = validate_zero_bugfix_constraint_floor(tmp_root)
            self.assertEqual(res["status"], "FAIL")
            joined = "\n".join(res["issues"])
            self.assertIn("INV-WAVE-PLAN-MAX-WORDS must remain 0", joined)
            self.assertIn("INV-ZERO-BUGFIX-BLAST-RADIUS-CAP must remain 0", joined)
            self.assertIn("Zero Blast-Radius Ceiling", joined)
            self.assertIn("BUG_DEFERRED", joined)
            self.assertIn("post_agent_adg_audit.py", joined)
            self.assertIn("grep_search", joined)


if __name__ == "__main__":
    unittest.main()
