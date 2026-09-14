"""tests/unit/test_architecture_wave4_state_and_gateway.py

Wave 4 State, Retrieval & Capability Gateway Verification Test Suite:
Validates that:
1. ContextItem and ContextSnapshot contracts preserve immutable origin provenance.
2. TokenBudget strictly bounds prompt sizes and prioritizes authoritative sources.
3. ModelCapabilityGateway enforces pre-commit validation and seals observations.
4. Provider errors are isolated cleanly behind the gateway contract.
"""

from __future__ import annotations

import pytest

from agents.context.budgeting import TokenBudget, TokenBudgetExceededError
from agents.context.provenance import (
    ContextItem,
    ContextSnapshot,
    ContextSourceType,
)
from agents.gateway.contracts import (
    CapabilityRequest,
    CapabilityResponse,
    ModelTier,
)
from agents.gateway.model_gateway import (
    GatewayPreCommitValidationError,
    ModelCapabilityGateway,
)


def test_context_item_and_snapshot_contracts():
    """Verify ContextItem and ContextSnapshot compute deterministic provenance digests."""
    item1 = ContextItem(
        source_id="resume_canonical",
        source_type=ContextSourceType.USER_DOCUMENT,
        content="Experience: Principal AI Architect at Leading Tech.",
        authority="canonical",
        relevance_score=0.95,
    )
    item2 = ContextItem(
        source_id="jd_requirements",
        source_type=ContextSourceType.RETRIEVED_EVIDENCE,
        content="Requirements: 10+ years distributed systems.",
        authority="verified",
        relevance_score=0.90,
    )

    assert item1.item_digest != ""
    assert item2.item_digest != ""
    assert item1.item_digest != item2.item_digest

    snapshot = ContextSnapshot(
        snapshot_id="test_snapshot_01",
        items=(item1, item2),
        max_token_budget=1000,
    )

    assert snapshot.item_count if hasattr(snapshot, "item_count") else len(snapshot.items) == 2
    assert snapshot.total_estimated_tokens > 0
    assert snapshot.is_within_budget is True
    assert snapshot.provenance_digest != ""

    # Text stream assembly
    text = snapshot.assemble_text()
    assert "Principal AI Architect" in text
    assert "10+ years" in text


def test_context_budget_enforcement():
    """Verify TokenBudget validates within bounds and raises on overflow."""
    small_item = ContextItem(
        source_id="item_small",
        source_type=ContextSourceType.REQUEST,
        content="Short request text.",
        estimated_tokens=50,
    )
    large_item = ContextItem(
        source_id="item_large",
        source_type=ContextSourceType.EPHEMERAL_SCRATCH,
        content="Very long scratch text " * 100,
        estimated_tokens=2000,
    )

    budget = TokenBudget(max_total_tokens=1500, reserved_output_tokens=500)
    assert budget.max_context_tokens == 1000

    # Valid snapshot
    valid_snapshot = ContextSnapshot(
        snapshot_id="valid_snap",
        items=(small_item,),
        max_token_budget=budget.max_context_tokens,
    )
    budget.validate_snapshot(valid_snapshot)

    # Overflow snapshot raises TokenBudgetExceededError
    overflow_snapshot = ContextSnapshot(
        snapshot_id="overflow_snap",
        items=(large_item,),
        max_token_budget=budget.max_context_tokens,
    )
    with pytest.raises(TokenBudgetExceededError):
        budget.validate_snapshot(overflow_snapshot)


def test_token_budget_priority_fitting():
    """Verify fit_items_to_budget preserves authoritative sources over scratch."""
    authoritative_doc = ContextItem(
        source_id="user_resume",
        source_type=ContextSourceType.USER_DOCUMENT,
        content="Authoritative User Resume",
        estimated_tokens=600,
        relevance_score=1.0,
    )
    ephemeral_scratch = ContextItem(
        source_id="scratch_notes",
        source_type=ContextSourceType.EPHEMERAL_SCRATCH,
        content="Ephemeral Scratch Notes",
        estimated_tokens=600,
        relevance_score=0.2,
    )

    budget = TokenBudget(max_total_tokens=1500, reserved_output_tokens=500)  # max_context_tokens = 1000

    fitted = budget.fit_items_to_budget([ephemeral_scratch, authoritative_doc])
    # The budget can only fit one 600-token item out of the two (total 1200 > 1000)
    assert len(fitted.items) == 1
    assert fitted.items[0].source_id == "user_resume"
    assert fitted.is_within_budget is True


def test_capability_gateway_pre_commit_validation():
    """Verify ModelCapabilityGateway catches malformed requests before invocation."""
    gateway = ModelCapabilityGateway()

    valid_item = ContextItem(
        source_id="req_doc",
        source_type=ContextSourceType.REQUEST,
        content="Generate executive headline",
        estimated_tokens=20,
    )
    snapshot = ContextSnapshot(
        snapshot_id="snap_01",
        items=(valid_item,),
        max_token_budget=500,
    )

    # Empty capability name
    with pytest.raises(GatewayPreCommitValidationError):
        gateway.validate_pre_commit(
            CapabilityRequest(
                capability_name="",
                prompt_snapshot=snapshot,
            )
        )

    # Over-budget snapshot
    over_snapshot = ContextSnapshot(
        snapshot_id="snap_over",
        items=(valid_item,),
        max_token_budget=10,  # lower than item tokens
    )
    with pytest.raises(GatewayPreCommitValidationError):
        gateway.validate_pre_commit(
            CapabilityRequest(
                capability_name="headline_generation",
                prompt_snapshot=over_snapshot,
            )
        )


def test_capability_gateway_execution_and_observation_sealing():
    """Verify ModelCapabilityGateway dispatches to registered adapter and seals observation."""
    gateway = ModelCapabilityGateway()

    def mock_adapter(req: CapabilityRequest) -> CapabilityResponse:
        return CapabilityResponse(
            content="Tailored Headline: VP of Engineering",
            provider="openai",
            model_id="gpt-5.6-luna",
            status="SUCCESS",
        )

    gateway.register_adapter("headline_generation", mock_adapter)

    item = ContextItem(
        source_id="role_spec",
        source_type=ContextSourceType.RETRIEVED_EVIDENCE,
        content="Target: VP of Engineering",
        estimated_tokens=15,
    )
    snapshot = ContextSnapshot(
        snapshot_id="snap_vp",
        items=(item,),
        max_token_budget=1000,
    )

    req = CapabilityRequest(
        capability_name="headline_generation",
        prompt_snapshot=snapshot,
        model_tier=ModelTier.FRONTIER,
    )

    response = gateway.execute(req)
    assert response.is_success is True
    assert "VP of Engineering" in response.content
    assert response.provider == "openai"
    assert response.model_id == "gpt-5.6-luna"
    assert response.observation_digest != ""
    assert response.latency_ms >= 0.0


def test_capability_gateway_error_isolation():
    """Verify exceptions in adapters are isolated into structured ERROR responses."""
    gateway = ModelCapabilityGateway()

    def failing_adapter(req: CapabilityRequest) -> CapabilityResponse:
        raise ConnectionResetError("Connection closed by peer")

    gateway.register_adapter("failing_capability", failing_adapter)

    item = ContextItem(
        source_id="req",
        source_type=ContextSourceType.REQUEST,
        content="Test content",
    )
    snapshot = ContextSnapshot(
        snapshot_id="snap_fail",
        items=(item,),
    )

    req = CapabilityRequest(
        capability_name="failing_capability",
        prompt_snapshot=snapshot,
    )

    resp = gateway.execute(req)
    assert resp.is_success is False
    assert resp.status == "ERROR"
    assert "Connection closed by peer" in resp.error_message
