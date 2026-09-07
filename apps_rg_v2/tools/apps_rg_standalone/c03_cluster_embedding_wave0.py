"""Build or verify the deterministic C0.3 cluster-embedding Wave 0 receipt."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.fact_inventory.c03_cluster_embedding_wave0 import (  # noqa: E402
    build_wave0_receipt,
    validate_wave0_receipt,
)

DEFAULT_OUTPUT = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave0_baseline_receipt.json"
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


def _serialized(receipt: dict[str, object]) -> bytes:
    return (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-ref", default="origin/main")
    parser.add_argument("--source-commit")
    parser.add_argument("--source-tree")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the checked-in receipt differs from a fresh build.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    source_commit = args.source_commit or _git_value(
        repo_root, "rev-parse", args.source_ref
    )
    source_tree = args.source_tree or _git_value(
        repo_root, "rev-parse", f"{args.source_ref}^{{tree}}"
    )
    receipt = build_wave0_receipt(
        repo_root,
        source_commit=source_commit,
        source_tree=source_tree,
        source_ref=args.source_ref,
    )
    validate_wave0_receipt(receipt)
    payload = _serialized(receipt)
    output_path = (repo_root / args.output).resolve()

    if args.check:
        if not output_path.is_file() or output_path.read_bytes() != payload:
            raise SystemExit(f"Wave 0 receipt is missing or stale: {output_path}")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "completion_marker": receipt["completion_marker"],
                    "receipt_sha256": receipt["receipt_sha256"],
                    "output": args.output.as_posix(),
                },
                sort_keys=True,
            )
        )
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = output_path.with_suffix(f"{output_path.suffix}.tmp")
    staging.write_bytes(payload)
    staging.replace(output_path)
    print(
        json.dumps(
            {
                "status": "PASS",
                "completion_marker": receipt["completion_marker"],
                "receipt_sha256": receipt["receipt_sha256"],
                "output": args.output.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
