"""CLI entrypoint when outreach_engine is executed as a module (python -m outreach_engine)."""

from __future__ import annotations

import os
import sys
import threading

import outreach_engine  # noqa: F401


def _terminate_cleanly(exit_code: int) -> None:
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except OSError:
        pass
    active = [
        t
        for t in threading.enumerate()
        if t is not threading.main_thread() and not t.daemon and t.is_alive()
    ]
    if active:
        timer = threading.Timer(1.5, lambda: os._exit(exit_code))
        timer.daemon = True
        timer.start()
    sys.exit(exit_code)


if __name__ == "__main__":
    from apps_lic.__main__ import main

    _terminate_cleanly(main(sys.argv[1:], prog="python -m outreach_engine"))
