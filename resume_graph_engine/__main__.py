"""CLI entrypoint when resume_graph_engine is executed as a module (python -m resume_graph_engine)."""

from __future__ import annotations

import sys
from resume_engine.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], prog="python -m resume_graph_engine"))
