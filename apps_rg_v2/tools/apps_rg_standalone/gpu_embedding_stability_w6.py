from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("APPS_RG_SKIP_DOTENV_AUTOLOAD", "1")

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apps_rg.evals.gpu_embedding_stability_w6 import (  # noqa: E402
    GpuEmbeddingStabilityError,
    run_stability_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run W6 concurrent and sustained GPU embedding stability gates."
    )
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cycles", type=int)
    args = parser.parse_args()
    try:
        receipt, path = run_stability_benchmark(
            repository_root=args.repository_root,
            output=args.output,
            cycles=args.cycles,
        )
    except (GpuEmbeddingStabilityError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "receipt_path": str(path),
                "receipt_sha256": receipt["receipt_sha256"],
                "runtime": receipt["runtime"],
                "cycles": receipt["cycles"],
                "workload_stability": receipt["workload_stability"],
                "memory_stability": receipt["memory_stability"],
                "lifecycle_after_unload": receipt["lifecycle_after_unload"],
                "scope": receipt["scope"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
