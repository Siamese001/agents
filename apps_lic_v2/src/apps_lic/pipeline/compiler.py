"""Prompt compiler and context assembler with strict guardrails."""

from __future__ import annotations

from typing import Any, Dict, List

from apps_lic.domain.models import CandidateProfile, ChannelType, RecipientClass, TargetOpportunity


class PromptCompiler:
    """Compiles prompt context slots and enforces forbidden behavior rules."""

    def __init__(self, templates_dir: str | None = None) -> None:
        self.templates_dir = templates_dir

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

        # Persona tone selection based on recipient class
        tone_map = {
            RecipientClass.TALENT_PARTNER: "concise, direct, alignment-focused",
            RecipientClass.HIRING_MANAGER: "strategic, metrics-driven, problem-solving",
            RecipientClass.EXECUTIVE_PEER: "peer-to-peer, reciprocity-first, exploratory",
            RecipientClass.BOARD_MEMBER: "governance-oriented, high-level, fiduciary",
        }

        context = {
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
            "forbidden_behaviors": [
                "DO NOT invent a pre-existing personal or professional relationship.",
                "DO NOT invent application or interview stage status.",
                "DO NOT fabricate company initiatives not mentioned in strategic priorities.",
                "DO NOT make claims or quote metrics absent from verified facts.",
            ],
        }
        return context
