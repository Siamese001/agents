"""Apps RG-owned retrieval contracts and deterministic C0 helpers.

This module is deliberately small and dependency-free.  It provides the
contracts shared by the dense, sparse, and graph-adjacent C0 lanes without
loading another application's runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


VERDICT_PASS = "PASS"
VERDICT_UNKNOWN = "UNKNOWN"
VERDICT_NOT_APPLICABLE = "NOT_APPLICABLE"
VERDICT_WARN = "WARN"
VERDICT_FAIL = "FAIL"
_VERDICTS = frozenset(
    {
        VERDICT_PASS,
        VERDICT_UNKNOWN,
        VERDICT_NOT_APPLICABLE,
        VERDICT_WARN,
        VERDICT_FAIL,
    }
)


@dataclass(frozen=True, slots=True)
class GateVerdict:
    """A C0 gate result with explicit unknown and non-applicable reasons."""

    gate_id: str
    gate_family: str
    evaluated_stage: str
    result: str
    remediation_hint: str = ""
    unknown_reason: str | None = None
    not_applicable_reason: str | None = None
    evaluated_at: str = ""
    evidence_digest: str = ""

    def __post_init__(self) -> None:
        if not self.gate_id:
            raise ValueError("gate_id is required")
        if self.result not in _VERDICTS:
            raise ValueError(f"unsupported gate result: {self.result!r}")
        if self.result == VERDICT_UNKNOWN and not self.unknown_reason:
            raise ValueError("unknown_reason is required for UNKNOWN gate results")
        if self.result == VERDICT_NOT_APPLICABLE and not self.not_applicable_reason:
            raise ValueError(
                "not_applicable_reason is required for NOT_APPLICABLE gate results"
            )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "gate_id": self.gate_id,
            "gate_family": self.gate_family,
            "evaluated_stage": self.evaluated_stage,
            "result": self.result,
            "remediation_hint": self.remediation_hint,
            "unknown_reason": self.unknown_reason,
            "not_applicable_reason": self.not_applicable_reason,
            "evaluated_at": self.evaluated_at,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    """A source-grounded retrieval row used by the bounded C0 lane."""

    chunk_id: str
    content: str
    metadata: Mapping[str, Any]
    combined_score: float = 0.0
    source: str = ""
    vector_score: float = 0.0
    lexical_score: float = 0.0


class SparseLexicalLaneStatus(str, Enum):
    OK = "OK"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class SparseLexicalQuerySpec:
    lane_id: str
    query_text: str
    top_k: int
    sparse_index_collection_name: str = ""
    metadata_filter: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SparseLexicalHit:
    chunk_id: str
    source_id: str
    text: str
    span_ref: str
    lexical_score: float
    dense_score: float
    metadata: Mapping[str, Any]
    citation_ref: str


@dataclass(frozen=True, slots=True)
class SparseLexicalLaneOutcome:
    lane_id: str
    status: SparseLexicalLaneStatus
    hits: tuple[SparseLexicalHit, ...]
    receipt_ref: str
    hybrid_rows: tuple[HybridSearchResult, ...]


def dedupe_hybrid_by_chunk_id(
    rows: Sequence[HybridSearchResult],
) -> list[HybridSearchResult]:
    """Keep the strongest row per chunk, using first-seen order for ties."""

    out: list[HybridSearchResult] = []
    positions: dict[str, int] = {}
    for row in rows:
        key = str(row.chunk_id or "")
        if not key:
            continue
        prior_index = positions.get(key)
        if prior_index is None:
            positions[key] = len(out)
            out.append(row)
        elif row.combined_score > out[prior_index].combined_score:
            out[prior_index] = row
    return out


def merge_dense_sparse_rrf(
    dense_rows: Sequence[HybridSearchResult],
    sparse_rows: Sequence[HybridSearchResult],
    *,
    rank_constant: int = 60,
) -> list[HybridSearchResult]:
    """Fuse bounded dense and sparse results with deterministic RRF scoring."""

    by_chunk: dict[str, HybridSearchResult] = {}
    scores: dict[str, float] = {}
    order: list[str] = []
    for rows in (dense_rows, sparse_rows):
        for rank, row in enumerate(rows, start=1):
            key = str(row.chunk_id or "")
            if not key:
                continue
            if key not in by_chunk:
                by_chunk[key] = row
                order.append(key)
            scores[key] = scores.get(key, 0.0) + (1.0 / (rank_constant + rank))
    return [
        replace(by_chunk[key], combined_score=scores[key])
        for key in sorted(order, key=lambda value: (-scores[value], order.index(value)))
    ]


def filter_candidates_exact_subphrase(
    rows: Iterable[HybridSearchResult],
    phrase: str,
) -> list[HybridSearchResult]:
    """Return only candidates containing the normalized phrase verbatim."""

    needle = " ".join(str(phrase or "").lower().split())
    if not needle:
        return list(rows)
    return [
        row
        for row in rows
        if needle in " ".join(str(row.content or "").lower().split())
    ]


def fec_sparse_refs_from_lane_outcomes(*refs: str) -> tuple[str, ...]:
    """Normalize sparse lane references for a final evidence contract."""

    return tuple(dict.fromkeys(str(ref) for ref in refs if str(ref).strip()))


@dataclass(frozen=True, slots=True)
class GraphTraversalResult:
    """Explicitly records that this app-local runtime did not run a graph adapter."""

    executed: bool = False
    pool: object | None = None


def maybe_run_graph_rag(_route: object, _items: Sequence[object]) -> GraphTraversalResult:
    """Return a non-executed result; Apps RG falls back to its owned graph index."""

    return GraphTraversalResult()


@dataclass(frozen=True, slots=True)
class SupportTarget:
    """Prefix-based proof-support target for the Apps RG evidence surface."""

    prefixes: tuple[str, ...]
    label: str = ""

    @classmethod
    def from_prefix_list(
        cls, prefixes: Sequence[str], *, label: str = ""
    ) -> "SupportTarget":
        normalized = tuple(
            dict.fromkeys(str(prefix).strip().rstrip(":") for prefix in prefixes if str(prefix).strip())
        )
        if not normalized:
            raise ValueError("at least one retrieval source prefix is required")
        return cls(prefixes=normalized, label=label)

    def matches(self, source: str) -> bool:
        value = str(source or "")
        return any(value == prefix or value.startswith(f"{prefix}:") for prefix in self.prefixes)


@dataclass(frozen=True, slots=True)
class EvidenceMetrics:
    support_status: str
    support_target_met: bool
    evidence_count: int
    excluded_evidence_refs: tuple[str, ...]
    blocked_source_refs: tuple[str, ...]
    retrieval_sources: tuple[str, ...]
    freshness_receipts: tuple[str, ...]
    citation_map: tuple[tuple[str, str], ...]
    support_score_profile: dict[str, float]
    coercion_warnings: tuple[str, ...]


def extract_evidence_metrics(fec: Any, target: SupportTarget) -> EvidenceMetrics:
    """Derive serializable C0 metrics from the app-owned evidence contract."""

    evidence_items = tuple(getattr(fec, "evidence_items", ()) or ())
    retrieval_sources = tuple(getattr(fec, "retrieval_sources", ()) or ())
    evidence_sources = tuple(str(getattr(item, "source", "") or "") for item in evidence_items)
    all_sources = tuple(dict.fromkeys((*retrieval_sources, *evidence_sources)))
    excluded = tuple(getattr(fec, "excluded_evidence_refs", ()) or ())
    blocked = tuple(getattr(fec, "blocked_source_refs", ()) or ())
    freshness = tuple(getattr(fec, "freshness_receipts", ()) or ())
    citation_map = tuple(getattr(fec, "citation_map", ()) or ())
    raw_profile = tuple(getattr(fec, "support_score_profile", ()) or ())
    support_profile = {str(key): float(value) for key, value in raw_profile}
    support_status = str(getattr(fec, "support_status", "UNKNOWN") or "UNKNOWN")
    required_source_present = any(target.matches(source) for source in all_sources)
    target_met = bool(getattr(fec, "support_target_met", False)) and required_source_present
    warnings: list[str] = []
    if getattr(fec, "support_target_met", False) and not required_source_present:
        warnings.append("declared_support_target_not_backed_by_required_source")
    return EvidenceMetrics(
        support_status=support_status,
        support_target_met=target_met,
        evidence_count=len(evidence_items),
        excluded_evidence_refs=excluded,
        blocked_source_refs=blocked,
        retrieval_sources=all_sources,
        freshness_receipts=freshness,
        citation_map=citation_map,
        support_score_profile=support_profile,
        coercion_warnings=tuple(warnings),
    )


__all__ = [
    "EvidenceMetrics",
    "GateVerdict",
    "GraphTraversalResult",
    "HybridSearchResult",
    "SparseLexicalHit",
    "SparseLexicalLaneOutcome",
    "SparseLexicalLaneStatus",
    "SparseLexicalQuerySpec",
    "SupportTarget",
    "VERDICT_FAIL",
    "VERDICT_NOT_APPLICABLE",
    "VERDICT_PASS",
    "VERDICT_UNKNOWN",
    "VERDICT_WARN",
    "dedupe_hybrid_by_chunk_id",
    "extract_evidence_metrics",
    "fec_sparse_refs_from_lane_outcomes",
    "filter_candidates_exact_subphrase",
    "maybe_run_graph_rag",
    "merge_dense_sparse_rrf",
]
