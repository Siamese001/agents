"""CLI entrypoint when resume_graph_engine is executed as a module (python -m resume_graph_engine)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure local dev route signing secrets exist if not supplied in environment
if not os.environ.get("APPS_RG_ROUTE_HMAC_SECRET"):
    os.environ["APPS_RG_ROUTE_HMAC_SECRET"] = "agents-local-dev-session-secret"
if not os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID"):
    os.environ["APPS_RG_ROUTE_HMAC_KEY_ID"] = "agents-local-dev-key"

import resume_graph_engine
from apps_rg.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], prog="python -m resume_graph_engine"))

