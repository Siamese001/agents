"""Modular Pipeline Package for Sovereign Agentic Platform.

Decomposes monolithic bare_pipeline into cleanly decoupled services.
"""

from apps_rg.runtime.pipeline.artifact_assembly import (
    ArtifactAssembler,
    AssembledDocument,
)
from apps_rg.runtime.pipeline.evaluation import (
    EvaluationReport,
    EvaluationService,
)
from apps_rg.runtime.pipeline.orchestration import (
    ModularPipelineOrchestrator,
    PipelineRunOutcome,
)
from apps_rg.runtime.pipeline.release_policy import (
    ReleaseGateDecision,
    ReleasePolicy,
)
from apps_rg.runtime.pipeline.section_generation import (
    SectionGenerationService,
    SectionOutput,
)

__all__ = [
    "ArtifactAssembler",
    "AssembledDocument",
    "EvaluationReport",
    "EvaluationService",
    "ModularPipelineOrchestrator",
    "PipelineRunOutcome",
    "ReleaseGateDecision",
    "ReleasePolicy",
    "SectionGenerationService",
    "SectionOutput",
]
