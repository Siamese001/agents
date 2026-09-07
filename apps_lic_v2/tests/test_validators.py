"""Unit tests for domain validators."""

from apps_lic.domain.models import ChannelType
from apps_lic.domain.validators import (
    ChannelLengthValidator,
    GroundingValidator,
    QuestionEndingValidator,
    SpamTriggerValidator,
)


def test_spam_trigger_validator_detects_critical_urgency():
    validator = SpamTriggerValidator()
    text = "Please act now on this limited time opportunity!"
    is_valid, violations, warnings = validator.validate(text)
    assert not is_valid
    assert len(violations) >= 1
    assert any("act now" in v for v in violations)


def test_spam_trigger_validator_passes_professional_message():
    validator = SpamTriggerValidator()
    text = "Given your team's expansion, would you be open to an introductory discussion?"
    is_valid, violations, warnings = validator.validate(text)
    assert is_valid
    assert len(violations) == 0


def test_channel_length_validator_enforces_connection_note_limit():
    validator = ChannelLengthValidator()
    long_note = "A" * 305
    is_valid, err = validator.validate(ChannelType.LINKEDIN_CONNECTION, long_note)
    assert not is_valid
    assert "exceeds channel ceiling" in err

    short_note = "A" * 250
    is_valid_short, err_short = validator.validate(ChannelType.LINKEDIN_CONNECTION, short_note)
    assert is_valid_short
    assert err_short is None


def test_question_ending_validator_detects_missing_question():
    validator = QuestionEndingValidator()
    assert not validator.validate("I look forward to hearing from you.")[0]
    assert validator.validate("Would next Tuesday work for a quick discussion?")[0]


def test_grounding_validator_blocks_hallucinated_facts():
    validator = GroundingValidator()
    allowed = {"fact_scale_01", "fact_team_02"}
    
    valid, viols = validator.validate(["fact_scale_01"], allowed)
    assert valid
    assert len(viols) == 0

    invalid, viols_inv = validator.validate(["fact_scale_01", "unverified_patent_claim"], allowed)
    assert not invalid
    assert len(viols_inv) == 1
    assert "unverified_patent_claim" in viols_inv[0]
