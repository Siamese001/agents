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

from apps_rg.evals.gpu_embedding_precision_w4 import (  # noqa: E402
    GpuEmbeddingPrecisionError,
    run_precision_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare FP32, FP16, and BF16 on the governed BGE workloads."
    )
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--explore",
        action="store_true",
        help="Write measured recommendation without requiring the tracked selection to match.",
    )
    args = parser.parse_args()
    try:
        receipt, path = run_precision_benchmark(
            repository_root=args.repository_root,
            output=args.output,
            repetitions=args.repetitions,
            require_config_match=not args.explore,
        )
    except (GpuEmbeddingPrecisionError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "receipt_path": str(path),
                "receipt_sha256": receipt["receipt_sha256"],
                "runtime": receipt["runtime"],
                "profiles": [
                    {
                        "profile_id": profile_id,
                        "dtype": row["dtype"],
                        "aggregate_texts_per_second": row["aggregate"][
                            "p50_texts_per_second"
                        ],
                        "peak_allocated_mib": row["cuda_peak"]["allocated_mib"],
                        "speedup_ratio": receipt["comparisons_to_fp32"][profile_id][
                            "throughput_speedup_ratio"
                        ],
                        "minimum_cosine": receipt["comparisons_to_fp32"][profile_id][
                            "same_index_cosine"
                        ]["minimum"],
                        "exact_top10_order_queries": receipt[
                            "comparisons_to_fp32"
                        ][profile_id]["rank_proxy"]["exact_top10_order_query_count"],
                        "equal_top10_set_queries": receipt[
                            "comparisons_to_fp32"
                        ][profile_id]["rank_proxy"]["equal_top10_set_query_count"],
                        "eligible": receipt["comparisons_to_fp32"][profile_id][
                            "eligible"
                        ],
                        "ineligible_reasons": receipt["comparisons_to_fp32"][
                            profile_id
                        ]["ineligible_reasons"],
                    }
                    for profile_id, row in receipt["profiles"].items()
                ],
                "selection": receipt["selection"],
                "scope": receipt["scope"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
