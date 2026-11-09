"""Evidence-packet compaction and concurrent dispatch helpers for full-resume coherence review."""
from __future__ import annotations

import time
from typing import Any

from apps_rg.runtime.providers.wallclock_http_guard import (
    DaemonWorkerPool,
    resolve_judge_total_budget_s,
)

MAX_COMPACT_CLAIM_CHARS = 260


def resolve_coherence_judge_effort(effort: str | None) -> str:
    """Resolve whole-resume coherence judge effort without clamping high effort."""
    norm = str(effort or "").strip().lower()
    if not norm or norm == "xhigh":
        return "high"
    return norm


def compact_evidence_packet_for_prompt(evidence_packet: dict[str, Any]) -> dict[str, Any]:
    """Deduplicate repeated visible prose arrays before serializing into the judge prompt."""
    sections_in = evidence_packet.get("sections") or []
    compact_sections: list[dict[str, Any]] = []
    for sec in sections_in:
        if not isinstance(sec, dict):
            continue
        facts_compact = []
        for f in sec.get("selected_candidate_facts") or []:
            if not isinstance(f, dict):
                continue
            raw_claim = f.get("claim_text")
            claim_compact = (
                raw_claim[:MAX_COMPACT_CLAIM_CHARS]
                if isinstance(raw_claim, str) and len(raw_claim) > MAX_COMPACT_CLAIM_CHARS
                else raw_claim
            )
            entry: dict[str, Any] = {
                "fact_id": f.get("fact_id"),
                "claim_text": claim_compact,
            }
            if f.get("metric_outcome_ids"):
                entry["metric_outcome_ids"] = f.get("metric_outcome_ids")
            if f.get("metric_values"):
                entry["metric_values"] = f.get("metric_values")
            if f.get("graph_skill_node_ids"):
                entry["graph_skill_node_ids"] = f.get("graph_skill_node_ids")
            facts_compact.append(entry)
        bindings_compact = []
        for b in sec.get("graph_claim_bindings") or []:
            if not isinstance(b, dict):
                continue
            b_entry: dict[str, Any] = {
                "fact_ids": b.get("fact_ids") or [],
                "binding_status": b.get("binding_status"),
            }
            raw_visible_claim = b.get("visible_claim_text")
            if isinstance(raw_visible_claim, str) and raw_visible_claim.strip():
                b_entry["visible_claim_text"] = (
                    raw_visible_claim[:MAX_COMPACT_CLAIM_CHARS]
                    if len(raw_visible_claim) > MAX_COMPACT_CLAIM_CHARS
                    else raw_visible_claim
                )
            if b.get("claim_source_fact_ids"):
                b_entry["claim_source_fact_ids"] = b.get("claim_source_fact_ids")
            if b.get("metric_outcome_id"):
                b_entry["metric_outcome_id"] = b.get("metric_outcome_id")
            if b.get("metric_value"):
                b_entry["metric_value"] = b.get("metric_value")
            if b.get("skill_ids"):
                b_entry["skill_ids"] = b.get("skill_ids")
            bindings_compact.append(b_entry)
        compact_sections.append(
            {
                "section_id": sec.get("section_id"),
                "allocation_plan_digest": sec.get("allocation_plan_digest"),
                "claim_binding_pass": sec.get("claim_binding_pass"),
                "selected_candidate_facts": facts_compact,
                "graph_claim_bindings": bindings_compact,
            }
        )
    return {
        "schema": evidence_packet.get("schema"),
        "authority_semantics": evidence_packet.get("authority_semantics") or [],
        "sections": compact_sections,
    }


def dispatch_coherence_judges(roster: list[str], *, mode: str, evaluate_fn: Any) -> list[Any]:
    if mode != "mocked" and len(roster) > 1:
        panel_budget_s = max(10.0, resolve_judge_total_budget_s() + 5.0)
        deadline = time.monotonic() + panel_budget_s
        with DaemonWorkerPool(
            max_workers=len(roster),
            thread_name_prefix="apps_rg_coherence_judge",
        ) as pool:
            futures = [(key, pool.submit(evaluate_fn, key)) for key in roster]
            results: list[Any] = []
            for key, fut in futures:
                remaining = max(0.05, deadline - time.monotonic())
                try:
                    results.append(fut.result(timeout=remaining))
                except TimeoutError as exc:
                    raise TimeoutError(
                        f"COHERENCE_JUDGE_PANEL_TIMEOUT:provider={key}:budget_s={panel_budget_s}"
                    ) from exc
            return results
    return [evaluate_fn(key) for key in roster]


def finding_is_negative_assertion(text: str) -> bool:
    """True if finding asserts the ABSENCE of a defect rather than presence of a defect."""
    low = str(text or "").strip().lower()
    if not low:
        return False
    if low.startswith(("no ", "zero ", "none ", "not ", "neither ")):
        return True
    if any(
        phrase in low
        for phrase in (
            "is not evident",
            "not evident",
            "not found",
            "not present",
            "not observed",
            "no evidence",
            "with no ",
            "no unsupported",
            "zero unsupported",
            "free of",
            "without invention",
            "without distortion",
            "without unsupported",
        )
    ):
        return True
    if "is evident" in low:
        first_part = low.split("is evident")[0]
        if any(neg in first_part for neg in ("no ", "neither ", "not ", "zero ")):
            return True
    return False
