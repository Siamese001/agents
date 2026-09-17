"""CLI entrypoint when resume_engine is executed as a module (python -m resume_engine)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RG_SRC = _REPO_ROOT / "resume_graph_engine" / "src"

for p in (_REPO_ROOT, _RG_SRC):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

import resume_graph_engine

# Ensure local dev route signing secrets exist if not supplied in environment
if not os.environ.get("APPS_RG_ROUTE_HMAC_SECRET"):
    os.environ["APPS_RG_ROUTE_HMAC_SECRET"] = "agents-local-dev-session-secret"
if not os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID"):
    os.environ["APPS_RG_ROUTE_HMAC_KEY_ID"] = "agents-local-dev-key"

from apps_rg.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], prog="python -m resume_engine"))
