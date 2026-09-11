"""CLI entrypoint when agents is executed as a module (python -m agents)."""

from __future__ import annotations

import sys
from agents.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
