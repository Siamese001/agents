"""Research Service with Integrated Swarm Retrieval Cross-Examination.

Part of Monorepo-Wide Swarm Integration (Wave 2).
Coordinates source harvesting, insight synthesis, and multi-agent retrieval
cross-examination to guarantee full factual attribution and prevent hallucinations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from apps_research.reasoning.retrieval_challenger import (
    RetrievalChallenger,
    RetrievalDeliberationReceipt,
    RetrievalDisposition,
)

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CertifiedResearchResult:
    """Outcome of research synthesis after multi-agent cross-examination."""

    query: str
    certified_findings: tuple[str, ...]
    unverified_findings_rejected: tuple[str, ...]
    receipt: RetrievalDeliberationReceipt
    is_fully_grounded: bool

    @property
    def total_claims(self) -> int:
        return len(self.certified_findings) + len(self.unverified_findings_rejected)


class ResearchService:
    """Orchestrator for grounded research synthesis and cross-examination."""

    def __init__(self, challenger: RetrievalChallenger | None = None) -> None:
        self._challenger = challenger or RetrievalChallenger()

    def synthesize_research(
        self,
        query: str,
        candidate_claims: Sequence[str],
        sources: Sequence[Mapping[str, Any]],
        canonical_assertions: Sequence[str] | None = None,
        confidence_floor: float = 0.65,
    ) -> CertifiedResearchResult:
        """Synthesize research findings with mandatory cross-examiner audit."""
        if not candidate_claims:
            receipt = self._challenger.cross_examine(
                query=query,
                claims=(),
                sources=sources,
                canonical_graph_assertions=canonical_assertions,
                confidence_floor=confidence_floor,
            )
            return CertifiedResearchResult(
                query=query,
                certified_findings=(),
                unverified_findings_rejected=(),
                receipt=receipt,
                is_fully_grounded=True,
            )

        receipt = self._challenger.cross_examine(
            query=query,
            claims=candidate_claims,
            sources=sources,
            canonical_graph_assertions=canonical_assertions,
            confidence_floor=confidence_floor,
        )

        is_grounded = receipt.final_disposition == RetrievalDisposition.VERIFIED

        return CertifiedResearchResult(
            query=query,
            certified_findings=receipt.certified_claims,
            unverified_findings_rejected=receipt.rejected_claims,
            receipt=receipt,
            is_fully_grounded=is_grounded,
        )
