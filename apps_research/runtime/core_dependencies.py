"""Approved apps_research boundary for optional shared-core dependencies."""

from __future__ import annotations

from apps_rg.runtime.apps_runtime_compat import (
    BGE_M3_EMBEDDING_DIMENSION,
    BGE_M3_MODEL_ID,
)

try:
    from apps_rg.mixins.embedding_mixin import EmbeddingMixin
except ImportError:

    class EmbeddingMixin:  # type: ignore[no-redef]
        pass


try:
    from apps_rg.mixins.semantic_cache_mixin import SemanticCacheMixin
except ImportError:  # guardian: allow-silent-swallow -- optional dependency

    class SemanticCacheMixin:  # type: ignore[no-redef]
        pass


def resolve_embedding_device() -> str:
    """Resolve the core-owned default only after app-level overrides."""
    try:
        from apps_rg.embeddings.bge_runtime import _resolve_device  # type: ignore[import-not-found]

        return str(_resolve_device())
    except ImportError:
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:  # guardian: allow-silent-swallow -- fallback to cpu when torch is absent
            pass
        return "cpu"


__all__ = [
    "BGE_M3_EMBEDDING_DIMENSION",
    "BGE_M3_MODEL_ID",
    "EmbeddingMixin",
    "SemanticCacheMixin",
    "resolve_embedding_device",
]
