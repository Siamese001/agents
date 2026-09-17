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
