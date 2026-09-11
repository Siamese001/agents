"""CLI Entrypoint for outreach_engine."""
import sys
from apps_lic.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
