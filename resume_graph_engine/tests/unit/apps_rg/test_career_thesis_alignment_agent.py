"""Unit tests for the Career Thesis Alignment Agent."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps_rg.runtime.reasoning.CareerThesisAlignmentAgent import (
    CAREER_THESIS_ALIGNMENT_FILENAME,
    CAREER_THESIS_ALIGNMENT_SCHEMA,
    CareerThesisAlignmentAgent,
    execute_career_thesis_alignment,
)


class TestCareerThesisAlignmentAgent(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.artifact_dir = Path(self.tmp_dir.name)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_synthesize_strategic_fit_basic(self) -> None:
        agent = CareerThesisAlignmentAgent()

        requirements = [
            {"id": "req_01", "text": "Experience building large scale distributed systems in Python and Go"},
            {"id": "req_02", "text": "Deep knowledge of LLM fine-tuning and evaluation harnesses"},
            {"id": "req_03", "text": "Experience managing budgets and executive board communication"},
        ]

        evidence = [
            {
                "assertion_id": "ev_001",
                "text": "Architected distributed streaming platform handling 2M QPS in Go and Python.",
                "matched_skills": ["Python", "Go", "Distributed Systems", "Kubernetes"],
            },
            {
                "assertion_id": "ev_002",
                "text": "Trained and deployed internal LLM evaluation benchmark for production agent workflows.",
                "matched_skills": ["LLMs", "Evaluation", "Machine Learning"],
            },
        ]

        plan = agent.synthesize(
            target_company="Anthropic",
            target_role="Applied AI Research Engineer",
            target_level="Staff",
            jd_requirements=requirements,
            c0_evidence_items=evidence,
        )

        self.assertEqual(plan.schema_version, CAREER_THESIS_ALIGNMENT_SCHEMA)
        self.assertEqual(plan.target_company, "Anthropic")
        self.assertEqual(plan.target_role, "Applied AI Research Engineer")
        self.assertEqual(plan.target_level, "Staff")

        # 1. Career thesis checks
        thesis = plan.career_thesis
        self.assertIn("Staff Applied AI Research Engineer", thesis.primary_positioning)
        self.assertIn("Anthropic", thesis.executive_summary_anchor)
        self.assertTrue(len(thesis.key_themes) >= 3)
        self.assertTrue(any("Distributed" in t for t in thesis.key_themes))
        self.assertTrue(any("AI" in t or "Machine Learning" in t for t in thesis.key_themes))

        # 2. Evidence gap mitigation checks
        gaps = plan.evidence_gaps
        self.assertEqual(len(gaps), 3)

        # req_01 has matching distributed systems skills in ev_001
        self.assertEqual(gaps[0].gap_status, "DIRECT_MATCH")
        self.assertIn("ev_001", gaps[0].matched_evidence_ids)

        # req_02 has matching LLM skills in ev_002
        self.assertEqual(gaps[1].gap_status, "DIRECT_MATCH")
        self.assertIn("ev_002", gaps[1].matched_evidence_ids)

        # req_03 (board communication/budgets) has no direct match in evidence -> adjacent pivot
        self.assertEqual(gaps[2].gap_status, "ADJACENT_PIVOT")
        self.assertIn("Pivot", gaps[2].pivot_strategy)

        # 3. Thematic allocation checks
        alloc = plan.thematic_allocation
        self.assertTrue(len(alloc.headline_focus) > 0)
        self.assertTrue(len(alloc.executive_summary_focus) > 0)
        self.assertTrue(len(alloc.competencies_focus) > 0)
        self.assertIn("Python", alloc.competencies_focus)
        self.assertIn("unify_bullets", alloc.bullet_lanes_focus)

    def test_execute_career_thesis_alignment_persists_artifact(self) -> None:
        plan = execute_career_thesis_alignment(
            self.artifact_dir,
            target_company="Google DeepMind",
            target_role="Director of AI Engineering",
            target_level="Director",
            job_description_text="Must lead engineering teams building planetary-scale AI systems and infrastructure.",
        )

        output_file = self.artifact_dir / CAREER_THESIS_ALIGNMENT_FILENAME
        self.assertTrue(output_file.is_file())

        data = json.loads(output_file.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], CAREER_THESIS_ALIGNMENT_SCHEMA)
        self.assertEqual(data["target_company"], "Google DeepMind")
        self.assertEqual(data["target_role"], "Director of AI Engineering")
        self.assertTrue(data["digest"].startswith("sha256:"))
        self.assertTrue(len(data["career_thesis"]["key_themes"]) >= 3)

        receipt_file = self.artifact_dir / "career_thesis_alignment_receipt.json"
        self.assertTrue(receipt_file.is_file())
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        self.assertEqual(receipt["schema_version"], "career_thesis_alignment_receipt_v1")
        self.assertTrue(receipt["pass"])

    def test_c03_assignment_uniqueness_and_adjacent_pivot_receipt(self) -> None:
        from apps_rg.runtime.c0.resume_graph_allocation import _validate_assignment_uniqueness

        c03_assignments = [
            {
                "claim_unit_id": "headline:001",
                "section_id": "headline",
                "skill_id": "skill_distributed_systems",
                "skill_label": "Distributed Systems Architecture",
                "root_bundle_theme": "Cloud Platform Transformation",
                "metric_outcome_id": "",
                "counts_toward_global_uniqueness": True,
            },
            {
                "claim_unit_id": "executive_summary:001",
                "section_id": "executive_summary",
                "skill_id": "skill_llm_governance",
                "skill_label": "LLM Evaluation & Governance",
                "root_bundle_theme": "Enterprise AI Safety",
                "metric_outcome_id": "metric_revenue_22m",
                "metric_text": "$22M revenue",
                "counts_toward_global_uniqueness": True,
            },
            {
                "claim_unit_id": "unify_bullets:bul_unify_001",
                "section_id": "unify_bullets",
                "skill_id": "skill_kubernetes_scale",
                "skill_label": "Kubernetes Fleet Scaling",
                "root_bundle_theme": "High-Throughput Infrastructure",
                "metric_outcome_id": "metric_margin_35pct",
                "metric_text": "35% margin",
                "counts_toward_global_uniqueness": True,
            },
        ]

        plan = execute_career_thesis_alignment(
            self.artifact_dir,
            target_company="Anthropic",
            target_role="SVP Agentic Engineering",
            target_level="SVP",
            jd_requirements=[
                {"id": "r1", "text": "Distributed Systems Architecture and Cloud Platform Transformation"},
                {"id": "r2", "text": "Quantum Sovereign Hardware Foundry Operations"},
            ],
            c0_evidence_items=c03_assignments,
        )

        self.assertIsNotNone(plan.thematic_allocation)
        self.assertTrue(len(plan.thematic_allocation.competencies_focus) >= 3)
        self.assertEqual(plan.evidence_gaps[0].gap_status, "DIRECT_MATCH")
        self.assertEqual(plan.evidence_gaps[1].gap_status, "ADJACENT_PIVOT")
        self.assertIn("C0.3 bridge anchors", plan.evidence_gaps[1].pivot_strategy)

        uniqueness = _validate_assignment_uniqueness(c03_assignments)
        self.assertTrue(uniqueness["pass"])
        self.assertEqual(uniqueness["repeated_skill_ids"], [])
        self.assertEqual(uniqueness["repeated_metric_outcome_ids"], [])

        receipt = json.loads(
            (self.artifact_dir / "career_thesis_alignment_receipt.json").read_text(encoding="utf-8")
        )
        self.assertTrue(receipt["pass"])
        self.assertEqual(receipt["adjacent_pivot_count"], 1)
        self.assertEqual(receipt["uniqueness_receipt"], uniqueness)


if __name__ == "__main__":
    unittest.main()
