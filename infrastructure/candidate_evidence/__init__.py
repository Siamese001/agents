"""Candidate evidence graph, 5-check SQLite custody, and 4-channel hybrid retrieval.

Re-exports public contracts, custody validators, caches, and retriever classes.
Zero upward imports: never import ``apps_lic``, ``apps_rg``, ``apps_research``, or ``apps_eval``.
"""

from __future__ import annotations

from infrastructure.candidate_evidence.caches import (
    BGE_DENSE_DIM,
    CandidateEvidenceColbertCache,
    CandidateEvidenceSparseCache,
    CandidateEvidenceVectorCache,
    dequantize_colbert_vectors_int8,
)
from infrastructure.candidate_evidence.contracts import (
    CANDIDATE_EVIDENCE_SCHEMA_VERSION,
    CandidateEvidenceContractError,
    CandidateFactChunk,
    ChannelScoreBreakdown,
    CustodyCheckReport,
    DEFAULT_CHANNEL_WEIGHTS,
    DEFAULT_RRF_K,
    HybridCandidatePool,
    QuadRetrievalConfig,
    extract_entity_tags,
    extract_metric_tokens,
)
from infrastructure.candidate_evidence.quad_hybrid_retriever import (
    QuadHybridCandidateRetriever,
    project_text_bge_m3_heads,
)
from infrastructure.candidate_evidence.sqlite_custody import (
    REQUIRED_FTS5_TABLES,
    REQUIRED_TABLES,
    build_in_memory_fixture_db,
    compute_sha256,
    open_candidate_graph_readonly,
    verify_sqlite_custody,
)

__all__ = [
    "BGE_DENSE_DIM",
    "CANDIDATE_EVIDENCE_SCHEMA_VERSION",
    "CandidateEvidenceColbertCache",
    "CandidateEvidenceContractError",
    "CandidateEvidenceSparseCache",
    "CandidateEvidenceVectorCache",
    "CandidateFactChunk",
    "ChannelScoreBreakdown",
    "CustodyCheckReport",
    "DEFAULT_CHANNEL_WEIGHTS",
    "DEFAULT_RRF_K",
    "HybridCandidatePool",
    "QuadHybridCandidateRetriever",
    "QuadRetrievalConfig",
    "REQUIRED_FTS5_TABLES",
    "REQUIRED_TABLES",
    "build_in_memory_fixture_db",
    "compute_sha256",
    "dequantize_colbert_vectors_int8",
    "extract_entity_tags",
    "extract_metric_tokens",
    "open_candidate_graph_readonly",
    "project_text_bge_m3_heads",
    "verify_sqlite_custody",
]
