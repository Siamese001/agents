"""Artifact Assembler Service.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Assembles verified section outputs into complete resume documents and manifests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from agents.observability.artifacts import ArtifactManifest, create_artifact_manifest
from apps_rg.runtime.artifact_output.serializers import DeterministicSerializer


@dataclass(frozen=True, slots=True)
class AssembledDocument:
    """Assembled resume document with cryptographic manifest."""

    document_id: str
    markdown_content: str
    raw_bytes: bytes
    manifest: ArtifactManifest


class ArtifactAssembler:
    """Assembles individual verified section outputs into complete documents."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def assemble_resume(
        self,
        sections: Mapping[str, str],
        order: tuple[str, ...] = ("headline", "executive_summary", "competencies"),
    ) -> AssembledDocument:
        """Assemble sections in canonical order into a complete markdown resume."""
        parts: list[str] = []
        for sec_id in order:
            if sec_id in sections:
                parts.append(sections[sec_id].strip())

        full_md = "\n\n---\n\n".join(parts) + "\n"
        raw_bytes = DeterministicSerializer.serialize_markdown(full_md)

        doc_id = f"resume_{self.run_id[:8]}"
        manifest = create_artifact_manifest(
            run_id=self.run_id,
            artifact_id=doc_id,
            artifact_type="markdown_resume",
            producer="apps_rg_artifact_assembler",
            raw_bytes=raw_bytes,
            media_type="text/markdown",
        )

        return AssembledDocument(
            document_id=doc_id,
            markdown_content=full_md,
            raw_bytes=raw_bytes,
            manifest=manifest,
        )
