"""Blind dual 4.7/5.0 judge evaluation & single bounded 3-attempt fresh-turn loop for executive_summary_v2."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import inspect
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from apps_rg.runtime.judges.executive_summary_judge_packet import build_executive_summary_judge_packet, write_executive_summary_judge_packet
from apps_rg.runtime.judges.executive_summary_x1d import run_llm_judges
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import executive_summary_human_dimension_floor_passes
from apps_rg.runtime.section_judge_policy import get_section_judge_policy

from .evidence_firewall import APPS_RG_SRC_ROOT, LANE_KEY
from .prompt_and_generate import GenerationTurnOutput, generate_executive_summary_v2_turn
from .x2_invariants import evaluate_executive_summary_v2_x2

MAX_V2_ATTEMPTS = 3
EXEC_SUMMARY_PASS_FLOOR = 4.7
EXEC_SUMMARY_PASS_FLOOR_0_TO_1 = round(EXEC_SUMMARY_PASS_FLOOR / 5.0, 4)


@dataclass(frozen=True)
class LoopExecutionOutcome:
    final_turn: GenerationTurnOutput
    final_x2_gates: list[dict[str, Any]]
    final_x1d_rows: list[dict[str, Any]]
    final_judge_packet: dict[str, Any] | None
    attempts_used: int
    attempt_history: list[dict[str, Any]]
    winning_attempt: int = 1


def _judge_row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "to_dict") and callable(row.to_dict):
        return dict(row.to_dict())
    if is_dataclass(row) and not isinstance(row, type):
        d = asdict(row)
        if "pass_" in d and "pass" not in d:
            d["pass"] = d.pop("pass_")
        return d
    return dict(row)


def judge_row_passes_4_7_human_bar(row: Mapping[str, Any]) -> bool:
    mode = str(row.get("evaluator_mode") or "")
    if mode == "MOCKED":
        return bool(row.get("pass")) and not bool(row.get("decisive_failure"))
    if mode != "MODEL_BACKED" or bool(row.get("provider_blocked")) or bool(row.get("decisive_failure")) or not bool(row.get("pass")):
        return False
    try:
        score = float(row.get("score") or 0.0)
    except (TypeError, ValueError):
        return False
    scale = str(row.get("score_scale") or "0_to_5")
    if (scale == "0_to_5" and score < EXEC_SUMMARY_PASS_FLOOR) or (scale == "0_to_1" and score < EXEC_SUMMARY_PASS_FLOOR_0_TO_1):
        return False
    if isinstance(dim_verdicts := row.get("dimension_verdicts"), dict):
        dims_ok, _ = executive_summary_human_dimension_floor_passes(dim_verdicts)
        if not dims_ok:
            return False
    return True


def format_x2_failure_feedback(failed_gates: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(
        ["Deterministic X2 invariants failed (rewrite from scratch to satisfy all checks):"]
        + [f"- {g.get('gate_id')}: {g.get('failure_reason')} (required: {g.get('threshold')})" for g in failed_gates]
    )


def format_blind_judge_feedback(x1d_rows: Sequence[Mapping[str, Any]]) -> str:
    lines = ["Blind 4.7/5.0 human hiring-committee judge feedback (resolve every critique cleanly from scratch):"]
    for row in x1d_rows:
        if judge_row_passes_4_7_human_bar(row):
            continue
        pname = str(row.get("provider_name") or row.get("provider_key") or "judge")
        lines.append(f"- [{pname}] score={row.get('score')}/5.0 (decisive_failure={bool(row.get('decisive_failure'))}): {str(row.get('rationale') or '').strip()[:360]}")
        lines.extend(f"  * Finding: {f}" for f in (row.get("findings") or [])[:5])
        lines.extend(f"  * Suggestion: {s}" for s in (row.get("remediation_suggestions") or [])[:4])
        if isinstance(dims := row.get("dimension_verdicts"), Mapping):
            bad_dims = [f"{k}(pass={v.get('pass')},severity={v.get('severity')},codes={v.get('codes')})" for k, v in dims.items() if isinstance(v, Mapping) and (not v.get("pass") or v.get("severity") not in {None, "none"})]
            if bad_dims:
                lines.append(f"  * Failing dimensions: {', '.join(bad_dims)}")
    return "\n".join(lines)


def evaluate_blind_dual_judges(
    *, artifact_dir: Path, attempt: int, turn: GenerationTurnOutput, selected_fact_plan: dict[str, Any],
    allowed_fact_ids: set[str], proof_pool_metadata: dict[str, Any], target_title: str,
    target_company: str, jd_text: str, briefing_text: str, judge_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plan_facts = [dict(f) for f in (selected_fact_plan.get("facts") or []) if isinstance(f, dict)]
    capsule = proof_pool_metadata.get("graph_targeting_capsule") if isinstance(proof_pool_metadata, dict) else None
    packet = build_executive_summary_judge_packet(
        resume_display_text=turn.resume_display_text, claim_ledger=turn.claim_ledger, allowed_fact_packet=plan_facts,
        allowed_fact_ids=allowed_fact_ids, target_title=target_title, target_company=target_company, jd_text=jd_text,
        briefing_text=briefing_text, parsed_output=turn.parsed_output,
        graph_targeting_capsule=capsule if isinstance(capsule, dict) else None,
        proof_pool_metadata=proof_pool_metadata, repo_root=APPS_RG_SRC_ROOT,
    )
    write_executive_summary_judge_packet(artifact_dir / ("judge_packet.json" if attempt == 1 else f"judge_packet_attempt_{attempt}.json"), packet)
    write_executive_summary_judge_packet(artifact_dir / "executive_summary_judge_packet.json", packet)
    if attempt > 1:
        write_executive_summary_judge_packet(artifact_dir / "judge_packet.json", packet)
        write_executive_summary_judge_packet(artifact_dir / "executive_summary_judge_packet_post_x2.json", packet)
    eff_mode = "mocked" if str(judge_mode).strip().lower() == "mocked" else "blocked_if_unavailable"
    raw_outputs = run_llm_judges(
        resume_display_text=turn.resume_display_text,
        claim_ledger=turn.claim_ledger,
        judge_keys=list(get_section_judge_policy(LANE_KEY).required_judge_providers),
        mode=eff_mode, artifact_base=artifact_dir, judge_packet=packet,
        judge_packet_ref=str(artifact_dir / "judge_packet.json"), compiled_prompt=turn.compiled_prompt, section_id=LANE_KEY,
    )
    return [_judge_row_to_dict(r) for r in raw_outputs], packet


def run_bounded_v2_generation_and_judge_loop(
    *, provider_name: str, judge_mode: str, temperature: float, input_payload_hash: str, run_id: str, artifact_dir: Path,
    target_company: str, target_title: str, jd_text: str, briefing_text: str, selected_fact_plan: dict[str, Any],
    allowed_fact_ids: set[str], allowed_fact_ids_ordered: Sequence[str], compact_verified_facts: Sequence[Mapping[str, Any]],
    verified_numbers: frozenset[str], verified_corpus_lower: str, proof_pool_metadata: dict[str, Any],
    generate_turn_fn: Callable[..., GenerationTurnOutput] = generate_executive_summary_v2_turn,
    evaluate_judges_fn: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]] = evaluate_blind_dual_judges,
    diagnostic_focus: str = "", force_new_seed: bool = False, reasoning_effort: str = "",
) -> LoopExecutionOutcome:
    prior_draft, rejection_feedback = "", ""
    attempt_history: list[dict[str, Any]] = []
    last_turn: GenerationTurnOutput | None = None
    last_x2: list[dict[str, Any]] = []
    last_x1d: list[dict[str, Any]] = []
    last_packet: dict[str, Any] | None = None
    winning_attempt = 1
    best_rank: tuple[int, float, float] | None = None
    fn_params = inspect.signature(generate_turn_fn).parameters
    accepts_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in fn_params.values())
    extra_turn_kw = {k: v for k, v in (("diagnostic_focus", diagnostic_focus), ("force_new_seed", force_new_seed), ("reasoning_effort", reasoning_effort)) if accepts_kw or k in fn_params}
    for attempt in range(1, MAX_V2_ATTEMPTS + 1):
        turn = generate_turn_fn(
            attempt=attempt, provider_name=provider_name, temperature=temperature, input_payload_hash=input_payload_hash,
            run_id=run_id, artifact_dir=artifact_dir, target_company=target_company, target_title=target_title,
            jd_text=jd_text, briefing_text=briefing_text, allowed_fact_ids=allowed_fact_ids,
            allowed_fact_ids_ordered=allowed_fact_ids_ordered, compact_verified_facts=compact_verified_facts,
            prior_draft=prior_draft, rejection_feedback=rejection_feedback, **extra_turn_kw,
        )
        if last_turn is None:
            last_turn = turn
        if turn.runtime_generation_status not in {"REAL_LLM", "OFFLINE_CONTRACT_STUB"}:
            x2 = evaluate_executive_summary_v2_x2(resume_display_text="", claim_ledger=[], parsed_output=None, allowed_fact_ids=allowed_fact_ids, verified_numbers=verified_numbers, verified_corpus_lower=verified_corpus_lower, target_company=target_company, jd_text=jd_text, target_role=target_title, briefing_text=briefing_text, x1d_judges=[])
            attempt_history.append({"attempt": attempt, "stage": "provider_blocked", "error": turn.parse_error})
            return LoopExecutionOutcome(final_turn=turn, final_x2_gates=x2, final_x1d_rows=[], final_judge_packet=None, attempts_used=attempt, attempt_history=attempt_history, winning_attempt=attempt)
        pre_x2 = evaluate_executive_summary_v2_x2(resume_display_text=turn.resume_display_text, claim_ledger=turn.claim_ledger, parsed_output=turn.parsed_output, allowed_fact_ids=allowed_fact_ids, verified_numbers=verified_numbers, verified_corpus_lower=verified_corpus_lower, target_company=target_company, jd_text=jd_text, target_role=target_title, briefing_text=briefing_text, x1d_judges=None)
        if failed_x2 := [g for g in pre_x2 if not g["pass"]]:
            attempt_history.append({"attempt": attempt, "stage": "x2_failed_fast", "failed_gates": [g["gate_id"] for g in failed_x2]})
            if attempt < MAX_V2_ATTEMPTS and str(provider_name).strip().lower() != "mock":
                prior_draft, rejection_feedback = turn.resume_display_text or turn.raw_output, format_x2_failure_feedback(failed_x2)
                continue
            if best_rank is None:
                last_turn = turn
                winning_attempt = attempt
                last_x2 = evaluate_executive_summary_v2_x2(resume_display_text=turn.resume_display_text, claim_ledger=turn.claim_ledger, parsed_output=turn.parsed_output, allowed_fact_ids=allowed_fact_ids, verified_numbers=verified_numbers, verified_corpus_lower=verified_corpus_lower, target_company=target_company, jd_text=jd_text, target_role=target_title, briefing_text=briefing_text, x1d_judges=last_x1d)
            break
        x1d_rows, packet = evaluate_judges_fn(
            artifact_dir=artifact_dir, attempt=attempt, turn=turn, selected_fact_plan=selected_fact_plan,
            allowed_fact_ids=allowed_fact_ids, proof_pool_metadata=proof_pool_metadata, target_title=target_title,
            target_company=target_company, jd_text=jd_text, briefing_text=briefing_text, judge_mode=judge_mode,
        )
        cur_x2 = evaluate_executive_summary_v2_x2(resume_display_text=turn.resume_display_text, claim_ledger=turn.claim_ledger, parsed_output=turn.parsed_output, allowed_fact_ids=allowed_fact_ids, verified_numbers=verified_numbers, verified_corpus_lower=verified_corpus_lower, target_company=target_company, jd_text=jd_text, target_role=target_title, briefing_text=briefing_text, x1d_judges=x1d_rows)
        both_pass = len(x1d_rows) >= 2 and all(judge_row_passes_4_7_human_bar(r) for r in x1d_rows)
        scores = [float(r.get("score") or 0.0) for r in x1d_rows]
        cur_rank = (1 if both_pass else 0, min(scores, default=0.0), sum(scores))
        if best_rank is None or cur_rank >= best_rank:
            best_rank = cur_rank
            last_turn, last_x2, last_x1d, last_packet, winning_attempt = turn, cur_x2, x1d_rows, packet, attempt
        attempt_history.append({"attempt": attempt, "stage": "x1d_evaluated", "both_judges_pass": both_pass, "scores": [r.get("score") for r in x1d_rows], "decisive_failures": [bool(r.get("decisive_failure")) for r in x1d_rows]})
        if both_pass or any(bool(r.get("provider_blocked")) for r in x1d_rows) or str(provider_name).strip().lower() == "mock":
            break
        if attempt < MAX_V2_ATTEMPTS:
            prior_draft, rejection_feedback = turn.resume_display_text, format_blind_judge_feedback(x1d_rows)
    assert last_turn is not None
    if last_packet is not None and winning_attempt != len(attempt_history):
        write_executive_summary_judge_packet(artifact_dir / "judge_packet.json", last_packet)
        write_executive_summary_judge_packet(artifact_dir / "executive_summary_judge_packet.json", last_packet)
    return LoopExecutionOutcome(final_turn=last_turn, final_x2_gates=last_x2, final_x1d_rows=last_x1d, final_judge_packet=last_packet, attempts_used=len(attempt_history), attempt_history=attempt_history, winning_attempt=winning_attempt)
