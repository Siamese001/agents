"""Value Objects and Specifications for Mandatory Run Artifacts.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MandatoryArtifactSpec:
    """Specification of an expected mandatory output artifact."""

    artifact_key: str
    filename: str
    description: str
    required: bool = True
    media_type: str = "text/markdown"
    order: int = 100


@dataclass(frozen=True, slots=True)
class ArtifactOutputResult:
    """Result descriptor for a materialized and emitted artifact."""

    artifact_key: str
    filename: str
    rel_path: str
    digest: str
    size_bytes: int
    manifest_id: str
    is_valid: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)
