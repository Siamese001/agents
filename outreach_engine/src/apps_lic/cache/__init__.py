"""Multi-tier R1A exact and R1B opt-in semantic cache adapters for outreach_engine.

Re-exports R1A exact-match and R1B semantic cache classes, contracts, and helpers.
"""

from __future__ import annotations

from apps_lic.cache.r1a_adapter import (
    DEFAULT_R1A_TTL_SECONDS,
    R1ACacheEntry,
    R1ACacheKey,
    R1AExactCacheAdapter,
    R1A_SCHEMA_VERSION,
    compute_r1a_cache_key,
)
from apps_lic.cache.r1b_adapter import (
    DEFAULT_R1B_TTL_SECONDS,
    R1BSemanticCacheAdapter,
    R1BSemanticEntry,
    R1B_DEFAULT_COSINE_THRESHOLD,
    R1B_MIN_COSINE_THRESHOLD,
    R1B_SCHEMA_VERSION,
    compute_cosine_similarity,
    embed_prompt_for_r1b,
)

__all__ = [
    "DEFAULT_R1A_TTL_SECONDS",
    "DEFAULT_R1B_TTL_SECONDS",
    "R1ACacheEntry",
    "R1ACacheKey",
    "R1AExactCacheAdapter",
    "R1A_SCHEMA_VERSION",
    "R1BSemanticCacheAdapter",
    "R1BSemanticEntry",
    "R1B_DEFAULT_COSINE_THRESHOLD",
    "R1B_MIN_COSINE_THRESHOLD",
    "R1B_SCHEMA_VERSION",
    "compute_cosine_similarity",
    "compute_r1a_cache_key",
    "embed_prompt_for_r1b",
]
