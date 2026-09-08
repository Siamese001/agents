"""apps_research is a governed internal library, not an operator CLI entrypoint.

The sole public Apps RG resume command is:
    python -m apps_rg run
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    sys.stderr.write(
        "APPS_RG_CLI_VIOLATION: apps_research is an internal engine, not an operator CLI entrypoint.\n"
        "Use the sole canonical public command: python -m apps_rg run\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
