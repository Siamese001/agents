#!/usr/bin/env python3
"""Wrapper CLI for snapshot_graph_sqlite located in resume_graph_engine."""

import sys
from pathlib import Path

# Add resume_graph_engine/tools to sys.path
rge_tools = Path(__file__).resolve().parent.parent.parent / "resume_graph_engine/tools"
if str(rge_tools) not in sys.path:
    sys.path.insert(0, str(rge_tools))

from apps_rg_standalone.snapshot_graph_sqlite import main

if __name__ == "__main__":
    sys.exit(main())
