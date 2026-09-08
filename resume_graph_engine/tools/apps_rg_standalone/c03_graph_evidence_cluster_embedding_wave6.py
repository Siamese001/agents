"""Generate or verify the immutable W6 C0.3 semantic-cluster vectors."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (  # noqa: E402
    ARTIFACT_DIR,
    CONTRACT_PATH,
    GRAPH_PATH,
    REGISTRY_PATH,
    RETIREMENT_MARKER_PATH,
    W5_RECEIPT_PATH,
    W6_RECEIPT_PATH,
    build_generation_manifest,
    build_w6_receipt,
    validate_generation_contract,
    validate_generation_manifest,
    validate_w6_receipt,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_registry import (  # noqa: E402
    validate_registry,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (  # noqa: E402
    canonical_sha256,
)
from apps_rg.fact_inventory.c03_legacy_embedding_retirement_wave5 import (  # noqa: E402
    LEGACY_ARTIFACT_DIR,
    validate_retirement_marker,
    validate_w5_receipt,
)
from apps_rg.fact_inventory.c03_skill_embedding_builder import (  # noqa: E402
    build_local_model_manifest,
    encode_bge_m3,
)
from apps_rg.runtime.c0.graph_evidence_cluster_embedding_activation import (  # noqa: E402
    ACTIVE_CLUSTER_MANIFEST,
)
from apps_rg.runtime.graph_evidence_cluster_embedding_projection import (  # noqa: E402
    GraphEvidenceClusterEmbeddingError,
    GraphEvidenceClusterEmbeddingIndex,
    build_cluster_embedding_projection,
    rehydrate_cluster_candidates,
    validate_cluster_embedding_projection,
)

DEFAULT_BASELINE_REF = "ac828da46157271edaf7e9f745dfccf9436361ef"
EXPECTED_MODEL_ID = "BAAI/bge-m3"
EXPECTED_MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_bytes(repo_root: Path, ref: str, path: Path) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return result.stdout


def _load_json_bytes(payload: bytes, description: str) -> dict[str, Any]:
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON authority must be an object: {description}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    return _load_json_bytes(path.read_bytes(), str(path))


def _render_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write_immutable(path: Path, payload: bytes) -> str:
    if path.exists():
        if path.read_bytes() != payload:
            raise SystemExit(f"Immutable artifact collision: {path}")
        return hashlib.sha256(payload).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    staging.write_bytes(payload)
    os.replace(staging, path)
    return hashlib.sha256(payload).hexdigest()


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    staging.write_bytes(payload)
    os.replace(staging, path)


def _repository_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"Artifact path escapes repository: {path}") from exc


def _assert_w6_boundary(repo_root: Path) -> None:
    if (repo_root / LEGACY_ARTIFACT_DIR).exists():
        raise SystemExit("Retired legacy embedding artifact directory reappeared")
    if (repo_root / ACTIVE_CLUSTER_MANIFEST).exists():
        raise SystemExit("W6 cannot create or coexist with an activation manifest")


def _smoke_projection(
    projection_path: Path,
    *,
    registry: dict[str, Any],
    graph: dict[str, Any],
    model_artifact_sha256: str,
) -> dict[str, Any]:
    first_cluster = sorted(
        registry["clusters"], key=lambda row: str(row["cluster_id"])
    )[0]
    first_id = str(first_cluster["cluster_id"])
    uri = f"file:{projection_path.resolve().as_posix()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        blob = conn.execute(
            "SELECT vector FROM cluster_vectors WHERE cluster_id = ?", (first_id,)
        ).fetchone()[0]
    query_vector = struct.unpack("<1024f", blob)
    with GraphEvidenceClusterEmbeddingIndex(
        projection_path,
        expected_registry_sha256=str(registry["registry_sha256"]),
        expected_model_artifact_sha256=model_artifact_sha256,
    ) as index:
        candidates = index.query(query_vector, k=3)
        if not candidates or candidates[0]["cluster_id"] != first_id:
            raise SystemExit("Candidate-only query did not retrieve its source cluster")
        if any(set(item) != {"cluster_id", "similarity"} for item in candidates):
            raise SystemExit("Candidate-only query exposed forbidden fields")
        section_id = str(first_cluster["allowed_sections"][0])
        section_candidates = index.query(query_vector, k=3, section_id=section_id)
        allowed_by_id = {
            str(row["cluster_id"]): set(row["allowed_sections"])
            for row in registry["clusters"]
        }
        if not section_candidates or any(
            section_id not in allowed_by_id[item["cluster_id"]]
            for item in section_candidates
        ):
            raise SystemExit("Section-filtered query returned a forbidden cluster")
        try:
            index.query(query_vector, k=index.vector_count)
        except GraphEvidenceClusterEmbeddingError:
            bounded_rejection = True
        else:
            raise SystemExit("Full-corpus top-k did not fail closed")
    hydrated = rehydrate_cluster_candidates(
        [candidates[0]],
        registry=registry,
        graph_payload=graph,
        section_id=section_id,
    )
    if len(hydrated) != 1 or hydrated[0]["cluster_id"] != first_id:
        raise SystemExit("Current-authority cluster rehydration failed")
    return {
        "candidate_only_query_passed": True,
        "bounded_top_k_rejection_passed": bounded_rejection,
        "section_filter_query_passed": True,
        "current_authority_rehydration_passed": True,
        "smoke_query_cluster_id": first_id,
        "smoke_query_top_similarity": float(candidates[0]["similarity"]),
    }


def _validate_model_manifest(model: dict[str, Any]) -> None:
    unsigned = dict(model)
    supplied = unsigned.pop("artifact_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        raise SystemExit("Model manifest self digest is invalid")
    expected = {
        "model_id": EXPECTED_MODEL_ID,
        "revision": EXPECTED_MODEL_REVISION,
        "dimension": 1024,
        "normalization": "l2",
    }
    for field, value in expected.items():
        if model.get(field) != value:
            raise SystemExit(f"Model manifest {field} does not match the W6 contract")


def _load_w5_baseline(
    repo_root: Path, baseline_ref: str
) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, bytes]
]:
    paths = (GRAPH_PATH, REGISTRY_PATH, W5_RECEIPT_PATH, RETIREMENT_MARKER_PATH)
    source_bytes = {
        path.as_posix(): _git_bytes(repo_root, baseline_ref, path) for path in paths
    }
    graph = _load_json_bytes(source_bytes[GRAPH_PATH.as_posix()], GRAPH_PATH.as_posix())
    registry = _load_json_bytes(
        source_bytes[REGISTRY_PATH.as_posix()], REGISTRY_PATH.as_posix()
    )
    w5_receipt = _load_json_bytes(
        source_bytes[W5_RECEIPT_PATH.as_posix()], W5_RECEIPT_PATH.as_posix()
    )
    marker = _load_json_bytes(
        source_bytes[RETIREMENT_MARKER_PATH.as_posix()],
        RETIREMENT_MARKER_PATH.as_posix(),
    )
    for path in paths:
        if (repo_root / path).read_bytes() != source_bytes[path.as_posix()]:
            raise SystemExit(
                f"W5 authority changed after the baseline: {path.as_posix()}"
            )
    validate_registry(registry, graph=graph)
    validate_w5_receipt(w5_receipt)
    validate_retirement_marker(marker)
    if canonical_sha256(graph) != (registry.get("source_authority") or {}).get(
        "canonical_graph_sha256"
    ):
        raise SystemExit("Registry is not bound to the current canonical graph")
    return graph, registry, w5_receipt, marker, source_bytes


def _source_baseline(
    *,
    repo_root: Path,
    baseline_ref: str,
    graph: dict[str, Any],
    registry: dict[str, Any],
    w5_receipt: dict[str, Any],
    marker: dict[str, Any],
    source_bytes: dict[str, bytes],
) -> dict[str, Any]:
    return {
        "commit": baseline_ref,
        "tree": _git_value(repo_root, "rev-parse", f"{baseline_ref}^{{tree}}"),
        "canonical_graph": {
            "path": GRAPH_PATH.as_posix(),
            "file_sha256": hashlib.sha256(
                source_bytes[GRAPH_PATH.as_posix()]
            ).hexdigest(),
            "canonical_sha256": canonical_sha256(graph),
        },
        "cluster_registry": {
            "path": REGISTRY_PATH.as_posix(),
            "file_sha256": hashlib.sha256(
                source_bytes[REGISTRY_PATH.as_posix()]
            ).hexdigest(),
            "registry_sha256": registry["registry_sha256"],
        },
        "wave5_receipt": {
            "path": W5_RECEIPT_PATH.as_posix(),
            "file_sha256": hashlib.sha256(
                source_bytes[W5_RECEIPT_PATH.as_posix()]
            ).hexdigest(),
            "receipt_sha256": w5_receipt["receipt_sha256"],
        },
        "retirement_marker": {
            "path": RETIREMENT_MARKER_PATH.as_posix(),
            "file_sha256": hashlib.sha256(
                source_bytes[RETIREMENT_MARKER_PATH.as_posix()]
            ).hexdigest(),
            "retirement_sha256": marker["retirement_sha256"],
        },
    }


def _generate(
    *,
    repo_root: Path,
    model_path: Path,
    device: str,
    contract: dict[str, Any],
    graph: dict[str, Any],
    registry: dict[str, Any],
    w5_receipt: dict[str, Any],
    marker: dict[str, Any],
    source_bytes: dict[str, bytes],
    baseline_ref: str,
) -> dict[str, Any]:
    artifact_dir = repo_root / ARTIFACT_DIR
    model_manifest = build_local_model_manifest(model_path)
    _validate_model_manifest(model_manifest)
    model_path_out = artifact_dir / (
        f"bge_m3_model_manifest.{model_manifest['artifact_sha256']}.json"
    )
    model_file_sha256 = _write_immutable(model_path_out, _render_json(model_manifest))

    cluster_rows = sorted(registry["clusters"], key=lambda row: str(row["cluster_id"]))
    runtime_proof, vectors = encode_bge_m3(
        [str(row["canonical_embedding_text"]) for row in cluster_rows],
        model_path=model_path,
        device=device,
        batch_size=8,
    )
    if runtime_proof.get("fallback_used") is not False:
        raise SystemExit("Embedding runtime used a forbidden fallback")
    vectors_by_cluster = {
        str(row["cluster_id"]): vector
        for row, vector in zip(cluster_rows, vectors, strict=True)
    }
    staging_projection = artifact_dir / f".cluster-vectors-{os.getpid()}.sqlite"
    projection_build = build_cluster_embedding_projection(
        staging_projection,
        registry=registry,
        vectors_by_cluster=vectors_by_cluster,
        model_manifest=model_manifest,
    )
    projection_path = artifact_dir / (
        "graph_evidence_cluster_embeddings."
        f"{projection_build['generation_sha256']}.sqlite"
    )
    if projection_path.exists():
        if _file_sha256(projection_path) != projection_build["sqlite_sha256"]:
            staging_projection.unlink(missing_ok=True)
            raise SystemExit(f"Immutable projection collision: {projection_path}")
        staging_projection.unlink()
    else:
        os.replace(staging_projection, projection_path)
    issues = validate_cluster_embedding_projection(
        projection_path, registry=registry, model_manifest=model_manifest
    )
    if issues:
        raise SystemExit(f"Generated projection is invalid: {issues}")
    smoke_proof = _smoke_projection(
        projection_path,
        registry=registry,
        graph=graph,
        model_artifact_sha256=str(model_manifest["artifact_sha256"]),
    )

    source_baseline = _source_baseline(
        repo_root=repo_root,
        baseline_ref=baseline_ref,
        graph=graph,
        registry=registry,
        w5_receipt=w5_receipt,
        marker=marker,
        source_bytes=source_bytes,
    )
    projection_record = {
        "path": _repository_path(projection_path, repo_root),
        "file_sha256": _file_sha256(projection_path),
        "generation_sha256": projection_build["generation_sha256"],
        "registry_sha256": registry["registry_sha256"],
        "graph_sha256": (registry.get("source_authority") or {})[
            "canonical_graph_sha256"
        ],
        "model_artifact_sha256": model_manifest["artifact_sha256"],
        "vector_count": projection_build["vector_count"],
        "dimension": projection_build["dimension"],
        "normalization": projection_build["normalization"],
        "held_candidate_vector_count": 0,
        "skill_or_node_vector_count": 0,
    }
    model_record = {
        "path": _repository_path(model_path_out, repo_root),
        "manifest_file_sha256": model_file_sha256,
        "model_id": model_manifest["model_id"],
        "revision": model_manifest["revision"],
        "artifact_sha256": model_manifest["artifact_sha256"],
        "dimension": model_manifest["dimension"],
        "normalization": model_manifest["normalization"],
    }
    generation_manifest = build_generation_manifest(
        source_baseline=source_baseline,
        model=model_record,
        projection=projection_record,
        runtime_proof=runtime_proof,
        smoke_proof=smoke_proof,
    )
    validate_generation_manifest(generation_manifest)
    generation_path = artifact_dir / (
        "graph_evidence_cluster_embedding_generation."
        f"{generation_manifest['manifest_sha256']}.json"
    )
    generation_file_sha256 = _write_immutable(
        generation_path, _render_json(generation_manifest)
    )
    receipt = build_w6_receipt(
        contract=contract,
        generation_manifest=generation_manifest,
        generation_manifest_path=_repository_path(generation_path, repo_root),
        generation_manifest_file_sha256=generation_file_sha256,
        registry=registry,
        w5_receipt=w5_receipt,
        source_commit=baseline_ref,
        source_tree=source_baseline["tree"],
    )
    validate_w6_receipt(receipt)
    _write_atomic(repo_root / W6_RECEIPT_PATH, _render_json(receipt))
    return receipt


def _check_existing(
    *,
    repo_root: Path,
    registry: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    receipt_path = repo_root / W6_RECEIPT_PATH
    if not receipt_path.is_file():
        raise SystemExit(f"W6 receipt is missing: {receipt_path}")
    receipt = _load_json(receipt_path)
    validate_w6_receipt(receipt)
    generation_record = receipt["generation"]
    generation_path = repo_root / str(generation_record["manifest_path"])
    if not generation_path.is_file():
        raise SystemExit("W6 immutable generation manifest is missing")
    if _file_sha256(generation_path) != generation_record["manifest_file_sha256"]:
        raise SystemExit("W6 generation manifest file digest is invalid")
    generation = _load_json(generation_path)
    validate_generation_manifest(generation)
    if generation["manifest_sha256"] != generation_record["manifest_sha256"]:
        raise SystemExit("W6 generation manifest authority digest is invalid")

    model_record = generation["model"]
    model_manifest_path = repo_root / str(model_record["path"])
    if _file_sha256(model_manifest_path) != model_record["manifest_file_sha256"]:
        raise SystemExit("W6 model manifest file digest is invalid")
    model_manifest = _load_json(model_manifest_path)
    _validate_model_manifest(model_manifest)
    if model_manifest["artifact_sha256"] != model_record["artifact_sha256"]:
        raise SystemExit("W6 model artifact digest binding is invalid")

    projection_record = generation["projection"]
    projection_path = repo_root / str(projection_record["path"])
    if _file_sha256(projection_path) != projection_record["file_sha256"]:
        raise SystemExit("W6 projection file digest is invalid")
    issues = validate_cluster_embedding_projection(
        projection_path, registry=registry, model_manifest=model_manifest
    )
    if issues:
        raise SystemExit(f"W6 projection validation failed: {issues}")
    smoke = _smoke_projection(
        projection_path,
        registry=registry,
        graph=graph,
        model_artifact_sha256=str(model_manifest["artifact_sha256"]),
    )
    if {
        key: value
        for key, value in generation["smoke_proof"].items()
        if key != "smoke_query_top_similarity"
    } != {
        key: value
        for key, value in smoke.items()
        if key != "smoke_query_top_similarity"
    }:
        raise SystemExit("W6 projection smoke proof drifted")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=(
            Path(os.environ["APPS_RG_EMBEDDING_MODEL_PATH"])
            if os.environ.get("APPS_RG_EMBEDDING_MODEL_PATH")
            else None
        ),
    )
    parser.add_argument("--device", default="cuda:0")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    _assert_w6_boundary(repo_root)
    contract = _load_json(repo_root / CONTRACT_PATH)
    validate_generation_contract(contract)
    graph, registry, w5_receipt, marker, source_bytes = _load_w5_baseline(
        repo_root, args.baseline_ref
    )
    if len(registry["clusters"]) != 38 or len(registry["held_candidates"]) != 94:
        raise SystemExit(
            "W4 registry cardinality does not match the frozen W6 contract"
        )

    if args.write:
        if (repo_root / W6_RECEIPT_PATH).exists():
            raise SystemExit(
                "W6 is already generated; use --check for immutable verification"
            )
        if args.model_path is None:
            raise SystemExit(
                "--model-path or APPS_RG_EMBEDDING_MODEL_PATH is required for --write"
            )
        receipt = _generate(
            repo_root=repo_root,
            model_path=args.model_path.resolve(),
            device=args.device,
            contract=contract,
            graph=graph,
            registry=registry,
            w5_receipt=w5_receipt,
            marker=marker,
            source_bytes=source_bytes,
            baseline_ref=args.baseline_ref,
        )
    else:
        receipt = _check_existing(repo_root=repo_root, registry=registry, graph=graph)
    _assert_w6_boundary(repo_root)
    result = {
        "status": "PASS",
        "wave": "W6",
        "completion_marker": receipt["completion_marker"],
        "vector_count": receipt["generation"]["vector_count"],
        "active_cluster_count": receipt["generation"]["active_cluster_count"],
        "held_candidate_count": receipt["generation"]["held_candidate_count"],
        "held_candidate_vector_count": receipt["generation"][
            "held_candidate_vector_count"
        ],
        "skill_or_node_vector_count": receipt["generation"][
            "skill_or_node_vector_count"
        ],
        "semantic_retrieval_qualification": receipt["wave_exit_gates"][
            "semantic_retrieval_qualification"
        ],
        "production_promotion": receipt["wave_exit_gates"]["production_promotion"],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
