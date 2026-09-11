"""CLI entrypoint when outreach_engine is executed as a module (python -m outreach_engine)."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure paths are bootstrapped
_PKG_ROOT = Path(__file__).resolve().parent
_SRC_ROOT = _PKG_ROOT / "src"
_REPO_ROOT = _PKG_ROOT.parent

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SHARED_SRC = _REPO_ROOT / "resume_graph_engine" / "src"
if _SHARED_SRC.is_dir() and str(_SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(_SHARED_SRC))

from apps_lic.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
