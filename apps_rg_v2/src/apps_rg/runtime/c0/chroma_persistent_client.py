"""Path-scoped Chroma PersistentClient with E2E-11 liveness recovery.

W1 (apps-rg-aig-e2e-remediation-e4b7c1) added ``ChromaVectorStore.ensure_client`` in
``tools/retrieval/vector_store.py`` but apps_rg dense-retrieval paths still created
ephemeral ``chromadb.PersistentClient`` instances. After the shared Chroma system is torn
down between sequential integrated lanes, the next lane raises
``'RustBindingsAPI' object has no attribute 'bindings'`` and cascades phase-1 abort.

This module is the apps_rg SSOT for obtaining a live client at a persist path.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_clients_by_path: dict[str, Any] = {}


def _client_is_alive(client: Any) -> bool:
    heartbeat = getattr(client, "heartbeat", None)
    if not callable(heartbeat):
        return True
    try:
        heartbeat()
    except Exception:  # noqa: BLE001 - any backend failure requires a rebuild
        return False
    return True


def _clear_chroma_system_cache() -> None:
    try:
        from chromadb.api.shared_system_client import SharedSystemClient

        SharedSystemClient.clear_system_cache()
    except (ImportError, AttributeError, RuntimeError):
        return


def _new_client(path: str) -> Any:
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:  # pragma: no cover - dependency contract failure
        raise RuntimeError(
            "ChromaDB is required for the apps_rg persistent vector read surface"
        ) from exc
    Path(path).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=path,
        settings=Settings(anonymized_telemetry=False),
    )


def ensure_apps_rg_chroma_client(chroma_path: str) -> Any:
    """Return a live Chroma PersistentClient for ``chroma_path``, rebuilding if torn down."""
    path = str(chroma_path or "").strip()
    if not path:
        raise ValueError("chroma_path is required")
    key = str(Path(path).resolve())
    with _lock:
        client = _clients_by_path.get(key)
        if client is not None and not _client_is_alive(client):
            _clear_chroma_system_cache()
            client = None
        if client is None:
            client = _new_client(key)
            if not _client_is_alive(client):
                raise RuntimeError("ChromaDB client failed its liveness probe")
            _clients_by_path[key] = client
        return client


def reset_apps_rg_chroma_client_cache_for_tests() -> None:
    """Clear path-scoped store cache (tests only)."""
    with _lock:
        _clients_by_path.clear()
        _clear_chroma_system_cache()


__all__ = [
    "ensure_apps_rg_chroma_client",
    "reset_apps_rg_chroma_client_cache_for_tests",
]
