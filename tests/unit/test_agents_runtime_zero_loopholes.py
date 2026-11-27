"""Unmocked Wave 2 regression tests proving closure of LH-01, LH-02, LH-03, and LH-12 runtime loopholes."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from agents.context.precedent_bridge import RuntimePrecedentBridge
from agents.context.provenance import ContextItem, ContextSnapshot, ContextSourceType
from agents.e2e_artifacts import resolve_and_verify_outreach_artifact
from agents.gateway.contracts import CapabilityRequest, ModelTier
from agents.gateway.model_gateway import (
    GatewayUnregisteredCapabilityError,
    ModelCapabilityGateway,
)
from agents.orchestration.services.executive_summary_repair import (
    DEFAULT_VOICE_RULES,
    ExecutiveSummaryRepairService,
)
from agents.orchestration.services.swarm_challenger import (
    CriticAgent,
    ProponentAgent,
    SwarmChallenger,
    SwarmDisposition,
)
from tools.audit_mock_reachability import audit_production_file

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_model_capability_gateway_fails_closed_when_unregistered() -> None:
    """LH-01: ModelCapabilityGateway.execute() raises GatewayUnregisteredCapabilityError instead of simulated-v1."""
    gateway = ModelCapabilityGateway()
    snapshot = ContextSnapshot(
        snapshot_id="snap-w2-unreg",
        items=(ContextItem(source_id="s1", source_type=ContextSourceType.REQUEST, content="Draft brief"),),
        max_token_budget=500,
    )
    req = CapabilityRequest(
        capability_name="unregistered_capability",
        prompt_snapshot=snapshot,
        model_tier=ModelTier.REASONING,
    )
    with pytest.raises(GatewayUnregisteredCapabilityError, match="UNREGISTERED_CAPABILITY_ADAPTER"):
        gateway.execute(req)
    assert not hasattr(gateway, "_default_adapter")


def test_swarm_challenger_has_no_regex_prose_mutator_and_catches_expanded_metrics() -> None:
    """LH-02: ProponentAgent never regex-splices prose, and CriticAgent catches 9%, $45M, and 4x claims."""
    proponent = ProponentAgent()
    draft = "I am leading a $45M platform delivering 9% savings and 4x throughput."
    assert proponent.draft(draft, ("remove first person", "remove ungrounded metric")) == draft

    critic = CriticAgent()
    canonical = ("Led regulated cloud modernization delivering 22% infrastructure savings.",)
    critique = critic.evaluate(
        text="Delivered 9% latency reduction, $45M enterprise revenue impact, and 4x deployment speed.",
        turn=1,
        canonical_assertions=canonical,
    )
    assert critique.is_passing is False
    unverified_joined = " | ".join(critique.unverified_claims)
    assert "9%" in unverified_joined
    assert "$45M" in unverified_joined
    assert "4x" in unverified_joined

    # Grounded metric present in canonical assertions must NOT be flagged
    grounded_critique = critic.evaluate(
        text="Delivered 22% infrastructure savings across regulated cloud workloads.",
        turn=1,
        canonical_assertions=canonical,
    )
    assert grounded_critique.unverified_claims == ()
    assert grounded_critique.is_passing is True

    # Default repair rules contain only whitespace normalization (zero prose mutators)
    rule_names = {r.name for r in DEFAULT_VOICE_RULES}
    assert rule_names == {"trailing_whitespace_normalization", "redundant_horizontal_space_normalization"}
    svc = ExecutiveSummaryRepairService()
    res = svc.repair("I am an executive leader   \n", enable_challenger=True)
    assert res.is_successful is False
    assert res.swarm_receipt is not None
    assert res.swarm_receipt.final_disposition == SwarmDisposition.ESCALATED


def test_outreach_artifact_verifier_never_bypasses_for_callable_with_mock_attrs(tmp_path: Path) -> None:
    """LH-03: Missing outreach campaign fails closed even in --demo mode when callable carries mock_calls."""
    class _CallableWithMockAttr:
        mock_calls: list[object] = []

        def __call__(self) -> int:
            return 0

    empty_outreach = tmp_path / "outreach"
    empty_outreach.mkdir(parents=True)
    args = argparse.Namespace(demo=True, json=True)
    summary: dict[str, dict[str, object]] = {"stages": {}}

    with pytest.raises(RuntimeError, match="not generated or is empty"):
        resolve_and_verify_outreach_artifact(
            outreach_artifact_dir=empty_outreach,
            oe_code=0,
            outreach_main_callable=_CallableWithMockAttr(),
            summary_payload=summary,
            args=args,
        )
    assert summary["stages"]["executive_outreach"]["status"] == "FAILED"


def test_precedent_bridge_degraded_fallback_enforces_confidence_floor_and_multi_option_guard() -> None:
    """LH-12: Degraded precedent fallback without SQLite store surfaces HITL below 0.65 or with < 2 options."""
    bridge = RuntimePrecedentBridge.__new__(RuntimePrecedentBridge)
    bridge._store = None

    single_low = bridge.evaluate_runtime_ambiguity([{"label": "Single", "confidence": 0.30}])
    assert single_low["should_surface"] is True
    assert single_low["action"] == "SURFACE_HITL_ATOMIC"

    two_low_wide_margin = bridge.evaluate_runtime_ambiguity(
        [{"label": "Low A", "confidence": 0.40}, {"label": "Low B", "confidence": 0.15}]
    )
    assert two_low_wide_margin["margin"] == 0.25
    assert two_low_wide_margin["should_surface"] is True
    assert two_low_wide_margin["action"] == "SURFACE_HITL_ATOMIC"

    single_high = bridge.evaluate_runtime_ambiguity([{"label": "Only High", "confidence": 0.90}])
    assert single_high["should_surface"] is True
    assert single_high["action"] == "SURFACE_HITL_ATOMIC"

    two_high_wide = bridge.evaluate_runtime_ambiguity(
        [{"label": "Strong A", "confidence": 0.91}, {"label": "Weak B", "confidence": 0.45}]
    )
    assert two_high_wide["should_surface"] is False
    assert two_high_wide["action"] == "PROCEED_AUTONOMOUSLY"


def test_audit_mock_reachability_blocks_simulated_adapters_and_hasattr_mock_calls(tmp_path: Path) -> None:
    """Wave 2 scanner proof: tools/audit_mock_reachability.py rejects simulated-v1 and hasattr(..., 'mock_calls')."""
    bad_file = tmp_path / "agents" / "bad_gateway.py"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        'def execute(fn):\n'
        '    if hasattr(fn, "mock_calls"):\n'
        '        return "simulated-v1"\n'
        '    return dict(provider="simulated_default")\n',
        encoding="utf-8",
    )
    violations = audit_production_file(bad_file, tmp_path)
    joined = "\n".join(violations)
    assert "MR011" in joined
    assert "MR007" in joined
    assert "MR006" in joined
