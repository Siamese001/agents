"""End-to-end smoke test for apps_lic_v2 orchestrator and judge evaluator."""

from apps_lic.domain.models import ChannelType
from apps_lic.judges.evaluator import RubricJudgeEvaluator
from apps_lic.pipeline.orchestrator import OutreachOrchestrator


def test_orchestrator_e2e_pass(sample_candidate, sample_opportunity):
    orchestrator = OutreachOrchestrator()
    draft, val = orchestrator.generate_single_draft(
        sample_candidate, sample_opportunity, ChannelType.LINKEDIN_INMAIL
    )

    assert val.is_valid
    assert val.hard_gate_passed
    assert len(val.violations) == 0
    assert draft.character_count > 0

    # Test judge evaluation
    judge = RubricJudgeEvaluator()
    report = judge.evaluate(draft, sample_candidate, sample_opportunity)

    assert report.passed
    assert report.hop1_classifier_score >= 0.7
    assert report.hop2_grounding_score == 1.0
    assert report.hop6_alignment_score >= 0.7
    assert report.hop8_narrative_score >= 0.7
