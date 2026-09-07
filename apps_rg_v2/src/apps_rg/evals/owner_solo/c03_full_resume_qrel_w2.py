"""W2 sealed full-universe rankings for the owner-solo full-resume QREL lane.

W2 consumes the separate W1C projection.  It creates one BGE-M3 query vector
per frozen target (the exact job description followed by its brief), filters
the 54-vector projection by résumé section, and freezes every permitted
candidate's rank.  Rankings and similarity scores remain private under
``.runtime``; W2 creates no human grade, QREL, metric, activation, or release
authority.
"""

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

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    ranking_identity_sha256,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_scope import (
    EXPECTED_SECTION_IDS,
    RESULT_LABEL,
    SCOPE_PATH,
    load_full_resume_scope,
    validate_full_resume_scope,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w1c import (
    PROJECTION_SCHEMA_VERSION,
    RECEIPT_STATUS as W1C_RECEIPT_STATUS,
    RUNTIME_DIR as W1C_RUNTIME_DIR,
    validate_combined_projection,
    validate_combined_registry,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (
    W6_RECEIPT_PATH,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)
from apps_rg.fact_inventory.c03_skill_embedding_builder import (
    MODEL_DIMENSION,
    MODEL_ID,
    build_local_model_manifest,
    encode_bge_m3,
)


QUERY_MANIFEST_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_query_manifest.v1"
QUERY_MANIFEST_STATUS = "FROZEN_UNLABELED_OWNER_SOLO_PROVISIONAL"
RANKING_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_frozen_rankings.v1"
RANKING_STATUS = "FROZEN_OWNER_SOLO_PROVISIONAL_UNLABELED_RANKINGS"
RECEIPT_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_qrel_w2_receipt.v1"
RECEIPT_STATUS = "W2_FROZEN_RANKINGS_READY_FOR_BLINDED_PACKET"
RUNTIME_DIR = Path(".runtime/c03-owner-solo-qrel/w2")

_EXPECTED_MODEL = {
    "model_id": MODEL_ID,
    "revision": "5617a9f61b028005a4858fdac845db406aefb181",
    "artifact_sha256": (
        "38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263"
    ),
    "dimension": MODEL_DIMENSION,
    "normalization": "l2",
}
_EXPECTED_SECTION_CANDIDATE_COUNTS = {
    "headline": 8,
    "executive_summary": 12,
    "competencies": 22,
    "unify_bullets": 19,
    "unify_narrative": 3,
    "ibm_bullets": 8,
    "ibm_narrative": 8,
    "ey_bullets": 2,
    "ey_narrative": 2,
    "insurtech_bullets": 8,
    "insurtech_narrative": 8,
}


class FullResumeQrelW2Error(ValueError):
    """Raised when W2 cannot freeze a complete, source-bound ranking."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FullResumeQrelW2Error(f"JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise FullResumeQrelW2Error(f"JSON object required: {path}")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FullResumeQrelW2Error(f"File unavailable: {path}") from exc
    return digest.hexdigest()


def _repository_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise FullResumeQrelW2Error(f"Path escapes repository root: {path}") from exc


def _resolve_repository_path(root: Path, value: Path | str) -> Path:
    candidate = Path(value)
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise FullResumeQrelW2Error(f"Path escapes repository root: {value}") from exc
    return path


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    data = rendered.encode("utf-8")
    if path.exists():
        if path.read_bytes() != data:
            raise FullResumeQrelW2Error(f"Immutable artifact collision: {path}")
        return hashlib.sha256(data).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.staging-{os.getpid()}")
    try:
        staging.write_bytes(data)
        os.replace(staging, path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return hashlib.sha256(data).hexdigest()


def _vector_bytes(values: Sequence[float], dimension: int) -> bytes:
    if len(values) != dimension:
        raise FullResumeQrelW2Error(
            f"vector dimension mismatch: expected {dimension}, observed {len(values)}"
        )
    vector = [float(value) for value in values]
    if not all(math.isfinite(value) for value in vector):
        raise FullResumeQrelW2Error("vector values must be finite")
    norm = math.sqrt(math.fsum(value * value for value in vector))
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-5):
        raise FullResumeQrelW2Error(
            f"vector must be L2 normalized; observed norm={norm:.9f}"
        )
    return struct.pack(f"<{dimension}f", *vector)


def _decode_vector(blob: bytes, dimension: int) -> tuple[float, ...]:
    expected_bytes = dimension * 4
    if len(blob) != expected_bytes:
        raise FullResumeQrelW2Error(
            "stored vector byte length mismatch: "
            f"expected {expected_bytes}, observed {len(blob)}"
        )
    return struct.unpack(f"<{dimension}f", blob)


def _open_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def _validate_pinned_model(model: Mapping[str, Any]) -> None:
    mismatches = [
        field for field, expected in _EXPECTED_MODEL.items() if model.get(field) != expected
    ]
    if mismatches:
        raise FullResumeQrelW2Error(
            "local BGE-M3 model does not match the frozen W2 binding: "
            + ", ".join(mismatches)
        )


def _query_text(root: Path, query: Mapping[str, Any]) -> str:
    return (
        (root / str(query["jd_path"])).read_text(encoding="utf-8").strip()
        + "\n\n"
        + (root / str(query["brief_path"])).read_text(encoding="utf-8").strip()
    )


def build_w2_query_manifest(repo_root: Path | str) -> dict[str, Any]:
    """Freeze W2's exact target-query construction without storing raw text."""

    root = Path(repo_root).resolve()
    scope = load_full_resume_scope(root)
    issues = validate_full_resume_scope(scope, root)
    if issues:
        raise FullResumeQrelW2Error(f"W0 scope invalid: {issues}")
    queries: list[dict[str, Any]] = []
    for target in scope["targets"]:
        query = dict(target)
        query["query_text_sha256"] = hashlib.sha256(
            _query_text(root, query).encode("utf-8")
        ).hexdigest()
        queries.append(query)
    payload: dict[str, Any] = {
        "schema_version": QUERY_MANIFEST_SCHEMA_VERSION,
        "status": QUERY_MANIFEST_STATUS,
        "result_label": RESULT_LABEL,
        "query_construction": {
            "exact_text": "utf8(jd).strip() + double_newline + utf8(brief).strip()",
            "one_bge_m3_query_vector_per_target": True,
            "section_id_applies_candidate_universe_filter_only": True,
        },
        "source_authority": {
            "scope_path": SCOPE_PATH.as_posix(),
            "scope_manifest_sha256": scope["scope_manifest_sha256"],
        },
        "section_ids": list(EXPECTED_SECTION_IDS),
        "queries": queries,
        "label_authority": {
            "human_labels_present": False,
            "synthetic_labels_created": False,
            "human_review_required": True,
        },
    }
    payload["query_manifest_sha256"] = canonical_sha256(payload)
    return payload


def validate_w2_query_manifest(
    payload: Mapping[str, Any], repo_root: Path | str
) -> list[str]:
    """Fail closed on any source or construction drift in the W2 query manifest."""

    root = Path(repo_root).resolve()
    issues: list[str] = []
    if (
        payload.get("schema_version") != QUERY_MANIFEST_SCHEMA_VERSION
        or payload.get("status") != QUERY_MANIFEST_STATUS
        or payload.get("result_label") != RESULT_LABEL
    ):
        issues.append("SCHEMA_OR_STATUS")
    unsigned = dict(payload)
    digest = unsigned.pop("query_manifest_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(unsigned) != digest:
        issues.append("QUERY_MANIFEST_DIGEST")
    try:
        expected = build_w2_query_manifest(root)
    except FullResumeQrelW2Error:
        return sorted(set(issues + ["W0_SCOPE"]))
    if payload != expected:
        issues.append("QUERY_SOURCE_OR_CONSTRUCTION")
    return sorted(set(issues))


def write_w2_query_manifest(repo_root: Path | str) -> tuple[Path, dict[str, Any]]:
    """Write the immutable source-bound query manifest under ignored runtime."""

    root = Path(repo_root).resolve()
    payload = build_w2_query_manifest(root)
    issues = validate_w2_query_manifest(payload, root)
    if issues:
        raise FullResumeQrelW2Error(f"W2 query manifest invalid: {issues}")
    path = root / RUNTIME_DIR / f"query_manifest.{payload['query_manifest_sha256']}.json"
    _write_immutable_json(path, payload)
    return path, payload


def _resolve_w1c_receipt(root: Path, supplied_path: Path | str | None) -> Path:
    if supplied_path is not None:
        path = _resolve_repository_path(root, supplied_path)
        if not path.is_file():
            raise FullResumeQrelW2Error(f"W1C receipt is missing: {path}")
        return path
    candidates = sorted((root / W1C_RUNTIME_DIR).glob("w1c_combined_projection_receipt.*.json"))
    if len(candidates) != 1:
        raise FullResumeQrelW2Error(
            "exactly one W1C receipt is required; pass --w1c-receipt explicitly"
        )
    return candidates[0]


def _base_projection_path(root: Path) -> Path:
    receipt = _read_json(root / W6_RECEIPT_PATH)
    generation = receipt.get("generation") or {}
    manifest_path = _resolve_repository_path(
        root, str(generation.get("manifest_path") or "")
    )
    manifest = _read_json(manifest_path)
    projection = manifest.get("projection") or {}
    path = _resolve_repository_path(root, str(projection.get("path") or ""))
    if not path.is_file():
        raise FullResumeQrelW2Error("authoritative W6 projection is missing")
    return path


def _load_w1c_context(
    root: Path,
    *,
    w1c_receipt_path: Path | str | None,
    model_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    path = _resolve_w1c_receipt(root, w1c_receipt_path)
    receipt = _read_json(path)
    unsigned = dict(receipt)
    receipt_digest = unsigned.pop("receipt_sha256", None)
    if not isinstance(receipt_digest, str) or canonical_sha256(unsigned) != receipt_digest:
        raise FullResumeQrelW2Error("W1C receipt digest is invalid")
    if (
        receipt.get("status") != W1C_RECEIPT_STATUS
        or receipt.get("result_label") != RESULT_LABEL
    ):
        raise FullResumeQrelW2Error("W1C receipt status is invalid")
    guards = receipt.get("scope_guards") or {}
    if any(
        guards.get(field) is not False
        for field in (
            "human_qrels_created",
            "rankings_frozen",
            "metrics_computable",
            "authoritative_release_qualification_satisfied",
            "activation_manifest_created",
            "production_promotion_authorized",
        )
    ):
        raise FullResumeQrelW2Error("W1C receipt scope boundary drifted")

    combined_record = receipt.get("combined_registry") or {}
    combined_path = _resolve_repository_path(root, str(combined_record.get("path") or ""))
    if (
        not combined_path.is_file()
        or _file_sha256(combined_path) != combined_record.get("file_sha256")
    ):
        raise FullResumeQrelW2Error("W1C combined registry file binding failed")
    combined = _read_json(combined_path)
    combined_issues = validate_combined_registry(combined, root)
    if combined_issues:
        raise FullResumeQrelW2Error(
            f"W1C combined registry invalid: {combined_issues}"
        )
    if combined.get("combined_registry_sha256") != combined_record.get(
        "combined_registry_sha256"
    ):
        raise FullResumeQrelW2Error("W1C combined registry digest binding failed")

    projection_record = receipt.get("projection") or {}
    projection_path = _resolve_repository_path(
        root, str(projection_record.get("path") or "")
    )
    if (
        not projection_path.is_file()
        or _file_sha256(projection_path) != projection_record.get("file_sha256")
    ):
        raise FullResumeQrelW2Error("W1C projection file binding failed")
    projection_issues = validate_combined_projection(
        projection_path,
        combined_registry=combined,
        base_projection_path=_base_projection_path(root),
        model_manifest=model_manifest,
    )
    if projection_issues:
        raise FullResumeQrelW2Error(f"W1C projection invalid: {projection_issues}")
    if projection_record.get("generation_sha256") != _projection_generation_sha256(
        projection_path
    ):
        raise FullResumeQrelW2Error("W1C projection generation binding failed")
    return {
        "receipt_path": path,
        "receipt": receipt,
        "combined_path": combined_path,
        "combined": combined,
        "projection_path": projection_path,
        "projection": projection_record,
    }


def _projection_generation_sha256(path: Path) -> str:
    try:
        with _open_read_only(path) as conn:
            metadata = dict(
                conn.execute("SELECT key, value FROM metadata ORDER BY key")
            )
    except sqlite3.Error as exc:
        raise FullResumeQrelW2Error("projection cannot be read") from exc
    if metadata.get("schema_version") != PROJECTION_SCHEMA_VERSION:
        raise FullResumeQrelW2Error("projection schema is not W1C")
    value = str(metadata.get("generation_sha256") or "")
    if len(value) != 64:
        raise FullResumeQrelW2Error("projection generation digest is absent")
    return value


def _projection_vectors(
    projection_path: Path,
    *,
    combined_registry: Mapping[str, Any],
    dimension: int,
) -> dict[str, tuple[float, ...]]:
    try:
        with _open_read_only(projection_path) as conn:
            rows = conn.execute(
                "SELECT cluster_id, vector FROM cluster_vectors ORDER BY cluster_id"
            ).fetchall()
    except sqlite3.Error as exc:
        raise FullResumeQrelW2Error("projection vectors cannot be read") from exc
    expected_ids = {
        str(row.get("cluster_id") or "")
        for row in combined_registry.get("clusters") or []
        if isinstance(row, Mapping)
    }
    vectors = {str(cluster_id): _decode_vector(blob, dimension) for cluster_id, blob in rows}
    if set(vectors) != expected_ids or len(vectors) != 54:
        raise FullResumeQrelW2Error("projection vector/combined registry parity failed")
    for vector in vectors.values():
        _vector_bytes(vector, dimension)
    return vectors


def _rank_full_section_universe(
    query_vector: Sequence[float],
    *,
    candidate_ids: Sequence[str],
    cluster_vectors: Mapping[str, Sequence[float]],
) -> list[tuple[str, float]]:
    ranked = [
        (
            cluster_id,
            math.fsum(
                left * right
                for left, right in zip(
                    query_vector, cluster_vectors[cluster_id], strict=True
                )
            ),
        )
        for cluster_id in candidate_ids
    ]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked


def build_frozen_ranking_artifact(
    *,
    repo_root: Path | str,
    query_manifest: Mapping[str, Any],
    w1c_context: Mapping[str, Any],
    model_manifest: Mapping[str, Any],
    rankings_by_pair: Mapping[str, Sequence[tuple[str, float]]],
    query_vector_sha256: Mapping[str, str],
    runtime_proof: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a sealed W2 ranking artifact from fully enumerated candidates."""

    root = Path(repo_root).resolve()
    combined = w1c_context["combined"]
    expected_pairs = [
        f"{query['query_id']}|{section_id}"
        for query in sorted(query_manifest["queries"], key=lambda row: str(row["query_id"]))
        for section_id in EXPECTED_SECTION_IDS
    ]
    if set(rankings_by_pair) != set(expected_pairs):
        raise FullResumeQrelW2Error("W2 ranking pair denominator failed")
    section_ids = combined["section_candidate_cluster_ids"]
    ranking_rows: list[dict[str, Any]] = []
    identity_bindings: dict[str, list[str]] = {}
    for pair in expected_pairs:
        query_id, section_id = pair.split("|", 1)
        candidates = list(rankings_by_pair[pair])
        expected_ids = list(section_ids[section_id])
        candidate_ids = [str(cluster_id) for cluster_id, _ in candidates]
        if len(candidates) != len(expected_ids) or set(candidate_ids) != set(expected_ids):
            raise FullResumeQrelW2Error(f"W2 finite candidate universe failed: {pair}")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise FullResumeQrelW2Error(f"W2 duplicate candidate: {pair}")
        if any(not math.isfinite(float(score)) for _, score in candidates):
            raise FullResumeQrelW2Error(f"W2 non-finite similarity: {pair}")
        identity_bindings[pair] = candidate_ids
        ranking_rows.append(
            {
                "query_id": query_id,
                "section_id": section_id,
                "candidate_count": len(candidates),
                "candidates": [
                    {
                        "cluster_id": cluster_id,
                        "frozen_rank": rank,
                        "similarity": float(score),
                    }
                    for rank, (cluster_id, score) in enumerate(candidates, start=1)
                ],
            }
        )
    if set(query_vector_sha256) != {
        str(query["query_id"]) for query in query_manifest["queries"]
    } or any(len(str(value)) != 64 for value in query_vector_sha256.values()):
        raise FullResumeQrelW2Error("W2 query-vector digest binding failed")
    source = combined["source_authority"]
    receipt = w1c_context["receipt"]
    receipt_path = w1c_context["receipt_path"]
    payload: dict[str, Any] = {
        "schema_version": RANKING_SCHEMA_VERSION,
        "status": RANKING_STATUS,
        "result_label": RESULT_LABEL,
        "source_authority": {
            "scope_manifest_sha256": source["scope_manifest_sha256"],
            "query_manifest_sha256": query_manifest["query_manifest_sha256"],
            "w1c_receipt_path": _repository_path(receipt_path, root),
            "w1c_receipt_sha256": receipt["receipt_sha256"],
            "combined_registry_sha256": combined["combined_registry_sha256"],
            "projection_generation_sha256": w1c_context["projection"][
                "generation_sha256"
            ],
            "projection_file_sha256": w1c_context["projection"]["file_sha256"],
            "model_id": model_manifest["model_id"],
            "model_revision": model_manifest["revision"],
            "model_artifact_sha256": model_manifest["artifact_sha256"],
        },
        "query_vector_sha256_by_query": dict(sorted(query_vector_sha256.items())),
        "ranking_identity_sha256": ranking_identity_sha256(identity_bindings),
        "query_section_count": len(ranking_rows),
        "candidate_judgment_count": sum(
            int(row["candidate_count"]) for row in ranking_rows
        ),
        "full_finite_candidate_universe_required": True,
        "partial_top_k_judging_forbidden": True,
        "sealed_mapping": {
            "rank_or_score_distribution_forbidden": True,
            "reviewer_visible": False,
            "similarity_is_claim_authority": False,
        },
        "runtime_proof": dict(runtime_proof),
        "rankings": ranking_rows,
        "scope_guards": {
            "human_qrels_created": False,
            "metrics_computable": False,
            "authoritative_release_qualification_satisfied": False,
            "activation_manifest_created": False,
            "production_promotion_authorized": False,
        },
    }
    payload["ranking_artifact_sha256"] = canonical_sha256(payload)
    return payload


def validate_frozen_ranking_artifact(
    payload: Mapping[str, Any],
    *,
    query_manifest: Mapping[str, Any],
    w1c_context: Mapping[str, Any],
    model_manifest: Mapping[str, Any],
    repo_root: Path | str,
) -> list[str]:
    """Validate structural conservation and every immutable W2 source binding."""

    root = Path(repo_root).resolve()
    issues: list[str] = []
    if (
        payload.get("schema_version") != RANKING_SCHEMA_VERSION
        or payload.get("status") != RANKING_STATUS
        or payload.get("result_label") != RESULT_LABEL
    ):
        issues.append("SCHEMA_OR_STATUS")
    unsigned = dict(payload)
    digest = unsigned.pop("ranking_artifact_sha256", None)
    if not isinstance(digest, str) or canonical_sha256(unsigned) != digest:
        issues.append("RANKING_ARTIFACT_DIGEST")

    combined = w1c_context["combined"]
    expected_source = {
        "scope_manifest_sha256": combined["source_authority"]["scope_manifest_sha256"],
        "query_manifest_sha256": query_manifest["query_manifest_sha256"],
        "w1c_receipt_path": _repository_path(w1c_context["receipt_path"], root),
        "w1c_receipt_sha256": w1c_context["receipt"]["receipt_sha256"],
        "combined_registry_sha256": combined["combined_registry_sha256"],
        "projection_generation_sha256": w1c_context["projection"][
            "generation_sha256"
        ],
        "projection_file_sha256": w1c_context["projection"]["file_sha256"],
        "model_id": model_manifest["model_id"],
        "model_revision": model_manifest["revision"],
        "model_artifact_sha256": model_manifest["artifact_sha256"],
    }
    if (payload.get("source_authority") or {}) != expected_source:
        issues.append("SOURCE_AUTHORITY")
    vectors = payload.get("query_vector_sha256_by_query") or {}
    expected_query_ids = {str(query["query_id"]) for query in query_manifest["queries"]}
    if set(vectors) != expected_query_ids or any(
        len(str(value)) != 64 for value in vectors.values()
    ):
        issues.append("QUERY_VECTOR_BINDINGS")

    expected_by_pair = {
        f"{query['query_id']}|{section_id}": list(
            combined["section_candidate_cluster_ids"][section_id]
        )
        for query in query_manifest["queries"]
        for section_id in EXPECTED_SECTION_IDS
    }
    rankings = payload.get("rankings")
    observed_identity: dict[str, list[str]] = {}
    candidate_count = 0
    if not isinstance(rankings, list) or len(rankings) != len(expected_by_pair):
        issues.append("RANKING_PAIR_COUNT")
    else:
        for row in rankings:
            if not isinstance(row, Mapping):
                issues.append("RANKING_ROW_SHAPE")
                continue
            pair = f"{row.get('query_id')}|{row.get('section_id')}"
            candidates = row.get("candidates")
            expected_ids = expected_by_pair.get(pair)
            if pair in observed_identity or expected_ids is None:
                issues.append("RANKING_PAIR_IDENTITY")
                continue
            if not isinstance(candidates, list) or row.get("candidate_count") != len(
                expected_ids
            ):
                issues.append(f"CANDIDATE_COUNT:{pair}")
                continue
            cluster_ids = [str(item.get("cluster_id") or "") for item in candidates if isinstance(item, Mapping)]
            ranks = [item.get("frozen_rank") for item in candidates if isinstance(item, Mapping)]
            scores = [item.get("similarity") for item in candidates if isinstance(item, Mapping)]
            if (
                len(cluster_ids) != len(candidates)
                or set(cluster_ids) != set(expected_ids)
                or len(cluster_ids) != len(set(cluster_ids))
            ):
                issues.append(f"FINITE_CANDIDATE_UNIVERSE:{pair}")
            if ranks != list(range(1, len(candidates) + 1)):
                issues.append(f"RANK_CONSERVATION:{pair}")
            if any(
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
                for score in scores
            ):
                issues.append(f"SIMILARITY_CONTRACT:{pair}")
            observed_identity[pair] = cluster_ids
            candidate_count += len(candidates)
    if payload.get("ranking_identity_sha256") != ranking_identity_sha256(observed_identity):
        issues.append("RANKING_IDENTITY")
    if payload.get("query_section_count") != 66 or payload.get(
        "candidate_judgment_count"
    ) != 600 or candidate_count != 600:
        issues.append("DENOMINATOR")
    if (
        payload.get("full_finite_candidate_universe_required") is not True
        or payload.get("partial_top_k_judging_forbidden") is not True
    ):
        issues.append("FULL_UNIVERSE_POLICY")
    if payload.get("sealed_mapping") != {
        "rank_or_score_distribution_forbidden": True,
        "reviewer_visible": False,
        "similarity_is_claim_authority": False,
    }:
        issues.append("SEALED_MAPPING")
    runtime = payload.get("runtime_proof") or {}
    if (
        runtime.get("fallback_used") is not False
        or runtime.get("vector_count") != 6
        or runtime.get("dimension") != MODEL_DIMENSION
    ):
        issues.append("RUNTIME_PROOF")
    if payload.get("scope_guards") != {
        "human_qrels_created": False,
        "metrics_computable": False,
        "authoritative_release_qualification_satisfied": False,
        "activation_manifest_created": False,
        "production_promotion_authorized": False,
    }:
        issues.append("SCOPE_GUARDS")
    return sorted(set(issues))


def _assert_deterministic_existing_output(root: Path, payload: Mapping[str, Any]) -> None:
    """Reject a second, different ranking for the same frozen inputs."""

    source = payload["source_authority"]
    for path in sorted((root / RUNTIME_DIR).glob("frozen_rankings.*.json")):
        existing = _read_json(path)
        if (existing.get("source_authority") or {}) == source and existing.get(
            "ranking_artifact_sha256"
        ) != payload.get("ranking_artifact_sha256"):
            raise FullResumeQrelW2Error(
                "non-deterministic W2 ranking output for identical frozen inputs"
            )


def materialize_w2_rankings(
    repo_root: Path | str,
    *,
    model_path: Path | str,
    device: str,
    w1c_receipt_path: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Generate and freeze all 66 private W2 full-universe rankings."""

    root = Path(repo_root).resolve()
    model = build_local_model_manifest(model_path)
    _validate_pinned_model(model)
    w1c = _load_w1c_context(
        root,
        w1c_receipt_path=w1c_receipt_path,
        model_manifest=model,
    )
    query_manifest_path, query_manifest = write_w2_query_manifest(root)
    query_issues = validate_w2_query_manifest(query_manifest, root)
    if query_issues:
        raise FullResumeQrelW2Error(f"W2 query manifest invalid: {query_issues}")
    projection_vectors = _projection_vectors(
        w1c["projection_path"],
        combined_registry=w1c["combined"],
        dimension=int(model["dimension"]),
    )
    query_texts = {
        str(query["query_id"]): _query_text(root, query)
        for query in query_manifest["queries"]
    }
    query_ids = sorted(query_texts)
    runtime_proof, query_vectors = encode_bge_m3(
        [query_texts[query_id] for query_id in query_ids],
        model_path=model_path,
        device=device,
        batch_size=6,
    )
    if runtime_proof.get("fallback_used") is not False or runtime_proof.get(
        "vector_count"
    ) != len(query_ids):
        raise FullResumeQrelW2Error("BGE-M3 W2 runtime proof is incomplete")
    vectors_by_query = dict(zip(query_ids, query_vectors, strict=True))
    query_vector_sha256 = {
        query_id: hashlib.sha256(
            _vector_bytes(vectors_by_query[query_id], int(model["dimension"]))
        ).hexdigest()
        for query_id in query_ids
    }
    rankings_by_pair: dict[str, list[tuple[str, float]]] = {}
    section_ids = w1c["combined"]["section_candidate_cluster_ids"]
    for query_id in query_ids:
        for section_id in EXPECTED_SECTION_IDS:
            pair = f"{query_id}|{section_id}"
            rankings_by_pair[pair] = _rank_full_section_universe(
                vectors_by_query[query_id],
                candidate_ids=section_ids[section_id],
                cluster_vectors=projection_vectors,
            )
    ranking = build_frozen_ranking_artifact(
        repo_root=root,
        query_manifest=query_manifest,
        w1c_context=w1c,
        model_manifest=model,
        rankings_by_pair=rankings_by_pair,
        query_vector_sha256=query_vector_sha256,
        runtime_proof=runtime_proof,
    )
    ranking_issues = validate_frozen_ranking_artifact(
        ranking,
        query_manifest=query_manifest,
        w1c_context=w1c,
        model_manifest=model,
        repo_root=root,
    )
    if ranking_issues:
        raise FullResumeQrelW2Error(f"W2 ranking invalid: {ranking_issues}")
    _assert_deterministic_existing_output(root, ranking)
    ranking_path = root / RUNTIME_DIR / (
        f"frozen_rankings.{ranking['ranking_artifact_sha256']}.json"
    )
    _write_immutable_json(ranking_path, ranking)

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": RECEIPT_STATUS,
        "result_label": RESULT_LABEL,
        "query_manifest": {
            "path": _repository_path(query_manifest_path, root),
            "file_sha256": _file_sha256(query_manifest_path),
            "query_manifest_sha256": query_manifest["query_manifest_sha256"],
        },
        "rankings": {
            "path": _repository_path(ranking_path, root),
            "file_sha256": _file_sha256(ranking_path),
            "ranking_artifact_sha256": ranking["ranking_artifact_sha256"],
            "ranking_identity_sha256": ranking["ranking_identity_sha256"],
            "query_section_count": ranking["query_section_count"],
            "candidate_judgment_count": ranking["candidate_judgment_count"],
        },
        "coverage": {
            "query_count": 6,
            "section_count": 11,
            "query_section_case_count": 66,
            "candidate_count_by_section": _EXPECTED_SECTION_CANDIDATE_COUNTS,
            "candidate_judgment_count": 600,
        },
        "runtime_proof": dict(runtime_proof),
        "scope_guards": dict(ranking["scope_guards"]),
        "reviewer_visibility": {
            "ranks_or_scores_distributed": False,
            "sealed_mapping_visible_to_reviewer": False,
        },
        "next_action": "W3_BUILD_BLINDED_OWNER_REVIEW_PACKET",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    receipt_path = root / RUNTIME_DIR / f"w2_ranking_receipt.{receipt['receipt_sha256']}.json"
    _write_immutable_json(receipt_path, receipt)
    return receipt, {
        "query_manifest": query_manifest_path,
        "rankings": ranking_path,
        "receipt": receipt_path,
    }


__all__ = [
    "FullResumeQrelW2Error",
    "QUERY_MANIFEST_SCHEMA_VERSION",
    "QUERY_MANIFEST_STATUS",
    "RANKING_SCHEMA_VERSION",
    "RANKING_STATUS",
    "RECEIPT_SCHEMA_VERSION",
    "RECEIPT_STATUS",
    "RUNTIME_DIR",
    "build_frozen_ranking_artifact",
    "build_w2_query_manifest",
    "materialize_w2_rankings",
    "validate_frozen_ranking_artifact",
    "validate_w2_query_manifest",
    "write_w2_query_manifest",
]
