"""Frozen domain contracts for 5-check SQLite custody and 4-channel candidate evidence retrieval.

Zero upward imports: never import ``apps_lic``, ``apps_rg``, ``apps_research``, or ``apps_eval``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from infrastructure.types.metric_lexical_primitives import (
    COMMON_LEXICAL_STOPWORDS,
    METRIC_DOLLAR_PAT,
    METRIC_PERCENT_PAT,
    METRIC_SCALE_PAT,
    extract_numeric_tokens,
    normalize_dollar_token,
    tokenize_words,
)

CANDIDATE_EVIDENCE_SCHEMA_VERSION = "infrastructure.candidate_evidence.v1"
DEFAULT_RRF_K = 60
DEFAULT_CHANNEL_WEIGHTS: dict[str, float] = {
    "dense": 0.20,
    "bm25": 0.40,
    "sparse": 0.15,
    "colbert": 0.25,
    "graph": 0.15,
}


class CandidateEvidenceContractError(ValueError):
    """Raised when candidate evidence custody or retrieval contracts are violated."""


def extract_metric_tokens(text: str) -> tuple[str, ...]:
    """Extract canonical normalized dollar, percent, scale, and numeric tokens from text."""
    raw_text = str(text or "")
    seen: list[str] = []

    def _add(tok: str) -> None:
        cleaned = tok.strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)

    for match in METRIC_DOLLAR_PAT.finditer(raw_text):
        _add(match.group(0))
        _add(normalize_dollar_token(match.group(0)))
    for match in METRIC_PERCENT_PAT.finditer(raw_text):
        _add(match.group(0))
    for match in METRIC_SCALE_PAT.finditer(raw_text):
        _add(match.group(0))
    for tok in extract_numeric_tokens(raw_text):
        _add(tok)
    return tuple(seen)


def extract_entity_tags(
    text: str,
    *,
    employer: str = "",
    category: str = "",
    extra_tags: Sequence[str] = (),
) -> tuple[str, ...]:
    """Extract deterministic entity/capability tags from fact text and metadata."""
    tags: list[str] = []

    def _add(val: str) -> None:
        norm = val.strip().lower().replace(" ", "_")
        if norm and norm not in tags:
            tags.append(norm)

    if employer:
        _add(employer)
    if category:
        _add(category)
    for item in extra_tags:
        if item:
            _add(str(item))
    for tok in tokenize_words(text, min_len=4, stopwords=COMMON_LEXICAL_STOPWORDS):
        if len(tags) >= 16:
            break
        _add(tok)
    return tuple(tags)


@dataclass(frozen=True, slots=True)
class ChannelScoreBreakdown:
    """Per-channel scores and ranks for a single candidate fact chunk across all 4 channels + 1-hop graph."""

    dense_cosine: float = 0.0
    fts5_bm25: float = 0.0
    learned_sparse: float = 0.0
    colbert_maxsim: float = 0.0
    graph_1hop: float = 0.0
    rrf_score: float = 0.0
    final_score: float = 0.0
    dense_rank: int | None = None
    bm25_rank: int | None = None
    sparse_rank: int | None = None
    colbert_rank: int | None = None
    graph_rank: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize channel score breakdown to a JSON-compatible dictionary."""
        return {
            "dense_cosine": round(float(self.dense_cosine), 6),
            "fts5_bm25": round(float(self.fts5_bm25), 6),
            "learned_sparse": round(float(self.learned_sparse), 6),
            "colbert_maxsim": round(float(self.colbert_maxsim), 6),
            "graph_1hop": round(float(self.graph_1hop), 6),
            "rrf_score": round(float(self.rrf_score), 6),
            "final_score": round(float(self.final_score), 6),
            "dense_rank": self.dense_rank,
            "bm25_rank": self.bm25_rank,
            "sparse_rank": self.sparse_rank,
            "colbert_rank": self.colbert_rank,
            "graph_rank": self.graph_rank,
        }


@dataclass(frozen=True, slots=True)
class CandidateFactChunk:
    """Verified candidate proof fact chunk returned by 4-channel hybrid retrieval."""

    fact_id: str
    source_chunk_id: str
    verbatim_span: str
    metric_tokens: tuple[str, ...] = ()
    entity_tags: tuple[str, ...] = ()
    channel_scores: ChannelScoreBreakdown = field(default_factory=ChannelScoreBreakdown)
    employer: str = ""
    category: str = "general"
    career_epoch: str = ""
    skill_ids: tuple[str, ...] = ()
    external_eligible: bool = True

    def __post_init__(self) -> None:
        if not str(self.fact_id or "").strip():
            raise CandidateEvidenceContractError("CandidateFactChunk.fact_id must be non-empty")
        if not str(self.source_chunk_id or "").strip():
            raise CandidateEvidenceContractError("CandidateFactChunk.source_chunk_id must be non-empty")
        if not str(self.verbatim_span or "").strip():
            raise CandidateEvidenceContractError("CandidateFactChunk.verbatim_span must be non-empty")

    @property
    def primary_metric_token(self) -> str:
        """Return the primary metric token for disjoint slot reservation, or empty string."""
        return self.metric_tokens[0] if self.metric_tokens else ""

    @property
    def statement(self) -> str:
        """Alias for verbatim_span for compatibility with CandidateFact consumers."""
        return self.verbatim_span

    @property
    def final_score(self) -> float:
        """Return fused final score from channel_scores."""
        return self.channel_scores.final_score

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate fact chunk to a canonical JSON-compatible dictionary."""
        return {
            "fact_id": self.fact_id,
            "source_chunk_id": self.source_chunk_id,
            "verbatim_span": self.verbatim_span,
            "metric_tokens": list(self.metric_tokens),
            "entity_tags": list(self.entity_tags),
            "channel_scores": self.channel_scores.to_dict(),
            "employer": self.employer,
            "category": self.category,
            "career_epoch": self.career_epoch,
            "skill_ids": list(self.skill_ids),
            "external_eligible": bool(self.external_eligible),
        }


@dataclass(frozen=True, slots=True)
class CustodyCheckReport:
    """5-check SQLite chain-of-custody report for augmented_skills_graph.sqlite."""

    db_path: str
    passed: bool
    check_1_file_exists_nonzero: bool
    check_2_sqlite_header_and_quick_check: bool
    check_3_required_tables_and_fts5: bool
    check_4_candidate_node_count_and_schema: bool
    check_5_sha256_and_manifest_verified: bool
    candidate_graph_db_sha256: str
    manifest_verification_status: str
    file_size_bytes: int = 0
    node_count: int = 0
    eligible_fact_count: int = 0
    semantic_unit_count: int = 0
    schema_version: str = ""
    ledger_hash: str = ""
    errors: tuple[str, ...] = ()

    @property
    def checks_passed_count(self) -> int:
        """Return how many of the 5 custody checks passed (0..5)."""
        return sum(
            1
            for flag in (
                self.check_1_file_exists_nonzero,
                self.check_2_sqlite_header_and_quick_check,
                self.check_3_required_tables_and_fts5,
                self.check_4_candidate_node_count_and_schema,
                self.check_5_sha256_and_manifest_verified,
            )
            if flag
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize custody report to a JSON-compatible dictionary."""
        return {
            "db_path": self.db_path,
            "passed": self.passed,
            "checks_passed_count": self.checks_passed_count,
            "check_1_file_exists_nonzero": self.check_1_file_exists_nonzero,
            "check_2_sqlite_header_and_quick_check": self.check_2_sqlite_header_and_quick_check,
            "check_3_required_tables_and_fts5": self.check_3_required_tables_and_fts5,
            "check_4_candidate_node_count_and_schema": self.check_4_candidate_node_count_and_schema,
            "check_5_sha256_and_manifest_verified": self.check_5_sha256_and_manifest_verified,
            "candidate_graph_db_sha256": self.candidate_graph_db_sha256,
            "manifest_verification_status": self.manifest_verification_status,
            "file_size_bytes": self.file_size_bytes,
            "node_count": self.node_count,
            "eligible_fact_count": self.eligible_fact_count,
            "semantic_unit_count": self.semantic_unit_count,
            "schema_version": self.schema_version,
            "ledger_hash": self.ledger_hash,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class QuadRetrievalConfig:
    """Configuration for 4-channel hybrid retrieval and 1-hop graph expansion."""

    top_k: int = 24
    union_limit: int = 100
    rrf_k: int = DEFAULT_RRF_K
    dense_weight: float = 0.20
    bm25_weight: float = 0.40
    sparse_weight: float = 0.15
    colbert_weight: float = 0.25
    graph_weight: float = 0.15
    colbert_stage2_boost: float = 0.15
    graph_stage2_boost: float = 0.05
    metric_boost: float = 0.04
    include_graph_1hop: bool = True
    require_external_eligible: bool = True
    allow_fallback_hydration: bool = True

    def channel_weights(self) -> dict[str, float]:
        """Return the base RRF channel weight map."""
        return {
            "dense": float(self.dense_weight),
            "bm25": float(self.bm25_weight),
            "sparse": float(self.sparse_weight),
            "colbert": float(self.colbert_weight),
            "graph": float(self.graph_weight),
        }


@dataclass(frozen=True, slots=True)
class HybridCandidatePool:
    """Ranked candidate evidence pool produced by 4-channel hybrid retrieval."""

    query_text: str
    query_digest: str
    candidate_graph_db_sha256: str
    custody_report: CustodyCheckReport
    chunks: tuple[CandidateFactChunk, ...]
    admitted_union_ids: tuple[str, ...] = ()
    active_weights: Mapping[str, float] = field(default_factory=dict)
    channels_executed: Mapping[str, bool] = field(default_factory=dict)
    pool_digest: str = ""

    def __post_init__(self) -> None:
        if not self.pool_digest:
            payload = {
                "query_digest": self.query_digest,
                "candidate_graph_db_sha256": self.candidate_graph_db_sha256,
                "fact_ids": [c.fact_id for c in self.chunks],
            }
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            object.__setattr__(self, "pool_digest", digest)

    @property
    def fact_ids(self) -> tuple[str, ...]:
        """Return ordered tuple of fact_ids in the pool."""
        return tuple(c.fact_id for c in self.chunks)

    def by_fact_id(self) -> dict[str, CandidateFactChunk]:
        """Return lookup dictionary mapping fact_id to CandidateFactChunk."""
        return {c.fact_id: c for c in self.chunks}

    def to_dict(self) -> dict[str, Any]:
        """Serialize hybrid candidate pool to a JSON-compatible dictionary."""
        return {
            "schema_version": CANDIDATE_EVIDENCE_SCHEMA_VERSION,
            "query_text": self.query_text,
            "query_digest": self.query_digest,
            "candidate_graph_db_sha256": self.candidate_graph_db_sha256,
            "pool_digest": self.pool_digest,
            "custody_report": self.custody_report.to_dict(),
            "chunks": [c.to_dict() for c in self.chunks],
            "admitted_union_ids": list(self.admitted_union_ids),
            "active_weights": dict(self.active_weights),
            "channels_executed": dict(self.channels_executed),
        }


__all__ = [
    "CANDIDATE_EVIDENCE_SCHEMA_VERSION",
    "CandidateEvidenceContractError",
    "CandidateFactChunk",
    "ChannelScoreBreakdown",
    "CustodyCheckReport",
    "DEFAULT_CHANNEL_WEIGHTS",
    "DEFAULT_RRF_K",
    "HybridCandidatePool",
    "QuadRetrievalConfig",
    "extract_entity_tags",
    "extract_metric_tokens",
]
