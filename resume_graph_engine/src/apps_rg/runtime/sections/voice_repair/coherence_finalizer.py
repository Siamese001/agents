"""Terminal executive summary coherence pipeline and post-LLM mutator orchestrator."""
from __future__ import annotations

import json
from typing import Any

from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MAX_WORDS

from .fact_utilization import (
    _align_display_override_anchors_in_resume,
    _excuse_gap_for_orphan_ledger_row,
    _strip_commercialization_thread_for_strategy_lane,
    ensure_required_allowed_fact_utilization,
)
from .filler_and_meta import strip_unsupported_source_sensitive_prose
from .ledger_reconcile import (
    _strip_claim_ledger_source_fact_ids_not_in_allowed_pool,
    apply_voice_repair_to_parsed,
    reconcile_claim_ledger_after_voice_repair,
)
from .parent_proxy import _p
from .source_fact_binding import _rebuild_claim_ledger_from_display
from .word_budget_and_arc import (
    _trim_paragraph_word_budget,
    polish_executive_summary_judge_alignment,
)

def finalize_executive_summary_coherence(
    parsed: dict[str, Any],
    *,
    selected_facts: list[dict[str, Any]] | None = None,
    allowed_fact_ids: set[str] | None = None,
    target_role: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Last post-LLM mutator: voice repair, ledger reconcile, gap excuse for display drift."""
    from apps_rg.runtime.validators.executive_summary_x2 import (
        check_claim_ledger_materialized_or_gap_excused,
        gap_notes_excuse_ledger_claim,
        ledger_row_materialized_in_display,
    )

    receipt: dict[str, Any] = {
        "schema": "executive_summary_finalize_coherence_v1",
        "voice_repair": {},
        "ledger_reconciled": False,
        "gap_excuses_added": [],
        "orphan_citations_stripped": [],
        "graph_claim_binding_repairs": [],
        "materialization_pass": False,
    }
    if not isinstance(parsed, dict):
        return parsed, receipt

    out, voice_receipt = _p("apply_voice_repair_to_parsed", apply_voice_repair_to_parsed)(
        parsed, selected_facts=selected_facts
    )
    receipt["voice_repair"] = voice_receipt
    receipt["ledger_reconciled"] = bool(voice_receipt.get("claim_ledger_reconciled"))

    out, util_receipt = _p("ensure_required_allowed_fact_utilization", ensure_required_allowed_fact_utilization)(
        out,
        selected_facts=selected_facts,
    )
    receipt["allowed_fact_utilization"] = util_receipt
    if util_receipt.get("patched_fact_ids"):
        receipt["ledger_reconciled"] = True

    out, ss_receipt = _p("strip_unsupported_source_sensitive_prose", strip_unsupported_source_sensitive_prose)(
        out, selected_facts=selected_facts
    )
    receipt["source_sensitive_strip"] = ss_receipt
    if ss_receipt.get("repaired"):
        out = _p("reconcile_claim_ledger_after_voice_repair", reconcile_claim_ledger_after_voice_repair)(out)
        receipt["ledger_reconciled"] = True

    text = str(out.get("resume_display_text") or "")
    ledger = [dict(r) for r in (out.get("claim_ledger") or []) if isinstance(r, dict)]
    gaps = list(out.get("gap_notes") or [])

    for i in range(len(ledger)):
        row = ledger[i]
        if ledger_row_materialized_in_display(row, text):
            continue
        if gap_notes_excuse_ledger_claim(row, gaps):
            continue
        out = _p("reconcile_claim_ledger_after_voice_repair", reconcile_claim_ledger_after_voice_repair)(out)
        text = str(out.get("resume_display_text") or "")
        ledger = [dict(r) for r in (out.get("claim_ledger") or []) if isinstance(r, dict)]
        row = ledger[i]
        if ledger_row_materialized_in_display(row, text):
            receipt["ledger_reconciled"] = True
            continue
        excuse = _p("_excuse_gap_for_orphan_ledger_row", _excuse_gap_for_orphan_ledger_row)(
            row,
            idx=i,
            reason="display_authority_or_voice_drift",
        )
        gaps.append(excuse)
        receipt["gap_excuses_added"].append(excuse)

    out["gap_notes"] = gaps
    out["claim_ledger"] = ledger
    mat_ok, mat_reason = check_claim_ledger_materialized_or_gap_excused(
        text, ledger, gaps
    )
    receipt["materialization_pass"] = mat_ok
    receipt["materialization_reason"] = mat_reason or ""
    out, polish_receipt = _p("polish_executive_summary_judge_alignment", polish_executive_summary_judge_alignment)(
        out,
        selected_facts=selected_facts,
        target_role=target_role,
    )
    receipt["judge_polish"] = polish_receipt
    if polish_receipt.get("applied"):
        receipt["ledger_reconciled"] = True
        text = str(out.get("resume_display_text") or "")
        ledger = [dict(r) for r in (out.get("claim_ledger") or []) if isinstance(r, dict)]
    out = _p("_align_display_override_anchors_in_resume", _align_display_override_anchors_in_resume)(out, selected_facts=selected_facts)
    out, polish_after_align = _p("polish_executive_summary_judge_alignment", polish_executive_summary_judge_alignment)(
        out,
        selected_facts=selected_facts,
        target_role=target_role,
    )
    if polish_after_align.get("applied"):
        receipt["judge_polish_after_align"] = polish_after_align
        receipt["ledger_reconciled"] = True
    out, strategy_comm_receipt = _p("_strip_commercialization_thread_for_strategy_lane", _strip_commercialization_thread_for_strategy_lane)(
        out, target_role=target_role
    )
    receipt["strategy_commercialization_strip"] = strategy_comm_receipt
    if strategy_comm_receipt.get("applied"):
        receipt["ledger_reconciled"] = True
    # Final hard cap pass: downstream polish/anchor/commercialization substitutions can
    # re-expand text after an earlier trim. Enforce the validator-owned word ceiling at
    # function end so x2_exec_summary_paragraph_max_words cannot regress.
    from apps_rg.runtime.validators.executive_summary_x2 import split_sentences

    _final_text = str(out.get("resume_display_text") or "")
    _final_sents = split_sentences(_final_text)
    _final_trimmed = _p("_trim_paragraph_word_budget", _trim_paragraph_word_budget)(_final_sents, max_words=EXEC_SUMMARY_MAX_WORDS)
    if _final_trimmed != _final_sents:
        out["resume_display_text"] = " ".join(s.strip() for s in _final_trimmed if s.strip())
        out = _p("reconcile_claim_ledger_after_voice_repair", reconcile_claim_ledger_after_voice_repair)(out)
        receipt["final_word_budget_trim_applied"] = True
        receipt["ledger_reconciled"] = True
    else:
        receipt["final_word_budget_trim_applied"] = False
    prior_ledger = json.dumps(out.get("claim_ledger") or [], ensure_ascii=False, sort_keys=True)
    out = _p("_rebuild_claim_ledger_from_display", _rebuild_claim_ledger_from_display)(out)
    if json.dumps(out.get("claim_ledger") or [], ensure_ascii=False, sort_keys=True) != prior_ledger:
        receipt["ledger_reconciled"] = True

    out, stripped = _p("_strip_claim_ledger_source_fact_ids_not_in_allowed_pool", _strip_claim_ledger_source_fact_ids_not_in_allowed_pool)(
        out,
        allowed_fact_ids=allowed_fact_ids,
    )
    if stripped:
        receipt["orphan_citations_stripped"] = stripped
        receipt["ledger_reconciled"] = True

    # ``_rebuild_claim_ledger_from_display`` is deliberately last because
    # upstream display polish can replace a sentence.  That rebuild can
    # reattach two graph-root aliases to a causal sentence even when the
    # earlier authority repair correctly clamped its attribution.  Reapply
    # the existing allocation-aware clamp after the final rebuild; it only
    # removes unrelated attribution and never changes visible prose.
    from apps_rg.runtime.sections.section_authority_repairs import (
        repair_exec_summary_causal_multi_root_allocation_rows,
    )

    graph_binding_repairs = repair_exec_summary_causal_multi_root_allocation_rows(out)
    receipt["graph_claim_binding_repairs"] = graph_binding_repairs
    if graph_binding_repairs:
        receipt["ledger_reconciled"] = True

    # Final display alignment and ledger rebuilding can replace an earlier
    # DevSecOps brushstroke.  Re-run utilization only after those terminal
    # mutators so the final materialized paragraph and its final ledger carry
    # every required approved root, rather than merely an intermediate draft.
    out, final_util_receipt = _p("ensure_required_allowed_fact_utilization", ensure_required_allowed_fact_utilization)(
        out,
        selected_facts=selected_facts,
    )
    receipt["final_allowed_fact_utilization"] = final_util_receipt
    if final_util_receipt.get("patched_fact_ids"):
        receipt["ledger_reconciled"] = True
        out = _p("_rebuild_claim_ledger_from_display", _rebuild_claim_ledger_from_display)(out)
        out, stripped = _p("_strip_claim_ledger_source_fact_ids_not_in_allowed_pool", _strip_claim_ledger_source_fact_ids_not_in_allowed_pool)(
            out,
            allowed_fact_ids=allowed_fact_ids,
        )
        if stripped:
            receipt["orphan_citations_stripped"].extend(stripped)
        final_graph_repairs = repair_exec_summary_causal_multi_root_allocation_rows(out)
        if final_graph_repairs:
            receipt["graph_claim_binding_repairs"].extend(final_graph_repairs)
    return out, receipt
