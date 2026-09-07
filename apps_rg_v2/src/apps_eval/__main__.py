"""apps_eval is an internal evaluation engine, not an operator CLI entrypoint.

To evaluate a completed product run, use the sole canonical public command:
    python -m apps_rg eval --run-dir <completed-run-dir>
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    sys.stderr.write(
        "APPS_RG_CLI_VIOLATION: apps_eval is an internal engine, not an operator CLI entrypoint.\n"
        "Use the sole canonical public command: python -m apps_rg eval --run-dir <completed_run>\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
