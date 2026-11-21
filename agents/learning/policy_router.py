"""Risk-tiered post-runtime auto-application policy router enforcing all 7 fail-closed safety gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.schemas import (
    AutonomyTier,
    HoldoutReplayVerdict,
    ImprovementProposal,
)


@dataclass(frozen=True)
class PolicyRoutingDecision:
    proposal_id: str
    effective_tier: AutonomyTier
    auto_apply_permitted: bool
    requires_hitl: bool
    requires_pr: bool
    blocking_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_auto_apply_policy(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root).resolve() / "config" / "governance" / "auto_apply_policy.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Missing required auto_apply_policy.yaml at {path}")
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def evaluate_auto_apply_policy(
    *,
    proposal: ImprovementProposal,
    holdout_verdict: HoldoutReplayVerdict | None,
    repo_root: Path,
    ledger_store: SqliteLearningLedgerStore | None = None,
    confidence_margin: float = 0.30,
    now_utc: datetime | None = None,
) -> PolicyRoutingDecision:
    """Evaluate all 7 mandatory safety gates and classify proposal into Tier A / B / C."""
    policy = load_auto_apply_policy(repo_root)
    tier_c = policy.get("tier_c_pr_only") or {}
    tier_b = policy.get("tier_b_hitl_gated") or {}
    tier_a = policy.get("tier_a_auto_apply") or {}
    limits = policy.get("step_and_budget_limits") or {}
    cool = policy.get("cooldown_and_hysteresis") or {}

    norm_path = str(proposal.target_path or "").replace("\\", "/")
    forbidden_exts = tuple(tier_c.get("forbidden_auto_apply_extensions") or (".py",))
    forbidden_prefixes = tuple(tier_c.get("forbidden_auto_apply_prefixes") or ())
    tier_c_classes = set(tier_c.get("artifact_classes") or ())

    # Unconditional Tier C (PR-only) enforcement: Python code, governance, schemas, model profiles, rubrics.
    if (
        proposal.artifact_class in tier_c_classes
        or any(norm_path.endswith(ext) for ext in forbidden_exts)
        or any(norm_path.startswith(pref) for pref in forbidden_prefixes)
        or proposal.risk_lane == "LANE_2"
    ):
        return PolicyRoutingDecision(
            proposal_id=proposal.proposal_id,
            effective_tier="TIER_C_PR_ONLY",
            auto_apply_permitted=False,
            requires_hitl=False,
            requires_pr=True,
            blocking_reasons=[f"TIER_C_PR_ONLY_SURFACE:{norm_path}"],
        )

    # Tier B (HITL-gated) surfaces: prompts, priors, baselines.
    tier_b_classes = set(tier_b.get("artifact_classes") or ())
    tier_b_prefixes = tuple(tier_b.get("target_path_prefixes") or ())
    if (
        proposal.artifact_class in tier_b_classes
        or any(norm_path.startswith(pref) for pref in tier_b_prefixes)
    ):
        return PolicyRoutingDecision(
            proposal_id=proposal.proposal_id,
            effective_tier="TIER_B_HITL_GATED",
            auto_apply_permitted=False,
            requires_hitl=True,
            requires_pr=False,
            blocking_reasons=[f"TIER_B_REQUIRES_HITL:{proposal.artifact_class}"],
        )

    # Check Tier A allowlist membership.
    allowed_classes = set(tier_a.get("allowed_artifact_classes") or ())
    allowed_paths = set(tier_a.get("allowed_target_paths") or ())
    reasons: list[str] = []

    if proposal.artifact_class not in allowed_classes:
        reasons.append(f"ARTIFACT_CLASS_NOT_TIER_A:{proposal.artifact_class}")
    if norm_path not in allowed_paths:
        reasons.append(f"TARGET_PATH_NOT_ALLOWLISTED:{norm_path}")

    # Gate 2 & 3: HoldoutReplayVerdict must be PASS and bound to proposal digest.
    if holdout_verdict is None:
        reasons.append("MISSING_HOLDOUT_REPLAY_VERDICT")
    else:
        if holdout_verdict.proposal_id != proposal.proposal_id or holdout_verdict.proposal_digest != proposal.canonical_digest:
            reasons.append("HOLDOUT_VERDICT_PROPOSAL_DIGEST_MISMATCH")
        if holdout_verdict.verdict != "PASS":
            reasons.append(f"HOLDOUT_VERDICT_NOT_PASS:{holdout_verdict.verdict}")
        if not holdout_verdict.zero_mutation_verified:
            reasons.append("SHADOW_ZERO_MUTATION_NOT_VERIFIED")
        if not holdout_verdict.unlabeled_view_enforced:
            reasons.append("UNLABELED_VIEW_NOT_ENFORCED")
        if not holdout_verdict.pinned_regressions_passed:
            reasons.append("PINNED_REGRESSIONS_FAILED")
        if holdout_verdict.veto_regressions_count > 0:
            reasons.append("VETO_REGRESSION_PRESENT")

    # Gate 4: Step delta and numeric SSOT min/max bounds.
    max_step = float(limits.get("max_step_delta", 0.15))
    if proposal.step_delta_magnitude > max_step + 1e-9:
        reasons.append(f"STEP_DELTA_EXCEEDS_MAX:{proposal.step_delta_magnitude}>{max_step}")

    if proposal.artifact_class in {"bounded_threshold", "routing_weight"}:
        param_ref = f"{norm_path}::{proposal.target_key or ''}"
        bounds = (tier_a.get("bounded_numeric_parameters") or {}).get(param_ref)
        if bounds is None:
            reasons.append(f"PARAMETER_NOT_IN_SSOT_BOUNDS:{param_ref}")
        else:
            try:
                val = float(proposal.proposed_value_or_patch)
                if val < float(bounds["min"]) or val > float(bounds["max"]):
                    reasons.append(f"PROPOSED_VALUE_OUT_OF_BOUNDS:{val}")
            except (TypeError, ValueError):
                reasons.append("PROPOSED_VALUE_NOT_NUMERIC")

    # Gate 6: Cooldown & post-rollback anti-oscillation lock.
    min_margin = float(cool.get("hysteresis_min_confidence_margin", 0.20))
    if confidence_margin <= min_margin:
        reasons.append(f"AMBIGUITY_MARGIN_TOO_LOW:{confidence_margin:.2f}<={min_margin:.2f}")

    if ledger_store is not None:
        key_str = str(proposal.target_key or "")
        active_lock = ledger_store.get_active_rollback_lock(
            target_path=norm_path,
            target_key=key_str,
            now_utc=now_utc,
        )
        if active_lock is not None:
            return PolicyRoutingDecision(
                proposal_id=proposal.proposal_id,
                effective_tier="TIER_B_HITL_GATED",
                auto_apply_permitted=False,
                requires_hitl=True,
                requires_pr=False,
                blocking_reasons=[f"POST_ROLLBACK_LOCK_ACTIVE_UNTIL:{active_lock['locked_until_utc']}"],
            )
        per_key_hours = int(cool.get("per_key_cooldown_hours", 24))
        if ledger_store.count_recent_auto_applies(
            window_hours=per_key_hours,
            target_path=norm_path,
            target_key=key_str,
            now_utc=now_utc,
        ) >= 1:
            reasons.append("PER_KEY_COOLDOWN_ACTIVE")
        global_cap = int(cool.get("global_max_auto_applies_per_24h", 3))
        if ledger_store.count_recent_auto_applies(window_hours=24, now_utc=now_utc) >= global_cap:
            reasons.append("GLOBAL_24H_AUTO_APPLY_CAP_REACHED")

    if reasons:
        # Escalate to HITL if target/class is not Tier C but failed a Tier A gate.
        return PolicyRoutingDecision(
            proposal_id=proposal.proposal_id,
            effective_tier="TIER_B_HITL_GATED",
            auto_apply_permitted=False,
            requires_hitl=True,
            requires_pr=False,
            blocking_reasons=reasons,
        )

    return PolicyRoutingDecision(
        proposal_id=proposal.proposal_id,
        effective_tier="TIER_A_AUTO_APPLY",
        auto_apply_permitted=True,
        requires_hitl=False,
        requires_pr=False,
        blocking_reasons=[],
    )
