"""Base spine adapter for apps_shared."""

from __future__ import annotations

from typing import Any


class BaseSpineAdapter:
    def __init__(
        self,
        cid_registry: Any = None,
        orchestrator: Any = None,
        *,
        prefix: str = "",
        max_reentry_attempts: int = 3,
    ) -> None:
        self.cid_registry = cid_registry
        self.orchestrator = orchestrator
        self.prefix = prefix
        self.max_reentry_attempts = max_reentry_attempts


__all__ = ["BaseSpineAdapter"]
