"""Modular Pipeline Coordinator.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Coordinates execution across SectionGenerationService, EvaluationService,
ArtifactAssembler, and ReleasePolicy using canonical state contracts and event envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from agents.observability.events import (
    AgentEventEnvelope,
    AgentEventType,
    create_event_envelope,
)
from agents.orchestration.feedback_controller import FeedbackController
from agents.orchestration.services.artifact_assembly import (
    ArtifactAssembler,
    AssemblyRequest,
    AssemblyResult,
)
from agents.orchestration.services.evaluation import (
    EvaluationRequest,
    EvaluationResult,
    EvaluationService,
)
from agents.orchestration.services.release_policy import ReleaseDecision, ReleasePolicy
from agents.orchestration.services.section_generation import (
    SectionGenerationRequest,
    SectionGenerationResult,
    SectionGenerationService,
)
from agents.orchestration.state_contracts import (
    RecoveryBudget,
    ResumeRunState,
    RunPhase,
    validate_and_transition,
)


@dataclass(frozen=True, slots=True)
class PipelineExecutionRequest:
    """Request to execute a multi-section document or resume pipeline."""

    run_id: str
    workflow_id: str
    section_specs: Mapping[str, Mapping[str, Any]]
    budget: RecoveryBudget = field(default_factory=RecoveryBudget)
    producer: str = "PipelineCoordinator"


@dataclass(frozen=True, slots=True)
class PipelineExecutionResult:
    """End-to-end outcome of modular pipeline execution."""

    run_id: str
    state: ResumeRunState
    is_successful: bool
    sections: Mapping[str, SectionGenerationResult]
    evaluations: Mapping[str, EvaluationResult]
    assembly: AssemblyResult | None
    release_decision: ReleaseDecision | None
    events: tuple[AgentEventEnvelope, ...]
    errors: tuple[str, ...] = ()


class PipelineCoordinator:
    """Coordinates modular domain services without monolithic entanglement."""

    def __init__(
        self,
        generation_service: SectionGenerationService | None = None,
        evaluation_service: EvaluationService | None = None,
        assembler: ArtifactAssembler | None = None,
        release_policy: ReleasePolicy | None = None,
        feedback_controller: FeedbackController | None = None,
    ) -> None:
        self.generation_service = generation_service or SectionGenerationService()
        self.evaluation_service = evaluation_service or EvaluationService(feedback_controller)
        self.assembler = assembler or ArtifactAssembler()
        self.release_policy = release_policy or ReleasePolicy()

    def run(self, request: PipelineExecutionRequest) -> PipelineExecutionResult:
        """Run the end-to-end pipeline across decomposed domain service boundaries."""
        events: list[AgentEventEnvelope] = []
        seq = 1
        prev_digest: str | None = None

        # 1. State initialization
        state = ResumeRunState(
            run_id=request.run_id,
            workflow_id=request.workflow_id,
            phase=RunPhase.CREATED,
            budget=request.budget,
        )

        e_start = create_event_envelope(
            event_type=AgentEventType.PHASE_TRANSITION,
            run_id=request.run_id,
            correlation_id=f"corr-{request.run_id}",
            sequence=seq,
            producer=request.producer,
            payload={"previous_phase": "CREATED", "next_phase": "RUNNING"},
            previous_event_digest=prev_digest,
        )
        events.append(e_start)
        prev_digest = e_start.event_digest
        seq += 1

        state = validate_and_transition(state, RunPhase.RUNNING)

        # 2. Section Generation & Evaluation Loop
        section_results: dict[str, SectionGenerationResult] = {}
        eval_results: dict[str, EvaluationResult] = {}
        assembled_sections: dict[str, Mapping[str, Any]] = {}
        errors: list[str] = []

        for sec_name, sec_inputs in request.section_specs.items():
            # Generation
            gen_req = SectionGenerationRequest(
                run_id=request.run_id,
                section_name=sec_name,
                lane_id=f"lane_{sec_name}",
                inputs=sec_inputs,
                budget=state.budget,
                current_state=state,
            )
            gen_res = self.generation_service.generate(gen_req)
            section_results[sec_name] = gen_res

            if not gen_res.success:
                err_msg = gen_res.failure.message if gen_res.failure else "Unknown generation failure"
                errors.append(f"Generation failed for section '{sec_name}': {err_msg}")
                break

            # Evaluation
            eval_req = EvaluationRequest(
                run_id=request.run_id,
                section_name=sec_name,
                content=gen_res.content,
            )
            eval_res, decision = self.evaluation_service.evaluate_and_decide(eval_req)
            eval_results[sec_name] = eval_res

            e_eval = create_event_envelope(
                event_type=AgentEventType.FEEDBACK_DECISION,
                run_id=request.run_id,
                correlation_id=f"corr-{request.run_id}",
                sequence=seq,
                producer=request.producer,
                payload={
                    "section_name": sec_name,
                    "action": decision.action.value,
                    "is_valid": eval_res.is_valid,
                },
                previous_event_digest=prev_digest,
            )
            events.append(e_eval)
            prev_digest = e_eval.event_digest
            seq += 1

            if not eval_res.is_valid:
                errors.append(f"Evaluation failed for section '{sec_name}': {', '.join(eval_res.errors)}")
                break

            assembled_sections[sec_name] = gen_res.content

        # 3. Artifact Assembly
        assembly_res: AssemblyResult | None = None
        release_dec: ReleaseDecision | None = None

        if len(errors) == 0:
            asm_req = AssemblyRequest(
                run_id=request.run_id,
                sections=assembled_sections,
                target_formats=("json", "markdown"),
                producer=request.producer,
            )
            assembly_res = self.assembler.assemble(asm_req)

            if not assembly_res.is_complete:
                errors.extend(assembly_res.errors)
            else:
                for art in assembly_res.artifacts:
                    e_art = create_event_envelope(
                        event_type=AgentEventType.ARTIFACT_COMMITTED,
                        run_id=request.run_id,
                        correlation_id=f"corr-{request.run_id}",
                        sequence=seq,
                        producer=request.producer,
                        payload={
                            "artifact_id": art.artifact_id,
                            "artifact_type": art.artifact_type,
                            "manifest_digest": art.manifest.manifest_digest,
                        },
                        previous_event_digest=prev_digest,
                    )
                    events.append(e_art)
                    prev_digest = e_art.event_digest
                    seq += 1

        # 4. Release Evaluation
        final_phase = RunPhase.COMPLETED if len(errors) == 0 else RunPhase.FAILED
        state = validate_and_transition(state, final_phase)

        if assembly_res is not None:
            release_dec = self.release_policy.evaluate_release(
                state=state,
                evaluation_results=tuple(eval_results.values()),
                assembly_result=assembly_res,
            )

        e_finish = create_event_envelope(
            event_type=AgentEventType.PHASE_TRANSITION,
            run_id=request.run_id,
            correlation_id=f"corr-{request.run_id}",
            sequence=seq,
            producer=request.producer,
            payload={"previous_phase": "RUNNING", "next_phase": final_phase.value},
            previous_event_digest=prev_digest,
        )
        events.append(e_finish)

        return PipelineExecutionResult(
            run_id=request.run_id,
            state=state,
            is_successful=len(errors) == 0 and (release_dec.is_releasable if release_dec else False),
            sections=section_results,
            evaluations=eval_results,
            assembly=assembly_res,
            release_decision=release_dec,
            events=tuple(events),
            errors=tuple(errors),
        )
