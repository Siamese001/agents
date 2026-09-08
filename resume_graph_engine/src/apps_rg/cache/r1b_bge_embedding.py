"""BGE-M3 embeddings for apps_rg R1B semantic cache (Chroma vector store only).

When ``resolve_apps_rg_embedding_settings().embedding_model_resolved`` is true, all
R1B intent/chunk vectors use explicit local BGE. Pseudo-digest vectors are fallback
only when embeddings are disabled (tests / CI without weights).
"""

from __future__ import annotations

from apps_rg.runtime.core_model_catalog import (
    BGE_M3_EMBEDDING_DIMENSION,
    BGE_M3_MODEL_ID,
)

import logging
from typing import Any, Sequence

from apps_rg.cache.r1b_constants import R1B_STORAGE_SUBSYSTEM

_logger = logging.getLogger(__name__)

_BGE_DIM = BGE_M3_EMBEDDING_DIMENSION


def bge_embeddings_active() -> bool:
    from apps_rg.runtime.embedding_settings import resolve_apps_rg_embedding_settings

    s = resolve_apps_rg_embedding_settings()
    return bool(s.embeddings_enabled and s.embedding_model_resolved)


def _get_bge_runtime() -> Any:
    from apps_rg.runtime.bge_embedding import get_bge_runtime_for_settings
    from apps_rg.runtime.embedding_settings import resolve_apps_rg_embedding_settings

    settings = resolve_apps_rg_embedding_settings()
    if not settings.embedding_model_resolved:
        return None
    try:
        return get_bge_runtime_for_settings(settings)
    except Exception as exc:  # guardian: allow-broad-exception -- optional test/CI fallback remains governed below
        from apps_rg.runtime.embedding_settings import AppsRgEmbeddingFailClosedError
        from apps_rg.runtime.product_output_policy import require_live_bge_embeddings

        if require_live_bge_embeddings():
            raise AppsRgEmbeddingFailClosedError(f"BGE-M3 load failed on product path: {exc}") from exc
        _logger.warning("R1B BGE load failed (%s); using pseudo-digest fallback", exc)
        return None


def _get_bge_model() -> Any:
    """Backward-compatible access to the app-owned resident model."""

    runtime = _get_bge_runtime()
    return runtime.model if runtime is not None else None


def reset_bge_model_for_testing() -> None:
    from apps_rg.runtime.bge_embedding import reset_bge_runtime_for_testing

    reset_bge_runtime_for_testing()


def _coerce_bge_vector(vec: Any) -> list[float]:
    values = [float(v) for v in vec]
    if len(values) != _BGE_DIM:
        raise RuntimeError(f"BGE_DIM_MISMATCH: got {len(values)}, expected {_BGE_DIM}")
    return values


def embed_text_bge(text: str) -> list[float] | None:
    """L2-normalized BGE-M3 embedding; None when BGE unavailable."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    runtime = _get_bge_runtime()
    if runtime is None:
        return None
    return _coerce_bge_vector(runtime.encode([stripped], batch_size=1)[0])


def embed_texts_bge(
    texts: Sequence[str], *, batch_size: int | None = None
) -> list[list[float] | None]:
    """L2-normalized BGE-M3 embeddings, preserving input order for batch callers."""
    outputs: list[list[float] | None] = [None] * len(texts)
    indexed_texts: list[tuple[int, str]] = []
    for idx, text in enumerate(texts):
        stripped = (text or "").strip()
        if stripped:
            indexed_texts.append((idx, stripped))
    if not indexed_texts:
        return outputs
    runtime = _get_bge_runtime()
    if runtime is None:
        return outputs
    from apps_rg.runtime.bge_embedding import resolve_bge_batch_size

    selected_batch_size = resolve_bge_batch_size(
        "r1b_projection",
        len(indexed_texts),
        requested=batch_size if batch_size is not None and batch_size > 0 else None,
    )
    rows = runtime.encode(
        [text for _idx, text in indexed_texts],
        batch_size=selected_batch_size,
    )
    for (idx, _text), row in zip(indexed_texts, rows):
        outputs[idx] = _coerce_bge_vector(row)
    return outputs


def intent_vector_payload(*, intent_text: str, digest: str) -> dict[str, Any]:
    """Canonical vector JSON persisted under ``vectors/<record_id>.json``."""
    from apps_rg.cache.r1b_intent_vector import (
        normalized_intent_digest,
        pseudo_vector_from_digest,
    )

    from apps_rg.runtime.embedding_settings import AppsRgEmbeddingFailClosedError
    from apps_rg.runtime.product_output_policy import require_live_bge_embeddings

    digest = digest or normalized_intent_digest(intent_text)
    bge = embed_text_bge(intent_text)
    if bge is not None:
        return {
            "subsystem": R1B_STORAGE_SUBSYSTEM,
            "embedding_model": BGE_M3_MODEL_ID,
            "embedding_provider": "bge_local",
            "not_c0_fact_vectors": True,
            "not_chroma_default_ef": True,
            "normalized_intent_digest": digest,
            "dimensions": _BGE_DIM,
            "values": bge,
        }
    if require_live_bge_embeddings():
        raise AppsRgEmbeddingFailClosedError(
            "BGE-M3 embedding required; pseudo_digest_fallback forbidden on product path"
        )
    return {
        "subsystem": R1B_STORAGE_SUBSYSTEM,
        "embedding_model": "pseudo_digest_fallback",
        "not_c0_fact_vectors": True,
        "normalized_intent_digest": digest,
        "dimensions": 32,
        "values": pseudo_vector_from_digest(digest),
        "fallback_reason": "bge_unavailable",
    }


def chunk_vector_payload(*, chunk_text: str, chunk_id: str) -> dict[str, Any]:
    from apps_rg.runtime.embedding_settings import AppsRgEmbeddingFailClosedError
    from apps_rg.runtime.product_output_policy import require_live_bge_embeddings

    text = (chunk_text or chunk_id or "").strip()
    bge = embed_text_bge(text) if text else None
    if bge is not None:
        return {
            "chunk_id": chunk_id,
            "embedding_model": BGE_M3_MODEL_ID,
            "dimensions": _BGE_DIM,
            "values": bge,
        }
    if require_live_bge_embeddings():
        raise AppsRgEmbeddingFailClosedError(
            f"BGE-M3 chunk embedding required; pseudo_digest forbidden (chunk_id={chunk_id!r})"
        )
    from apps_rg.cache.r1b_intent_vector import (
        normalized_intent_digest,
        pseudo_vector_from_digest,
    )

    digest = normalized_intent_digest(text or chunk_id)
    return {
        "chunk_id": chunk_id,
        "embedding_model": "pseudo_digest_fallback",
        "dimensions": 32,
        "values": pseudo_vector_from_digest(digest),
    }


def resolve_query_vector(intent_text: str, digest: str) -> tuple[list[float], str]:
    """Query vector for R1B lookup — BGE when active, else pseudo (tests only)."""
    from apps_rg.cache.r1b_intent_vector import pseudo_vector_from_digest
    from apps_rg.runtime.embedding_settings import AppsRgEmbeddingFailClosedError
    from apps_rg.runtime.product_output_policy import require_live_bge_embeddings

    bge = embed_text_bge(intent_text)
    if bge is not None:
        return bge, "bge_m3"
    if require_live_bge_embeddings():
        raise AppsRgEmbeddingFailClosedError("BGE-M3 query vector required; pseudo_digest forbidden on product path")
    return pseudo_vector_from_digest(digest), "pseudo_digest"


__all__ = [
    "bge_embeddings_active",
    "chunk_vector_payload",
    "embed_text_bge",
    "embed_texts_bge",
    "intent_vector_payload",
    "reset_bge_model_for_testing",
    "resolve_query_vector",
]
