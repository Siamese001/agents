"""Lineage tracking and input manifest digest computation for skills graph.

Computes cryptographic digests over all upstream SSOT inputs
(master ledger, role episode bundles, candidate fact ledger, semantic contracts)
and enforces source authority boundaries on the generated SQLite projection.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    default_arsenal_ledger_path,
)
from apps_rg.fact_inventory.metric_outcome_materializer import (
    discover_role_episode_bundle_files,
)
from .constants import (
    C03_SQLITE_MATERIALIZER_CODE_VERSION,
    CANDIDATE_LEDGER_REL_PATH,
)

ALLOWLISTED_SOURCE_AUTHORITIES: frozenset[str] = frozenset(
    {
        "augmented_skills_graph",
        "candidate_skills_fact_ledger",
        "role_episode_bundles",
    }
)


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _canonical_json_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def compute_input_manifest(repo_root: Path | None = None) -> dict[str, Any]:
    """Compute itemized SHA256 manifest and overall digest across all graph inputs."""
    root = Path(repo_root or Path.cwd()).resolve()

    inputs: list[dict[str, str]] = []

    # 1. Master skills arsenal ledger
    arsenal_path = default_arsenal_ledger_path(root)
    if arsenal_path.is_file():
        inputs.append({
            "path": str(arsenal_path.relative_to(root)) if arsenal_path.is_relative_to(root) else str(arsenal_path),
            "role": "canonical_graph_ledger",
            "sha256": _file_sha256(arsenal_path),
        })

    # 2. Candidate skills fact ledger
    candidate_path = root / CANDIDATE_LEDGER_REL_PATH
    if candidate_path.is_file():
        inputs.append({
            "path": str(candidate_path.relative_to(root)) if candidate_path.is_relative_to(root) else str(candidate_path),
            "role": "candidate_fact_ledger",
            "sha256": _file_sha256(candidate_path),
        })

    # 3. All role episode bundle files
    for bundle_path in discover_role_episode_bundle_files(root):
        if bundle_path.is_file():
            inputs.append({
                "path": str(bundle_path.relative_to(root)) if bundle_path.is_relative_to(root) else str(bundle_path),
                "role": "role_episode_bundle",
                "sha256": _file_sha256(bundle_path),
            })

    # 4. Semantic contract (v1 or v2)
    contract_v2 = root / "src/apps_rg/fact_inventory/c03_graph_edge_semantic_contract.v2.json"
    contract_v1 = root / "src/apps_rg/fact_inventory/c03_graph_edge_semantic_contract.v1.json"
    contract_path = contract_v2 if contract_v2.is_file() else contract_v1
    if not contract_path.is_file():
        candidate_contract = root / "resume_graph_engine/src/apps_rg/fact_inventory/c03_graph_edge_semantic_contract.v1.json"
        if candidate_contract.is_file():
            contract_path = candidate_contract

    if contract_path.is_file():
        inputs.append({
            "path": str(contract_path.relative_to(root)) if contract_path.is_relative_to(root) else str(contract_path),
            "role": "edge_semantic_contract",
            "sha256": _file_sha256(contract_path),
        })

    # Sort inputs deterministically by path
    inputs.sort(key=lambda x: x["path"])

    manifest_body = {
        "materializer_code_version": C03_SQLITE_MATERIALIZER_CODE_VERSION,
        "inputs": inputs,
    }
    input_manifest_digest = _canonical_json_sha256(manifest_body)

    return {
        "input_manifest_digest": input_manifest_digest,
        "materializer_code_version": C03_SQLITE_MATERIALIZER_CODE_VERSION,
        "input_count": len(inputs),
        "inputs": inputs,
    }


def compute_input_manifest_digest(repo_root: Path | None = None) -> str:
    """Return the input_manifest_digest hex string."""
    manifest = compute_input_manifest(repo_root)
    return manifest["input_manifest_digest"]


def validate_projection_source_authorities(
    conn: sqlite3.Connection,
    *,
    allowlisted: frozenset[str] = ALLOWLISTED_SOURCE_AUTHORITIES,
) -> None:
    """Validate that every node and edge in projection carries an allowlisted source_authority."""
    unauthorized: set[str] = set()

    node_rows = conn.execute(
        "SELECT DISTINCT source_authority FROM graph_nodes WHERE source_authority IS NOT NULL"
    ).fetchall()
    for (auth,) in node_rows:
        if auth and auth not in allowlisted:
            unauthorized.add(str(auth))

    edge_rows = conn.execute(
        "SELECT DISTINCT source_authority FROM graph_edges WHERE source_authority IS NOT NULL"
    ).fetchall()
    for (auth,) in edge_rows:
        if auth and auth not in allowlisted:
            unauthorized.add(str(auth))

    if unauthorized:
        raise ValueError(
            f"unauthorized source_authority found in projection: {sorted(unauthorized)} "
            f"(allowlist={sorted(allowlisted)})"
        )


def get_git_commit(repo_root: Path | None = None) -> str:
    """Best-effort git commit SHA resolution with bounded timeout."""
    try:
        import subprocess

        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root or Path.cwd()),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "UNKNOWN"


def generate_build_run_id(timestamp: str, input_manifest_digest: str) -> str:
    """Generate structured run ID: run_<timestamp>_<short_digest>."""
    clean_ts = timestamp.replace("-", "").replace(":", "").replace("T", "_").replace("Z", "")
    short = input_manifest_digest[:8]
    return f"run_{clean_ts}_{short}"


def build_inputs_from_manifest(
    build_run_id: str,
    input_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build rows for the graph_build_inputs table from the input manifest."""
    rows: list[dict[str, Any]] = []
    for inp in input_manifest.get("inputs") or []:
        role = str(inp.get("role") or "").strip()
        path = str(inp.get("path") or "").strip()
        sha = str(inp.get("sha256") or "").strip()
        rows.append(
            {
                "build_run_id": build_run_id,
                "input_role": role,
                "artifact_relpath": path,
                "artifact_sha256": sha,
                "record_count": int(inp.get("record_count") or 0),
            }
        )
    return rows


__all__ = [
    "ALLOWLISTED_SOURCE_AUTHORITIES",
    "build_inputs_from_manifest",
    "compute_input_manifest",
    "compute_input_manifest_digest",
    "generate_build_run_id",
    "get_git_commit",
    "validate_projection_source_authorities",
]

