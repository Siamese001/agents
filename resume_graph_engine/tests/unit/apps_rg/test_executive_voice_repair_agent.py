"""Unit tests for the Executive Voice Repair Agent."""

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
from apps_rg.runtime.sections.ExecutiveVoiceRepairAgent import (
    EXECUTIVE_VOICE_REPAIR_MAX_ATTEMPTS,
    ExecutiveVoiceRepairAgent,
    ExecutiveVoiceRepairReceipt,
    executive_voice_repair_enabled,
    repair_section_with_executive_voice_agent,
)


class TestExecutiveVoiceRepairAgent(unittest.TestCase):

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

        diag = extract_x1d_diagnostic(result)
        self.assertTrue(diag["repair_needed"])
        self.assertIn("Credential dump in sentence 5", diag["findings"])
        self.assertIn(5, diag["cited_sentence_indexes"])
        self.assertIn("Foreground quantitative outcome", diag["remediation_suggestions"])

    def test_extract_x1d_diagnostic_all_pass(self) -> None:
        outcome1 = PanelJudgeOutcome(
            provider_key="gemini_pro",
            contract_hash="abc",
            input_hash="abc1",
            evaluator_mode="MODEL_BACKED",
            provider_status="OK",
            score=4.5,
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
            outcomes=(outcome1,),
            transport_violations=(),
        )

        diag = extract_x1d_diagnostic(result)
        self.assertFalse(diag["repair_needed"])
        self.assertEqual(diag["findings"], [])

    def test_repair_executive_summary_voice(self) -> None:
        raw_text = (
            "Dynamic technology executive who leads platform engineering. "
            "Manages $40M budget across global infrastructure. "
            "Pioneered distributed systems handling 1M QPS. "
            "Engineered cloud migrations with zero downtime. "
            "Certified in AWS, Azure, GCP, PMP, CISSP with extensive qualifications. "
            "Strategic advisor to executive leadership teams."
        )
        candidate = {"resume_display_text": raw_text}
        diagnostic = {
            "repair_needed": True,
            "findings": ["Credential dump in sentence 5"],
            "cited_sentence_indexes": [4],
            "remediation_suggestions": ["Foreground quantitative savings"],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            art_dir = Path(tmp_dir)
            updated, receipt = repair_section_with_executive_voice_agent(
                section_id="executive_summary",
                candidate_data=candidate,
                diagnostic=diagnostic,
                mock_mode=True,
                artifact_dir=art_dir,
            )

            self.assertTrue(receipt.repair_attempted)
            self.assertTrue(receipt.repair_succeeded)
            self.assertIn("resume_display_text", receipt.repaired_fields)
            repaired_text = updated["resume_display_text"]
            self.assertNotIn("Certified in AWS, Azure", repaired_text)
            self.assertIn("$4.2M", repaired_text)

            receipt_file = art_dir / "x1_repair_receipt.json"
            self.assertTrue(receipt_file.is_file())
            data = json.loads(receipt_file.read_text(encoding="utf-8"))
            self.assertEqual(data["section_id"], "executive_summary")
            self.assertTrue(data["repair_succeeded"])

    def test_repair_headline_clarity(self) -> None:
        bad_headline = "VP Engineering | IT Solutions, Big Data, Cloud | Dynamic Leader"
        candidate = {"headline_line": bad_headline}
        diagnostic = {
            "repair_needed": True,
            "findings": ["Clunky noun stacks; missing SVP Engineering prefix"],
            "remediation_suggestions": ["Standardize to SVP Engineering 4-segment format"],
        }

        updated, receipt = repair_section_with_executive_voice_agent(
            section_id="headline",
            candidate_data=candidate,
            diagnostic=diagnostic,
            mock_mode=True,
        )

        self.assertTrue(receipt.repair_succeeded)
        hl = updated["headline_line"]
        self.assertTrue(hl.startswith("SVP Engineering |"))
        parts = [p.strip() for p in hl.split("|")]
        self.assertEqual(len(parts), 4)
        words = [w for w in hl.split() if w != "|"]
        self.assertTrue(8 <= len(words) <= 12)

    def test_repair_competencies_alignment(self) -> None:
        bad_comps = [
            {"category": "Cloud Platforms — AWS/GCP", "skills": ["EC2", "S3"]},
            {"category": "Leadership — Executive Management", "skills": ["Agile"]},
        ]
        candidate = {"competencies": bad_comps}
        diagnostic = {
            "repair_needed": True,
            "findings": ["Contains em-dashes; fewer than 6 categories"],
            "remediation_suggestions": ["Expand to 6-8 executive categories without em-dashes"],
        }

        updated, receipt = repair_section_with_executive_voice_agent(
            section_id="competencies",
            candidate_data=candidate,
            diagnostic=diagnostic,
            mock_mode=True,
        )

        self.assertTrue(receipt.repair_succeeded)
        comps = updated["competencies"]
        self.assertTrue(6 <= len(comps) <= 8)
        for c in comps:
            cat = c.get("category", "")
            self.assertNotIn("—", cat)

    def test_repair_bypassed_when_not_needed(self) -> None:
        candidate = {"resume_display_text": "Good text."}
        diagnostic = {"repair_needed": False}
        updated, receipt = repair_section_with_executive_voice_agent(
            section_id="executive_summary",
            candidate_data=candidate,
            diagnostic=diagnostic,
            mock_mode=True,
        )
        self.assertFalse(receipt.repair_attempted)
        self.assertTrue(receipt.repair_succeeded)
        self.assertEqual(receipt.repair_mechanism, "none")

    def test_repair_kill_switch(self) -> None:
        old_env = os.environ.get("APPS_RG_X1_REPAIR_ENABLED")
        try:
            os.environ["APPS_RG_X1_REPAIR_ENABLED"] = "0"
            self.assertFalse(executive_voice_repair_enabled())

            candidate = {"resume_display_text": "Text."}
            diagnostic = {"repair_needed": True}
            updated, receipt = repair_section_with_executive_voice_agent(
                section_id="executive_summary",
                candidate_data=candidate,
                diagnostic=diagnostic,
                mock_mode=True,
            )
            self.assertFalse(receipt.repair_attempted)
            self.assertIn("disabled", receipt.notes)
        finally:
            if old_env is not None:
                os.environ["APPS_RG_X1_REPAIR_ENABLED"] = old_env
            else:
                os.environ.pop("APPS_RG_X1_REPAIR_ENABLED", None)

    def test_agent_class_repair_method(self) -> None:
        agent = ExecutiveVoiceRepairAgent()
        candidate = {"resume_display_text": "Some text."}
        diagnostic = {"repair_needed": False}
        updated, receipt = agent.repair(
            section_id="executive_summary",
            candidate_data=candidate,
            diagnostic=diagnostic,
            mock_mode=True,
        )
        self.assertFalse(receipt.repair_attempted)
        self.assertTrue(receipt.repair_succeeded)


    def test_fail_closed_without_live_key_in_production(self) -> None:
        candidate = {"resume_display_text": "Bad text."}
        diagnostic = {"repair_needed": True}
        old_test = os.environ.pop("PYTEST_CURRENT_TEST", None)
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        old_harness = os.environ.pop("APPS_RG_TEST_HARNESS", None)
        try:
            import sys
            from unittest import mock
            with mock.patch.dict(sys.modules):
                sys.modules.pop("pytest", None)
                with self.assertRaises(RuntimeError) as ctx:
                    repair_section_with_executive_voice_agent(
                        section_id="executive_summary",
                        candidate_data=candidate,
                        diagnostic=diagnostic,
                        mock_mode=False,
                    )
                self.assertIn("LIVE_REPAIR_KEY_REQUIRED", str(ctx.exception))
        finally:
            if old_test:
                os.environ["PYTEST_CURRENT_TEST"] = old_test
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key
            if old_harness:
                os.environ["APPS_RG_TEST_HARNESS"] = old_harness

    def test_o2_a2a_socratic_loop_uses_cross_family_auditor_and_json_schema(self) -> None:
        from unittest import mock
        from apps_rg.runtime.sections.ExecutiveVoiceRepairAgent import (
            DEFAULT_AUDITOR_MODEL,
            DEFAULT_REPAIR_MODEL,
        )

        self.assertNotEqual(DEFAULT_REPAIR_MODEL, DEFAULT_AUDITOR_MODEL)

        six_sentences = (
            "Technology strategy executive who aligns large-scale platform engineering with enterprise business objectives. "
            "Manages $40M budget across global infrastructure. "
            "Pioneered distributed systems handling 1M QPS. "
            "Engineered cloud migrations with zero downtime. "
            "Orchestrated cross-functional operational improvements delivering $4.2M in recurring savings across enterprise platforms. "
            "Strategic advisor to executive leadership teams."
        )
        calls: list[tuple[str, str]] = []

        def _fake_llm(sec: str, prompt: str, model: str = DEFAULT_REPAIR_MODEL) -> dict[str, object]:
            calls.append((model, prompt))
            if len(calls) == 1:
                return {"repaired_text": six_sentences}
            return {"disposition": "PASS", "violated_facts": [], "repair_hint": ""}

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-live"}), mock.patch(
            "apps_rg.runtime.sections.ExecutiveVoiceRepairAgent._call_llm_repair",
            side_effect=_fake_llm,
        ):
            updated, receipt = repair_section_with_executive_voice_agent(
                section_id="executive_summary",
                candidate_data={"resume_display_text": "Old draft."},
                diagnostic={"repair_needed": True, "findings": ["Fix voice"]},
                allowed_facts=[{"assertion_id": "f1", "fact_text": "$4.2M recurring savings"}],
                mock_mode=False,
            )

        self.assertTrue(receipt.repair_succeeded)
        self.assertEqual(receipt.repair_mechanism, "a2a_socratic_repair_loop")
        self.assertEqual(updated["resume_display_text"], six_sentences)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], DEFAULT_REPAIR_MODEL)
        self.assertEqual(calls[1][0], DEFAULT_AUDITOR_MODEL)
        self.assertIn('"disposition": "PASS" | "FAIL"', calls[1][1])

    def test_call_llm_repair_routes_openai_auditor_to_chat_completions_with_low_reasoning_effort(self) -> None:
        import json
        from unittest import mock
        from apps_rg.runtime.sections.ExecutiveVoiceRepairAgent import (
            DEFAULT_AUDITOR_MODEL,
            _call_llm_repair,
        )

        captured_reqs: list[object] = []

        class _FakeHTTPResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"disposition": "PASS", "violated_facts": [], "repair_hint": ""}'
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        def _fake_urlopen(req, timeout=30):
            captured_reqs.append(req)
            return _FakeHTTPResp()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai-test"}), mock.patch(
            "apps_rg.runtime.providers.external_provider.urlopen_provider_request",
            side_effect=_fake_urlopen,
        ):
            res = _call_llm_repair("executive_summary", "Audit draft", model=DEFAULT_AUDITOR_MODEL)

        self.assertEqual(res, {"disposition": "PASS", "violated_facts": [], "repair_hint": ""})
        self.assertEqual(len(captured_reqs), 1)
        req = captured_reqs[0]
        self.assertEqual(req.full_url, "https://api.openai.com/v1/chat/completions")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["model"], DEFAULT_AUDITOR_MODEL)
        self.assertEqual(body["reasoning_effort"], "low")


if __name__ == "__main__":
    unittest.main()


