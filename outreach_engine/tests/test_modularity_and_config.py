"""Tests for candidate profile SSOT, declarative rubrics, modularity, and sys.path purity."""

from __future__ import annotations

import sys
from pathlib import Path

import outreach_engine as oe
from apps_lic.domain.models import (
    AudiencePersona,
    CandidateFact,
    CandidateProfile,
    CandidateProfileLoader,
    ChannelType,
    TargetOpportunity,
)
from apps_lic.domain.validators import SpamTriggerValidator, _load_canonical_spam_phrases
from apps_lic.judges.evaluator import ExecutiveOutreachJudgePanel
from apps_lic.pipeline.compiler import (
    get_executive_signature_block,
    get_recruiter_signature_block,
)


def test_candidate_profile_loader_default():
    CandidateProfileLoader.clear_cache()
    profile = CandidateProfileLoader.load_default()
    assert profile.full_name == "Amit Ayer"
    assert "Chief Agentic AI Officer" in (profile.current_title or profile.target_title)
    assert "linkedin.com/in/amitayer1" in profile.linkedin_url
    assert "github.com" in profile.github_url
    assert len(profile.verified_facts) >= 2


def test_candidate_profile_loader_overrides():
    CandidateProfileLoader.clear_cache()
    custom = CandidateProfileLoader.load_default(
        overrides={
            "candidate_id": "cand_custom",
            "full_name": "Elena Rostova",
            "target_title": "VP of Architecture",
            "current_title": "Distinguished Architect",
            "linkedin_url": "linkedin.com/in/erostova",
            "github_url": "github.com/erostova",
            "phone": "+1-555-0199",
        }
    )
    assert custom.candidate_id == "cand_custom"
    assert custom.full_name == "Elena Rostova"
    assert custom.current_title == "Distinguished Architect"

    # Signature blocks using custom profile object
    exec_sig = get_executive_signature_block(custom)
    assert "Elena Rostova" in exec_sig
    assert "Distinguished Architect" in exec_sig
    assert "linkedin.com/in/erostova" in exec_sig
    assert "github.com/erostova" in exec_sig
    assert "+1-555-0199" in exec_sig

    rec_sig = get_recruiter_signature_block(custom)
    assert "Elena Rostova" in rec_sig
    assert "linkedin.com/in/erostova" in rec_sig
    assert "+1-555-0199" in rec_sig
    assert "Distinguished Architect" not in rec_sig  # recruiter sig is compact


def test_declarative_rubrics_loaded_by_judge_panel():
    panel = ExecutiveOutreachJudgePanel()
    assert panel._active_rubric.get("rubric_id") == "executive_outreach_rubric_v3"
    assert panel.get_threshold("lens1_altitude", 0.0) == 0.70
    assert panel.get_threshold("lens2_grounding", 0.0) == 0.99
    assert panel.get_threshold("lens3_resonance", 0.0) == 0.70
    assert panel.get_threshold("lens4_cta", 0.0) == 0.70
    assert panel.get_threshold("lens5_anti_spam", 0.0) == 0.70
    assert panel.get_threshold("lens6_constraints", 0.0) == 0.70

    hint = panel.get_remediation_hint("lens1_altitude", "")
    assert "peer-to-peer" in hint.lower()


def test_no_sys_path_mutation_in_validators():
    original_path = list(sys.path)
    phrases = _load_canonical_spam_phrases()
    assert isinstance(phrases, dict)
    validator = SpamTriggerValidator()
    assert validator is not None
    assert sys.path == original_path, "sys.path was mutated by validator initialization"


def test_root_exports_complete():
    assert hasattr(oe, "AudiencePersona")
    assert hasattr(oe, "CandidateProfileLoader")
    assert hasattr(oe, "ExecutiveOutreachJudgePanel")
    assert hasattr(oe, "OutreachModelRegistry")
    assert hasattr(oe, "OutreachModelPin")
    assert hasattr(oe, "OutreachModelRegistryError")
    assert hasattr(oe, "get_executive_signature_block")
    assert hasattr(oe, "get_recruiter_signature_block")
