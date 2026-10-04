"""CLI entrypoint when resume_engine is executed as a module (python -m resume_engine)."""

import sys
from resume_engine.cli import main

if __name__ == "__main__":
    sys.exit(main())
