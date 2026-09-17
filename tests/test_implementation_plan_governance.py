#!/usr/bin/env python3
"""Unit tests for wave-based implementation plan governance and validator.

Verifies:
1. Compliant wave-based implementation plans pass validation.
2. Flat or un-wavered plans are rejected with actionable diagnostics.
3. Missing mandatory subsections (Milestones, Acceptance Criteria, Receipt Gate) fail.
4. Non-consecutive wave numbering fails closed.
5. Legacy exemptions are respected.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.validate_implementation_plan import (
    DEFAULT_LEGACY_EXEMPTIONS,
    extract_wave_summary_entries,
    get_active_plan_file,
    render_markdown_wave_summary_table,
    render_wave_summary_table,
    validate_file,
    validate_plan_content,
)


ROOT = Path(__file__).resolve().parents[1]


class ImplementationPlanGovernanceTests(unittest.TestCase):
    def test_compliant_wave_plan_passes(self) -> None:
        """Verify that a properly structured wave-based plan passes validation."""
        valid_plan = """# Implementation Plan: Example Feature

## Implementation Status Table

| Wave / Component | Description | Status | Deliverables / Receipts |
|---|---|---|---|
| Wave 1: Core Foundation & Tooling | Initial tool and config updates | COMPLETED | `tools/example_tool.py` |
| Wave 2: Downstream Integration | Integration into agentic core | IN_PROGRESS | `agentic_core/integration.py` |

## Wave 1: Core Foundation & Tooling
### Milestones & Deliverables
- [NEW] `tools/example_tool.py`
- [MODIFY] `config/settings.py`

### Acceptance Criteria
- Unit tests pass with 100% code coverage.
- Linter reports zero warnings.

### Runtime Receipt & Completion Gate
- Execution receipt generated via `pytest tests/test_example.py --timeout=60`.
- Gate: Wave 2 cannot start until receipt is validated.

## Wave 2: Downstream Integration
### Milestones & Deliverables
- [NEW] `agentic_core/integration.py`

### Acceptance Criteria
- Integration test suite passes cleanly.

### Runtime Receipt & Completion Gate
- Verification receipt emitted.
"""
        is_valid, errors = validate_plan_content(valid_plan, "valid_plan.md")
        self.assertTrue(is_valid, f"Plan should be valid, but failed with: {errors}")
        self.assertEqual(len(errors), 0)

    def test_flat_monolithic_plan_is_rejected(self) -> None:
        """Verify that plans without wave decomposition are rejected."""
        flat_plan = """# Unstructured Implementation Plan

## Proposed Changes
We will modify several files in the repository to add features.
- Edit file A
- Edit file B

## Verification Plan
Run tests.
"""
        is_valid, errors = validate_plan_content(flat_plan, "flat_plan.md")
        self.assertFalse(is_valid)
        self.assertTrue(
            any("Implementation plan must be wave-based" in err for err in errors),
            f"Expected wave-based error message, got: {errors}",
        )

    def test_missing_title_is_rejected(self) -> None:
        """Verify that plans without a top-level title are rejected."""
        no_title_plan = """## Wave 1: Initial Setup
### Milestones & Deliverables
- [NEW] `file.py`

### Acceptance Criteria
- Tests pass.

### Runtime Receipt & Completion Gate
- Receipt verified.
"""
        is_valid, errors = validate_plan_content(no_title_plan, "no_title.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("Missing required top-level title" in err for err in errors))

    def test_missing_milestones_is_rejected(self) -> None:
        """Verify that waves missing Milestones & Deliverables are rejected."""
        missing_milestones = """# Plan Title

## Wave 1: Setup
### Acceptance Criteria
- Criteria met.

### Runtime Receipt & Completion Gate
- Receipt confirmed.
"""
        is_valid, errors = validate_plan_content(missing_milestones, "missing_milestones.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("Milestones & Deliverables" in err for err in errors))

    def test_empty_milestones_items_is_rejected(self) -> None:
        """Verify that wave plans with empty milestones sections fail."""
        empty_milestones = """# Plan Title

## Wave 1: Setup
### Milestones & Deliverables
No items specified here just free text with no deliverables.

### Acceptance Criteria
- Criteria met.

### Runtime Receipt & Completion Gate
- Receipt confirmed.
"""
        is_valid, errors = validate_plan_content(empty_milestones, "empty_milestones.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("must contain at least one itemized output" in err for err in errors))

    def test_missing_acceptance_criteria_is_rejected(self) -> None:
        """Verify that waves missing Acceptance Criteria are rejected."""
        missing_criteria = """# Plan Title

## Wave 1: Setup
### Milestones & Deliverables
- [NEW] `file.py`

### Runtime Receipt & Completion Gate
- Receipt confirmed.
"""
        is_valid, errors = validate_plan_content(missing_criteria, "missing_criteria.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("Acceptance Criteria" in err for err in errors))

    def test_missing_runtime_receipt_is_rejected(self) -> None:
        """Verify that waves missing Runtime Receipt / Completion Gate fail."""
        missing_receipt = """# Plan Title

## Wave 1: Setup
### Milestones & Deliverables
- [NEW] `file.py`

### Acceptance Criteria
- Passes.
"""
        is_valid, errors = validate_plan_content(missing_receipt, "missing_receipt.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("Runtime Receipt & Completion Gate" in err for err in errors))

    def test_non_sequential_wave_numbering_is_rejected(self) -> None:
        """Verify that skipping wave numbers fails validation."""
        skipped_wave = """# Plan Title

## Wave 1: Setup
### Milestones & Deliverables
- [NEW] `file.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.

## Wave 3: Skipped Wave 2
### Milestones & Deliverables
- [NEW] `file2.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.
"""
        is_valid, errors = validate_plan_content(skipped_wave, "skipped_wave.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("Non-sequential wave numbering" in err for err in errors))

    def test_legacy_exemptions_respected(self) -> None:
        """Verify that legacy plans configured in exemptions pass without error."""
        exempt_file = ROOT / "plans" / "core-judge-panel-harness-f3c8d1.md"
        if exempt_file.is_file():
            is_valid, errors = validate_file(exempt_file, legacy_exemptions=DEFAULT_LEGACY_EXEMPTIONS)
            self.assertTrue(is_valid)
            self.assertTrue(any("[EXEMPT]" in e for e in errors))

    def test_plan_with_valid_status_table_passes(self) -> None:
        """Verify that a plan with a valid implementation status table passes."""
        plan = """# Implementation Plan: Status Table Feature

## Status Table

| Wave | Scope | Status | Deliverables |
|---|---|---|---|
| Wave 1 | Setup and scaffolding | COMPLETED | `tools/setup.py` |
| Wave 2 | Core functionality | IN_PROGRESS | `tools/core.py` |
| Wave 3 | Validation | PENDING | Test results |

## Wave 1: Setup
### Milestones & Deliverables
- [NEW] `tools/setup.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.

## Wave 2: Core
### Milestones & Deliverables
- [NEW] `tools/core.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.

## Wave 3: Validation
### Milestones & Deliverables
- [NEW] `tests/test_core.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.
"""
        is_valid, errors = validate_plan_content(plan, "status_table_plan.md")
        self.assertTrue(is_valid, f"Expected valid plan, got errors: {errors}")

    def test_missing_status_table_is_rejected(self) -> None:
        """Verify that a wave plan lacking an implementation status table is rejected."""
        no_table_plan = """# Plan Without Status Table

## Wave 1: Setup
### Milestones & Deliverables
- [NEW] `tools/setup.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.
"""
        is_valid, errors = validate_plan_content(no_table_plan, "no_table.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("Missing mandatory Implementation Status Table" in err for err in errors))

    def test_status_table_missing_columns_is_rejected(self) -> None:
        """Verify that a status table missing required columns is rejected."""
        missing_cols_plan = """# Plan With Incomplete Table

## Status Table
| Wave | Deliverables |
|---|---|
| Wave 1 | `tools/setup.py` |

## Wave 1: Setup
### Milestones & Deliverables
- [NEW] `tools/setup.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.
"""
        is_valid, errors = validate_plan_content(missing_cols_plan, "missing_cols.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("missing required column(s)" in err for err in errors))

    def test_status_table_invalid_status_is_rejected(self) -> None:
        """Verify that a status table with unrecognized status values is rejected."""
        invalid_status_plan = """# Plan With Bad Status

## Status Table
| Wave | Description | Status |
|---|---|---|
| Wave 1 | Core implementation | MAYBE_LATER |

## Wave 1: Core
### Milestones & Deliverables
- [NEW] `tools/core.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.
"""
        is_valid, errors = validate_plan_content(invalid_status_plan, "bad_status.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("Invalid status 'MAYBE_LATER'" in err for err in errors))

    def test_status_table_missing_declared_wave_is_rejected(self) -> None:
        """Verify that omitting a declared wave from the status table is rejected."""
        missing_wave_in_table = """# Plan Missing Wave In Table

## Status Table
| Wave | Description | Status |
|---|---|---|
| Wave 1 | Wave 1 scope | COMPLETED |

## Wave 1: First
### Milestones & Deliverables
- [NEW] `tools/first.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.

## Wave 2: Second
### Milestones & Deliverables
- [NEW] `tools/second.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Passes.
"""
        is_valid, errors = validate_plan_content(missing_wave_in_table, "missing_wave.md")
        self.assertFalse(is_valid)
        self.assertTrue(
            any(
                "Wave 2 (declared at line" in err and "missing from the Implementation Status Table" in err
                for err in errors
            )
        )

    def test_plan_with_unapproved_model_token_is_rejected(self) -> None:
        """Verify that plans referencing unapproved model tokens like gpt-6.5-luna fail validation."""
        bad_model_plan = """# Plan With Unapproved Model
## Implementation Status Table
| Wave | Description | Status | Deliverables / Receipts |
|---|---|---|---|
| Wave 1: Evaluation | Run gpt-6.5-luna evaluation | COMPLETED | `receipt.json` |

## Wave 1: Evaluation
### Milestones & Deliverables
- [NEW] `receipt.json`

### Acceptance Criteria
- Run under gpt-6.5-luna evaluator.

### Runtime Receipt & Completion Gate
- Verification receipt emitted.
"""
        is_valid, errors = validate_plan_content(bad_model_plan, "bad_model.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("References unapproved model token 'gpt-6.5-luna'" in err for err in errors))

    def test_plan_with_approved_model_token_passes(self) -> None:
        """Verify that plans referencing approved canonical model tokens like gpt-5.6-luna pass validation."""
        good_model_plan = """# Plan With Approved Model
## Implementation Status Table
| Wave | Description | Status | Deliverables / Receipts |
|---|---|---|---|
| Wave 1: Evaluation | Run gpt-5.6-luna evaluation | COMPLETED | `receipt.json` |

## Wave 1: Evaluation
### Milestones & Deliverables
- [NEW] `receipt.json`

### Acceptance Criteria
- Run under gpt-5.6-luna evaluator.

### Runtime Receipt & Completion Gate
- Verification receipt emitted.
"""
        is_valid, errors = validate_plan_content(good_model_plan, "good_model.md")
        self.assertTrue(is_valid, f"Plan should pass, but failed with: {errors}")

    def test_extract_wave_summary_entries_from_status_table(self) -> None:
        """Verify extraction of wave number, description, status, and check/open status."""
        plan_text = """# Test Plan
## Implementation Status Table
| Wave / Component | Description / Scope | Status | Deliverables / Receipts |
|---|---|---|---|
| Wave 1: Core Foundation | Build foundation | COMPLETED | `out.py` |
| Wave 2: Integration | Connect components | IN_PROGRESS | `int.py` |
| Wave 3: Verification | Full test sweep | PLANNED | `test.py` |
"""
        entries, issues = extract_wave_summary_entries(plan_text)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["wave"], "Wave 1")
        self.assertEqual(entries[0]["description"], "Build foundation")
        self.assertEqual(entries[0]["status"], "COMPLETED")
        self.assertEqual(entries[0]["check_open"], "[x] CHECK")
        self.assertTrue(entries[0]["is_checked"])

        self.assertEqual(entries[1]["wave"], "Wave 2")
        self.assertEqual(entries[1]["check_open"], "[ ] OPEN")
        self.assertFalse(entries[1]["is_checked"])

        self.assertEqual(entries[2]["wave"], "Wave 3")
        self.assertEqual(entries[2]["check_open"], "[ ] OPEN")
        self.assertFalse(entries[2]["is_checked"])

    def test_render_wave_summary_table_contains_all_required_columns(self) -> None:
        """Verify rendered table includes Wave #, Description / Scope, Status, and Check/Open."""
        entries = [
            {"wave": "Wave 1", "description": "Foundation", "status": "COMPLETED", "check_open": "[x] CHECK"},
            {"wave": "Wave 2", "description": "Integration", "status": "PLANNED", "check_open": "[ ] OPEN"},
        ]
        table_output = render_wave_summary_table("sample_plan.md", entries)
        self.assertIn("Wave #", table_output)
        self.assertIn("Description / Scope", table_output)
        self.assertIn("Status", table_output)
        self.assertIn("Check/Open", table_output)
        self.assertIn("[x] CHECK", table_output)
        self.assertIn("[ ] OPEN", table_output)

    def test_get_active_plan_file_finds_recent_plan(self) -> None:
        """Verify get_active_plan_file returns a valid markdown plan file."""
        active = get_active_plan_file(ROOT)
        self.assertIsNotNone(active)
        self.assertTrue(active.is_file())
        self.assertTrue(active.name.endswith(".md"))

    def test_render_markdown_wave_summary_table_formats_gfm(self) -> None:
        """Verify render_markdown_wave_summary_table generates valid GitHub-flavored markdown table."""
        entries = [
            {"wave": "Wave 1", "description": "Foundation", "status": "COMPLETED", "check_open": "[x] CHECK"},
            {"wave": "Wave 2", "description": "Integration", "status": "PENDING", "check_open": "[ ] OPEN"},
        ]
        md_table = render_markdown_wave_summary_table("test_plan.md", entries)
        self.assertIn("### Wave Summary Table: test_plan.md", md_table)
        self.assertIn("| Wave # | Description / Scope | Status | Check/Open |", md_table)
        self.assertIn("| Wave 1 | Foundation | COMPLETED | [x] CHECK |", md_table)
        self.assertIn("| Wave 2 | Integration | PENDING | [ ] OPEN |", md_table)

    def test_get_active_plan_file_respects_env_variable(self) -> None:
        """Verify get_active_plan_file discovers plan via ANTIGRAVITY_ARTIFACTS_DIR env."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            plan_path = Path(tmp_dir) / "implementation_plan.md"
            plan_path.write_text("# Temp Plan\n", encoding="utf-8")
            old_val = os.environ.get("ANTIGRAVITY_ARTIFACTS_DIR")
            try:
                os.environ["ANTIGRAVITY_ARTIFACTS_DIR"] = tmp_dir
                discovered = get_active_plan_file(ROOT)
                self.assertEqual(discovered, plan_path)
            finally:
                if old_val is not None:
                    os.environ["ANTIGRAVITY_ARTIFACTS_DIR"] = old_val
                else:
                    os.environ.pop("ANTIGRAVITY_ARTIFACTS_DIR", None)


if __name__ == "__main__":
    unittest.main()

