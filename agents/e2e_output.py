"""Output isolation and canonical lifecycle JSON serialization for agents e2e."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterator


class _TeeStream:
    """Stream that captures written bytes into an in-memory buffer and optional file."""

    def __init__(self, file_obj=None) -> None:
        self.file_obj = file_obj
        self.buffer = io.StringIO()

    def write(self, data: str) -> int:
        self.buffer.write(data)
        if self.file_obj:
            try:
                self.file_obj.write(data)
                self.file_obj.flush()
            except Exception:
                pass
        return len(data)

    def flush(self) -> None:
        self.buffer.flush()
        if self.file_obj:
            try:
                self.file_obj.flush()
            except Exception:
                pass

    def getvalue(self) -> str:
        return self.buffer.getvalue()


@contextlib.contextmanager
def isolate_child_output(log_path: Path | str | None = None) -> Iterator[dict[str, str]]:
    """Context manager to isolate child stage output from top-level stdout/stderr.

    All in-process output emitted by sub-engines (print calls, logging handlers)
    is redirected into the specified log file and captured in memory. Top-level
    stdout is preserved clean for authoritative JSON emission.
    """
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    file_obj = None
    captured = {"stdout": "", "stderr": ""}

    if log_path:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            file_obj = open(p, "a", encoding="utf-8", errors="replace")
        except Exception:
            file_obj = None

    stdout_tee = _TeeStream(file_obj)
    stderr_tee = _TeeStream(file_obj)

    # Intercept any root loggers pointing to orig streams
    modified_handlers = []
    for h in logging.root.handlers:
        if isinstance(h, logging.StreamHandler):
            if h.stream is orig_stdout:
                h.stream = stdout_tee
                modified_handlers.append((h, orig_stdout))
            elif h.stream is orig_stderr:
                h.stream = stderr_tee
                modified_handlers.append((h, orig_stderr))

    try:
        sys.stdout = stdout_tee  # type: ignore
        sys.stderr = stderr_tee  # type: ignore
        yield captured
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        captured["stdout"] = stdout_tee.getvalue()
        captured["stderr"] = stderr_tee.getvalue()
        for h, orig_strm in modified_handlers:
            h.stream = orig_strm
        if file_obj:
            try:
                file_obj.close()
            except Exception:
                pass


def emit_authoritative_lifecycle_json(payload: dict[str, Any], stream=None) -> None:
    """Emit exactly one authoritative lifecycle JSON payload to stdout (or provided stream)."""
    target = stream or sys.stdout
    serialized = json.dumps(payload, indent=2, sort_keys=False)
    target.write(serialized + "\n")
    target.flush()
