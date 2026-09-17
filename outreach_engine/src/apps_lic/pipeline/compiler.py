"""Prompt compiler and context assembler with strict guardrails."""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateProfile,
    ChannelType,
    RecipientClass,
    TargetOpportunity,
)


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
    title = profile.current_title or profile.target_title
    if title:
        lines.append(title)
    if profile.linkedin_url:
        lines.append(profile.linkedin_url)
    if profile.github_url:
        lines.append(profile.github_url)
    if profile.phone:
        lines.append(profile.phone)
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
    if profile.linkedin_url:
        lines.append(profile.linkedin_url)
    if profile.phone:
        lines.append(profile.phone)
    return "\n".join(lines)


@functools.lru_cache(maxsize=32)
def _load_cached_yaml_template(file_path_str: str, mtime: float) -> Dict[str, Any]:
    """Parse and cache a YAML template file, keyed by path and mtime."""
    try:
        with open(file_path_str, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


class PromptCompiler:
    """Compiles prompt context slots and enforces forbidden behavior rules."""

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        if templates_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            self.templates_dir = repo_root / "config" / "prompt_templates"
        else:
            self.templates_dir = Path(templates_dir)

    def load_template(self, template_name: str) -> Dict[str, Any]:
        """Loads a YAML prompt template definition with mtime-aware caching."""
        tmpl_file = self.templates_dir / f"{template_name}.yaml"
        if not tmpl_file.is_file():
            tmpl_file = self.templates_dir / template_name
        if tmpl_file.is_file():
            try:
                mtime = tmpl_file.stat().st_mtime
                return dict(_load_cached_yaml_template(str(tmpl_file.resolve()), mtime))
            except Exception:  # guardian: allow-silent-swallow -- fallback to empty dict if template is unreadable or malformed
                pass
        return {}

    def select_template_for_channel(
        self,
        channel: ChannelType,
        recipient_class: RecipientClass,
        audience_persona: Optional[AudiencePersona] = None,
    ) -> str:
        """Selects the optimal production template based on channel, tier, and persona."""
        if audience_persona == AudiencePersona.EXECUTIVE_RECRUITER or recipient_class == RecipientClass.TALENT_PARTNER:
            return "compact_recruiter_arc"
        if audience_persona == AudiencePersona.EXECUTIVE_CONTACT or recipient_class in (
            RecipientClass.EXECUTIVE_PEER,
            RecipientClass.BOARD_MEMBER,
        ):
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
        facts_block = "\n".join(
            f"- [{f.fact_id}] {f.statement} (Metric: {f.metric or 'N/A'})"
            for f in candidate.verified_facts
        )

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
            "DO NOT use em dashes.",
            "DO NOT use markdown link syntax.",
            "DO NOT use subordinate or deferential job-seeker language.",
        ]
        if template_spec.get("forbidden_behaviors"):
            for b in template_spec["forbidden_behaviors"]:
                clean_b = f"DO NOT {b.replace('_', ' ')}."
                if clean_b not in forbidden:
                    forbidden.append(clean_b)

        context = {
            "template_id": template_id,
            "template_purpose": template_spec.get("purpose", "").strip(),
            "candidate_name": candidate.full_name,
            "candidate_title": candidate.target_title,
            "candidate_facts": facts_block,
            "recipient_name": opportunity.recipient_name,
            "recipient_title": opportunity.recipient_title,
            "recipient_class": opportunity.recipient_class.value,
            "company_name": opportunity.company_name,
            "role_title": opportunity.role_title,
            "industry": opportunity.industry,
            "strategic_priorities": priorities_block,
            "briefing_summary": opportunity.briefing_text[:300] if opportunity.briefing_text else "",
            "research_digest": opportunity.research_digest,
            "tone": tone_map.get(opportunity.recipient_class, "professional"),
            "channel": channel.value,
            "forbidden_behaviors": forbidden,
        }
        return context

    def _format_strategic_hook(self, raw_hook: str, company_name: Optional[str] = None) -> str:
        """Format and condense a raw priority or JD bullet into a clean conversational phrase."""
        clean = (raw_hook or "").strip().rstrip(".!?:;")
        # If multi-sentence, take the first sentence
        for sep in (". ", "; ", " - "):
            if sep in clean:
                clean = clean.split(sep)[0].strip()
        # Strip leading bullet, numbering markers, or executive prefixes
        clean = re.sub(r"^(?:\d+[\.\)]\s*|[-*•]\s*|signal:\s*|focus:\s*)", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^[A-Za-z\s]+(?:’s|\x27s)\s+immediate mandate is to\s*", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^[A-Za-z\s]+(?:’s|\x27s)\s+organizational priorities revolve around\s*", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^(?:A\s+)?core priority will be\s*", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^From an architectural standpoint,\s*(?:he|she|they) (?:is|are) focused on\s*", "", clean, flags=re.IGNORECASE).strip()

        # Convert common leading verbs to -ing gerund for natural sentence flow after "focus on ..."
        verb_map = {
            "translate": "translating",
            "modernize": "modernizing",
            "transform": "transforming",
            "optimize": "optimizing",
            "execute": "executing",
            "deliver": "delivering",
            "drive": "driving",
            "accelerate": "accelerating",
            "architect": "architecting",
            "deploy": "deploying",
            "migrate": "migrating",
            "consolidate": "consolidating",
            "streamline": "streamlining",
            "navigate": "navigating",
            "build": "building",
            "scale": "scaling",
            "lead": "leading",
            "integrate": "integrating",
            "standardize": "standardizing",
            "move": "moving",
            "generate": "generating",
            "expand": "expanding",
            "advance": "advancing",
            "establish": "establishing",
        }
        for v, g in verb_map.items():
            if re.match(rf"^{v}\b", clean, flags=re.IGNORECASE):
                clean = re.sub(rf"^{v}\b", g, clean, count=1, flags=re.IGNORECASE)
                break

        # If first word is capitalized, lowercase if it is not an acronym or proper noun
        if clean and clean[0].isupper() and (len(clean) == 1 or clean[1].islower()):
            first_word = clean.split()[0].lower()
            preserved_terms = {"aws", "azure", "gcp", "ai", "ml", "the"}
            if company_name:
                for tok in re.findall(r"\b[A-Za-z]{3,}\b", company_name.lower()):
                    preserved_terms.add(tok)
            if first_word not in preserved_terms:
                clean = clean[0].lower() + clean[1:]

        # Truncate gracefully at word boundary if overly verbose
        if len(clean) > 90:
            words = clean.split()
            truncated = ""
            for w in words:
                if len(truncated) + len(w) + 1 > 85:
                    break
                truncated = f"{truncated} {w}" if truncated else w
            clean = truncated if truncated else " ".join(words[:10])

        return clean.strip().rstrip(".!?:;")

    def render_draft_message(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
        audience_persona: Optional[AudiencePersona] = None,
    ) -> tuple[str, str, list[str]]:
        """Renders subject, body, and used fact IDs using template guidance."""
        context = self.assemble_context(candidate, opportunity, channel, audience_persona)
        template_id = context["template_id"]

        lead_fact = candidate.verified_facts[0] if candidate.verified_facts else None
        fact_statement = lead_fact.statement if lead_fact else candidate.executive_summary
        fact_ids = [lead_fact.fact_id] if lead_fact else []

        raw_hook = opportunity.strategic_priorities[0] if opportunity.strategic_priorities else opportunity.industry
        hook = self._format_strategic_hook(raw_hook, company_name=opportunity.company_name)

        # Connection notes have a 300-char limit
        if channel == ChannelType.LINKEDIN_CONNECTION:
            subject = ""
            if template_id == "compact_recruiter_arc":
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Following {opportunity.company_name}'s {opportunity.role_title} search in {hook}. "
                    f"As {candidate.target_title}, {fact_statement}.\n\n"
                    f"Open to connecting?"
                )
            else:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Noticed {opportunity.company_name}'s focus on {hook}. "
                    f"In my work as {candidate.target_title}, {fact_statement}.\n\n"
                    f"Open to exchanging perspectives?"
                )
            if len(body) > 295:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Following {opportunity.company_name}'s focus on {hook}. "
                    f"In my work as {candidate.target_title}, {fact_statement[:110]}...\n\n"
                    f"Open to connecting?"
                )
            body = body.replace("—", ", ").replace("\u2014", ", ")
            return subject, body, fact_ids

        if template_id == "exec_positioning":
            subject = f"{opportunity.company_name} / {opportunity.role_title} - Executive Alignment"
            body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"I have been following {opportunity.company_name}'s focus on {hook}. "
                f"In my recent work as {candidate.target_title}, {fact_statement}.\n\n"
                f"Given your focus, would you be open to a brief conversation next week?"
            )
        elif template_id == "compact_recruiter_arc":
            subject = f"{candidate.full_name} -> {opportunity.company_name} ({opportunity.role_title})"
            body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Reaching out regarding {opportunity.company_name}'s priorities in {hook}. "
                f"As {candidate.target_title}, {fact_statement}.\n\n"
                f"Would you be open to connecting on this role?"
            )
        else:
            subject = f"{opportunity.company_name} / {opportunity.role_title} - Strategic Alignment"
            body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"I have been following {opportunity.company_name}'s work in {opportunity.industry}. "
                f"In my recent work as {candidate.target_title}, {fact_statement}.\n\n"
                f"Given your focus, would you be open to a brief conversation next week?"
            )

        # Enforce no em dashes
        body = body.replace("—", ", ").replace("\u2014", ", ")
        subject = subject.replace("—", "-").replace("\u2014", "-")

        return subject, body, fact_ids
