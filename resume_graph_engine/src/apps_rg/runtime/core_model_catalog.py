"""Apps RG-owned embedding model constants.

These values are the local model contract declared in
``config/model_catalog.json``. They are deliberately kept in the app because
embedding identity is part of Apps RG's retrieval and cache compatibility
checks, not an external runtime concern.
"""

from typing import Final

from apps_rg.runtime.model_registry import resolve

_RESOLVED_BGE = resolve("embedding.bge_m3")
BGE_M3_MODEL_ID: Final[str] = _RESOLVED_BGE.model
BGE_M3_EMBEDDING_DIMENSION: Final[int] = 1024

__all__ = ["BGE_M3_EMBEDDING_DIMENSION", "BGE_M3_MODEL_ID"]
