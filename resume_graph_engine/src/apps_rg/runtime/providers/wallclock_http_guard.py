"""Hard wall-clock HTTP guards, daemon worker pools, and lane cancellation isolation."""
from __future__ import annotations

import io
import os
import queue
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from apps_rg.runtime.section_model_limits import runtime_limit_float

_LANE_CANCEL_TLS = threading.local()
_CANCELLED_DIRS_LOCK = threading.Lock()
_CANCELLED_ARTIFACT_DIRS: set[str] = set()


def current_cancel_event() -> threading.Event | None:
    """Return the active lane cancellation event bound to the current thread, if any."""
    ev = getattr(_LANE_CANCEL_TLS, "cancel_event", None)
    return ev if isinstance(ev, threading.Event) else None


def is_lane_cancelled() -> bool:
    """Return True when the current worker thread belongs to a timed-out/cancelled lane."""
    ev = current_cancel_event()
    return bool(ev is not None and ev.is_set())


@contextmanager
def lane_cancellation_scope(cancel_event: threading.Event | None) -> Iterator[None]:
    """Bind a lane cancellation event to thread-local storage for the duration of a task."""
    prior = getattr(_LANE_CANCEL_TLS, "cancel_event", None)
    _LANE_CANCEL_TLS.cancel_event = cancel_event
    try:
        yield
    finally:
        _LANE_CANCEL_TLS.cancel_event = prior


def _norm_dir_key(path: Path | str) -> str:
    try:
        return str(Path(path).expanduser().resolve(strict=False))
    except OSError:
        return str(Path(path).absolute())


def mark_artifact_dir_cancelled(path: Path | str | None) -> None:
    """Quarantine an artifact directory after lane timeout so late workers cannot write to it."""
    if path is None or not str(path).strip():
        return
    key = _norm_dir_key(path)
    with _CANCELLED_DIRS_LOCK:
        _CANCELLED_ARTIFACT_DIRS.add(key)


def clear_cancelled_artifact_dirs() -> None:
    """Clear quarantined artifact directories (used by isolated unit tests)."""
    with _CANCELLED_DIRS_LOCK:
        _CANCELLED_ARTIFACT_DIRS.clear()


def is_lane_or_dir_cancelled(path: Path | str | None = None) -> bool:
    """Return True when the caller's lane is cancelled or ``path`` is under a cancelled dir."""
    if is_lane_cancelled():
        return True
    if path is None or not str(path).strip():
        return False
    target = _norm_dir_key(path)
    with _CANCELLED_DIRS_LOCK:
        if not _CANCELLED_ARTIFACT_DIRS:
            return False
        snapshot = tuple(_CANCELLED_ARTIFACT_DIRS)
    sep = os.sep
    for root in snapshot:
        if target == root or target.startswith(root + sep):
            return True
    return False


class DaemonWorkerPool:
    """Thread pool backed exclusively by daemon threads so abandoned calls never hang exit."""

    def __init__(self, max_workers: int = 1, *, thread_name_prefix: str = "apps-rg-daemon") -> None:
        self._max_workers = max(1, int(max_workers or 1))
        self._prefix = thread_name_prefix
        self._queue: queue.Queue[tuple[Future[Any], Callable[..., Any], tuple[Any, ...], dict[str, Any], threading.Event | None] | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._shutdown = False

    def _ensure_worker_capacity(self) -> None:
        with self._lock:
            if len(self._threads) >= self._max_workers:
                return
            idx = len(self._threads)
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"{self._prefix}-{idx}",
                daemon=True,
            )
            self._threads.append(worker)
            worker.start()

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            fut, fn, args, kwargs, cancel_ev = item
            if not fut.set_running_or_notify_cancel():
                continue
            if cancel_ev is not None and cancel_ev.is_set():
                fut.set_exception(TimeoutError("Lane worker cancelled before execution"))
                continue
            try:
                with lane_cancellation_scope(cancel_ev):
                    result = fn(*args, **kwargs)
            except BaseException as exc:  # guardian: allow-broad-exception -- propagate exact worker exception into Future
                fut.set_exception(exc)
            else:
                fut.set_result(result)

    def submit(
        self,
        fn: Callable[..., Any],
        /,
        *args: Any,
        cancel_event: threading.Event | None = None,
        **kwargs: Any,
    ) -> Future[Any]:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Cannot schedule new futures after DaemonWorkerPool shutdown")
        inherited = cancel_event if cancel_event is not None else current_cancel_event()
        fut: Future[Any] = Future()
        self._queue.put((fut, fn, args, kwargs, inherited))
        self._ensure_worker_capacity()
        return fut

    def shutdown(self, wait: bool = False, *, cancel_futures: bool = False) -> None:
        with self._lock:
            already_shutdown = self._shutdown
            self._shutdown = True
            threads = list(self._threads)
        if cancel_futures:
            while True:
                try:
                    queued = self._queue.get_nowait()
                except queue.Empty:
                    break
                if queued is not None:
                    queued[0].cancel()
        if not already_shutdown:
            for _ in threads:
                self._queue.put(None)
        if wait:
            for t in threads:
                t.join()

    def __enter__(self) -> DaemonWorkerPool:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.shutdown(wait=False, cancel_futures=exc_type is not None)


class _BufferedHTTPResponse:
    """In-memory HTTP response returned after complete body read within wall-clock budget."""

    def __init__(
        self,
        body: Any,
        *,
        status: int = 200,
        headers: Any = None,
        url: str = "",
    ) -> None:
        self._raw_body = body
        self._stream = io.BytesIO(bytes(body)) if isinstance(body, (bytes, bytearray)) else None
        self._consumed = False
        self.status = int(status)
        self.code = int(status)
        self.headers = headers if headers is not None else {}
        self.url = url

    def read(self, amt: int | None = None) -> Any:
        if self._stream is not None:
            return self._stream.read() if amt is None else self._stream.read(amt)
        if self._consumed:
            return b""
        self._consumed = True
        return self._raw_body

    def getcode(self) -> int:
        return self.status

    def info(self) -> Any:
        return self.headers

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()

    def __enter__(self) -> _BufferedHTTPResponse:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def urlopen_with_wallclock_cap(
    request: Any,
    *,
    timeout: float,
    opener: Callable[..., Any],
) -> _BufferedHTTPResponse:
    """Execute ``opener(request, timeout=...)`` + ``.read()`` under a strict total wall-clock cap."""
    if is_lane_cancelled():
        raise TimeoutError("Provider HTTP aborted because owning lane was cancelled")
    budget = max(0.05, float(timeout))
    inherited_cancel = current_cancel_event()
    done_ev = threading.Event()
    result_box: list[tuple[str, Any]] = []
    active_resp: list[Any] = []

    def _runner() -> None:
        try:
            with lane_cancellation_scope(inherited_cancel):
                raw_resp = opener(request, timeout=budget)
                active_resp.append(raw_resp)
                if hasattr(raw_resp, "__enter__"):
                    with raw_resp as resp:
                        body = resp.read()
                        status = int(getattr(resp, "status", None) or getattr(resp, "code", None) or 200)
                        headers = getattr(resp, "headers", None)
                        url = str(getattr(resp, "url", "") or (resp.geturl() if hasattr(resp, "geturl") else ""))
                else:
                    try:
                        body = raw_resp.read()
                        status = int(getattr(raw_resp, "status", None) or getattr(raw_resp, "code", None) or 200)
                        headers = getattr(raw_resp, "headers", None)
                        url = str(getattr(raw_resp, "url", "") or "")
                    finally:
                        if hasattr(raw_resp, "close"):
                            raw_resp.close()
                result_box.append(("ok", _BufferedHTTPResponse(body, status=status, headers=headers, url=url)))
        except HTTPError as exc:
            try:
                err_bytes = exc.read()
                exc.fp = io.BytesIO(err_bytes if isinstance(err_bytes, (bytes, bytearray)) else str(err_bytes).encode("utf-8"))
            except OSError:
                pass
            result_box.append(("error", exc))
        except BaseException as exc:  # guardian: allow-broad-exception -- capture transport failure for caller thread
            result_box.append(("error", exc))
        finally:
            done_ev.set()

    worker = threading.Thread(target=_runner, name="apps-rg-http-wallclock", daemon=True)
    deadline = time.monotonic() + budget
    worker.start()
    while not done_ev.is_set():
        if inherited_cancel is not None and inherited_cancel.is_set():
            for resp_obj in active_resp:
                try:
                    resp_obj.close()
                except Exception:  # guardian: allow-broad-exception -- best-effort socket close on cancellation
                    pass
            raise TimeoutError("Provider HTTP cancelled after lane timeout")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            for resp_obj in active_resp:
                try:
                    resp_obj.close()
                except Exception:  # guardian: allow-broad-exception -- best-effort socket close on wall-clock cutoff
                    pass
            raise TimeoutError(f"Provider HTTP wall-clock timeout after {budget:.2f}s")
        done_ev.wait(timeout=min(0.05, remaining))

    if not result_box:
        raise TimeoutError("Provider HTTP worker exited without result")
    kind, payload = result_box[0]
    if kind == "error":
        raise payload
    return payload


def _env_or_ssot_seconds(env_key: str, ssot_path: str, fallback: float) -> float:
    from apps_rg.config.runtime_env import get_runtime_env_str

    raw = (get_runtime_env_str(env_key, "") or "").strip()
    if raw:
        try:
            val = float(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    try:
        return max(0.05, runtime_limit_float(ssot_path))
    except Exception:  # guardian: allow-broad-exception -- emergency fallback if SSOT unavailable in thin unit test
        return fallback


def resolve_section_lane_timeout_s(override: float | None = None) -> float:
    """Resolve hard per-lane wall-clock deadline for Phase-1 section dispatch."""
    if override is not None and float(override) > 0:
        return float(override)
    return _env_or_ssot_seconds(
        "APPS_RG_SECTION_LANE_TIMEOUT_SECONDS",
        "section_dispatch.lane_timeout_seconds",
        300.0,  # ssot: exempt(HARDCODED_TIMEOUT)
    )


def resolve_section_run_timeout_s(override: float | None = None) -> float:
    """Resolve hard whole-run wall-clock deadline for Phase-1 section dispatch."""
    if override is not None and float(override) > 0:
        return float(override)
    return _env_or_ssot_seconds(
        "APPS_RG_SECTION_RUN_TIMEOUT_SECONDS",
        "section_dispatch.run_timeout_seconds",
        900.0,  # ssot: exempt(HARDCODED_TIMEOUT)
    )


def resolve_judge_total_budget_s(override: float | None = None) -> float:
    """Resolve cumulative retry + backoff wall-clock ceiling for one judge evaluation."""
    if override is not None and float(override) > 0:
        return float(override)
    return _env_or_ssot_seconds(
        "APPS_RG_JUDGE_TOTAL_BUDGET_SECONDS",
        "judge_http.total_budget_seconds",
        150.0,  # ssot: exempt(HARDCODED_TIMEOUT)
    )
