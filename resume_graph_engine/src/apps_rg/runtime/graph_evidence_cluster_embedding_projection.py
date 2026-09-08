"""Immutable cluster-vector projection and candidate-only C0.3 search."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_evidence_cluster_registry import (
    validate_registry,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

PROJECTION_SCHEMA_VERSION = "apps_rg.graph_evidence_cluster_embedding_projection.v1"


class GraphEvidenceClusterEmbeddingError(RuntimeError):
    """Raised when a cluster projection cannot preserve graph authority."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _vector_bytes(values: Sequence[float], dimension: int) -> bytes:
    if len(values) != dimension:
        raise GraphEvidenceClusterEmbeddingError(
            f"vector dimension mismatch: expected {dimension}, observed {len(values)}"
        )
    floats = [float(value) for value in values]
    if not all(math.isfinite(value) for value in floats):
        raise GraphEvidenceClusterEmbeddingError("vector values must be finite")
    norm = math.sqrt(math.fsum(value * value for value in floats))
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-5):
        raise GraphEvidenceClusterEmbeddingError(
            f"vector must be L2 normalized; observed norm={norm:.9f}"
        )
    return struct.pack(f"<{dimension}f", *floats)


def _decode_vector(blob: bytes, dimension: int) -> tuple[float, ...]:
    expected = dimension * 4
    if len(blob) != expected:
        raise GraphEvidenceClusterEmbeddingError(
            f"stored vector byte length mismatch: expected {expected}, observed {len(blob)}"
        )
    return struct.unpack(f"<{dimension}f", blob)


def _open_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def build_cluster_embedding_projection(
    output_path: Path | str,
    *,
    registry: Mapping[str, Any],
    vectors_by_cluster: Mapping[str, Sequence[float]],
    model_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Stage an immutable projection with one vector per active semantic cluster."""

    validate_registry(registry)
    path = Path(output_path)
    if path.exists():
        raise GraphEvidenceClusterEmbeddingError(
            f"immutable projection already exists: {path}"
        )
    dimension = int(model_manifest.get("dimension") or 0)
    if dimension <= 0:
        raise GraphEvidenceClusterEmbeddingError("model dimension must be positive")

    clusters = {
        str(row.get("cluster_id") or ""): row
        for row in registry.get("clusters") or []
        if isinstance(row, Mapping)
    }
    expected_ids = set(clusters)
    observed_ids = {str(value) for value in vectors_by_cluster}
    if expected_ids != observed_ids:
        raise GraphEvidenceClusterEmbeddingError(
            "cluster/vector parity mismatch: "
            f"missing={sorted(expected_ids - observed_ids)}, "
            f"orphaned={sorted(observed_ids - expected_ids)}"
        )

    encoded: dict[str, bytes] = {}
    vector_bindings: list[dict[str, str]] = []
    for cluster_id in sorted(expected_ids):
        cluster = clusters[cluster_id]
        blob = _vector_bytes(vectors_by_cluster[cluster_id], dimension)
        encoded[cluster_id] = blob
        vector_bindings.append(
            {
                "cluster_id": cluster_id,
                "canonical_embedding_text_sha256": canonical_sha256(
                    str(cluster.get("canonical_embedding_text") or "")
                ),
                "authority_envelope_sha256": str(
                    cluster.get("authority_envelope_sha256") or ""
                ),
                "vector_sha256": hashlib.sha256(blob).hexdigest(),
            }
        )

    generation_payload = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "registry_sha256": str(registry.get("registry_sha256") or ""),
        "graph_sha256": str(
            (registry.get("source_authority") or {}).get("canonical_graph_sha256") or ""
        ),
        "model_artifact_sha256": str(model_manifest.get("artifact_sha256") or ""),
        "model_id": str(model_manifest.get("model_id") or ""),
        "model_revision": str(model_manifest.get("revision") or ""),
        "dimension": dimension,
        "normalization": str(model_manifest.get("normalization") or ""),
        "vectors": vector_bindings,
    }
    generation_sha256 = canonical_sha256(generation_payload)
    metadata = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "generation_sha256": generation_sha256,
        "registry_sha256": generation_payload["registry_sha256"],
        "graph_sha256": generation_payload["graph_sha256"],
        "model_artifact_sha256": generation_payload["model_artifact_sha256"],
        "model_id": generation_payload["model_id"],
        "model_revision": generation_payload["model_revision"],
        "dimension": str(dimension),
        "normalization": generation_payload["normalization"],
        "vector_count": str(len(encoded)),
        "logical_retrieval_unit": "graph_evidence_cluster",
    }
    if any(not value for value in metadata.values()):
        raise GraphEvidenceClusterEmbeddingError("projection metadata is incomplete")

    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.staging-{os.getpid()}")
    if staging.exists():
        staging.unlink()
    try:
        conn = sqlite3.connect(staging)
        try:
            conn.execute("PRAGMA page_size=4096")
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute("PRAGMA locking_mode=EXCLUSIVE")
            conn.execute("PRAGMA auto_vacuum=NONE")
            conn.execute("PRAGMA application_id=1095911251")
            conn.execute("PRAGMA user_version=1")
            conn.execute(
                "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID"
            )
            conn.execute(
                "CREATE TABLE cluster_vectors ("
                "cluster_id TEXT PRIMARY KEY, "
                "cluster_kind TEXT NOT NULL, "
                "canonical_embedding_text_sha256 TEXT NOT NULL, "
                "authority_envelope_sha256 TEXT NOT NULL, "
                "allowed_sections_json TEXT NOT NULL, "
                "vector_sha256 TEXT NOT NULL, "
                "vector BLOB NOT NULL"
                ") WITHOUT ROWID"
            )
            conn.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                sorted(metadata.items()),
            )
            for cluster_id in sorted(clusters):
                cluster = clusters[cluster_id]
                blob = encoded[cluster_id]
                conn.execute(
                    "INSERT INTO cluster_vectors VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        cluster_id,
                        str(cluster.get("cluster_kind") or ""),
                        canonical_sha256(
                            str(cluster.get("canonical_embedding_text") or "")
                        ),
                        str(cluster.get("authority_envelope_sha256") or ""),
                        _canonical_json(
                            sorted(
                                str(value)
                                for value in cluster.get("allowed_sections") or []
                            )
                        ),
                        hashlib.sha256(blob).hexdigest(),
                        blob,
                    ),
                )
            conn.commit()
            conn.execute("VACUUM")
            conn.commit()
        finally:
            conn.close()
        os.replace(staging, path)
    except BaseException:
        if staging.exists():
            staging.unlink()
        raise

    return {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "generation_sha256": generation_sha256,
        "sqlite_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "vector_count": len(encoded),
        "dimension": dimension,
        "normalization": str(model_manifest.get("normalization") or ""),
    }


def validate_cluster_embedding_projection(
    path: Path | str,
    *,
    registry: Mapping[str, Any],
    model_manifest: Mapping[str, Any] | None = None,
) -> list[str]:
    """Validate row parity and every authority/vector digest without mutating SQLite."""

    issues: list[str] = []
    try:
        validate_registry(registry)
    except ValueError:
        return ["REGISTRY_INVALID"]
    db_path = Path(path)
    if not db_path.is_file():
        return ["PROJECTION_MISSING"]
    expected = {
        str(row.get("cluster_id") or ""): row
        for row in registry.get("clusters") or []
        if isinstance(row, Mapping)
    }
    try:
        with _open_read_only(db_path) as conn:
            metadata = dict(
                conn.execute("SELECT key, value FROM metadata ORDER BY key")
            )
            rows = conn.execute(
                "SELECT cluster_id, cluster_kind, canonical_embedding_text_sha256, "
                "authority_envelope_sha256, allowed_sections_json, vector_sha256, vector "
                "FROM cluster_vectors ORDER BY cluster_id"
            ).fetchall()
    except (sqlite3.Error, ValueError) as exc:
        return [f"PROJECTION_SQLITE_ERROR:{type(exc).__name__}"]

    required_metadata = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "logical_retrieval_unit": "graph_evidence_cluster",
        "registry_sha256": str(registry.get("registry_sha256") or ""),
        "graph_sha256": str(
            (registry.get("source_authority") or {}).get("canonical_graph_sha256") or ""
        ),
        "vector_count": str(len(expected)),
    }
    if model_manifest is not None:
        required_metadata |= {
            "model_artifact_sha256": str(model_manifest.get("artifact_sha256") or ""),
            "model_id": str(model_manifest.get("model_id") or ""),
            "model_revision": str(model_manifest.get("revision") or ""),
            "dimension": str(model_manifest.get("dimension") or ""),
            "normalization": str(model_manifest.get("normalization") or ""),
        }
    for key, value in required_metadata.items():
        if metadata.get(key) != value:
            issues.append(f"METADATA_MISMATCH:{key}")
    try:
        dimension = int(metadata.get("dimension") or 0)
    except ValueError:
        dimension = 0
        issues.append("DIMENSION_INVALID")
    if {str(row[0]) for row in rows} != set(expected):
        issues.append("CLUSTER_VECTOR_PARITY_MISMATCH")
    for (
        cluster_id,
        cluster_kind,
        text_digest,
        authority_digest,
        allowed_json,
        vector_digest,
        blob,
    ) in rows:
        cluster = expected.get(str(cluster_id))
        if cluster is None:
            continue
        if cluster_kind != cluster.get("cluster_kind"):
            issues.append(f"CLUSTER_KIND_MISMATCH:{cluster_id}")
        if text_digest != canonical_sha256(
            str(cluster.get("canonical_embedding_text") or "")
        ):
            issues.append(f"CANONICAL_TEXT_DIGEST_MISMATCH:{cluster_id}")
        if authority_digest != cluster.get("authority_envelope_sha256"):
            issues.append(f"AUTHORITY_ENVELOPE_DIGEST_MISMATCH:{cluster_id}")
        if allowed_json != _canonical_json(
            sorted(str(value) for value in cluster.get("allowed_sections") or [])
        ):
            issues.append(f"ALLOWED_SECTIONS_MISMATCH:{cluster_id}")
        if hashlib.sha256(blob).hexdigest() != vector_digest:
            issues.append(f"VECTOR_DIGEST_MISMATCH:{cluster_id}")
        try:
            _vector_bytes(_decode_vector(blob, dimension), dimension)
        except GraphEvidenceClusterEmbeddingError:
            issues.append(f"VECTOR_CONTRACT_MISMATCH:{cluster_id}")
    recomputed_generation = canonical_sha256(
        {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "registry_sha256": metadata.get("registry_sha256", ""),
            "graph_sha256": metadata.get("graph_sha256", ""),
            "model_artifact_sha256": metadata.get("model_artifact_sha256", ""),
            "model_id": metadata.get("model_id", ""),
            "model_revision": metadata.get("model_revision", ""),
            "dimension": dimension,
            "normalization": metadata.get("normalization", ""),
            "vectors": [
                {
                    "cluster_id": str(row[0]),
                    "canonical_embedding_text_sha256": str(row[2]),
                    "authority_envelope_sha256": str(row[3]),
                    "vector_sha256": str(row[5]),
                }
                for row in rows
            ],
        }
    )
    if metadata.get("generation_sha256") != recomputed_generation:
        issues.append("GENERATION_DIGEST_MISMATCH")
    return sorted(set(issues))


class GraphEvidenceClusterEmbeddingIndex:
    """Read-only exact normalized-dot-product cluster candidate index."""

    def __init__(
        self,
        path: Path | str,
        *,
        expected_registry_sha256: str,
        expected_model_artifact_sha256: str | None = None,
    ) -> None:
        self.path = Path(path)
        self._conn = _open_read_only(self.path)
        self.metadata = dict(
            self._conn.execute("SELECT key, value FROM metadata ORDER BY key")
        )
        if self.metadata.get("schema_version") != PROJECTION_SCHEMA_VERSION:
            self.close()
            raise GraphEvidenceClusterEmbeddingError("projection schema mismatch")
        if self.metadata.get("logical_retrieval_unit") != "graph_evidence_cluster":
            self.close()
            raise GraphEvidenceClusterEmbeddingError("logical retrieval unit mismatch")
        if self.metadata.get("registry_sha256") != expected_registry_sha256:
            self.close()
            raise GraphEvidenceClusterEmbeddingError("registry digest mismatch")
        if (
            expected_model_artifact_sha256 is not None
            and self.metadata.get("model_artifact_sha256")
            != expected_model_artifact_sha256
        ):
            self.close()
            raise GraphEvidenceClusterEmbeddingError("model artifact digest mismatch")
        self.dimension = int(self.metadata["dimension"])
        self.vector_count = int(self.metadata["vector_count"])
        if (
            self.dimension <= 0
            or self.vector_count < 2
            or self.metadata.get("normalization") != "l2"
        ):
            self.close()
            raise GraphEvidenceClusterEmbeddingError(
                "projection shape contract mismatch"
            )

    def __enter__(self) -> GraphEvidenceClusterEmbeddingIndex:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def close(self) -> None:
        conn = getattr(self, "_conn", None)
        if conn is not None:
            conn.close()
            self._conn = None

    def query(
        self,
        query_vector: Sequence[float],
        *,
        k: int,
        section_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self._conn is None:
            raise GraphEvidenceClusterEmbeddingError("embedding index is closed")
        if k < 1 or k >= self.vector_count:
            raise GraphEvidenceClusterEmbeddingError(
                f"top-k must be between 1 and {self.vector_count - 1}"
            )
        query = _decode_vector(
            _vector_bytes(query_vector, self.dimension), self.dimension
        )
        rows = self._conn.execute(
            "SELECT cluster_id, allowed_sections_json, vector "
            "FROM cluster_vectors ORDER BY cluster_id"
        ).fetchall()
        ranked: list[tuple[float, str]] = []
        for cluster_id, allowed_json, blob in rows:
            if section_id and section_id not in json.loads(allowed_json):
                continue
            vector = _decode_vector(blob, self.dimension)
            score = math.fsum(
                left * right for left, right in zip(query, vector, strict=True)
            )
            ranked.append((score, str(cluster_id)))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            {"cluster_id": cluster_id, "similarity": score}
            for score, cluster_id in ranked[:k]
        ]


def rehydrate_cluster_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    registry: Mapping[str, Any],
    graph_payload: Mapping[str, Any],
    section_id: str,
) -> list[dict[str, Any]]:
    """Resolve candidate-only results through current cluster and graph authority."""

    validate_registry(registry, graph=graph_payload)
    if (registry.get("source_authority") or {}).get(
        "canonical_graph_sha256"
    ) != canonical_sha256(graph_payload):
        raise GraphEvidenceClusterEmbeddingError("stale graph digest")
    clusters = {
        str(row.get("cluster_id") or ""): row
        for row in registry.get("clusters") or []
        if isinstance(row, Mapping)
    }
    hydrated: list[dict[str, Any]] = []
    for candidate in candidates:
        if set(candidate) != {"cluster_id", "similarity"}:
            raise GraphEvidenceClusterEmbeddingError(
                "candidate payload exposes forbidden fields"
            )
        cluster_id = str(candidate.get("cluster_id") or "")
        cluster = clusters.get(cluster_id)
        if cluster is None:
            raise GraphEvidenceClusterEmbeddingError(
                f"orphan cluster candidate: {cluster_id}"
            )
        if cluster.get("activation_status") != "ACTIVE_CONFIRMED":
            raise GraphEvidenceClusterEmbeddingError(
                f"inactive cluster candidate: {cluster_id}"
            )
        if section_id not in cluster.get("allowed_sections", []):
            raise GraphEvidenceClusterEmbeddingError(
                f"cluster not allowed in section {section_id}: {cluster_id}"
            )
        row = dict(cluster)
        row["similarity"] = float(candidate["similarity"])
        hydrated.append(row)
    return hydrated


__all__ = [
    "GraphEvidenceClusterEmbeddingError",
    "GraphEvidenceClusterEmbeddingIndex",
    "PROJECTION_SCHEMA_VERSION",
    "build_cluster_embedding_projection",
    "rehydrate_cluster_candidates",
    "validate_cluster_embedding_projection",
]
