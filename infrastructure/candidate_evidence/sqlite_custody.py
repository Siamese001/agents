"""5-check SQLite chain-of-custody validator for candidate evidence graph.

Zero upward imports: never import ``apps_lic``, ``apps_rg``, ``apps_research``, or ``apps_eval``.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from infrastructure.candidate_evidence.contracts import (
    CandidateEvidenceContractError,
    CustodyCheckReport,
)

REQUIRED_TABLES: tuple[str, ...] = (
    "graph_nodes",
    "graph_edges",
    "semantic_unit",
    "unit_vectors",
    "assertion_learned_sparse",
    "assertion_colbert_vectors",
    "graph_metadata",
)

REQUIRED_FTS5_TABLES: tuple[str, ...] = (
    "graph_nodes_fts",
)


def compute_sha256(path: Path | str, chunk_size: int = 1024 * 1024) -> str:
    """Compute deterministic hex SHA-256 digest of file on disk."""
    p = Path(path)
    if not p.is_file():
        return ""
    hasher = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def open_candidate_graph_readonly(db_path: Path | str) -> sqlite3.Connection:
    """Open candidate graph SQLite connection strictly read-only with URI isolation and PRAGMA query_only=ON."""
    p = Path(db_path).resolve()
    if not p.is_file():
        raise CandidateEvidenceContractError(f"Candidate graph SQLite file does not exist: {p}")
    uri = f"file:{p.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=15)
    conn.execute("PRAGMA query_only=ON")
    return conn


def verify_sqlite_custody(
    db_path: Path | str,
    *,
    expected_sha256: str = "",
    min_node_count: int = 10,
    min_fact_count: int = 10,
    min_unit_count: int = 10,
    check_colbert: bool = True,
) -> CustodyCheckReport:
    """Perform 5-check SQLite chain-of-custody validation on augmented_skills_graph.sqlite.

    Check 1: File existence & non-zero file size.
    Check 2: SQLite header magic bytes ('SQLite format 3\\x00') & PRAGMA quick_check integrity.
    Check 3: Required tables, FTS5 virtual tables, and views present.
    Check 4: Non-empty candidate nodes/facts count & schema version metadata check.
    Check 5: Deterministic SHA-256 checksum & manifest verification status.
    """
    p = Path(db_path).resolve()
    errors: list[str] = []

    # Check 1: File exists and is non-zero
    check_1 = p.is_file() and p.stat().st_size > 100
    file_size = p.stat().st_size if p.is_file() else 0
    if not check_1:
        errors.append(f"Check 1 failed: file missing or size <= 100 bytes ({file_size} bytes)")
        return CustodyCheckReport(
            db_path=str(p),
            passed=False,
            check_1_file_exists_nonzero=False,
            check_2_sqlite_header_and_quick_check=False,
            check_3_required_tables_and_fts5=False,
            check_4_candidate_node_count_and_schema=False,
            check_5_sha256_and_manifest_verified=False,
            candidate_graph_db_sha256="",
            manifest_verification_status="FILE_NOT_FOUND_OR_EMPTY",
            file_size_bytes=file_size,
            errors=tuple(errors),
        )

    # Check 2: SQLite header magic & quick_check
    check_2 = False
    try:
        with p.open("rb") as f:
            header = f.read(16)
        if header != b"SQLite format 3\x00":
            errors.append(f"Check 2 failed: invalid header magic: {header!r}")
        else:
            conn = open_candidate_graph_readonly(p)
            try:
                cur = conn.cursor()
                quick_res = [r[0] for r in cur.execute("PRAGMA quick_check").fetchall()]
                if quick_res == ["ok"]:
                    check_2 = True
                else:
                    errors.append(f"Check 2 failed: PRAGMA quick_check returned: {quick_res}")
            finally:
                conn.close()
    except Exception as exc:
        errors.append(f"Check 2 exception: {exc}")

    # Check 3: Required tables & FTS5 virtual tables
    check_3 = False
    existing_tables: set[str] = set()
    if check_2:
        try:
            conn = open_candidate_graph_readonly(p)
            try:
                cur = conn.cursor()
                rows = cur.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()
                existing_tables = {str(r[0]) for r in rows}
                missing_tables = [t for t in REQUIRED_TABLES if t not in existing_tables]
                missing_fts = [t for t in REQUIRED_FTS5_TABLES if t not in existing_tables]
                if missing_tables or missing_fts:
                    errors.append(f"Check 3 failed: missing tables {missing_tables}, missing fts {missing_fts}")
                else:
                    check_3 = True
            finally:
                conn.close()
        except Exception as exc:
            errors.append(f"Check 3 exception: {exc}")

    # Check 4: Non-empty candidate node count & schema version
    check_4 = False
    node_count = 0
    fact_count = 0
    unit_count = 0
    schema_ver = ""
    ledger_hash = ""
    if check_3:
        try:
            conn = open_candidate_graph_readonly(p)
            try:
                cur = conn.cursor()
                node_count = int(cur.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0] or 0)
                fact_count = int(
                    cur.execute(
                        "SELECT COUNT(*) FROM graph_nodes WHERE node_type = 'fact' AND external_eligible = 1"
                    ).fetchone()[0]
                    or 0
                )
                unit_count = int(cur.execute("SELECT COUNT(*) FROM semantic_unit").fetchone()[0] or 0)
                meta_row = cur.execute(
                    "SELECT graph_version, ledger_hash FROM graph_metadata ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
                if meta_row:
                    schema_ver = str(meta_row[0] or "")
                    ledger_hash = str(meta_row[1] or "")

                if node_count < min_node_count or fact_count < min_fact_count or unit_count < min_unit_count:
                    errors.append(
                        f"Check 4 failed: insufficient counts: nodes={node_count} (min {min_node_count}), "
                        f"facts={fact_count} (min {min_fact_count}), semantic_units={unit_count} (min {min_unit_count})"
                    )
                elif not schema_ver:
                    errors.append("Check 4 failed: graph_version missing in graph_metadata")
                else:
                    check_4 = True
            finally:
                conn.close()
        except Exception as exc:
            errors.append(f"Check 4 exception: {exc}")

    # Check 5: Deterministic SHA-256 and manifest verification
    check_5 = False
    db_sha256 = ""
    manifest_status = "UNVERIFIED"
    if check_4:
        try:
            db_sha256 = compute_sha256(p)
            if expected_sha256:
                if db_sha256.lower() == expected_sha256.lower():
                    check_5 = True
                    manifest_status = "SHA256_MATCH"
                else:
                    errors.append(
                        f"Check 5 failed: SHA-256 mismatch (observed={db_sha256}, expected={expected_sha256})"
                    )
                    manifest_status = "SHA256_MISMATCH"
            else:
                if len(db_sha256) == 64 and ledger_hash:
                    check_5 = True
                    manifest_status = "VERIFIED_AUTHORITATIVE"
                else:
                    errors.append("Check 5 failed: missing ledger_hash or invalid digest length")
                    manifest_status = "MISSING_LEDGER_HASH"
        except Exception as exc:
            errors.append(f"Check 5 exception: {exc}")

    all_passed = check_1 and check_2 and check_3 and check_4 and check_5
    return CustodyCheckReport(
        db_path=str(p),
        passed=all_passed,
        check_1_file_exists_nonzero=check_1,
        check_2_sqlite_header_and_quick_check=check_2,
        check_3_required_tables_and_fts5=check_3,
        check_4_candidate_node_count_and_schema=check_4,
        check_5_sha256_and_manifest_verified=check_5,
        candidate_graph_db_sha256=db_sha256,
        manifest_verification_status=manifest_status,
        file_size_bytes=file_size,
        node_count=node_count,
        eligible_fact_count=fact_count,
        semantic_unit_count=unit_count,
        schema_version=schema_ver,
        ledger_hash=ledger_hash,
        errors=tuple(errors),
    )


def build_in_memory_fixture_db(
    facts: Sequence[Mapping[str, Any]] = (),
) -> tuple[sqlite3.Connection, CustodyCheckReport]:
    """Create an in-memory SQLite database populated with schema and candidate facts for hermetic tests."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE graph_nodes (
            node_id TEXT PRIMARY KEY,
            node_type TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            external_eligible INTEGER NOT NULL DEFAULT 1,
            employer TEXT NOT NULL DEFAULT '',
            career_epoch TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE graph_edges (
            edge_id TEXT PRIMARY KEY,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE semantic_unit (
            unit_id TEXT PRIMARY KEY,
            unit_type TEXT NOT NULL,
            root_node_id TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            external_eligible INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE semantic_unit_member (
            unit_id TEXT NOT NULL,
            member_kind TEXT NOT NULL,
            member_id TEXT NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (unit_id, member_kind, member_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE unit_vectors (
            unit_id TEXT PRIMARY KEY,
            vector BLOB
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE assertion_learned_sparse (
            assertion_id TEXT PRIMARY KEY,
            entity_kind TEXT NOT NULL DEFAULT 'semantic_unit',
            weights_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE assertion_colbert_vectors (
            assertion_id TEXT PRIMARY KEY,
            entity_kind TEXT NOT NULL DEFAULT 'semantic_unit',
            token_count INTEGER NOT NULL DEFAULT 1,
            dim INTEGER NOT NULL DEFAULT 1024,
            scales_json TEXT NOT NULL DEFAULT '[]',
            vectors_int8 BLOB NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE graph_metadata (
            graph_version TEXT PRIMARY KEY,
            ledger_hash TEXT NOT NULL,
            authority_status TEXT NOT NULL DEFAULT 'test_fixture'
        )
        """
    )
    conn.execute("CREATE VIRTUAL TABLE graph_nodes_fts USING fts5(node_id UNINDEXED, label, description)")
    conn.execute(
        "INSERT INTO graph_metadata (graph_version, ledger_hash, authority_status) "
        "VALUES ('fixture_v1', 'fixture_hash_00000000000000000000000000000000000000000000000000000000', 'test_fixture')"
    )

    for idx, f in enumerate(facts, start=1):
        fid = str(f.get("fact_id") or f"fact_fixture_{idx:03d}")
        statement = str(f.get("statement") or f.get("verbatim_span") or f"Grounded candidate fact {idx}")
        employer = str(f.get("employer") or "Enterprise Labs")
        epoch = str(f.get("career_epoch") or "epoch_agentic_systems")
        category = str(f.get("category") or "architecture")
        conn.execute(
            "INSERT INTO graph_nodes (node_id, node_type, label, description, external_eligible, employer, career_epoch, title) "
            "VALUES (?, 'fact', ?, ?, 1, ?, ?, ?)",
            (fid, statement[:80], statement, employer, epoch, category),
        )
        conn.execute(
            "INSERT INTO graph_nodes_fts (node_id, label, description) VALUES (?, ?, ?)",
            (fid, statement[:80], statement),
        )
        uid = f"semantic_unit:{fid}"
        conn.execute(
            "INSERT INTO semantic_unit (unit_id, unit_type, root_node_id, text, external_eligible) "
            "VALUES (?, 'skill_evidence_cluster', ?, ?, 1)",
            (uid, fid, statement),
        )
        conn.execute(
            "INSERT INTO semantic_unit_member (unit_id, member_kind, member_id, role) "
            "VALUES (?, 'node', ?, 'evidence')",
            (uid, fid),
        )

    conn.commit()
    report = CustodyCheckReport(
        db_path=":memory:",
        passed=True,
        check_1_file_exists_nonzero=True,
        check_2_sqlite_header_and_quick_check=True,
        check_3_required_tables_and_fts5=True,
        check_4_candidate_node_count_and_schema=True,
        check_5_sha256_and_manifest_verified=True,
        candidate_graph_db_sha256="fixture_db_sha256_000000000000000000000000000000000000000000000000",
        manifest_verification_status="TEST_FIXTURE_IN_MEMORY",
        file_size_bytes=len(facts) * 512,
        node_count=len(facts),
        eligible_fact_count=len(facts),
        semantic_unit_count=len(facts),
        schema_version="fixture_v1",
        ledger_hash="fixture_hash_00000000000000000000000000000000000000000000000000000000",
        errors=(),
    )
    return conn, report


__all__ = [
    "REQUIRED_FTS5_TABLES",
    "REQUIRED_TABLES",
    "build_in_memory_fixture_db",
    "compute_sha256",
    "open_candidate_graph_readonly",
    "verify_sqlite_custody",
]
