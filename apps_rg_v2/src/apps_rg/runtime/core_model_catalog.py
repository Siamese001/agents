"""Apps RG-owned embedding model constants.

These values are the local model contract declared in
``config/model_catalog.json``. They are deliberately kept in the app because
embedding identity is part of Apps RG's retrieval and cache compatibility
checks, not an external runtime concern.
"""

from typing import Final


BGE_M3_MODEL_ID: Final[str] = "BAAI/bge-m3"
BGE_M3_EMBEDDING_DIMENSION: Final[int] = 1024

__all__ = ["BGE_M3_EMBEDDING_DIMENSION", "BGE_M3_MODEL_ID"]
