"""Unit tests for Wave 4 Antigravity SDK Budgets, Retries, Compaction, Session Persistence & Observability."""

from __future__ import annotations

import json
import logging
from pathlib import Path


def test_budget_config_and_stop_reason_projections() -> None:
    """Verify BudgetConfig and StopReason projections across all 4 token governors."""
    from agents.context.budgeting import TokenBudget as ContextTokenBudget
    from apps_model_telemetry.token_budget_governor import (
        TokenBudgetPolicy,
        inspect_antigravity_stop_reason,
    )
    from apps_rg.runtime.model_token_governor import apps_rg_antigravity_budget_config
    from infrastructure.live_governor import (
        BudgetScope,
        LiveTokenGovernor,
        StopReason,
        TokenBudget as LiveTokenBudget,
    )

    live_budget = LiveTokenBudget(
        max_prompt_tokens=16000,
        max_completion_tokens=4096,
        max_total_tokens=20000,
        max_run_tokens=80000,
    )
    cfg_lifetime = live_budget.to_antigravity_budget_config(scope=BudgetScope.LIFETIME)
    assert cfg_lifetime.max_input_tokens == 16000
    assert cfg_lifetime.max_output_tokens == 4096
    assert cfg_lifetime.max_total_tokens == 80000
    assert cfg_lifetime.scope == BudgetScope.LIFETIME

    ctx_budget = ContextTokenBudget(max_total_tokens=4000, reserved_output_tokens=1000)
    cfg_forward = ctx_budget.to_antigravity_budget_config(scope="forward_looking")
    assert cfg_forward.max_input_tokens == 3000
    assert cfg_forward.max_output_tokens == 1000
    assert cfg_forward.scope == BudgetScope.FORWARD_LOOKING
    assert ctx_budget.to_compaction_config(ratio=0.8)["token_threshold"] == 2400

    pol = TokenBudgetPolicy(
        chars_per_token_estimate=4,
        safety_multiplier=1.1,
        max_input_tokens_per_attempt=48000,
        max_reserved_tokens_per_run=300000,
    )
    pol_cfg = pol.to_antigravity_budget_config(max_output_tokens=8192)
    assert pol_cfg.max_input_tokens == 48000
    assert pol_cfg.max_total_tokens == 300000

    rg_cfg = apps_rg_antigravity_budget_config(max_output_tokens=4096)
    assert getattr(rg_cfg, "max_output_tokens", 0) == 4096

    assert LiveTokenGovernor.inspect_stop_reason({"stop_reason": "MAX_TOTAL_TOKENS"}) == StopReason.MAX_TOTAL_TOKENS
    assert inspect_antigravity_stop_reason({"stop_reason": "MAX_MODEL_CALLS"}) == "MAX_MODEL_CALLS"


def test_retry_compaction_persistence_and_runtime_boundary() -> None:
    """Verify RetryConfig.benchmark(), CompactionConfig, session persistence, and runtime-boundary.json."""
    from infrastructure.utils.distributed_state_manager import DistributedStateManager
    from tools.agent_runtime_auditor import (
        AntigravityConnectionError,
        AntigravityValidationError,
        CompactionConfig,
        OnToolErrorHook,
        RetryConfig,
        run_agent_runtime_audit,
    )

    bench = RetryConfig.benchmark()
    assert bench.api_retry >= 3
    assert bench.model_output_retry >= 2
    assert CompactionConfig(token_threshold=1500).token_threshold == 1500

    hook = OnToolErrorHook(handler=lambda exc: {"recovered": isinstance(exc, (AntigravityValidationError, AntigravityConnectionError))})
    assert hook.handler(AntigravityValidationError("bad arg"))["recovered"] is True

    sess_cfg = DistributedStateManager.build_antigravity_session_persistence_config(
        save_dir="artifacts/sessions",
        conversation_id="conv-123",
    )
    assert sess_cfg["save_dir"] == "artifacts/sessions"
    assert sess_cfg["conversation_id"] == "conv-123"
    assert sess_cfg["app_data_dir"] == ".antigravity/app_data"

    repo_root = Path(__file__).resolve().parents[2]
    boundary = json.loads((repo_root / ".antigravity" / "runtime-boundary.json").read_text(encoding="utf-8"))
    assert "app_data_dir" in boundary
    assert "save_dir" in boundary
    assert "workspaces" in boundary

    audit_report = run_agent_runtime_audit(repo_root)
    assert audit_report["is_clean"] is True


def test_usage_metadata_thought_tokens_and_sdk_logger(tmp_path: Path) -> None:
    """Verify UsageMetadata extraction, thoughts_token_count telemetry, and google.antigravity logger."""
    from agents.observability.events import configure_antigravity_sdk_logger
    from agents.observability.prompt_cache import antigravity_usage_metrics
    from apps_model_telemetry.telemetry_facade import record_llm_call

    class _FakeUsage:
        prompt_token_count = 1000
        candidates_token_count = 250
        thoughts_token_count = 150
        cached_content_token_count = 400
        total_token_count = 1400

    class _FakeConversation:
        total_usage = _FakeUsage()

    class _FakeAgent:
        conversation = _FakeConversation()

    metrics = antigravity_usage_metrics(_FakeAgent())
    assert metrics["prompt_token_count"] == 1000
    assert metrics["candidates_token_count"] == 250
    assert metrics["thoughts_token_count"] == 150
    assert metrics["cached_content_token_count"] == 400
    assert metrics["total_token_count"] == 1400
    assert metrics["cache_read_ratio"] == 0.4

    rec = record_llm_call(
        artifact_dir=tmp_path,
        provider="google",
        model="gemini-2.5-flash",  # guardian: allow-model-id -- unit test fixture
        request_digest="req_wave4",
        usage={
            "prompt_token_count": 1000,
            "candidates_token_count": 250,
            "thoughts_token_count": 150,
            "cached_content_token_count": 400,
            "total_token_count": 1400,
        },
        run_id="wave4_test",
        stage="L2",
    )
    assert rec["thought_tokens"] == 150
    assert rec["prompt_tokens"] == 1000

    sdk_logger = configure_antigravity_sdk_logger(level=logging.DEBUG)
    assert sdk_logger.name == "google.antigravity"
    assert sdk_logger.level == logging.DEBUG
