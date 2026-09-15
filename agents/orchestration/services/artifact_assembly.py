"""Artifact Assembler Service.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Transforms validated domain outputs into deterministic byte payloads and
self-verifying ArtifactManifest instances without direct disk/store side effects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from agents.observability.artifacts import ArtifactManifest, create_artifact_manifest
from agents.observability.envelopes import canonical_json_dumps


@dataclass(frozen=True, slots=True)
class AssemblyRequest:
    """Request to assemble structured section outputs into final deliverables."""

    run_id: str
    sections: Mapping[str, Mapping[str, Any]]
    target_formats: tuple[str, ...] = ("markdown", "json")
    required_sections: tuple[str, ...] = ()
    producer: str = "ArtifactAssembler"


@dataclass(frozen=True, slots=True)
class AssembledArtifact:
    """Immutable assembled artifact payload paired with its cryptographic manifest."""

    artifact_id: str
    artifact_type: str
    raw_bytes: bytes
    media_type: str
    manifest: ArtifactManifest


@dataclass(frozen=True, slots=True)
class AssemblyResult:
    """Outcome of artifact assembly."""

    run_id: str
    artifacts: tuple[AssembledArtifact, ...]
    is_complete: bool
    errors: tuple[str, ...] = ()

    def get_artifact(self, artifact_type: str) -> AssembledArtifact | None:
        for art in self.artifacts:
            if art.artifact_type == artifact_type:
                return art
        return None


class ArtifactAssembler:
    """Domain service responsible for deterministic artifact assembly."""

    def __init__(self, producer_name: str = "ArtifactAssembler") -> None:
        self._producer_name = producer_name

    def assemble(self, request: AssemblyRequest) -> AssemblyResult:
        """Assemble section outputs into deterministic payloads and manifests."""
        errors: list[str] = []

        # 1. Check completeness
        missing = [s for s in request.required_sections if s not in request.sections]
        if missing:
            errors.append(f"Missing mandatory sections for assembly: {', '.join(missing)}")

        if errors:
            return AssemblyResult(
                run_id=request.run_id,
                artifacts=(),
                is_complete=False,
                errors=tuple(errors),
            )

        artifacts: list[AssembledArtifact] = []

        # 2. Build JSON Structured Resume Artifact
        if "json" in request.target_formats:
            json_bytes = canonical_json_dumps(dict(request.sections)).encode("utf-8")
            art_id = f"{request.run_id}-sections-json"
            manifest = create_artifact_manifest(
                run_id=request.run_id,
                artifact_id=art_id,
                artifact_type="json_resume",
                producer=request.producer or self._producer_name,
                raw_bytes=json_bytes,
                media_type="application/json",
            )
            artifacts.append(
                AssembledArtifact(
                    artifact_id=art_id,
                    artifact_type="json_resume",
                    raw_bytes=json_bytes,
                    media_type="application/json",
                    manifest=manifest,
                )
            )

        # 3. Build Markdown Composite Artifact
        if "markdown" in request.target_formats:
            md_lines: list[str] = [f"# Resume Document — Run {request.run_id}\n"]
            for sec_name, sec_content in sorted(request.sections.items()):
                md_lines.append(f"## {sec_name.replace('_', ' ').title()}\n")
                if isinstance(sec_content, dict):
                    for k, v in sorted(sec_content.items()):
                        md_lines.append(f"- **{k}**: {v}")
                else:
                    md_lines.append(str(sec_content))
                md_lines.append("\n")

            md_bytes = "\n".join(md_lines).encode("utf-8")
            art_id = f"{request.run_id}-resume-md"
            manifest = create_artifact_manifest(
                run_id=request.run_id,
                artifact_id=art_id,
                artifact_type="markdown_resume",
                producer=request.producer or self._producer_name,
                raw_bytes=md_bytes,
                media_type="text/markdown",
            )
            artifacts.append(
                AssembledArtifact(
                    artifact_id=art_id,
                    artifact_type="markdown_resume",
                    raw_bytes=md_bytes,
                    media_type="text/markdown",
                    manifest=manifest,
                )
            )

        return AssemblyResult(
            run_id=request.run_id,
            artifacts=tuple(artifacts),
            is_complete=True,
            errors=(),
        )
