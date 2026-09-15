#!/usr/bin/env python3
"""Unit tests for model-neutral artifact naming and code linter."""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.lint_model_neutral_naming import (
    check_file_model_neutrality,
    check_path_model_neutrality,
    is_path_exempt,
)

ROOT = Path(__file__).resolve().parents[1]


class ModelNeutralNamingTests(unittest.TestCase):
    def test_compliant_filenames_pass(self) -> None:
        """Domain-functional filenames without model identifiers pass validation."""
        valid_paths = [
            Path("reports/system_architecture_overview.md"),
            Path("plans/cache_optimization_wave1.md"),
            Path("agentic_core/runtime/session_manager.py"),
            Path("docs/decision_record.md"),
        ]
        for p in valid_paths:
            violations = check_path_model_neutrality(p, ROOT)
            self.assertEqual(violations, [], f"Path '{p}' should be compliant, got: {violations}")

    def test_model_branded_filename_rejected(self) -> None:
        """Filenames embedding proprietary model identifiers fail closed."""
        violating_paths = [
            Path("reports/gpt4_refactor_specification.md"),
            Path("docs/luna_performance_audit.md"),
            Path("plans/claude_agent_dispatch.md"),
            Path("output/gemini_pro_evaluation.json"),
        ]
        for p in violating_paths:
            violations = check_path_model_neutrality(p, ROOT)
            self.assertTrue(len(violations) > 0, f"Expected violations for path '{p}', but passed.")

    def test_exempt_paths_pass(self) -> None:
        """Exempted paths (e.g. archive, temporary tooling scripts) are skipped."""
        exempt_paths = [
            Path("archive/legacy_report.md"),
            Path("docs/archive/old_model.md"),
            Path("tools/run_luna_antipattern_review.py"),
            Path("plans/live-llm-enforcement-wave1-b7d14e.md"),
        ]
        for p in exempt_paths:
            self.assertTrue(is_path_exempt(str(p)))
            violations = check_path_model_neutrality(p, ROOT)
            self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
