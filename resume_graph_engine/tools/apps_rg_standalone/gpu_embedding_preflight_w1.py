"""Run the fail-closed apps_rg W1 GPU embedding environment preflight."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

for _name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
    os.environ.setdefault(_name, "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from apps_rg.evals.gpu_embedding_baseline_w0 import resolve_output_path  # noqa: E402
from apps_rg.runtime.gpu_embedding_environment_w1 import (  # noqa: E402
    GpuEmbeddingEnvironmentError,
    build_preflight_receipt,
    collect_observations,
    load_environment_contract,
    write_preflight_receipt,
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
            "Verify the locked apps_rg GPU embedding control: Python, dependency "
            "closure, wheel payloads, Apps RG source revision, GPU, CUDA, offline "
            "policy, and pinned BGE-M3 bytes."
        )
    )
    parser.add_argument("--repository-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--model-path", type=Path, default=_default_model_path())
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON file or directory beneath <repository>/.runtime",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repository_root.resolve()
    default_output = (
        Path(".runtime/apps_rg/gpu-embedding-environment-w1")
        / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        / "receipt.json"
    )
    try:
        output = resolve_output_path(root, args.output or default_output)
        contract = load_environment_contract(root)
        observations = collect_observations(
            repository_root=root,
            contract=contract,
            model_path=args.model_path,
        )
        receipt = build_preflight_receipt(
            repository_root=root,
            contract=contract,
            observations=observations,
        )
        write_preflight_receipt(output, receipt)
    except (GpuEmbeddingEnvironmentError, OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema_version": "apps_rg.gpu_embedding_environment_w1.failure.v1",
                    "status": "FAIL",
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    summary = {
        "status": receipt["status"],
        "receipt_path": str(output),
        "receipt_sha256": receipt["receipt_sha256"],
        "issues": receipt["issues"],
        "python": receipt["observations"]["python"],
        "cuda": receipt["observations"]["cuda"],
        "apps_rg_source": receipt["observations"]["apps_rg_source"],
        "model": receipt["observations"]["model"],
        "scope": receipt["scope"],
    }
    print(json.dumps(summary, indent=2))
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
