"""Small atomic writer for evaluator-owned derived artifacts.

Apps Eval output is proof-harness state, not a product-state mutation.  Keeping
this gateway stdlib-only lets post-runtime evaluation run without importing the
product UWG or any provider-adjacent Apps RG runtime package graph.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_text(
    path: str | Path,
    content: str,
    encoding: str = "utf-8",
) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:12]}.tmp")
    try:
        with temporary.open("w", encoding=encoding, newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return str(target)


__all__ = ["ensure_dir", "write_text"]
