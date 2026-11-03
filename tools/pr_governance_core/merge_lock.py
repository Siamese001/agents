"""Governed Merge Queue Trunk Reservation Lock.

Provides atomic file locking at .git/governed_merge_queue.lock to serialize
rebasing, readiness qualification, and landing across multiple concurrent
feature branches and worktrees, eliminating convoy thrashing and livelock.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import errno
import fcntl
import json
import logging
import os
import random
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tools.pr_governance_core.merge_lock")

LOCK_FILE_NAME = "governed_merge_queue.lock"
META_FILE_NAME = "governed_merge_queue.json"

_ACTIVE_LOCKS: dict[Path, tuple[str, int]] = {}


class MergeQueueError(RuntimeError):
    """Base error for merge queue operations."""


class LockContentionError(MergeQueueError):
    """Raised when queue lock cannot be acquired within timeout."""


class StaleLockRecoveredError(MergeQueueError):
    """Raised/logged when a stale lock from a dead process is broken."""


@dataclass
class LockInfo:
    """Metadata describing an active merge queue reservation."""

    branch: str
    holder_pid: int
    holder_host: str
    acquired_at: str
    heartbeat_at: str
    timeout_sec: float
    worktree_path: str
    holder_alive: bool = True

    @property
    def pid(self) -> int:
        return self.holder_pid

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockInfo:
        return cls(
            branch=str(data.get("branch", "unknown")),
            holder_pid=int(data.get("holder_pid", 0)),
            holder_host=str(data.get("holder_host", os.environ.get("DEFAULT_HOST", "localhost"))),
            acquired_at=str(data.get("acquired_at", "")),
            heartbeat_at=str(data.get("heartbeat_at", "")),
            timeout_sec=float(data.get("timeout_sec", 300.0)),
            worktree_path=str(data.get("worktree_path", "")),
        )


def _is_pid_alive(pid: int) -> bool:
    """Checks whether the process with given PID is still alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError as err:
        return err.errno == errno.EPERM


def _resolve_from_git_command(cwd: str) -> Optional[Path]:
    from .common import sanitized_git_env

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd,
            env=sanitized_git_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            p = Path(res.stdout.strip()).resolve()
            if p.is_dir():
                return p
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _resolve_from_gitfile(dot_git: Path) -> Optional[Path]:
    if not dot_git.is_file():
        return None
    try:
        content = dot_git.read_text(encoding="utf-8").strip()
        if not content.startswith("gitdir:"):
            return None
        target = Path(content.split(":", 1)[1].strip())
        if not target.is_absolute():
            target = (dot_git.parent / target).resolve()
        if "worktrees" in target.parts:
            return target.parents[1].resolve()
        return target.resolve()
    except (OSError, ValueError, IndexError):
        return None


def resolve_git_common_dir(repo_root: Optional[Path] = None) -> Path:
    """Resolves the shared .git common directory across worktrees."""
    cwd = str(repo_root) if repo_root else os.getcwd()
    cmd_dir = _resolve_from_git_command(cwd)
    if cmd_dir is not None:
        return cmd_dir

    root = repo_root or Path.cwd()
    file_dir = _resolve_from_gitfile(root / ".git")
    if file_dir is not None:
        return file_dir

    return (root / ".git").resolve()


class GovernedMergeQueueLock:
    """Manages an atomic, serialized merge queue reservation lock in .git/."""

    def __init__(
        self,
        branch: str,
        repo_root: Optional[Path] = None,
        timeout_sec: float = 300.0,
        retry_interval_sec: float = 0.15,
        non_blocking: bool = False,
        changed_files: Optional[list[str]] = None,
        has_valid_receipt: Optional[bool] = None,
    ) -> None:
        self.branch = branch
        self.repo_root = repo_root or Path.cwd()
        self.git_common_dir = resolve_git_common_dir(self.repo_root)
        self.timeout_sec = timeout_sec
        self.retry_interval_sec = retry_interval_sec
        self.non_blocking = non_blocking
        self.changed_files = changed_files
        self.has_valid_receipt = has_valid_receipt

        self.lock_file = self.git_common_dir / LOCK_FILE_NAME
        self.meta_file = self.git_common_dir / META_FILE_NAME

        self._fd: Optional[int] = None
        self._acquired: bool = False
        self._hb_stop: Optional[Any] = None
        self._hb_thread: Optional[Any] = None
        self.waited_in_fifo: bool = False

    def is_acquired(self) -> bool:
        return self._acquired

    def _start_heartbeat_thread(self) -> None:
        import threading

        stop_ev = threading.Event()
        self._hb_stop = stop_ev
        interval = max(0.2, min(5.0, self.timeout_sec / 4.0))

        def _loop() -> None:
            while not stop_ev.wait(interval):
                self.heartbeat()

        t = threading.Thread(target=_loop, name=f"mq-hb-{self.branch}", daemon=True)
        self._hb_thread = t
        t.start()

    def _stop_heartbeat_thread(self) -> None:
        if self._hb_stop is not None:
            self._hb_stop.set()
            self._hb_stop = None
        self._hb_thread = None

    def _read_meta(self) -> Optional[LockInfo]:
        if not self.meta_file.is_file():
            return None
        try:
            data = json.loads(self.meta_file.read_text(encoding="utf-8"))
            return LockInfo.from_dict(data)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def _write_meta(self) -> None:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        info = LockInfo(
            branch=self.branch,
            holder_pid=os.getpid(),
            holder_host=os.uname().nodename,
            acquired_at=now_iso,
            heartbeat_at=now_iso,
            timeout_sec=self.timeout_sec,
            worktree_path=str(self.repo_root.resolve()),
        )
        tmp_meta = self.git_common_dir / f"{META_FILE_NAME}.tmp.{os.getpid()}"
        tmp_meta.write_text(json.dumps(info.to_dict(), indent=2), encoding="utf-8")
        tmp_meta.replace(self.meta_file)

    def _check_and_break_stale_lock(self) -> bool:
        """Inspects existing lock. If holder process is dead, breaks stale lock."""
        meta = self._read_meta()
        if meta is None:
            return False

        if not _is_pid_alive(meta.holder_pid):
            logger.warning(
                f"[STALE-LOCK-RECOVERED] Lock holder PID {meta.holder_pid} for branch '{meta.branch}' "
                f"is dead. Forcibly releasing stale lock."
            )
            self._force_release()
            return True

        return self._check_heartbeat_timeout(meta)

    def _check_heartbeat_timeout(self, meta: LockInfo) -> bool:
        try:
            hb_time = dt.datetime.fromisoformat(meta.heartbeat_at)
            age = (dt.datetime.now(dt.timezone.utc) - hb_time).total_seconds()
            if age > meta.timeout_sec:
                logger.warning(
                    f"[STALE-LOCK-TIMEOUT] Lock for branch '{meta.branch}' held by PID {meta.holder_pid} "
                    f"expired after {age:.1f}s (> {meta.timeout_sec}s). Forcibly breaking lock."
                )
                self._force_release()
                return True
        except (OSError, ValueError, TypeError):
            pass
        return False

    def _force_release(self) -> None:
        _ACTIVE_LOCKS.pop(self.git_common_dir.resolve(), None)
        with contextlib.suppress(Exception):
            if self.meta_file.exists():
                self.meta_file.unlink()
        with contextlib.suppress(Exception):
            if self.lock_file.exists():
                self.lock_file.unlink()

    def _try_flock_acquire(self) -> bool:
        """Single non-blocking attempt to acquire the lock file."""
        try:
            fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd = fd
            self._acquired = True
            _ACTIVE_LOCKS[self.git_common_dir.resolve()] = (self.branch, 1)
            self._write_meta()
            self._start_heartbeat_thread()
            logger.info(f"Governed merge queue lock acquired for '{self.branch}' (PID {os.getpid()}).")
            return True
        except (OSError, IOError) as err:
            if err.errno not in (errno.EACCES, errno.EAGAIN):
                raise MergeQueueError(f"Failed to open/lock {self.lock_file}: {err}") from err
            with contextlib.suppress(Exception):
                os.close(fd)
            return False

    def _resolve_candidate_diff_files(self) -> list[str]:
        """Resolves changed files for the candidate branch relative to main."""
        if self.changed_files is not None:
            return list(self.changed_files)
        try:
            from .common import sanitized_git_env

            diff_res = subprocess.run(
                ["git", "diff", "--name-only", f"main...{self.branch}"],
                cwd=str(self.repo_root),
                env=sanitized_git_env(),
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if diff_res.returncode == 0:
                return [f.strip() for f in diff_res.stdout.splitlines() if f.strip()]
        except (OSError, subprocess.SubprocessError, ImportError):
            pass
        return []

    def _resolve_candidate_review_receipt(self) -> bool:
        """Resolves whether candidate branch has an existing passing review receipt."""
        if self.has_valid_receipt is not None:
            return bool(self.has_valid_receipt)
        try:
            from .common import slugify_branch

            slug = slugify_branch(self.branch)
            receipt_file = self.repo_root / "reports" / f"pr_review_{slug}_receipt.json"
            if receipt_file.is_file():
                data = json.loads(receipt_file.read_text(encoding="utf-8"))
                return bool(data.get("terminal_outcome") == "PASS")
        except (OSError, ValueError, TypeError, ImportError):
            pass
        return False

    def _handle_lock_contention(self, start_t: float) -> None:
        """Handles lock acquisition failure: raises contention error or registers in queue and sleeps with jitter."""
        meta = self._read_meta()
        holder_str = f"PID {meta.holder_pid} ({meta.branch})" if meta else "another process"

        if self.non_blocking:
            raise LockContentionError(f"Merge queue lock held by {holder_str}.")

        if not self.waited_in_fifo:
            from .merge_queue import register_fifo_waiter

            diff_files = self._resolve_candidate_diff_files()
            valid_rcpt = self._resolve_candidate_review_receipt()

            pos = register_fifo_waiter(
                self.git_common_dir,
                self.branch,
                os.getpid(),
                changed_files=diff_files,
                has_valid_receipt=valid_rcpt,
            )
            self.waited_in_fifo = True
            logger.info(f"Paused '{self.branch}' in PR queue (position {pos}) behind {holder_str}.")

        elapsed = time.monotonic() - start_t
        if elapsed >= self.timeout_sec:
            raise LockContentionError(
                f"Timed out after {elapsed:.1f}s waiting for merge queue lock (held by {holder_str})."
            )

        jitter = random.uniform(-0.03, 0.03)
        time.sleep(max(0.05, self.retry_interval_sec + jitter))

    def acquire(self) -> bool:
        """Attempts to acquire the reservation lock, pausing in FIFO queue until turn arrives."""
        if os.environ.get("GOVERNED_MERGE_QUEUE_LOCK_BRANCH") == self.branch:
            self._acquired = True
            return True

        self.git_common_dir.mkdir(parents=True, exist_ok=True)
        canon_dir = self.git_common_dir.resolve()
        existing = _ACTIVE_LOCKS.get(canon_dir)
        if existing and existing[0] == self.branch:
            _ACTIVE_LOCKS[canon_dir] = (self.branch, existing[1] + 1)
            self._acquired = True
            return True

        from .merge_queue import is_first_live_waiter, unregister_fifo_waiter

        pid = os.getpid()
        start_t = time.monotonic()
        try:
            while True:
                self._check_and_break_stale_lock()
                can_try = self.non_blocking or is_first_live_waiter(
                    self.git_common_dir,
                    self.branch,
                    pid,
                    changed_files=self.changed_files,
                    has_valid_receipt=self.has_valid_receipt,
                )
                if can_try and self._try_flock_acquire():
                    if self.waited_in_fifo:
                        unregister_fifo_waiter(self.git_common_dir, self.branch, pid)
                    return True
                self._handle_lock_contention(start_t)
        except Exception:
            if self.waited_in_fifo:
                unregister_fifo_waiter(self.git_common_dir, self.branch, pid)
            raise

    def heartbeat(self) -> None:
        """Updates heartbeat_at timestamp to prevent premature lock expiration."""
        if not self._acquired or not self.meta_file.is_file():
            return
        try:
            meta = self._read_meta()
            if meta and meta.holder_pid == os.getpid():
                meta.heartbeat_at = dt.datetime.now(dt.timezone.utc).isoformat()
                tmp_meta = self.git_common_dir / f"{META_FILE_NAME}.tmp.{os.getpid()}"
                tmp_meta.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
                tmp_meta.replace(self.meta_file)
        except Exception as err:
            logger.warning(f"Failed to update lock heartbeat: {err}")

    def release(self) -> None:
        """Releases the reservation lock and wakes next FIFO waiter."""
        if os.environ.get("GOVERNED_MERGE_QUEUE_LOCK_BRANCH") == self.branch:
            self._acquired = False
            return

        canon_dir = self.git_common_dir.resolve()
        existing = _ACTIVE_LOCKS.get(canon_dir)
        if existing and existing[0] == self.branch:
            count = existing[1] - 1
            if count > 0:
                _ACTIVE_LOCKS[canon_dir] = (self.branch, count)
                return
            _ACTIVE_LOCKS.pop(canon_dir, None)

        self._stop_heartbeat_thread()
        with contextlib.suppress(Exception):
            from .merge_queue import unregister_fifo_waiter

            unregister_fifo_waiter(self.git_common_dir, self.branch, os.getpid())

        if self._fd is not None:
            with contextlib.suppress(Exception):
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            with contextlib.suppress(Exception):
                os.close(self._fd)
            self._fd = None

        with contextlib.suppress(Exception):
            if self.meta_file.exists():
                self.meta_file.unlink()

        with contextlib.suppress(Exception):
            if self.lock_file.exists():
                self.lock_file.unlink()

        self._acquired = False
        logger.info(f"Governed merge queue lock released for '{self.branch}'.")

    def __enter__(self) -> GovernedMergeQueueLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


def inspect_queue_lock(repo_root: Optional[Path] = None) -> Optional[LockInfo]:
    """Inspects active queue reservation status without acquiring lock."""
    common_dir = resolve_git_common_dir(repo_root)
    meta_p = common_dir / META_FILE_NAME
    if not meta_p.is_file():
        return None
    try:
        data = json.loads(meta_p.read_text(encoding="utf-8"))
        info = LockInfo.from_dict(data)
        info.holder_alive = _is_pid_alive(info.holder_pid)
        return info
    except (OSError, ValueError, TypeError, KeyError):
        return None


def force_break_queue_lock(repo_root: Optional[Path] = None) -> bool:
    """Manually breaks an active or orphaned queue lock (emergency operator tool)."""
    common_dir = resolve_git_common_dir(repo_root)
    _ACTIVE_LOCKS.pop(common_dir.resolve(), None)
    lock_file = common_dir / LOCK_FILE_NAME
    meta_file = common_dir / META_FILE_NAME
    broken = False
    if meta_file.exists():
        meta_file.unlink()
        broken = True
    if lock_file.exists():
        lock_file.unlink()
        broken = True
    return broken
