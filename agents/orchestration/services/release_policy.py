"""Release Policy Service.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Decides whether workflow outputs meet strict release standards without
performing generation, repair, or direct persistence side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from agents.orchestration.services.artifact_assembly import AssemblyResult
from agents.orchestration.services.evaluation import EvaluationResult
from agents.orchestration.state_contracts import ResumeRunState, RunPhase


@dataclass(frozen=True, slots=True)
class ReleaseDecision:
    """Deterministic release evaluation outcome."""

    run_id: str
    is_releasable: bool
    reasons: tuple[str, ...] = ()
    blocking_failures: tuple[str, ...] = ()
    verified_manifest_count: int = 0

    @property
    def approved(self) -> bool:
        return self.is_releasable


class ReleasePolicy:
    """Domain policy deciding release eligibility."""

    def evaluate_release(
        self,
        state: ResumeRunState,
        evaluation_results: Sequence[EvaluationResult] = (),
        assembly_result: AssemblyResult | None = None,
    ) -> ReleaseDecision:
        """Evaluate run state, evaluation outcomes, and assembled artifacts for release."""
        blocking: list[str] = []
        reasons: list[str] = []

        # 1. State Phase Check
        if state.phase not in (RunPhase.RUNNING, RunPhase.COMPLETED):
            blocking.append(f"Illegal run phase for release: {state.phase.value}")

        # 2. Evaluation Results Check
        for ev in evaluation_results:
            if not ev.is_valid:
                kind_str = ev.failure_kind.value if ev.failure_kind else "UNKNOWN"
                blocking.append(
                    f"Section '{ev.section_name}' failed validation ({kind_str}): {', '.join(ev.errors)}"
                )

        # 3. Assembly Check
        verified_manifests = 0
        if assembly_result is not None:
            if not assembly_result.is_complete:
                blocking.append(
                    f"Incomplete artifact assembly: {', '.join(assembly_result.errors)}"
                )
            for art in assembly_result.artifacts:
                if not art.manifest.verify_integrity():
                    blocking.append(
                        f"Artifact '{art.artifact_id}' manifest failed cryptographic integrity."
                    )
                else:
                    verified_manifests += 1
        else:
            blocking.append("No assembly result provided for release evaluation.")

        # 4. Final Decision
        is_releasable = len(blocking) == 0
        if is_releasable:
            reasons.append("All release criteria, validations, and manifest verifications passed.")
        else:
            reasons.append(f"Release blocked by {len(blocking)} requirement violations.")

        return ReleaseDecision(
            run_id=state.run_id,
            is_releasable=is_releasable,
            reasons=tuple(reasons),
            blocking_failures=tuple(blocking),
            verified_manifest_count=verified_manifests,
        )
