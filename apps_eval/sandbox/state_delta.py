"""Filesystem state delta auditor verifying zero unintended mutations (zero sqlite3 dependency)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from apps_eval.contracts.digests import sha256_file


@dataclass(frozen=True)
class StateDeltaReport:
    """Before/after filesystem digest comparison report."""

    roots_audited: list[str]
    added_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)

    @property
    def total_mutations(self) -> int:
        return len(self.added_files) + len(self.removed_files) + len(self.modified_files)

    @property
    def is_idempotent_noop(self) -> bool:
        return self.total_mutations == 0

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["total_mutations"] = self.total_mutations
        out["is_idempotent_noop"] = self.is_idempotent_noop
        return out


class StateDeltaAuditor:
    """Snapshots file SHA-256 digests across watched paths and computes exact mutation deltas."""

    def __init__(
        self,
        paths: Iterable[Path],
        *,
        exclude_globs: tuple[str, ...] = ("*.pyc", "__pycache__/*", ".retention.json"),
    ) -> None:
        self.paths = [Path(p).resolve() for p in paths]
        self.exclude_globs = exclude_globs
        self._before: dict[str, str] = {}

    def _is_excluded(self, rel: str) -> bool:
        p = Path(rel)
        for pattern in self.exclude_globs:
            if p.match(pattern) or any(part == "__pycache__" for part in p.parts):
                return True
        return False

    def _snapshot(self) -> dict[str, str]:
        snap: dict[str, str] = {}
        for root in self.paths:
            if not root.exists():
                continue
            if root.is_file():
                snap[str(root)] = sha256_file(root)
                continue
            for item in sorted(root.rglob("*")):
                if not item.is_file() or item.is_symlink():
                    continue
                rel = item.relative_to(root).as_posix()
                if self._is_excluded(rel):
                    continue
                snap[f"{root.as_posix()}::{rel}"] = sha256_file(item)
        return snap

    def capture_before(self) -> dict[str, str]:
        self._before = self._snapshot()
        return dict(self._before)

    def compare_after(self) -> StateDeltaReport:
        after = self._snapshot()
        before_keys = set(self._before.keys())
        after_keys = set(after.keys())
        added = sorted(after_keys - before_keys)
        removed = sorted(before_keys - after_keys)
        modified = sorted(k for k in (before_keys & after_keys) if self._before[k] != after[k])
        return StateDeltaReport(
            roots_audited=[p.as_posix() for p in self.paths],
            added_files=added,
            removed_files=removed,
            modified_files=modified,
        )
