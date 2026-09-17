"""Provider retry loop for executive summary synthesis."""
from __future__ import annotations

import json
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *

__all__ = ['retry_provider_for_synthesis']

def retry_provider_for_synthesis(
    messages: list[dict[str, str]],
    provider_payload: dict[str, Any],
    raw_output: str,
    parsed: dict[str, Any],
    *,
    selected_facts: list[dict[str, Any]] | None = None,
    selected_fact_plan: dict[str, Any] | None = None,
    strategy_executive: bool = False,
    artifact_dir: Path | None = None,
    run_id: str | None = None,
    jd_text: str = "",
) -> tuple[str, dict[str, Any], str]:
    """Bounded same-authority regeneration when pre-X2 synthesis shape checks fail."""
    from apps_rg.runtime.sections.executive_summary_repair_policy import (
        synthesis_regen_max_attempts,
        synthesis_regeneration_enabled,
    )
    from apps_rg.runtime.sections.executive_summary_synthesis_monotonic import (
        evaluate_synthesis_regen_monotonicity,
    )

    if not synthesis_regeneration_enabled():
        return raw_output, parsed, ""

    first_raw = raw_output
    first_parsed = parsed
    first_text = str(parsed.get("resume_display_text") or "")
    shape_ok, reject_reason = _synthesis_shape_reject_reason(
        first_text,
        parsed,
        selected_facts=selected_facts,
        selected_fact_plan=selected_fact_plan,
        jd_text=jd_text,
    )
    if shape_ok:
        return raw_output, parsed, ""

    max_attempts = synthesis_regen_max_attempts()
    regen_receipt: dict[str, Any] = {
        "schema": "executive_summary_synthesis_regen_v2",
        "triggered": True,
        "reject_reason": reject_reason,
        "initial_candidate_digest": sha16(first_text),
        "initial_defects": [
            part.strip() for part in reject_reason.split(";") if part.strip()
        ],
        "first_pass_resume_word_count": len(re.findall(r"\S+", first_text)),
        "first_pass_claim_ledger_rows": len(list(parsed.get("claim_ledger") or [])),
        "max_attempts": max_attempts,
        "acceptance_semantics": {
            "monotonicity_accepted": "candidate improved relative to the prior draft; full pre-X2 shape closure is not implied",
            "receipt_accepted": "the selected candidate cleared every pre-X2 synthesis-shape check",
            "transport_accepted": "the provider call completed and parsed; product acceptance is not implied",
        },
        "attempts": [],
    }
    current_raw = raw_output
    current_parsed = parsed
    parse_err = ""
    baseline_messages = list(messages)
    last_mono_rejected = False

    best_raw = raw_output
    best_parsed = parsed
    best_fail_count = _shape_failure_count(
        first_text,
        parsed,
        selected_facts=selected_facts,
        selected_fact_plan=selected_fact_plan,
        jd_text=jd_text,
    )
    best_ledger_rows = len(list(parsed.get("claim_ledger") or []))

    for attempt in range(max_attempts):
        resume_text = str(current_parsed.get("resume_display_text") or "")
        prior_wc = len(re.findall(r"\S+", resume_text))
        prior_ledger_rows = len(list(current_parsed.get("claim_ledger") or []))
        shape_ok, reject_reason = _synthesis_shape_reject_reason(
            resume_text,
            current_parsed,
            selected_facts=selected_facts,
            selected_fact_plan=selected_fact_plan,
            jd_text=jd_text,
        )
        if shape_ok:
            regen_receipt["accepted"] = True
            regen_receipt["accepted_via"] = "shape_pass"
            regen_receipt["final_resume_word_count"] = prior_wc
            if artifact_dir is not None:
                write_json(artifact_dir / "synthesis_regen_receipt.json", regen_receipt)
            return current_raw, current_parsed, parse_err

        repair_user = _build_synthesis_repair_user(
            reject_reason,
            attempt_index=attempt,
            prior_word_count=prior_wc,
            prior_ledger_rows=prior_ledger_rows,
            last_monotonicity_rejected=last_mono_rejected,
            strategy_executive=strategy_executive,
            selected_fact_plan=selected_fact_plan,
        )
        repair_messages = [
            *baseline_messages,
            {"role": "assistant", "content": current_raw},
            {"role": "user", "content": repair_user},
        ]
        from apps_rg.runtime.sections.executive_summary_regen_dispatch import (
            budgeted_regen_call,
            mark_regen_call_parse,
        )

        regen_outcome = budgeted_regen_call(
            provider_payload,
            messages=repair_messages,
            phase="synthesis_regen",
            call_site="retry_provider_for_synthesis",
            cycle_index=0,
            attempt_index=attempt + 1,
            artifact_dir=artifact_dir,
            run_id=run_id,
        )
        result = regen_outcome.result
        attempt_record: dict[str, Any] = {
            "attempt": attempt + 1,
            "reject_reason": reject_reason,
            "call_id": regen_outcome.call_id,
            "dispatch_allowed": regen_outcome.dispatch_allowed,
            "block_reason": regen_outcome.block_reason,
        }
        last_mono_rejected = False
        if not regen_outcome.dispatch_allowed:
            attempt_record["skipped"] = "budget_blocked"
            regen_receipt["attempts"].append(attempt_record)
            break
        if result is None or result.runtime_generation_status != "REAL_LLM":
            attempt_record["runtime_status"] = (
                result.runtime_generation_status if result is not None else "BLOCKED"
            )
            attempt_record["skipped"] = "non_real_llm"
            regen_receipt["attempts"].append(attempt_record)
            break
        attempt_record["runtime_status"] = result.runtime_generation_status
        new_raw = result.raw_model_output
        new_parsed, new_err = parse_model_json(new_raw)
        parse_err = new_err or ""
        attempt_record["parse_ok"] = bool(new_parsed)
        mark_regen_call_parse(artifact_dir, regen_outcome.call_id, parse_ok=bool(new_parsed))
        if new_parsed:
            regen_text = str(new_parsed.get("resume_display_text") or "")
            attempt_record["candidate_digest"] = sha16(regen_text)
            attempt_record["regen_resume_word_count"] = len(re.findall(r"\S+", regen_text))
            attempt_record["regen_claim_ledger_rows"] = len(list(new_parsed.get("claim_ledger") or []))
            new_shape_ok, new_shape_reason = _synthesis_shape_reject_reason(
                regen_text,
                new_parsed,
                selected_facts=selected_facts,
                selected_fact_plan=selected_fact_plan,
                jd_text=jd_text,
            )
            attempt_record["defects_after"] = [
                part.strip()
                for part in new_shape_reason.split(";")
                if part.strip()
            ]
            attempt_record["shape_gate_snapshot"] = {
                "scope": "PRE_X2_SYNTHESIS_SHAPE",
                "pass": new_shape_ok,
                "failed_reasons": attempt_record["defects_after"],
            }
            new_fail_count = _shape_failure_count(
                regen_text,
                new_parsed,
                selected_facts=selected_facts,
                selected_fact_plan=selected_fact_plan,
                jd_text=jd_text,
            )
            attempt_record["shape_failure_count"] = new_fail_count
            mono_ok, mono_detail = evaluate_synthesis_regen_monotonicity(
                prior_parsed=current_parsed,
                prior_reject_reason=reject_reason,
                new_parsed=new_parsed,
            )
            attempt_record["monotonicity"] = mono_detail
            attempt_record["acceptance_scope"] = (
                "FULL_PRE_X2_SHAPE_PASS"
                if new_shape_ok
                else "MONOTONIC_IMPROVEMENT_ONLY"
                if mono_ok
                else "REJECTED"
            )
            attempt_record["advanced_to_next_attempt"] = bool(
                mono_ok and not new_shape_ok
            )
            new_ledger_rows = len(list(new_parsed.get("claim_ledger") or []))
            if mono_ok:
                current_raw = new_raw
                current_parsed = new_parsed
                if artifact_dir is not None and attempt == 0:
                    write_json(artifact_dir / "provider_response_synthesis_regen.json", result.to_dict())
            else:
                last_mono_rejected = True
                attempt_record["skipped"] = "monotonicity_rejected"
            if _regen_candidate_preferred(
                new_fail_count=new_fail_count,
                new_ledger_rows=new_ledger_rows,
                new_word_count=attempt_record["regen_resume_word_count"],
                best_fail_count=best_fail_count,
                best_ledger_rows=best_ledger_rows,
                best_word_count=len(re.findall(r"\S+", str(best_parsed.get("resume_display_text") or ""))),
                monotonicity_accepted=mono_ok,
            ):
                best_fail_count = new_fail_count
                best_ledger_rows = new_ledger_rows
                best_raw = new_raw
                best_parsed = new_parsed
                attempt_record["best_candidate"] = True
        else:
            attempt_record["parse_error"] = new_err
        regen_receipt["attempts"].append(attempt_record)

    final_text = str(current_parsed.get("resume_display_text") or "")
    final_ok, final_reason = _synthesis_shape_reject_reason(
        final_text,
        current_parsed,
        selected_facts=selected_facts,
        selected_fact_plan=selected_fact_plan,
        jd_text=jd_text,
    )
    final_fail_count = _shape_failure_count(
        final_text,
        current_parsed,
        selected_facts=selected_facts,
        selected_fact_plan=selected_fact_plan,
        jd_text=jd_text,
    )
    best_wc = len(re.findall(r"\S+", str(best_parsed.get("resume_display_text") or "")))
    best_text = str(best_parsed.get("resume_display_text") or "")
    best_ok, _best_reason = _synthesis_shape_reject_reason(
        best_text,
        best_parsed,
        selected_facts=selected_facts,
        selected_fact_plan=selected_fact_plan,
        jd_text=jd_text,
    )
    if (
        not final_ok
        and best_ok
        and best_fail_count == 0
        and _regen_candidate_preferred(
            new_fail_count=best_fail_count,
            new_ledger_rows=best_ledger_rows,
            new_word_count=best_wc,
            best_fail_count=final_fail_count,
            best_ledger_rows=len(list(current_parsed.get("claim_ledger") or [])),
            best_word_count=len(re.findall(r"\S+", final_text)),
            monotonicity_accepted=True,
        )
    ):
        current_raw = best_raw
        current_parsed = best_parsed
        regen_receipt["accepted_via"] = "best_candidate_fallback"
        final_text = str(current_parsed.get("resume_display_text") or "")
        final_ok, final_reason = _synthesis_shape_reject_reason(
            final_text,
            current_parsed,
            selected_facts=selected_facts,
            selected_fact_plan=selected_fact_plan,
            jd_text=jd_text,
        )
        regen_receipt["best_candidate_shape_failure_count"] = best_fail_count
    elif final_ok:
        regen_receipt["accepted_via"] = regen_receipt.get("accepted_via") or "shape_pass_after_regen"

    regen_receipt["accepted"] = final_ok
    regen_receipt["authoritative_candidate_digest"] = sha16(
        final_text if final_ok else first_text
    )
    regen_receipt["judge_stage_eligible_from_retry"] = final_ok
    if not final_ok:
        regen_receipt["final_reject_reason"] = final_reason
    regen_receipt["final_resume_word_count"] = len(re.findall(r"\S+", final_text))
    regen_receipt["final_claim_ledger_rows"] = len(list(current_parsed.get("claim_ledger") or []))
    if not final_ok:
        regen_receipt["reverted_to_first_pass"] = True
    if artifact_dir is not None:
        if regen_receipt.get("triggered") and regen_receipt.get("attempts"):
            from apps_rg.runtime.section_repair_ledger import (
                KIND_REGEN_LLM,
                record_repair,
                set_authoritative_attempt,
            )

            regen_accepted = bool(regen_receipt.get("accepted"))
            record_repair(
                artifact_dir,
                kind=KIND_REGEN_LLM,
                operation="synthesis_regen",
                reason=str(regen_receipt.get("reject_reason") or regen_receipt.get("final_reject_reason") or "")[
                    :240
                ],
                replaced_l2=regen_accepted,
            )
            if regen_accepted:
                set_authoritative_attempt(
                    artifact_dir,
                    2,
                    reason="synthesis_regen_shape_pass",
                )
        write_json(artifact_dir / "synthesis_regen_receipt.json", regen_receipt)
    if not regen_receipt.get("accepted"):
        return first_raw, first_parsed, parse_err
    return current_raw, current_parsed, parse_err

