"""CLI entrypoint when outreach_engine is executed as a module (python -m outreach_engine)."""

from __future__ import annotations

import sys
from pathlib import Path

import outreach_engine
from apps_lic.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
