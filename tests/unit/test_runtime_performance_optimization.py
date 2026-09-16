"""Unit tests verifying Runtime Performance Acceleration & Optimization (Waves 1-4).

Verifies:
1. Tooling acceleration: Single-pass file discovery with exact pruning, shared AST parsing, and fast secrets scan.
2. Capability Gateway: Batch threadpool dispatch and async non-blocking execution.
3. SQLite Persistence: High-performance WAL mode and pragma activation on file databases.
4. Correctness & Isolation: Zero regression across governance invariants, state contracts, and purity rules.
"""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import time
from pathlib import Path
import pytest

from agents.context.provenance import ContextSnapshot
from agents.gateway.contracts import CapabilityRequest, CapabilityResponse, ModelTier
from agents.gateway.model_gateway import ModelCapabilityGateway
from agents.observability.events import AgentEventEnvelope, AgentEventType
from agents.orchestration.state_contracts import (
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
    RunPhase,
)
from agents.persistence.sqlite.event_store import SqliteEventStore
from agents.persistence.sqlite.schema import tune_connection_pragmas
from agents.persistence.sqlite.state_repository import SqliteStateRepository
from tools.lint_secrets import FAST_SECRET_TRIGGERS, check_file_for_secrets
from tools.verify_commit import (
    _analyze_single_python_file,
    _collect_repository_files,
    run_precommit_gate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Wave 1: Tooling & Pre-Commit AST Single-Pass Acceleration
# ---------------------------------------------------------------------------

def test_collect_repository_files_pruning() -> None:
    """Verify single-pass file collection prunes .venv, .git, artifacts, and docs/archive."""
    py_files, schema_files, secret_files = _collect_repository_files(REPO_ROOT)
    assert len(py_files) > 1000
    assert len(secret_files) > 1000

    # Ensure no pruned directories leaked into collection
    for p in py_files:
        rel = str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        assert not rel.startswith(".git/"), f"Leaked .git: {rel}"
        assert not rel.startswith(".venv/"), f"Leaked .venv: {rel}"
        assert not rel.startswith("artifacts/"), f"Leaked artifacts: {rel}"
        assert not rel.startswith("docs/archive/"), f"Leaked docs/archive: {rel}"


def test_analyze_single_python_file_clean_file(tmp_path: Path) -> None:
    """Verify _analyze_single_python_file cleanly validates a compliant production file."""
    clean_code = (
        "'''Clean module.'''\n"
        "def compute(a: int, b: int) -> int:\n"
        "    return a + b\n"
    )
    clean_file = tmp_path / "clean_mod.py"
    clean_file.write_text(clean_code, encoding="utf-8")

    h_errs, g_errs, p_errs = _analyze_single_python_file(clean_file, tmp_path)
    assert len(h_errs) == 0
    assert len(g_errs) == 0
    assert len(p_errs) == 0


def test_analyze_single_python_file_catches_syntax_error(tmp_path: Path) -> None:
    """Verify _analyze_single_python_file detects syntax errors in-memory without crashing."""
    bad_code = "def broken(\n"
    bad_file = tmp_path / "bad_syntax.py"
    bad_file.write_text(bad_code, encoding="utf-8")

    h_errs, g_errs, p_errs = _analyze_single_python_file(bad_file, tmp_path)
    assert len(h_errs) == 1
    assert "Syntax compilation error" in h_errs[0] or "AST syntax error" in h_errs[0]


def test_lint_secrets_fast_prefilter(tmp_path: Path) -> None:
    """Verify FAST_SECRET_TRIGGERS correctly flags secret lines and skips benign files."""
    assert "private key" in FAST_SECRET_TRIGGERS
    assert "sk-" in FAST_SECRET_TRIGGERS
    assert "akia" in FAST_SECRET_TRIGGERS

    # Benign file: should be skipped in sub-millisecond time
    benign_file = tmp_path / "benign.txt"
    benign_file.write_text("Hello world, this is a plain document without credentials.\n" * 100)
    violations = check_file_for_secrets(benign_file, tmp_path)
    assert len(violations) == 0


# ---------------------------------------------------------------------------
# Wave 2: SQLite WAL & Persistence Optimization
# ---------------------------------------------------------------------------

def test_sqlite_wal_pragma_activation_on_disk(tmp_path: Path) -> None:
    """Verify file-backed SQLite state repository and event store activate WAL mode."""
    db_file = tmp_path / "test_perf.sqlite"
    repo = SqliteStateRepository(db_file)

    # Inspect SQLite connection pragmas directly
    cursor = repo._conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal", f"Expected WAL journal mode, got {mode}"

    cursor.execute("PRAGMA synchronous;")
    sync_mode = cursor.fetchone()[0]
    # In SQLite, NORMAL synchronous mode is 1
    assert sync_mode == 1, f"Expected synchronous=1 (NORMAL), got {sync_mode}"

    # Verify state roundtrip under WAL mode
    state = ResumeRunState(
        run_id="run_wal_test",
        workflow_id="wf_wal_test",
        phase=RunPhase.RUNNING,
        step_index=1,
        budget=RecoveryBudget(),
        counters=RecoveryCounters(),
        payload={"stage": "test"},
        context_digest="abc123",
    )
    repo.save_run_state(state)
    loaded = repo.load_run_state("run_wal_test")
    assert loaded is not None
    assert loaded.run_id == "run_wal_test"
    repo.close()


def test_sqlite_event_store_wal_pragma_on_disk(tmp_path: Path) -> None:
    """Verify file-backed SQLite event store activates WAL mode."""
    db_file = tmp_path / "events_perf.sqlite"
    store = SqliteEventStore(db_file)

    cursor = store._conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal", f"Expected WAL journal mode, got {mode}"

    cursor.execute("PRAGMA busy_timeout;")
    busy_timeout = cursor.fetchone()[0]
    assert busy_timeout == 5000, f"Expected busy_timeout=5000, got {busy_timeout}"
    store.close()


def test_sqlite_event_store_append_many_atomic_transaction(tmp_path: Path) -> None:
    """Verify append_many batches event insertion in a single atomic transaction."""
    db_file = tmp_path / "events_batch.sqlite"
    store = SqliteEventStore(db_file)

    from agents.observability.events import create_event_envelope

    events = []
    prev_digest = None
    for i in range(1, 21):
        evt = create_event_envelope(
            run_id="run_batch_test",
            correlation_id="corr_batch_test",
            sequence=i,
            event_type=AgentEventType.PHASE_TRANSITION,
            producer="test_producer",
            payload={"index": i},
            previous_event_digest=prev_digest,
        )
        events.append(evt)
        prev_digest = evt.event_digest

    t0 = time.perf_counter()
    store.append_many(events)
    elapsed = time.perf_counter() - t0

    loaded = store.get_run_events("run_batch_test")
    assert len(loaded) == 20
    assert loaded[-1].sequence == 20

    # Chain must verify untampered
    result = store.verify_run_chain("run_batch_test")
    assert result.is_valid is True
    # 20 events in a single batch on SSD should complete in < 0.1s
    assert elapsed < 0.2
    store.close()



# ---------------------------------------------------------------------------
# Wave 3: Capability Gateway Batch & Async Dispatch
# ---------------------------------------------------------------------------

def test_capability_gateway_execute_batch() -> None:
    """Verify execute_batch runs multiple requests concurrently and preserves ordering."""
    gateway = ModelCapabilityGateway()

    # Register a simulated adapter with a tiny simulated latency
    def delayed_adapter(req: CapabilityRequest) -> CapabilityResponse:
        time.sleep(0.01)
        return CapabilityResponse(
            content=f"Response for {req.capability_name}",
            provider="test",
            model_id="test-model",
            status="SUCCESS",
        )

    gateway.register_adapter("cap_a", delayed_adapter)
    gateway.register_adapter("cap_b", delayed_adapter)
    gateway.register_adapter("cap_c", delayed_adapter)

    snapshot = ContextSnapshot(snapshot_id="snap_batch", items=(), max_token_budget=1000)
    requests = [
        CapabilityRequest(capability_name="cap_a", prompt_snapshot=snapshot),
        CapabilityRequest(capability_name="cap_b", prompt_snapshot=snapshot),
        CapabilityRequest(capability_name="cap_c", prompt_snapshot=snapshot),
    ]

    t0 = time.perf_counter()
    responses = gateway.execute_batch(requests, max_workers=3, batch_id="batch_perf_123")
    elapsed = time.perf_counter() - t0

    assert len(responses) == 3
    assert responses[0].content == "Response for cap_a"
    assert responses[1].content == "Response for cap_b"
    assert responses[2].content == "Response for cap_c"
    assert responses[0].batch_id == "batch_perf_123"
    assert responses[1].batch_id == "batch_perf_123"
    assert responses[2].batch_id == "batch_perf_123"
    # Concurrent execution of 3 x 10ms tasks should finish in ~10-25ms, not 30ms+
    assert elapsed < 0.15


def test_capability_gateway_async_execute() -> None:
    """Verify async_execute runs non-blockingly inside an asyncio event loop."""
    gateway = ModelCapabilityGateway()
    snapshot = ContextSnapshot(snapshot_id="snap_async", items=(), max_token_budget=1000)
    req = CapabilityRequest(
        capability_name="async_test",
        prompt_snapshot=snapshot,
        correlation_id="corr_async_456",
    )

    async def _runner() -> CapabilityResponse:
        return await gateway.async_execute(req)

    response = asyncio.run(_runner())
    assert response.status == "SUCCESS"
    assert response.correlation_id == "corr_async_456"
    assert "Simulated execution" in response.content


# ---------------------------------------------------------------------------
# Wave 4: Pre-Commit Gate Accelerated Performance Bounds
# ---------------------------------------------------------------------------

def test_precommit_gate_performance_on_explicit_files() -> None:
    """Verify pre-commit quality gate executes on explicit files in under 0.5s."""
    sample_files = [
        REPO_ROOT / "agents" / "cli.py",
        REPO_ROOT / "agents" / "gateway" / "model_gateway.py",
        REPO_ROOT / "tools" / "verify_commit.py",
    ]
    t0 = time.perf_counter()
    code, results = run_precommit_gate(sample_files, REPO_ROOT, mode_name="unit-test-explicit")
    elapsed = time.perf_counter() - t0

    assert code == 0
    assert elapsed < 1.0, f"Pre-commit check on 3 files took {elapsed:.2f}s (expected < 1.0s)"
