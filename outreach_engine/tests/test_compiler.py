"""Unit tests for prompt compiler."""

from apps_lic.domain.models import ChannelType
from apps_lic.pipeline.compiler import PromptCompiler


def test_prompt_compiler_assembles_verified_context(sample_candidate, sample_opportunity):
    compiler = PromptCompiler()
    ctx = compiler.assemble_context(sample_candidate, sample_opportunity, ChannelType.LINKEDIN_INMAIL)

    assert ctx["candidate_name"] == "Jordan Reed"
    assert ctx["company_name"] == "Apex Financial Systems"
    assert "fact_scale_01" in ctx["candidate_facts"]
    assert "DO NOT invent" in ctx["forbidden_behaviors"][0]


def test_compiler_executive_vs_recruiter_persona(sample_candidate, sample_opportunity):
    from apps_lic.domain.models import AudiencePersona, RecipientClass

    compiler = PromptCompiler()

    # 1. Executive contact track
    subj_exec, body_exec, facts_exec = compiler.render_draft_message(
        sample_candidate,
        sample_opportunity,
        ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    assert "Executive Alignment" in subj_exec
    assert "I have been following" in body_exec
    assert "—" not in body_exec
    assert "fact_scale_01" in facts_exec

    # 2. Recruiter track
    subj_rec, body_rec, facts_rec = compiler.render_draft_message(
        sample_candidate,
        sample_opportunity,
        ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_RECRUITER,
    )
    assert f"{sample_candidate.full_name} ->" in subj_rec
    assert "Reaching out regarding" in body_rec
    assert "—" not in body_rec


def test_compiler_connection_note_under_300_chars(sample_candidate, sample_opportunity):
    compiler = PromptCompiler()
    _, body, _ = compiler.render_draft_message(
        sample_candidate,
        sample_opportunity,
        ChannelType.LINKEDIN_CONNECTION,
    )
    assert len(body) <= 300
    assert body.endswith("?")


def test_signature_block_helpers():
    from apps_lic.pipeline.compiler import (
        get_executive_signature_block,
        get_recruiter_signature_block,
    )

    exec_sig = get_executive_signature_block("Amit Ayer")
    assert "Chief Agentic AI Officer" in exec_sig
    assert "linkedin.com/in/amitayer1" in exec_sig

    rec_sig = get_recruiter_signature_block("Amit Ayer")
    assert "linkedin.com/in/amitayer1" in rec_sig


def test_compiler_connection_note_long_title_and_long_fact_no_double_ellipsis():
    """Defect 6A & 6B: Long target_title and long fact statement must not produce '......' or drop metrics."""
    from apps_lic.domain.models import (
        CandidateFact,
        CandidateProfile,
        RecipientClass,
        RelationshipDistance,
        TargetOpportunity,
    )

    compiler = PromptCompiler()
    cand = CandidateProfile(
        candidate_id="cand_long",
        full_name="Jordan Reed",
        target_title="Executive Vice President of Global Enterprise Cloud Infrastructure and AI Platform Architecture",
        current_title="EVP Cloud & AI",
        executive_summary="Scaled cloud platforms.",
        key_competencies=["Cloud", "AI"],
        verified_facts=[
            CandidateFact(
                fact_id="f_long",
                category="scale",
                statement="architected and scaled distributed multi-region payment and risk platforms processing $4.2B annual volume with 99.995% availability across regulated global banking markets",
                metric="$4.2B",
                source_reference="resume",
            )
        ],
    )
    opp = TargetOpportunity(
        opportunity_id="opp_long",
        company_name="Global Financial Services Group",
        role_title="Head of Enterprise Cloud & AI Infrastructure",
        industry="Banking & Financial Services",
        recipient_name="Morgan Vance",
        recipient_title="Chief Information Officer",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=[
            "Modernize core multi-region cloud banking infrastructure and payment resilience across global operations"
        ],
    )

    _, body, fact_ids = compiler.render_draft_message(cand, opp, ChannelType.LINKEDIN_CONNECTION)
    assert len(body) <= 300
    assert "......" not in body
    assert "...." not in body
    assert "$4.2B" in body
    assert fact_ids == ["f_long"]


def test_compiler_follow_up_channel_with_and_without_priorities(sample_candidate, sample_opportunity):
    """Defect 7: ChannelType.FOLLOW_UP single-draft compilation stays <= 800 chars and grounds company/priorities."""
    from dataclasses import replace

    compiler = PromptCompiler()

    # 1. With strategic priorities
    subj1, body1, _ = compiler.render_draft_message(
        sample_candidate,
        sample_opportunity,
        ChannelType.FOLLOW_UP,
    )
    assert len(body1) <= 800
    assert "Following up" in subj1
    assert sample_opportunity.company_name in body1
    assert body1.endswith("?")

    # 2. Without strategic priorities
    opp_empty = replace(sample_opportunity, strategic_priorities=[])
    subj2, body2, _ = compiler.render_draft_message(
        sample_candidate,
        opp_empty,
        ChannelType.FOLLOW_UP,
    )
    assert len(body2) <= 800
    assert sample_opportunity.company_name in body2
    assert body2.endswith("?")

