"""Materialize or verify the C0.3 graph-evidence cluster registry Wave 4."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.fact_inventory.c03_graph_evidence_cluster_registry import (  # noqa: E402
    CANDIDATE_FACT_LEDGER_PATH,
    CONTRACT_PATH,
    GRAPH_PATH,
    LEGACY_ARTIFACT_DIR,
    REGISTRY_PATH,
    ROLE_EPISODE_BUNDLE_PATHS,
    W3_RECEIPT_PATH,
    W4_RECEIPT_PATH,
    build_w4_receipt,
    materialize_cluster_registry,
    registry_profile,
    validate_registry,
    validate_registry_contract,
    validate_w4_receipt,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (  # noqa: E402
    canonical_sha256,
    file_sha256,
)
from apps_rg.fact_inventory.c03_legacy_embedding_retirement_wave5 import (  # noqa: E402
    RETIREMENT_MARKER_PATH,
    historical_legacy_inventory_from_marker,
)

DEFAULT_BASELINE_REF = "c8b50be2ef8fbc01d923fec6ada321568f725783"


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


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _load_json_bytes(payload: bytes, description: str) -> dict[str, Any]:
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON authority must be an object: {description}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    return _load_json_bytes(path.read_bytes(), str(path))


def _source_record(path: Path, payload: bytes) -> dict[str, Any]:
    value = _load_json_bytes(payload, path.as_posix())
    return {
        "path": path.as_posix(),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "canonical_sha256": canonical_sha256(value),
    }


def _legacy_records(repo_root: Path) -> list[dict[str, Any]]:
    directory = repo_root / LEGACY_ARTIFACT_DIR
    if not directory.is_dir():
        retirement_path = repo_root / RETIREMENT_MARKER_PATH
        if not retirement_path.is_file():
            raise SystemExit(f"Legacy artifact directory is missing: {directory}")
        retirement = _load_json(retirement_path)
        return historical_legacy_inventory_from_marker(retirement)
    records = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        record: dict[str, Any] = {
            "path": path.relative_to(repo_root).as_posix(),
            "file_sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        if path.suffix.lower() == ".json":
            record["canonical_sha256"] = canonical_sha256(_load_json(path))
        records.append(record)
    return records


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(f"{path.suffix}.tmp")
    staging.write_bytes(payload)
    staging.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    source_paths = (
        GRAPH_PATH,
        W3_RECEIPT_PATH,
        CANDIDATE_FACT_LEDGER_PATH,
        *ROLE_EPISODE_BUNDLE_PATHS,
    )
    source_bytes = {
        path.as_posix(): _git_bytes(repo_root, args.baseline_ref, path)
        for path in source_paths
    }
    source_records = {
        path: _source_record(Path(path), payload)
        for path, payload in source_bytes.items()
    }
    graph = _load_json_bytes(source_bytes[GRAPH_PATH.as_posix()], GRAPH_PATH.as_posix())
    w3_receipt = _load_json_bytes(
        source_bytes[W3_RECEIPT_PATH.as_posix()], W3_RECEIPT_PATH.as_posix()
    )
    candidate_fact_ledger = _load_json_bytes(
        source_bytes[CANDIDATE_FACT_LEDGER_PATH.as_posix()],
        CANDIDATE_FACT_LEDGER_PATH.as_posix(),
    )
    bundles_by_path = {
        path.as_posix(): _load_json_bytes(
            source_bytes[path.as_posix()], path.as_posix()
        )
        for path in ROLE_EPISODE_BUNDLE_PATHS
    }
    contract = _load_json(repo_root / CONTRACT_PATH)
    validate_registry_contract(contract)
    source_tree = _git_value(repo_root, "rev-parse", f"{args.baseline_ref}^{{tree}}")
    registry = materialize_cluster_registry(
        graph=graph,
        bundles_by_path=bundles_by_path,
        candidate_fact_ledger=candidate_fact_ledger,
        source_records=source_records,
        w3_receipt=w3_receipt,
        source_commit=args.baseline_ref,
        source_tree=source_tree,
    )
    validate_registry(registry, graph=graph)

    legacy_records = _legacy_records(repo_root)
    frozen_legacy = (w3_receipt.get("legacy_embedding_artifacts") or {}).get(
        "artifacts"
    )
    if legacy_records != frozen_legacy:
        raise SystemExit("Legacy embedding artifacts changed after the Wave 3 freeze")
    working_graph = repo_root / GRAPH_PATH
    if (
        not working_graph.is_file()
        or working_graph.read_bytes() != source_bytes[GRAPH_PATH.as_posix()]
    ):
        raise SystemExit("Canonical graph changed after the Wave 3 baseline")

    receipt = build_w4_receipt(
        registry=registry,
        contract=contract,
        graph=graph,
        w3_receipt=w3_receipt,
        legacy_artifacts=legacy_records,
        source_commit=args.baseline_ref,
        source_tree=source_tree,
    )
    validate_w4_receipt(receipt)
    registry_bytes = _json_bytes(registry)
    receipt_bytes = _json_bytes(receipt)
    registry_path = repo_root / REGISTRY_PATH
    receipt_path = repo_root / W4_RECEIPT_PATH
    if args.check:
        stale = []
        if not registry_path.is_file() or registry_path.read_bytes() != registry_bytes:
            stale.append(REGISTRY_PATH.as_posix())
        if not receipt_path.is_file() or receipt_path.read_bytes() != receipt_bytes:
            stale.append(W4_RECEIPT_PATH.as_posix())
        if stale:
            raise SystemExit(f"W4 outputs are missing or stale: {stale}")
    else:
        _write_atomic(registry_path, registry_bytes)
        _write_atomic(receipt_path, receipt_bytes)

    profile = registry_profile(registry)
    print(
        json.dumps(
            {
                "status": "PASS",
                "completion_marker": receipt["completion_marker"],
                "registry_sha256": registry["registry_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "materialized_cluster_count": profile["materialized_cluster_count"],
                "role_episode_cluster_count": profile["role_episode_cluster_count"],
                "capability_evidence_cluster_count": profile[
                    "capability_evidence_cluster_count"
                ],
                "held_candidate_count": profile["held_candidate_count"],
                "active_unique_member_count": profile["active_unique_member_count"],
                "held_unembedded_skill_count": len(
                    registry["eligible_skill_audit"]["held_unembedded_skill_ids"]
                ),
                "replacement_vectors_generated": False,
                "production_promotion_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
