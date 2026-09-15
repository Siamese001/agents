"""Unit tests for Wave 4: Observability, Replay, and Persistence Boundaries.

Verifies:
1. Canonical AgentEventEnvelope creates tamper-evident cryptographic hash chains.
2. ArtifactManifest binds raw bytes to SHA-256 digests and detects corruption.
3. SQLite StateRepository stores and recovers ResumeRunState and RunCheckpoint.
4. SQLite and JSONL EventStores maintain immutable audit logs and verify chains.
5. FilesystemArtifactStore enforces digest verification on put/get.
6. ReplayVerifier forensically reconstructs workflow history from recorded events.
7. Domain contracts maintain clean separation from concrete persistence adapters.
8. TelemetryEvent adapts seamlessly to canonical AgentEventEnvelope.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import pytest

from agents.observability import (
    AgentEventEnvelope,
    AgentEventType,
    ArtifactDigest,
    ArtifactManifest,
    DeterministicReplayEngine,
    ReplayRequest,
    ReplayVerifier,
    create_artifact_manifest,
    create_event_envelope,
    verify_event_chain,
)
from agents.orchestration.state_contracts import (
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
    RunPhase,
)
from agents.persistence import (
    FilesystemArtifactStore,
    JsonlEventStore,
    SqliteEventStore,
    SqliteStateRepository,
    TamperDetectionError,
)
from agents.telemetry import CorrelationContext, TelemetryEvent, TelemetryEventType


def test_canonical_event_envelope_tamper_evidence() -> None:
    run_id = "run-wave4-001"
    corr_id = "corr-wave4-001"

    # Event 1: Root
    e1 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=1,
        producer="orchestration_engine",
        payload={"previous_phase": "CREATED", "next_phase": "RUNNING"},
        previous_event_digest=None,
    )
    assert e1.verify_integrity() is True
    assert e1.previous_event_digest is None

    # Event 2: Chained
    e2 = create_event_envelope(
        event_type=AgentEventType.FEEDBACK_DECISION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=2,
        producer="feedback_controller",
        payload={"action": "ACCEPT", "diagnostic": "Validation passed"},
        previous_event_digest=e1.event_digest,
    )
    assert e2.verify_integrity() is True
    assert e2.previous_event_digest == e1.event_digest

    # Verify chain
    res = verify_event_chain([e1, e2])
    assert res.is_valid is True
    assert res.verified_count == 2

    # Tampering test: modify payload of e2
    tampered_e2 = AgentEventEnvelope(
        event_id=e2.event_id,
        event_type=e2.event_type,
        schema_version=e2.schema_version,
        run_id=e2.run_id,
        correlation_id=e2.correlation_id,
        sequence=e2.sequence,
        occurred_at=e2.occurred_at,
        producer=e2.producer,
        payload={"action": "TERMINAL_FAIL", "diagnostic": "Tampered payload"},
        metadata=e2.metadata,
        previous_event_digest=e2.previous_event_digest,
        event_digest=e2.event_digest,
    )
    assert tampered_e2.verify_integrity() is False
    tampered_res = verify_event_chain([e1, tampered_e2])
    assert tampered_res.is_valid is False
    assert tampered_res.tampered_event_id == e2.event_id


def test_artifact_manifest_provenance_and_verification(tmp_path: Path) -> None:
    content = b"Candidate John Doe - Principal Systems Architect\nExperience: 10 years..."
    manifest = create_artifact_manifest(
        run_id="run-manifest-001",
        artifact_id="resume-001",
        artifact_type="markdown_resume",
        producer="resume_assembler",
        raw_bytes=content,
        media_type="text/markdown",
    )

    assert manifest.verify_integrity() is True
    assert manifest.content.algorithm == "sha256"
    assert manifest.content.value == hashlib.sha256(content).hexdigest()
    assert manifest.content.byte_length == len(content)

    # Corrupting manifest digest
    corrupt_manifest = ArtifactManifest(
        manifest_id=manifest.manifest_id,
        run_id=manifest.run_id,
        artifact_id=manifest.artifact_id,
        artifact_type=manifest.artifact_type,
        producer=manifest.producer,
        created_at=manifest.created_at,
        content=manifest.content,
        input_artifact_ids=manifest.input_artifact_ids,
        provenance={"unauthorized": "modification"},
        previous_manifest_digest=manifest.previous_manifest_digest,
        manifest_digest=manifest.manifest_digest,
        schema_version=manifest.schema_version,
    )
    assert corrupt_manifest.verify_integrity() is False


def test_sqlite_state_repository_roundtrip() -> None:
    repo = SqliteStateRepository(":memory:")

    state = ResumeRunState(
        run_id="run-sqlite-001",
        workflow_id="wf-sqlite-001",
        phase=RunPhase.RUNNING,
        step_index=3,
        payload={"section": "experience", "candidate_name": "Alice"},
        counters=RecoveryCounters(transport_retries=1, semantic_revisions=1),
        budget=RecoveryBudget(max_semantic_revisions=2),
    )

    # 1. Save and load run state
    repo.save_run_state(state)
    loaded = repo.load_run_state("run-sqlite-001")
    assert loaded is not None
    assert loaded.run_id == state.run_id
    assert loaded.phase == RunPhase.RUNNING
    assert loaded.step_index == 3
    assert loaded.counters.transport_retries == 1
    assert loaded.counters.semantic_revisions == 1
    assert loaded.payload["candidate_name"] == "Alice"

    # 2. Checkpoint persistence
    chk1 = state.create_checkpoint(sequence=1)
    chk2 = state.create_checkpoint(sequence=2)
    repo.save_checkpoint(chk1)
    repo.save_checkpoint(chk2)

    loaded_chk = repo.load_checkpoint("run-sqlite-001", sequence=1)
    assert loaded_chk is not None
    assert loaded_chk.checkpoint_id == chk1.checkpoint_id
    assert loaded_chk.state_digest == chk1.state_digest
    assert loaded_chk.verify_integrity() is True

    # Checkpoint listing
    checkpoints = repo.list_checkpoints("run-sqlite-001")
    assert len(checkpoints) == 2
    assert checkpoints[0].sequence == 1
    assert checkpoints[1].sequence == 2

    repo.close()


def test_sqlite_event_store_append_and_chain_verification() -> None:
    store = SqliteEventStore(":memory:")
    run_id = "run-sql-events"

    e1 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id="corr-sql-1",
        sequence=1,
        producer="test",
        payload={"phase": "CREATED"},
    )
    e2 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id="corr-sql-1",
        sequence=2,
        producer="test",
        payload={"phase": "RUNNING"},
        previous_event_digest=e1.event_digest,
    )

    store.append_many([e1, e2])

    recorded = store.get_run_events(run_id)
    assert len(recorded) == 2
    assert recorded[0].sequence == 1
    assert recorded[1].sequence == 2

    v_res = store.verify_run_chain(run_id)
    assert v_res.is_valid is True
    assert v_res.verified_count == 2

    store.close()


def test_jsonl_and_filesystem_persistence(tmp_path: Path) -> None:
    # 1. JsonlEventStore
    log_file = tmp_path / "events.jsonl"
    store = JsonlEventStore(log_file)
    run_id = "run-jsonl-001"

    e1 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id="corr-1",
        sequence=1,
        producer="engine",
        payload={"phase": "CREATED"},
    )
    e2 = create_event_envelope(
        event_type=AgentEventType.CHECKPOINT_STORED,
        run_id=run_id,
        correlation_id="corr-1",
        sequence=2,
        producer="engine",
        payload={"checkpoint_id": "chk-001"},
        previous_event_digest=e1.event_digest,
    )
    store.append(e1)
    store.append(e2)

    events = store.get_run_events(run_id)
    assert len(events) == 2
    assert store.verify_run_chain(run_id).is_valid is True

    # 2. FilesystemArtifactStore
    art_store = FilesystemArtifactStore(tmp_path / "artifacts_repo")
    content = b"PDF resume binary bytes header: 12345"
    manifest = create_artifact_manifest(
        run_id=run_id,
        artifact_id="resume-pdf-01",
        artifact_type="pdf_resume",
        producer="pdf_renderer",
        raw_bytes=content,
    )

    art_store.put_artifact("resume-pdf-01", content, manifest)
    read_bytes = art_store.get_artifact("resume-pdf-01")
    assert read_bytes == content
    assert art_store.verify_artifact("resume-pdf-01") is True

    # Tampering test: corrupt stored binary
    bin_file = tmp_path / "artifacts_repo" / "artifacts" / "resume-pdf-01.bin"
    bin_file.write_bytes(b"CORRUPTED_BYTES")
    assert art_store.verify_artifact("resume-pdf-01") is False


def test_replay_verifier_reconstruction() -> None:
    run_id = "run-replay-001"
    corr_id = "corr-replay-001"

    e1 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=1,
        producer="engine",
        payload={"previous_phase": "CREATED", "next_phase": "RUNNING"},
    )
    e2 = create_event_envelope(
        event_type=AgentEventType.FEEDBACK_DECISION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=2,
        producer="feedback_controller",
        payload={"action": "REQUEST_SEMANTIC_REVISION", "errors": ["Word count > 24"]},
        previous_event_digest=e1.event_digest,
    )
    e3 = create_event_envelope(
        event_type=AgentEventType.FEEDBACK_DECISION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=3,
        producer="feedback_controller",
        payload={"action": "ACCEPT", "errors": []},
        previous_event_digest=e2.event_digest,
    )
    e4 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=4,
        producer="engine",
        payload={"previous_phase": "RUNNING", "next_phase": "COMPLETED"},
        previous_event_digest=e3.event_digest,
    )

    verifier = ReplayVerifier()
    result = verifier.verify_run_integrity(run_id, [e1, e2, e3, e4])

    assert result.is_replayable is True
    assert result.total_events == 4
    assert result.final_phase == "COMPLETED"
    assert result.phase_transitions == ("CREATED->RUNNING", "RUNNING->COMPLETED")
    assert result.feedback_decisions == ("REQUEST_SEMANTIC_REVISION", "ACCEPT")
    assert len(result.errors) == 0


def test_telemetry_event_adaptation() -> None:
    corr = CorrelationContext(run_id="run-telem-001", workflow_id="wf-telem-001")
    telem = TelemetryEvent(
        event_id="telem-001",
        event_type=TelemetryEventType.WORKFLOW_START,
        timestamp="2026-09-14T20:00:00Z",
        correlation=corr,
        payload={"workflow_name": "resume_flow"},
    )

    envelope = telem.to_agent_event_envelope(sequence=1, producer="test_harness")
    assert isinstance(envelope, AgentEventEnvelope)
    assert envelope.run_id == "run-telem-001"
    assert envelope.event_type == AgentEventType.PHASE_TRANSITION
    assert envelope.sequence == 1
    assert envelope.verify_integrity() is True


def test_event_chain_failure_modes() -> None:
    run_id = "run-fail-modes"
    corr_id = "corr-fail-modes"

    e1 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=1,
        producer="engine",
        payload={"phase": "CREATED"},
    )
    e2 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=2,
        producer="engine",
        payload={"phase": "RUNNING"},
        previous_event_digest=e1.event_digest,
    )
    e3 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=3,
        producer="engine",
        payload={"phase": "COMPLETED"},
        previous_event_digest=e2.event_digest,
    )

    # 1. Missing event (e.g. e2 skipped -> e1 followed by e3)
    skip_res = verify_event_chain([e1, e3])
    assert skip_res.is_valid is False
    assert "previous_event_digest" in skip_res.error_message

    # 2. Reordered events (e2 before e1)
    reordered_res = verify_event_chain([e2, e1])
    assert reordered_res.is_valid is False


def test_persistence_domain_isolation() -> None:
    import inspect
    import agents.orchestration.state_contracts as sc
    import agents.orchestration.feedback_controller as fc

    sc_source = inspect.getsource(sc)
    fc_source = inspect.getsource(fc)

    # Domain contracts must not directly import sqlite3 or concrete persistence modules
    assert "import sqlite3" not in sc_source
    assert "import sqlite3" not in fc_source
    assert "agents.persistence.sqlite" not in sc_source
    assert "agents.persistence.sqlite" not in fc_source


def test_sqlite_event_store_concurrency_and_duplicates() -> None:
    store = SqliteEventStore(":memory:")
    run_id = "run-sql-dups"

    e1 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id="corr-sql-dup",
        sequence=1,
        producer="test",
        payload={"phase": "CREATED"},
    )
    store.append(e1)

    # Attempt to append duplicate sequence for the same run_id must raise sqlite3.IntegrityError
    duplicate_e1 = create_event_envelope(
        event_type=AgentEventType.FEEDBACK_DECISION,
        run_id=run_id,
        correlation_id="corr-sql-dup",
        sequence=1,
        producer="test",
        payload={"action": "CONFLICT"},
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.append(duplicate_e1)

    store.close()


def test_adversarial_replay_scenarios() -> None:
    run_id = "run-adversarial"
    corr_id = "corr-adversarial"

    e1 = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id=run_id,
        correlation_id=corr_id,
        sequence=1,
        producer="engine",
        payload={"previous_phase": "CREATED", "next_phase": "RUNNING"},
    )

    # Valid artifact manifest and content
    content = b"Candidate Resume v1.0"
    manifest = create_artifact_manifest(
        run_id=run_id,
        artifact_id="art-adv-01",
        artifact_type="text_resume",
        producer="builder",
        raw_bytes=content,
    )

    engine = DeterministicReplayEngine()

    # Scenario 1: Missing artifact manifest
    bad_req_1 = ReplayRequest(
        run_id=run_id,
        events=[e1],
        artifacts={"art-adv-01": content},
        manifests=[],
    )
    res_1 = engine.replay_run(bad_req_1)
    assert res_1.is_replayable is False
    assert any("Missing manifest" in err for err in res_1.errors)

    # Scenario 2: Content tampering (byte hash mismatch against manifest)
    tampered_bytes = b"Tampered Content!"
    bad_req_2 = ReplayRequest(
        run_id=run_id,
        events=[e1],
        artifacts={"art-adv-01": tampered_bytes},
        manifests=[manifest],
    )
    res_2 = engine.replay_run(bad_req_2)
    assert res_2.is_replayable is False
    assert any("hash mismatch" in err for err in res_2.errors)


def test_schema_version_and_metadata_invariants() -> None:
    e = create_event_envelope(
        event_type=AgentEventType.PHASE_TRANSITION,
        run_id="run-schema-01",
        correlation_id="corr-schema-01",
        sequence=1,
        producer="engine",
        payload={"phase": "CREATED"},
        metadata={"tenant": "acme", "environment": "production"},
    )
    assert e.schema_version == 1
    assert e.metadata["tenant"] == "acme"
    assert e.verify_integrity() is True

    manifest = create_artifact_manifest(
        run_id="run-schema-01",
        artifact_id="art-schema-01",
        artifact_type="audit_log",
        producer="logger",
        raw_bytes=b"log bytes",
    )
    assert manifest.schema_version == 1
    assert manifest.verify_integrity() is True


