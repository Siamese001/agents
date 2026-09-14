"""CLI entrypoint when resume_graph_engine is executed as a module (python -m resume_graph_engine)."""

from __future__ import annotations

import sys
from pathlib import Path

import resume_graph_engine
from apps_rg.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
