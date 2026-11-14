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
            Path("resume_graph_engine/src/apps_rg/runtime/judges/bullet_pool_claude_selector.py"),
            Path("resume_graph_engine/src/apps_rg/runtime/judges/bullet_pool_claude_selector/__init__.py"),
            Path("resume_graph_engine/src/apps_rg/runtime/judges/bullet_pool_claude_selector/scoring.py"),
            Path("infrastructure/sdks_mcps/gemini_client/transport.py"),
            Path("tools/run_luna_antipattern_review/worker.py"),
        ]
        for p in exempt_paths:
            self.assertTrue(is_path_exempt(str(p)), f"Expected '{p}' to be exempt")
            violations = check_path_model_neutrality(p, ROOT)
            self.assertEqual(violations, [], f"Expected '{p}' to pass neutrality, got: {violations}")

    def test_exempt_package_rejects_new_prohibited_child_tokens(self) -> None:
        """Child submodules under exempt packages must not smuggle new prohibited model tokens."""
        bad_child = Path("resume_graph_engine/src/apps_rg/runtime/judges/bullet_pool_claude_selector/gpt4_override.py")
        self.assertFalse(is_path_exempt(str(bad_child)))
        violations = check_path_model_neutrality(bad_child, ROOT)
        self.assertTrue(len(violations) > 0)

    def test_catalog_package_submodules_inherit_catalog_exemption(self) -> None:
        """Extracted core_model_catalog submodules inherit canonical model-catalog literal exemption."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            cat_sub = repo / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "core_model_catalog" / "tiers.py"
            cat_sub.parent.mkdir(parents=True, exist_ok=True)
            cat_sub.write_text('DEFAULT_MODEL = "claude-sonnet-4-6"\n', encoding="utf-8")
            self.assertEqual(check_file_model_neutrality(cat_sub, repo), [])


if __name__ == "__main__":
    unittest.main()
