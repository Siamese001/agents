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
    validate_file,
    validate_plan_content,
)

ROOT = Path(__file__).resolve().parents[1]


class ImplementationPlanGovernanceTests(unittest.TestCase):
    def test_compliant_wave_plan_passes(self) -> None:
        """Verify that a properly structured wave-based plan passes validation."""
        valid_plan = """# Implementation Plan: Example Feature

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


if __name__ == "__main__":
    unittest.main()
