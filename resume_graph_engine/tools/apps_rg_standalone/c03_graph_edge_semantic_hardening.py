"""Apply or verify C0.3 graph-edge semantic hardening Wave 2."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.fact_inventory.c03_graph_edge_semantic_hardening import (  # noqa: E402
    EDGE_SEMANTIC_CONTRACT_PATH,
    GRAPH_PATH,
    W1_RECEIPT_PATH,
    build_w2_receipt,
    edge_semantic_profile,
    harden_graph_edge_semantics,
    validate_edge_semantic_contract,
    validate_w2_receipt,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (  # noqa: E402
    LEGACY_ARTIFACT_DIR,
    canonical_sha256,
    file_sha256,
)

DEFAULT_BASELINE_REF = "3e67e0dc99216c1263cd8ce21793ecde24681b9a"
DEFAULT_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave2_edge_assertion_hardening_receipt.json"
)


def _git_value(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_json(repo_root: Path, ref: str, path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    value = json.loads(result.stdout.decode("utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"Git baseline JSON must be an object: {ref}:{path}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON authority must be an object: {path}")
    return value


def _serialize(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _legacy_records(repo_root: Path) -> list[dict[str, Any]]:
    root = repo_root / LEGACY_ARTIFACT_DIR
    if not root.is_dir():
        raise SystemExit(f"Legacy artifact directory is missing: {root}")
    return [
        {
            "path": path.relative_to(repo_root).as_posix(),
            "file_sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
            **(
                {"canonical_sha256": canonical_sha256(_load_json(path))}
                if path.suffix.lower() == ".json"
                else {}
            ),
        }
        for path in sorted(root.iterdir(), key=lambda value: value.name)
        if path.is_file()
    ]


def _assert_legacy_unchanged(
    current: list[dict[str, Any]],
    w1_receipt: dict[str, Any],
) -> None:
    frozen = (w1_receipt.get("legacy_embedding_artifacts") or {}).get("artifacts")
    if current != frozen:
        raise SystemExit("Legacy embedding artifacts changed after the Wave 1 freeze")


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(f"{path.suffix}.tmp")
    staging.write_bytes(payload)
    staging.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    before_graph = _git_json(repo_root, args.baseline_ref, GRAPH_PATH)
    contract = _load_json(repo_root / EDGE_SEMANTIC_CONTRACT_PATH)
    validate_edge_semantic_contract(contract)
    w1_receipt = _load_json(repo_root / W1_RECEIPT_PATH)
    legacy_records = _legacy_records(repo_root)
    _assert_legacy_unchanged(legacy_records, w1_receipt)
    after_graph = harden_graph_edge_semantics(before_graph)
    source_tree = _git_value(repo_root, "rev-parse", f"{args.baseline_ref}^{{tree}}")
    receipt = build_w2_receipt(
        before_graph=before_graph,
        after_graph=after_graph,
        w1_receipt=w1_receipt,
        contract=contract,
        legacy_artifacts=legacy_records,
        source_commit=args.baseline_ref,
        source_tree=source_tree,
    )
    validate_w2_receipt(receipt)
    graph_bytes = _serialize(after_graph)
    receipt_bytes = _serialize(receipt)
    graph_path = repo_root / GRAPH_PATH
    receipt_path = repo_root / args.receipt

    if args.check:
        stale = []
        if not graph_path.is_file() or graph_path.read_bytes() != graph_bytes:
            stale.append(GRAPH_PATH.as_posix())
        if not receipt_path.is_file() or receipt_path.read_bytes() != receipt_bytes:
            stale.append(args.receipt.as_posix())
        if stale:
            raise SystemExit(f"W2 outputs are missing or stale: {stale}")
    else:
        _write_atomic(graph_path, graph_bytes)
        _write_atomic(receipt_path, receipt_bytes)

    profile = edge_semantic_profile(after_graph)
    print(
        json.dumps(
            {
                "status": "PASS",
                "completion_marker": receipt["completion_marker"],
                "receipt_sha256": receipt["receipt_sha256"],
                "graph_sha256": receipt["after"]["graph_canonical_sha256"],
                "edge_count": profile["edge_count"],
                "lifecycle_disposition_counts": profile["lifecycle_disposition_counts"],
                "semantic_status_counts": profile["semantic_status_counts"],
                "integrity_gap_reason_counts": profile["integrity_gap_reason_counts"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
