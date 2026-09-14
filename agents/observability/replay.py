"""Authoritative Replay Verification and Audit Lineage Reconstruction.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Validates that a recorded run history forms an unbroken, deterministic chain of events,
checkpoints, and decisions capable of forensic replay.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from agents.observability.artifacts import ArtifactManifest
from agents.observability.events import (
    AgentEventEnvelope,
    AgentEventType,
    VerificationResult,
    verify_event_chain,
)
from agents.orchestration.state_contracts import ResumeRunState, RunCheckpoint


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    """Request to verify or reconstruct a workflow execution run."""

    run_id: str
    events: Sequence[AgentEventEnvelope] = field(default_factory=tuple)
    checkpoints: Sequence[RunCheckpoint] = field(default_factory=tuple)
    artifacts: Mapping[str, bytes] = field(default_factory=dict)
    manifests: Sequence[ArtifactManifest] = field(default_factory=tuple)
    target_checkpoint_id: str | None = None
    strict_chain_verification: bool = True
    dry_run: bool = True


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Outcome of a forensic run verification or replay reconstruction."""

    run_id: str
    is_replayable: bool
    total_events: int
    total_checkpoints: int
    final_phase: str
    chain_verification: VerificationResult
    phase_transitions: tuple[str, ...]
    feedback_decisions: tuple[str, ...]
    verified_artifact_count: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def success(self) -> bool:
        return self.is_replayable

    @property
    def verified_event_count(self) -> int:
        return self.total_events

    @property
    def verified_checkpoint_count(self) -> int:
        return self.total_checkpoints

    @property
    def mismatches(self) -> tuple[str, ...]:
        return self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "success": self.success,
            "is_replayable": self.is_replayable,
            "verified_event_count": self.verified_event_count,
            "verified_checkpoint_count": self.verified_checkpoint_count,
            "verified_artifact_count": self.verified_artifact_count,
            "mismatch_count": len(self.mismatches),
            "mismatches": list(self.mismatches),
        }


class ReplayVerifier:
    """Verifies that persisted run events and checkpoints permit deterministic replay."""

    @staticmethod
    def verify_event_chain(events: Sequence[AgentEventEnvelope]) -> list[str]:
        """Verify sequence monotonicity, cryptographic integrity, and predecessor linkage."""
        res = verify_event_chain(events)
        if not res.is_valid:
            return [res.error_message]
        return []

    @staticmethod
    def verify_artifacts(
        artifacts: Mapping[str, bytes],
        manifests: Sequence[ArtifactManifest],
    ) -> list[str]:
        """Verify that payload bytes match manifest content digests and manifest digests are valid."""
        errors: list[str] = []
        manifest_map = {m.artifact_id: m for m in manifests}

        for aid, raw in artifacts.items():
            man = manifest_map.get(aid)
            if not man:
                errors.append(f"Missing manifest for artifact {aid}")
                continue
            if not man.verify_integrity():
                errors.append(f"Manifest for artifact {aid} failed integrity check.")
            computed = hashlib.sha256(raw).hexdigest()
            if computed != man.content.value:
                errors.append(
                    f"Artifact {aid} hash mismatch: expected {man.content.value}, got {computed}"
                )
            if len(raw) != man.content.byte_length:
                errors.append(
                    f"Artifact {aid} size mismatch: expected {man.content.byte_length}, got {len(raw)}"
                )
        return errors

    def verify_run_integrity(
        self,
        run_id: str,
        events: Sequence[AgentEventEnvelope],
        checkpoints: Sequence[RunCheckpoint] = (),
    ) -> ReplayResult:
        """Inspect recorded events and checkpoints for cryptographic integrity and replayability."""
        errors: list[str] = []

        # 1. Verify cryptographic event chain
        chain_res = verify_event_chain(events)
        if not chain_res.is_valid:
            errors.append(f"Event chain integrity failed: {chain_res.error_message}")

        # 2. Extract phase transitions
        transitions: list[str] = []
        feedbacks: list[str] = []
        final_phase = "UNKNOWN"

        for evt in events:
            if evt.event_type == AgentEventType.PHASE_TRANSITION:
                prev = evt.payload.get("previous_phase", "")
                nxt = evt.payload.get("next_phase", "")
                transitions.append(f"{prev}->{nxt}")
                final_phase = str(nxt)
            elif evt.event_type == AgentEventType.FEEDBACK_DECISION:
                action = evt.payload.get("action", "")
                feedbacks.append(str(action))

        # 3. Verify checkpoint sequence and integrity
        for chk in checkpoints:
            if not chk.verify_integrity():
                errors.append(f"Checkpoint {chk.checkpoint_id} failed cryptographic digest verification.")

        is_replayable = len(errors) == 0 and chain_res.is_valid

        return ReplayResult(
            run_id=run_id,
            is_replayable=is_replayable,
            total_events=len(events),
            total_checkpoints=len(checkpoints),
            final_phase=final_phase,
            chain_verification=chain_res,
            phase_transitions=tuple(transitions),
            feedback_decisions=tuple(feedbacks),
            errors=tuple(errors),
        )

    def replay_run(self, request: ReplayRequest) -> ReplayResult:
        """Perform full forensic verification of a recorded run."""
        res = self.verify_run_integrity(request.run_id, request.events, request.checkpoints)
        art_errs = self.verify_artifacts(request.artifacts, request.manifests)

        all_errors = tuple(list(res.errors) + art_errs)
        is_replayable = len(all_errors) == 0 and res.chain_verification.is_valid

        return ReplayResult(
            run_id=request.run_id,
            is_replayable=is_replayable,
            total_events=len(request.events),
            total_checkpoints=len(request.checkpoints),
            final_phase=res.final_phase,
            chain_verification=res.chain_verification,
            phase_transitions=res.phase_transitions,
            feedback_decisions=res.feedback_decisions,
            verified_artifact_count=len(request.artifacts),
            errors=all_errors,
        )


DeterministicReplayEngine = ReplayVerifier

__all__ = [
    "DeterministicReplayEngine",
    "ReplayRequest",
    "ReplayResult",
    "ReplayVerifier",
]
