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
    RelationshipDistance,
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

    def _format_fact_phrase(self, statement: str) -> str:
        """Format candidate verified fact statement into a natural lowercased clause."""
        clean = (statement or "").strip().rstrip(".!?:;")
        if not clean:
            return ""
        first_word = clean.split()[0]
        if len(first_word) > 1 and first_word.isupper():
            return clean
        if clean and clean[0].isupper() and (len(clean) == 1 or clean[1].islower()):
            clean = clean[0].lower() + clean[1:]
        return clean

    def _compose_connection_note(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        template_id: str,
        hook: str,
        fact_statement: str,
    ) -> str:
        """Compose a LinkedIn connection note strictly bounded under 300 characters."""
        fact_phrase = self._format_fact_phrase(fact_statement)
        # Bounded fact slice for connection note
        fact_short = fact_phrase
        if len(fact_short) > 75:
            words = fact_short.split()
            accum = ""
            for w in words:
                if len(accum) + len(w) + 1 > 70:
                    break
                accum = f"{accum} {w}" if accum else w
            fact_short = (accum or " ".join(words[:6])) + "..."

        if template_id == "compact_recruiter_arc":
            if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Great seeing your work at {opportunity.company_name}. "
                    f"Following your {opportunity.role_title} search in {hook}. "
                    f"As {candidate.target_title}, {fact_short}.\n\n"
                    f"Open to connecting?"
                )
            elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Reaching out via mutual connection regarding {opportunity.company_name}'s {opportunity.role_title} search in {hook}. "
                    f"As {candidate.target_title}, {fact_short}.\n\n"
                    f"Open to connecting?"
                )
            else:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Following {opportunity.company_name}'s {opportunity.role_title} search in {hook}. "
                    f"As {candidate.target_title}, {fact_short}.\n\n"
                    f"Open to connecting?"
                )
        else:
            if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Great seeing your momentum at {opportunity.company_name}. "
                    f"Following your work in {hook}. "
                    f"In my work as {candidate.target_title}, {fact_short}.\n\n"
                    f"Open to catching up?"
                )
            elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Reaching out from our shared network regarding {opportunity.company_name}'s focus on {hook}. "
                    f"In my work as {candidate.target_title}, {fact_short}.\n\n"
                    f"Open to exchanging perspectives?"
                )
            elif opportunity.relationship_distance == RelationshipDistance.SECOND_DEGREE:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Following {opportunity.company_name}'s focus on {hook} from our shared circles. "
                    f"In my work as {candidate.target_title}, {fact_short}.\n\n"
                    f"Open to exchanging perspectives?"
                )
            else:
                body = (
                    f"Hi {opportunity.recipient_name},\n\n"
                    f"Noticed {opportunity.company_name}'s focus on {hook}. "
                    f"In my work as {candidate.target_title}, {fact_short}.\n\n"
                    f"Open to exchanging perspectives?"
                )

        if len(body) > 295:
            body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Following {opportunity.company_name}'s focus on {hook}. "
                f"In my work as {candidate.target_title}, {fact_phrase[:70]}...\n\n"
                f"Open to connecting?"
            )
        return body

    def _compose_recruiter_draft(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
        hook: str,
        fact_statement: str,
    ) -> tuple[str, str]:
        """Compose compact 2-paragraph draft aligned with compact_recruiter_arc.yaml."""
        fact_phrase = self._format_fact_phrase(fact_statement)

        if channel == ChannelType.EMAIL:
            subject = f"{candidate.full_name} / {opportunity.company_name} {opportunity.role_title} search"
        elif opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            subject = f"Reconnecting: {candidate.full_name} -> {opportunity.company_name} ({opportunity.role_title})"
        else:
            subject = f"{candidate.full_name} -> {opportunity.company_name} ({opportunity.role_title})"

        # Paragraph 1: Opener + Core fit statement and single proof point
        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            p1 = (
                f"Reaching out following our previous collaboration regarding {opportunity.company_name}'s {opportunity.role_title} search in {hook}. "
                f"As {candidate.target_title}, {fact_phrase}."
            )
        elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
            p1 = (
                f"Reaching out via mutual connection regarding {opportunity.company_name}'s {opportunity.role_title} search in {hook}. "
                f"As {candidate.target_title}, {fact_phrase}."
            )
        else:
            p1 = (
                f"Reaching out regarding {opportunity.company_name}'s priorities in {hook}. "
                f"As {candidate.target_title}, {fact_phrase}."
            )

        # Paragraph 2: Low-friction ask
        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            p2 = "Would you be open to connecting briefly to discuss the mandate?"
        else:
            p2 = "Would you be open to connecting on this role?"

        body = f"Hi {opportunity.recipient_name},\n\n{p1}\n\n{p2}"
        return subject, body

    def _compose_executive_draft(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
        hook: str,
        fact_statement: str,
    ) -> tuple[str, str]:
        """Compose 4-part executive arc aligned with exec_positioning.yaml."""
        fact_phrase = self._format_fact_phrase(fact_statement)

        # 1. Subject calibration
        if channel == ChannelType.EMAIL:
            if opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
                subject = f"{opportunity.company_name} {opportunity.role_title} - Strategic Governance Perspective"
            elif opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
                subject = f"Catching up: {opportunity.company_name} / {candidate.full_name}"
            else:
                subject = f"{opportunity.company_name} / {opportunity.role_title} - Strategic Alignment"
        else:
            if opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
                subject = f"{opportunity.company_name} / {opportunity.role_title} - Board & Governance Alignment"
            elif opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
                subject = f"Catching up / {opportunity.company_name} {opportunity.role_title} perspective"
            else:
                subject = f"{opportunity.company_name} / {opportunity.role_title} - Executive Alignment"

        # 2. Slot 1: Credible Opener
        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            opener = f"Great to see your continued momentum at {opportunity.company_name}."
        elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
            opener = f"Reaching out following recommendations from our shared network regarding {opportunity.company_name}'s work in {hook}."
        elif opportunity.relationship_distance == RelationshipDistance.SECOND_DEGREE:
            opener = f"Reaching out from our shared network, following {opportunity.company_name}'s focus on {hook}."
        elif opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
            opener = f"Following {opportunity.company_name}'s strategic mandate and governance focus on {hook}."
        else:
            opener = f"I have been following {opportunity.company_name}'s focus on {hook}."

        # 3. Slot 2: Strategic Fit Signal
        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
            fit = f"In my executive leadership work as {candidate.target_title}, {fact_phrase}."
        else:
            fit = f"In my recent work as {candidate.target_title}, {fact_phrase}."

        # 4. Slot 3: Reciprocity Offer
        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
            reciprocity = "Happy to share architectural lessons and governance benchmarks from similar scale transformations."
        elif opportunity.recipient_class == RecipientClass.HIRING_MANAGER:
            reciprocity = "Happy to share our operational scaling framework and metrics if useful for your roadmap."
        elif opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            reciprocity = "Happy to compare notes and share operational lessons from similar architecture transitions."
        else:
            reciprocity = "Happy to share our operational playbook and architectural benchmarks if helpful for your roadmap."

        # 5. Slot 4: Respectful Ask
        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            ask = "Open to catching up for a brief conversation sometime next week?"
        elif opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
            ask = "Given your focus, would you be open to a brief high-level conversation next week?"
        else:
            ask = "Given your focus, would you be open to a brief conversation next week?"

        p1 = f"{opener} {fit}"
        p2 = f"{reciprocity} {ask}"
        body = f"Hi {opportunity.recipient_name},\n\n{p1}\n\n{p2}"
        return subject, body

    def _compose_general_draft(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
        hook: str,
        fact_statement: str,
    ) -> tuple[str, str]:
        """Compose general/hiring-manager draft aligned with outreach_draft_v2.yaml."""
        fact_phrase = self._format_fact_phrase(fact_statement)
        subject = f"{opportunity.company_name} / {opportunity.role_title} - Strategic Alignment"

        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            opener = f"Great to reconnect as {opportunity.company_name} expands its focus on {hook}."
        elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
            opener = f"Reaching out via our shared network regarding {opportunity.company_name}'s work in {hook}."
        elif opportunity.relationship_distance == RelationshipDistance.SECOND_DEGREE:
            opener = f"Following {opportunity.company_name}'s work in {opportunity.industry} from our shared circles."
        else:
            opener = f"I have been following {opportunity.company_name}'s work in {opportunity.industry}."

        fit = f"In my recent work as {candidate.target_title}, {fact_phrase}."
        reciprocity = "Happy to share our operational scaling framework and metrics if useful for your roadmap."
        ask = "Given your focus, would you be open to a brief conversation next week?"

        p1 = f"{opener} {fit}"
        p2 = f"{reciprocity} {ask}"
        body = f"Hi {opportunity.recipient_name},\n\n{p1}\n\n{p2}"
        return subject, body

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

        # Connection notes have a strict 300-char limit
        if channel == ChannelType.LINKEDIN_CONNECTION:
            subject = ""
            body = self._compose_connection_note(candidate, opportunity, template_id, hook, fact_statement)
        elif template_id == "compact_recruiter_arc":
            subject, body = self._compose_recruiter_draft(candidate, opportunity, channel, hook, fact_statement)
        elif template_id == "exec_positioning":
            subject, body = self._compose_executive_draft(candidate, opportunity, channel, hook, fact_statement)
        else:
            subject, body = self._compose_general_draft(candidate, opportunity, channel, hook, fact_statement)

        # Enforce no em dashes
        body = body.replace("—", ", ").replace("\u2014", ", ")
        subject = subject.replace("—", "-").replace("\u2014", "-")

        return subject, body, fact_ids
