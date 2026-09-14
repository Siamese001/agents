"""Artifact Manifest Builder for Mandatory Outputs.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Uses Wave 4 ArtifactManifest contracts for cryptographic tamper evidence.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from agents.observability.artifacts import ArtifactManifest, create_artifact_manifest


class ArtifactManifestBuilder:
    """Builds authoritative ArtifactManifest records for emitted artifacts."""

    @staticmethod
    def build_manifest(
        run_id: str,
        artifact_id: str,
        artifact_type: str,
        producer: str,
        content: bytes,
        input_artifact_ids: Sequence[str] = (),
        provenance: Mapping[str, Any] | None = None,
        media_type: str | None = None,
    ) -> ArtifactManifest:
        """Construct sealed ArtifactManifest with SHA-256 digest."""
        return create_artifact_manifest(
            run_id=run_id,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            producer=producer,
            raw_bytes=content,
            input_artifact_ids=input_artifact_ids,
            provenance=provenance,
            media_type=media_type,
        )
