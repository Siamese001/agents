"""Run or verify W7 cluster-embedding qualification readiness diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (  # noqa: E402
    ACTIVATION_MANIFEST_PATH,
    CONTRACT_PATH,
    QUERY_MANIFEST_PATH,
    W6_RECEIPT_PATH,
    W7_RECEIPT_PATH,
    build_query_texts,
    build_w7_blocked_receipt,
    expected_judgment_keys,
    ranking_identity_sha256,
    validate_qualification_contract,
    validate_query_manifest,
    validate_w7_receipt,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_embedding_generation import (  # noqa: E402
    GRAPH_PATH,
    REGISTRY_PATH,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_registry import (  # noqa: E402
    validate_registry,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (  # noqa: E402
    canonical_sha256,
)
from apps_rg.fact_inventory.c03_skill_embedding_builder import (  # noqa: E402
    build_local_model_manifest,
    encode_bge_m3,
)
from apps_rg.runtime.graph_evidence_cluster_embedding_projection import (  # noqa: E402
    GraphEvidenceClusterEmbeddingIndex,
    rehydrate_cluster_candidates,
    validate_cluster_embedding_projection,
)

DEFAULT_BASELINE_REF = "1b2252734db24d5fcea8349cfb1f2abb204c4f47"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON authority must be an object: {path}")
    return value


def _render_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


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


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    staging.write_bytes(payload)
    os.replace(staging, path)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise SystemExit("Cannot calculate latency percentile without observations")
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[rank]


def _load_w6_authority(
    repo_root: Path, baseline_ref: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    for path in (GRAPH_PATH, REGISTRY_PATH, W6_RECEIPT_PATH):
        baseline = _git_bytes(repo_root, baseline_ref, path)
        if (repo_root / path).read_bytes() != baseline:
            raise SystemExit(f"W6 authority changed after baseline: {path.as_posix()}")
    graph = _load_json(repo_root / GRAPH_PATH)
    registry = _load_json(repo_root / REGISTRY_PATH)
    w6_receipt = _load_json(repo_root / W6_RECEIPT_PATH)
    validate_registry(registry, graph=graph)
    generation_path = repo_root / str(w6_receipt["generation"]["manifest_path"])
    generation = _load_json(generation_path)
    projection_path = repo_root / str(generation["projection"]["path"])
    if _file_sha256(projection_path) != generation["projection"]["file_sha256"]:
        raise SystemExit("W6 projection file digest is invalid")
    return graph, registry, w6_receipt, generation, projection_path


def _assert_non_activation_boundary(repo_root: Path) -> None:
    if (repo_root / ACTIVATION_MANIFEST_PATH).exists():
        raise SystemExit("W7 cannot create or coexist with an activation manifest")


def _run_diagnostics(
    *,
    repo_root: Path,
    contract: dict[str, Any],
    query_manifest: dict[str, Any],
    graph: dict[str, Any],
    registry: dict[str, Any],
    generation: dict[str, Any],
    projection_path: Path,
    model_path: Path,
    device: str,
) -> dict[str, Any]:
    model_manifest = build_local_model_manifest(model_path)
    model = generation["model"]
    if model_manifest["artifact_sha256"] != model["artifact_sha256"]:
        raise SystemExit("Local model does not match the W6 model artifact")
    projection_issues = validate_cluster_embedding_projection(
        projection_path, registry=registry, model_manifest=model_manifest
    )
    if projection_issues:
        raise SystemExit(f"W6 projection validation failed: {projection_issues}")

    query_texts = build_query_texts(query_manifest, repository_root=repo_root)
    ordered_query_ids = sorted(query_texts)
    encode_started = time.perf_counter()
    runtime_proof, vectors = encode_bge_m3(
        [query_texts[query_id] for query_id in ordered_query_ids],
        model_path=model_path,
        device=device,
        batch_size=6,
    )
    encode_elapsed_ms = (time.perf_counter() - encode_started) * 1000.0
    vectors_by_query = dict(zip(ordered_query_ids, vectors, strict=True))

    sections = sorted(str(value) for value in query_manifest["section_ids"])
    expected_keys = expected_judgment_keys(query_manifest, registry)
    expected_by_pair: dict[str, set[str]] = {}
    for query_id, section_id, cluster_id in expected_keys:
        expected_by_pair.setdefault(f"{query_id}|{section_id}", set()).add(cluster_id)
    search_latencies: list[float] = []
    ranking_bindings: dict[str, list[str]] = {}
    candidate_rows = 0
    candidate_only_passed = True
    section_policy_passed = True
    rehydration_passed = True
    with GraphEvidenceClusterEmbeddingIndex(
        projection_path,
        expected_registry_sha256=str(registry["registry_sha256"]),
        expected_model_artifact_sha256=str(model_manifest["artifact_sha256"]),
    ) as index:
        for query_id in ordered_query_ids:
            for section_id in sections:
                started = time.perf_counter()
                candidates = index.query(
                    vectors_by_query[query_id], k=37, section_id=section_id
                )
                search_latencies.append((time.perf_counter() - started) * 1000.0)
                pair = f"{query_id}|{section_id}"
                ranking_bindings[pair] = [str(row["cluster_id"]) for row in candidates]
                candidate_rows += len(candidates)
                if any(set(row) != {"cluster_id", "similarity"} for row in candidates):
                    candidate_only_passed = False
                if set(ranking_bindings[pair]) != expected_by_pair.get(pair, set()):
                    section_policy_passed = False
                hydrated = rehydrate_cluster_candidates(
                    candidates,
                    registry=registry,
                    graph_payload=graph,
                    section_id=section_id,
                )
                if {str(row["cluster_id"]) for row in hydrated} != set(
                    ranking_bindings[pair]
                ):
                    rehydration_passed = False

    thresholds = contract["quality_gates"]
    search_p95_ms = _percentile(search_latencies, 0.95)
    latency_gate_passed = encode_elapsed_ms <= float(
        thresholds["cold_six_query_encode_elapsed_ms_max"]
    ) and search_p95_ms <= float(thresholds["projection_search_p95_ms_max"])
    diagnostic = {
        "projection_integrity_passed": not projection_issues,
        "candidate_only_payload_passed": candidate_only_passed,
        "section_policy_passed": section_policy_passed,
        "current_authority_rehydration_passed": rehydration_passed,
        "latency_gate_passed": latency_gate_passed,
        "query_count": len(ordered_query_ids),
        "section_count": len(sections),
        "query_section_count": len(ranking_bindings),
        "candidate_row_count": candidate_rows,
        "expected_judgment_count": len(expected_keys),
        "ranking_identity_sha256": ranking_identity_sha256(ranking_bindings),
        "cold_six_query_encode_elapsed_ms": round(encode_elapsed_ms, 3),
        "projection_search_p50_ms": round(_percentile(search_latencies, 0.50), 3),
        "projection_search_p95_ms": round(search_p95_ms, 3),
        "projection_search_max_ms": round(max(search_latencies), 3),
        "runtime_proof": runtime_proof,
        "quality_metrics_computed": False,
        "quality_metrics_blocked_by": "CURRENT_CLUSTER_QRELS_MISSING",
        "rankings_or_scores_published": False,
    }
    if not all(
        diagnostic[field]
        for field in (
            "projection_integrity_passed",
            "candidate_only_payload_passed",
            "section_policy_passed",
            "current_authority_rehydration_passed",
            "latency_gate_passed",
        )
    ):
        raise SystemExit(f"W7 readiness diagnostic failed: {diagnostic}")
    return diagnostic


def _check_receipt_sources(
    *,
    repo_root: Path,
    receipt: dict[str, Any],
    contract: dict[str, Any],
    query_manifest: dict[str, Any],
    w6_receipt: dict[str, Any],
    registry: dict[str, Any],
    generation: dict[str, Any],
    projection_path: Path,
) -> None:
    validate_w7_receipt(receipt)
    if receipt["contract"]["canonical_sha256"] != canonical_sha256(contract):
        raise SystemExit(
            "W7 receipt is not bound to the current qualification contract"
        )
    source = receipt["source_baseline"]
    if source["wave6_receipt_sha256"] != w6_receipt["receipt_sha256"]:
        raise SystemExit("W7 receipt is not bound to the current W6 receipt")
    if source["wave4_registry_sha256"] != registry["registry_sha256"]:
        raise SystemExit("W7 receipt is not bound to the current cluster registry")
    if (
        source["projection_generation_sha256"]
        != generation["projection"]["generation_sha256"]
    ):
        raise SystemExit("W7 receipt is not bound to the current projection")
    if (
        receipt["query_manifest"]["query_manifest_sha256"]
        != query_manifest["query_manifest_sha256"]
    ):
        raise SystemExit("W7 receipt is not bound to the current query manifest")
    if _file_sha256(projection_path) != generation["projection"]["file_sha256"]:
        raise SystemExit("W7 projection digest drifted")


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
    _assert_non_activation_boundary(repo_root)
    contract = _load_json(repo_root / CONTRACT_PATH)
    query_manifest = _load_json(repo_root / QUERY_MANIFEST_PATH)
    validate_qualification_contract(contract)
    validate_query_manifest(query_manifest, repository_root=repo_root)
    graph, registry, w6_receipt, generation, projection_path = _load_w6_authority(
        repo_root, args.baseline_ref
    )
    receipt_path = repo_root / W7_RECEIPT_PATH

    if args.write:
        if receipt_path.exists():
            raise SystemExit("W7 receipt already exists; use --check")
        if args.model_path is None:
            raise SystemExit(
                "--model-path or APPS_RG_EMBEDDING_MODEL_PATH is required for --write"
            )
        diagnostic = _run_diagnostics(
            repo_root=repo_root,
            contract=contract,
            query_manifest=query_manifest,
            graph=graph,
            registry=registry,
            generation=generation,
            projection_path=projection_path,
            model_path=args.model_path.resolve(),
            device=args.device,
        )
        receipt = build_w7_blocked_receipt(
            contract=contract,
            query_manifest=query_manifest,
            w6_receipt=w6_receipt,
            registry=registry,
            diagnostic_proof=diagnostic,
            source_commit=args.baseline_ref,
            source_tree=_git_value(
                repo_root, "rev-parse", f"{args.baseline_ref}^{{tree}}"
            ),
        )
        validate_w7_receipt(receipt)
        _write_atomic(receipt_path, _render_json(receipt))
    else:
        if not receipt_path.is_file():
            raise SystemExit("W7 receipt is missing")
        receipt = _load_json(receipt_path)
        _check_receipt_sources(
            repo_root=repo_root,
            receipt=receipt,
            contract=contract,
            query_manifest=query_manifest,
            w6_receipt=w6_receipt,
            registry=registry,
            generation=generation,
            projection_path=projection_path,
        )
    _assert_non_activation_boundary(repo_root)
    output = {
        "status": receipt["status"],
        "wave": "W7",
        "qualification_harness_ready": receipt["scope"]["qualification_harness_ready"],
        "semantic_retrieval_qualified": receipt["scope"][
            "semantic_retrieval_qualified"
        ],
        "required_human_judgment_count": receipt["label_authority"][
            "required_judgment_count"
        ],
        "observed_human_judgment_count": receipt["label_authority"][
            "observed_judgment_count"
        ],
        "candidate_row_count": receipt["diagnostic_proof"]["candidate_row_count"],
        "production_promotion": receipt["wave_exit_gates"]["production_promotion"],
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
