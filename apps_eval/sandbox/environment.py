"""Hermetic per-case sandbox environment with DELETE_PASS_RETAIN_FAILURE_7_DAYS lifecycle."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

WORKSPACE_POLICY_DELETE_PASS_RETAIN_FAIL = "DELETE_PASS_RETAIN_FAILURE_7_DAYS"
FAILED_WORKSPACE_RETENTION_DAYS = 7


def _assert_safe_mutable_path(path: Path, base_dir: Path) -> None:
    """Reject symlink escapes or paths outside base_dir before destructive cleanup."""
    if path.is_symlink():
        raise PermissionError(f"Refusing to operate on symlink workspace: {path}")
    resolved_base = base_dir.resolve()
    resolved_target = path.resolve()
    if resolved_target == resolved_base:
        raise PermissionError("Refusing to delete sandbox base root itself")
    try:
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise PermissionError(f"Sandbox path escapes base directory: {path}") from exc


class SandboxEnvironment:
    """Disposable isolated filesystem sandbox for hermetic case execution."""

    def __init__(
        self,
        *,
        case_id: str,
        work_root: Path | None = None,
        seed_dir: Path | None = None,
        retention_days: int = FAILED_WORKSPACE_RETENTION_DAYS,
    ) -> None:
        self.case_id = case_id
        self.retention_days = max(1, int(retention_days))
        self._ephemeral_parent = work_root is None
        self.base_dir = (
            Path(tempfile.mkdtemp(prefix="agents-eval-work-"))
            if work_root is None
            else Path(work_root).resolve()
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.seed_dir = Path(seed_dir).resolve() if seed_dir is not None else None
        self.workspace_dir: Path | None = None
        self._passed: bool = True
        self._failure_reason: str = ""

    def mark_failed(self, reason: str) -> None:
        self._passed = False
        self._failure_reason = str(reason)

    def mark_passed(self) -> None:
        self._passed = True
        self._failure_reason = ""

    def __enter__(self) -> SandboxEnvironment:
        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in self.case_id)[:48]
        self.workspace_dir = Path(tempfile.mkdtemp(prefix=f"c-{safe_name}-", dir=str(self.base_dir)))
        if self.seed_dir is not None and self.seed_dir.is_dir():
            for child in self.seed_dir.iterdir():
                if child.is_symlink():
                    continue
                dest = self.workspace_dir / child.name
                if child.is_dir():
                    shutil.copytree(child, dest, symlinks=False)
                else:
                    shutil.copy2(child, dest)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is not None:
            self.mark_failed(f"{exc_type.__name__}: {exc}")
        if self.workspace_dir is None or not self.workspace_dir.exists():
            if self._ephemeral_parent and self.base_dir.exists():
                shutil.rmtree(self.base_dir, ignore_errors=True)
            return False

        if self._passed:
            _assert_safe_mutable_path(self.workspace_dir, self.base_dir)
            shutil.rmtree(self.workspace_dir)
            if self._ephemeral_parent and self.base_dir.exists():
                shutil.rmtree(self.base_dir, ignore_errors=True)
        else:
            now = datetime.now(timezone.utc)
            expires = now + timedelta(days=self.retention_days)
            retention_meta = {
                "policy": WORKSPACE_POLICY_DELETE_PASS_RETAIN_FAIL,
                "case_id": self.case_id,
                "failed_at_utc": now.isoformat().replace("+00:00", "Z"),
                "expires_at_utc": expires.isoformat().replace("+00:00", "Z"),
                "failure_reason": self._failure_reason,
            }
            meta_path = self.workspace_dir / ".retention.json"
            meta_path.write_text(json.dumps(retention_meta, indent=2, sort_keys=True), encoding="utf-8")
        return False


def prune_expired_failed_workspaces(work_root: Path, *, now_utc: datetime | None = None) -> list[str]:
    """Delete failed workspaces whose .retention.json expires_at_utc has passed."""
    base = Path(work_root).resolve()
    if not base.is_dir():
        return []
    now = now_utc or datetime.now(timezone.utc)
    pruned: list[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        meta_file = child / ".retention.json"
        if not meta_file.is_file():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            expires_raw = str(meta.get("expires_at_utc") or "")
            if not expires_raw:
                continue
            expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        except (OSError, ValueError):
            continue
        if expires <= now:
            _assert_safe_mutable_path(child, base)
            shutil.rmtree(child)
            pruned.append(child.name)
    return pruned
