"""Stage receipt filenames for apps_rg whole-run spine (R3R4 + draft leg)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

STAGE_RECEIPT_SCHEMA_VERSION = "apps_rg.stage_receipt.v1"

FILENAME_INGRESS_RAW = "ingress_raw.json"
FILENAME_U0_RECEIPT = "u0_receipt.json"
FILENAME_L1_PLAN = "l1_plan_contract.json"
FILENAME_L1_PLANNING_CAPSULE = "l1_planning_capsule.json"
FILENAME_L1_PLANNING_V2_CAPSULE = "l1_planning_v2_capsule.json"
FILENAME_L1_COGNITIVE_PLAN = "l1_cognitive_plan.json"
FILENAME_L1_COGNITIVE_TREATMENT = "l1_cognitive_treatment.json"
FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT = "l1_cognitive_c0_outcome_receipt.json"
FILENAME_L1_COGNITIVE_REVISION = "l1_cognitive_revision.json"
FILENAME_L1_COGNITIVE_REVISION_ADVISORY = "l1_cognitive_revision_advisory.json"
FILENAME_L1_COGNITIVE_OUTPUT_PROJECTION = "l1_cognitive_output_projection.json"
FILENAME_L1_COGNITIVE_OUTPUT_DISPOSITION = "l1_cognitive_output_disposition.json"
FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION = "l1_cognitive_treatment_execution.json"
FILENAME_L1_REASONING_BASELINE = "l1_reasoning_baseline.json"
FILENAME_L1_EVIDENCE_OBLIGATION_RECEIPT = "l1_evidence_obligation_receipt.json"
FILENAME_L1_V2_COMPARISON = "l1_v2_comparison_receipt.json"
FILENAME_L1_V2_REVIEW_PACKET = "l1_v2_human_review_packet.json"
FILENAME_L1_V2_PROMOTION_READINESS = "l1_v2_promotion_readiness.json"
FILENAME_GOVERNED_L3_SCHEDULE_RECEIPT = "governed_l3_schedule_receipt.json"
FILENAME_PLAN_EXECUTION_RECEIPT = "plan_execution_receipt.json"
FILENAME_PLAN_REPLAN_DECISION = "plan_replan_decision.json"
FILENAME_PLAN_EXECUTION_FAILURE_DIAGNOSTIC = "plan_execution_failure_diagnostic.json"
FILENAME_FAILURE_AWARE_REPLAN_V2 = "failure_aware_replan_v2.json"
FILENAME_ROUTE_CONTRACT = "route_contract.json"
FILENAME_ROUTE_PRE_RESEARCH = "route_contract_pre_research.json"
FILENAME_RESEARCH_BRIDGE_REQUEST = "research_bridge_request.json"
FILENAME_RESEARCH_BRIDGE_RESPONSE = "research_bridge_response.json"
FILENAME_RESEARCH_EVIDENCE_CONTRACT = "research_final_evidence_contract.json"
FILENAME_DELEGATED_BRIEFING = "research/delegated_briefing.txt"
FILENAME_SPINE_MANIFEST = "spine_run_manifest.json"
FILENAME_MOCK_ELIMINATION_PROOF = "mock_elimination_proof.json"
FILENAME_DRAFT_LEG_MANIFEST = "r4_run_manifest.json"


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def sha256_digest(payload: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    )


def write_stage_receipt(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return str(path)


__all__ = [
    "FILENAME_DELEGATED_BRIEFING",
    "FILENAME_DRAFT_LEG_MANIFEST",
    "FILENAME_INGRESS_RAW",
    "FILENAME_L1_PLAN",
    "FILENAME_L1_PLANNING_CAPSULE",
    "FILENAME_L1_PLANNING_V2_CAPSULE",
    "FILENAME_L1_COGNITIVE_PLAN",
    "FILENAME_L1_COGNITIVE_TREATMENT",
    "FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT",
    "FILENAME_L1_COGNITIVE_REVISION",
    "FILENAME_L1_COGNITIVE_REVISION_ADVISORY",
    "FILENAME_L1_COGNITIVE_OUTPUT_PROJECTION",
    "FILENAME_L1_COGNITIVE_OUTPUT_DISPOSITION",
    "FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION",
    "FILENAME_L1_REASONING_BASELINE",
    "FILENAME_L1_EVIDENCE_OBLIGATION_RECEIPT",
    "FILENAME_L1_V2_COMPARISON",
    "FILENAME_L1_V2_REVIEW_PACKET",
    "FILENAME_L1_V2_PROMOTION_READINESS",
    "FILENAME_GOVERNED_L3_SCHEDULE_RECEIPT",
    "FILENAME_PLAN_EXECUTION_RECEIPT",
    "FILENAME_PLAN_EXECUTION_FAILURE_DIAGNOSTIC",
    "FILENAME_PLAN_REPLAN_DECISION",
    "FILENAME_FAILURE_AWARE_REPLAN_V2",
    "FILENAME_MOCK_ELIMINATION_PROOF",
    "FILENAME_RESEARCH_BRIDGE_REQUEST",
    "FILENAME_RESEARCH_BRIDGE_RESPONSE",
    "FILENAME_RESEARCH_EVIDENCE_CONTRACT",
    "FILENAME_ROUTE_CONTRACT",
    "FILENAME_ROUTE_PRE_RESEARCH",
    "FILENAME_SPINE_MANIFEST",
    "FILENAME_U0_RECEIPT",
    "STAGE_RECEIPT_SCHEMA_VERSION",
    "sha256_digest",
    "write_stage_receipt",
]
