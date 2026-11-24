"""Candidate ImprovementProposal synthesizer with log-damped bounded step sizing and signed provenance."""

from __future__ import annotations

import json
import math
import re
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


def synthesize_graduation_proposals(
    *,
    repo_root: Path,
    graduation_state_path: Path | None = None,
    ttl_hours: int = 72,
) -> list[ImprovementProposal]:
    """Synthesize Tier A regression_case_pin proposals for capability suites reaching 10 consecutive passes."""
    root = Path(repo_root).resolve()
    grad_path = (
        Path(graduation_state_path).resolve()
        if graduation_state_path is not None
        else (root / "artifacts" / "learning" / "capability_graduation_state.json")
    )
    if not grad_path.is_file():
        return []
    try:
        state = json.loads(grad_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(state, Mapping):
        return []

    ready_suites = [str(s) for s in (state.get("graduation_ready_suites") or []) if str(s).strip()]
    suites_map = state.get("suites") if isinstance(state.get("suites"), Mapping) else {}
    if not ready_suites:
        return []

    pin_path_rel = "apps_eval/suites/pinned_fix_regressions.json"
    pin_file = root / pin_path_rel
    existing_graduated: list[str] = []
    if pin_file.is_file():
        try:
            pin_doc = json.loads(pin_file.read_text(encoding="utf-8"))
            if isinstance(pin_doc, Mapping) and isinstance(pin_doc.get("graduated_capability_suites"), list):
                existing_graduated = [str(x) for x in pin_doc["graduated_capability_suites"]]
        except (OSError, json.JSONDecodeError):
            existing_graduated = []

    expires_iso = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat().replace("+00:00", "Z")
    proposals: list[ImprovementProposal] = []
    for suite_id in sorted(set(ready_suites)):
        suite_rec = suites_map.get(suite_id) if isinstance(suites_map.get(suite_id), Mapping) else {}
        if str(suite_rec.get("stage") or "capability") == "regression" or suite_id in existing_graduated:
            continue
        streak = int(suite_rec.get("consecutive_passes") or 10)
        proposed_suites = sorted(set(existing_graduated + [suite_id]))
        proposal_id = stable_id("prop_grad", suite_id, pin_path_rel, streak, length=16)
        eval_plan = ["locked_holdout_replay", "pinned_regression_shield", "lp5_canary"]
        prov = build_signed_provenance(
            proposal_id=proposal_id,
            evidence_trace_ids=[f"graduation:{suite_id}:streak={streak}"],
            source_receipt_digests=[],
            proposed_change={"key": "graduated_capability_suites", "value": proposed_suites},
            evaluation_plan=eval_plan,
        )
        proposals.append(
            ImprovementProposal(
                proposal_id=proposal_id,
                cluster_id=f"clst-grad-{suite_id}",
                artifact_class="regression_case_pin",
                autonomy_tier="TIER_A_AUTO_APPLY",
                risk_lane="LANE_1",
                target_path=pin_path_rel,
                target_key="graduated_capability_suites",
                expected_current_value=existing_graduated if existing_graduated else None,
                proposed_value_or_patch=proposed_suites,
                step_delta_magnitude=0.0,
                evidence_trace_ids=[f"graduation:{suite_id}:streak={streak}"],
                source_receipt_digests=[],
                provenance_digest=prov,
                evaluation_plan=eval_plan,
                status="PROPOSED",
                expires_at_utc=expires_iso,
            )
        )
    return proposals


_PROSE_SPLICE_FORBIDDEN_RE = re.compile(
    r"(?:\b(?:prepend|append|insert|splice)\s+(?:literal|exact|prefix|suffix|phrase)\b|"
    r"\balways\s+start\s+with\b|\balways\s+end\s+with\b)",
    re.IGNORECASE,
)

_TIER_A_PARAMETER_DEFAULTS: dict[str, tuple[float, float]] = {
    "config/routing_calibration.yaml::v12_routing.loop_guard_efficiency_threshold": (0.40, 0.04),
    "config/routing_calibration.yaml::semantic_cache.similarity_threshold": (0.98, -0.02),
    "config/routing_calibration.yaml::abstain.default_threshold": (0.50, 0.04),
    "config/routing_calibration.yaml::v12_routing.r_casc_escalation_threshold": (0.55, 0.04),
    "config/routing_calibration.yaml::v12_routing.r1b_semantic_match_threshold": (0.88, -0.02),
    "config/routing_calibration.yaml::v12_routing.classifier_surface_threshold": (0.72, 0.04),
}


def validate_no_prose_splicing(guidance_text: str) -> None:
    """Reject repair hints or prompt priors that attempt literal prose splicing (INV-NO-POST-LLM-PROSE-MUTATORS)."""
    if _PROSE_SPLICE_FORBIDDEN_RE.search(str(guidance_text or "")):
        raise ValueError(
            f"PROSE_SPLICING_HINT_REJECTED: Candidate prior violates INV-NO-POST-LLM-PROSE-MUTATORS: {guidance_text!r}"
        )


def resolve_calibration_route(cluster: FailureCluster) -> tuple[str, str, str]:
    """Map a TRACK_1_CALIBRATION FailureCluster to (mode, target_path, target_key).

    mode is 'TIER_A_BOUNDED' or 'TIER_B_PRIOR'.
    """
    sig = f"{cluster.root_cause_bucket} {cluster.owner_subsystem}".lower()
    if any(
        tok in sig
        for tok in (
            "hitl_override",
            "hitl_calibration",
            "prompt_prior",
            "correction_terminology",
            "correction_prompt",
            "correction_voice",
            "correction_style",
        )
    ):
        safe_bucket = re.sub(r"[^a-zA-Z0-9_]+", "_", cluster.root_cause_bucket).strip("_") or "general"
        return "TIER_B_PRIOR", "config/prompt_governance/priors.yaml", f"flywheel_priors.{safe_bucket}"
    if any(tok in sig for tok in ("latency_sla", "loop_guard", "loop_efficiency", "trajectory_loop")):
        return (
            "TIER_A_BOUNDED",
            "config/routing_calibration.yaml",
            "v12_routing.loop_guard_efficiency_threshold",
        )
    if any(tok in sig for tok in ("semantic_cache", "cache_similarity", "gptcache")):
        return (
            "TIER_A_BOUNDED",
            "config/routing_calibration.yaml",
            "semantic_cache.similarity_threshold",
        )
    if any(tok in sig for tok in ("r_casc", "cascade_escalation", "escalate_tier")):
        return (
            "TIER_A_BOUNDED",
            "config/routing_calibration.yaml",
            "v12_routing.r_casc_escalation_threshold",
        )
    if any(tok in sig for tok in ("abstain", "safe_abstain", "x3e")):
        return (
            "TIER_A_BOUNDED",
            "config/routing_calibration.yaml",
            "abstain.default_threshold",
        )
    if any(tok in sig for tok in ("r1b", "semantic_match", "post_gate_match")):
        return (
            "TIER_A_BOUNDED",
            "config/routing_calibration.yaml",
            "v12_routing.r1b_semantic_match_threshold",
        )
    return (
        "TIER_A_BOUNDED",
        "config/routing_calibration.yaml",
        "v12_routing.classifier_surface_threshold",
    )


def synthesize_proposals_from_clusters(
    clusters: Sequence[FailureCluster],
    *,
    repo_root: Path,
    current_config_values: Mapping[str, float] | None = None,
    source_receipt_digests: Sequence[str] = (),
    graduation_state_path: Path | None = None,
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
            route_mode, target_path, target_key = resolve_calibration_route(cl)
            if route_mode == "TIER_B_PRIOR":
                guidance = (
                    f"Diagnostic critique guidance for {cl.root_cause_bucket}: verify domain grounding "
                    f"and rubric alignment in {cl.owner_subsystem} before promotion."
                )
                validate_no_prose_splicing(guidance)
                eval_plan = ["locked_holdout_replay", "lp5_canary"]
                proposal_id = stable_id("prop", cl.cluster_id, target_path, target_key, length=16)
                prov = build_signed_provenance(
                    proposal_id=proposal_id,
                    evidence_trace_ids=evidence_ids,
                    source_receipt_digests=source_receipt_digests,
                    proposed_change={"key": target_key, "value": guidance},
                    evaluation_plan=eval_plan,
                )
                proposals.append(
                    ImprovementProposal(
                        proposal_id=proposal_id,
                        cluster_id=cl.cluster_id,
                        artifact_class="prompt_prior",
                        autonomy_tier="TIER_B_HITL_GATED",
                        risk_lane="LANE_1",
                        target_path=target_path,
                        target_key=target_key,
                        expected_current_value=None,
                        proposed_value_or_patch=guidance,
                        step_delta_magnitude=0.0,
                        evidence_trace_ids=evidence_ids,
                        source_receipt_digests=list(source_receipt_digests),
                        provenance_digest=prov,
                        evaluation_plan=eval_plan,
                        status="PROPOSED",
                        expires_at_utc=expires_iso,
                    )
                )
            else:
                param_ref = f"{target_path}::{target_key}"
                default_val, base_step = _TIER_A_PARAMETER_DEFAULTS.get(param_ref, (0.72, 0.04))
                bounds = bounds_map.get(param_ref) or {"min": 0.25, "max": 0.99}
                curr = float(current_vals.get(param_ref, default_val))
                delta = _log_damped_delta(base_step, len(evidence_ids), max_step)
                proposed_val = round(min(float(bounds["max"]), max(float(bounds["min"]), curr + delta)), 4)
                if math.isclose(proposed_val, curr, abs_tol=1e-6):
                    # Step in opposite direction if already at boundary ceiling/floor.
                    proposed_val = round(min(float(bounds["max"]), max(float(bounds["min"]), curr - delta)), 4)
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
    proposals.extend(
        synthesize_graduation_proposals(
            repo_root=repo_root,
            graduation_state_path=graduation_state_path,
            ttl_hours=ttl_hours,
        )
    )
    return proposals
