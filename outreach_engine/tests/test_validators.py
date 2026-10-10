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


def test_em_dash_validator():
    from apps_lic.domain.validators import EmDashValidator

    val = EmDashValidator()
    assert val.validate("Standard hyphen - is allowed")[0] is True
    assert val.validate("Em dash — is forbidden")[0] is False


def test_markdown_link_validator():
    from apps_lic.domain.validators import MarkdownLinkValidator

    val = MarkdownLinkValidator()
    assert val.validate("Visit https://linkedin.com/in/amitayer1 for details")[0] is True
    assert val.validate("Check [profile](https://linkedin.com/in/amitayer1)")[0] is False


def test_subordinate_tone_validator():
    from apps_lic.domain.validators import SubordinateToneValidator

    val = SubordinateToneValidator()
    assert val.validate("I would love to learn more about this role")[0] is False
    assert val.validate("I think I'd be a great fit for your team")[0] is False
    assert val.validate("Open to exchanging perspectives next week?")[0] is True


def test_forbidden_claims_validator_detects_compensation():
    from apps_lic.domain.validators import ForbiddenClaimsValidator

    val = ForbiddenClaimsValidator()
    # Test salary and OTE mentions
    is_valid, viols = val.validate("At a compensation level of $481k OTE, I would be interested.")
    assert not is_valid
    assert any("compensation" in v.lower() for v in viols)

    is_valid, viols = val.validate("Targeting a base salary of $250k plus equity.")
    assert not is_valid
    assert len(viols) >= 1

    # Clean message has no compensation violations
    is_valid_clean, viols_clean = val.validate("Following Truist's focus on enterprise AI modernizations.")
    assert is_valid_clean
    assert len(viols_clean) == 0


def test_forbidden_claims_validator_detects_unverifiable_tenure():
    from apps_lic.domain.models import CandidateFact
    from apps_lic.domain.validators import ForbiddenClaimsValidator

    val = ForbiddenClaimsValidator()
    verified_facts = [
        CandidateFact(
            fact_id="f1",
            category="scale",
            statement="Architected enterprise agentic systems with 15 years in software",
            metric="15 years",
        )
    ]

    # Valid grounded tenure
    is_valid, viols = val.validate("Bringing 15 years of experience leading systems.", verified_facts=verified_facts)
    assert is_valid
    assert len(viols) == 0

    # Unverifiable exaggerated tenure
    is_valid, viols = val.validate("Bringing 30 years of experience in enterprise systems.", verified_facts=verified_facts)
    assert not is_valid
    assert any("Unverifiable tenure" in v for v in viols)


def test_forbidden_claims_validator_detects_policy_violations():
    from apps_lic.domain.validators import ForbiddenClaimsValidator

    val = ForbiddenClaimsValidator()
    is_valid, viols = val.validate("I will require visa sponsorship for this role.")
    assert not is_valid
    assert any("Policy-forbidden" in v for v in viols)

    is_valid, viols = val.validate("Inquiring on the status of my application submitted last week.")
    assert not is_valid
    assert any("Policy-forbidden" in v for v in viols)

