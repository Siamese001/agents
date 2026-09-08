"""Prompt compiler and context assembler with strict guardrails."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from apps_lic.domain.models import CandidateProfile, ChannelType, RecipientClass, TargetOpportunity


class PromptCompiler:
    """Compiles prompt context slots and enforces forbidden behavior rules."""

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        if templates_dir is None:
            # Default to config/prompt_templates relative to package root
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            self.templates_dir = repo_root / "config" / "prompt_templates"
        else:
            self.templates_dir = Path(templates_dir)

    def load_template(self, template_name: str) -> Dict[str, Any]:
        """Loads a YAML prompt template definition."""
        tmpl_file = self.templates_dir / f"{template_name}.yaml"
        if not tmpl_file.is_file():
            # Try direct file match
            tmpl_file = self.templates_dir / template_name
        if tmpl_file.is_file():
            try:
                with open(tmpl_file, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        return {}

    def select_template_for_channel(self, channel: ChannelType, recipient_class: RecipientClass) -> str:
        """Selects the optimal production template based on channel and tier."""
        if recipient_class in (RecipientClass.EXECUTIVE_PEER, RecipientClass.BOARD_MEMBER):
            return "exec_positioning"
        if recipient_class == RecipientClass.TALENT_PARTNER:
            return "compact_recruiter_arc"
        return "outreach_draft_v2"

    def assemble_context(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
    ) -> Dict[str, Any]:
        """Assembles verified context slots with zero hallucinated facts."""
        facts_block = "\n".join(
            f"- [{f.fact_id}] {f.statement} (Metric: {f.metric or 'N/A'})"
            for f in candidate.verified_facts
        )

        priorities_block = "\n".join(f"- {p}" for p in opportunity.strategic_priorities)

        template_id = self.select_template_for_channel(channel, opportunity.recipient_class)
        template_spec = self.load_template(template_id)

        # Persona tone selection based on recipient class
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
            "tone": tone_map.get(opportunity.recipient_class, "professional"),
            "channel": channel.value,
            "forbidden_behaviors": forbidden,
        }
        return context
