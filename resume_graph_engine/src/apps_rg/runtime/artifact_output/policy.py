"""Mandatory Output Inclusion and Compliance Policy.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
"""

from __future__ import annotations

from typing import Sequence
from apps_rg.runtime.artifact_output.models import MandatoryArtifactSpec

STANDARD_MANDATORY_SPECS: tuple[MandatoryArtifactSpec, ...] = (
    MandatoryArtifactSpec(
        artifact_key="bcg_executive_output",
        filename="01_BCG_executive_output.md",
        description="Decision-oriented RCA and implementation plan",
        order=1,
    ),
    MandatoryArtifactSpec(
        artifact_key="output_bisect",
        filename="02_output_bisect.md",
        description="Prior-pass/current-failure attempt and causal bisect",
        order=2,
    ),
    MandatoryArtifactSpec(
        artifact_key="section_lane_summary_table",
        filename="02_section_lane_summary_table.md",
        description="Operational ledger of executed section lanes",
        order=3,
    ),
    MandatoryArtifactSpec(
        artifact_key="mandatory_run_output_json",
        filename="apps_rg_mandatory_run_outputs.json",
        description="Machine-readable run artifact index",
        media_type="application/json",
        order=4,
    ),
)


class MandatoryOutputPolicy:
    """Policy governing mandatory artifact requirements for runs."""

    def __init__(self, specs: Sequence[MandatoryArtifactSpec] | None = None) -> None:
        self._specs = tuple(specs or STANDARD_MANDATORY_SPECS)

    @property
    def specs(self) -> tuple[MandatoryArtifactSpec, ...]:
        return self._specs

    def get_required_filenames(self) -> set[str]:
        """Return set of filenames strictly required by this policy."""
        return {s.filename for s in self._specs if s.required}
