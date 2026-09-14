"""Artifact Output Emitter.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Emits formatted artifacts and manifests to filesystem and/or ArtifactStore ports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agents.persistence.ports import ArtifactStore
from apps_rg.runtime.artifact_output.builders import ArtifactPayloadBuilder
from apps_rg.runtime.artifact_output.manifest_builder import ArtifactManifestBuilder
from apps_rg.runtime.artifact_output.models import ArtifactOutputResult
from apps_rg.runtime.artifact_output.policy import MandatoryOutputPolicy
from apps_rg.runtime.artifact_output.serializers import DeterministicSerializer


class ArtifactOutputEmitter:
    """Emits mandatory run artifacts with cryptographic manifests and deterministic serializations."""

    def __init__(
        self,
        artifact_dir: Path | str,
        policy: MandatoryOutputPolicy | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.policy = policy or MandatoryOutputPolicy()
        self.artifact_store = artifact_store

    def emit_all_mandatory_outputs(
        self,
        run_id: str,
        workflow_status: str,
        context: Mapping[str, Any] | None = None,
        section_statuses: Mapping[str, str] | None = None,
    ) -> list[ArtifactOutputResult]:
        """Emit full suite of mandatory outputs for a workflow run."""
        results: list[ArtifactOutputResult] = []

        # 1. 01_BCG_executive_output.md
        bcg_text = ArtifactPayloadBuilder.build_bcg_executive_output(run_id, workflow_status, context)
        bcg_bytes = DeterministicSerializer.serialize_markdown(bcg_text)
        bcg_res = self._emit_single(
            run_id=run_id,
            artifact_key="bcg_executive_output",
            filename="01_BCG_executive_output.md",
            content=bcg_bytes,
            media_type="text/markdown",
        )
        results.append(bcg_res)

        # 2. 02_output_bisect.md
        bisect_text = ArtifactPayloadBuilder.build_output_bisect(run_id)
        bisect_bytes = DeterministicSerializer.serialize_markdown(bisect_text)
        bisect_res = self._emit_single(
            run_id=run_id,
            artifact_key="output_bisect",
            filename="02_output_bisect.md",
            content=bisect_bytes,
            media_type="text/markdown",
        )
        results.append(bisect_res)

        # 3. 02_section_lane_summary_table.md
        section_text = ArtifactPayloadBuilder.build_section_summary_table(section_statuses)
        section_bytes = DeterministicSerializer.serialize_markdown(section_text)
        section_res = self._emit_single(
            run_id=run_id,
            artifact_key="section_lane_summary_table",
            filename="02_section_lane_summary_table.md",
            content=section_bytes,
            media_type="text/markdown",
        )
        results.append(section_res)

        # 4. apps_rg_mandatory_run_outputs.json
        index_data = {
            "run_id": run_id,
            "workflow_status": workflow_status,
            "artifacts": {r.artifact_key: r.filename for r in results},
            "manifest_ids": {r.artifact_key: r.manifest_id for r in results},
        }
        index_bytes = DeterministicSerializer.serialize_json(index_data)
        index_res = self._emit_single(
            run_id=run_id,
            artifact_key="mandatory_run_output_json",
            filename="apps_rg_mandatory_run_outputs.json",
            content=index_bytes,
            media_type="application/json",
        )
        results.append(index_res)

        return results

    def _emit_single(
        self,
        run_id: str,
        artifact_key: str,
        filename: str,
        content: bytes,
        media_type: str,
    ) -> ArtifactOutputResult:
        """Write single artifact file, manifest, and delegate to store if configured."""
        file_path = self.artifact_dir / filename
        file_path.write_bytes(content)

        manifest = ArtifactManifestBuilder.build_manifest(
            run_id=run_id,
            artifact_id=artifact_key,
            artifact_type=media_type,
            producer="apps_rg_artifact_emitter",
            content=content,
            media_type=media_type,
        )

        manifest_path = self.artifact_dir / f"{filename}.manifest.json"
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")

        if self.artifact_store is not None:
            self.artifact_store.put_artifact(artifact_key, content, manifest)

        return ArtifactOutputResult(
            artifact_key=artifact_key,
            filename=filename,
            rel_path=str(file_path.relative_to(self.artifact_dir)),
            digest=manifest.content.value,
            size_bytes=len(content),
            manifest_id=manifest.manifest_id,
            is_valid=manifest.verify_integrity(),
        )
