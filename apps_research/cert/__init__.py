"""apps_research cert-path utilities."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

_logger = logging.getLogger(__name__)

_PRODUCERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
_LOCK = threading.Lock()


def register_producer(
    app_id: str,
    producer: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """Register an app-specific FEC producer callable."""
    with _LOCK:
        _PRODUCERS[app_id] = producer


def resolve_fec(
    app_id: str,
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke the registered FEC producer for app_id, or return an empty dict."""
    with _LOCK:
        producer = _PRODUCERS.get(app_id)
    if producer is None:
        return {}
    try:
        res = producer(run_context or {})
        return res if isinstance(res, dict) else {}
    except Exception as exc:  # noqa: BLE001
        _logger.warning("FEC producer for %s raised %s: %s", app_id, type(exc).__name__, exc)
        return {}


def maybe_invoke_exit_eval(
    receipts_dict: dict[str, Any] | None = None,
    run_context: dict[str, Any] | None = None,
) -> None:
    """Safe pass-through for exit evaluation hook."""
    pass


from apps_research.cert.fec_producer import produce_fec

register_producer("apps_research", produce_fec)

__all__ = [
    "maybe_invoke_exit_eval",
    "produce_fec",
    "register_producer",
    "resolve_fec",
]
