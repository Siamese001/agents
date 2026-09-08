"""Core domain models for Lifecycle Intelligence & Communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ChannelType(str, Enum):
    LINKEDIN_INMAIL = "inmail"
    LINKEDIN_CONNECTION = "connection_note"
    EMAIL = "email"
    FOLLOW_UP = "follow_up"


class RecipientClass(str, Enum):
    TALENT_PARTNER = "talent_partner"
    HIRING_MANAGER = "hiring_manager"
    EXECUTIVE_PEER = "executive_peer"
    BOARD_MEMBER = "board_member"


class RelationshipDistance(str, Enum):
    COLD = "cold"
    SECOND_DEGREE = "2nd_degree"
    WARM_REFERRAL = "warm_referral"
    FORMER_COLLEAGUE = "former_colleague"


@dataclass(frozen=True)
class CandidateFact:
    """A verified, indisputable candidate claim or metric."""
    fact_id: str
    category: str
    statement: str
    metric: Optional[str] = None
    source_reference: Optional[str] = None


@dataclass(frozen=True)
class CandidateProfile:
    """The authoritative candidate dossier containing verified facts only."""
    candidate_id: str
    full_name: str
    target_title: str
    executive_summary: str
    verified_facts: List[CandidateFact] = field(default_factory=list)
    key_competencies: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TargetOpportunity:
    """Target context and recipient brief for outbound messaging."""
    opportunity_id: str
    company_name: str
    role_title: str
    industry: str
    recipient_name: str
    recipient_title: str
    recipient_class: RecipientClass = RecipientClass.HIRING_MANAGER
    relationship_distance: RelationshipDistance = RelationshipDistance.COLD
    strategic_priorities: List[str] = field(default_factory=list)


@dataclass
class OutreachMessageDraft:
    """An outreach message draft produced by the pipeline."""
    draft_id: str
    channel: ChannelType
    subject: str
    body: str
    character_count: int = 0
    word_count: int = 0
    grounded_facts_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.character_count:
            self.character_count = len(self.body)
        if not self.word_count:
            self.word_count = len(self.body.split())


@dataclass
class ValidationResult:
    """Result of running domain validators over an outreach message."""
    is_valid: bool
    hard_gate_passed: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class TouchPoint:
    """A single scheduled touch within a multi-touch cadence."""
    touch_number: int
    day_offset: int
    channel: ChannelType
    objective: str
    draft: OutreachMessageDraft


@dataclass
class TouchSequence:
    """A coordinated sequence of touches planned for a target recipient."""
    sequence_id: str
    candidate_id: str
    opportunity_id: str
    touches: List[TouchPoint] = field(default_factory=list)
