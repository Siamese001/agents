"""JSONL Stream Implementation of EventStore Port.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Appends canonical AgentEventEnvelope records to an audit log stream with chain verification.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from agents.observability.events import (
    AgentEventEnvelope,
    AgentEventType,
    VerificationResult,
    verify_event_chain,
)
from agents.persistence.ports import EventStore


class JsonlEventStore(EventStore):
    """Append-only JSONL event stream implementation."""

    def __init__(self, log_path: str | Path) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def append(self, event: AgentEventEnvelope) -> None:
        """Append a single event to the JSONL log file."""
        line = json.dumps(event.to_dict()) + "\n"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def append_many(self, events: Sequence[AgentEventEnvelope]) -> None:
        """Append multiple events to the JSONL log file."""
        lines = "".join(json.dumps(e.to_dict()) + "\n" for e in events)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(lines)

    def get_run_events(self, run_id: str) -> Sequence[AgentEventEnvelope]:
        """Read all events from the log and filter by run_id in monotonic sequence."""
        events: list[AgentEventEnvelope] = []
        if not self.log_path.exists():
            return events

        with self.log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("run_id") == run_id:
                    events.append(
                        AgentEventEnvelope(
                            event_id=data["event_id"],
                            event_type=AgentEventType(data["event_type"]),
                            schema_version=data["schema_version"],
                            run_id=data["run_id"],
                            correlation_id=data["correlation_id"],
                            sequence=data["sequence"],
                            occurred_at=data["occurred_at"],
                            producer=data["producer"],
                            payload=data["payload"],
                            metadata=data["metadata"],
                            previous_event_digest=data["previous_event_digest"],
                            event_digest=data["event_digest"],
                        )
                    )
        events.sort(key=lambda x: x.sequence)
        return events

    def verify_run_chain(self, run_id: str) -> VerificationResult:
        """Verify that a run's event sequence forms an unbroken, untampered chain."""
        events = self.get_run_events(run_id)
        return verify_event_chain(events)
