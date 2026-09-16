"""SQLite Schema Definitions for State, Checkpoints, and Events.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
"""

from __future__ import annotations

import sqlite3

CREATE_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS run_states (
    run_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    counters_json TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    context_digest TEXT NOT NULL,
    last_failure_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""

CREATE_CHECKPOINTS_TABLE = """
CREATE TABLE IF NOT EXISTS run_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    state_digest TEXT NOT NULL,
    state_json TEXT NOT NULL,
    timestamp REAL NOT NULL,
    UNIQUE(run_id, sequence)
);
"""

CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS agent_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    producer TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    previous_event_digest TEXT,
    event_digest TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(run_id, sequence)
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON run_checkpoints(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_events_run ON agent_events(run_id, sequence);
"""


def tune_connection_pragmas(conn: sqlite3.Connection, db_path: str = "") -> None:
    """Configure high-performance SQLite pragmas (WAL, NORMAL sync, memory cache, busy timeout)."""
    try:
        if db_path and db_path != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA cache_size = -32000;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA busy_timeout = 5000;")
        else:
            conn.execute("PRAGMA synchronous = OFF;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA busy_timeout = 5000;")
    except Exception:
        pass


def initialize_schema(conn: sqlite3.Connection, db_path: str = "") -> None:
    """Initialize database tables, indexes, and performance pragmas."""
    tune_connection_pragmas(conn, db_path)
    with conn:
        conn.execute(CREATE_STATE_TABLE)
        conn.execute(CREATE_CHECKPOINTS_TABLE)
        conn.execute(CREATE_EVENTS_TABLE)
        conn.executescript(CREATE_INDEXES)

