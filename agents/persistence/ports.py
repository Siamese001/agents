"""Authoritative Persistence Ports and Storage-Independent Protocols.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Decouples domain orchestrators and state machines from concrete persistence
backends (SQLite, JSONL, Filesystem, Object Storage).
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from agents.observability.artifacts import ArtifactManifest
from agents.observability.events import AgentEventEnvelope, VerificationResult
from agents.orchestration.state_contracts import ResumeRunState, RunCheckpoint
from apps_eval.contracts.schemas import FindingRecord


class StateRepository(Protocol):
    """Storage-independent port for persisting and recovering typed run state and checkpoints."""

    def save_run_state(self, state: ResumeRunState) -> None:
        """Persist or update the current workflow run state."""
        ...

    def load_run_state(self, run_id: str) -> ResumeRunState | None:
        """Retrieve the latest run state by run_id, or None if not found."""
        ...

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        """Persist an immutable, tamper-evident checkpoint."""
        ...

    def load_checkpoint(self, run_id: str, sequence: int | None = None) -> RunCheckpoint | None:
        """Retrieve a checkpoint by sequence or the latest checkpoint for the run."""
        ...

    def list_checkpoints(self, run_id: str) -> Sequence[RunCheckpoint]:
        """List all checkpoints recorded for a run in monotonic sequence."""
        ...


class EventStore(Protocol):
    """Storage-independent port for append-only, tamper-evident event persistence."""

    def append(self, event: AgentEventEnvelope) -> None:
        """Append an event to the run's audit trail, enforcing cryptographic integrity."""
        ...

    def append_many(self, events: Sequence[AgentEventEnvelope]) -> None:
        """Append multiple events atomically or in sequential order."""
        ...

    def get_run_events(self, run_id: str) -> Sequence[AgentEventEnvelope]:
        """Retrieve all events recorded for a run in monotonic sequence."""
        ...

    def verify_run_chain(self, run_id: str) -> VerificationResult:
        """Verify that a run's event sequence forms an unbroken, untampered chain."""
        ...


class ArtifactStore(Protocol):
    """Storage-independent port for storing and retrieving verified artifacts and manifests."""

    def put_artifact(
        self,
        artifact_id: str,
        content: bytes,
        manifest: ArtifactManifest,
    ) -> ArtifactManifest:
        """Store artifact bytes and manifest, verifying content digest matches."""
        ...

    def get_artifact(self, artifact_id: str) -> bytes:
        """Retrieve raw artifact bytes by artifact_id."""
        ...

    def get_manifest(self, artifact_id: str) -> ArtifactManifest:
        """Retrieve the tamper-evident manifest for an artifact."""
        ...

    def verify_artifact(self, artifact_id: str) -> bool:
        """Verify that stored artifact bytes match the recorded manifest digest."""
        ...


class FindingsQueuePort(Protocol):
    """Storage-independent port for the canonical deduplicated eval findings queue."""

    def upsert_finding(
        self,
        *,
        source_surface: str,
        app_id: str,
        failed_gate_signature: str,
        root_cause_bucket: str,
        owner_subsystem: str,
        track: str,
        priority: str,
        title: str,
        summary: str,
        recommended_action: str,
        occurrence_count: int = 1,
        target_files: Sequence[str] = (),
        sample_trace_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        seen_at_utc: str | None = None,
        cutoff_utc: str | None = None,
    ) -> FindingRecord:
        """Insert or merge a fingerprinted finding while preserving human workflow states."""
        ...

    def list_findings(
        self,
        *,
        status: str | None = None,
        track: str | None = None,
        limit: int = 500,
    ) -> list[FindingRecord]:
        """List findings ordered by impact_score DESC, occurrence_count DESC, finding_id ASC."""
        ...

    def transition_status(
        self,
        finding_id: str,
        to_status: str,
        *,
        actor: str,
        rationale: str,
        hitl_decision_id: str | None = None,
        snoozed_until_utc: str | None = None,
    ) -> FindingRecord:
        """Transition a finding's status and append an immutable audit event."""
        ...

    def export_snapshot(self, snapshot_path: Any) -> dict[str, Any]:
        """Atomically export a canonical JSON snapshot of the findings queue."""
        ...
