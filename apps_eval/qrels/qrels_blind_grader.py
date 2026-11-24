"""Frozen query-agnostic blind core-statement relevance grader & 5-axis mutual-exclusivity queue builder (DIE Parity).

Pure domain module (zero `sqlite3` imports) implementing:
1. Frozen blind core-statement 3-2-1-0 relevance grader that NEVER reads channel ranks,
   fusion scores, or `is_verified_target`, and contains zero query-specific string rules.
2. Pre-Wave-2 `grader_source_sha256` immutability hashing.
3. Deduplicated Human Label Ledger (`qrels_human_label_ledger.v1.json`) with 70/30
   grader-calibration vs. untouched human-holdout partitioning.
4. 5-axis mutual-exclusivity verifier and 4-passage (`A/B/C/D`) blind anchor queue
   builder (`hitl_qrels_queue.v1.json`) partitioned into 10-question batches.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_eval.qrels.qrels_rubric_contract import split_core_and_boilerplate

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "what", "when", "where", "which",
        "who", "why", "how", "are", "was", "were", "have", "has", "had", "into", "over", "under",
        "across", "not", "all", "its", "their", "our", "via", "does", "did", "can", "will",
        "unit", "claim", "outcomes", "evidence", "capabilities", "graph", "supports", "role",
        "episode", "skill", "phase", "employer", "time", "window", "source", "archive", "wave",
        "engagement", "metric", "story", "cluster", "bound", "epoch", "enterprise",
    }
)
_UNIT_PREFIX_RE = re.compile(r"\[Unit\]\s*[^·|]+·\s*([^·|]+)", re.IGNORECASE)
_SECTION_TAG_RE = re.compile(r"\[(?:Unit|Claim|Outcomes|Capabilities|Evidence|Scope)\]", re.IGNORECASE)
_STUB_PATTERN_RE = re.compile(
    r"(?:\bROUTES_TO_CARD\b|\bSOW_BACKED_BY\b|\bHAS_CLAIM_TEXT\b|\bis an identified\b)",
    re.IGNORECASE,
)
_NUMERIC_ANCHOR_RE = re.compile(r"\b\d+(?:\.\d+)?%?(?:ms|mw|gw|m|k|b)?\b", re.IGNORECASE)


def content_tokens(text: str) -> set[str]:
    """Extract normalized alphanumeric content tokens (>=3 chars, excluding domain-generic stopwords)."""
    cleaned = _SECTION_TAG_RE.sub(" ", str(text or ""))
    return {t for t in re.findall(r"[a-z0-9]{3,}", cleaned.casefold()) if t not in _STOPWORDS}


def numeric_anchor_tokens(text: str) -> set[str]:
    """Extract numeric/metric tokens (percentages, counts, latencies, standards) for grounding checks."""
    return {m.casefold() for m in _NUMERIC_ANCHOR_RE.findall(str(text or ""))}


def content_jaccard(text_a: str, text_b: str) -> float:
    """Compute content-word Jaccard similarity between two text passages."""
    ta, tb = content_tokens(text_a), content_tokens(text_b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def extract_unit_employer(raw_text: str) -> str:
    """Extract normalized employer label from a semantic unit header if present."""
    m = _UNIT_PREFIX_RE.search(str(raw_text or ""))
    if not m:
        return ""
    return m.group(1).strip().casefold()


def strip_unit_header(raw_text: str) -> tuple[str, str]:
    """Return (employer_key, claim_body) after removing the [Unit] structural prefix."""
    text = str(raw_text or "").strip()
    emp = extract_unit_employer(text)
    if "|" in text and text.lstrip().startswith("[Unit]"):
        body = text.split("|", 1)[1].strip()
    else:
        body = text
    body = _SECTION_TAG_RE.sub("", body).strip(" |·-")
    return emp, body


def grade_blind_core_statement(query: Mapping[str, Any], candidate: Mapping[str, Any]) -> int:
    """Assign a 3-2-1-0 relevance grade strictly from query text, reference summary, and candidate core statement.

    Never inspects fused_rank, dense_rank, sparse_rank, colbert_rank, bm25_rank, model scores,
    or `is_verified_target`. Contains zero query-specific string rules.
    """
    if not query.get("answerable", True):
        return 0

    raw_core = str(candidate.get("core_statement") or candidate.get("retrieval_text") or "").strip()
    cand_emp = extract_unit_employer(raw_core)
    core_only, _ = split_core_and_boilerplate(raw_core)
    if not core_only or _STUB_PATTERN_RE.search(core_only):
        return 0

    emp_from_core, body = strip_unit_header(core_only)
    cand_emp = cand_emp or emp_from_core
    if not body:
        return 0

    q_text = str(query.get("query_text") or "")
    q_toks = content_tokens(q_text)
    b_toks = content_tokens(body)
    q_overlap = len(q_toks & b_toks) / max(len(q_toks), 1)

    gt_raw = str(query.get("ground_truth_summary") or "").strip()
    gt_emp = extract_unit_employer(gt_raw)
    gt_only, _ = split_core_and_boilerplate(gt_raw)
    emp_from_gt, gt_body = strip_unit_header(gt_only)
    gt_emp = gt_emp or emp_from_gt
    gt_toks = content_tokens(gt_body) if gt_body else set()
    gt_overlap = len(b_toks & gt_toks) / max(len(gt_toks), 1) if gt_toks else 0.0
    gt_precision = len(b_toks & gt_toks) / max(len(b_toks), 1) if (gt_toks and b_toks) else 0.0

    same_emp = bool(cand_emp and gt_emp and cand_emp == gt_emp)
    anchor_toks = q_toks & gt_toks
    anchor_overlap = len(b_toks & anchor_toks) / max(len(anchor_toks), 1) if anchor_toks else q_overlap

    q_nums = numeric_anchor_tokens(q_text)
    b_nums = numeric_anchor_tokens(body)
    num_match_ratio = (len(q_nums & b_nums) / len(q_nums)) if q_nums else 1.0

    is_short_stub = len(body) < 55

    # Grade 3: Authoritative direct answer matching ground-truth facts & boundary
    if not is_short_stub and gt_overlap >= 0.72 and gt_precision >= 0.55 and (same_emp or not gt_emp):
        return 3
    if not is_short_stub and gt_overlap >= 0.58 and anchor_overlap >= 0.65 and num_match_ratio >= 0.50 and (same_emp or not gt_emp):
        return 3

    # Grade 2: Specific supporting evidence corroborating the query under same employer or high anchor overlap
    if not is_short_stub and same_emp and (
        gt_overlap >= 0.28 or anchor_overlap >= 0.45 or (q_overlap >= 0.38 and num_match_ratio >= 0.50)
    ):
        return 2
    if not is_short_stub and anchor_overlap >= 0.55 and q_overlap >= 0.35 and gt_overlap >= 0.22:
        return 2

    # Grade 1: Marginal topical or employer background without directly answering the inquiry
    if same_emp and (q_overlap >= 0.12 or gt_overlap >= 0.12 or anchor_overlap >= 0.15):
        return 1
    if anchor_overlap >= 0.25 and (q_overlap >= 0.18 or gt_overlap >= 0.16):
        return 1
    if q_overlap >= 0.24:
        return 1

    # Grade 0: Irrelevant, wrong employer/domain, or lexical confounder trap
    return 0


def compute_grader_source_sha256(grader_path: Path | None = None) -> str:
    """Compute SHA-256 digest of this frozen query-agnostic blind grader module."""
    target = Path(grader_path) if grader_path is not None else Path(__file__).resolve()
    return hashlib.sha256(target.read_bytes()).hexdigest()


def load_human_label_ledger(ledger_path: Path) -> dict[str, Any]:
    """Load or initialize the deduplicated human QRELS label ledger."""
    if ledger_path.is_file():
        return json.loads(ledger_path.read_text(encoding="utf-8"))
    return {
        "schema_version": "1.0.0",
        "ledger_contract": "urn:agents:qrels:human-label-ledger:1.0.0",
        "frozen_blind_grader_module": "apps_eval/qrels/qrels_blind_grader.py",
        "frozen_blind_grader_sha256": compute_grader_source_sha256(),
        "total_human_queries": 0,
        "total_human_passage_labels": 0,
        "target_total_human_passage_labels": 200,
        "remaining_passage_labels_to_collect": 200,
        "human_graded_queries": [],
    }


def save_human_label_ledger(ledger_path: Path, ledger: dict[str, Any]) -> None:
    """Persist the deduplicated human label ledger with updated totals."""
    entries = list(ledger.get("human_graded_queries") or [])
    total_labels = sum(len(e.get("record_grades") or {}) for e in entries)
    target = int(ledger.get("target_total_human_passage_labels") or 200)
    ledger["total_human_queries"] = len(entries)
    ledger["total_human_passage_labels"] = total_labels
    ledger["remaining_passage_labels_to_collect"] = max(0, target - total_labels)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def is_query_already_human_graded(query_entry: Mapping[str, Any], ledger: Mapping[str, Any]) -> bool:
    """Check whether a query_id, topic_id, target_record_id, or close paraphrase is already graded."""
    qid = str(query_entry.get("query_id") or "")
    tid = str(query_entry.get("topic_id") or "")
    target_rid = str(query_entry.get("target_record_id") or "")
    qtxt = str(query_entry.get("query_text") or "")
    for entry in ledger.get("human_graded_queries") or []:
        if qid and str(entry.get("query_id") or "") == qid:
            return True
        if tid and str(entry.get("topic_id") or "") == tid:
            return True
        if target_rid and target_rid in set(entry.get("target_record_ids") or []):
            return True
        prev_qt = str(entry.get("query_text") or "")
        if qtxt and prev_qt and content_jaccard(qtxt, prev_qt) > 0.35:
            return True
    return False


def _exceeds_passage_overlap(body_a: str, body_b: str, threshold: float) -> bool:
    ta, tb = content_tokens(body_a), content_tokens(body_b)
    if min(len(ta), len(tb)) < 4:
        return False
    return (len(ta & tb) / len(ta | tb)) > threshold


def _select_four_diverse_candidates(
    query_entry: Mapping[str, Any],
    *,
    banned_record_ids: set[str],
    max_intra_panel_jaccard: float = 0.35,
) -> list[dict[str, Any]]:
    """Select 4 mutually exclusive candidates (target + fused competitor + BM25 trap + dense neighbor)."""
    raw_cands = [
        dict(c) for c in (query_entry.get("candidates") or [])
        if str(c.get("core_statement") or c.get("retrieval_text") or "").strip()
        and not _STUB_PATTERN_RE.search(str(c.get("core_statement") or c.get("retrieval_text") or ""))
    ]
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set(banned_record_ids)

    def _add(item: dict[str, Any] | None, *, enforce_overlap: bool = True) -> None:
        if item is None or len(selected) >= 4:
            return
        rid = str(item["record_id"])
        if rid in seen_ids:
            return
        _, body = strip_unit_header(str(item.get("core_statement") or item.get("retrieval_text") or ""))
        if enforce_overlap and any(
            _exceeds_passage_overlap(
                body,
                strip_unit_header(str(prev.get("core_statement") or prev.get("retrieval_text") or ""))[1],
                max_intra_panel_jaccard,
            )
            for prev in selected
        ):
            return
        seen_ids.add(rid)
        selected.append(item)

    tid = str(query_entry.get("target_record_id") or "")
    if tid:
        _add(next((c for c in raw_cands if str(c["record_id"]) == tid), None))

    fused = sorted(raw_cands, key=lambda c: (int(c.get("fused_rank") or 999), str(c["record_id"])))
    _add(next((c for c in fused if str(c["record_id"]) not in seen_ids), None))

    bm25_trap = sorted(
        [c for c in raw_cands if c.get("bm25_rank") is not None],
        key=lambda c: (int(c["bm25_rank"]), -(int(c.get("dense_rank") or 999)), str(c["record_id"])),
    )
    _add(next((c for c in bm25_trap if str(c["record_id"]) not in seen_ids), None))

    sem_neighbor = sorted(
        [c for c in raw_cands if c.get("colbert_rank") is not None or c.get("dense_rank") is not None],
        key=lambda c: (int(c.get("colbert_rank") or c.get("dense_rank") or 999), str(c["record_id"])),
    )
    _add(next((c for c in sem_neighbor if str(c["record_id"]) not in seen_ids), None))

    for extra in fused:
        if len(selected) >= 4:
            break
        _add(extra, enforce_overlap=True)
    return selected


def verify_qrels_mutual_exclusivity(
    queue: Sequence[Mapping[str, Any]],
    ledger: Mapping[str, Any],
    *,
    max_cross_question_jaccard: float = 0.35,
    max_intra_panel_jaccard: float = 0.28,
) -> dict[str, Any]:
    """Fail-closed verifier enforcing 5-axis mutual exclusivity across queued and historical QRELS."""
    ledger_entries = list(ledger.get("human_graded_queries") or [])
    ledger_rids = {
        str(r)
        for e in ledger_entries
        for r in list((e.get("record_grades") or {}).keys()) + list(e.get("target_record_ids") or [])
        if r
    }
    seen_qids = {str(e.get("query_id") or "") for e in ledger_entries}
    seen_qtexts = [str(e.get("query_text") or "") for e in ledger_entries if e.get("query_text")]
    seen_queue_rids: set[str] = set()
    seen_target_rids: set[str] = set()
    max_obs_q_jacc = 0.0
    max_obs_p_jacc = 0.0

    for q in queue:
        if q.get("status") == "COMPLETED_HUMAN_GRADED":
            continue
        qid = str(q["query_id"])
        qtxt = str(q["query_text"])
        if qid in seen_qids:
            raise ValueError(f"Duplicate query_id in queue: {qid}")
        for prev_qt in seen_qtexts:
            j = content_jaccard(qtxt, prev_qt)
            max_obs_q_jacc = max(max_obs_q_jacc, j)
            if j > max_cross_question_jaccard:
                raise ValueError(f"Query similarity collision ({j:.3f}) on {qid}: '{qtxt}' vs '{prev_qt}'")
        seen_qids.add(qid)
        seen_qtexts.append(qtxt)

        tid = str(q.get("target_record_id") or "")
        if tid:
            if tid in seen_target_rids:
                raise ValueError(f"Duplicate target_record_id across queue on {qid}: {tid}")
            seen_target_rids.add(tid)

        cands = list(q.get("candidates") or [])
        if len(cands) != 4:
            raise ValueError(f"Expected 4 candidates on {qid}, got {len(cands)}")
        panel_bodies: list[str] = []
        for c in cands:
            rid = str(c["record_id"])
            if rid in ledger_rids or rid in seen_queue_rids:
                raise ValueError(f"Record ID collision across QRELS on {qid}: {rid}")
            seen_queue_rids.add(rid)
            _, body = strip_unit_header(str(c.get("core_statement") or ""))
            for prev_b in panel_bodies:
                ta, tb = content_tokens(body), content_tokens(prev_b)
                if min(len(ta), len(tb)) >= 4:
                    pj = len(ta & tb) / len(ta | tb)
                    max_obs_p_jacc = max(max_obs_p_jacc, pj)
                    if pj > max_intra_panel_jaccard:
                        raise ValueError(f"Intra-panel passage similarity {pj:.3f} > {max_intra_panel_jaccard} on {qid}")
            panel_bodies.append(body)

    return {
        "verified_pending_queries": sum(1 for q in queue if q.get("status") != "COMPLETED_HUMAN_GRADED"),
        "unique_pending_record_ids": len(seen_queue_rids),
        "unique_target_records": len(seen_target_rids),
        "max_cross_question_jaccard": round(max_obs_q_jacc, 4),
        "max_intra_panel_jaccard": round(max_obs_p_jacc, 4),
        "is_mutually_exclusive": True,
    }


def populate_hitl_qrels_queue_from_pool(
    pool_data: Mapping[str, Any],
    ledger: Mapping[str, Any],
    *,
    catalog: Mapping[str, Mapping[str, Any]] | None = None,
    max_anchor_queries: int = 50,
    batch_size: int = 10,
    max_intra_panel_jaccard: float = 0.28,
    include_blind_negative_probes: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build deterministic shuffled 4-passage Human Gold Anchor queue with 5-axis mutual exclusivity.

    Enforces Frontier 2026 anti-forced-choice design:
    - Selects at most ONE representative query per unique `topic_id` (zero paraphrase duplication in human batches).
    - Interleaves realistic near-domain unanswerable probes (`answerable=False`) blindly across batches
      (1 hidden unanswerable probe per 10-question batch) so raters never assume every query has a Grade 3.
    - Guarantees 100% unique `record_id` across all queued panels (`200` unique passages for 50 queries).
    """
    corpus_digest = str(pool_data.get("corpus_digest") or "")
    all_queries = list(pool_data.get("queries") or [])

    answerable_by_topic: list[Mapping[str, Any]] = []
    seen_topics: set[str] = set()
    negative_probes: list[Mapping[str, Any]] = []
    for q in all_queries:
        if is_query_already_human_graded(q, ledger):
            continue
        tid = str(q.get("topic_id") or "")
        if not q.get("answerable", True):
            if include_blind_negative_probes and tid not in seen_topics:
                seen_topics.add(tid)
                negative_probes.append(q)
            continue
        if tid and tid in seen_topics:
            continue
        if tid:
            seen_topics.add(tid)
        answerable_by_topic.append(q)

    # Interleave 1 blind near-domain negative probe into each batch at a deterministic non-predictable slot
    ordered_eligible: list[Mapping[str, Any]] = []
    neg_pool = list(negative_probes)
    ans_pool = list(answerable_by_topic)
    n_batches = max(1, (max_anchor_queries + batch_size - 1) // batch_size)
    ans_idx = 0
    for b_idx in range(n_batches):
        if len(ordered_eligible) >= max_anchor_queries:
            break
        has_neg = bool(neg_pool)
        slots_this_batch = min(batch_size, max_anchor_queries - len(ordered_eligible))
        ans_needed = slots_this_batch - (1 if has_neg else 0)
        chunk = ans_pool[ans_idx : ans_idx + ans_needed]
        ans_idx += len(chunk)
        if has_neg:
            neg_q = neg_pool.pop(0)
            pos_hash = int(hashlib.sha256(f"{corpus_digest}:negpos:{b_idx}".encode("utf-8")).hexdigest()[:8], 16)
            insert_at = pos_hash % (len(chunk) + 1)
            chunk.insert(insert_at, neg_q)
        ordered_eligible.extend(chunk)
    while len(ordered_eligible) < max_anchor_queries and ans_idx < len(ans_pool):
        ordered_eligible.append(ans_pool[ans_idx])
        ans_idx += 1

    used_rids: set[str] = {
        str(r)
        for e in (ledger.get("human_graded_queries") or [])
        for r in list((e.get("record_grades") or {}).keys()) + list(e.get("target_record_ids") or [])
        if r
    }
    eligible_targets = {str(q.get("target_record_id") or "") for q in ordered_eligible if q.get("target_record_id")}

    chosen_with_panels: list[tuple[Mapping[str, Any], list[dict[str, Any]]]] = []
    for q in ordered_eligible:
        if len(chosen_with_panels) >= max_anchor_queries:
            break
        q_target = str(q.get("target_record_id") or "")
        banned = used_rids | (eligible_targets - ({q_target} if q_target else set()))
        panel_cands = _select_four_diverse_candidates(
            q, banned_record_ids=banned, max_intra_panel_jaccard=max_intra_panel_jaccard
        )
        if len(panel_cands) < 4 and catalog is not None:
            local_seen = banned | {str(c["record_id"]) for c in panel_cands}
            panel_bodies = [
                strip_unit_header(str(c.get("core_statement") or c.get("retrieval_text") or ""))[1]
                for c in panel_cands
            ]
            for rid, rec in sorted(catalog.items()):
                if len(panel_cands) >= 4:
                    break
                if rid in local_seen:
                    continue
                core_stmt, footer = split_core_and_boilerplate(str(rec.get("retrieval_text") or ""))
                if not core_stmt or _STUB_PATTERN_RE.search(core_stmt):
                    continue
                _, body = strip_unit_header(core_stmt)
                if any(_exceeds_passage_overlap(body, pb, max_intra_panel_jaccard) for pb in panel_bodies):
                    continue
                panel_cands.append(
                    {
                        "record_id": rid,
                        "title": rec.get("title", ""),
                        "core_statement": core_stmt,
                        "boilerplate_footer": footer,
                    }
                )
                panel_bodies.append(body)
                local_seen.add(rid)
        if len(panel_cands) == 4:
            used_rids.update(str(c["record_id"]) for c in panel_cands)
            chosen_with_panels.append((q, panel_cands))

    queue: list[dict[str, Any]] = []
    slots = ("A", "B", "C", "D")
    for idx, (q, panel_cands) in enumerate(chosen_with_panels, start=1):
        seed_int = int(hashlib.sha256(f"{corpus_digest}:{q['query_id']}".encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed_int)
        shuffled = list(panel_cands)
        rng.shuffle(shuffled)

        blind_candidates: list[dict[str, Any]] = []
        for slot, cand in zip(slots, shuffled):
            core_stmt = str(cand.get("core_statement") or "")
            footer = str(cand.get("boilerplate_footer") or "")
            if not core_stmt:
                core_stmt, footer = split_core_and_boilerplate(str(cand.get("retrieval_text") or ""))
            blind_candidates.append(
                {
                    "slot": slot,
                    "record_id": str(cand["record_id"]),
                    "title": str(cand.get("title") or ""),
                    "core_statement": core_stmt,
                    "boilerplate_footer": footer,
                    "relevance_label": None,
                }
            )
        batch_index = ((idx - 1) // batch_size) + 1
        queue.append(
            {
                "qrel_id": f"anchor-{idx:02d}",
                "batch_index": batch_index,
                "query_id": str(q["query_id"]),
                "topic_id": str(q["topic_id"]),
                "partition": str(q.get("partition") or "dev"),
                "surface": str(q.get("surface") or "resume_graph_engine"),
                "tier": str(q.get("tier") or "tier2_cross_domain_orthogonal"),
                "answerable": bool(q.get("answerable", True)),
                "corpus_digest": corpus_digest,
                "query_text": str(q["query_text"]),
                "phrasing_type": str(q.get("phrasing_type") or "executive"),
                "target_record_id": str(q.get("target_record_id") or ""),
                "ground_truth_summary": str(q.get("ground_truth_summary") or ""),
                "grading_scale": "3-2-1-0_core_statement_only",
                "status": "PENDING_BLIND_GRADING",
                "candidates": blind_candidates,
            }
        )

    me_report = verify_qrels_mutual_exclusivity(queue, ledger)
    me_report["blind_negative_probes_interleaved"] = sum(1 for q in queue if not q.get("answerable", True))
    return queue, me_report


def record_human_batch_grades(
    queue: list[dict[str, Any]],
    ledger: dict[str, Any],
    batch_grades: Mapping[str, Mapping[str, int | str]],
    *,
    batch_tags: Mapping[str, Mapping[str, str]] | None = None,
    session_label: str = "frontier_2026_10q_batch_widget",
) -> int:
    """Apply human A/B/C/D grades (0..3 or 'Q' quarantine) and optional error tags into queue and ledger."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing_qids = {str(e.get("query_id") or "") for e in (ledger.get("human_graded_queries") or [])}
    tags_lookup = batch_tags or {}
    added = 0
    for item in queue:
        key = str(item["qrel_id"])
        qid = str(item["query_id"])
        slot_scores = batch_grades.get(key) or batch_grades.get(qid)
        if not slot_scores:
            continue
        slot_tags = tags_lookup.get(key) or tags_lookup.get(qid) or {}
        record_grades: dict[str, int] = {}
        quarantined_records: dict[str, str] = {}
        failure_tags: dict[str, str] = {}
        passage_texts: dict[str, str] = {}
        for cand in item["candidates"]:
            slot = str(cand["slot"])
            if slot not in slot_scores:
                raise ValueError(f"Missing human grade for {key} slot {slot}.")
            raw_val = slot_scores[slot]
            rid = str(cand["record_id"])
            passage_texts[rid] = str(cand["core_statement"])
            if str(raw_val).upper() == "Q":
                cand["relevance_label"] = "Q"
                quarantined_records[rid] = "HUMAN_ABSTAIN_OR_FLAG"
            else:
                g = int(raw_val)
                if g not in {0, 1, 2, 3}:
                    raise ValueError(f"Invalid grade {g} for {key} slot {slot}; expected 0..3 or 'Q'.")
                cand["relevance_label"] = g
                record_grades[rid] = g
                if slot in slot_tags:
                    failure_tags[rid] = str(slot_tags[slot])
        item["status"] = "COMPLETED_HUMAN_GRADED"
        if qid not in existing_qids:
            idx_num = int(key.split("-")[-1])
            split_role = "human_holdout_30pct" if (idx_num % 10 in (3, 7, 10)) else "grader_calibration_70pct"
            ledger.setdefault("human_graded_queries", []).append(
                {
                    "query_id": qid,
                    "qrel_id": key,
                    "topic_id": str(item["topic_id"]),
                    "partition": str(item["partition"]),
                    "surface": str(item["surface"]),
                    "tier": str(item.get("tier") or "tier2_cross_domain_orthogonal"),
                    "answerable": bool(item.get("answerable", True)),
                    "source_session": session_label,
                    "graded_at": now_utc,
                    "query_text": str(item["query_text"]),
                    "target_record_ids": [str(item["target_record_id"])] if item.get("target_record_id") else [],
                    "ground_truth_summary": str(item.get("ground_truth_summary") or ""),
                    "record_grades": record_grades,
                    "quarantined_records": quarantined_records,
                    "failure_tags": failure_tags,
                    "passage_texts": passage_texts,
                    "split_role": split_role,
                }
            )
            existing_qids.add(qid)
            added += 1
    return added


__all__ = [
    "compute_grader_source_sha256",
    "content_jaccard",
    "content_tokens",
    "extract_unit_employer",
    "grade_blind_core_statement",
    "is_query_already_human_graded",
    "load_human_label_ledger",
    "numeric_anchor_tokens",
    "populate_hitl_qrels_queue_from_pool",
    "record_human_batch_grades",
    "save_human_label_ledger",
    "strip_unit_header",
    "verify_qrels_mutual_exclusivity",
]
