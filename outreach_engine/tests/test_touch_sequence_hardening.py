"""Hardening and regression test suite for TouchSequencePlanner, compiler, deterministic repair, and isolated regeneration.

Tests:
1. Select only provenance-backed candidate facts (ignores facts with missing/whitespace provenance).
2. Deterministic pre-eval repairs for formatting and channel failures (em dashes, markdown links, length ceilings, questions).
3. Touch-isolated regeneration preserving passing touches with bounded retries.
4. Zero unnecessary synthesis proof: all three touches pass E2E without regenerating already-passing touches.
"""

from __future__ import annotations

import copy
import pytest

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateFact,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.domain.repair import DeterministicDraftRepairer
from apps_lic.judges.evaluator import ExecutiveOutreachJudgePanel
from apps_lic.pipeline.compiler import PromptCompiler
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.pipeline.touch_sequence import TouchSequencePlanner


@pytest.fixture
def candidate_mixed_provenance() -> CandidateProfile:
    """Candidate with unproven facts at index 0 and 2, but valid provenance at index 1 and 3."""
    return CandidateProfile(
        candidate_id="cand_mixed_prov",
        full_name="Morgan Vance",
        target_title="Chief Technology Officer",
        executive_summary="Experienced technology executive leading cloud transformations.",
        verified_facts=[
            CandidateFact(
                fact_id="fact_unproven_0",
                category="scale",
                statement="scaled hypothetical system to $999B volume",
                metric="$999B",
                source_reference=None,  # Missing provenance!
            ),
            CandidateFact(
                fact_id="fact_proven_1",
                category="scale",
                statement="scaled enterprise platform handling $3.5B annual volume at 99.99% SLA",
                metric="$3.5B",
                source_reference="canonical_dossier_platform",  # Valid provenance!
            ),
            CandidateFact(
                fact_id="fact_unproven_2",
                category="leadership",
                statement="led team of 1000+ engineers without record",
                metric="1000+",
                source_reference="   ",  # Whitespace-only provenance!
            ),
            CandidateFact(
                fact_id="fact_proven_3",
                category="leadership",
                statement="recruited and retained an engineering organization of 120+ engineers",
                metric="120+",
                source_reference="canonical_dossier_leadership",  # Valid provenance!
            ),
        ],
    )


@pytest.fixture
def target_opportunity_clean() -> TargetOpportunity:
    return TargetOpportunity(
        opportunity_id="opp_hardening_01",
        company_name="Apex Financial Systems",
        role_title="Head of Core Engineering",
        industry="Fintech & WealthTech",
        recipient_name="Jordan Reed",
        recipient_title="VP of Engineering",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["cloud modern banking core", "zero-downtime reliability"],
        briefing_text="Apex Financial Systems is accelerating its cloud banking core transformation.",
    )


def test_select_only_provenance_backed_candidate_facts(candidate_mixed_provenance, target_opportunity_clean):
    """Planner and compiler MUST ignore unproven facts at index 0 and pick only provenance-backed facts."""
    # 1. Compiler fact selection verification
    compiler = PromptCompiler()
    subject, body, fact_ids = compiler.render_draft_message(
        candidate_mixed_provenance,
        target_opportunity_clean,
        ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    # Must select fact_proven_1, NOT fact_unproven_0
    assert fact_ids == ["fact_proven_1"]
    assert "fact_unproven_0" not in fact_ids
    assert "$999B" not in body
    assert "$3.5B" in body

    # 2. TouchSequencePlanner fact selection verification
    planner = TouchSequencePlanner()
    seq = planner.plan_sequence(candidate_mixed_provenance, target_opportunity_clean)

    assert len(seq.touches) == 3
    t1_facts = seq.touches[0].draft.grounded_facts_used
    t2_facts = seq.touches[1].draft.grounded_facts_used

    # Touch 1 gets first provenance-backed fact
    assert t1_facts == ["fact_proven_1"]
    # Touch 2 gets second provenance-backed fact
    assert t2_facts == ["fact_proven_3"]

    # All touches must pass without grounding violations
    for touch in seq.touches:
        assert touch.draft.metadata.get("passed") is True
        assert len(touch.draft.metadata.get("validation_violations", [])) == 0


def test_repair_deterministic_formatting_and_channel_failures():
    """Verify DeterministicDraftRepairer repairs em dashes, markdown links, channel lengths, and questions."""
    # 1. Em dash and markdown link repair
    dirty_body = (
        "Hi Jordan,\n\n"
        "Following Apex's cloud banking core transformation—we should connect. "
        "Review our work at [Cloud Platform](https://example.com/platform) — it drove $3.5B volume.\n\n"
        "Would love to learn more."
    )
    dirty_subject = "Apex / Core Engineering — Strategic Alignment"

    repaired_body, repaired_subject = DeterministicDraftRepairer.repair_text(
        body=dirty_body,
        subject=dirty_subject,
        channel=ChannelType.LINKEDIN_INMAIL,
    )

    assert "—" not in repaired_body
    assert "\u2014" not in repaired_body
    assert "—" not in repaired_subject
    assert "[" not in repaired_body
    assert "https://example.com/platform" in repaired_body
    # Subordinate tone repaired to executive framing
    assert "would love to learn more" not in repaired_body.lower()
    # Question ending guaranteed
    assert repaired_body.strip().endswith("?")

    # 2. LinkedIn Connection note length ceiling repair (<300 chars)
    long_connection_body = (
        "Hi Jordan Vance,\n\n"
        "Following Apex Financial Systems's focus on cloud modern banking core and enterprise scale transformations across global markets. "
        "In my recent executive work as Chief Technology Officer, I led multiple large-scale legacy modernization initiatives delivering high resilience and zero downtime.\n\n"
        "Open to exchanging perspectives?"
    )
    assert len(long_connection_body) > 300

    repaired_conn, _ = DeterministicDraftRepairer.repair_text(
        body=long_connection_body,
        channel=ChannelType.LINKEDIN_CONNECTION,
    )
    assert len(repaired_conn) <= 300
    assert repaired_conn.startswith("Hi Jordan Vance,")
    assert repaired_conn.strip().endswith("?")


def test_preserve_passing_outputs_and_regenerate_only_failing_touch(candidate_mixed_provenance, target_opportunity_clean):
    """When a touch is blocked, passing touches are strictly preserved and only the failing touch regenerates."""
    planner = TouchSequencePlanner()
    initial_seq = planner.plan_sequence(candidate_mixed_provenance, target_opportunity_clean)

    assert initial_seq.status == "PASSED"
    assert len(initial_seq.touches) == 3

    # Snapshot drafts of Touch 1 and Touch 3
    t1_orig_body = initial_seq.touches[0].draft.body
    t1_orig_id = initial_seq.touches[0].draft.draft_id
    t3_orig_body = initial_seq.touches[2].draft.body
    t3_orig_id = initial_seq.touches[2].draft.draft_id

    # Deliberately corrupt Touch 2 with an ungrounded claim and mark it BLOCKED
    corrupted_seq = copy.deepcopy(initial_seq)
    corrupted_t2 = corrupted_seq.touches[1]
    corrupted_t2.draft.body = "Hi Jordan,\n\nIn my recent work, I achieved $999B in ungrounded revenue.\n\nOpen to a brief call?"
    corrupted_t2.draft.metadata["passed"] = False
    corrupted_t2.draft.metadata["failure_reasons"] = ["Unsupported dollar metric claim in message body: '$999B'."]
    corrupted_seq.blocked_touches = [{
        "touch_number": 2,
        "day_offset": corrupted_t2.day_offset,
        "channel": corrupted_t2.channel.value,
        "status": "BLOCKED",
    }]
    corrupted_seq.status = "BLOCKED"

    # Regenerate ONLY failing Touch 2
    healed_seq = planner.regenerate_failing_touch(
        sequence=corrupted_seq,
        touch_number=2,
        candidate=candidate_mixed_provenance,
        opportunity=target_opportunity_clean,
    )

    # 1. Passing touches 1 and 3 are strictly preserved with ZERO re-synthesis
    assert healed_seq.touches[0].draft.draft_id == t1_orig_id
    assert healed_seq.touches[0].draft.body == t1_orig_body
    assert healed_seq.touches[2].draft.draft_id == t3_orig_id
    assert healed_seq.touches[2].draft.body == t3_orig_body

    # 2. Only Touch 2 was regenerated and healed
    assert healed_seq.touches[1].draft.metadata.get("passed") is True
    assert "$999B" not in healed_seq.touches[1].draft.body

    # 3. Overall sequence passes with zero unnecessary synthesis
    assert healed_seq.status == "PASSED"
    assert len(healed_seq.blocked_touches) == 0
    assert healed_seq.metadata.get("unnecessary_synthesis_count") == 0


def test_bounded_retries_never_weaken_thresholds():
    """Verify retry bounds and strict threshold enforcement."""
    planner = TouchSequencePlanner()
    assert planner.MAX_TOUCH_RETRIES == 2

    # Verify judge panel active thresholds are not weakened
    panel = ExecutiveOutreachJudgePanel()
    assert panel.get_threshold("lens2_grounding", 0.99) >= 0.99
    assert panel.get_threshold("lens1_altitude", 0.70) >= 0.70
    assert panel.get_min_composite_score(0.75) >= 0.75


def test_all_three_touches_pass_e2e_zero_unnecessary_synthesis(candidate_mixed_provenance, target_opportunity_clean, tmp_path):
    """End-to-end verification proving all 3 touches pass with zero unnecessary synthesis."""
    orchestrator = OutreachOrchestrator()

    campaign = orchestrator.generate_full_campaign(
        candidate=candidate_mixed_provenance,
        opportunity=target_opportunity_clean,
        channel=ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
        artifact_dir=tmp_path,
    )

    assert campaign.status == "PASSED"
    assert len(campaign.touches) == 3
    assert len(campaign.blocked_touches) == 0

    # Ensure all 3 touches pass authoritative evaluation
    for touch in campaign.touches:
        assert touch.draft.metadata.get("passed") is True
        verdict = touch.draft.metadata.get("authoritative_verdict", {})
        assert verdict.get("passed") is True
        assert verdict.get("composite_score", 0.0) >= 0.75
        assert len(touch.draft.metadata.get("validation_violations", [])) == 0

    # Zero unnecessary synthesis metric
    assert campaign.metadata.get("unnecessary_synthesis_count", 0) == 0

    # Verify artifacts on disk
    assert (tmp_path / "campaign_sequence.json").is_file()
