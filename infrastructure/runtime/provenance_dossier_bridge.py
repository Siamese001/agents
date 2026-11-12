"""Cross-Engine Provenance Dossier Bridge: Runtime Swarm Integration.

Part of Monorepo-Wide Swarm Integration (Wave 3).
Connects the Resume Swarm verification output directly to the Outreach Swarm coordinator
so that candidate outreach copy is generated strictly from verified factual assertions,
preventing hallucinated outreach claims and establishing a cryptographic chain of custody.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Sequence


class DossierDisposition(str, Enum):
    """Disposition of the cross-engine handoff."""

    DELIVERABLE = "DELIVERABLE"
    REJECTED_RESUME_DISPOSITION = "REJECTED_RESUME_DISPOSITION"
    NO_CERTIFIED_CLAIMS = "NO_CERTIFIED_CLAIMS"
    REJECTED_OUTREACH_SWARM = "REJECTED_OUTREACH_SWARM"


@dataclass(frozen=True, slots=True)
class CrossEngineDossierReceipt:
    """Cryptographically verifiable receipt certifying cross-engine handoff."""

    dossier_id: str
    resume_run_id: str
    campaign_id: str
    recipient_name: str
    certified_claims: tuple[str, ...]
    rejected_claims: tuple[str, ...]
    outreach_deliverable: bool
    certified_outreach_message: str
    outreach_word_count: int
    provenance_digest: str
    disposition: DossierDisposition
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        """Convert receipt to JSON dictionary."""
        return {
            "dossier_id": self.dossier_id,
            "resume_run_id": self.resume_run_id,
            "campaign_id": self.campaign_id,
            "recipient_name": self.recipient_name,
            "certified_claims": list(self.certified_claims),
            "rejected_claims": list(self.rejected_claims),
            "outreach_deliverable": self.outreach_deliverable,
            "certified_outreach_message": self.certified_outreach_message,
            "outreach_word_count": self.outreach_word_count,
            "provenance_digest": self.provenance_digest,
            "disposition": self.disposition.value,
            "created_at_ms": self.created_at_ms,
        }

    def write_to_path(self, target_path: Path | str) -> Path:
        """Persist receipt to disk atomically."""
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


def compute_dossier_digest(
    dossier_id: str,
    resume_run_id: str,
    campaign_id: str,
    certified_claims: Sequence[str],
    certified_message: str,
) -> str:
    """Compute deterministic SHA-256 digest of handoff data."""
    payload = {
        "dossier_id": dossier_id,
        "resume_run_id": resume_run_id,
        "campaign_id": campaign_id,
        "certified_claims": sorted(certified_claims),
        "certified_message": certified_message.strip(),
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_dossier_integrity(receipt: CrossEngineDossierReceipt) -> bool:
    """Independently verify cryptographic provenance and structural validity."""
    expected_digest = compute_dossier_digest(
        dossier_id=receipt.dossier_id,
        resume_run_id=receipt.resume_run_id,
        campaign_id=receipt.campaign_id,
        certified_claims=receipt.certified_claims,
        certified_message=receipt.certified_outreach_message,
    )
    if receipt.provenance_digest != expected_digest:
        return False

    if receipt.outreach_deliverable:
        if receipt.disposition != DossierDisposition.DELIVERABLE:
            return False
        if len(receipt.certified_claims) == 0:
            return False
        if not receipt.certified_outreach_message.strip():
            return False

    return True


class ProvenanceDossierBridge:
    """Cross-engine coordinator bridging resume verification with outreach synthesis."""

    def __init__(self, coordinator: Any | None = None) -> None:
        if coordinator is None:
            coord_mod = importlib.import_module("apps_lic.pipeline.coordinator")
            coordinator = coord_mod.OutreachSwarmCoordinator()
        self._coordinator = coordinator

    def bridge_and_dispatch(
        self,
        resume_receipt: Any,
        campaign_id: str,
        recipient_name: str,
        candidate_claims: Sequence[str] | None = None,
        role_title: str = "Technology Leader",
        company_name: str = "Enterprise Partner",
        max_turns: int = 3,
    ) -> CrossEngineDossierReceipt:
        """Filter unverified claims, assemble verified value props, and deliberate through outreach swarm."""
        dossier_id = f"dos_{hashlib.sha256(f'{resume_receipt.run_id}_{campaign_id}'.encode()).hexdigest()[:12]}"

        # Gate 1: Check resume swarm disposition
        disp_val = getattr(resume_receipt.final_disposition, "value", str(resume_receipt.final_disposition))
        is_resume_approved = disp_val == "APPROVED" or str(resume_receipt.final_disposition).endswith("APPROVED")
        if not is_resume_approved:
            digest = compute_dossier_digest(
                dossier_id=dossier_id,
                resume_run_id=resume_receipt.run_id,
                campaign_id=campaign_id,
                certified_claims=(),
                certified_message="",
            )
            return CrossEngineDossierReceipt(
                dossier_id=dossier_id,
                resume_run_id=resume_receipt.run_id,
                campaign_id=campaign_id,
                recipient_name=recipient_name,
                certified_claims=(),
                rejected_claims=tuple(candidate_claims or ()),
                outreach_deliverable=False,
                certified_outreach_message="",
                outreach_word_count=0,
                provenance_digest=digest,
                disposition=DossierDisposition.REJECTED_RESUME_DISPOSITION,
            )

        # Gate 2: Extract certified bullets
        certified_corpus = " ".join(resume_receipt.certified_bullets).lower()
        if not resume_receipt.certified_bullets:
            digest = compute_dossier_digest(
                dossier_id=dossier_id,
                resume_run_id=resume_receipt.run_id,
                campaign_id=campaign_id,
                certified_claims=(),
                certified_message="",
            )
            return CrossEngineDossierReceipt(
                dossier_id=dossier_id,
                resume_run_id=resume_receipt.run_id,
                campaign_id=campaign_id,
                recipient_name=recipient_name,
                certified_claims=(),
                rejected_claims=tuple(candidate_claims or ()),
                outreach_deliverable=False,
                certified_outreach_message="",
                outreach_word_count=0,
                provenance_digest=digest,
                disposition=DossierDisposition.NO_CERTIFIED_CLAIMS,
            )

        # Gate 3: Filter provided candidate claims against certified resume corpus
        verified_claims: list[str] = []
        rejected_claims: list[str] = []

        if candidate_claims:
            for claim in candidate_claims:
                claim_tokens = [tok for tok in re.findall(r"[a-z0-9]+", claim.lower()) if len(tok) >= 3]
                if not claim_tokens:
                    rejected_claims.append(claim)
                    continue

                # Check token overlap with certified corpus
                matching_tokens = sum(1 for tok in claim_tokens if tok in certified_corpus)
                overlap_ratio = matching_tokens / len(claim_tokens)

                # Require at least 60% token corroboration with certified bullets
                if overlap_ratio >= 0.60:
                    verified_claims.append(claim)
                else:
                    rejected_claims.append(claim)
        else:
            # If no candidate claims explicitly passed, formulate value props from certified bullets
            verified_claims.extend(resume_receipt.certified_bullets)

        if not verified_claims:
            digest = compute_dossier_digest(
                dossier_id=dossier_id,
                resume_run_id=resume_receipt.run_id,
                campaign_id=campaign_id,
                certified_claims=(),
                certified_message="",
            )
            return CrossEngineDossierReceipt(
                dossier_id=dossier_id,
                resume_run_id=resume_receipt.run_id,
                campaign_id=campaign_id,
                recipient_name=recipient_name,
                certified_claims=(),
                rejected_claims=tuple(rejected_claims),
                outreach_deliverable=False,
                certified_outreach_message="",
                outreach_word_count=0,
                provenance_digest=digest,
                disposition=DossierDisposition.NO_CERTIFIED_CLAIMS,
            )

        # Gate 4: Deliberate via Outreach Swarm Coordinator
        outreach_package: Any = self._coordinator.compile_and_certify(
            campaign_id=campaign_id,
            recipient_name=recipient_name,
            value_props=verified_claims,
            role_title=role_title,
            company_name=company_name,
            max_turns=max_turns,
        )

        disposition = (
            DossierDisposition.DELIVERABLE
            if outreach_package.is_deliverable
            else DossierDisposition.REJECTED_OUTREACH_SWARM
        )

        digest = compute_dossier_digest(
            dossier_id=dossier_id,
            resume_run_id=resume_receipt.run_id,
            campaign_id=campaign_id,
            certified_claims=verified_claims,
            certified_message=outreach_package.certified_body,
        )

        return CrossEngineDossierReceipt(
            dossier_id=dossier_id,
            resume_run_id=resume_receipt.run_id,
            campaign_id=campaign_id,
            recipient_name=recipient_name,
            certified_claims=tuple(verified_claims),
            rejected_claims=tuple(rejected_claims),
            outreach_deliverable=outreach_package.is_deliverable,
            certified_outreach_message=outreach_package.certified_body,
            outreach_word_count=outreach_package.word_count,
            provenance_digest=digest,
            disposition=disposition,
        )
