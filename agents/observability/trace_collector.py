"""Thread-safe post-runtime RunTrace collector with PII scrubbing and atomic byte-offset cursor."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.contracts.digests import canonical_sha256, stable_id
from apps_eval.contracts.schemas import RunTrace, utc_now_iso

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_SECRET_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{20,})",
    re.IGNORECASE,
)

DEFAULT_TRACES_REL_PATH = Path("artifacts/learning/run_traces.jsonl")
DEFAULT_CURSOR_REL_PATH = Path("artifacts/learning/run_traces_cursor.json")
MAX_DEDUP_IDS = 1000

logger = logging.getLogger(__name__)


def scrub_pii_text(text: str) -> str:
    """Scrub emails, phone numbers, SSNs, and bearer/API tokens from text."""
    out = _SECRET_RE.sub("[REDACTED_SECRET]", text)
    out = _EMAIL_RE.sub("[REDACTED_EMAIL]", out)
    out = _SSN_RE.sub("[REDACTED_SSN]", out)
    out = _PHONE_RE.sub("[REDACTED_PHONE]", out)
    return out


def scrub_pii(payload: Any) -> Any:
    """Recursively scrub PII and credentials from nested JSON-compatible structures."""
    if isinstance(payload, str):
        return scrub_pii_text(payload)
    if isinstance(payload, Mapping):
        sanitized: dict[str, Any] = {}
        for k, v in payload.items():
            kl = str(k).lower()
            if any(tok in kl for tok in ("api_key", "secret", "token", "password", "authorization")):
                sanitized[str(k)] = "[REDACTED_SECRET]"
            else:
                sanitized[str(k)] = scrub_pii(v)
        return sanitized
    if isinstance(payload, list):
        return [scrub_pii(item) for item in payload]
    if isinstance(payload, tuple):
        return [scrub_pii(item) for item in payload]
    return payload


def build_run_trace(
    *,
    app_id: str,
    run_id: str,
    session_id: str = "default",
    git_sha: str = "0" * 40,
    config_digest: str = "0" * 64,
    terminal_status: str = "PASS",
    raw_input: Mapping[str, Any] | None = None,
    output_summary: Mapping[str, Any] | None = None,
    trajectory_steps: Sequence[Mapping[str, Any]] = (),
    gate_outcomes: Mapping[str, Any] | None = None,
    telemetry: Mapping[str, Any] | None = None,
    user_feedback: Mapping[str, Any] | None = None,
    started_at_utc: str | None = None,
    finished_at_utc: str | None = None,
) -> RunTrace:
    """Construct a PII-scrubbed, canonically digested RunTrace."""
    now = utc_now_iso()
    redacted_in = scrub_pii(dict(raw_input or {}))
    redacted_out = scrub_pii(dict(output_summary or {}))
    redacted_fb = scrub_pii(dict(user_feedback or {}))
    payload_digest = canonical_sha256(redacted_in)
    trace_id = stable_id("trace", app_id, run_id, session_id, payload_digest, finished_at_utc or now, length=16)

    norm_status = str(terminal_status or "PASS").upper()
    if norm_status not in {"PASS", "FAIL", "BLOCKED", "TIMEOUT", "ERROR"}:
        norm_status = "PASS" if norm_status in {"SUCCESS", "COMPLETED", "OK"} else "FAIL"

    return RunTrace(
        trace_id=trace_id,
        app_id=app_id,
        run_id=str(run_id),
        session_id=str(session_id),
        git_sha=str(git_sha),
        config_digest=str(config_digest),
        started_at_utc=started_at_utc or now,
        finished_at_utc=finished_at_utc or now,
        terminal_status=norm_status,  # type: ignore[arg-type]
        input_redacted={
            "payload_digest": payload_digest,
            "redacted_snapshot": redacted_in,
            "pii_scrubbed": True,
        },
        output_summary=redacted_out,
        trajectory_steps=[scrub_pii(dict(s)) for s in trajectory_steps],
        gate_outcomes=scrub_pii(dict(gate_outcomes or {})),
        telemetry=dict(telemetry or {}),
        user_feedback=redacted_fb,
    )


class RunTraceCollector:
    """Thread-safe JSONL writer and atomic O(1) byte-offset cursor reader for RunTraces."""

    def __init__(
        self,
        *,
        traces_path: Path | None = None,
        cursor_path: Path | None = None,
        repo_root: Path | None = None,
    ) -> None:
        base = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[2]
        self.traces_path = Path(traces_path).resolve() if traces_path is not None else (base / DEFAULT_TRACES_REL_PATH)
        self.cursor_path = Path(cursor_path).resolve() if cursor_path is not None else (base / DEFAULT_CURSOR_REL_PATH)
        self._lock = threading.Lock()

    def emit(self, trace: RunTrace) -> Path:
        """Append a single sealed RunTrace line safely."""
        self.traces_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(trace.to_dict(), sort_keys=True, ensure_ascii=False) + "\n"
        with self._lock:
            with self.traces_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
        return self.traces_path

    def _load_cursor(self) -> dict[str, Any]:
        if not self.cursor_path.is_file():
            return {"byte_offset": 0, "line_number": 0, "recent_trace_ids": []}
        try:
            data = json.loads(self.cursor_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "byte_offset": int(data.get("byte_offset", 0)),
                    "line_number": int(data.get("line_number", 0)),
                    "recent_trace_ids": list(data.get("recent_trace_ids") or []),
                }
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Resetting unreadable trace cursor at %s: %s", self.cursor_path, exc)
        return {"byte_offset": 0, "line_number": 0, "recent_trace_ids": []}

    def _save_cursor_atomic(self, cursor: dict[str, Any]) -> None:
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cursor_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cursor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.cursor_path)

    def drain_new_traces(self) -> list[RunTrace]:
        """Read only unseen RunTrace records from byte_offset, deduplicating by trace_id atomically."""
        with self._lock:
            if not self.traces_path.is_file():
                return []
            cursor = self._load_cursor()
            file_size = self.traces_path.stat().st_size
            offset = int(cursor["byte_offset"])
            if offset > file_size:
                offset = 0
                cursor["line_number"] = 0

            seen_ids = list(cursor["recent_trace_ids"])
            seen_set = set(seen_ids)
            drained: list[RunTrace] = []

            with self.traces_path.open("rb") as handle:
                handle.seek(offset)
                while True:
                    raw_line = handle.readline()
                    if not raw_line:
                        break
                    offset = handle.tell()
                    cursor["line_number"] = int(cursor["line_number"]) + 1
                    text = raw_line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    try:
                        parsed = json.loads(text)
                        trace = RunTrace.from_dict(parsed)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue
                    if trace.trace_id in seen_set:
                        continue
                    seen_set.add(trace.trace_id)
                    seen_ids.append(trace.trace_id)
                    drained.append(trace)

            cursor["byte_offset"] = offset
            cursor["recent_trace_ids"] = seen_ids[-MAX_DEDUP_IDS:]
            self._save_cursor_atomic(cursor)
            return drained


def emit_post_run_trace_safe(
    *,
    app_id: str,
    run_id: str,
    terminal_status: str,
    session_id: str = "default",
    raw_input: Mapping[str, Any] | None = None,
    output_summary: Mapping[str, Any] | None = None,
    trajectory_steps: Sequence[Mapping[str, Any]] = (),
    gate_outcomes: Mapping[str, Any] | None = None,
    telemetry: Mapping[str, Any] | None = None,
    user_feedback: Mapping[str, Any] | None = None,
    traces_path: Path | None = None,
    repo_root: Path | None = None,
) -> RunTrace | None:
    """Fail-safe observer hook to emit a scrubbed RunTrace from any runtime exit seam."""
    if os.environ.get("PYTEST_CURRENT_TEST") and traces_path is None and os.environ.get("AGENTS_TRACE_IN_PYTEST") != "1":
        return None
    try:
        trace = build_run_trace(
            app_id=app_id,
            run_id=run_id,
            session_id=session_id,
            terminal_status=terminal_status,
            raw_input=raw_input,
            output_summary=output_summary,
            trajectory_steps=trajectory_steps,
            gate_outcomes=gate_outcomes,
            telemetry=telemetry,
            user_feedback=user_feedback,
        )
        RunTraceCollector(traces_path=traces_path, repo_root=repo_root).emit(trace)
        return trace
    except (OSError, ValueError, TypeError, RuntimeError):  # guardian: allow-silent-swallow -- observer-only trace hook must never fail production runs
        return None
