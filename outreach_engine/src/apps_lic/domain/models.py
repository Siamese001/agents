"""Core domain models for Lifecycle Intelligence & Communication."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ChannelType(str, Enum):
    LINKEDIN_INMAIL = "inmail"
    LINKEDIN_CONNECTION = "connection_note"
    EMAIL = "email"
    FOLLOW_UP = "follow_up"


class AudiencePersona(str, Enum):
    EXECUTIVE_CONTACT = "executive_contact"
    EXECUTIVE_RECRUITER = "executive_recruiter"


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
    executive_summary: str = ""
    verified_facts: List[CandidateFact] = field(default_factory=list)
    key_competencies: List[str] = field(default_factory=list)
    current_title: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    phone: str = ""
    email: str = ""
    location: str = ""


class CandidateProfileLoader:
    """Authoritative loader and SSOT for candidate profiles."""

    _lock = threading.Lock()
    _cached_profile: Optional[CandidateProfile] = None
    _cached_mtime: float = -1.0
    _cached_path: Optional[Path] = None

    @classmethod
    def _resolve_profile_path(cls, explicit_path: Path | str | None = None) -> Path:
        if explicit_path is not None:
            return Path(explicit_path).resolve()
        env_override = os.environ.get("OUTREACH_CANDIDATE_PROFILE_PATH")
        if env_override:
            p = Path(env_override).resolve()
            if p.is_file():
                return p
        pkg_root = Path(__file__).resolve().parent.parent.parent.parent
        default_path = pkg_root / "config" / "candidate_profile.json"
        if default_path.is_file():
            return default_path
        repo_root = pkg_root.parent
        repo_fallback = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "resume" / "base" / "candidate_static_profile.json"
        if repo_fallback.is_file():
            return repo_fallback
        return default_path

    @classmethod
    def load_from_dict(cls, data: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> CandidateProfile:
        facts_data = data.get("verified_facts") or []
        facts: List[CandidateFact] = []
        for f in facts_data:
            if isinstance(f, dict):
                facts.append(
                    CandidateFact(
                        fact_id=str(f.get("fact_id", "")),
                        category=str(f.get("category", "general")),
                        statement=str(f.get("statement", "")),
                        metric=f.get("metric"),
                        source_reference=f.get("source_reference"),
                    )
                )
            elif isinstance(f, CandidateFact):
                facts.append(f)

        profile_data: Dict[str, Any] = {
            "candidate_id": str(data.get("candidate_id", "cand_exec")),
            "full_name": str(data.get("full_name") or data.get("name") or "Executive Candidate"),
            "target_title": str(data.get("target_title") or data.get("title") or "Engineering Leader"),
            "current_title": str(data.get("current_title") or data.get("title") or ""),
            "executive_summary": str(data.get("executive_summary") or data.get("background") or ""),
            "verified_facts": facts,
            "key_competencies": list(data.get("key_competencies") or []),
            "linkedin_url": str(data.get("linkedin_url") or data.get("linkedin") or ""),
            "github_url": str(data.get("github_url") or data.get("github") or ""),
            "phone": str(data.get("phone") or ""),
            "email": str(data.get("email") or ""),
            "location": str(data.get("location") or ""),
        }
        if overrides:
            for k, v in overrides.items():
                if v is not None:
                    profile_data[k] = v

        return CandidateProfile(**profile_data)

    @classmethod
    def load_default(
        cls,
        config_path: Path | str | None = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> CandidateProfile:
        resolved = cls._resolve_profile_path(config_path)
        if not resolved.is_file():
            return cls.load_from_dict({}, overrides)

        current_mtime = resolved.stat().st_mtime
        with cls._lock:
            if (
                cls._cached_profile is not None
                and cls._cached_path == resolved
                and cls._cached_mtime == current_mtime
                and not overrides
            ):
                return cls._cached_profile

            try:
                data = json.loads(resolved.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RuntimeError(f"Failed to parse candidate profile JSON from {resolved}: {exc}") from exc

            profile = cls.load_from_dict(data, overrides)
            if not overrides:
                cls._cached_profile = profile
                cls._cached_mtime = current_mtime
                cls._cached_path = resolved
            return profile

    @classmethod
    def clear_cache(cls) -> None:
        with cls._lock:
            cls._cached_profile = None
            cls._cached_mtime = -1.0
            cls._cached_path = None


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
    briefing_text: str = ""
    research_digest: str = ""
    evidence_items: List[Dict[str, Any]] = field(default_factory=list)
    sealed_resolution: Optional[Dict[str, Any]] = None


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
    research_metadata: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    signature_block: str = ""
    audience_persona: Optional[AudiencePersona] = None

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
    sealed_resolution: Optional[Dict[str, Any]] = None
