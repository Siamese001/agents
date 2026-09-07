"""Apply or verify C0.3 graph authority reconciliation Wave 3."""

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

from apps_rg.fact_inventory.c03_graph_authority_reconciliation_wave3 import (  # noqa: E402
    AUTHORITY_RECONCILIATION_CONTRACT_PATH,
    GRAPH_PATH,
    W2_RECEIPT_PATH,
    authority_reconciliation_profile,
    build_w3_receipt,
    reconcile_graph_authority_wave3,
    validate_authority_reconciliation_contract,
    validate_w3_receipt,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (  # noqa: E402
    LEGACY_ARTIFACT_DIR,
    canonical_sha256,
    file_sha256,
)
from apps_rg.fact_inventory.c03_legacy_embedding_retirement_wave5 import (  # noqa: E402
    RETIREMENT_MARKER_PATH,
    historical_legacy_inventory_from_marker,
)

DEFAULT_BASELINE_REF = "d1cac4f592e76d0e6ad9f565fba927cf855eeb29"
DEFAULT_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave3_authority_reconciliation_receipt.json"
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
        retirement_path = repo_root / RETIREMENT_MARKER_PATH
        if not retirement_path.is_file():
            raise SystemExit(f"Legacy artifact directory is missing: {root}")
        return historical_legacy_inventory_from_marker(_load_json(retirement_path))
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


def _historical_references(
    repo_root: Path,
    retired_edge_ids: list[str],
) -> list[str]:
    if not retired_edge_ids:
        return []
    result = subprocess.run(
        [
            "git",
            "grep",
            "-l",
            "-F",
            "-f",
            "-",
            "--",
            ".",
            f":(exclude){GRAPH_PATH.as_posix()}",
            ":(exclude)artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/**",
        ],
        cwd=repo_root,
        input="\n".join(retired_edge_ids) + "\n",
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise SystemExit(f"Unable to audit historical edge references: {result.stderr}")
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


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
    contract = _load_json(repo_root / AUTHORITY_RECONCILIATION_CONTRACT_PATH)
    validate_authority_reconciliation_contract(contract)
    w2_receipt = _load_json(repo_root / W2_RECEIPT_PATH)
    legacy_records = _legacy_records(repo_root)
    frozen_legacy = (w2_receipt.get("legacy_embedding_artifacts") or {}).get(
        "artifacts"
    )
    if legacy_records != frozen_legacy:
        raise SystemExit("Legacy embedding artifacts changed after the Wave 2 freeze")
    after_graph = reconcile_graph_authority_wave3(before_graph)
    before_edge_ids = {
        str(edge.get("edge_id") or "") for edge in before_graph.get("graph_edges") or []
    }
    after_edge_ids = {
        str(edge.get("edge_id") or "") for edge in after_graph.get("graph_edges") or []
    }
    historical_refs = _historical_references(
        repo_root, sorted(before_edge_ids - after_edge_ids)
    )
    source_tree = _git_value(repo_root, "rev-parse", f"{args.baseline_ref}^{{tree}}")
    receipt = build_w3_receipt(
        before_graph=before_graph,
        after_graph=after_graph,
        contract=contract,
        w2_receipt=w2_receipt,
        legacy_artifacts=legacy_records,
        historical_retired_edge_references=historical_refs,
        source_commit=args.baseline_ref,
        source_tree=source_tree,
    )
    validate_w3_receipt(receipt)
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
            raise SystemExit(f"W3 outputs are missing or stale: {stale}")
    else:
        _write_atomic(graph_path, graph_bytes)
        _write_atomic(receipt_path, receipt_bytes)

    profile = authority_reconciliation_profile(after_graph)
    reconciliation = receipt["reconciliation"]
    print(
        json.dumps(
            {
                "status": "PASS",
                "completion_marker": receipt["completion_marker"],
                "receipt_sha256": receipt["receipt_sha256"],
                "graph_sha256": receipt["after"]["graph_canonical_sha256"],
                "node_count": profile["node_count"],
                "edge_count": profile["edge_count"],
                "skill_row_count": profile["skill_row_count"],
                "retired_edge_count": reconciliation["retired_edge_count"],
                "added_edge_count": reconciliation["added_edge_count"],
                "authority_issue_count": profile["authority_issue_count"],
                "historical_reference_file_count": len(historical_refs),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
