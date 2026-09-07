"""Run the read-only apps_rg W0 BGE-M3 GPU baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.gpu_embedding_baseline_w0 import (  # noqa: E402
    GpuEmbeddingBaselineError,
    resolve_output_path,
    run_baseline,
    write_receipt,
)


def _default_model_path() -> Path:
    explicit = os.environ.get("APPS_RG_EMBEDDING_MODEL_PATH", "").strip()
    if explicit:
        return Path(explicit)
    revision = "5617a9f61b028005a4858fdac845db406aefb181"
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return hf_home / "hub" / "models--BAAI--bge-m3" / "snapshots" / revision


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the four governed apps_rg BGE-M3 workload shapes on cuda:0; "
            "writes only beneath .runtime and makes no retrieval-quality claim."
        )
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--model-path", type=Path, default=_default_model_path())
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--warm-repetitions", type=int, default=5)
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON file or directory beneath <repository>/.runtime",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repository_root = args.repository_root.resolve()
        output = resolve_output_path(repository_root, args.output)
        receipt = run_baseline(
            repository_root=repository_root,
            model_path=args.model_path,
            device=str(args.device),
            warm_repetitions=int(args.warm_repetitions),
        )
        write_receipt(output, receipt)
    except (GpuEmbeddingBaselineError, OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "apps_rg.gpu_embedding_baseline_w0.failure.v1",
                    "status": "FAIL",
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "receipt_path": str(output),
                "receipt_sha256": receipt["receipt_sha256"],
                "gpu": receipt["runtime"]["gpu"],
                "model": {
                    "model_id": receipt["model"]["model_id"],
                    "revision": receipt["model"]["revision"],
                    "load_elapsed_ms": receipt["model"]["load_elapsed_ms"],
                },
                "workloads": [
                    {
                        "workload_id": row["workload_id"],
                        "text_count": row["text_count"],
                        "cold_first_pass_ms": row["cold_first_pass"]["elapsed_ms"],
                        "warm_p50_ms": row["warm"]["p50_ms"],
                        "warm_p95_ms": row["warm"]["p95_ms"],
                        "warm_p50_texts_per_second": row["warm"][
                            "p50_texts_per_second"
                        ],
                        "peak_allocated_mib": row["cuda_memory"]["peak_allocated_mib"],
                    }
                    for row in receipt["workloads"]
                ],
                "scope": receipt["scope"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
