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
