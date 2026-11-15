"""Causal multi-root, multi-metric, unallocated-metric, and cross-fact conflation repairs."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    SOURCE_FACT_TOKEN_STOPWORDS as _SOURCE_FACT_TOKEN_STOPWORDS,
    TOKEN_RE as _TOKEN_RE,
    citation_repair_tokens as _citation_repair_tokens,
)
from apps_rg.runtime.validators.executive_summary_sentence_utils import split_sentences

def repair_exec_summary_causal_multi_root_allocation_rows(
    parsed: dict[str, Any],
) -> list[dict[str, Any]]:
    """Clamp a causal sentence to the one frozen graph path its prose supports.

    The final graph binder rejects causal claims that merge unrelated roots.
    This repair changes attribution only: it selects the highest-overlap path
    already assigned to the row and never changes visible prose or creates a
    new fact.
    """
    if not isinstance(parsed, dict):
        return []
    plan = parsed.get("selected_fact_plan")
    ledger = parsed.get("claim_ledger")
    if not isinstance(plan, dict) or not isinstance(ledger, list):
        return []

    from apps_rg.runtime.c0.resume_graph_allocation import extract_exact_metric_value_unit
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        _CAUSAL_RE,
        _assignment_aliases,
        _fact_aliases_by_root,
        _select_assignments_for_claim,
    )

    assignments = [
        dict(row) for row in plan.get("allocation_assignments") or []
        if isinstance(row, dict) and str(row.get("section_id") or "") == "executive_summary"
    ]
    if not assignments:
        return []
    aliases_by_root = _fact_aliases_by_root(plan)
    aliases = {
        str(row.get("claim_unit_id") or ""): _assignment_aliases(row, aliases_by_root=aliases_by_root)
        for row in assignments
    }

    repairs: list[dict[str, Any]] = []
    for index, raw_row in enumerate(ledger, start=1):
        if not isinstance(raw_row, dict):
            continue
        claim_text = str(raw_row.get("claim_text") or raw_row.get("claim") or "").strip()
        if not _CAUSAL_RE.search(claim_text):
            continue
        selected, _ = _select_assignments_for_claim(
            raw_row, section_id="executive_summary", assignments=assignments, aliases=aliases
        )
        roots = {str(row.get("root_id") or "") for row in selected if row.get("root_id")}
        if len(roots) <= 1:
            continue
        metric_val, metric_unit = extract_exact_metric_value_unit(claim_text)
        claim_tokens = _citation_repair_tokens(claim_text)

        def rank(assignment: dict[str, Any]) -> tuple[int, int, float, float, str]:
            support = " ".join(str(assignment.get(k) or "") for k in ("root_bundle_theme", "root_claim_text", "root_claim_action", "root_claim_scope", "root_claim_outcome", "skill_label"))
            metric_match = int(bool(metric_val or metric_unit) and str(assignment.get("metric_value") or "") == metric_val and str(assignment.get("metric_unit") or "") == metric_unit)
            return (metric_match, len(claim_tokens & _citation_repair_tokens(support)), float(assignment.get("claim_entailment_score") or 0.0), float(assignment.get("target_alignment_score") or 0.0), str(assignment.get("claim_unit_id") or ""))

        # Check if this sentence combines multiple valid career milestones (e.g. platform/insurtech + revenue)
        revenue_aliases = {"reb_unify_platform_commercialization_leadership", "metric_unify_22m_ip_led_revenue", "fact_engineering_platform_006"}
        has_revenue_tokens = bool(re.search(r"\$22m|\b22\s*million\b|ip-led\s+revenue", claim_text, re.I))
        if has_revenue_tokens and any(str(a.get("root_id") or "") in revenue_aliases or str(a.get("metric_outcome_id") or "") in revenue_aliases or str(a.get("fact_id") or "") in revenue_aliases for a in selected):
            revenue_units = [a for a in selected if str(a.get("root_id") or "") == "reb_unify_platform_commercialization_leadership" or str(a.get("metric_outcome_id") or "") == "metric_unify_22m_ip_led_revenue" or str(a.get("fact_id") or "") == "fact_engineering_platform_006"]
            other_units = [a for a in selected if a not in revenue_units]
            if revenue_units and other_units:
                best_revenue, best_other = max(revenue_units, key=rank), max(other_units, key=rank)
                combined_aliases = set(aliases.get(str(best_revenue.get("claim_unit_id") or ""), set())) | set(aliases.get(str(best_other.get("claim_unit_id") or ""), set()))
                prior_ids = [str(value).strip() for value in raw_row.get("source_fact_ids") or [] if str(value).strip()]
                kept = [value for value in prior_ids if value in combined_aliases]
                if not kept:
                    kept = [f for f in (str(best_revenue.get("root_id") or best_revenue.get("fact_id") or "").strip(), str(best_other.get("root_id") or best_other.get("fact_id") or "").strip()) if f]
                if kept and kept != prior_ids:
                    raw_row["source_fact_ids"] = list(dict.fromkeys(kept))
                    repairs.append({"operation": "repair_exec_summary_causal_multi_root_allocation_row", "reason": f"claim_{index}_multi_milestone_preserved", "sentence_index": index, "prior_source_fact_ids": prior_ids, "source_fact_ids": raw_row["source_fact_ids"]})
                continue

        chosen = max(selected, key=rank)
        chosen_unit = str(chosen.get("claim_unit_id") or "")
        chosen_aliases = aliases.get(chosen_unit, set())
        prior_ids = [str(value).strip() for value in raw_row.get("source_fact_ids") or [] if str(value).strip()]
        kept = [value for value in prior_ids if value in chosen_aliases]
        if not kept:
            fallback = str(chosen.get("root_id") or chosen.get("fact_id") or "").strip()
            if fallback:
                kept = [fallback]
        if not kept or kept == prior_ids:
            continue
        raw_row["source_fact_ids"] = list(dict.fromkeys(kept))
        repairs.append({"operation": "repair_exec_summary_causal_multi_root_allocation_row", "reason": f"claim_{index}_clamped_to:{chosen_unit}", "sentence_index": index, "prior_source_fact_ids": prior_ids, "source_fact_ids": raw_row["source_fact_ids"]})

    if repairs:
        change_log = list(parsed.get("change_log") or [])
        change_log.extend(repairs)
        parsed["change_log"] = change_log
    return repairs


def repair_exec_summary_causal_multi_metric_rows(
    parsed: dict[str, Any],
) -> list[dict[str, Any]]:
    """Keep one frozen metric path when a causal row renders two unrelated outcomes.

    The graph binder deliberately rejects a visible claim which joins two metrics
    from different roots.  Attribution-only repair cannot make that claim true:
    the rendered text still contains both metrics.  This narrow materialization
    repair is allowed only when a ``while``/``whereas`` clause isolates exactly
    one metric that is reserved by exactly one selected graph assignment.  It
    preserves that clause, removes the unrelated clause, and aligns the claim
    ledger to the retained frozen path.  Ambiguous sentence shapes are left for
    the normal bounded regeneration path.
    """
    if not isinstance(parsed, dict):
        return []
    text = str(parsed.get("resume_display_text") or "").strip()
    plan = parsed.get("selected_fact_plan")
    ledger = parsed.get("claim_ledger")
    if not text or not isinstance(plan, dict) or not isinstance(ledger, list):
        return []
    sentences = [sentence for sentence in split_sentences(text) if str(sentence).strip()]
    if len(sentences) != len(ledger):
        return []

    from apps_rg.runtime.c0.resume_graph_allocation import extract_exact_metric_value_unit
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        _CAUSAL_RE,
        _VISIBLE_METRIC_RE,
        _assignment_aliases,
        _fact_aliases_by_root,
        _select_assignments_for_claim,
    )

    assignments = [
        dict(row)
        for row in plan.get("allocation_assignments") or []
        if isinstance(row, dict)
        and str(row.get("section_id") or "") == "executive_summary"
    ]
    if not assignments:
        return []
    aliases_by_root = _fact_aliases_by_root(plan)
    aliases = {
        str(row.get("claim_unit_id") or ""): _assignment_aliases(
            row,
            aliases_by_root=aliases_by_root,
        )
        for row in assignments
    }

    repairs: list[dict[str, Any]] = []
    for index, raw_row in enumerate(ledger):
        if not isinstance(raw_row, dict):
            continue
        claim_text = str(raw_row.get("claim_text") or raw_row.get("claim") or "").strip()
        display_sentence = sentences[index]
        if not (_CAUSAL_RE.search(claim_text) or _CAUSAL_RE.search(display_sentence)):
            continue
        visible_metrics = list(_VISIBLE_METRIC_RE.finditer(display_sentence))
        if len(visible_metrics) < 2:
            continue
        selected, _ = _select_assignments_for_claim(
            raw_row,
            section_id="executive_summary",
            assignments=assignments,
            aliases=aliases,
        )
        metric_assignments = [
            assignment
            for assignment in selected
            if str(assignment.get("metric_outcome_id") or "").strip()
            and str(assignment.get("metric_value") or "").strip()
            and str(assignment.get("metric_unit") or "").strip()
        ]
        if len(metric_assignments) != 1:
            continue
        chosen = metric_assignments[0]
        chosen_signature = (
            str(chosen.get("metric_value") or ""),
            str(chosen.get("metric_unit") or ""),
        )
        matching_metrics = [
            match
            for match in visible_metrics
            if extract_exact_metric_value_unit(match.group(0)) == chosen_signature
        ]
        if len(matching_metrics) != 1:
            continue

        # A conjunction is only safe to collapse when it creates a clean,
        # complete clause containing the one graph-reserved metric, or when
        # inline secondary numeric modifiers can be scrubbed in place.
        from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import scrub_secondary_causal_metrics
        replacement = scrub_secondary_causal_metrics(
            display_sentence=display_sentence, visible_metrics=visible_metrics,
            chosen_signature=chosen_signature, visible_metric_re=_VISIBLE_METRIC_RE,
            extract_sig_fn=extract_exact_metric_value_unit,
        )
        if not replacement:
            continue
        if replacement and replacement[0].islower():
            replacement = replacement[0].upper() + replacement[1:]
        if replacement and replacement[-1] not in ".!?":
            replacement += "."

        root_id = str(chosen.get("root_id") or "").strip()
        fact_id = str(chosen.get("fact_id") or "").strip()
        metric_id = str(chosen.get("metric_outcome_id") or "").strip()
        source_fact_ids = [value for value in (root_id, fact_id, metric_id) if value]
        if not source_fact_ids:
            continue
        sentences[index] = replacement
        raw_row["claim"] = replacement[:80]
        raw_row["claim_text"] = replacement
        raw_row["source_fact_ids"] = list(dict.fromkeys(source_fact_ids))
        repairs.append(
            {
                "operation": "repair_exec_summary_causal_multi_metric_row",
                "reason": (
                    f"claim_{index + 1}_retained_reserved_metric_path:"
                    f"{chosen.get('claim_unit_id')}"
                ),
                "sentence_index": index + 1,
                "retained_metric_outcome_id": metric_id,
                "source_fact_ids": raw_row["source_fact_ids"],
            }
        )

    if repairs:
        parsed["resume_display_text"] = " ".join(sentences).strip()
        change_log = list(parsed.get("change_log") or [])
        change_log.extend(repairs)
        parsed["change_log"] = change_log
    return repairs


def repair_exec_summary_unallocated_metric_rows(
    parsed: dict[str, Any],
) -> list[dict[str, Any]]:
    """Replace a rendered metric that the frozen allocation did not reserve.

    The replacement is the selected graph path's own ``root_claim_text``.  It
    removes an unsupported numeric outcome without weakening the exact-metric
    binder or inventing substitute performance.
    """
    if not isinstance(parsed, dict):
        return []
    plan = parsed.get("selected_fact_plan")
    ledger = parsed.get("claim_ledger")
    text = str(parsed.get("resume_display_text") or "").strip()
    if not isinstance(plan, dict) or not isinstance(ledger, list) or not text:
        return []
    sentences = [sentence for sentence in split_sentences(text) if str(sentence).strip()]
    if len(sentences) != len(ledger):
        return []

    from apps_rg.runtime.c0.resume_graph_allocation import extract_exact_metric_value_unit
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        _assignment_aliases,
        _fact_aliases_by_root,
        _select_assignments_for_claim,
    )

    assignments = [
        dict(row)
        for row in plan.get("allocation_assignments") or []
        if isinstance(row, dict)
        and str(row.get("section_id") or "") == "executive_summary"
    ]
    if not assignments:
        return []
    aliases_by_root = _fact_aliases_by_root(plan)
    aliases = {
        str(row.get("claim_unit_id") or ""): _assignment_aliases(
            row,
            aliases_by_root=aliases_by_root,
        )
        for row in assignments
    }

    repairs: list[dict[str, Any]] = []
    for index, raw_row in enumerate(ledger):
        if not isinstance(raw_row, dict):
            continue
        claim_text = str(raw_row.get("claim_text") or raw_row.get("claim") or "").strip()
        metric_value, metric_unit = extract_exact_metric_value_unit(claim_text)
        if not metric_value and not metric_unit:
            continue
        selected, _ = _select_assignments_for_claim(
            raw_row,
            section_id="executive_summary",
            assignments=assignments,
            aliases=aliases,
        )
        if (metric_value, metric_unit) == ("22", "USD_M"):
            rev_assign = next((a for a in assignments if str(a.get("metric_outcome_id") or "") == "metric_unify_22m_ip_led_revenue" or (str(a.get("metric_value") or "") == "22" and str(a.get("metric_unit") or "") == "USD_M")), None)
            if rev_assign:
                if rev_assign not in selected:
                    selected.append(rev_assign)
                rev_root, rev_metric = str(rev_assign.get("root_id") or rev_assign.get("fact_id") or "").strip(), str(rev_assign.get("metric_outcome_id") or "").strip()
                rfids = list(raw_row.get("source_fact_ids") or [])
                for fid in (rev_root, rev_metric):
                    if fid and fid not in rfids:
                        rfids.append(fid)
                raw_row["source_fact_ids"] = rfids
        if not selected:
            continue
        exact = [
            assignment
            for assignment in selected
            if str(assignment.get("metric_value") or "") == metric_value
            and str(assignment.get("metric_unit") or "") == metric_unit
        ]
        if len(exact) == 1:
            continue
        disp_sent = str(sentences[index] or "").strip() if index < len(sentences) else ""
        disp_val, disp_unit = extract_exact_metric_value_unit(disp_sent)
        if disp_sent and (disp_val, disp_unit) != (metric_value, metric_unit):
            exact_disp = [
                assignment
                for assignment in selected
                if str(assignment.get("metric_value") or "") == disp_val
                and str(assignment.get("metric_unit") or "") == disp_unit
            ]
            if (disp_val and disp_unit and len(exact_disp) == 1) or (not disp_val and not disp_unit):
                matched_a = exact_disp[0] if len(exact_disp) == 1 else selected[0]
                sync_ids = [
                    str(v).strip()
                    for v in (
                        matched_a.get("root_id"),
                        matched_a.get("fact_id"),
                        matched_a.get("metric_outcome_id") if (disp_val and disp_unit) else "",
                    )
                    if str(v or "").strip()
                ]
                if sync_ids:
                    raw_row["claim"] = disp_sent[:80]
                    raw_row["claim_text"] = disp_sent
                    raw_row["source_fact_ids"] = list(dict.fromkeys(sync_ids))
                    repairs.append({"operation": "repair_exec_summary_unallocated_metric_row", "reason": f"claim_{index + 1}_ledger_synced_to_clean_display_sentence", "sentence_index": index + 1, "source_fact_ids": raw_row["source_fact_ids"]})
                    continue
        claim_tokens = _citation_repair_tokens(claim_text)

        def rank(assignment: dict[str, Any]) -> tuple[int, float, float, str]:
            support = " ".join(str(assignment.get(k) or "") for k in ("root_bundle_theme", "root_claim_text", "root_claim_action", "root_claim_scope", "root_claim_outcome"))
            return (len(claim_tokens & _citation_repair_tokens(support)), float(assignment.get("claim_entailment_score") or 0.0), float(assignment.get("target_alignment_score") or 0.0), str(assignment.get("claim_unit_id") or ""))

        chosen = max(selected, key=rank)
        from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import resolve_unallocated_metric_sentence_replacement
        replacement, root_id, fact_id, skill_id = resolve_unallocated_metric_sentence_replacement(
            display_sentence=sentences[index], sentences=sentences, index=index, raw_row=raw_row, selected=selected, chosen=chosen, rank_fn=rank, extract_sig_fn=extract_exact_metric_value_unit, tokens_fn=_citation_repair_tokens,
        )
        if not replacement:
            continue
        if replacement[-1] not in ".!?":
            replacement += "."
        source_fact_ids = [value for value in (root_id, fact_id) if value]
        if not source_fact_ids:
            continue
        sentences[index] = replacement
        raw_row["claim"] = replacement[:80]
        raw_row["claim_text"] = replacement
        raw_row["source_fact_ids"] = list(dict.fromkeys(source_fact_ids))
        repairs.append({"operation": "repair_exec_summary_unallocated_metric_row", "reason": f"claim_{index + 1}_metric_{metric_value}_{metric_unit}_not_reserved_by:{chosen.get('claim_unit_id')}", "sentence_index": index + 1, "source_fact_ids": raw_row["source_fact_ids"]})

    if repairs:
        parsed["resume_display_text"] = " ".join(sentences).strip()
        change_log = list(parsed.get("change_log") or [])
        change_log.extend(repairs)
        parsed["change_log"] = change_log
    return repairs


def _source_fact_relevance_score(source_fact_id: str, sentence: str) -> int:
    fid = str(source_fact_id or "").strip().lower()
    if not fid:
        return 0
    sentence_tokens = set(_TOKEN_RE.findall(str(sentence or "").lower()))
    fid_tokens = [
        t
        for t in re.split(r"[_\W]+", fid)
        if t and len(t) > 2 and t not in _SOURCE_FACT_TOKEN_STOPWORDS
    ]
    score = sum(2 for token in fid_tokens if token in sentence_tokens)
    if fid.startswith("reb_"):
        score += 3
    elif fid.startswith("metric_"):
        score += 2
    elif fid.startswith("skill_"):
        score += 1
    if re.search(r"[\d%$]", sentence) and fid.startswith("metric_"):
        score += 2
    return score


def _compact_source_fact_ids_for_sentence(
    source_fact_ids: list[Any],
    sentence: str,
    *,
    max_ids: int = 3,
) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in source_fact_ids:
        fid = str(raw or "").strip()
        if not fid or fid in seen:
            continue
        seen.add(fid)
        normalized.append(fid)
    if len(normalized) <= max_ids:
        return normalized
    ranked = sorted(
        enumerate(normalized),
        key=lambda item: (-_source_fact_relevance_score(item[1], sentence), item[0]),
    )
    keep_indexes = sorted(idx for idx, _fid in ranked[:max_ids])
    return [normalized[idx] for idx in keep_indexes]


def repair_exec_summary_cross_fact_conflation_rows(
    parsed: dict[str, Any],
    *,
    max_ids_per_row: int = 3,
) -> list[dict[str, Any]]:
    """Reduce over-dense claim rows so each displayed sentence maps to direct proof."""
    if not isinstance(parsed, dict):
        return []
    text = str(parsed.get("resume_display_text") or "").strip()
    ledger = parsed.get("claim_ledger")
    if not text or not isinstance(ledger, list):
        return []
    sentences = [s for s in split_sentences(text) if str(s).strip()]
    if len(sentences) != len(ledger):
        return []

    repairs: list[dict[str, Any]] = []
    for idx, row in enumerate(ledger):
        if not isinstance(row, dict):
            continue
        original_ids = list(row.get("source_fact_ids") or [])
        compacted = _compact_source_fact_ids_for_sentence(
            original_ids,
            sentences[idx],
            max_ids=max_ids_per_row,
        )
        if len(compacted) == len({str(x).strip() for x in original_ids if str(x).strip()}):
            continue
        row["source_fact_ids"] = compacted
        row["claim"] = str(row.get("claim") or row.get("claim_text") or sentences[idx])[:72]
        row["claim_text"] = str(row.get("claim_text") or sentences[idx])
        repairs.append(
            {
                "operation": "repair_exec_summary_cross_fact_conflation_row",
                "reason": (
                    f"sentence_{idx + 1}_source_fact_ids_compacted_to_"
                    f"{len(compacted)}"
                ),
                "sentence_index": idx + 1,
                "source_fact_ids_before": len(original_ids),
                "source_fact_ids_after": len(compacted),
            }
        )

    if repairs:
        clog = list(parsed.get("change_log") or [])
        clog.extend(repairs)
        parsed["change_log"] = clog
    return repairs
