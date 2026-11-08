"""Non-mock Wave 2 tests for DeterministicDraftRepairer connection note trimming and ellipsis rules."""

from __future__ import annotations

from apps_lic.domain.models import AudiencePersona, ChannelType, OutreachMessageDraft
from apps_lic.domain.repair import DeterministicDraftRepairer


def test_repair_connection_note_never_emits_double_ellipsis() -> None:
    """Defect 6A: _trim_connection_note must never produce '......' when input already contains '...'."""
    raw_body = (
        "Hi Morgan,\n\n"
        "Following Global Financial Services Group's focus on modernizing core multi-region cloud banking "
        "infrastructure across regulated markets. In my work as Chief Platform Architect, architected "
        "distributed payment systems processing $4.2B annual volume with 99.995% reliability...\n\n"
        "Open to connecting?"
    )
    repaired_body, _ = DeterministicDraftRepairer.repair_text(
        raw_body,
        channel=ChannelType.LINKEDIN_CONNECTION,
        persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    assert len(repaired_body) <= 300
    assert "......" not in repaired_body
    assert "...." not in repaired_body
    assert repaired_body.endswith("?")


def test_repair_connection_note_condenses_long_title_to_preserve_metric() -> None:
    """Defect 6B: _trim_connection_note condenses long title clauses so grounded metrics survive."""
    raw_body = (
        "Hi Morgan,\n\n"
        "Noticed Apex Financial's focus on multi-region cloud modernization. "
        "In my work as Executive Vice President of Global Enterprise Cloud Infrastructure and Platform Engineering, "
        "scaled distributed platforms processing $4.2B annual volume with 99.995% reliability.\n\n"
        "Open to exchanging perspectives?"
    )
    draft = OutreachMessageDraft(
        draft_id="d_repair_01",
        channel=ChannelType.LINKEDIN_CONNECTION,
        subject="",
        body=raw_body,
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    DeterministicDraftRepairer.repair_draft(draft, channel=ChannelType.LINKEDIN_CONNECTION)
    assert len(draft.body) <= 300
    assert "$4.2B" in draft.body
    assert "......" not in draft.body
    assert draft.body.endswith("?")
