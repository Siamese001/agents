"""Retire or verify retired malformed C0.3 per-skill embedding artifacts."""

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

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (  # noqa: E402
    file_sha256,
)
from apps_rg.fact_inventory.c03_legacy_embedding_retirement_wave5 import (  # noqa: E402
    CONTRACT_PATH,
    GRAPH_PATH,
    LEGACY_ARTIFACT_DIR,
    REGISTRY_PATH,
    RETIREMENT_MARKER_PATH,
    W4_RECEIPT_PATH,
    W5_RECEIPT_PATH,
    build_retirement_marker,
    build_w5_receipt,
    frozen_legacy_inventory,
    validate_retirement_contract,
    validate_retirement_marker,
    validate_w5_receipt,
)

DEFAULT_BASELINE_REF = "3e2fcaf47d37789688ad4fd6b2cc7ce2972423b4"


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


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(f"{path.suffix}.tmp")
    staging.write_bytes(payload)
    staging.replace(path)


def _actual_legacy_files(repo_root: Path) -> list[Path]:
    directory = (repo_root / LEGACY_ARTIFACT_DIR).resolve()
    if not directory.exists():
        return []
    return sorted(
        (path for path in directory.rglob("*") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


def _validate_pre_retirement_inventory(
    repo_root: Path,
    frozen: list[dict[str, Any]],
) -> list[Path]:
    expected = {str(item["path"]): item for item in frozen}
    actual_paths = _actual_legacy_files(repo_root)
    actual = {path.relative_to(repo_root).as_posix(): path for path in actual_paths}
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        raise SystemExit(
            f"Legacy inventory differs from W4 freeze; missing={missing}, "
            f"unexpected={unexpected}"
        )
    for relative, path in actual.items():
        record = expected[relative]
        if path.stat().st_size != int(record["size_bytes"]):
            raise SystemExit(f"Legacy artifact size drift: {relative}")
        if file_sha256(path) != str(record["file_sha256"]):
            raise SystemExit(f"Legacy artifact digest drift: {relative}")
    return actual_paths


def _delete_exact_legacy_inventory(repo_root: Path, paths: list[Path]) -> None:
    directory = (repo_root / LEGACY_ARTIFACT_DIR).resolve()
    for path in paths:
        resolved = path.resolve()
        try:
            resolved.relative_to(directory)
        except ValueError as exc:
            raise SystemExit(
                f"Refusing deletion outside legacy directory: {resolved}"
            ) from exc
        resolved.unlink()
    remaining = _actual_legacy_files(repo_root)
    if remaining:
        raise SystemExit(
            "Legacy artifact deletion left files behind: "
            + ", ".join(str(path) for path in remaining)
        )
    if directory.exists():
        children = list(directory.iterdir())
        if children:
            raise SystemExit(
                "Legacy artifact directory contains unexpected non-file entries: "
                + ", ".join(str(path) for path in children)
            )
        directory.rmdir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--baseline-ref", default=DEFAULT_BASELINE_REF)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    contract = _load_json(repo_root / CONTRACT_PATH)
    validate_retirement_contract(contract)
    graph_bytes = _git_bytes(repo_root, args.baseline_ref, GRAPH_PATH)
    registry_bytes = _git_bytes(repo_root, args.baseline_ref, REGISTRY_PATH)
    w4_receipt_bytes = _git_bytes(repo_root, args.baseline_ref, W4_RECEIPT_PATH)
    registry = _load_json_bytes(registry_bytes, REGISTRY_PATH.as_posix())
    w4_receipt = _load_json_bytes(w4_receipt_bytes, W4_RECEIPT_PATH.as_posix())
    frozen = frozen_legacy_inventory(w4_receipt)
    source_tree = _git_value(repo_root, "rev-parse", f"{args.baseline_ref}^{{tree}}")
    git_blobs = {
        str(item["path"]): _git_value(
            repo_root,
            "rev-parse",
            f"{args.baseline_ref}:{item['path']}",
        )
        for item in frozen
    }
    marker = build_retirement_marker(
        w4_receipt=w4_receipt,
        registry=registry,
        source_commit=args.baseline_ref,
        source_tree=source_tree,
        git_blob_sha1_by_path=git_blobs,
    )
    validate_retirement_marker(marker)
    receipt = build_w5_receipt(
        contract=contract,
        marker=marker,
        w4_receipt=w4_receipt,
        registry=registry,
        source_commit=args.baseline_ref,
        source_tree=source_tree,
    )
    validate_w5_receipt(receipt)

    if (repo_root / GRAPH_PATH).read_bytes() != graph_bytes:
        raise SystemExit("Canonical graph changed after the W4 baseline")
    if (repo_root / REGISTRY_PATH).read_bytes() != registry_bytes:
        raise SystemExit("W4 cluster registry changed after the W4 baseline")
    if (repo_root / W4_RECEIPT_PATH).read_bytes() != w4_receipt_bytes:
        raise SystemExit("W4 receipt changed after the W4 baseline")

    marker_path = repo_root / RETIREMENT_MARKER_PATH
    receipt_path = repo_root / W5_RECEIPT_PATH
    marker_bytes = _render_json(marker)
    receipt_bytes = _render_json(receipt)
    if args.write:
        deletion_paths = _validate_pre_retirement_inventory(repo_root, frozen)
        _delete_exact_legacy_inventory(repo_root, deletion_paths)
        _write_atomic(marker_path, marker_bytes)
        _write_atomic(receipt_path, receipt_bytes)
    else:
        remaining = _actual_legacy_files(repo_root)
        if remaining:
            raise SystemExit(
                "Retired legacy artifacts remain: "
                + ", ".join(
                    path.relative_to(repo_root).as_posix() for path in remaining
                )
            )
        stale = []
        if not marker_path.is_file() or marker_path.read_bytes() != marker_bytes:
            stale.append(RETIREMENT_MARKER_PATH.as_posix())
        if not receipt_path.is_file() or receipt_path.read_bytes() != receipt_bytes:
            stale.append(W5_RECEIPT_PATH.as_posix())
        if stale:
            raise SystemExit(f"W5 outputs are missing or stale: {stale}")

    print(
        json.dumps(
            {
                "status": "PASS",
                "completion_marker": receipt["completion_marker"],
                "retirement_sha256": marker["retirement_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "deleted_artifact_count": marker["retired_artifact_count"],
                "deleted_total_size_bytes": marker["retired_total_size_bytes"],
                "remaining_legacy_file_count": len(_actual_legacy_files(repo_root)),
                "replacement_vectors_generated": False,
                "production_promotion_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
