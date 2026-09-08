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

from apps_rg.evals.gpu_embedding_batching_w3 import (  # noqa: E402
    GpuEmbeddingBatchingError,
    run_batching_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure bounded production BGE batching on the configured CUDA GPU."
    )
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    try:
        receipt, path = run_batching_benchmark(
            repository_root=args.repository_root,
            output=args.output,
            repetitions=args.repetitions,
        )
    except (GpuEmbeddingBatchingError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "receipt_path": str(path),
                "receipt_sha256": receipt["receipt_sha256"],
                "runtime": receipt["runtime"],
                "benchmarks": [
                    {
                        "benchmark_id": row["benchmark_id"],
                        "text_count": row["text_count"],
                        "selected_batch_size": row["selected_batch_size"],
                        "prior_loop_p50_ms": row["prior_per_item_loop"]["p50_ms"],
                        "batch_p50_ms": row["bounded_batch"]["p50_ms"],
                        "speedup_ratio": row["bounded_batch"]["speedup_ratio"],
                        "peak_allocated_mib": row["cuda_peak"]["allocated_mib"],
                        "minimum_same_index_cosine": row[
                            "ordered_vector_equivalence"
                        ]["minimum_same_index_cosine"],
                    }
                    for row in receipt["benchmarks"]
                ],
                "lifecycle_after_unload": receipt["lifecycle_after_unload"],
                "scope": receipt["scope"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
