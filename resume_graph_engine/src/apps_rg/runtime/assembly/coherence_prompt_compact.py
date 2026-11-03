"""Evidence-packet compaction and concurrent dispatch helpers for full-resume coherence review."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any


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
            entry: dict[str, Any] = {
                "fact_id": f.get("fact_id"),
                "claim_text": f.get("claim_text"),
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
        with ThreadPoolExecutor(max_workers=len(roster)) as executor:
            futures = [executor.submit(evaluate_fn, key) for key in roster]
            return [f.result() for f in futures]
    return [evaluate_fn(key) for key in roster]
