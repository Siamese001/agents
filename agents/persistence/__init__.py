"""Agents Persistence Package.

Exports storage-independent persistence ports, typed errors, and standard
reference adapters (SQLite and JSONL/Filesystem).
"""

from agents.persistence.errors import (
    ConcurrencyError,
    PersistenceError,
    RecordNotFoundError,
    TamperDetectionError,
)
from agents.persistence.jsonl import (
    FilesystemArtifactStore,
    JsonlEventStore,
)
from agents.persistence.ports import (
    ArtifactStore,
    EventStore,
    StateRepository,
)
from agents.persistence.sqlite import (
    SqliteEventStore,
    SqliteStateRepository,
)

__all__ = [
    "ArtifactStore",
    "ConcurrencyError",
    "EventStore",
    "FilesystemArtifactStore",
    "JsonlEventStore",
    "PersistenceError",
    "RecordNotFoundError",
    "SqliteEventStore",
    "SqliteStateRepository",
    "StateRepository",
    "TamperDetectionError",
]
