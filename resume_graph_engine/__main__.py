"""CLI entrypoint when resume_graph_engine is executed as a module (python -m resume_graph_engine)."""

from __future__ import annotations

import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_SRC_ROOT = _PKG_ROOT / "src"
_REPO_ROOT = _PKG_ROOT.parent

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps_rg.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
