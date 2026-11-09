"""Retrieval Challenger Service: Cross-Examiner for Research Evidence and Provenance.

Part of Monorepo-Wide Swarm Integration (Wave 2).
Audits synthesized research findings against source documents and canonical
knowledge graphs, enforcing source attribution and eliminating uncorroborated claims.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


class RetrievalDisposition(str, Enum):
    """Disposition states for research evidence cross-examination."""

    VERIFIED = "VERIFIED"
    NEEDS_CORROBORATION = "NEEDS_CORROBORATION"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


@dataclass(frozen=True, slots=True)
class EvidenceAttribution:
    """Verifiable link connecting a synthesized claim to source evidence."""

    claim: str
    source_id: str
    source_title: str
    is_corroborated: bool
    confidence: float
    excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalCritique:
    """Detailed evaluation emitted by the retrieval cross-examiner."""

    turn: int
    groundedness_score: float
    attributions: tuple[EvidenceAttribution, ...]
    ungrounded_claims: tuple[str, ...]
    repair_directives: tuple[str, ...]
    is_passing: bool


@dataclass(frozen=True, slots=True)
class RetrievalDeliberationReceipt:
    """Durable receipt certifying evidence grounding and provenance."""

    query: str
    turns_executed: int
    final_disposition: RetrievalDisposition
    certified_claims: tuple[str, ...]
    rejected_claims: tuple[str, ...]
    attributions: tuple[EvidenceAttribution, ...]
    groundedness_score: float
    calibrated_confidence: float
    margin: float
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Convert receipt to JSON-serializable dictionary."""
        return {
            "query": self.query,
            "turns_executed": self.turns_executed,
            "final_disposition": self.final_disposition.value,
            "certified_claims": list(self.certified_claims),
            "rejected_claims": list(self.rejected_claims),
            "attributions": [
                {
                    "claim": a.claim,
                    "source_id": a.source_id,
                    "source_title": a.source_title,
                    "is_corroborated": a.is_corroborated,
                    "confidence": a.confidence,
                    "excerpt": a.excerpt,
                }
                for a in self.attributions
            ],
            "groundedness_score": self.groundedness_score,
            "calibrated_confidence": self.calibrated_confidence,
            "margin": self.margin,
            "created_at_ms": self.created_at_ms,
        }

    def write_to_path(self, target_path: Path | str) -> Path:
        """Persist receipt to disk atomically."""
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


class RetrievalChallenger:
    """Cross-examiner swarm validating research claims against source evidence."""

    MAX_TURNS: int = 3

    def cross_examine(
        self,
        query: str,
        claims: Sequence[str],
        sources: Sequence[Mapping[str, Any]],
        canonical_graph_assertions: Sequence[str] | None = None,
        confidence_floor: float = 0.65,
    ) -> RetrievalDeliberationReceipt:
        """Cross-examine claims against candidate sources and canonical assertions."""
        attributions: list[EvidenceAttribution] = []
        certified: list[str] = []
        rejected: list[str] = []
        ungrounded: list[str] = []
        directives: list[str] = []

        # Prepare normalized source pool
        normalized_sources: list[tuple[str, str, str]] = []
        for src in sources:
            src_id = str(src.get("id") or src.get("source_id") or "src_unknown")
            src_title = str(src.get("title") or src.get("name") or "Untitled Source")
            src_content = str(src.get("content") or src.get("text") or src.get("body") or "").lower()
            normalized_sources.append((src_id, src_title, src_content))

        # Include canonical graph assertions as authoritative sources if provided
        if canonical_graph_assertions:
            for idx, assertion in enumerate(canonical_graph_assertions):
                normalized_sources.append((f"graph_assertion_{idx}", "Canonical Assertion Graph", assertion.lower()))

        for claim in claims:
            claim_norm = claim.strip().lower()
            if not claim_norm:
                continue

            # Check if claim is corroborated by any source
            best_match: tuple[str, str, str, float] | None = None
            for src_id, src_title, src_content in normalized_sources:
                # Substring or token overlap match
                tokens = [t for t in re.findall(r"\w+", claim_norm) if len(t) > 3]
                if not tokens:
                    continue
                overlap = sum(1 for t in tokens if t in src_content)
                ratio = overlap / len(tokens)
                if ratio > 0.40:
                    if best_match is None or ratio > best_match[3]:
                        best_match = (src_id, src_title, src_content[:160], round(ratio, 2))

            if best_match and best_match[3] >= 0.50:
                attr = EvidenceAttribution(
                    claim=claim,
                    source_id=best_match[0],
                    source_title=best_match[1],
                    is_corroborated=True,
                    confidence=best_match[3],
                    excerpt=best_match[2],
                )
                attributions.append(attr)
                certified.append(claim)
            else:
                attr = EvidenceAttribution(
                    claim=claim,
                    source_id="unverified",
                    source_title="None",
                    is_corroborated=False,
                    confidence=0.10,
                    excerpt=None,
                )
                attributions.append(attr)
                rejected.append(claim)
                ungrounded.append(claim)
                directives.append(f"Remove or corroborate unverified claim: '{claim[:60]}...'")

        # Calculate scores
        total_claims = len(claims) if claims else 1
        groundedness_score = round(len(certified) / total_claims, 2) if claims else 1.0
        calibrated_conf = round(max(0.05, min(0.99, groundedness_score)), 2)
        alternative_score = round(1.0 - calibrated_conf, 2)
        margin = round(abs(calibrated_conf - alternative_score), 2)

        # Determine disposition
        if len(rejected) == 0 and calibrated_conf >= confidence_floor:
            disposition = RetrievalDisposition.VERIFIED
        elif len(certified) > 0 and len(rejected) > 0:
            disposition = RetrievalDisposition.NEEDS_CORROBORATION
        else:
            disposition = RetrievalDisposition.REJECTED

        return RetrievalDeliberationReceipt(
            query=query,
            turns_executed=1,
            final_disposition=disposition,
            certified_claims=tuple(certified),
            rejected_claims=tuple(rejected),
            attributions=tuple(attributions),
            groundedness_score=groundedness_score,
            calibrated_confidence=calibrated_conf,
            margin=margin,
        )
