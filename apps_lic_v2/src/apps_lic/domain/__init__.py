"""Domain contracts, data structures, and validators for apps_lic_v2."""

from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
    TouchPoint,
    TouchSequence,
    ValidationResult,
)
from apps_lic.domain.validators import (
    ChannelLengthValidator,
    GroundingValidator,
    QuestionEndingValidator,
    SpamTriggerValidator,
)

__all__ = [
    "CandidateFact",
    "CandidateProfile",
    "ChannelType",
    "OutreachMessageDraft",
    "RecipientClass",
    "RelationshipDistance",
    "TargetOpportunity",
    "TouchPoint",
    "TouchSequence",
    "ValidationResult",
    "ChannelLengthValidator",
    "GroundingValidator",
    "QuestionEndingValidator",
    "SpamTriggerValidator",
]
