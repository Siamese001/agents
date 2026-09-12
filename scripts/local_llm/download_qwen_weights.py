#!/usr/bin/env python3
"""Download Qwen 27B 4-bit weights from Hugging Face for Apple Silicon (MLX / GGUF)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from huggingface_hub import snapshot_download


DEFAULT_REPO_ID = "mlx-community/Qwen3.8-27B-4bit"


def download_weights(repo_id: str = DEFAULT_REPO_ID, local_dir: str | None = None) -> Path:
    print(f"Starting download of weights from {repo_id}...")
    start_time = time.time()
    
    download_kwargs = {
        "repo_id": repo_id,
        "resume_download": True,
        "max_workers": 8,
    }
    if local_dir:
        download_kwargs["local_dir"] = local_dir

    cached_path = snapshot_download(**download_kwargs)
    elapsed = time.time() - start_time
    target_path = Path(cached_path).resolve()
    print(f"Successfully downloaded {repo_id} in {elapsed:.1f}s to: {target_path}")
    return target_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Qwen 27B weights for local M5 inference.")
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help=f"HF repo id (default: {DEFAULT_REPO_ID})")
    parser.add_argument("--local-dir", default=None, help="Optional local directory to store model weights")
    args = parser.parse_args()

    try:
        path = download_weights(repo_id=args.repo_id, local_dir=args.local_dir)
        print(f"Model path ready: {path}")
    except Exception as exc:
        print(f"Failed to download weights: {exc}", file=sys.stderr)
        sys.exit(1)
