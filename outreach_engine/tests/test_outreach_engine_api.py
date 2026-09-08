"""Tests verifying outreach_engine public API and backwards compatibility."""

def test_outreach_engine_root_exports():
    import outreach_engine as oe

    assert hasattr(oe, "OutreachOrchestrator")
    assert hasattr(oe, "CandidateProfile")
    assert hasattr(oe, "TargetOpportunity")
    assert hasattr(oe, "ChannelType")
    assert hasattr(oe, "GovernedBriefingResolver")
    assert hasattr(oe, "SealedBriefingResolution")
    assert hasattr(oe, "AppsResearchBridge")
    assert hasattr(oe, "MissionLoader")
    assert hasattr(oe, "RubricJudgeEvaluator")


def test_apps_lic_alias_compatibility():
    import apps_lic
    from apps_lic.domain.models import CandidateProfile, TargetOpportunity
    from apps_lic.pipeline.orchestrator import OutreachOrchestrator

    assert CandidateProfile is not None
    assert TargetOpportunity is not None
    assert OutreachOrchestrator is not None
