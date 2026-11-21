"""Candidate ImprovementProposal synthesizer with log-damped bounded step sizing and signed provenance."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from apps_eval.contracts.digests import canonical_sha256, stable_id
from apps_eval.contracts.schemas import (
    ArtifactClass,
    AutonomyTier,
    FailureCluster,
    ImprovementProposal,
    RiskLaneName,
)


def _load_auto_apply_policy(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root).resolve() / "config" / "governance" / "auto_apply_policy.yaml"
    if not path.is_file():
        return {}
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def _log_damped_delta(raw_delta: float, sample_count: int, max_step: float) -> float:
    n = max(1, int(sample_count))
    damping = (1.0 + math.log(n)) / (1.0 + 0.5 * math.log(n))
    damped = raw_delta * min(1.0, damping / 2.0)
    if damped > max_step:
        return round(max_step, 4)
    if damped < -max_step:
        return round(-max_step, 4)
    return round(damped, 4)


def build_signed_provenance(
    *,
    proposal_id: str,
    evidence_trace_ids: Sequence[str],
    source_receipt_digests: Sequence[str],
    proposed_change: Any,
    evaluation_plan: Sequence[str],
) -> str:
    """Compute canonical SHA-256 provenance digest binding proposal, evidence, and replay plan."""
    payload = {
        "proposal_id": proposal_id,
        "evidence_trace_ids": sorted(set(str(x) for x in evidence_trace_ids)),
        "source_receipt_digests": sorted(set(str(x) for x in source_receipt_digests)),
        "proposed_change_hash": canonical_sha256(proposed_change),
        "evaluation_plan": list(evaluation_plan),
    }
    return canonical_sha256(payload)


def synthesize_proposals_from_clusters(
    clusters: Sequence[FailureCluster],
    *,
    repo_root: Path,
    current_config_values: Mapping[str, float] | None = None,
    source_receipt_digests: Sequence[str] = (),
    ttl_hours: int = 72,
) -> list[ImprovementProposal]:
    """Synthesize bounded ImprovementProposals from eligible FailureClusters."""
    policy = _load_auto_apply_policy(repo_root)
    limits = policy.get("step_and_budget_limits") or {}
    max_step = float(limits.get("max_step_delta", 0.15))
    bounds_map = (policy.get("tier_a_auto_apply") or {}).get("bounded_numeric_parameters") or {}
    current_vals = dict(current_config_values or {})
    expires_iso = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat().replace("+00:00", "Z")

    proposals: list[ImprovementProposal] = []
    for cl in clusters:
        if not cl.eligible_for_proposal_synthesis or cl.conflict_detected:
            continue
        evidence_ids = list(cl.unique_run_ids) or [cl.cluster_id]

        if cl.recommended_track == "TRACK_1_CALIBRATION":
            target_path = "config/routing_calibration.yaml"
            target_key = "v12_routing.classifier_surface_threshold"
            param_ref = f"{target_path}::{target_key}"
            bounds = bounds_map.get(param_ref) or {"min": 0.55, "max": 0.90}
            curr = float(current_vals.get(param_ref, 0.72))
            delta = _log_damped_delta(0.04, len(evidence_ids), max_step)
            proposed_val = round(min(float(bounds["max"]), max(float(bounds["min"]), curr + delta)), 4)
            step_mag = round(abs(proposed_val - curr), 4)
            artifact_class: ArtifactClass = "bounded_threshold"
            autonomy_tier: AutonomyTier = "TIER_A_AUTO_APPLY"
            risk_lane: RiskLaneName = "LANE_1"
            eval_plan = ["target_cluster_replay", "locked_holdout_replay", "pinned_regression_shield"]
            proposal_id = stable_id("prop", cl.cluster_id, target_path, target_key, proposed_val, length=16)
            prov = build_signed_provenance(
                proposal_id=proposal_id,
                evidence_trace_ids=evidence_ids,
                source_receipt_digests=source_receipt_digests,
                proposed_change={"key": target_key, "value": proposed_val},
                evaluation_plan=eval_plan,
            )
            proposals.append(
                ImprovementProposal(
                    proposal_id=proposal_id,
                    cluster_id=cl.cluster_id,
                    artifact_class=artifact_class,
                    autonomy_tier=autonomy_tier,
                    risk_lane=risk_lane,
                    target_path=target_path,
                    target_key=target_key,
                    expected_current_value=curr,
                    proposed_value_or_patch=proposed_val,
                    step_delta_magnitude=step_mag,
                    evidence_trace_ids=evidence_ids,
                    source_receipt_digests=list(source_receipt_digests),
                    provenance_digest=prov,
                    evaluation_plan=eval_plan,
                    status="PROPOSED",
                    expires_at_utc=expires_iso,
                )
            )
        else:
            # Structural code / validator defects route strictly to TIER_C_PR_ONLY (never auto-applied).
            target_path = f"{cl.owner_subsystem}/"
            eval_plan = ["isolated_worktree_fix", "diff_scoped_eval_shield", "pr_governance_readiness"]
            patch_spec = {
                "action": "open_pr_for_root_cause_fix",
                "owner_subsystem": cl.owner_subsystem,
                "root_cause_bucket": cl.root_cause_bucket,
                "member_finding_ids": cl.member_finding_ids,
            }
            proposal_id = stable_id("prop", cl.cluster_id, target_path, cl.root_cause_bucket, length=16)
            prov = build_signed_provenance(
                proposal_id=proposal_id,
                evidence_trace_ids=evidence_ids,
                source_receipt_digests=source_receipt_digests,
                proposed_change=patch_spec,
                evaluation_plan=eval_plan,
            )
            proposals.append(
                ImprovementProposal(
                    proposal_id=proposal_id,
                    cluster_id=cl.cluster_id,
                    artifact_class="validator_or_code",
                    autonomy_tier="TIER_C_PR_ONLY",
                    risk_lane="LANE_2",
                    target_path=target_path,
                    target_key=None,
                    expected_current_value=None,
                    proposed_value_or_patch=patch_spec,
                    step_delta_magnitude=0.0,
                    evidence_trace_ids=evidence_ids,
                    source_receipt_digests=list(source_receipt_digests),
                    provenance_digest=prov,
                    evaluation_plan=eval_plan,
                    status="PROPOSED",
                    expires_at_utc=expires_iso,
                )
            )
    return proposals
