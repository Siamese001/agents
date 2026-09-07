"""Unit tests for the X1 Semantic & Voice Repair Agent."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from apps_rg.runtime.judges.x1d_panel_harness import (
    PanelJudgeOutcome,
    PanelRunResult,
    extract_x1d_diagnostic,
)
from apps_rg.runtime.sections.x1_repair_agent import (
    X1_REPAIR_MAX_ATTEMPTS,
    repair_section_with_x1_agent,
    x1_repair_enabled,
)


class TestX1RepairAgent(unittest.TestCase):

    def test_extract_x1d_diagnostic_from_panel_run_result(self) -> None:
        outcome1 = PanelJudgeOutcome(
            provider_key="gemini_pro",
            contract_hash="abc",
            input_hash="abc1",
            evaluator_mode="MODEL_BACKED",
            provider_status="OK",
            score=3.5,
            score_scale="0_to_5",
            threshold=4.0,
            pass_=False,
            decisive_failure=False,
            findings=("Credential dump in sentence 5",),
            cited_sentence_indexes=(5,),
            remediation_suggestions=("Foreground quantitative outcome",),
        )
        outcome2 = PanelJudgeOutcome(
            provider_key="openai_chatgpt",
            contract_hash="abc",
            input_hash="abc2",
            evaluator_mode="MODEL_BACKED",
            provider_status="OK",
            score=4.2,
            score_scale="0_to_5",
            threshold=4.0,
            pass_=True,
            decisive_failure=False,
            findings=(),
            cited_sentence_indexes=(),
            remediation_suggestions=(),
        )
        result = PanelRunResult(
            contract_hash="abc",
            outcomes=(outcome1, outcome2),
            transport_violations=(),
        )

        diag = result.diagnostic_output(section_id="executive_summary")
        self.assertEqual(diag["section_id"], "executive_summary")
        self.assertFalse(diag["all_pass"])
        self.assertTrue(diag["repair_needed"])
        self.assertEqual(diag["scores"]["gemini_pro"], 3.5)
        self.assertEqual(diag["scores"]["openai_chatgpt"], 4.2)
        self.assertIn("Credential dump in sentence 5", diag["findings"])
        self.assertIn(5, diag["cited_sentence_indexes"])
        self.assertIn("Foreground quantitative outcome", diag["remediation_suggestions"])
        self.assertGreaterEqual(len(diag["instructions"]), 2)

    def test_extract_x1d_diagnostic_all_pass(self) -> None:
        outcomes = [
            {"provider_name": "gemini_pro", "pass": True, "score": 4.5},
            {"provider_name": "openai_chatgpt", "pass": True, "score": 4.8},
        ]
        diag = extract_x1d_diagnostic(outcomes, "headline")
        self.assertTrue(diag["all_pass"])
        self.assertFalse(diag["repair_needed"])
        self.assertEqual(diag["findings"], [])

    def test_repair_executive_summary_voice(self) -> None:
        bad_text = (
            "Enterprise technology executive leading digital transformation. "
            "Delivered cloud platforms scaling across global regions. "
            "Engineered resilient distributed systems with 99.99% uptime. "
            "Scaled architecture teams and standardized agile engineering practices. "
            "Built advanced quantitative foundation through derivatives pricing, multi-Greek hedging, capital modeling, and FSA credential rigor. "
            "Governed platform delivery, engineering scale, and regulatory-grade controls extend that arc toward enterprise architecture modernization."
        )
        diag = {
            "section_id": "executive_summary",
            "repair_needed": True,
            "cited_sentence_indexes": [5, 6],
            "findings": ["Sentence 5 is a credential dump", "Sentence 6 is a thin recap"],
            "remediation_suggestions": ["Foreground quantitative outcome", "Strengthen forward synthesis"],
        }
        candidate = {
            "resume_display_text": bad_text,
            "claim_ledger": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            repaired, receipt = repair_section_with_x1_agent(
                section_id="executive_summary",
                candidate_data=candidate,
                diagnostic=diag,
                mock_mode=True,
                artifact_dir=tmp_path,
            )

            self.assertTrue(receipt.repair_attempted)
            self.assertTrue(receipt.repair_succeeded)
            self.assertNotIn("derivatives pricing, multi-Greek hedging", repaired["resume_display_text"])
            self.assertIn("portfolio resilience", repaired["resume_display_text"])
            from apps_rg.runtime.sections.x1_repair_agent import _split_into_sentences
            sentences = _split_into_sentences(repaired["resume_display_text"])
            self.assertEqual(len(sentences), 6)
            # Audit receipt written to disk
            self.assertTrue((tmp_path / "x1_repair_receipt.json").is_file())

    def test_repair_headline_clarity(self) -> None:
        bad_headline = "SVP Engineering | Opaque Noun Stack | Cloud Transformation | Global Operations"
        diag = {
            "section_id": "headline",
            "repair_needed": True,
            "findings": ["Segment 2 is an opaque noun stack"],
            "remediation_suggestions": ["Use high-signal platform architecture phrasing"],
        }
        candidate = {
            "headline_line": bad_headline,
            "claim_ledger": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            repaired, receipt = repair_section_with_x1_agent(
                section_id="headline",
                candidate_data=candidate,
                diagnostic=diag,
                mock_mode=True,
                artifact_dir=tmp_path,
            )

            self.assertTrue(receipt.repair_attempted)
            self.assertTrue(receipt.repair_succeeded)
            hl = repaired["headline_line"]
            self.assertNotIn("Opaque Noun Stack", hl)
            self.assertTrue(hl.startswith("SVP Engineering | "))
            parts = hl.split(" | ")
            self.assertEqual(len(parts), 4)

    def test_repair_competencies_alignment(self) -> None:
        bad_comps = [
            {"category": "AI Platforms — Deep Learning", "terms": ["Neural Nets — Transformers", "LLMs"]},
            {"category": "Cloud Architecture", "terms": ["Kubernetes", "AWS"]},
            {"category": "Engineering Leadership", "terms": ["Team Scaling", "Mentorship"]},
            {"category": "Governance", "terms": ["Compliance", "Policy"]},
            {"category": "Security", "terms": ["Zero Trust", "IAM"]},
            {"category": "Data Platforms", "terms": ["Data Mesh", "Kafka"]},
        ]
        diag = {
            "section_id": "competencies",
            "repair_needed": True,
            "findings": ["Em-dashes detected in category labels and terms"],
            "remediation_suggestions": ["Remove em-dashes and standardize formatting"],
        }
        candidate = {
            "competencies": bad_comps,
            "claim_ledger": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            repaired, receipt = repair_section_with_x1_agent(
                section_id="competencies",
                candidate_data=candidate,
                diagnostic=diag,
                mock_mode=True,
                artifact_dir=tmp_path,
            )

            self.assertTrue(receipt.repair_attempted)
            self.assertTrue(receipt.repair_succeeded)
            cats = repaired["competencies"]
            self.assertEqual(len(cats), 6)
            for c in cats:
                self.assertNotIn("—", c["category"])
                for t in c["terms"]:
                    self.assertNotIn("—", t)

    def test_repair_bypassed_when_not_needed(self) -> None:
        diag = {"repair_needed": False}
        candidate = {"headline_line": "SVP Engineering | AI | Cloud | Scale"}
        repaired, receipt = repair_section_with_x1_agent(
            section_id="headline",
            candidate_data=candidate,
            diagnostic=diag,
        )
        self.assertFalse(receipt.repair_attempted)
        self.assertTrue(receipt.repair_succeeded)
        self.assertEqual(repaired, candidate)

    def test_repair_kill_switch(self) -> None:
        orig = os.environ.get("APPS_RG_X1_REPAIR_ENABLED")
        try:
            os.environ["APPS_RG_X1_REPAIR_ENABLED"] = "0"
            diag = {"repair_needed": True, "findings": ["Bad tone"]}
            candidate = {"headline_line": "SVP Engineering | Bad | Bad | Bad"}
            repaired, receipt = repair_section_with_x1_agent(
                section_id="headline",
                candidate_data=candidate,
                diagnostic=diag,
            )
            self.assertFalse(receipt.repair_attempted)
            self.assertIn("disabled", receipt.notes.lower())
            self.assertEqual(repaired, candidate)
        finally:
            if orig is not None:
                os.environ["APPS_RG_X1_REPAIR_ENABLED"] = orig
            else:
                os.environ.pop("APPS_RG_X1_REPAIR_ENABLED", None)

    def test_polish_executive_summary_judge_alignment_invokes_x1_repair(self) -> None:
        from apps_rg.runtime.sections.executive_summary_voice_repair import (
            polish_executive_summary_judge_alignment,
        )

        bad_text = (
            "Technology strategy executive who aligns enterprise IT direction. "
            "Building on that platform foundation, delivered enterprise cloud architectures. "
            "Engineered resilient distributed systems with high uptime. "
            "Scaled architecture teams across multiple product divisions. "
            "Built advanced quantitative foundation through derivatives pricing, multi-Greek hedging, capital modeling, and FSA credential rigor. "
            "Governed platform delivery, engineering scale, and regulatory-grade controls extend that arc toward enterprise architecture modernization."
        )
        parsed = {
            "resume_display_text": bad_text,
            "claim_ledger": [],
        }
        diag = {
            "section_id": "executive_summary",
            "repair_needed": True,
            "findings": ["Credential dump in sentence 5"],
            "cited_sentence_indexes": [5],
            "remediation_suggestions": ["Foreground quantitative outcome"],
        }

        out, receipt = polish_executive_summary_judge_alignment(
            parsed,
            diagnostic=diag,
        )

        self.assertTrue(receipt["applied"])
        self.assertTrue(any("x1_repair_agent" in a for a in receipt["actions"]))
        self.assertNotIn("derivatives pricing, multi-Greek hedging", out["resume_display_text"])
        self.assertIn("portfolio resilience", out["resume_display_text"])


if __name__ == "__main__":
    unittest.main()

