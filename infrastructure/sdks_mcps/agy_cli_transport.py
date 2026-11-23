"""Keyless, model-pinned LLM transport that shells out to the headless Antigravity CLI (`agy -p`).

Canonical SSOT transport shared across `resume_graph_engine`, `outreach_engine`, `apps_eval`, and `ops_scripts`.

Why: the google-antigravity Python SDK requires a Gemini API key, so IDE-account models cannot be
reached from Python. The headless CLI uses the signed-in Antigravity session instead.

Guarantees enforced here (each one is checked, not assumed):
  * API-key env vars are removed from the child environment, so the call cannot silently use a key.
  * Tools are denied for the session via a session-only --settings file (deny beats allow); the
    call runs in an empty temp directory; any tool call in the result stream fails the call.
  * The model the CLI reports in its `init` event must equal the requested model.
  * The result status must be SUCCESS, with a non-empty conversation id and real token usage
    (so an imitation that skips the model cannot pass).

Note: on some machines `agy` on PATH is the IDE launcher, not this CLI. The CLI binary is therefore
taken from the AGY_CLI_BIN environment variable (or an explicit argument) and verified by its --help banner.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator

AGY_CLI_ENV_VAR = "AGY_CLI_BIN"
AGY_MAX_CONCURRENCY_ENV_VAR = "AGY_CLI_MAX_CONCURRENCY"
DEFAULT_AGY_MAX_CONCURRENCY = 8
_CONCURRENCY_LOCK = threading.Lock()
_CONCURRENCY_LIMIT = DEFAULT_AGY_MAX_CONCURRENCY
_CLI_CONCURRENCY_SEMAPHORE = threading.BoundedSemaphore(DEFAULT_AGY_MAX_CONCURRENCY)
_QUOTA_LOCK = threading.Lock()
_QUOTA_COOLDOWN_UNTIL: dict[str, float] = {}
_QUOTA_ERROR_RE = re.compile(
    r"(?:resource_exhausted|code\s*429|\b429\b|individual quota reached|rate[_\s-]*limit|quota[_\s-]*exceeded)",
    re.IGNORECASE,
)
_QUOTA_RESET_RE = re.compile(
    r"resets\s+in\s+(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?",
    re.IGNORECASE,
)


def resolve_agy_max_concurrency(explicit: int | None = None) -> int:
    """Resolve active concurrency cap for headless `agy -p` calls (explicit > env > default=8)."""
    if explicit is not None:
        return max(1, int(explicit))
    raw = str(os.environ.get(AGY_MAX_CONCURRENCY_ENV_VAR) or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            return DEFAULT_AGY_MAX_CONCURRENCY
    return DEFAULT_AGY_MAX_CONCURRENCY


@contextmanager
def _acquire_cli_slot(max_concurrency: int | None = None) -> Iterator[float]:
    """Acquire a concurrency slot dynamically honoring AGY_CLI_MAX_CONCURRENCY; yields queue_wait_seconds."""
    global _CONCURRENCY_LIMIT, _CLI_CONCURRENCY_SEMAPHORE
    target = resolve_agy_max_concurrency(max_concurrency)
    with _CONCURRENCY_LOCK:
        if target != _CONCURRENCY_LIMIT:
            _CONCURRENCY_LIMIT = target
            _CLI_CONCURRENCY_SEMAPHORE = threading.BoundedSemaphore(target)
        sem = _CLI_CONCURRENCY_SEMAPHORE
    t0 = time.monotonic()
    sem.acquire()
    wait_s = round(time.monotonic() - t0, 4)
    try:
        yield wait_s
    finally:
        sem.release()


KEY_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")
MAX_PROMPT_CHARS = 400_000  # well under macOS ARG_MAX (1 MiB); the prompt is passed as an argv element
NO_TOOLS_SETTINGS: dict[str, Any] = {
    "toolPermission": "request-review",
    "permissions": {
        "allow": [],
        "ask": [],
        "deny": [
            "command(*)", "unsandboxed(*)", "read_file(*)", "write_file(*)",
            "read_url(*)", "execute_url(*)", "mcp(*)",
        ],
    },
}


class AgyTransportError(RuntimeError):
    """Raised for any violated guarantee; the message states which one."""


class AgyQuotaExhaustedError(AgyTransportError):
    """Raised when `agy` reports per-model 429 / RESOURCE_EXHAUSTED quota exhaustion."""


def is_agy_quota_error(exc_or_msg: BaseException | str) -> bool:
    """Return True when an exception or stderr/status message indicates 429 quota exhaustion."""
    if isinstance(exc_or_msg, AgyQuotaExhaustedError):
        return True
    return bool(_QUOTA_ERROR_RE.search(str(exc_or_msg or "")))


def _parse_quota_cooldown_seconds(detail: str, *, default_s: float = 120.0, max_s: float = 600.0) -> float:
    m = _QUOTA_RESET_RE.search(str(detail or ""))
    if m and any(m.groups()):
        hours = int(m.group(1) or 0)
        mins = int(m.group(2) or 0)
        secs = int(m.group(3) or 0)
        parsed = float(hours * 3600 + mins * 60 + secs)
        if parsed > 0:
            return min(max_s, max(30.0, parsed))
    return default_s


def mark_agy_model_quota_exhausted(model_slug: str, detail: str = "", *, ttl_s: float | None = None) -> float:
    """Record an in-process cooldown deadline for an exhausted `agy` model slug."""
    slug = str(model_slug or "").strip()
    if not slug:
        return 0.0
    wait_s = float(ttl_s) if ttl_s is not None and ttl_s > 0 else _parse_quota_cooldown_seconds(detail)
    until = time.monotonic() + wait_s
    with _QUOTA_LOCK:
        _QUOTA_COOLDOWN_UNTIL[slug] = max(_QUOTA_COOLDOWN_UNTIL.get(slug, 0.0), until)
    return wait_s


def is_agy_model_quota_cooled_down(model_slug: str) -> bool:
    """Return True when `model_slug` is currently inside an active 429 cooldown window."""
    slug = str(model_slug or "").strip()
    if not slug:
        return False
    now = time.monotonic()
    with _QUOTA_LOCK:
        until = _QUOTA_COOLDOWN_UNTIL.get(slug)
        if until is None:
            return False
        if now >= until:
            _QUOTA_COOLDOWN_UNTIL.pop(slug, None)
            return False
        return True


def clear_agy_quota_cooldowns() -> None:
    """Reset in-process `agy` model quota cooldown state (primarily for unit tests)."""
    with _QUOTA_LOCK:
        _QUOTA_COOLDOWN_UNTIL.clear()


@dataclass(frozen=True)
class AgyResult:
    model_requested: str
    model_reported: str
    status: str
    response: str
    structured_output: Any
    usage: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float | None = None
    conversation_id: str | None = None
    queue_wait_seconds: float = 0.0


def _verify_banner(path: str) -> None:
    try:
        out = subprocess.run(
            [path, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AgyTransportError(f"cannot run {path}: {exc}") from exc
    banner = (out.stdout or "") + (out.stderr or "")
    if "Usage of agy" not in banner or "--print" not in banner:
        raise AgyTransportError(f"{path} is not the headless Antigravity CLI (missing 'Usage of agy' / --print)")


def resolve_agy_bin(agy_bin: str | os.PathLike[str] | None = None) -> str:
    path = str(agy_bin or os.environ.get(AGY_CLI_ENV_VAR) or "")
    if not path:
        raise AgyTransportError(
            f"agy binary not given: pass agy_bin= or set {AGY_CLI_ENV_VAR} (PATH 'agy' may be the IDE launcher)"
        )
    _verify_banner(path)
    return path


@lru_cache(maxsize=8)
def _ready_cached(path: str) -> str:
    try:
        _verify_banner(path)
    except AgyTransportError as exc:
        return str(exc)
    return ""


def ide_cli_ready(agy_bin: str | os.PathLike[str] | None = None) -> tuple[bool, str]:
    """Cheap readiness check for preflight and credential gates: binary configured and genuine."""
    path = str(agy_bin or os.environ.get(AGY_CLI_ENV_VAR) or "")
    if not path:
        return False, f"{AGY_CLI_ENV_VAR} is not set; the IDE CLI transport needs the headless Antigravity CLI path"
    reason = _ready_cached(path)
    return (not reason), reason


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_MODEL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def parse_models_output(raw: str) -> list[str]:
    """Extract model slugs from `agy models` stdout (strips spinner CR frames and ANSI sequences)."""
    cleaned = _ANSI_ESCAPE_RE.sub("", raw or "")
    seen: list[str] = []
    for segment in re.split(r"[\r\n]+", cleaned):
        line = segment.strip()
        if not line or "Fetching available models" in line:
            continue
        first = line.split(None, 1)[0]
        if _MODEL_SLUG_RE.match(first) and "-" in first and first not in seen:
            seen.append(first)
    return seen


def list_agy_models(
    agy_bin: str | os.PathLike[str] | None = None,
    *,
    timeout_s: int = 30,
    _resolver: Callable[[str | os.PathLike[str] | None], str] | None = None,
) -> list[str]:
    """Query `agy models` using the signed-in OS session (with API-key env vars stripped)."""
    binary = (_resolver or resolve_agy_bin)(agy_bin)
    env = {k: v for k, v in os.environ.items() if k not in KEY_ENV_VARS}
    try:
        proc = subprocess.run(
            [binary, "models"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgyTransportError(f"`agy models` timed out after {timeout_s}s") from exc
    except OSError as exc:
        raise AgyTransportError(f"`agy models` failed to start: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        raise AgyTransportError(f"`agy models` exited with code {proc.returncode} (check CLI sign-in): {detail}")
    models = parse_models_output((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if not models:
        raise AgyTransportError("`agy models` returned zero model slugs (check CLI sign-in)")
    return models


def parse_stream(ndjson: str) -> dict[str, Any]:
    """Reduce stream-json output to init model, distinct tool calls, and the final result event."""
    init_model: str | None = None
    tools: dict[tuple[Any, Any], list[str]] = {}
    result: dict[str, Any] | None = None
    for line in ndjson.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgyTransportError(f"non-JSON line in agy stream: {line[:120]!r}") from exc
        kind = evt.get("event")
        if kind == "init":
            init_model = (evt.get("init") or {}).get("model")
        elif kind == "step_update":
            step = evt.get("step_update") or {}
            if step.get("step_type") == "tool":
                tools.setdefault((step.get("step_index"), step.get("tool_name")), []).append(str(step.get("state")))
        elif kind == "result":
            result = evt.get("result") or {}
    return {"init_model": init_model, "tool_calls": [k[1] for k in tools], "result": result}


def run_agy(
    prompt: str,
    *,
    model: str,
    json_schema: dict[str, Any] | None = None,
    effort: str | None = None,
    timeout_s: int = 600,
    agy_bin: str | os.PathLike[str] | None = None,
    _resolver: Callable[[str | os.PathLike[str] | None], str] | None = None,
) -> AgyResult:
    if not prompt.strip():
        raise AgyTransportError("empty prompt")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise AgyTransportError(f"prompt too large for argv transport: {len(prompt)} chars")
    binary = (_resolver or resolve_agy_bin)(agy_bin)
    env = {k: v for k, v in os.environ.items() if k not in KEY_ENV_VARS}
    with tempfile.TemporaryDirectory(prefix="agy_transport_") as tmp:
        settings = Path(tmp) / "no_tools_settings.json"
        settings.write_text(json.dumps(NO_TOOLS_SETTINGS), encoding="utf-8")
        argv = [binary, "-p", prompt, "--model", model, "--output-format", "stream-json", "--settings", str(settings)]
        norm_effort = str(effort or "").strip().lower()
        if norm_effort in {"low", "medium", "high", "xhigh", "max"} and not model.endswith(
            ("-low", "-medium", "-high", "-xhigh", "-max")
        ):
            argv += ["--effort", norm_effort]
        if json_schema is not None:
            argv += ["--json-schema", json.dumps(json_schema)]
        try:
            with _acquire_cli_slot() as queue_wait_s:
                proc = subprocess.run(
                    argv,
                    cwd=tmp,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=timeout_s,
                    check=False,
                    shell=False,
                )
        except subprocess.TimeoutExpired as exc:
            raise AgyTransportError(f"agy timed out after {timeout_s}s") from exc
        except OSError as exc:
            raise AgyTransportError(f"agy failed to start: {exc}") from exc
        stray = [p.name for p in Path(tmp).iterdir() if p.name != settings.name]
    parsed = parse_stream(proc.stdout)
    res = parsed["result"]
    if proc.returncode != 0 or res is None:
        err_msg = (
            f"agy exit={proc.returncode}, result={'missing' if res is None else res.get('status')}: "
            f"{proc.stderr.strip()[:300]}"
        )
        if is_agy_quota_error(err_msg) or is_agy_quota_error(proc.stderr):
            mark_agy_model_quota_exhausted(model, proc.stderr or err_msg)
            raise AgyQuotaExhaustedError(err_msg)
        raise AgyTransportError(err_msg)
    if res.get("status") != "SUCCESS":
        err_msg = f"agy status={res.get('status')}: {str(res.get('error'))[:300]}"
        if is_agy_quota_error(err_msg) or is_agy_quota_error(proc.stderr):
            mark_agy_model_quota_exhausted(model, f"{err_msg} {proc.stderr}")
            raise AgyQuotaExhaustedError(err_msg)
        raise AgyTransportError(err_msg)
    if parsed["tool_calls"]:
        raise AgyTransportError(f"tool calls attempted despite deny-all settings: {parsed['tool_calls']}")
    if stray:
        raise AgyTransportError(f"files appeared in the isolated cwd: {stray}")
    if parsed["init_model"] != model:
        raise AgyTransportError(f"model mismatch: requested {model!r}, CLI reported {parsed['init_model']!r}")
    usage = dict(res.get("usage") or {})
    if not str(res.get("conversation_id") or "").strip():
        raise AgyTransportError("no conversation id in the CLI result (missing receipt)")
    if not isinstance(usage.get("total_tokens"), (int, float)) or usage["total_tokens"] <= 0:
        raise AgyTransportError("no real token usage in the CLI result (missing receipt)")
    return AgyResult(
        model_requested=model,
        model_reported=str(parsed["init_model"]),
        status="SUCCESS",
        response=str(res.get("response") or ""),
        structured_output=res.get("structured_output"),
        usage=usage,
        duration_seconds=res.get("duration_seconds"),
        conversation_id=str(res.get("conversation_id")),
        queue_wait_seconds=queue_wait_s,
    )


__all__ = [
    "AGY_CLI_ENV_VAR",
    "AGY_MAX_CONCURRENCY_ENV_VAR",
    "AgyQuotaExhaustedError",
    "AgyResult",
    "AgyTransportError",
    "DEFAULT_AGY_MAX_CONCURRENCY",
    "KEY_ENV_VARS",
    "MAX_PROMPT_CHARS",
    "NO_TOOLS_SETTINGS",
    "_acquire_cli_slot",
    "_parse_quota_cooldown_seconds",
    "_ready_cached",
    "_verify_banner",
    "clear_agy_quota_cooldowns",
    "ide_cli_ready",
    "is_agy_model_quota_cooled_down",
    "is_agy_quota_error",
    "list_agy_models",
    "mark_agy_model_quota_exhausted",
    "parse_models_output",
    "parse_stream",
    "resolve_agy_bin",
    "resolve_agy_max_concurrency",
    "run_agy",
    "subprocess",
]
