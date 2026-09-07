from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("APPS_RG_SKIP_DOTENV_AUTOLOAD", "1")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apps_rg.evals.gpu_embedding_residency_w2 import run_residency_proof  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove C0, C0.3, and R1B reuse one local resident BGE-M3 runtime."
    )
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt, path = run_residency_proof(
        repository_root=args.repository_root,
        output=args.output,
    )
    before = receipt["resident_runtime_before_unload"]
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "receipt_path": str(path),
                "receipt_sha256": receipt["receipt_sha256"],
                "model_load_count": before["model_load_count"],
                "registry_size_before_unload": before["registry_size"],
                "lifecycle_after_unload": receipt["lifecycle_after_unload"],
                "runtime": before["runtimes"][0],
                "scope": receipt["scope"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
