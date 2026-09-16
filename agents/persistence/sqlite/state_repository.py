"""SQLite Implementation of StateRepository Port.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Persists typed ResumeRunState and RunCheckpoint records with atomic transactions.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence

from agents.orchestration.failure_taxonomy import (
    ExecutionFailure,
    FailureKind,
    RecoveryAction,
)
from agents.orchestration.state_contracts import (
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
    RunCheckpoint,
    RunPhase,
)
from agents.persistence.errors import RecordNotFoundError
from agents.persistence.ports import StateRepository
from agents.persistence.sqlite.schema import initialize_schema


class SqliteStateRepository(StateRepository):
    """SQLite-backed persistent store for ResumeRunState and RunCheckpoint."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        initialize_schema(self._conn, self.db_path)

    def close(self) -> None:
        """Close SQLite database connection."""
        self._conn.close()

    def save_run_state(self, state: ResumeRunState) -> None:
        """Persist or upsert current workflow run state."""
        counters_dict = {
            "transport_retries": state.counters.transport_retries,
            "schema_repairs": state.counters.schema_repairs,
            "semantic_revisions": state.counters.semantic_revisions,
            "cognitive_replans": state.counters.cognitive_replans,
        }
        budget_dict = {
            "max_transport_retries": state.budget.max_transport_retries,
            "max_schema_repairs": state.budget.max_schema_repairs,
            "max_semantic_revisions": state.budget.max_semantic_revisions,
            "max_cognitive_replans": state.budget.max_cognitive_replans,
        }
        last_failure_json = None
        if state.last_failure is not None:
            last_failure_json = json.dumps({
                "failure_kind": state.last_failure.failure_kind.value,
                "message": state.last_failure.message,
                "recovery_action": state.last_failure.recovery_action.value,
                "retryable": state.last_failure.retryable,
                "error_code": state.last_failure.error_code,
                "evidence": list(state.last_failure.evidence),
                "timestamp": state.last_failure.timestamp,
            })

        query = """
        INSERT INTO run_states (
            run_id, workflow_id, phase, step_index, payload_json,
            counters_json, budget_json, context_digest, last_failure_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            workflow_id=excluded.workflow_id,
            phase=excluded.phase,
            step_index=excluded.step_index,
            payload_json=excluded.payload_json,
            counters_json=excluded.counters_json,
            budget_json=excluded.budget_json,
            context_digest=excluded.context_digest,
            last_failure_json=excluded.last_failure_json,
            updated_at=excluded.updated_at;
        """
        with self._conn:
            self._conn.execute(
                query,
                (
                    state.run_id,
                    state.workflow_id,
                    state.phase.value,
                    state.step_index,
                    json.dumps(dict(state.payload)),
                    json.dumps(counters_dict),
                    json.dumps(budget_dict),
                    state.context_digest,
                    last_failure_json,
                    state.created_at,
                    state.updated_at,
                ),
            )

    def load_run_state(self, run_id: str) -> ResumeRunState | None:
        """Retrieve latest run state by run_id."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM run_states WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        if not row:
            return None

        counters_data = json.loads(row["counters_json"])
        budget_data = json.loads(row["budget_json"])
        last_failure = None
        if row["last_failure_json"]:
            fail_data = json.loads(row["last_failure_json"])
            last_failure = ExecutionFailure(
                failure_kind=FailureKind(fail_data["failure_kind"]),
                message=fail_data["message"],
                recovery_action=RecoveryAction(fail_data["recovery_action"]),
                retryable=fail_data.get("retryable", True),
                error_code=fail_data.get("error_code", ""),
                evidence=tuple(fail_data.get("evidence", ())),
                timestamp=fail_data.get("timestamp", 0.0),
            )

        return ResumeRunState(
            run_id=row["run_id"],
            workflow_id=row["workflow_id"],
            phase=RunPhase(row["phase"]),
            step_index=row["step_index"],
            payload=json.loads(row["payload_json"]),
            counters=RecoveryCounters(
                transport_retries=counters_data["transport_retries"],
                schema_repairs=counters_data["schema_repairs"],
                semantic_revisions=counters_data["semantic_revisions"],
                cognitive_replans=counters_data["cognitive_replans"],
            ),
            budget=RecoveryBudget(
                max_transport_retries=budget_data["max_transport_retries"],
                max_schema_repairs=budget_data["max_schema_repairs"],
                max_semantic_revisions=budget_data["max_semantic_revisions"],
                max_cognitive_replans=budget_data["max_cognitive_replans"],
            ),
            context_digest=row["context_digest"],
            last_failure=last_failure,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        """Persist an immutable checkpoint."""
        state = checkpoint.state
        state_repr = {
            "run_id": state.run_id,
            "workflow_id": state.workflow_id,
            "phase": state.phase.value,
            "step_index": state.step_index,
            "payload": dict(state.payload),
            "counters": {
                "transport_retries": state.counters.transport_retries,
                "schema_repairs": state.counters.schema_repairs,
                "semantic_revisions": state.counters.semantic_revisions,
                "cognitive_replans": state.counters.cognitive_replans,
            },
            "budget": {
                "max_transport_retries": state.budget.max_transport_retries,
                "max_schema_repairs": state.budget.max_schema_repairs,
                "max_semantic_revisions": state.budget.max_semantic_revisions,
                "max_cognitive_replans": state.budget.max_cognitive_replans,
            },
            "context_digest": state.context_digest,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }
        query = """
        INSERT INTO run_checkpoints (checkpoint_id, run_id, sequence, state_digest, state_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(checkpoint_id) DO NOTHING;
        """
        with self._conn:
            self._conn.execute(
                query,
                (
                    checkpoint.checkpoint_id,
                    state.run_id,
                    checkpoint.sequence,
                    checkpoint.state_digest,
                    json.dumps(state_repr),
                    checkpoint.timestamp,
                ),
            )

    def load_checkpoint(self, run_id: str, sequence: int | None = None) -> RunCheckpoint | None:
        """Retrieve a checkpoint by sequence or the latest checkpoint for the run."""
        cursor = self._conn.cursor()
        if sequence is not None:
            cursor.execute(
                "SELECT * FROM run_checkpoints WHERE run_id = ? AND sequence = ?",
                (run_id, sequence),
            )
        else:
            cursor.execute(
                "SELECT * FROM run_checkpoints WHERE run_id = ? ORDER BY sequence DESC LIMIT 1",
                (run_id,),
            )
        row = cursor.fetchone()
        if not row:
            return None

        state_data = json.loads(row["state_json"])
        state = ResumeRunState(
            run_id=state_data["run_id"],
            workflow_id=state_data["workflow_id"],
            phase=RunPhase(state_data["phase"]),
            step_index=state_data["step_index"],
            payload=state_data["payload"],
            counters=RecoveryCounters(**state_data["counters"]),
            budget=RecoveryBudget(**state_data["budget"]),
            context_digest=state_data["context_digest"],
            created_at=state_data["created_at"],
            updated_at=state_data["updated_at"],
        )
        return RunCheckpoint(
            checkpoint_id=row["checkpoint_id"],
            sequence=row["sequence"],
            state=state,
            state_digest=row["state_digest"],
            timestamp=row["timestamp"],
        )

    def list_checkpoints(self, run_id: str) -> Sequence[RunCheckpoint]:
        """List all checkpoints for a run in ascending sequence."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM run_checkpoints WHERE run_id = ? ORDER BY sequence ASC",
            (run_id,),
        )
        rows = cursor.fetchall()
        results: list[RunCheckpoint] = []
        for row in rows:
            state_data = json.loads(row["state_json"])
            state = ResumeRunState(
                run_id=state_data["run_id"],
                workflow_id=state_data["workflow_id"],
                phase=RunPhase(state_data["phase"]),
                step_index=state_data["step_index"],
                payload=state_data["payload"],
                counters=RecoveryCounters(**state_data["counters"]),
                budget=RecoveryBudget(**state_data["budget"]),
                context_digest=state_data["context_digest"],
                created_at=state_data["created_at"],
                updated_at=state_data["updated_at"],
            )
            results.append(
                RunCheckpoint(
                    checkpoint_id=row["checkpoint_id"],
                    sequence=row["sequence"],
                    state=state,
                    state_digest=row["state_digest"],
                    timestamp=row["timestamp"],
                )
            )
        return results
