"""Authoritative Artifact Digest and Tamper-Evident Manifest Contracts.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Binds all input, intermediate, and output artifacts to cryptographic SHA-256
digests and causal predecessor linkage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from agents.observability.events import canonical_json_dumps, compute_digest


@dataclass(frozen=True, slots=True)
class ArtifactDigest:
    """Cryptographic digest of artifact contents."""

    algorithm: str
    value: str
    byte_length: int
    media_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "value": self.value,
            "byte_length": self.byte_length,
            "media_type": self.media_type,
        }


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    """Tamper-evident manifest describing an artifact and its provenance."""

    manifest_id: str
    run_id: str
    artifact_id: str
    artifact_type: str
    producer: str
    created_at: str
    content: ArtifactDigest
    input_artifact_ids: tuple[str, ...]
    provenance: Mapping[str, Any] = field(default_factory=dict)
    previous_manifest_digest: str | None = None
    manifest_digest: str = ""
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "run_id": self.run_id,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "producer": self.producer,
            "created_at": self.created_at,
            "content": self.content.to_dict(),
            "input_artifact_ids": list(self.input_artifact_ids),
            "provenance": dict(self.provenance),
            "previous_manifest_digest": self.previous_manifest_digest,
            "manifest_digest": self.manifest_digest,
            "schema_version": self.schema_version,
        }

    def compute_canonical_digest(self) -> str:
        """Compute SHA-256 digest over all manifest fields excluding manifest_digest."""
        preimage = {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "content": self.content.to_dict(),
            "created_at": self.created_at,
            "input_artifact_ids": sorted(self.input_artifact_ids),
            "manifest_id": self.manifest_id,
            "previous_manifest_digest": self.previous_manifest_digest,
            "producer": self.producer,
            "provenance": dict(self.provenance),
            "run_id": self.run_id,
            "schema_version": self.schema_version,
        }
        return compute_digest(canonical_json_dumps(preimage))

    def verify_integrity(self) -> bool:
        """Verify that manifest contents match recorded manifest_digest."""
        if not self.manifest_digest:
            return False
        return self.compute_canonical_digest() == self.manifest_digest

    @classmethod
    def create(
        cls,
        run_id: str,
        artifact_id: str,
        artifact_type: str,
        producer: str,
        content: bytes,
        input_artifact_ids: Sequence[str] = (),
        provenance: Mapping[str, Any] | None = None,
        previous_manifest_digest: str | None = None,
        media_type: str | None = None,
        manifest_id: str | None = None,
        schema_version: int = 1,
    ) -> ArtifactManifest:
        return create_artifact_manifest(
            run_id=run_id,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            producer=producer,
            raw_bytes=content,
            input_artifact_ids=input_artifact_ids,
            provenance=provenance,
            previous_manifest_digest=previous_manifest_digest,
            media_type=media_type,
            manifest_id=manifest_id,
            schema_version=schema_version,
        )


def create_artifact_manifest(
    run_id: str,
    artifact_id: str,
    artifact_type: str,
    producer: str,
    raw_bytes: bytes,
    input_artifact_ids: Sequence[str] = (),
    provenance: Mapping[str, Any] | None = None,
    previous_manifest_digest: str | None = None,
    media_type: str | None = None,
    manifest_id: str | None = None,
    schema_version: int = 1,
) -> ArtifactManifest:
    """Construct, hash, and seal a tamper-evident ArtifactManifest."""
    content_digest = hashlib.sha256(raw_bytes).hexdigest()
    content = ArtifactDigest(
        algorithm="sha256",
        value=content_digest,
        byte_length=len(raw_bytes),
        media_type=media_type,
    )
    mid = manifest_id or f"man_{run_id[:8]}_{artifact_id[:12]}"
    created_at = datetime.now(timezone.utc).isoformat()
    prov = dict(provenance or {})
    sorted_inputs = tuple(sorted(input_artifact_ids))

    draft = ArtifactManifest(
        manifest_id=mid,
        run_id=run_id,
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        producer=producer,
        created_at=created_at,
        content=content,
        input_artifact_ids=sorted_inputs,
        provenance=prov,
        previous_manifest_digest=previous_manifest_digest,
        manifest_digest="",
        schema_version=schema_version,
    )
    digest = draft.compute_canonical_digest()

    return ArtifactManifest(
        manifest_id=mid,
        run_id=run_id,
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        producer=producer,
        created_at=created_at,
        content=content,
        input_artifact_ids=sorted_inputs,
        provenance=prov,
        previous_manifest_digest=previous_manifest_digest,
        manifest_digest=digest,
        schema_version=schema_version,
    )
