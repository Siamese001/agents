"""apps_shared data adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RepoSignalSnapshot:
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    adg: dict[str, Any] = field(default_factory=dict)
    tests: dict[str, Any] = field(default_factory=dict)
    ci: dict[str, Any] = field(default_factory=dict)
    governance: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)


class RepoSignalAdapter:
    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root

    def collect(self) -> RepoSignalSnapshot:
        return RepoSignalSnapshot(captured_at=datetime.now(timezone.utc).isoformat())


__all__ = [
    "RepoSignalAdapter",
    "RepoSignalSnapshot",
]
