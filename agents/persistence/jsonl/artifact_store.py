"""Filesystem Implementation of ArtifactStore Port.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Stores raw artifact bytes and JSON manifests, verifying SHA-256 digests on read and write.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agents.observability.artifacts import ArtifactDigest, ArtifactManifest
from agents.persistence.errors import RecordNotFoundError, TamperDetectionError
from agents.persistence.ports import ArtifactStore


class FilesystemArtifactStore(ArtifactStore):
    """Filesystem-backed store for artifacts and their cryptographic manifests."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = self.base_dir / "artifacts"
        self.manifests_dir = self.base_dir / "manifests"
        self.artifacts_dir.mkdir(exist_ok=True)
        self.manifests_dir.mkdir(exist_ok=True)

    def put_artifact(
        self,
        artifact_id: str,
        content: bytes,
        manifest: ArtifactManifest,
    ) -> ArtifactManifest:
        """Store artifact bytes and manifest, enforcing SHA-256 match."""
        # 1. Verify content matches manifest digest
        computed = hashlib.sha256(content).hexdigest()
        if computed != manifest.content.value:
            raise TamperDetectionError(
                f"Artifact {artifact_id} content digest mismatch: expected {manifest.content.value}, computed {computed}"
            )

        # 2. Write raw bytes
        art_path = self.artifacts_dir / f"{artifact_id}.bin"
        art_path.write_bytes(content)

        # 3. Write manifest
        man_path = self.manifests_dir / f"{artifact_id}.manifest.json"
        man_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

        return manifest

    def get_artifact(self, artifact_id: str) -> bytes:
        """Retrieve artifact raw bytes."""
        art_path = self.artifacts_dir / f"{artifact_id}.bin"
        if not art_path.exists():
            raise RecordNotFoundError(f"Artifact {artifact_id} not found at {art_path}")
        return art_path.read_bytes()

    def get_manifest(self, artifact_id: str) -> ArtifactManifest:
        """Retrieve artifact manifest."""
        man_path = self.manifests_dir / f"{artifact_id}.manifest.json"
        if not man_path.exists():
            raise RecordNotFoundError(f"Manifest for artifact {artifact_id} not found at {man_path}")
        data = json.loads(man_path.read_text(encoding="utf-8"))
        content_data = data["content"]
        return ArtifactManifest(
            manifest_id=data["manifest_id"],
            run_id=data["run_id"],
            artifact_id=data["artifact_id"],
            artifact_type=data["artifact_type"],
            producer=data["producer"],
            created_at=data["created_at"],
            content=ArtifactDigest(
                algorithm=content_data["algorithm"],
                value=content_data["value"],
                byte_length=content_data["byte_length"],
                media_type=content_data.get("media_type"),
            ),
            input_artifact_ids=tuple(data["input_artifact_ids"]),
            provenance=data["provenance"],
            previous_manifest_digest=data.get("previous_manifest_digest"),
            manifest_digest=data["manifest_digest"],
            schema_version=data.get("schema_version", 1),
        )

    def verify_artifact(self, artifact_id: str) -> bool:
        """Verify that stored bytes match recorded manifest digest and manifest integrity."""
        try:
            content = self.get_artifact(artifact_id)
            manifest = self.get_manifest(artifact_id)
            if not manifest.verify_integrity():
                return False
            computed = hashlib.sha256(content).hexdigest()
            return computed == manifest.content.value
        except Exception:
            return False
