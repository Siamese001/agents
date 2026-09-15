"""Modular Pipeline Orchestrator.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Coordinates decoupled services: SectionGenerationService, EvaluationService,
ArtifactAssembler, and ReleasePolicy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from apps_rg.runtime.pipeline.artifact_assembly import ArtifactAssembler, AssembledDocument
from apps_rg.runtime.pipeline.evaluation import EvaluationReport, EvaluationService
from apps_rg.runtime.pipeline.release_policy import ReleaseGateDecision, ReleasePolicy
from apps_rg.runtime.pipeline.section_generation import SectionGenerationService, SectionOutput


@dataclass(frozen=True, slots=True)
class PipelineRunOutcome:
    """Outcome of a complete modular pipeline run."""

    run_id: str
    is_success: bool
    sections: Mapping[str, SectionOutput]
    evaluations: Mapping[str, EvaluationReport]
    document: AssembledDocument | None
    release_decision: ReleaseGateDecision


class ModularPipelineOrchestrator:
    """Coordinates modular pipeline services."""

    def __init__(
        self,
        generation_service: SectionGenerationService | None = None,
        evaluation_service: EvaluationService | None = None,
        release_policy: ReleasePolicy | None = None,
    ) -> None:
        self.generation_service = generation_service or SectionGenerationService()
        self.evaluation_service = evaluation_service or EvaluationService()
        self.release_policy = release_policy or ReleasePolicy()

    def run_pipeline(
        self,
        run_id: str,
        section_ids: tuple[str, ...] = ("headline", "executive_summary", "competencies"),
        inputs: Mapping[str, Any] | None = None,
    ) -> PipelineRunOutcome:
        """Execute full generation, evaluation, assembly, and release sequence."""
        inp = dict(inputs or {})
        sections: dict[str, SectionOutput] = {}
        evaluations: dict[str, EvaluationReport] = {}

        # 1. Generation
        for sid in section_ids:
            s_out = self.generation_service.generate_section(sid, inp)
            sections[sid] = s_out

            # 2. Evaluation
            e_rep = self.evaluation_service.evaluate(sid, s_out.content)
            evaluations[sid] = e_rep

        # 3. Release gating
        release_dec = self.release_policy.evaluate_release(evaluations)

        # 4. Assembly
        doc: AssembledDocument | None = None
        if release_dec.approved:
            assembler = ArtifactAssembler(run_id)
            sec_contents = {sid: s.content for sid, s in sections.items() if s.is_success}
            doc = assembler.assemble_resume(sec_contents, order=section_ids)

        is_success = release_dec.approved and doc is not None

        return PipelineRunOutcome(
            run_id=run_id,
            is_success=is_success,
            sections=sections,
            evaluations=evaluations,
            document=doc,
            release_decision=release_dec,
        )
