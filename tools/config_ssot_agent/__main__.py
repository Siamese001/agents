"""Executable module entrypoint for python -m tools.config_ssot_agent."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
