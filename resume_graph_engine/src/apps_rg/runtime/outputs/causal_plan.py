"""Causal allocation planning and root cause analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .section_lane_tables import *

__all__ = ['_top_rca_sections', '_root_cause', '_implementation_plan', '_failed_gate_ids', '_gate_reason', '_pre_run_reason', '_allocation_row', '_validated_plan_items', '_validated_causal_allocation', '_recommended_action']

def _top_rca_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .causal_allocation import _causal_allocation
    findings: list[dict[str, Any]] = []
    for section in sections:
        x3 = str(section.get("x3_code") or "")
        bucket = str(section.get("status_bucket") or "")
        failed = section.get("failed_gates") or []
        judge_evidence = _judge_failure_evidence(section)
        has_judge_failure = bool(judge_evidence) and x3.startswith("X3_BLOCK")
        if x3 == "X3_ALLOW" and bucket not in {"pre_run_blocked", "not_run"}:
            continue
        if (
            not failed
            and bucket not in {"pre_run_blocked", "not_run"}
            and x3 != "NOT_RUN"
            and not has_judge_failure
        ):
            continue
        gate_text = ", ".join(str(g.get("gate_id")) for g in failed if isinstance(g, dict))
        implementation_plan = _implementation_plan(section)
        causal_allocation = _causal_allocation(section)
        findings.append(
            {
                "section": str(section.get("section") or ""),
                "classification": str(section.get("failure_classification") or ""),
                "root_cause": _root_cause(section),
                "evidence": gate_text or judge_evidence or x3 or bucket,
                "causal_allocation": causal_allocation,
                "implementation_plan": implementation_plan,
                "action": _recommended_action(section),
            }
        )
    return findings


def _root_cause(section: dict[str, Any]) -> str:
    classification = str(section.get("failure_classification") or "").lower()
    section_id = str(section.get("section") or "")
    if "output contract" in classification:
        return (
            "The lane's provider output, parser, and claim-ledger contract are not a single "
            "enforced schema from generation through X2 validation."
        )
    if "specificity" in classification:
        return (
            "The lane does not bind narrative text to evidence-backed mechanism or technology "
            "requirements before deterministic specificity validation."
        )
    if "executive summary synthesis contract" in classification:
        return (
            "The executive-summary final producer path accepted repaired prose before revalidating "
            "required brushstroke coverage, row-level attribution density, and non-robotic transition shape."
        )
    if "headline executive positioning contract" in classification:
        return (
            "The headline normalization path did not rewrite a vendor-specific migration phrase "
            "into the executive positioning vocabulary required for X/Y/Z display segments."
        )
    if "x1d decisive judge failure" in classification:
        return (
            "The lane published judge-visible narrative text after normalizing the provider payload "
            "through a lossy claim-ledger path that dropped source_fact_ids needed to support material claims."
        )
    if "evidence mapping" in classification:
        return (
            "Visible content can be rendered before every term or claim has source-fact IDs, "
            "graph lineage, and claim-ledger coverage."
        )
    if "provider capability" in classification:
        return (
            "The Anthropic Messages API request included a model-incompatible temperature field "
            "after the generation model changed to a no-temperature Sonnet 5 family model."
        )
    if "selector timeout" in classification:
        return (
            "The competencies pool selector used a live provider call whose timeout budget was "
            "too short for the graph-backed candidate-selection payload."
        )
    if "provider quorum" in classification:
        return (
            "The final full-resume coherence judge panel produced fewer model-backed verdicts "
            "than the required quorum, so final aggregation stayed blocked even though the "
            "generated section lanes may have product-authorized evidence."
        )
    if "upstream certification" in classification:
        return (
            "Final aggregation correctly refused to resolve a required section whose lane evidence "
            "was review-only rather than product-authorized; the section must pass X2 and every "
            "configured X1D proof judge before final assembly can authorize the resume."
        )
    if "pre-run" in classification:
        return (
            "The lane dependency graph allows a downstream lane to be scheduled without an "
            "explicit upstream product-authorization token."
        )
    if section_id == FINAL_AGGREGATION_LANE:
        return (
            "Final aggregation eligibility is downstream of required section authorization and "
            "must stay blocked until every required lane has product-authorized evidence."
        )
    return "The failed gate evidence has not been traced to a single owning runtime contract."


def _implementation_plan(section: dict[str, Any]) -> list[str]:
    classification = str(section.get("failure_classification") or "").lower()
    section_id = str(section.get("section") or "")
    if "output contract" in classification:
        return [
            "Trace the lane's canonical output schema from provider prompt to parser to X2 gate input and remove alternate empty or partial shapes.",
            "Move required-field and bullet-count validation ahead of X2 so malformed provider responses fail before claim evaluation.",
            "Emit claim-ledger rows with source_fact_id and claim_text at generation/parsing time instead of attempting post-hoc repair.",
            "Add a fixture that proves malformed provider output is rejected and a compliant provider payload produces the expected ledger rows.",
            "Add a CI assertion that the lane cannot emit display content unless the schema and claim-ledger contract is satisfied.",
        ]
    if "specificity" in classification:
        return [
            "Define the accepted mechanism and technology vocabulary for the lane from source evidence, not from generic resume keywords.",
            "Require each narrative sentence that makes a capability claim to bind to at least one evidence-backed mechanism fact.",
            "Update the deterministic specificity gate to check evidence-bound mechanisms in the claim ledger before accepting display text.",
            "Add a regression fixture with one generic narrative rejection and one mechanism-bound narrative acceptance.",
        ]
    if "executive summary synthesis contract" in classification:
        return [
            "Rebind the final executive-summary display text to the required composition-plan brushstroke facts after every deterministic and LLM repair.",
            "Run transition-shape repair after word-budget and judge-polish rewrites so stock bridge openers cannot re-enter X2.",
            "Keep each claim-ledger row capped to directly supporting source facts while preserving one cited fact per required B1-B4 brushstroke group.",
            "Add regression fixtures using the live failed Anthropic paragraph for allowed-fact utilization and robotic-transition stack gates.",
        ]
    if "headline executive positioning contract" in classification:
        return [
            "Map vendor-specific migration fragments to proof-backed executive headline abstractions before X2 runs.",
            "Rebuild the segment claim ledger after headline rewrites so the displayed X/Y/Z phrases remain source-bound.",
            "Keep vendor names and product terms in proof evidence, not standalone display segments, unless the segment also carries an executive abstraction.",
            "Add a regression fixture using the live failed headline with AWS Migration Modernization Execution.",
        ]
    if "x1d decisive judge failure" in classification:
        return [
            "Preserve valid source_fact_ids from parsed narrative claim_ledger rows when normalizing role-episode narrative output.",
            "Add source-binding patterns for material EY insurance, ERM, CCAR, regulatory analytics, and capital/solvency claims.",
            "Keep X2 PASS insufficient for authorization when X1D factual-support judges reject the published claim ledger.",
            "Add a regression fixture using the live EY narrative where insurance operations must cite reb_ey_insurance_core_modernization.",
        ]
    if "evidence mapping" in classification:
        return [
            "List every visible term or claim missing source_fact_id, graph path ID, or claim-ledger coverage from the failed gate evidence.",
            "Change the section enrichment step so selected visible terms are emitted only with canonical source_fact_ids and graph lineage.",
            "Add a pre-display validation guard that blocks rendering when any visible claim lacks lineage or per-term ledger coverage.",
            "Add a regression fixture that rejects ungrounded terms and accepts the same terms only when backed by source facts and graph paths.",
        ]
    if "provider capability" in classification:
        return [
            "Centralize provider request capability checks for Anthropic model families before any HTTP payload is serialized.",
            "Omit temperature from Claude Sonnet 5 generation, selector, and judge payloads while preserving it for older supported Anthropic models.",
            "Persist the exact provider HTTP error into lane pre-run failure receipts and mandatory RCA evidence.",
            "Add regression tests that prove Sonnet 5 payloads omit temperature and the run ledger surfaces provider capability errors.",
        ]
    if "selector timeout" in classification:
        return [
            "Align the competencies pool-selector timeout with the bounded competencies generation budget while preserving the operator override and shared ceiling.",
            "Keep competencies selection fail-closed when the selector is unavailable so no deterministic fallback silently authorizes the lane.",
            "Persist the selector timing receipt and exact timeout error into the lane pre-run failure and mandatory RCA records.",
            "Add regression tests proving selector timeout RCA is classified as provider selection budget, not dependency-token failure.",
        ]
    if "provider quorum" in classification:
        return [
            "Repair X1D full-resume judge artifact persistence and provider transport so Gemini/OpenAI request and response artifacts can be written under long run roots.",
            "Rerun final aggregation with the required model-backed judge roster and require model_backed_pass_count to meet quorum_required before authorization.",
            "Keep final resume inline output withheld whenever provider_blocked_count is nonzero or model_backed_pass_count is below quorum_required.",
            "Add regression tests for long-path provider artifacts and mandatory RCA provider-quorum reporting.",
        ]
    if "upstream certification" in classification:
        return [
            "Name each non-certified required section in final aggregation gate evidence, including its X3 code, publish_disposition, and blocking judge ids.",
            "Repair the blocking section producer or deterministic X2 gates so judge-visible certification defects trigger same-authority regeneration before X1D.",
            "Keep final assembly fail-closed on review-only section dispositions; do not treat X2 PASS alone as latest-successful-real authorization.",
            "Add regression tests proving executive_summary judge-certification soft fail blocks aggregation and is classified separately from missing-lane or provider-quorum failures.",
        ]
    if "pre-run" in classification:
        return [
            "Represent the upstream lane's product authorization as an explicit dependency token consumed by the downstream lane.",
            "Write the upstream blocker lane, gate, and artifact path into the pre-run failure receipt when dependency authorization is absent.",
            "Update rerun orchestration so upstream repair lanes execute and certify before dependent lanes are scheduled.",
            "Add an integration fixture proving the dependent lane remains blocked until the upstream authorization token is present.",
        ]
    if section_id == FINAL_AGGREGATION_LANE:
        return [
            "Compute aggregation eligibility from the mandatory per-section product-authorization ledger instead of inferred run completion.",
            "Emit a missing-lane manifest that names each non-authorized required section and its decisive gate evidence.",
            "Keep final assembly blocked until every required section has product-authorized evidence in the same run root.",
            "Add an aggregation fixture proving one blocked or not-run required section prevents final resume assembly.",
        ]
    return [
        "Assign the failed gate family to one owning runtime contract before changing prompts or thresholds.",
        "Trace the artifact producer, parser, and validator for that contract and identify where invalid state first becomes representable.",
        "Add a contract-level regression fixture at that boundary so symptom-only downstream repairs cannot pass.",
    ]


def _failed_gate_ids(section: dict[str, Any]) -> list[str]:
    return [
        str(gate.get("gate_id") or "unknown_gate")
        for gate in section.get("failed_gates") or []
        if isinstance(gate, dict)
    ]


def _gate_reason(section: dict[str, Any], *needles: str) -> str:
    lowered = [needle.lower() for needle in needles]
    for gate in section.get("failed_gates") or []:
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("gate_id") or "").lower()
        reason = str(gate.get("failure_reason") or "").strip()
        observed = gate.get("observed_value")
        haystack = f"{gate_id} {reason}".lower()
        if lowered and not any(needle in haystack for needle in lowered):
            continue
        if observed not in (None, "", [], {}):
            return f"{gate.get('gate_id')}: {reason or observed} observed={observed}"
        return f"{gate.get('gate_id')}: {reason or 'failed'}"
    return ""


def _pre_run_reason(section: dict[str, Any]) -> str:
    pre_run = section.get("pre_run_failure")
    if not isinstance(pre_run, dict):
        return ""
    blocker = pre_run.get("blocker") or pre_run.get("lane_exec_status") or section.get("x3_code")
    lane_status = pre_run.get("lane_exec_status")
    if lane_status and lane_status != blocker:
        return f"{blocker}; {lane_status}"
    return str(blocker or "")


def _allocation_row(
    *,
    domain: str,
    causal_role: str,
    root_cause_link: str,
    work_share: str,
    evidence_refs: list[str],
    required_work: str,
) -> dict[str, Any]:
    return {
        "domain": domain,
        "causal_role": causal_role,
        "root_cause_link": root_cause_link,
        "work_share": work_share,
        "evidence_refs": evidence_refs,
        "required_work": required_work,
    }


def _validated_plan_items(finding: dict[str, Any]) -> list[str]:
    plan = finding.get("implementation_plan")
    if not isinstance(plan, list):
        return [
            "Trace the failed evidence to the owning runtime contract before changing downstream presentation.",
            "Patch the producer, parser, or validator where invalid state first becomes representable.",
            "Add a contract-level regression fixture so symptom-only downstream repair cannot pass.",
        ]
    items = [str(item).strip() for item in plan if str(item).strip()]
    if 3 <= len(items) <= 5:
        return items
    return [
        "Trace the failed evidence to the owning runtime contract before changing downstream presentation.",
        "Patch the producer, parser, or validator where invalid state first becomes representable.",
        "Add a contract-level regression fixture so symptom-only downstream repair cannot pass.",
    ]


def _validated_causal_allocation(finding: dict[str, Any]) -> dict[str, Any] | None:
    allocation = finding.get("causal_allocation")
    if not isinstance(allocation, dict):
        return None
    rows = allocation.get("allocation")
    if not isinstance(rows, list) or not rows:
        return None
    valid_rows: list[dict[str, Any]] = []
    required = {"domain", "causal_role", "root_cause_link", "work_share", "evidence_refs", "required_work"}
    for row in rows:
        if not isinstance(row, dict) or not required.issubset(row):
            return None
        domain = str(row.get("domain") or "").strip()
        root_cause_link = str(row.get("root_cause_link") or "").strip()
        if not domain or not root_cause_link or root_cause_link == domain or len(root_cause_link) < 20:
            return None
        evidence_refs = row.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            return None
        valid_rows.append(row)
    dominant = str(allocation.get("dominant_cause") or "").strip()
    retry = str(allocation.get("retry_recoverability") or "").strip()
    retry_reason = str(allocation.get("retry_recoverability_reason") or "").strip()
    if not dominant or not retry or not retry_reason:
        return None
    return {
        "dominant_cause": dominant,
        "retry_recoverability": retry,
        "retry_recoverability_reason": retry_reason,
        "allocation": valid_rows,
    }


def _recommended_action(section: dict[str, Any]) -> str:
    classification = str(section.get("failure_classification") or "").lower()
    section_id = str(section.get("section") or "")
    if "output contract" in classification:
        return "Implement the output-contract plan; do not rerun until schema and claim-ledger contract tests pass."
    if "specificity" in classification:
        return "Implement the evidence-bound specificity plan; do not rely on text-only regeneration."
    if "headline executive positioning contract" in classification:
        return "Implement the headline display-policy normalization fix before rerunning headline/final assembly."
    if "x1d decisive judge failure" in classification:
        return "Implement the claim-ledger source-binding fix before rerunning the judge-blocked section."
    if "evidence mapping" in classification:
        return "Implement the evidence-mapping plan; do not accept visible claims without lineage."
    if "provider capability" in classification:
        return "Implement the provider-capability payload fix before rerunning Anthropic-backed lanes."
    if "provider quorum" in classification:
        return "Implement the final aggregation provider-quorum fix before rerunning final assembly."
    if "upstream certification" in classification:
        return "Repair the non-certified upstream section before rerunning final aggregation; do not authorize review-only section evidence."
    if "pre-run" in classification:
        return "Implement the dependency-token plan before scheduling the dependent lane."
    if section_id == FINAL_AGGREGATION_LANE:
        return "Implement the aggregation-eligibility plan before final assembly."
    return "Inspect failed gates and rerun after targeted remediation."

