"""4-Channel Unweighted TREC Depth-10 Candidate Pooling & Dominance Audit (DIE Parity).

Pure domain pooling module (zero `sqlite3` imports) implementing:
1. Unweighted Top-K union across Dense, Learned Sparse, ColBERT MaxSim, and FTS5 BM25
   plus verified corpus target injection.
2. Core-statement vs. boilerplate separation and MM/DD/YYYY display date normalization.
3. Zero-leakage topic-family partition validation across dev / calibration / final_holdout.
4. 3-tier BGE-M3 cosine stratification diagnostics and pre-grading channel-dominance audit.
5. Shuffled 4-passage Human Gold Anchor panel selection (A/B/C/D) stripped of rank/channel IDs.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

from apps_eval.qrels.qrels_rubric_contract import (
    normalize_display_dates,
    split_core_and_boilerplate,
    strip_blind_forbidden_fields,
)

POOLING_CHANNELS: tuple[str, ...] = ("dense", "sparse", "colbert", "bm25")
VALID_PARTITIONS: tuple[str, ...] = ("dev", "calibration", "final_holdout")
VALID_PHRASING_STYLES: tuple[str, ...] = (
    "executive",
    "engineering",
    "shorthand",
    "multi_hop",
    "exact_identifier",
    "negative_probe",
)


def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if not vec_a or len(vec_a) != len(vec_b):
        return 0.0
    dot = math.fsum(float(a) * float(b) for a, b in zip(vec_a, vec_b))
    na = math.sqrt(math.fsum(float(a) * float(a) for a in vec_a))
    nb = math.sqrt(math.fsum(float(b) * float(b) for b in vec_b))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return round(dot / (na * nb), 6)


def validate_zero_leakage_partitions(partitions_data: Mapping[str, Any]) -> dict[str, Any]:
    """Audit topic-family and query-ID separation across dev, calibration, and final_holdout."""
    topic_map = partitions_data.get("topic_assignments") or {}
    query_map = partitions_data.get("query_partitions") or {}
    dev_t = set(topic_map.get("dev") or [])
    cal_t = set(topic_map.get("calibration") or [])
    hold_t = set(topic_map.get("final_holdout") or [])
    dev_q = set(query_map.get("dev") or [])
    cal_q = set(query_map.get("calibration") or [])
    hold_q = set(query_map.get("final_holdout") or [])

    overlap_dev_cal = sorted(dev_t & cal_t)
    overlap_dev_hold = sorted(dev_t & hold_t)
    overlap_cal_hold = sorted(cal_t & hold_t)
    query_overlap = sorted((dev_q & cal_q) | (dev_q & hold_q) | (cal_q & hold_q))
    has_leakage = bool(overlap_dev_cal or overlap_dev_hold or overlap_cal_hold or query_overlap)
    return {
        "has_leakage": has_leakage,
        "dev_topics_count": len(dev_t),
        "calibration_topics_count": len(cal_t),
        "final_holdout_topics_count": len(hold_t),
        "overlap_dev_cal": overlap_dev_cal,
        "overlap_dev_holdout": overlap_dev_hold,
        "overlap_cal_holdout": overlap_cal_hold,
        "query_id_overlap": query_overlap,
    }


def audit_cosine_stratification(
    query_embeddings: Mapping[str, Sequence[float]],
    query_metadata: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute 3-tier BGE-M3 cosine stratification summary across query families."""
    by_topic: dict[str, list[str]] = {}
    for q in query_metadata:
        qid = str(q.get("query_id") or "")
        tid = str(q.get("topic_id") or "")
        if qid and tid and qid in query_embeddings:
            by_topic.setdefault(tid, []).append(qid)

    intra_sims: list[float] = []
    for qids in by_topic.values():
        for i in range(len(qids)):
            for j in range(i + 1, len(qids)):
                intra_sims.append(_cosine_similarity(query_embeddings[qids[i]], query_embeddings[qids[j]]))

    topic_reps = [qids[0] for qids in by_topic.values() if qids]
    inter_sims: list[float] = []
    for i in range(len(topic_reps)):
        for j in range(i + 1, len(topic_reps)):
            inter_sims.append(_cosine_similarity(query_embeddings[topic_reps[i]], query_embeddings[topic_reps[j]]))

    tier_counts: dict[str, int] = {}
    for q in query_metadata:
        tier = str(q.get("tier") or "tier1_corpus_anchored")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    return {
        "tier_counts": tier_counts,
        "paraphrase_pairs_checked": len(intra_sims),
        "mean_paraphrase_cosine": round(sum(intra_sims) / len(intra_sims), 4) if intra_sims else None,
        "orthogonal_pairs_checked": len(inter_sims),
        "mean_cross_topic_cosine": round(sum(inter_sims) / len(inter_sims), 4) if inter_sims else None,
        "max_cross_topic_cosine": round(max(inter_sims), 4) if inter_sims else None,
    }


def _candidate_artifact_sha256(query_id: str, record_id: str, core_statement: str) -> str:
    payload = f"{query_id}::{record_id}::{core_statement}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_trec_depth_k_query_pool(
    query: Mapping[str, Any],
    channel_rankings: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    catalog: Mapping[str, Mapping[str, Any]],
    fused_ranking: Sequence[Mapping[str, Any]] = (),
    top_k_per_channel: int = 10,
) -> dict[str, Any]:
    """Form unweighted 4-channel TREC Depth-K union pool plus verified target for one query."""
    query_id = str(query["query_id"])
    answerable = bool(query.get("answerable", True))
    target_record_id = str(query.get("target_record_id") or "").strip() or None

    per_channel_ranks: dict[str, dict[str, tuple[int, float]]] = {}
    pooled_ids: list[str] = []
    seen_ids: set[str] = set()

    def _add_id(rid: str) -> None:
        if not rid or rid in seen_ids:
            return
        rec = catalog.get(rid)
        if rec is None:
            return
        if rec.get("classification") == "restricted" or rec.get("external_eligible") is False:
            return
        seen_ids.add(rid)
        pooled_ids.append(rid)

    for channel in POOLING_CHANNELS:
        rank_map: dict[str, tuple[int, float]] = {}
        rows = channel_rankings.get(channel) or ()
        for rank_idx, row in enumerate(rows, start=1):
            rid = str(row.get("record_id") or "")
            if not rid:
                continue
            score = float(row.get("score") or 0.0)
            rank_map[rid] = (rank_idx, score)
            if rank_idx <= top_k_per_channel:
                _add_id(rid)
        per_channel_ranks[channel] = rank_map

    fused_map: dict[str, tuple[int, float]] = {}
    for f_idx, row in enumerate(fused_ranking, start=1):
        rid = str(row.get("record_id") or "")
        if not rid:
            continue
        fused_map[rid] = (f_idx, float(row.get("score") or 0.0))
        if f_idx <= top_k_per_channel:
            _add_id(rid)

    if answerable and target_record_id:
        _add_id(target_record_id)

    candidates: list[dict[str, Any]] = []
    for rid in pooled_ids:
        rec = catalog[rid]
        raw_text = str(rec.get("retrieval_text") or rec.get("description") or "")
        core_stmt, footer = split_core_and_boilerplate(raw_text)
        fused_rank, fused_score = fused_map.get(rid, (None, None))
        d_rank, d_score = per_channel_ranks["dense"].get(rid, (None, None))
        s_rank, s_score = per_channel_ranks["sparse"].get(rid, (None, None))
        c_rank, c_score = per_channel_ranks["colbert"].get(rid, (None, None))
        b_rank, b_score = per_channel_ranks["bm25"].get(rid, (None, None))
        pooled_from = [
            ch
            for ch in POOLING_CHANNELS
            if ch in per_channel_ranks
            and rid in per_channel_ranks[ch]
            and per_channel_ranks[ch][rid][0] <= top_k_per_channel
        ]
        if target_record_id and rid == target_record_id and "verified_target" not in pooled_from:
            pooled_from.append("verified_target")

        candidates.append(
            {
                "pair_id": f"{query_id}::{rid}",
                "record_id": rid,
                "surface": str(rec.get("surface") or query.get("surface") or "candidate_graph"),
                "record_type": str(rec.get("record_type") or "fact"),
                "employer": str(rec.get("employer") or ""),
                "title": normalize_display_dates(str(rec.get("title") or rid)),
                "retrieval_text": normalize_display_dates(raw_text),
                "core_statement": core_stmt,
                "boilerplate_footer": footer,
                "source_evidence_excerpts": list(rec.get("source_evidence_excerpts") or []),
                "artifact_sha256": _candidate_artifact_sha256(query_id, rid, core_stmt),
                "pooled_from": pooled_from,
                "is_verified_target": bool(target_record_id and rid == target_record_id),
                "fused_rank": fused_rank,
                "fused_score": round(fused_score, 6) if fused_score is not None else None,
                "dense_rank": d_rank,
                "dense_score": round(d_score, 6) if d_score is not None else None,
                "sparse_rank": s_rank,
                "sparse_score": round(s_score, 6) if s_score is not None else None,
                "colbert_rank": c_rank,
                "colbert_score": round(c_score, 6) if c_score is not None else None,
                "bm25_rank": b_rank,
                "bm25_score": round(b_score, 6) if b_score is not None else None,
            }
        )

    candidates.sort(
        key=lambda c: (
            c["fused_rank"] if c["fused_rank"] is not None else 10_000,
            c["record_id"],
        )
    )

    top1_score = candidates[0]["fused_score"] if candidates and candidates[0]["fused_score"] is not None else 0.0
    top2_score = (
        candidates[1]["fused_score"] if len(candidates) > 1 and candidates[1]["fused_score"] is not None else 0.0
    )
    margin = round(top1_score - top2_score, 6)

    return {
        "query_id": query_id,
        "query_text": normalize_display_dates(str(query.get("query_text") or "")),
        "topic_id": str(query.get("topic_id") or query_id),
        "topic_family": str(query.get("topic_family") or query.get("topic_id") or query_id),
        "surface": str(query.get("surface") or "candidate_graph"),
        "target_section": str(query.get("target_section") or "general"),
        "partition": str(query.get("partition") or "dev"),
        "tier": str(query.get("tier") or "tier1_corpus_anchored"),
        "phrasing_type": str(query.get("phrasing_type") or "executive"),
        "answerable": answerable,
        "target_record_id": target_record_id,
        "top1_vs_top2_margin": margin,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def compute_pre_grading_dominance_audit(pooled_queries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare target Recall@5, Recall@10, and MRR@10 across fused hybrid vs. each single channel."""
    lanes: tuple[tuple[str, str], ...] = (
        ("hybrid_fused", "fused_rank"),
        ("dense", "dense_rank"),
        ("sparse", "sparse_rank"),
        ("colbert", "colbert_rank"),
        ("bm25", "bm25_rank"),
    )
    answerable_queries = [q for q in pooled_queries if q.get("answerable", True) and q.get("target_record_id")]
    n = len(answerable_queries)
    metrics: dict[str, dict[str, float]] = {}
    for lane_name, rank_key in lanes:
        r5 = r10 = 0
        mrr10 = 0.0
        for q in answerable_queries:
            target = str(q["target_record_id"])
            t_rank: int | None = None
            for cand in q.get("candidates") or []:
                if str(cand.get("record_id")) == target:
                    raw_r = cand.get(rank_key)
                    t_rank = int(raw_r) if raw_r is not None else None
                    break
            if t_rank is not None:
                if t_rank <= 5:
                    r5 += 1
                if t_rank <= 10:
                    r10 += 1
                    mrr10 += 1.0 / t_rank
        metrics[lane_name] = {
            "recall_at_5": round(r5 / n, 4) if n else 0.0,
            "recall_at_10": round(r10 / n, 4) if n else 0.0,
            "mrr_at_10": round(mrr10 / n, 4) if n else 0.0,
        }

    single_best_r10 = max(metrics[ch]["recall_at_10"] for ch in POOLING_CHANNELS)
    single_best_mrr10 = max(metrics[ch]["mrr_at_10"] for ch in POOLING_CHANNELS)
    margins = [float(q.get("top1_vs_top2_margin") or 0.0) for q in answerable_queries]
    neg_scores = [
        float((q.get("candidates") or [{}])[0].get("fused_score") or 0.0)
        for q in pooled_queries
        if not q.get("answerable", True) and q.get("candidates")
    ]
    ans_scores = [
        float((q.get("candidates") or [{}])[0].get("fused_score") or 0.0)
        for q in answerable_queries
        if q.get("candidates")
    ]

    return {
        "answerable_queries_checked": n,
        "unanswerable_probes_checked": len(pooled_queries) - n,
        "channel_metrics": metrics,
        "hybrid_beats_or_matches_single_channels_recall10": metrics["hybrid_fused"]["recall_at_10"] >= single_best_r10,
        "hybrid_beats_or_matches_single_channels_mrr10": metrics["hybrid_fused"]["mrr_at_10"] >= single_best_mrr10,
        "mean_top1_vs_top2_margin": round(sum(margins) / len(margins), 6) if margins else 0.0,
        "mean_answerable_top1_score": round(sum(ans_scores) / len(ans_scores), 6) if ans_scores else 0.0,
        "mean_unanswerable_top1_score": round(sum(neg_scores) / len(neg_scores), 6) if neg_scores else 0.0,
    }


def build_blind_four_passage_panel(
    pooled_query: Mapping[str, Any],
    *,
    seed: int = 42,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Sample 4 diverse blind passages (A/B/C/D): target + fused competitor + lexical trap + semantic neighbor."""
    candidates = list(pooled_query.get("candidates") or [])
    if len(candidates) < 4:
        raise ValueError(
            f"Query '{pooled_query.get('query_id')}' needs >= 4 pooled candidates for A/B/C/D panel, got {len(candidates)}."
        )
    chosen: list[dict[str, Any]] = []
    chosen_ids: set[str] = set()

    def _pick(predicate_sort_key: Any) -> None:
        remaining = [c for c in candidates if str(c["record_id"]) not in chosen_ids]
        if not remaining:
            return
        remaining.sort(key=predicate_sort_key)
        pick = remaining[0]
        chosen.append(dict(pick))
        chosen_ids.add(str(pick["record_id"]))

    # 1. Verified target (if present)
    target_id = str(pooled_query.get("target_record_id") or "")
    if target_id:
        for c in candidates:
            if str(c["record_id"]) == target_id:
                chosen.append(dict(c))
                chosen_ids.add(target_id)
                break
    # 2. Top fused competitor
    _pick(lambda c: (c.get("fused_rank") if c.get("fused_rank") is not None else 10_000, str(c["record_id"])))
    # 3. Top lexical / BM25 trap
    _pick(lambda c: (c.get("bm25_rank") if c.get("bm25_rank") is not None else 10_000, str(c["record_id"])))
    # 4. Top semantic / Dense neighbor
    _pick(lambda c: (c.get("dense_rank") if c.get("dense_rank") is not None else 10_000, str(c["record_id"])))
    while len(chosen) < 4:
        _pick(lambda c: str(c["record_id"]))

    rng = random.Random(f"{seed}::{pooled_query.get('query_id')}")
    rng.shuffle(chosen)

    labels = ("A", "B", "C", "D")
    blind_passages: list[dict[str, Any]] = []
    sealed_slot_map: dict[str, str] = {}
    for label, cand in zip(labels, chosen):
        sealed_slot_map[label] = str(cand["record_id"])
        sanitized = strip_blind_forbidden_fields(cand)
        blind_passages.append(
            {
                "slot": label,
                "core_statement": sanitized["core_statement"],
                "boilerplate_footer": sanitized.get("boilerplate_footer", ""),
                "title": sanitized.get("title", ""),
                "artifact_sha256": sanitized.get("artifact_sha256", ""),
            }
        )

    panel = {
        "query_id": str(pooled_query["query_id"]),
        "query_text": str(pooled_query["query_text"]),
        "surface": str(pooled_query.get("surface") or "candidate_graph"),
        "target_section": str(pooled_query.get("target_section") or "general"),
        "passages": blind_passages,
    }
    return panel, sealed_slot_map


__all__ = [
    "POOLING_CHANNELS",
    "VALID_PARTITIONS",
    "VALID_PHRASING_STYLES",
    "audit_cosine_stratification",
    "build_blind_four_passage_panel",
    "build_trec_depth_k_query_pool",
    "compute_pre_grading_dominance_audit",
    "validate_zero_leakage_partitions",
]
