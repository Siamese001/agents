"""Outreach Swarm Coordinator: Pipeline Bridge for Multi-Agent Message Delivery.

Part of Monorepo-Wide Swarm Integration (Wave 2).
Coordinates campaign message assembly, tone and brevity deliberation,
and delivery signoff via the Outreach Swarm Challenger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from apps_lic.runtime.outreach_swarm_challenger import (
    OutreachSwarmChallenger,
    OutreachSwarmDisposition,
    OutreachSwarmReceipt,
)


@dataclass(frozen=True, slots=True)
class CertifiedOutreachPackage:
    """Certified candidate outreach package ready for transmission."""

    campaign_id: str
    recipient_name: str
    certified_body: str
    word_count: int
    is_deliverable: bool
    receipt: OutreachSwarmReceipt


class OutreachSwarmCoordinator:
    """Coordinates outreach message generation and multi-agent swarm deliberation."""

    def __init__(self, challenger: OutreachSwarmChallenger | None = None) -> None:
        self._challenger = challenger or OutreachSwarmChallenger()

    def compile_and_certify(
        self,
        campaign_id: str,
        recipient_name: str,
        value_props: Sequence[str],
        role_title: str = "Technology Leader",
        company_name: str = "Enterprise Partner",
        max_turns: int = 3,
    ) -> CertifiedOutreachPackage:
        """Assemble initial draft from value propositions and deliberate through swarm."""
        props_text = " ".join(value_props)
        initial_draft = (
            f"Hi {recipient_name}, reaching out regarding the {role_title} opportunity at {company_name}. "
            f"{props_text} Would welcome thirty minutes to discuss mutual alignment."
        )

        receipt = self._challenger.execute(
            text=initial_draft,
            campaign_id=campaign_id,
            max_turns=max_turns,
        )

        is_deliverable = receipt.final_disposition == OutreachSwarmDisposition.APPROVED

        return CertifiedOutreachPackage(
            campaign_id=campaign_id,
            recipient_name=recipient_name,
            certified_body=receipt.certified_message,
            word_count=receipt.word_count,
            is_deliverable=is_deliverable,
            receipt=receipt,
        )
