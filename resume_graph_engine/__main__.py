"""CLI entrypoint when resume_graph_engine is executed as a module (python -m resume_graph_engine)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import secrets

# Ensure local dev route signing secrets exist if not supplied in environment
if not os.environ.get("APPS_RG_ROUTE_HMAC_SECRET"):
    os.environ["APPS_RG_ROUTE_HMAC_SECRET"] = secrets.token_hex(32)
if not os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID"):
    os.environ["APPS_RG_ROUTE_HMAC_KEY_ID"] = f"session-key-{secrets.token_hex(8)}"

import resume_graph_engine
from apps_rg.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], prog="python -m resume_graph_engine"))

