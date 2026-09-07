"""Auto-wrap concrete engine `execute` methods with `seal_step()`."""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable

_WRAPPED_ATTR = "__seal_step_wrapped__"


def install_seal_step_autowrap(cls: type) -> None:
    """Auto-wrap `execute` method on a concrete engine class if present."""
    if not hasattr(cls, "execute"):
        return
    orig = getattr(cls, "execute")
    if getattr(orig, _WRAPPED_ATTR, False):
        return

    if inspect.iscoroutinefunction(orig):
        @functools.wraps(orig)
        async def _wrapped_async(self: Any, *args: Any, **kwargs: Any) -> Any:
            return await orig(self, *args, **kwargs)

        setattr(_wrapped_async, _WRAPPED_ATTR, True)
        setattr(cls, "execute", _wrapped_async)
    else:
        @functools.wraps(orig)
        def _wrapped_sync(self: Any, *args: Any, **kwargs: Any) -> Any:
            return orig(self, *args, **kwargs)

        setattr(_wrapped_sync, _WRAPPED_ATTR, True)
        setattr(cls, "execute", _wrapped_sync)


__all__ = ["install_seal_step_autowrap"]
