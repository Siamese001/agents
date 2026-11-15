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
            source_reference="canonical_tenure_dossier",
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


def test_forbidden_claims_validator_expanded_compensation_and_dollar_normalization():
    from apps_lic.domain.models import CandidateFact
    from apps_lic.domain.validators import ForbiddenClaimsValidator

    val = ForbiddenClaimsValidator()
    # 1. Catch 1-digit / 4-digit bonus, package, hourly, and retainer demands
    assert val.validate("Seeking a $2M bonus as part of the package.")[0] is False
    assert val.validate("Expecting $1000/hr or a monthly retainer for advisory.")[0] is False
    assert val.validate("Looking for a $500k base salary.")[0] is False

    # 2. Normalize dollar tokens ($10M matches $10,000,000 in verified_facts)
    verified_facts = [
        CandidateFact(
            fact_id="f_rev",
            category="impact",
            statement="Delivered $10,000,000 in annualized platform revenue growth",
            metric="$10,000,000",
            source_reference="dossier",
        ),
        CandidateFact(
            fact_id="f_save",
            category="efficiency",
            statement="Generated $18M in annual infrastructure cost savings",
            metric="$18M",
            source_reference="dossier",
        ),
    ]
    is_valid_norm, viols_norm = val.validate(
        "My work delivered $10M in annualized platform revenue growth and $18M in annual infrastructure savings.",
        verified_facts=verified_facts,
    )
    assert is_valid_norm, f"Expected normalized dollar claims to pass, got: {viols_norm}"


def test_outbound_privacy_validator_and_orchestrator_validate_draft_wiring():
    from apps_lic.domain.models import (
        CandidateProfileLoader,
        ChannelType,
        OutreachMessageDraft,
        RecipientClass,
        RelationshipDistance,
        TargetOpportunity,
    )
    from apps_lic.domain.validators import OutboundPrivacyValidator
    from apps_lic.pipeline.orchestrator import OutreachOrchestrator

    priv = OutboundPrivacyValidator()
    assert priv.validate("Here is a leaked key sk-proj-1234567890abcdefghijklmnop")[0] is False
    assert priv.validate("Note: [INTERNAL] do not share with external client")[0] is False

    orch = OutreachOrchestrator()
    candidate = CandidateProfileLoader.load_default()
    opportunity = TargetOpportunity(
        opportunity_id="opp_priv",
        company_name="Truist",
        role_title="VP of AI",
        industry="Financial Services",
        recipient_name="Alex Morgan",
        recipient_title="Head of Engineering",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["AI governance"],
        sealed_resolution={"is_verified": True, "resolution_source": "CANONICAL_FIXTURE"},
    )
    leaked_draft = OutreachMessageDraft(
        draft_id="d_leak",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist AI governance",
        body="Alex, [INTERNAL] token sk-proj-1234567890abcdefghijklmnop - open to a brief exchange?",
        grounded_facts_used=[candidate.verified_facts[0].fact_id],
    )
    val_res = orch.validate_draft(leaked_draft, candidate, opportunity)
    assert not val_res.is_valid
    assert val_res.scores["privacy_score"] == 0.0
    assert any("Outbound privacy block" in v for v in val_res.violations)

    verdict = orch.evaluate_authoritative_draft(leaked_draft, candidate, opportunity)
    assert not verdict.passed
    assert verdict.scores["privacy_score"] == 0.0
    assert "unsupported_personalization_score" in verdict.scores
    assert len(verdict.scores) >= 10


def test_pct_certificate_and_metric_laundering_blocked():
    from apps_lic.domain.models import CandidateFact
    from apps_lic.domain.validators import (
        METRIC_LAUNDERED_FROM_OPPORTUNITY,
        PCTCertificate,
        verify_candidate_metric_grounding,
    )

    cand_facts = [
        CandidateFact(
            fact_id="f_cand_18m",
            category="efficiency",
            statement="Generated $18M in annual infrastructure cost savings",
            metric="$18M",
            source_reference="chunk_cand_01",
        )
    ]
    opp_ctx = "Truist is executing a $50M core banking cloud migration initiative."

    # 1. Valid candidate metric produces verified PCTCertificate
    res_ok = verify_candidate_metric_grounding(
        "In my recent work, I generated $18M in annual infrastructure cost savings.",
        candidate_facts=cand_facts,
        opportunity_context=opp_ctx,
        declared_fact_ids=["f_cand_18m"],
    )
    assert res_ok.passed
    assert len(res_ok.certificates) == 1
    cert: PCTCertificate = res_ok.certificates[0]
    assert cert.in_cand is True
    assert cert.verified is True
    assert cert.fact_id == "f_cand_18m"
    assert cert.source_chunk_id == "chunk_cand_01"

    # 2. Candidate-attributed metric coming ONLY from opportunity context fails closed
    res_laundered = verify_candidate_metric_grounding(
        "In my recent work, I delivered a $50M core banking cloud migration.",
        candidate_facts=cand_facts,
        opportunity_context=opp_ctx,
        declared_fact_ids=["f_cand_18m"],
    )
    assert not res_laundered.passed
    assert any(METRIC_LAUNDERED_FROM_OPPORTUNITY in v for v in res_laundered.violations)
    assert res_laundered.certificates[0].in_opp is True
    assert res_laundered.certificates[0].in_cand is False


def test_sequence_x2_validator_and_reserve_pool_repair():
    from apps_lic.domain.models import CandidateFact
    from apps_lic.domain.repair import repair_touch_with_reserve_pool
    from apps_lic.domain.validators import (
        EXEMPLAR_4GRAM_OVERLAP_EXCEEDED,
        INV_LIC_C0_DISJOINT_TOUCH_FACTS,
        INV_RESUME_NO_UNDEFINED_ACRONYMS,
        PAIRWISE_COSINE_EXCEEDED,
        ZERO_DUPLICATE_OPENERS_AND_CTAS,
        check_undefined_mga_acronym,
        validate_sequence_x2,
    )

    assert check_undefined_mga_acronym("Scaled underwriting across MGAs nationwide.")[0] is False
    assert check_undefined_mga_acronym("Scaled underwriting across Managing General Agents (MGAs) nationwide.")[0] is True

    cand_facts = [
        CandidateFact(fact_id="f1", category="scale", statement="Scaled platform to $18M annual savings", metric="$18M", source_reference="c1"),
        CandidateFact(fact_id="f2", category="speed", statement="Cut deployment latency by 42% across regions", metric="42%", source_reference="c2"),
        CandidateFact(fact_id="f_res", category="growth", statement="Expanded enterprise adoption across 120 production services", metric="120", source_reference="c_res"),
    ]
    alloc_plan = {
        "allocated_fact_ids_by_touch": {1: ["f1"], 2: ["f2"]},
        "reserve_repair_pool_fact_ids": ["f_res"],
        "reserve_repair_pool_facts": [cand_facts[2]],
    }

    bad_touches = [
        {"touch_number": 1, "body": "Hi Alex, I scaled platform architecture to $18M annual savings for MGAs. Open to connecting?", "grounded_facts_used": ["f1"]},
        {"touch_number": 2, "body": "Hi Alex, I scaled platform architecture to $18M annual savings for enterprise teams. Open to connecting?", "grounded_facts_used": ["f1"]},
    ]
    rep_bad = validate_sequence_x2(
        bad_touches,
        allocation_plan=alloc_plan,
        e0_exemplars=["scaled platform architecture to annual savings for enterprise teams"],
        candidate_facts=cand_facts,
    )
    assert not rep_bad.passed
    codes = set(rep_bad.violation_codes)
    assert PAIRWISE_COSINE_EXCEEDED in codes
    assert ZERO_DUPLICATE_OPENERS_AND_CTAS in codes
    assert EXEMPLAR_4GRAM_OVERLAP_EXCEEDED in codes
    assert INV_LIC_C0_DISJOINT_TOUCH_FACTS in codes
    assert INV_RESUME_NO_UNDEFINED_ACRONYMS in codes

    # Repair Touch 2 using reserve pool and verify clean sequence passes X2
    good_touches = [
        {
            "touch_number": 1,
            "body": "Hi Alex, following Truist's platform modernization, I scaled infrastructure to $18M annual savings for Managing General Agents (MGAs). Open to a brief exchange next week?",
            "grounded_facts_used": ["f1"],
        },
        {
            "touch_number": 2,
            "body": "Hello Alex, regarding distributed release velocity, I cut deployment latency by $18M across global regions. Would Thursday work for a quick call?",
            "grounded_facts_used": ["f1"],
        },
    ]
    repair_res = repair_touch_with_reserve_pool(
        good_touches[1],
        allocation_plan=alloc_plan,
        colliding_metric="$18M",
    )
    assert repair_res.repaired
    assert repair_res.replacement_fact_id == "f_res"
    assert repair_res.certificate.verified is True
    assert "120" in good_touches[1]["body"]

    rep_good = validate_sequence_x2(
        good_touches,
        allocation_plan=alloc_plan,
        e0_exemplars=["distinct exemplar text with zero four gram overlap against outreach body"],
        candidate_facts=cand_facts,
    )
    assert rep_good.passed, f"Expected repaired sequence to pass X2, got: {rep_good.violation_messages}"



