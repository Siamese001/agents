"""resume_engine package alias and single unified CLI entrypoint for the resume pipeline."""

from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _REPO_ROOT / "resume_graph_engine" / "src"
for p in (_REPO_ROOT, _SRC_ROOT):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from apps_rg.__main__ import main

__all__ = ["main"]
