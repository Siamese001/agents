"""CLI entrypoint when resume_engine is executed as a module (python -m resume_engine)."""

from __future__ import annotations

import os
import sys
import resume_graph_engine

import secrets

# Ensure local dev route signing secrets exist if not supplied in environment
if not os.environ.get("APPS_RG_ROUTE_HMAC_SECRET"):
    os.environ["APPS_RG_ROUTE_HMAC_SECRET"] = secrets.token_hex(32)
if not os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID"):
    os.environ["APPS_RG_ROUTE_HMAC_KEY_ID"] = f"session-key-{secrets.token_hex(8)}"

from apps_rg.__main__ import main

if __name__ == "__main__":
    print(
        "[SSOT NOTICE] Canonical resume pipeline entrypoint is: python -m apps_rg run\n"
        "[SSOT NOTICE] Delegating to apps_rg.__main__...",
        file=sys.stderr,
    )
    sys.exit(main(sys.argv[1:], prog="python -m resume_engine"))
