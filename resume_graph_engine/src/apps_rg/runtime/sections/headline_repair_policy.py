"""Release repair policy for headline — bounded same-authority content-signal repair only."""

from __future__ import annotations

from typing import Any, Mapping

from apps_rg.config.runtime_env import get_runtime_env_str, get_runtime_environ

# Bounded same-authority content-signal regen (retry_headline_content_signal).
RELEASE_HEADLINE_CONTENT_SIGNAL_REPAIR_ENABLED = True
# Offline multi-rung unit-test ceiling (legacy rung tests verify attempts 1..3);
# live whole-run / production execution caps content-signal repair at 1 pass so
# deterministic pre-judge gating handles clarity/overlap without 3 serial LLM loops.
CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS = 3
CONTENT_SIGNAL_REPAIR_LIVE_MAX_ATTEMPTS = 1


def resolve_content_signal_repair_max_attempts(
    environ: Mapping[str, str] | None = None,
) -> int:
    env = get_runtime_environ() if environ is None else environ
    explicit = str(env.get("APPS_RG_HEADLINE_REPAIR_MAX_ATTEMPTS") or "").strip()
    if explicit:
        try:
            return max(1, min(CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS, int(explicit)))
        except ValueError:
            pass
    if (
        str(env.get("APPS_RG_PRODUCTION_RUN") or "").strip() == "1"
        or str(env.get("APPS_RG_WHOLE_RUN_ENVELOPE") or "").strip() == "1"
        or not str(env.get("PYTEST_CURRENT_TEST") or "").strip()
    ):
        return CONTENT_SIGNAL_REPAIR_LIVE_MAX_ATTEMPTS
    return CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS


def content_signal_repair_enabled() -> bool:
    raw = (get_runtime_env_str("APPS_RG_HEADLINE_CONTENT_SIGNAL_REPAIR", "1") or "1").strip().lower()
    return RELEASE_HEADLINE_CONTENT_SIGNAL_REPAIR_ENABLED and raw not in ("0", "false", "no", "off")


def content_signal_repair_env_state() -> str:
    raw = get_runtime_env_str("APPS_RG_HEADLINE_CONTENT_SIGNAL_REPAIR")
    return raw.strip() if isinstance(raw, str) and raw.strip() else "unset"


def deterministic_clarity_trim_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    env = get_runtime_environ() if environ is None else environ
    raw = str(env.get("APPS_RG_HEADLINE_DETERMINISTIC_CLARITY_TRIM") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return bool(
        str(env.get("APPS_RG_PRODUCTION_RUN") or "").strip() == "1"
        or str(env.get("APPS_RG_WHOLE_RUN_ENVELOPE") or "").strip() == "1"
        or not str(env.get("PYTEST_CURRENT_TEST") or "").strip()
    )


def candidate_3word_subsequences(seg: str) -> list[str]:
    words = seg.split()
    if len(words) < 4:
        return []
    raw_cands = [
        " ".join(words[:3]),
        " ".join([words[0], words[2], words[3]]),
        " ".join([words[0], words[1], words[3]]),
        " ".join(words[-3:]),
    ]
    out: list[str] = []
    for c in raw_cands:
        if c and c not in out:
            out.append(c)
    return out


def find_valid_3word_clarity_trim(
    *,
    headline_line: str,
    parsed: dict[str, Any],
    runtime_payload: dict[str, Any],
    allowed_fact_ids: set[str],
    clarity_report_fn: Any,
    graph_content_contract_active: bool = False,
) -> tuple[str, dict[str, Any], dict[str, Any], list[str], list[str]] | None:
    from apps_rg.runtime.claim_ledger.headline_claim_ledger import _headline_positioning_segments
    from apps_rg.runtime.sections.lane_perf_sync_helpers import remap_trimmed_headline_claim_ledger
    from apps_rg.runtime.sections.section_product_shape_ssot import HEADLINE_WORD_MAX, HEADLINE_WORD_MIN
    from apps_rg.runtime.validators.headline_positioning_x2 import (
        POSITIONING_FAMILY_FLOOR,
        governance_signal_families_matched,
        positioning_families_matched,
    )
    from apps_rg.runtime.validators.headline_x2 import (
        evaluate_headline_literal_grounding,
        headline_executive_abstraction_report,
        headline_word_count,
    )

    segments = _headline_positioning_segments(headline_line)
    if segments is None or len(segments) != 3:
        return None
    opaque = set((clarity_report_fn(headline_line) or {}).get("opaque_segments") or [])
    if not opaque:
        return None
    prefix = headline_line.split(" | ")[0].strip() if " | " in headline_line else "SVP Engineering"
    fallback_facts = (
        runtime_payload.get("selected_fact_plan", {}).get("facts")
        if isinstance(runtime_payload.get("selected_fact_plan"), dict)
        else None
    )
    pp_meta = (
        runtime_payload.get("proof_pool_metadata")
        if isinstance(runtime_payload.get("proof_pool_metadata"), dict)
        else None
    )
    new_segs = list(segments)
    modified = False
    for idx, seg in enumerate(new_segs):
        if seg not in opaque or len(seg.split()) < 4:
            continue
        for cand_seg in candidate_3word_subsequences(seg):
            trial_segs = list(new_segs)
            trial_segs[idx] = cand_seg
            trial_line = f"{prefix} | {' | '.join(trial_segs)}"
            if not (HEADLINE_WORD_MIN <= headline_word_count(trial_line) <= HEADLINE_WORD_MAX):
                continue
            if headline_executive_abstraction_report(trial_line).get("segments_missing_executive_abstraction"):
                continue
            if cand_seg in set((clarity_report_fn(trial_line) or {}).get("opaque_segments") or []):
                continue
            if not governance_signal_families_matched(trial_line):
                continue
            if len(positioning_families_matched(trial_line)) < POSITIONING_FAMILY_FLOOR:
                continue
            if graph_content_contract_active:
                trial_parsed = dict(parsed)
                trial_parsed["headline_line"] = trial_line
                remap_trimmed_headline_claim_ledger(trial_parsed, segments, trial_segs)
                g_ok, _go, _gf = evaluate_headline_literal_grounding(
                    headline_line=trial_line,
                    parsed_output=trial_parsed,
                    claim_ledger=list(trial_parsed.get("claim_ledger") or []),
                    proof_pool_metadata=pp_meta,
                    allowed_fact_ids=allowed_fact_ids,
                    fallback_facts=fallback_facts,
                )
                if not g_ok:
                    continue
            new_segs = trial_segs
            modified = True
            break

    if not modified:
        return None
    candidate_line = f"{prefix} | {' | '.join(new_segs)}"
    new_clarity = clarity_report_fn(candidate_line)
    new_gov = governance_signal_families_matched(candidate_line)
    new_spec = positioning_families_matched(candidate_line)
    new_wc = headline_word_count(candidate_line)
    new_abs = headline_executive_abstraction_report(candidate_line)
    if not (
        new_clarity.get("pass")
        and bool(new_gov)
        and len(new_spec) >= POSITIONING_FAMILY_FLOOR
        and HEADLINE_WORD_MIN <= new_wc <= HEADLINE_WORD_MAX
        and not new_abs.get("segments_missing_executive_abstraction")
    ):
        return None
    fixed_parsed = dict(parsed)
    fixed_parsed["headline_line"] = candidate_line
    remap_trimmed_headline_claim_ledger(fixed_parsed, segments, new_segs)
    if isinstance(fixed_parsed.get("self_check"), dict):
        fixed_parsed["self_check"] = dict(fixed_parsed["self_check"])
        fixed_parsed["self_check"]["word_count"] = new_wc
        fixed_parsed["self_check"]["word_count_in_range"] = (
            HEADLINE_WORD_MIN <= new_wc <= HEADLINE_WORD_MAX
        )
    return candidate_line, fixed_parsed, new_clarity, new_gov, new_spec


__all__ = [
    "CONTENT_SIGNAL_REPAIR_LIVE_MAX_ATTEMPTS",
    "CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS",
    "RELEASE_HEADLINE_CONTENT_SIGNAL_REPAIR_ENABLED",
    "candidate_3word_subsequences",
    "content_signal_repair_enabled",
    "content_signal_repair_env_state",
    "deterministic_clarity_trim_enabled",
    "find_valid_3word_clarity_trim",
    "resolve_content_signal_repair_max_attempts",
]
