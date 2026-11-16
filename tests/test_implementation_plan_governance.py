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
### Objective & Scope
Initial tool and config updates.

### Milestones & Deliverables
- [NEW] `tools/example_tool.py`
- [MODIFY] `config/settings.py`

### Acceptance Criteria
- Unit tests pass with 100% code coverage.
- Linter reports zero warnings.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_example.py --timeout=60
- Input: tests/test_example.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: non-zero exit code
- Record: receipts/wave1.json

## Wave 2: Downstream Integration
### Objective & Scope
Integration into agentic core.

### Milestones & Deliverables
- [NEW] `agentic_core/integration.py`

### Acceptance Criteria
- Integration test suite passes cleanly.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_integration.py --timeout=60
- Input: tests/test_integration.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: non-zero exit code
- Record: receipts/wave2.json
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
### Objective & Scope
Setup and scaffolding.

### Milestones & Deliverables
- [NEW] `tools/setup.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_setup.py --timeout=60
- Input: tests/test_setup.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/setup.json

## Wave 2: Core
### Objective & Scope
Core functionality.

### Milestones & Deliverables
- [NEW] `tools/core.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_core.py --timeout=60
- Input: tests/test_core.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/core.json

## Wave 3: Validation
### Objective & Scope
Validation suite.

### Milestones & Deliverables
- [NEW] `tests/test_core.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_val.py --timeout=60
- Input: tests/test_val.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/val.json
"""
        is_valid, errors = validate_plan_content(plan, "status_table_plan.md")
        self.assertTrue(is_valid, f"Expected valid plan, got errors: {errors}")

    def test_valid_wave_plan_without_status_table_passes(self) -> None:
        """Verify that a compliant wave plan without an implementation status table passes."""
        no_table_plan = """# Plan Without Status Table

## Wave 1: Setup
### Objective & Scope
Setup and scaffolding.

### Milestones & Deliverables
- [NEW] `tools/setup.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_setup.py --timeout=60
- Input: tests/test_setup.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/setup.json
"""
        is_valid, errors = validate_plan_content(no_table_plan, "no_table.md")
        self.assertTrue(is_valid, f"Plan without status table should pass, got: {errors}")
        self.assertEqual(len(errors), 0)

    def test_status_table_missing_columns_is_rejected(self) -> None:
        """Verify that a status table missing required columns is rejected."""
        missing_cols_plan = """# Plan With Incomplete Table

## Status Table
| Wave | Deliverables |
|---|---|
| Wave 1 | `tools/setup.py` |

## Wave 1: Setup
### Objective & Scope
Setup.

### Milestones & Deliverables
- [NEW] `tools/setup.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_setup.py --timeout=60
- Input: tests/test_setup.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/setup.json
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
### Objective & Scope
Core.

### Milestones & Deliverables
- [NEW] `tools/core.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_core.py --timeout=60
- Input: tests/test_core.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/core.json
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
### Objective & Scope
First.

### Milestones & Deliverables
- [NEW] `tools/first.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_first.py --timeout=60
- Input: tests/test_first.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/first.json

## Wave 2: Second
### Objective & Scope
Second.

### Milestones & Deliverables
- [NEW] `tools/second.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_second.py --timeout=60
- Input: tests/test_second.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/second.json
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
### Objective & Scope
Run gpt-6.5-luna evaluation.

### Milestones & Deliverables
- [NEW] `receipt.json`

### Acceptance Criteria
- Run under gpt-6.5-luna evaluator.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_eval.py --timeout=60
- Input: tests/test_eval.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/receipt.json
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
### Objective & Scope
Run gpt-5.6-luna evaluation.

### Milestones & Deliverables
- [NEW] `receipt.json`

### Acceptance Criteria
- Run under gpt-5.6-luna evaluator.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_eval.py --timeout=60
- Input: tests/test_eval.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipts/receipt.json
"""
        is_valid, errors = validate_plan_content(good_model_plan, "good_model.md")
        self.assertTrue(is_valid, f"Plan should pass, but failed with: {errors}")

    def test_missing_objective_is_rejected(self) -> None:
        """Verify that waves missing Objective & Scope are rejected."""
        missing_objective = """# Plan Title

## Wave 1: Setup
### Milestones & Deliverables
- [NEW] `file.py`

### Acceptance Criteria
- Criteria met.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_file.py --timeout=60
- Input: tests/test_file.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipt.json
"""
        is_valid, errors = validate_plan_content(missing_objective, "missing_objective.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("Objective & Scope" in err for err in errors))

    def test_missing_evidence_fields_is_rejected(self) -> None:
        """Verify that waves missing execution evidence fields in completion gate fail."""
        missing_evidence = """# Plan Title

## Wave 1: Setup
### Objective & Scope
Setup tools.

### Milestones & Deliverables
- [NEW] `file.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_file.py
- Input: tests/test_file.py
"""
        is_valid, errors = validate_plan_content(missing_evidence, "missing_evidence.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("completion gate must specify:" in err for err in errors))

    def test_word_count_exceeds_1000_is_accepted_without_artificial_cap(self) -> None:
        """Verify that large multi-wave refactoring plans (>1000 words) pass without artificial word cap."""
        long_body = "word " * 1250
        long_plan = f"""# Long Plan Title

## Wave 1: Large Cross-Repo Refactoring Scope
### Objective & Scope
{long_body}

### Milestones & Deliverables
- [NEW] `tools/large.py`

### Acceptance Criteria
- Passes.

### Runtime Receipt & Completion Gate
- Run: pytest tests/test_large.py --timeout=60
- Input: tests/test_large.py
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: receipt.json
"""
        is_valid, errors = validate_plan_content(long_plan, "long_plan.md")
        self.assertTrue(is_valid, f"Expected large refactoring plan to pass, got: {errors}")
        self.assertEqual(errors, [])

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

    def test_narrow_symptom_only_section_plan_is_rejected(self) -> None:
        """Verify INV-HOLISTIC-PIPELINE-PLANNING rejects section/bullet plans that omit upstream C0 allocation or downstream X2 gates."""
        symptom_only_plan = """# Bullet Naturalness Post-Processing Plan

## Wave 1: Section Authority & Repair Tweaks
### Objective & Scope
Patch downstream bullet repair dictionaries in role_episode_lane.py and ibm_bullets_lane.py.

### Milestones & Deliverables
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/ibm_bullets_lane.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/section_authority_repairs.py`

### Acceptance Criteria
- Local bullet repair strings sound less repetitive.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/pytest resume_graph_engine/tests/unit/apps_rg/test_role_episode_lane.py -v --timeout=60
- Input: role_episode_lane.py fixtures
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/wave1_symptom_patch.json
"""
        is_valid, errors = validate_plan_content(symptom_only_plan, "symptom_only_plan.md")
        self.assertFalse(is_valid)
        self.assertTrue(
            any("INV-HOLISTIC-PIPELINE-PLANNING" in err for err in errors),
            f"Expected INV-HOLISTIC-PIPELINE-PLANNING error, got: {errors}",
        )
        self.assertTrue(
            any("Upstream Producer/Allocation stage" in err for err in errors),
            f"Expected missing Upstream Producer/Allocation diagnostic, got: {errors}",
        )
        self.assertTrue(
            any("Downstream Cross-Section/X2 Validation stage" in err for err in errors),
            f"Expected missing Downstream Cross-Section/X2 diagnostic, got: {errors}",
        )

    def test_section_plan_missing_upstream_producer_is_rejected(self) -> None:
        """Verify INV-HOLISTIC-PIPELINE-PLANNING rejects plans that include X2 validators but omit upstream C0 allocation."""
        missing_upstream_plan = """# Bullet Naturalness and X2 Gate Plan

## Wave 1: Section Repairs and X2 Validator Tweaks
### Objective & Scope
Update role_episode_lane.py and narrative_quality_x2.py without checking C0 allocation.

### Milestones & Deliverables
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/validators/narrative_quality_x2.py`

### Acceptance Criteria
- Narrative echo repairs pass.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/pytest resume_graph_engine/tests/unit/apps_rg/test_narrative_quality_x2.py -v --timeout=60
- Input: narrative_quality_x2.py fixtures
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/wave1_no_upstream.json
"""
        is_valid, errors = validate_plan_content(missing_upstream_plan, "missing_upstream.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("INV-HOLISTIC-PIPELINE-PLANNING" in err for err in errors))
        self.assertTrue(any("Upstream Producer/Allocation stage" in err for err in errors))
        self.assertFalse(any("Downstream Cross-Section/X2 Validation stage" in err for err in errors))

    def test_holistic_pipeline_plan_with_upstream_c0_and_downstream_x2_passes(self) -> None:
        """Verify INV-HOLISTIC-PIPELINE-PLANNING passes when upstream C0 FactAnchor allocation and downstream X2 validation are both addressed."""
        holistic_plan = """# Holistic C0.3 FactAnchor, Section Bullet Generation, and X2 Gate Realignment Plan

## Executive Architectural Defense
- What Stays Unchanged: `quad_graph_retriever.py` Stage-1 4-channel hybrid retrieval math requires zero changes.
- What Realigns: Stage-2 `resume_graph_allocation.py` projects structured `FactAnchor` with `resolved_raw_chunk`, Stage-3 `role_episode_lane.py` and `ibm_bullets_lane.py` consume `FactAnchor` directly, and Stage-4 `cross_section_x2.py` and `bullet_quality_floor_x2.py` enforce 18-word floor, 60% stem grounding, and max-2-gerund rhythm.

## Wave 1: C0.3 FactAnchor Projection & Disjoint Partitioning
### Objective & Scope
Attach structured `FactAnchor` in `resume_graph_allocation.py` and bind `role_episode_lane.py` and `ibm_bullets_lane.py`.

### Milestones & Deliverables
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/c0/resume_graph_allocation.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/ibm_bullets_lane.py`

### Acceptance Criteria
- 100% of C0.3 assignments emit `FactAnchor` with zero overview-vs-bullet `fact_id` overlap.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/pytest tests/unit/resume_graph_engine/test_c0_resume_graph_allocation.py -v --timeout=60
- Input: C0.3 allocation fixtures
- Expected: 0 failures
- Verify independently: Inspect serialized C0.3 allocation JSON for `fact_anchor.resolved_raw_chunk`
- Fail if: exit code != 0
- Record: artifacts/receipts/wave1_c0_fact_anchor.json

## Wave 2: X2 Quality Floor & Cross-Section Gate Unification
### Objective & Scope
Unify `bullet_fact_entailment.py`, `bullet_quality_floor_x2.py`, and `cross_section_x2.py` around the 18-word floor and 60% stem entailment.

### Milestones & Deliverables
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/reasoning/bullet_fact_entailment.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/validators/bullet_quality_floor_x2.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/aggregation/cross_section_x2.py`

### Acceptance Criteria
- Zero cross-section intent conflicts and all bullets meet >=18 words and <=2 gerunds.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/pytest tests/unit/resume_graph_engine/test_cross_section_x2.py -v --timeout=60
- Input: Assembled whole-resume bundle
- Expected: 0 failures
- Verify independently: Inspect X2 evaluation JSON for zero intent conflicts
- Fail if: exit code != 0
- Record: artifacts/receipts/wave2_x2_gates.json
"""
        is_valid, errors = validate_plan_content(holistic_plan, "holistic_plan.md")
        self.assertTrue(is_valid, f"Holistic plan should pass, but failed with: {errors}")
        self.assertEqual(len(errors), 0)

    def test_section_plan_with_negated_stage_dismissal_is_rejected(self) -> None:
        """Verify INV-HOLISTIC-PIPELINE-PLANNING rejects plans that only mention upstream/downstream modules in negated dismissal prose."""
        negated_dismissal_plan = """# Bullet Repair Without Upstream Realignment Plan

## Wave 1: Section Repair Only
### Objective & Scope
Skip resume_graph_allocation.py and cross_section_x2.py completely and only patch role_episode_lane.py without checking C0 allocation or X2 validator.

### Milestones & Deliverables
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py`

### Acceptance Criteria
- Local bullet repair strings pass unit checks.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/pytest tests/unit/resume_graph_engine/test_role_episode_and_bullet_lanes.py -v --timeout=60
- Input: role_episode_lane.py fixtures
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/wave1_negated_dismissal.json
"""
        is_valid, errors = validate_plan_content(negated_dismissal_plan, "negated_dismissal.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("INV-HOLISTIC-PIPELINE-PLANNING" in err for err in errors))
        self.assertTrue(any("Upstream Producer/Allocation stage" in err for err in errors))
        self.assertTrue(any("Downstream Cross-Section/X2 Validation stage" in err for err in errors))

    def test_headline_and_executive_summary_lanes_require_holistic_spine(self) -> None:
        """Verify headline_lane.py and executive_summary_lane.py trigger INV-HOLISTIC-PIPELINE-PLANNING."""
        for lane_path, lane_name in (
            ("resume_graph_engine/src/apps_rg/runtime/sections/headline_lane.py", "headline_lane.py"),
            ("resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_lane.py", "executive_summary_lane.py"),
        ):
            narrow_plan = f"""# Narrow Lane Plan: {lane_name}

## Wave 1: Local Lane Adjustment
### Objective & Scope
Adjust {lane_name} phrasing locally.

### Milestones & Deliverables
- [MODIFY] `{lane_path}`

### Acceptance Criteria
- Output reads smoothly.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_lane.py -v --timeout=60
- Input: lane fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/narrow_{lane_name}.json
"""
            is_valid, errors = validate_plan_content(narrow_plan, f"narrow_{lane_name}.md")
            self.assertFalse(is_valid, f"Expected rejection for {lane_name}")
            self.assertTrue(any("INV-HOLISTIC-PIPELINE-PLANNING" in err for err in errors))
            self.assertTrue(any("Upstream Producer/Allocation stage" in err for err in errors))
            self.assertTrue(any("Downstream Cross-Section/X2 Validation stage" in err for err in errors))

        holistic_plan = """# Holistic Headline and Executive Summary Spine Plan

## Wave 1: Upstream C0, Section Lanes, and X2 Gate Alignment
### Objective & Scope
Align `resume_graph_allocation.py`, `headline_lane.py`, `executive_summary_lane.py`, `headline_x2.py`, and `executive_summary_x2.py`.

### Milestones & Deliverables
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/c0/resume_graph_allocation.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/headline_lane.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_lane.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/validators/headline_x2.py`
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/validators/executive_summary_x2.py`

### Acceptance Criteria
- Upstream FactAnchor and downstream X2 validators stay aligned.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_headline.py -v --timeout=60
- Input: headline and executive summary bundles
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/holistic_headline_exec.json
"""
        is_valid, errors = validate_plan_content(holistic_plan, "holistic_headline_exec.md")
        self.assertTrue(is_valid, f"Expected pass, got: {errors}")

    def test_outreach_engine_intermediate_lanes_require_holistic_spine(self) -> None:
        """Verify outreach_engine intermediate pipeline modules enforce briefing upstream and validator/repair downstream."""
        narrow_outreach = """# Narrow Outreach Sequence Plan

## Wave 1: Sequence Tweak
### Objective & Scope
Edit outreach sequence generation in compiler.py and touch_sequence.py.

### Milestones & Deliverables
- [MODIFY] `outreach_engine/src/apps_lic/pipeline/compiler.py`
- [MODIFY] `outreach_engine/src/apps_lic/pipeline/touch_sequence.py`

### Acceptance Criteria
- Outreach sequence text compiles.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest outreach_engine/tests/test_touch_sequence.py -v --timeout=60
- Input: sequence fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/narrow_outreach.json
"""
        is_valid, errors = validate_plan_content(narrow_outreach, "narrow_outreach.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("INV-HOLISTIC-PIPELINE-PLANNING" in err for err in errors))
        self.assertTrue(any("Upstream Briefing/Research stage" in err for err in errors))
        self.assertTrue(any("Downstream Outreach Validation/Repair stage" in err for err in errors))

        holistic_outreach = """# Holistic Outreach Spine Plan

## Wave 1: Briefing, Compiler/Sequence, and Validator/Repair Alignment
### Objective & Scope
Align `briefing_resolver.py`, `apps_research_bridge.py`, `compiler.py`, `touch_sequence.py`, `domain/validators.py`, and `domain/repair.py`.

### Milestones & Deliverables
- [MODIFY] `outreach_engine/src/apps_lic/pipeline/briefing_resolver.py`
- [MODIFY] `outreach_engine/src/apps_lic/integrations/apps_research_bridge.py`
- [MODIFY] `outreach_engine/src/apps_lic/pipeline/compiler.py`
- [MODIFY] `outreach_engine/src/apps_lic/pipeline/touch_sequence.py`
- [MODIFY] `outreach_engine/src/apps_lic/domain/validators.py`
- [MODIFY] `outreach_engine/src/apps_lic/domain/repair.py`

### Acceptance Criteria
- Upstream briefing signals and downstream outreach validators remain synchronized.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest outreach_engine/tests/test_touch_sequence.py -v --timeout=60
- Input: outreach sequence bundle
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/holistic_outreach.json
"""
        is_valid, errors = validate_plan_content(holistic_outreach, "holistic_outreach.md")
        self.assertTrue(is_valid, f"Expected holistic outreach plan to pass, got: {errors}")

    def test_apps_research_intermediate_engines_require_holistic_spine(self) -> None:
        """Verify apps_research engines require upstream retrieval/JD-intent and downstream handoff/contract alignment."""
        narrow_research = """# Narrow Research Brief Plan

## Wave 1: Company Brief Engine Adjustment
### Objective & Scope
Adjust synthesis in company_brief_engine.py and research_assembly_engine.py.

### Milestones & Deliverables
- [MODIFY] `apps_research/engines/company_brief_engine.py`
- [MODIFY] `apps_research/engines/research_assembly_engine.py`

### Acceptance Criteria
- Brief markdown renders cleanly.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest tests/test_company_brief.py -v --timeout=60
- Input: company fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/narrow_research.json
"""
        is_valid, errors = validate_plan_content(narrow_research, "narrow_research.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("INV-HOLISTIC-PIPELINE-PLANNING" in err for err in errors))
        self.assertTrue(any("Upstream Retrieval/JD-Intent stage" in err for err in errors))
        self.assertTrue(any("Downstream Handoff/Targeting-Brief stage" in err for err in errors))

        holistic_research = """# Holistic Research Engine Spine Plan

## Wave 1: Retrieval, Synthesis, and Handoff Contract Alignment
### Objective & Scope
Align `search_retrieval.py`, `jd_intent_coverage.py`, `company_brief_engine.py`, `research_assembly_engine.py`, `apps_rg_handoff.py`, and `apps_rg_targeting_brief_contract.py`.

### Milestones & Deliverables
- [MODIFY] `apps_research/integrations/search_retrieval.py`
- [MODIFY] `apps_research/types/jd_intent_coverage.py`
- [MODIFY] `apps_research/engines/company_brief_engine.py`
- [MODIFY] `apps_research/engines/research_assembly_engine.py`
- [MODIFY] `apps_research/integrations/apps_rg_handoff.py`
- [MODIFY] `apps_research/types/apps_rg_targeting_brief_contract.py`

### Acceptance Criteria
- Retrieval intent coverage and downstream apps_rg targeting handoff remain aligned.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest tests/test_company_brief.py -v --timeout=60
- Input: research fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/holistic_research.json
"""
        is_valid, errors = validate_plan_content(holistic_research, "holistic_research.md")
        self.assertTrue(is_valid, f"Expected holistic research plan to pass, got: {errors}")

    def test_monolith_split_milestone_requires_facade_submodule_boundary_and_tests(self) -> None:
        """Verify monolith split plans require facade, <=600-line submodules, ratchet/boundary, and test alignment."""
        incomplete_split = """# Split Headline Lane Monolith Plan

## Wave 1: Monolith Split
### Objective & Scope
Split `headline_lane.py` monolith into smaller modules.

### Milestones & Deliverables
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/headline_lane.py`: Split monolith into submodules.

### Acceptance Criteria
- Helper modules extracted cleanly.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_headline.py -v --timeout=60
- Input: headline fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit code != 0
- Record: artifacts/receipts/incomplete_split.json
"""
        is_valid, errors = validate_plan_content(incomplete_split, "incomplete_split.md")
        self.assertFalse(is_valid)
        self.assertTrue(any("INV-HOLISTIC-PIPELINE-PLANNING" in err for err in errors))
        self.assertTrue(any("re-export facade compatibility" in err for err in errors))
        self.assertTrue(any("SSOT/ratchet/boundary alignment" in err for err in errors))
        self.assertTrue(any("test coverage/monkeypatch alignment" in err for err in errors))

        complete_split = """# Holistic Monolith Decomposition Plan

## Wave 1: Decompose headline_lane.py Behind Re-Export Facade
### Objective & Scope
Decompose `headline_lane.py` into `<= 600`-line submodules behind an intact `ImportFrom` facade.

### Milestones & Deliverables
- [MODIFY] `resume_graph_engine/src/apps_rg/runtime/sections/headline_lane.py`: Split into `headline_lane/` submodules (`<= 600` lines) behind an `ImportFrom` re-export facade.
- [MODIFY] `config/governance/file_budgets_ratchet.json` and `config/governance/env_lookup_ratchet.json`: Clamp ratchets and update `centralization_registry.yaml` package prefixes.
- [MODIFY] `resume_graph_engine/tests/unit/apps_rg/test_headline_lane.py`: Align monkeypatches to public seams and satisfy `testing_gaps_auditor.py` module coverage.

### Acceptance Criteria
- Re-export facade keeps public imports intact and submodules remain <= 600 lines.

### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_headline_lane.py -v --timeout=60
- Input: headline lane fixture
- Expected: 0 failures
- Verify independently: .venv/bin/python tools/lint_file_budgets.py
- Fail if: exit code != 0
- Record: artifacts/receipts/complete_split.json
"""
        is_valid, errors = validate_plan_content(complete_split, "complete_split.md")
        self.assertTrue(is_valid, f"Expected complete monolith split plan to pass, got: {errors}")

    def test_existing_repo_plans_pass_expanded_validation(self) -> None:
        """Verify existing valid plans in plans/ continue passing validate_file."""
        for plan_name in (
            "sidecar-agents-decision-intel-parity-b7d4e1.md",
            "cost-token-budget-6ab7fb.md",
            "docx-and-runtime-optimization-b7e4c1.md",
            "selector-pin-optimization-c4a8e2.md",
        ):
            plan_path = ROOT / "plans" / plan_name
            if plan_path.is_file():
                is_valid, errors = validate_file(plan_path, repo_root=ROOT)
                self.assertTrue(is_valid, f"{plan_name} failed validation: {errors}")

    def test_fork_join_sharded_waves_and_shard_manifest_annex(self) -> None:
        """Verify Wave 2A / Wave 2B fork-join DAG headers and validated shard-manifest annex."""
        from tools.implementation_plan_core.wave_dag import (
            strip_and_validate_shard_manifests,
            validate_wave_dag_sequence,
        )

        sharded_plan = """# Fork Join Sharded Refactor Plan

```json shard-manifest
{
  "shards": [
    {"shard_id": "2A", "scope_in": ["tools/mod_a.py", "tools/__init__.py"], "verify_independently": "pytest tests/test_a.py --timeout=60"},
    {"shard_id": "2B", "scope_in": ["tools/mod_b.py", "tools/__init__.py"], "verify_independently": "pytest tests/test_b.py --timeout=60"}
  ]
}
```

## Wave 1: Contract Setup
### Objective & Scope
Define shared contract.
### Milestones & Deliverables
- [NEW] `tools/contract.py`
### Acceptance Criteria
- Contract passes.
### Runtime Receipt & Completion Gate
- Run: pytest tests/test_contract.py --timeout=60
- Input: fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit != 0
- Record: reports/w1.json

## Wave 2A: Shard A Implementation
Depends On: Wave 1
### Objective & Scope
Implement shard A.
### Milestones & Deliverables
- [NEW] `tools/mod_a.py`
### Acceptance Criteria
- Shard A passes.
### Runtime Receipt & Completion Gate
- Run: pytest tests/test_a.py --timeout=60
- Input: fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit != 0
- Record: reports/w2a.json

## Wave 2B: Shard B Implementation
Depends On: Wave 1
### Objective & Scope
Implement shard B.
### Milestones & Deliverables
- [NEW] `tools/mod_b.py`
### Acceptance Criteria
- Shard B passes.
### Runtime Receipt & Completion Gate
- Run: pytest tests/test_b.py --timeout=60
- Input: fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit != 0
- Record: reports/w2b.json
"""
        stripped, m_errs = strip_and_validate_shard_manifests(sharded_plan, "sharded.md")
        self.assertEqual(m_errs, [])
        self.assertNotIn("shard-manifest", stripped)
        is_valid, errors = validate_plan_content(sharded_plan, "sharded.md")
        self.assertTrue(is_valid, f"Expected sharded plan to pass, got: {errors}")
        self.assertEqual(validate_wave_dag_sequence([], "empty.md"), [])

        # Edge cases: single-shard manifest passes, empty shards rejected, opt-in require_disjoint enforced
        single_shard = '```json shard-manifest\n{"shards": [{"shard_id": "1A", "scope_in": ["tools/a.py"], "verify_independently": "pytest tests/test_a.py --timeout=60"}]}\n```'
        _, single_errs = strip_and_validate_shard_manifests(single_shard, "single.md")
        self.assertEqual(single_errs, [])

        empty_shard = '```json shard-manifest\n{"shards": []}\n```'
        _, empty_errs = strip_and_validate_shard_manifests(empty_shard, "empty_shards.md")
        self.assertTrue(any("minItems: 1" in e for e in empty_errs))

        strict_disjoint = (
            '```json shard-manifest\n'
            '{"require_disjoint": true, "shards": ['
            '{"shard_id": "2A", "scope_in": ["tools/shared.py"], "verify_independently": "pytest tests/test_a.py --timeout=60"},'
            '{"shard_id": "2B", "scope_in": ["tools/shared.py"], "verify_independently": "pytest tests/test_b.py --timeout=60"}'
            ']}\n```'
        )
        _, strict_errs = strip_and_validate_shard_manifests(strict_disjoint, "strict_disjoint.md")
        self.assertTrue(any("scope_in overlap" in e for e in strict_errs))

        # Focused bug-fix plans with explicit What Stays Unchanged upstream/downstream defense pass across all 3 domains
        for domain_target in (
            "resume_graph_engine/src/apps_rg/runtime/sections/headline_lane.py",
            "outreach_engine/src/apps_lic/pipeline/compiler.py",
            "apps_research/engines/company_brief_engine.py",
        ):
            bugfix_plan = f"""# Focused Bug Fix Plan

## What Stays Unchanged
- Upstream producers and input contracts remain unchanged.
- Downstream validators and consumers remain unchanged.

## Wave 1: Guard Null Input
### Objective & Scope
Fix null-input handling in `{domain_target}`.
### Milestones & Deliverables
- [MODIFY] `{domain_target}`: Guard null field access.
### Acceptance Criteria
- Null input handled cleanly while upstream contracts and downstream validators pass unchanged.
### Runtime Receipt & Completion Gate
- Run: .venv/bin/python -m pytest tests/ --timeout=60
- Input: null fixture
- Expected: 0 failures
- Verify independently: git diff --stat
- Fail if: exit != 0
- Record: reports/bugfix.json
"""
            ok_bf, bf_errs = validate_plan_content(bugfix_plan, "bugfix.md")
            self.assertTrue(ok_bf, f"Expected bugfix plan for {domain_target} to pass, got: {bf_errs}")


if __name__ == "__main__":
    unittest.main()

