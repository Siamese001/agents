"""Deterministic role-fit and off-domain clutter validator for top-of-page sections."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
    classify_exec_summary_role_archetype,
)

OFF_DOMAIN_FINANCE_INSURANCE_PATTERNS: tuple[str, ...] = (
    "bcbs 239",
    "bcbs-239",
    "monolithic policy administration",
    "insurance platform workloads",
    "three-lines-of-defense",
    "three lines of defense",
    "erm operating models",
    "guidewire",
    "duck creek",
    "majesco",
    "solvency ii",
    "variable annuity",
    "multi-greek",
    "ccar",
)


def is_regulated_finance_or_insurance_target(
    *,
    target_role: str = "",
    jd_text: str = "",
    briefing_text: str = "",
) -> bool:
    blob = f"{target_role} {jd_text} {briefing_text}".lower()
    padded = f" {re.sub(r'[^a-z0-9]+', ' ', blob)} "
    finance_tokens = (
        " insurance ",
        " brokerage ",
        " underwriting ",
        " actuarial ",
        " actuary ",
        " basel ",
        " ccar ",
        " bcbs ",
        " solvency ",
        " guidewire ",
        " carrier ",
        " reinsurance ",
        " capital modeling ",
        " credit risk ",
        " market risk ",
    )
    return any(tok in padded for tok in finance_tokens) or (
        classify_exec_summary_role_archetype(
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=briefing_text,
        )
        == "it_strategy_regulated"
    )


def find_off_domain_clutter_hits(
    text_or_facts: str | list[dict[str, Any]],
    *,
    target_role: str = "",
    jd_text: str = "",
    briefing_text: str = "",
) -> list[str]:
    """Return off-domain banking/insurance phrases present when target role is non-financial."""
    if is_regulated_finance_or_insurance_target(
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    ):
        return []
    if isinstance(text_or_facts, str):
        blob = text_or_facts.lower()
    else:
        parts: list[str] = []
        for row in text_or_facts or []:
            if isinstance(row, dict):
                parts.append(str(row.get("claim_text") or ""))
                parts.append(str(row.get("fact_text") or ""))
                parts.append(str(row.get("text") or ""))
                parts.append(str(row.get("role_episode_bundle_id") or ""))
                parts.append(str(row.get("employer_lane") or ""))
        blob = " ".join(parts).lower()
    hits = [pat for pat in OFF_DOMAIN_FINANCE_INSURANCE_PATTERNS if pat in blob]
    return hits


def check_allocation_jd_alignment_gate(
    *,
    section_id: str,
    candidate_text: str = "",
    selected_facts: list[dict[str, Any]] | None = None,
    target_role: str = "",
    jd_text: str = "",
    briefing_text: str = "",
) -> tuple[bool, dict[str, Any], str | None]:
    """Verify top-of-page section allocation and display text align with target role domain."""
    archetype = classify_exec_summary_role_archetype(
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    text_hits = find_off_domain_clutter_hits(
        candidate_text,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    fact_hits = find_off_domain_clutter_hits(
        list(selected_facts or []),
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    all_hits = sorted(set(text_hits + fact_hits))
    defect_origin = (
        "UPSTREAM_ALLOCATION_DEFECT"
        if fact_hits
        else ("WRITER_SYNTHESIS_DEFECT" if text_hits else "NONE")
    )
    observed = {
        "section_id": section_id,
        "role_archetype": archetype,
        "off_domain_text_hits": text_hits,
        "off_domain_fact_hits": fact_hits,
        "defect_origin": defect_origin,
        "pass": len(all_hits) == 0,
    }
    if all_hits:
        return (
            False,
            observed,
            f"Off-domain regulated finance/insurance clutter in {section_id} for {archetype} role: {', '.join(all_hits)} (defect_origin={defect_origin})",
        )
    return True, observed, None


def append_allocation_jd_alignment_x2_gate(
    add_fn: Any,
    *,
    section_id: str,
    candidate_text: str = "",
    selected_facts: list[dict[str, Any]] | None = None,
    target_role: str = "",
    jd_text: str = "",
    briefing_text: str = "",
) -> None:
    align_ok, align_obs, align_reason = check_allocation_jd_alignment_gate(
        section_id=section_id,
        candidate_text=candidate_text,
        selected_facts=selected_facts,
        target_role=str(target_role or ""),
        jd_text=str(jd_text or ""),
        briefing_text=str(briefing_text or ""),
    )
    add_fn(
        "x2_allocation_jd_alignment_gate",
        align_ok,
        align_obs,
        "no_off_domain_finance_insurance_clutter",
        align_reason,
    )


def inject_allocation_jd_alignment_gate_summary(
    gate_summary: dict[str, Any] | None,
    *,
    resume_display_text: str,
    allowed_fact_packet: list[dict[str, Any]] | None,
    target_title: str,
    jd_text: str,
    briefing_text: str,
) -> dict[str, Any] | None:
    align_ok, align_obs, align_reason = check_allocation_jd_alignment_gate(
        section_id="executive_summary",
        candidate_text=resume_display_text,
        selected_facts=list(allowed_fact_packet or []),
        target_role=target_title,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    if isinstance(gate_summary, dict):
        updated = dict(gate_summary)
        updated["x2_allocation_jd_alignment_gate"] = {
            "pass": align_ok,
            "detail": align_reason or "ok",
            "defect_origin": align_obs.get("defect_origin", "NONE"),
        }
        return updated
    return gate_summary


def reconcile_allocation_jd_alignment_judge_result(
    out: dict[str, Any],
    deterministic_gate_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(deterministic_gate_summary, dict):
        return out
    align_gate = deterministic_gate_summary.get("x2_allocation_jd_alignment_gate")
    if isinstance(align_gate, dict) and align_gate.get("pass") is False:
        out["decisive_failure"] = True
        out["pass"] = False
        try:
            scale = str(out.get("score_scale") or "0_to_5").strip()
            raw_score = float(out.get("score", 0.0))
            cap = 0.68 if scale == "0_to_1" else 3.4
            if raw_score > cap:
                out["score"] = cap
        except (TypeError, ValueError):  # guardian: allow-silent-swallow -- optional score coercion
            out["score"] = 3.4
        findings = list(out.get("findings") or [])
        detail = str(align_gate.get("detail") or "Off-domain clutter detected.")
        if detail not in findings:
            findings.insert(0, detail)
        out["findings"] = findings
        out["defect_origin"] = str(align_gate.get("defect_origin") or "UPSTREAM_ALLOCATION_DEFECT")
    return out


__all__ = [
    "OFF_DOMAIN_FINANCE_INSURANCE_PATTERNS",
    "append_allocation_jd_alignment_x2_gate",
    "check_allocation_jd_alignment_gate",
    "find_off_domain_clutter_hits",
    "inject_allocation_jd_alignment_gate_summary",
    "is_regulated_finance_or_insurance_target",
    "reconcile_allocation_jd_alignment_judge_result",
]
