"""Top-level orchestrator for executive summary display authority repairs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .causal_allocation import (
    repair_exec_summary_causal_multi_metric_rows,
    repair_exec_summary_causal_multi_root_allocation_rows,
    repair_exec_summary_cross_fact_conflation_rows,
    repair_exec_summary_unallocated_metric_rows,
)
from .citation_and_mechanism import (
    repair_exec_summary_mechanism_inventory_sentences,
    repair_exec_summary_thin_sentence_weave,
    repair_required_brushstroke_citations_from_materialized_sentences,
)
from .credential_and_shape import (
    _exec_summary_shape_ok,
    repair_exec_summary_orphan_rows_with_unused_required_facts,
    strip_exec_summary_credential_dump_sentences,
    strip_target_company_tailoring_sentences,
)

def apply_exec_summary_display_authority_repairs(
    parsed: dict[str, Any],
    *,
    allowed_fact_ids: set[str] | None = None,
    plan_facts: list[dict[str, Any]] | None = None,
    artifact_dir: Path | None = None,
    target_company: str = "",
) -> dict[str, Any]:
    """In-place repair of resume_display_text for rigor-critical X2 gates."""
    if not isinstance(parsed, dict):
        return parsed
    text = str(parsed.get("resume_display_text") or "").strip()
    if not text:
        return parsed
    # Orphan-row / unused-required-fact repair: runs first so its materialized sentence is in
    # the display text before the shape + graph-fallback checks below.
    _orphan_facts = plan_facts
    if _orphan_facts is None:
        _sfp = parsed.get("selected_fact_plan")
        if isinstance(_sfp, dict):
            _orphan_facts = list(_sfp.get("facts") or [])
    _orphan_allowed = allowed_fact_ids
    if _orphan_allowed is None and _orphan_facts:
        _orphan_allowed = {
            str(f.get("fact_id") or "").strip()
            for f in _orphan_facts
            if isinstance(f, dict) and str(f.get("fact_id") or "").strip()
        }
    if _orphan_facts and _orphan_allowed:
        _brushstroke_repairs = repair_required_brushstroke_citations_from_materialized_sentences(
            parsed, allowed_fact_ids=set(_orphan_allowed), plan_facts=_orphan_facts
        )
        if _brushstroke_repairs and artifact_dir is not None:
            from apps_rg.runtime.section_repair_ledger import KIND_DETERMINISTIC_REWRITE, record_repair

            record_repair(
                artifact_dir, kind=KIND_DETERMINISTIC_REWRITE,
                operation="repair_required_brushstroke_citation",
                reason=str(_brushstroke_repairs[0].get("reason") or "")[:240], replaced_l2=True,
            )
        _orphan_repairs = repair_exec_summary_orphan_rows_with_unused_required_facts(
            parsed, allowed_fact_ids=set(_orphan_allowed), plan_facts=_orphan_facts
        )
        if _orphan_repairs and artifact_dir is not None:
            from apps_rg.runtime.section_repair_ledger import KIND_DETERMINISTIC_REWRITE, record_repair

            record_repair(
                artifact_dir, kind=KIND_DETERMINISTIC_REWRITE,
                operation="repair_orphan_row_with_unused_required_fact",
                reason=str(_orphan_repairs[0].get("reason") or "")[:240], replaced_l2=True,
            )
        text = str(parsed.get("resume_display_text") or "").strip()
        _thin_repairs = repair_exec_summary_thin_sentence_weave(parsed)
        if _thin_repairs and artifact_dir is not None:
            from apps_rg.runtime.section_repair_ledger import (
                KIND_DETERMINISTIC_REWRITE,
                record_repair,
            )

            record_repair(
                artifact_dir,
                kind=KIND_DETERMINISTIC_REWRITE,
                operation="repair_exec_summary_thin_sentence_weave",
                reason=str(_thin_repairs[0].get("reason") or "")[:240],
                replaced_l2=True,
            )
        text = str(parsed.get("resume_display_text") or "").strip()
    _mechanism_repairs = repair_exec_summary_mechanism_inventory_sentences(parsed)
    if _mechanism_repairs and artifact_dir is not None:
        from apps_rg.runtime.section_repair_ledger import (
            KIND_DETERMINISTIC_REWRITE,
            record_repair,
        )

        record_repair(
            artifact_dir,
            kind=KIND_DETERMINISTIC_REWRITE,
            operation="repair_exec_summary_mechanism_inventory_sentence",
            reason=str(_mechanism_repairs[0].get("reason") or "")[:240],
            replaced_l2=True,
        )
    _conflation_repairs = repair_exec_summary_cross_fact_conflation_rows(parsed)
    if _conflation_repairs and artifact_dir is not None:
        from apps_rg.runtime.section_repair_ledger import (
            KIND_DETERMINISTIC_REWRITE,
            record_repair,
        )

        record_repair(
            artifact_dir,
            kind=KIND_DETERMINISTIC_REWRITE,
            operation="repair_exec_summary_cross_fact_conflation_row",
            reason=str(_conflation_repairs[0].get("reason") or "")[:240],
            replaced_l2=True,
        )
    _multi_metric_repairs = repair_exec_summary_causal_multi_metric_rows(parsed)
    if _multi_metric_repairs and artifact_dir is not None:
        from apps_rg.runtime.section_repair_ledger import (
            KIND_DETERMINISTIC_REWRITE,
            record_repair,
        )

        record_repair(
            artifact_dir,
            kind=KIND_DETERMINISTIC_REWRITE,
            operation="repair_exec_summary_causal_multi_metric_row",
            reason=str(_multi_metric_repairs[0].get("reason") or "")[:240],
            replaced_l2=True,
        )
    _metric_allocation_repairs = repair_exec_summary_unallocated_metric_rows(parsed)
    if _metric_allocation_repairs and artifact_dir is not None:
        from apps_rg.runtime.section_repair_ledger import (
            KIND_DETERMINISTIC_REWRITE,
            record_repair,
        )

        record_repair(
            artifact_dir,
            kind=KIND_DETERMINISTIC_REWRITE,
            operation="repair_exec_summary_unallocated_metric_row",
            reason=str(_metric_allocation_repairs[0].get("reason") or "")[:240],
            replaced_l2=True,
        )
    _graph_allocation_repairs = repair_exec_summary_causal_multi_root_allocation_rows(parsed)
    if _graph_allocation_repairs and artifact_dir is not None:
        from apps_rg.runtime.section_repair_ledger import (
            KIND_DETERMINISTIC_REWRITE,
            record_repair,
        )

        record_repair(
            artifact_dir,
            kind=KIND_DETERMINISTIC_REWRITE,
            operation="repair_exec_summary_causal_multi_root_allocation_row",
            reason=str(_graph_allocation_repairs[0].get("reason") or "")[:240],
            replaced_l2=True,
        )
    text = str(parsed.get("resume_display_text") or "").strip()
    clog = list(parsed.get("change_log") or [])
    repaired, removed = strip_exec_summary_credential_dump_sentences(text)
    if removed and repaired != text:
        text = repaired
        clog.append(
            {
                "operation": "strip_credential_dump_sentences",
                "reason": f"removed_{len(removed)}_sentences",
            }
        )
    co_repaired, co_removed = strip_target_company_tailoring_sentences(text, target_company)
    if co_removed and co_repaired != text:
        text = co_repaired
        clog.append(
            {
                "operation": "strip_target_company_tailoring_sentences",
                "reason": f"removed_{len(co_removed)}_sentences",
            }
        )
        if artifact_dir is not None:
            from apps_rg.runtime.section_repair_ledger import (
                KIND_MECHANICAL,
                record_repair,
            )

            record_repair(
                artifact_dir,
                kind=KIND_MECHANICAL,
                operation="strip_credential_dump_sentences",
                reason=f"removed_{len(removed)}_sentences",
                replaced_l2=False,
            )
    parsed["resume_display_text"] = text
    parsed["change_log"] = clog
    from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import repair_exec_summary_bullet_echo_parsed
    parsed = repair_exec_summary_bullet_echo_parsed(parsed)
    text = str(parsed.get("resume_display_text") or "").strip()
    shape_ok, reject_reason = _exec_summary_shape_ok(text, parsed)
    if shape_ok:
        return parsed
    from apps_rg.runtime.section_repair_policy import exec_summary_display_graph_fallback_allowed

    if not exec_summary_display_graph_fallback_allowed():
        if artifact_dir is not None:
            from apps_rg.runtime.section_repair_ledger import record_repair

            record_repair(
                artifact_dir,
                kind="blocked_deterministic_rewrite",
                operation="graph_only_display_authority_fallback",
                reason=(reject_reason or "shape_fail")[:240],
                replaced_l2=False,
            )
        return parsed
    facts = plan_facts
    if facts is None:
        sfp = parsed.get("selected_fact_plan")
        if isinstance(sfp, dict):
            facts = list(sfp.get("facts") or [])
    allowed = allowed_fact_ids
    if allowed is None and facts:
        allowed = {
            str(f.get("fact_id") or f.get("candidate_fact_id") or "").strip()
            for f in facts
            if isinstance(f, dict) and str(f.get("fact_id") or f.get("candidate_fact_id") or "").strip()
        }
    if not facts or not allowed:
        return parsed
    from apps_rg.runtime.sections.exec_summary_graph_only_quality import (
        build_graph_only_executive_summary_from_facts,
    )

    resume, ledger = build_graph_only_executive_summary_from_facts(facts, allowed)
    if not resume:
        return parsed
    post_ok, _ = _exec_summary_shape_ok(resume, parsed)
    if not post_ok:
        return parsed
    parsed["resume_display_text"] = resume
    parsed["claim_ledger"] = ledger
    clog.append(
        {
            "operation": "graph_only_display_authority_fallback",
            "reason": reject_reason[:240],
        }
    )
    parsed["change_log"] = clog
    if artifact_dir is not None:
        from apps_rg.runtime.sections.executive_summary_repair_policy import (
            graph_only_repair_mode_env_state,
        )
        from apps_rg.runtime.section_repair_ledger import (
            KIND_DETERMINISTIC_REWRITE,
            record_repair,
        )

        record_repair(
            artifact_dir,
            kind=KIND_DETERMINISTIC_REWRITE,
            operation="graph_only_display_authority_fallback",
            reason=(reject_reason or "")[:240],
            replaced_l2=True,
            detail={
                "section_id": "executive_summary",
                "repair_mode": "explicit_graph_only_repair",
                "explicit_repair_mode": True,
                "repair_mode_env": graph_only_repair_mode_env_state(),
                "evidence_authority": "augmented_skills_graph",
            },
        )
    return parsed
