"""Governed Merge Queue & Trunk Reservation Lock.

Provides atomic file locking at .git/governed_merge_queue.lock to serialize
rebasing, readiness qualification, and landing across multiple concurrent
feature branches and worktrees, eliminating convoy thrashing and livelock.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from tools.pr_governance_core.merge_lock import (
    LOCK_FILE_NAME,
    META_FILE_NAME,
    GovernedMergeQueueLock,
    LockContentionError,
    LockInfo,
    MergeQueueError,
    StaleLockRecoveredError,
    _is_pid_alive,
    force_break_queue_lock,
    inspect_queue_lock,
    resolve_git_common_dir,
)

logger = logging.getLogger("tools.pr_governance_core.merge_queue")

QUEUE_FILE_NAME = "governed_merge_queue_waiters.json"
MAX_BYPASS_COUNT = 3


@dataclass
class QueueItem:
    """Represents a PR waiting in the governed merge queue."""

    branch: str
    title: str
    enqueued_at: str
    enqueued_by: str = ""
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, FAILED, CONFLICT
    error_message: str = ""
    changed_files: list[str] = field(default_factory=list)
    has_valid_receipt: bool = False
    bypass_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueueItem:
        return cls(
            branch=str(data.get("branch", "")),
            title=str(data.get("title", "")),
            enqueued_at=str(data.get("enqueued_at", "")),
            enqueued_by=str(data.get("enqueued_by", "")),
            status=str(data.get("status", "PENDING")),
            error_message=str(data.get("error_message", "")),
            changed_files=list(data.get("changed_files", []) or []),
            has_valid_receipt=bool(data.get("has_valid_receipt", False)),
            bypass_count=int(data.get("bypass_count", 0)),
        )


@contextlib.contextmanager
def _waiters_file_lock(common_dir: Path, timeout_sec: float = 30.0):
    common_dir.mkdir(parents=True, exist_ok=True)
    lock_p = common_dir / f"{QUEUE_FILE_NAME}.lock"
    fd = os.open(str(lock_p), os.O_CREAT | os.O_RDWR, 0o644)
    deadline = time.monotonic() + timeout_sec
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting {timeout_sec}s for waiters file lock at {lock_p}")
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            with contextlib.suppress(Exception):
                fcntl.flock(fd, fcntl.LOCK_UN)
        with contextlib.suppress(Exception):
            os.close(fd)


def _read_waiters(common_dir: Path) -> list[QueueItem]:
    queue_p = common_dir / QUEUE_FILE_NAME
    if not queue_p.is_file():
        return []
    try:
        data = json.loads(queue_p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [QueueItem.from_dict(item) for item in data if isinstance(item, dict)]
    except Exception:
        pass
    return []


def _write_waiters(common_dir: Path, items: list[QueueItem]) -> None:
    queue_p = common_dir / QUEUE_FILE_NAME
    tid = threading.get_ident()
    tmp_p = common_dir / f"{QUEUE_FILE_NAME}.tmp.{os.getpid()}.{tid}"
    raw = [item.to_dict() for item in items]
    tmp_p.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    tmp_p.replace(queue_p)


def _extract_waiter_pid(item: QueueItem) -> int:
    if item.enqueued_by.startswith("pid:"):
        with contextlib.suppress(ValueError):
            return int(item.enqueued_by.split(":", 1)[1])
    return 0


def _prune_dead_live_waiters(items: list[QueueItem]) -> list[QueueItem]:
    kept: list[QueueItem] = []
    for item in items:
        pid = _extract_waiter_pid(item)
        if pid > 0 and not _is_pid_alive(pid):
            continue
        kept.append(item)
    return kept


def _can_bypass_priors(cand: QueueItem, priors: list[QueueItem]) -> bool:
    """Checks whether a ready disjoint candidate can bypass all prior pending waiters."""
    if not cand.has_valid_receipt or not cand.changed_files:
        return False

    if any(p.bypass_count >= MAX_BYPASS_COUNT for p in priors):
        return False

    cand_files = set(cand.changed_files)
    for p in priors:
        if not cand_files.isdisjoint(p.changed_files) or p.has_valid_receipt:
            return False

    return True


def _update_waiter_metadata(
    waiters: list[QueueItem],
    branch: str,
    tag: str,
    changed_files: Optional[list[str]],
    has_valid_receipt: Optional[bool],
) -> bool:
    """Updates candidate waiter metadata in-place and returns whether changes were made."""
    dirty = False
    for w in waiters:
        if w.branch == branch and w.enqueued_by == tag:
            if changed_files is not None and w.changed_files != changed_files:
                w.changed_files = list(changed_files)
                dirty = True
            if has_valid_receipt is not None and w.has_valid_receipt != has_valid_receipt:
                w.has_valid_receipt = bool(has_valid_receipt)
                dirty = True
    return dirty


def _evaluate_candidate_eligibility(
    common_dir: Path,
    pruned: list[QueueItem],
    live_pending: list[QueueItem],
    branch: str,
    tag: str,
    dirty: bool,
) -> bool:
    """Evaluates whether a candidate branch/tag can bypass pending priors."""
    cand_matches = [w for w in live_pending if w.branch == branch and w.enqueued_by == tag]
    if not cand_matches:
        if dirty:
            _write_waiters(common_dir, pruned)
        return False

    cand = cand_matches[0]
    cand_idx = live_pending.index(cand)
    priors = live_pending[:cand_idx]

    if not _can_bypass_priors(cand, priors):
        if dirty:
            _write_waiters(common_dir, pruned)
        return False

    for p in priors:
        p.bypass_count += 1
    _write_waiters(common_dir, pruned)
    logger.info(
        f"Disjoint bypass: '{branch}' bypassed {len(priors)} prior waiter(s) "
        f"(head bypass_count={priors[0].bypass_count}/{MAX_BYPASS_COUNT})."
    )
    return True


def register_fifo_waiter(
    common_dir: Path,
    branch: str,
    pid: int,
    changed_files: Optional[list[str]] = None,
    has_valid_receipt: bool = False,
) -> int:
    """Atomically registers a paused PR submission in the FIFO waiter queue; returns 1-based queue position."""
    with _waiters_file_lock(common_dir):
        waiters = _prune_dead_live_waiters(_read_waiters(common_dir))
        tag = f"pid:{pid}"
        for idx, item in enumerate(waiters):
            if item.branch == branch and item.enqueued_by == tag and item.status == "PENDING":
                if changed_files is not None:
                    item.changed_files = list(changed_files)
                item.has_valid_receipt = has_valid_receipt
                _write_waiters(common_dir, waiters)
                return idx + 1
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        waiters.append(
            QueueItem(
                branch=branch,
                title="Paused PR to local main (FIFO Queue)",
                enqueued_at=now_iso,
                enqueued_by=tag,
                status="PENDING",
                changed_files=list(changed_files or []),
                has_valid_receipt=has_valid_receipt,
                bypass_count=0,
            )
        )
        _write_waiters(common_dir, waiters)
        live_pending = [w for w in waiters if _extract_waiter_pid(w) > 0 and w.status == "PENDING"]
        return len(live_pending)


def unregister_fifo_waiter(common_dir: Path, branch: str, pid: int) -> None:
    """Atomically removes a branch's live FIFO waiter entry upon lock acquisition or abort."""
    with _waiters_file_lock(common_dir):
        waiters = _prune_dead_live_waiters(_read_waiters(common_dir))
        tag = f"pid:{pid}"
        updated = [w for w in waiters if not (w.branch == branch and w.enqueued_by == tag)]
        if len(updated) != len(waiters):
            _write_waiters(common_dir, updated)


def is_first_live_waiter(
    common_dir: Path,
    branch: str,
    pid: int,
    changed_files: Optional[list[str]] = None,
    has_valid_receipt: Optional[bool] = None,
) -> bool:
    """Returns True if (branch, pid) is eligible to acquire the lock under Starvation-Bounded Disjoint-First scheduling."""
    tag = f"pid:{pid}"
    with _waiters_file_lock(common_dir):
        waiters = _read_waiters(common_dir)
        pruned = _prune_dead_live_waiters(waiters)
        dirty = (len(pruned) != len(waiters)) | _update_waiter_metadata(
            pruned, branch, tag, changed_files, has_valid_receipt
        )

        live_pending = [w for w in pruned if _extract_waiter_pid(w) > 0 and w.status == "PENDING"]
        if not live_pending:
            if dirty:
                _write_waiters(common_dir, pruned)
            return True

        head = live_pending[0]
        if head.branch == branch and head.enqueued_by == tag:
            if dirty:
                _write_waiters(common_dir, pruned)
            return True

        return _evaluate_candidate_eligibility(common_dir, pruned, live_pending, branch, tag, dirty)


def enqueue_pr(branch: str, title: str, repo_root: Optional[Path] = None) -> QueueItem:
    """Adds a branch to the FIFO merge queue."""
    common_dir = resolve_git_common_dir(repo_root)
    with _waiters_file_lock(common_dir):
        waiters = _read_waiters(common_dir)

        for item in waiters:
            if item.branch == branch and item.status in ("PENDING", "IN_PROGRESS"):
                item.title = title or item.title
                _write_waiters(common_dir, waiters)
                return item

        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        new_item = QueueItem(
            branch=branch,
            title=title,
            enqueued_at=now_iso,
            enqueued_by=os.environ.get("USER", "unknown"),
            status="PENDING",
        )
        waiters.append(new_item)
        _write_waiters(common_dir, waiters)
        logger.info(f"Enqueued '{branch}' into governed merge queue at position {len(waiters)}.")
        return new_item


def dequeue_pr(branch: str, repo_root: Optional[Path] = None) -> bool:
    """Removes a branch from the merge queue."""
    common_dir = resolve_git_common_dir(repo_root)
    with _waiters_file_lock(common_dir):
        waiters = _read_waiters(common_dir)
        original_len = len(waiters)
        waiters = [w for w in waiters if w.branch != branch]
        if len(waiters) != original_len:
            _write_waiters(common_dir, waiters)
            return True
        return False


def get_queue_status(repo_root: Optional[Path] = None) -> dict[str, Any]:
    """Inspects active queue lock and all waiting PRs."""
    common_dir = resolve_git_common_dir(repo_root)
    lock_info = inspect_queue_lock(repo_root)
    waiters = _read_waiters(common_dir)
    pending = [w.to_dict() for w in waiters if w.status == "PENDING"]
    return {
        "active_lock": lock_info.to_dict() if lock_info else None,
        "is_locked": lock_info is not None,
        "total_queued": len(waiters),
        "waiters": pending,
        "pending_waiters": pending,
        "all_waiters": [w.to_dict() for w in waiters],
    }


def _update_terminal_status(common_dir: Path, branch: str, land_res: Any) -> None:
    """Refreshes waiters list and records terminal outcome for branch."""
    waiters = _read_waiters(common_dir)
    for w in waiters:
        if w.branch == branch:
            w.status = "COMPLETED" if land_res.status == "SUCCESS" else "FAILED"
            w.error_message = land_res.error_message
    _write_waiters(common_dir, waiters)


def process_queue(
    repo_root: Optional[Path] = None,
    timeout_per_pr: float = 600.0,
) -> list[dict[str, Any]]:
    """Drains the merge queue sequentially, landing each PR to main."""
    from tools.rebase_orchestrator import land_branch_serialized

    root = repo_root or Path.cwd()
    common_dir = resolve_git_common_dir(root)
    results: list[dict[str, Any]] = []

    max_iterations = 100
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        waiters = _read_waiters(common_dir)
        pending = [w for w in waiters if w.status == "PENDING"]
        if not pending:
            break

        current = pending[0]
        current.status = "IN_PROGRESS"
        _write_waiters(common_dir, waiters)

        logger.info(f"Processing queued branch: {current.branch} ('{current.title}')...")
        land_res = land_branch_serialized(
            branch=current.branch,
            title=current.title,
            repo_root=root,
            timeout_sec=timeout_per_pr,
        )

        results.append(land_res.to_dict())
        _update_terminal_status(common_dir, current.branch, land_res)

    if iteration >= max_iterations:
        logger.warning("Merge queue processing halted: reached maximum iteration limit of %d", max_iterations)

    return results


def _handle_status(args: argparse.Namespace) -> int:
    status = get_queue_status()
    if getattr(args, "json", False):
        print(json.dumps(status, indent=2))
        return 0
    print("=" * 80)
    print("  GOVERNED MERGE QUEUE STATUS")
    print("=" * 80)
    if status["active_lock"]:
        lock_entry = status["active_lock"]
        print(f"ACTIVE LOCK:  Branch '{lock_entry['branch']}' held by PID {lock_entry['holder_pid']}")
        print(f"   Acquired at:  {lock_entry['acquired_at']}")
    else:
        print("ACTIVE LOCK:  None (queue available)")

    pending = status["pending_waiters"]
    print(f"\nQUEUED PRs ({len(pending)}):")
    if not pending:
        print("   (No PRs in queue)")
    else:
        for idx, p in enumerate(pending, start=1):
            print(f"   {idx}. {p['branch']} — '{p['title']}' (enqueued {p['enqueued_at']})")
    print("=" * 80)
    return 0


def _handle_enqueue(args: argparse.Namespace) -> int:
    branch = getattr(args, "branch", None)
    title = getattr(args, "title", None) or f"Merge {branch}"
    if not branch:
        print("Branch required to enqueue: --branch <name>")
        return 1
    item = enqueue_pr(branch, title)
    print(f"Enqueued branch '{item.branch}' in position (status: {item.status})")
    return 0


def _handle_drop(args: argparse.Namespace) -> int:
    branch = getattr(args, "branch", None)
    if not branch:
        print("Branch required to drop: --branch <name>")
        return 1
    dropped = dequeue_pr(branch)
    if dropped:
        print(f"Dropped '{branch}' from merge queue.")
    else:
        print(f"Branch '{branch}' was not in the merge queue.")
    return 0


def _handle_run(_args: argparse.Namespace) -> int:
    print("Draining governed merge queue sequentially...")
    results = process_queue()
    print(f"Completed {len(results)} PR(s):")
    for r in results:
        print(f"   • {r['branch']}: {r['status']} ({r.get('merge_commit_sha', r.get('error_message'))})")
    return 0 if all(r["status"] == "SUCCESS" for r in results) else 1


def _handle_break_lock() -> int:
    broken = force_break_queue_lock()
    if broken:
        print("Emergency queue lock forcibly broken.")
    else:
        print("No active queue lock file to break.")
    return 0


def _get_branch_auth_path(repo_root: Path, branch: str) -> Path:
    from .common import slugify_branch

    slug = slugify_branch(branch)
    return repo_root / ".local" / "ledger" / "pr_merge_auth" / f"{slug}.json"


def record_branch_merge_authorization(
    repo_root: Path,
    branch: str,
    branch_tree_oid: str = "",
    operator_id: str = "human_operator",
    entry_id: str = "",
) -> Path:
    """Writes a conflict-free per-branch merge authorization record keyed by `(branch, branch_tree_oid)`."""
    auth_path = _get_branch_auth_path(repo_root, branch)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "branch": branch,
        "branch_tree_oid": branch_tree_oid,
        "operator_id": operator_id,
        "operator_class": "HUMAN_OPERATOR",
        "category": "pr_merge_authorization",
        "entry_id": entry_id or f"pr_merge_{branch.replace('/', '_')}",
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    auth_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return auth_path


def verify_branch_merge_authorization(
    repo_root: Path,
    branch: str,
    branch_tree_oid: str = "",
) -> tuple[bool, str]:
    """Verifies a per-branch merge authorization record keyed by `(branch, branch_tree_oid)`."""
    auth_path = _get_branch_auth_path(repo_root, branch)
    if not auth_path.is_file():
        return False, ""
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
        if data.get("branch") != branch:
            return False, ""
        if str(data.get("operator_class") or "").upper() == "AUTONOMOUS":
            return False, ""
        rec_tree = str(data.get("branch_tree_oid") or "")
        if branch_tree_oid and rec_tree and rec_tree != branch_tree_oid:
            return False, ""
        return True, f"Verified per-branch PR merge authorization ({data.get('entry_id')})"
    except Exception as exc:
        _ = exc
        return False, ""


def cmd_queue(args: argparse.Namespace) -> int:
    """CLI handler for `pr_governance.py queue`."""
    action = getattr(args, "action", "status") or "status"
    handlers = {
        "status": _handle_status,
        "enqueue": _handle_enqueue,
        "drop": _handle_drop,
        "run": _handle_run,
        "break": lambda _a: _handle_break_lock(),
        "break-lock": lambda _a: _handle_break_lock(),
    }
    handler = handlers.get(action)
    if handler:
        return handler(args)

    print(f"Unknown queue action: {action}")
    return 1


__all__ = [
    "LOCK_FILE_NAME",
    "META_FILE_NAME",
    "QUEUE_FILE_NAME",
    "GovernedMergeQueueLock",
    "LockContentionError",
    "LockInfo",
    "MergeQueueError",
    "QueueItem",
    "StaleLockRecoveredError",
    "cmd_queue",
    "dequeue_pr",
    "enqueue_pr",
    "force_break_queue_lock",
    "get_queue_status",
    "inspect_queue_lock",
    "process_queue",
    "resolve_git_common_dir",
    "register_fifo_waiter",
    "unregister_fifo_waiter",
    "is_first_live_waiter",
    "record_branch_merge_authorization",
    "verify_branch_merge_authorization",
]
