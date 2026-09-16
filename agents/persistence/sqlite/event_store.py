"""SQLite Implementation of EventStore Port.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Stores immutable AgentEventEnvelope records and verifies cryptographic hash chains.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Sequence

from agents.observability.events import (
    AgentEventEnvelope,
    AgentEventType,
    VerificationResult,
    verify_event_chain,
)
from agents.persistence.ports import EventStore
from agents.persistence.sqlite.schema import initialize_schema


class SqliteEventStore(EventStore):
    """SQLite-backed append-only audit log for AgentEventEnvelope records."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        initialize_schema(self._conn, self.db_path)

    def close(self) -> None:
        """Close SQLite database connection."""
        self._conn.close()

    def append(self, event: AgentEventEnvelope) -> None:
        """Append an event to the run's audit trail."""
        query = """
        INSERT INTO agent_events (
            event_id, run_id, correlation_id, sequence, event_type,
            occurred_at, producer, payload_json, metadata_json,
            previous_event_digest, event_digest, schema_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self._conn:
            self._conn.execute(
                query,
                (
                    event.event_id,
                    event.run_id,
                    event.correlation_id,
                    event.sequence,
                    event.event_type.value,
                    event.occurred_at,
                    event.producer,
                    json.dumps(dict(event.payload)),
                    json.dumps(dict(event.metadata)),
                    event.previous_event_digest,
                    event.event_digest,
                    event.schema_version,
                ),
            )

    def append_many(self, events: Sequence[AgentEventEnvelope]) -> None:
        """Append multiple events in order within a single atomic transaction."""
        if not events:
            return
        query = """
        INSERT INTO agent_events (
            event_id, run_id, correlation_id, sequence, event_type,
            occurred_at, producer, payload_json, metadata_json,
            previous_event_digest, event_digest, schema_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        rows = [
            (
                event.event_id,
                event.run_id,
                event.correlation_id,
                event.sequence,
                event.event_type.value,
                event.occurred_at,
                event.producer,
                json.dumps(dict(event.payload)),
                json.dumps(dict(event.metadata)),
                event.previous_event_digest,
                event.event_digest,
                event.schema_version,
            )
            for event in events
        ]
        with self._conn:
            self._conn.executemany(query, rows)

    def get_run_events(self, run_id: str) -> Sequence[AgentEventEnvelope]:
        """Retrieve all events recorded for a run in monotonic sequence."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM agent_events WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        )
        rows = cursor.fetchall()
        events: list[AgentEventEnvelope] = []
        for row in rows:
            events.append(
                AgentEventEnvelope(
                    event_id=row["event_id"],
                    event_type=AgentEventType(row["event_type"]),
                    schema_version=row["schema_version"],
                    run_id=row["run_id"],
                    correlation_id=row["correlation_id"],
                    sequence=row["sequence"],
                    occurred_at=row["occurred_at"],
                    producer=row["producer"],
                    payload=json.loads(row["payload_json"]),
                    metadata=json.loads(row["metadata_json"]),
                    previous_event_digest=row["previous_event_digest"],
                    event_digest=row["event_digest"],
                )
            )
        return events

    def verify_run_chain(self, run_id: str) -> VerificationResult:
        """Verify that a run's event sequence forms an unbroken, untampered chain."""
        events = self.get_run_events(run_id)
        return verify_event_chain(events)
