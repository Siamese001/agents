#!/usr/bin/env python3
"""Download Qwen 27B 4-bit weights from Hugging Face for Apple Silicon (MLX / GGUF)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from huggingface_hub import snapshot_download


def _resolve_default_repo_id() -> str:
    catalog_path = Path(__file__).resolve().parents[2] / "config" / "model_catalog.json"
    if catalog_path.is_file():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            for section in catalog.values():
                if isinstance(section, dict) and "local_27b_mlx" in section:
                    repo_id = str(section.get("local_27b_mlx") or "").strip()
                    if repo_id:
                        return repo_id
        except (OSError, ValueError, TypeError):
            pass
    return "local-mlx/default-27b-4bit"


DEFAULT_REPO_ID = _resolve_default_repo_id()


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
    parser = argparse.ArgumentParser(description="Download 27B weights for local M5 inference.")
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help=f"HF repo id (default: {DEFAULT_REPO_ID})")
    parser.add_argument("--local-dir", default=None, help="Optional local directory to store model weights")
    args = parser.parse_args()

    try:
        path = download_weights(repo_id=args.repo_id, local_dir=args.local_dir)
        print(f"Model path ready: {path}")
    except Exception as exc:
        print(f"Failed to download weights: {exc}", file=sys.stderr)
        sys.exit(1)
