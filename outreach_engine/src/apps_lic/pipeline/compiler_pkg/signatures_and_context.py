"""Signature blocks, YAML template caching, and context slot assembly for PromptCompiler."""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateProfile,
    ChannelType,
    RecipientClass,
    TargetOpportunity,
)

_log = logging.getLogger(__name__)


def get_executive_signature_block(candidate: CandidateProfile | str | None = None) -> str:
    """Standard executive signature block compliant with exec_positioning.yaml and CandidateProfile SSOT."""
    from apps_lic.domain.models import CandidateProfileLoader
    if isinstance(candidate, CandidateProfile):
        profile = candidate
    elif isinstance(candidate, str) and candidate.strip():
        profile = CandidateProfileLoader.load_default(overrides={"full_name": candidate.strip()})
    else:
        profile = CandidateProfileLoader.load_default()

    lines = [profile.full_name]
    if profile.current_title or profile.target_title:
        lines.append(profile.current_title or profile.target_title)
    for attr in (profile.linkedin_url, profile.github_url, profile.phone):
        if attr:
            lines.append(attr)
    return "\n".join(lines)


def get_recruiter_signature_block(candidate: CandidateProfile | str | None = None) -> str:
    """Compact signature block for recruiter communications compliant with CandidateProfile SSOT."""
    from apps_lic.domain.models import CandidateProfileLoader
    if isinstance(candidate, CandidateProfile):
        profile = candidate
    elif isinstance(candidate, str) and candidate.strip():
        profile = CandidateProfileLoader.load_default(overrides={"full_name": candidate.strip()})
    else:
        profile = CandidateProfileLoader.load_default()

    lines = [profile.full_name]
    for attr in (profile.linkedin_url, profile.phone):
        if attr:
            lines.append(attr)
    return "\n".join(lines)


@functools.lru_cache(maxsize=32)
def _load_cached_yaml_template(file_path_str: str, mtime: float) -> Dict[str, Any]:
    """Parse and cache a YAML template file, keyed by path and mtime."""
    parsed: Any = None
    try:
        with open(file_path_str, "r", encoding="utf-8") as f:
            parsed = yaml.safe_load(f)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
        _log.warning("Failed loading prompt template %s: %s", file_path_str, exc)
    return dict(parsed) if isinstance(parsed, dict) else {}


class PromptContextAssembler:
    """Base mixin loading prompt templates and assembling verified context slots."""

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        if templates_dir is None:
            outreach_root = Path(__file__).resolve().parents[4]
            self.templates_dir = outreach_root / "config" / "prompt_templates"
        else:
            self.templates_dir = Path(templates_dir)

    def load_template(self, template_name: str) -> Dict[str, Any]:
        """Loads a YAML prompt template definition with mtime-aware caching."""
        try:
            base_dir = self.templates_dir.resolve()
            tmpl_file = (self.templates_dir / f"{template_name}.yaml").resolve()
            if not tmpl_file.is_file():
                tmpl_file = (self.templates_dir / template_name).resolve()
            if tmpl_file.is_file() and tmpl_file.is_relative_to(base_dir):
                mtime = tmpl_file.stat().st_mtime
                return dict(_load_cached_yaml_template(str(tmpl_file), mtime))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return {}

    def select_template_for_channel(
        self, channel: ChannelType, recipient_class: RecipientClass, audience_persona: Optional[AudiencePersona] = None,
    ) -> str:
        """Selects the optimal production template based on channel, tier, and persona."""
        if audience_persona == AudiencePersona.EXECUTIVE_RECRUITER or recipient_class == RecipientClass.TALENT_PARTNER:
            return "compact_recruiter_arc"
        if audience_persona == AudiencePersona.EXECUTIVE_CONTACT or recipient_class in (RecipientClass.EXECUTIVE_PEER, RecipientClass.BOARD_MEMBER):
            return "exec_positioning"
        return "outreach_draft_v2"

    def assemble_context(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
        audience_persona: Optional[AudiencePersona] = None,
    ) -> Dict[str, Any]:
        """Assembles verified context slots with zero hallucinated facts."""
        grounded = candidate.grounded_facts
        facts_block = "\n".join(
            f"- [{f.fact_id}] {f.statement} (Metric: {f.metric or 'N/A'})"
            for f in grounded
        ) if grounded else "- No provenance-backed candidate facts available."

        priorities_block = "\n".join(f"- {p}" for p in opportunity.strategic_priorities)

        template_id = self.select_template_for_channel(channel, opportunity.recipient_class, audience_persona)
        template_spec = self.load_template(template_id)

        tone_map = {
            RecipientClass.TALENT_PARTNER: "concise, direct, alignment-focused",
            RecipientClass.HIRING_MANAGER: "strategic, metrics-driven, problem-solving",
            RecipientClass.EXECUTIVE_PEER: "peer-to-peer, reciprocity-first, exploratory",
            RecipientClass.BOARD_MEMBER: "governance-oriented, high-level, fiduciary",
        }

        forbidden = [
            "DO NOT invent a pre-existing personal or professional relationship.",
            "DO NOT invent application or interview stage status.",
            "DO NOT fabricate company initiatives not mentioned in strategic priorities.",
            "DO NOT make claims or quote metrics absent from verified facts.",
            "DO NOT use em dashes.", "DO NOT use markdown link syntax.",
            "DO NOT use subordinate or deferential job-seeker language.",
        ]
        if template_spec.get("forbidden_behaviors"):
            for b in template_spec["forbidden_behaviors"]:
                if isinstance(b, str) and b.strip():
                    clean_b = f"DO NOT {b.replace('_', ' ')}."
                    if clean_b not in forbidden:
                        forbidden.append(clean_b)

        eff_channel = ChannelType(channel) if isinstance(channel, str) else channel
        ch_val = eff_channel.value if hasattr(eff_channel, "value") else str(eff_channel)
        rc = opportunity.recipient_class
        rc_val = rc.value if hasattr(rc, "value") else str(rc)

        return {
            "template_id": template_id,
            "template_purpose": str(template_spec.get("purpose") or "").strip(),
            "candidate_name": candidate.full_name,
            "candidate_title": candidate.target_title,
            "candidate_facts": facts_block,
            "recipient_name": opportunity.recipient_name,
            "recipient_title": opportunity.recipient_title,
            "recipient_class": rc_val,
            "company_name": opportunity.company_name,
            "role_title": opportunity.role_title,
            "industry": opportunity.industry,
            "strategic_priorities": priorities_block,
            "briefing_summary": opportunity.briefing_text[:300] if opportunity.briefing_text else "",
            "research_digest": opportunity.research_digest,
            "tone": tone_map.get(opportunity.recipient_class, "professional"),
            "channel": ch_val,
            "forbidden_behaviors": forbidden,
        }


__all__ = [
    "PromptContextAssembler",
    "_load_cached_yaml_template",
    "get_executive_signature_block",
    "get_recruiter_signature_block",
]
