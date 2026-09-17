"""Word budget repair and X1D judge artifact emitters."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *

WORD_BUDGET_REPAIR_RECEIPT_FILENAME = "exec_summary_word_budget_repair_receipt.json"

__all__ = ['_write_x1d_judge_artifacts', '_emit_dimension_upstream_triangulation', '_build_word_budget_repair_user', 'apply_exec_summary_word_budget_repair', 'set_word_budget_repair_authoritative_after_x2', 'WORD_BUDGET_REPAIR_RECEIPT_FILENAME']

def _write_x1d_judge_artifacts(artifact_dir: Path, x1d: list[Any]) -> None:
    """Persist judge panel outputs and per-dimension debug matrix."""
    write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": x1d})
    write_x1d_dimension_matrix_artifact(artifact_dir / "x1d_dimension_matrix.json", x1d)


def _emit_dimension_upstream_triangulation(
    artifact_dir: Path,
    *,
    x1d_judges: list[Any],
    x2_gates: list[dict[str, Any]],
    runtime_payload: dict[str, Any],
    judge_regen_cycles: dict[str, Any] | None = None,
) -> None:
    """Map dimension failures to prompt surfaces without extra judge API spend."""
    from apps_rg.runtime.sections.executive_summary_repair_policy import post_regen_judge_rescore_mode
    from apps_rg.runtime.sections.executive_summary_upstream_triangulation import (
        build_dimension_upstream_triangulation,
        write_dimension_upstream_triangulation,
    )

    manifest: dict[str, Any] = {}
    _manifest_path = artifact_dir / "generation_grade_contract_manifest.json"
    if _manifest_path.is_file():
        try:
            _raw_m = json.loads(_manifest_path.read_text(encoding="utf-8"))
            if isinstance(_raw_m, dict):
                manifest = _raw_m
        except (OSError, json.JSONDecodeError):  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
            manifest = {}
    if not judge_regen_cycles and (artifact_dir / "judge_remediation_cycles.json").is_file():
        try:
            _raw_c = json.loads((artifact_dir / "judge_remediation_cycles.json").read_text(encoding="utf-8"))
            if isinstance(_raw_c, dict):
                judge_regen_cycles = _raw_c
        except (OSError, json.JSONDecodeError):  # guardian: allow-default-fallback -- P2 burndown: fail-soft optional boundary
            judge_regen_cycles = None
    x2_failed = [str(g.get("gate_id")) for g in x2_gates if not g.get("pass")]
    body = build_dimension_upstream_triangulation(
        x1d_judges=[j if isinstance(j, dict) else getattr(j, "to_dict", lambda: {})() for j in x1d_judges],
        x2_failed_gate_ids=x2_failed,
        generation_manifest=manifest,
        judge_regen_cycles=judge_regen_cycles,
        post_regen_judge_mode=post_regen_judge_rescore_mode(),
    )
    body["run_id"] = str(runtime_payload.get("run_id") or "")
    write_dimension_upstream_triangulation(
        artifact_dir / "dimension_upstream_triangulation.json",
        body,
    )


def _build_word_budget_repair_user(words_pre: int, *, word_ceiling: int) -> str:
    """Assistant-echo + user revision message for the bounded word-budget regen."""
    return (
        f"Your paragraph is {words_pre} words; the hard ceiling is {word_ceiling} words "
        "AFTER deterministic post-processing adds a bridge sentence. "
        "Rewrite the SAME evidence arc at 105-120 words, preserving the six-row claim_ledger "
        "structure while keeping each row to at most three directly supporting source_fact_ids. "
        "Do not preserve over-dense or indirect fact IDs just to keep the old ledger shape. "
        "Keep exactly six sentences and the same narrative arc. "
        "Return one NEW compact JSON object only — no markdown fences, no commentary. "
        "Keys: executive_strategy_thesis, resume_display_text, claim_ledger, jd_alignment, "
        "gap_notes, change_log, self_check."
    )


def apply_exec_summary_word_budget_repair(
    *,
    messages: list[dict[str, str]],
    provider_payload: dict[str, Any],
    raw_output: str,
    parsed: dict[str, Any] | None,
    resume_display_text: str,
    claim_ledger: list[dict[str, Any]],
    selected_fact_plan: dict[str, Any],
    allowed_fact_ids: set[str],
    artifact_dir: Path,
    runtime_payload: dict[str, Any],
    runtime_generation_status: str,
    target_role: str = "",
    target_company: str = "",
    run_id: str | None = None,
) -> tuple[str, dict[str, Any] | None, str, list[dict[str, Any]], bool]:
    """ONE bounded word-budget regen when post-polish prose exceeds the X2 word ceiling.

    Last seam before X2: trigger == gate predicate parity (the SAME ``_resume_word_count``
    that ``x2_exec_summary_paragraph_max_words`` uses, on the SAME final post-polish
    ``resume_display_text`` the gate will see). Acceptance is fail-closed: parse ok AND
    the full deterministic polish chain re-applied AND final word count <=
    EXEC_SUMMARY_MAX_WORDS AND orphan-zero (every ledger row keeps allowed
    source_fact_ids); otherwise attempt-1 is kept and X2 fails honestly. Single-repair
    authority: suppressed with receipt when a replaced_l2 regen already happened this run.
    Kill-switch: APPS_RG_EXEC_SUMMARY_WORD_BUDGET_REPAIR (default on).
    """
    from apps_rg.runtime.sections.executive_summary_repair_policy import (
        WORD_BUDGET_REPAIR_MAX_ATTEMPTS,
        word_budget_repair_enabled,
        word_budget_repair_env_state,
    )
    from apps_rg.runtime.validators.executive_summary_x2 import (
        EXEC_SUMMARY_MAX_WORDS,
        _resume_word_count,
        check_claim_ledger_orphan_source_ids,
    )

    if runtime_generation_status != "REAL_LLM" or not isinstance(parsed, dict):
        return raw_output, parsed, resume_display_text, claim_ledger, False

    words_pre = _resume_word_count(resume_display_text)
    fired = words_pre > EXEC_SUMMARY_MAX_WORDS
    receipt: dict[str, Any] = {
        "schema": "exec_summary_word_budget_repair_v1",
        "section_id": "executive_summary",
        "run_id": str(runtime_payload.get("run_id") or ""),
        "gate_id": "x2_exec_summary_paragraph_max_words",
        "word_ceiling": EXEC_SUMMARY_MAX_WORDS,
        "fired": fired,
        "words_pre": words_pre,
        "words_post": words_pre,
        "attempted": False,
        "regen_call_made": False,
        "accepted": False,
        "rejected_reason": None,
        "regen_raw_response_ref": None,
        "bounded": {"max_attempts": WORD_BUDGET_REPAIR_MAX_ATTEMPTS, "attempts_used": 0},
        "kill_switch": word_budget_repair_env_state(),
    }
    if not fired:
        write_json(artifact_dir / WORD_BUDGET_REPAIR_RECEIPT_FILENAME, receipt)
        return raw_output, parsed, resume_display_text, claim_ledger, False

    from apps_rg.runtime.section_repair_ledger import (
        KIND_REGEN_LLM,
        load_ledger,
        record_repair,
    )

    _ledger = load_ledger(artifact_dir) or {}
    budget_consumed = any(
        r.get("kind") == KIND_REGEN_LLM and r.get("replaced_l2")
        for r in (_ledger.get("repairs") or [])
    )
    accepted = False
    if not word_budget_repair_enabled():
        receipt["rejected_reason"] = "kill_switch_off"
    elif budget_consumed:
        receipt["rejected_reason"] = "regen_budget_consumed"
    else:
        receipt["attempted"] = True
        receipt["bounded"]["attempts_used"] = 1
        from apps_rg.runtime.sections.executive_summary_context_limits import (
            CHARS_PER_TOKEN_ESTIMATE,
            ESTIMATE_SAFETY_MULTIPLIER,
            resolve_regen_max_output_tokens,
        )
        from apps_rg.runtime.sections.executive_summary_regen_dispatch import (
            budgeted_regen_call,
            mark_regen_call_parse,
        )

        # max_tokens sized from attempt-1 raw length with margin; never below the lane's
        # regen cap (the token-cap truncation class bit 4 consecutive live rolls). The
        # dispatch SSOT still hard-caps at resolve_scratch_max_output_tokens().
        _attempt1_token_estimate = (
            int(len(str(raw_output or "")) / CHARS_PER_TOKEN_ESTIMATE * ESTIMATE_SAFETY_MULTIPLIER)
            + 1
        )
        _max_out = max(resolve_regen_max_output_tokens(), _attempt1_token_estimate)
        repair_messages = [
            *messages,
            {"role": "assistant", "content": str(raw_output or "")},
            {
                "role": "user",
                "content": _build_word_budget_repair_user(
                    words_pre, word_ceiling=EXEC_SUMMARY_MAX_WORDS
                ),
            },
        ]
        outcome = budgeted_regen_call(
            provider_payload,
            messages=repair_messages,
            phase="word_budget_repair",
            call_site="apply_exec_summary_word_budget_repair",
            cycle_index=0,
            attempt_index=1,
            artifact_dir=artifact_dir,
            run_id=run_id,
            max_output_tokens=_max_out,
        )
        receipt["regen_call_made"] = bool(outcome.dispatch_allowed)
        receipt["regen_raw_response_ref"] = str(
            outcome.call_record.get("provider_response_ref") or ""
        )
        receipt["max_output_tokens"] = outcome.call_record.get("max_output_tokens")
        result = outcome.result
        if not outcome.dispatch_allowed:
            receipt["rejected_reason"] = f"regen_dispatch_blocked:{outcome.block_reason}"
        elif result is None or str(getattr(result, "runtime_generation_status", "")) != "REAL_LLM":
            receipt["rejected_reason"] = "provider_not_real"
        else:
            new_raw = str(result.raw_model_output or "")
            new_parsed, new_err = parse_model_json(new_raw)
            mark_regen_call_parse(artifact_dir, outcome.call_id, parse_ok=bool(new_parsed))
            if not isinstance(new_parsed, dict):
                receipt["rejected_reason"] = f"parse_failed:{str(new_err or '')[:160]}"
            else:
                # Re-apply the FULL deterministic polish chain (same order as attempt-1).
                plan_facts = list(selected_fact_plan.get("facts") or [])
                candidate = normalize_executive_summary_llm_output(new_parsed, selected_fact_plan)
                prune_exec_summary_claim_ledger_orphans(candidate, allowed_fact_ids)
                _coerced = coerce_resume_display_sentence_count_band(
                    str(candidate.get("resume_display_text") or "")
                )
                if _coerced != candidate.get("resume_display_text"):
                    candidate["resume_display_text"] = _coerced
                    reconcile_claim_ledger_to_sentence_count(candidate)
                from apps_rg.runtime.sections.section_authority_repairs import (
                    apply_exec_summary_display_authority_repairs,
                )

                candidate = apply_exec_summary_display_authority_repairs(
                    candidate,
                    allowed_fact_ids=allowed_fact_ids,
                    plan_facts=plan_facts,
                    artifact_dir=artifact_dir,
                    target_company=target_company,
                )
                from apps_rg.runtime.sections.executive_summary_voice_repair import (
                    finalize_executive_summary_coherence,
                )

                candidate, _wb_finalize_receipt = finalize_executive_summary_coherence(
                    candidate,
                    selected_facts=plan_facts,
                    allowed_fact_ids=allowed_fact_ids,
                    target_role=target_role,
                )
                receipt["polish_chain_reapplied"] = True
                receipt["final_word_budget_trim_applied"] = bool(
                    _wb_finalize_receipt.get("final_word_budget_trim_applied")
                )
                if _wb_finalize_receipt.get("orphan_citations_stripped") and artifact_dir is not None:
                    write_json(
                        artifact_dir / "voice_repair_orphan_citations_stripped.json",
                        {
                            "stripped": list(_wb_finalize_receipt.get("orphan_citations_stripped") or []),
                            "allowed_fact_ids": sorted(allowed_fact_ids),
                        },
                    )
                new_text = str(candidate.get("resume_display_text") or "")
                words_post = _resume_word_count(new_text)
                receipt["words_post_candidate"] = words_post
                orphan_ok, orphan_reason = check_claim_ledger_orphan_source_ids(
                    list(candidate.get("claim_ledger") or []), allowed_fact_ids
                )
                if words_post > EXEC_SUMMARY_MAX_WORDS:
                    receipt["rejected_reason"] = f"regen_still_over_budget:{words_post}"
                elif not orphan_ok:
                    receipt["rejected_reason"] = (
                        f"orphan_zero_failed:{str(orphan_reason or '')[:200]}"
                    )
                else:
                    _chg = candidate.get("change_log")
                    if not isinstance(_chg, list):
                        _chg = []
                    _chg.append(
                        {
                            "operation": "exec_summary_word_budget_repair",
                            "reason": (
                                f"x2_exec_summary_paragraph_max_words:"
                                f"{words_pre}_gt_{EXEC_SUMMARY_MAX_WORDS}"
                            ),
                        }
                    )
                    candidate["change_log"] = _chg
                    record_repair(
                        artifact_dir,
                        kind=KIND_REGEN_LLM,
                        operation="exec_summary_word_budget_repair",
                        reason=(
                            f"x2_exec_summary_paragraph_max_words:"
                            f"{words_pre}_gt_{EXEC_SUMMARY_MAX_WORDS}"
                        ),
                        replaced_l2=True,
                    )
                    raw_output = json.dumps(
                        {k: v for k, v in candidate.items() if k != "selected_fact_plan"},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    parsed = candidate
                    resume_display_text = new_text
                    new_ledger = list(candidate.get("claim_ledger") or [])
                    claim_ledger = list(new_ledger)
                    accepted = True
                    receipt["accepted"] = True
                    receipt["words_post"] = words_post

    write_json(artifact_dir / WORD_BUDGET_REPAIR_RECEIPT_FILENAME, receipt)
    return raw_output, parsed, resume_display_text, claim_ledger, accepted


def set_word_budget_repair_authoritative_after_x2(
    artifact_dir: Path,
    *,
    accepted: bool,
    x2_gates: list[dict[str, Any]],
) -> bool:
    """Lane idiom: bump authoritative attempt only after the accepted regen survives X2."""
    if not accepted:
        return False
    if [g for g in x2_gates if not g.get("pass")]:
        return False
    from apps_rg.runtime.section_repair_ledger import set_authoritative_attempt

    set_authoritative_attempt(artifact_dir, 2, reason="word_budget_repair_x2_pass")
    return True

