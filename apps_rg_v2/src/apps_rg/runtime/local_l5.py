"""Apps RG-owned L5 evidence packet contracts.

The packet is intentionally metadata-only: it seals governance receipts and
digest references, never provider prompts or generated content.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Sequence


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ChildCertifierReceipt:
    domain: str
    applicability: str
    certified: bool
    evidence_digest: str
    evidence_ref: str
    reason_codes: tuple[str, ...] = ()
    not_applicable_reason: str = ""
    deciding_policy_ref: str = ""
    deciding_stage: str = ""
    l5_governance_context_digest: str = ""


@dataclass(frozen=True, slots=True)
class EgressCertificationReceipt:
    provider_ref: str
    call_purpose_ref: str
    request_digest: str
    response_digest: str
    redaction_policy_ref: str
    l5_governance_context_digest: str = ""
    redaction_receipt_ref: str = ""
    egress_status: str = "EGRESS_CERTIFIED"
    egress_policy_ref: str = ""
    schema_version: str = "apps_rg_l5_egress_receipt.v2"

    @property
    def certified(self) -> bool:
        return self.egress_status == "EGRESS_CERTIFIED"


@dataclass(frozen=True, slots=True)
class L5CertificationPacket:
    certified_object_ref: str
    policy_ref: str
    blueprint_ref: str
    registry_ref: str
    authority_ref: str
    replay_ref: str
    audit_ref: str
    static_ref: str
    runtime_ref: str
    producer_ref: str
    certifier_version: str
    run_id: str
    trace_id: str
    child_receipts: tuple[ChildCertifierReceipt, ...]
    egress_receipts: tuple[EgressCertificationReceipt, ...]
    l5_governance_context_digest: str
    certification_status: str
    reason_codes: tuple[str, ...]
    digest_sha256: str
    evidence_refs: tuple[str, ...]
    prior_packet_digest: str = ""


class L5PacketProducer:
    """Build deterministic L5 packets from app-owned receipt contracts."""

    def produce_packet(
        self,
        *,
        child_receipts: Sequence[ChildCertifierReceipt],
        egress_receipts: Sequence[EgressCertificationReceipt],
        certified_object_ref: str,
        policy_ref: str,
        blueprint_ref: str = "",
        registry_ref: str = "",
        authority_ref: str = "",
        replay_ref: str = "",
        audit_ref: str = "",
        static_ref: str = "",
        runtime_ref: str = "",
        producer_ref: str,
        certifier_version: str = "apps_rg_l5_runtime_certification.v2",
        run_id: str = "",
        trace_id: str = "",
    ) -> L5CertificationPacket:
        children = tuple(child_receipts)
        egress = tuple(egress_receipts)
        context_digest = _canonical_digest(
            {
                "certified_object_ref": certified_object_ref,
                "policy_ref": policy_ref,
                "blueprint_ref": blueprint_ref,
                "registry_ref": registry_ref,
                "authority_ref": authority_ref,
                "replay_ref": replay_ref,
                "audit_ref": audit_ref,
                "static_ref": static_ref,
                "runtime_ref": runtime_ref,
                "producer_ref": producer_ref,
                "certifier_version": certifier_version,
                "run_id": run_id,
                "trace_id": trace_id,
            }
        )
        reason_codes: list[str] = []
        for receipt in children:
            if receipt.applicability == "REQUIRED" and not receipt.certified:
                reason_codes.extend(receipt.reason_codes or (f"uncertified:{receipt.domain}",))
        for receipt in egress:
            if not receipt.certified:
                reason_codes.append(f"uncertified_egress:{receipt.provider_ref}")
        reasons = tuple(dict.fromkeys(reason_codes))
        status = "L5_CERTIFIED" if not reasons else "L5_NOT_CERTIFIED"
        digest_sha256 = _canonical_digest(
            {
                "governance_context_digest": context_digest,
                "certification_status": status,
                "reason_codes": sorted(reasons),
                "prior_packet_digest": "",
                "producer_ref": producer_ref,
                "policy_ref": policy_ref,
                "certifier_version": certifier_version,
            }
        )
        return L5CertificationPacket(
            certified_object_ref=certified_object_ref,
            policy_ref=policy_ref,
            blueprint_ref=blueprint_ref,
            registry_ref=registry_ref,
            authority_ref=authority_ref,
            replay_ref=replay_ref,
            audit_ref=audit_ref,
            static_ref=static_ref,
            runtime_ref=runtime_ref,
            producer_ref=producer_ref,
            certifier_version=certifier_version,
            run_id=run_id,
            trace_id=trace_id,
            child_receipts=children,
            egress_receipts=egress,
            l5_governance_context_digest=context_digest,
            certification_status=status,
            reason_codes=reasons,
            digest_sha256=digest_sha256,
            evidence_refs=(context_digest,),
        )


__all__ = [
    "ChildCertifierReceipt",
    "EgressCertificationReceipt",
    "L5CertificationPacket",
    "L5PacketProducer",
]
