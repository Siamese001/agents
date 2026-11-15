"""Unit tests for Wave 2 Core Antigravity SDK Dependencies, Client Lifecycle & Local Runtime Adapters."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agents.context.provenance import ContextItem, ContextSnapshot, ContextSourceType
from agents.gateway.contracts import CapabilityRequest, ModelTier
from agents.gateway.model_gateway import ModelCapabilityGateway
from infrastructure.device.device_manager import resolve_litert_backend
from infrastructure.live_execution import api_key, require_live_pipeline
from infrastructure.sdks_mcps.client_wrappers import (
    LiteRTBackend,
    ServiceTier,
    create_antigravity_agent_config,
    create_litert_agent_config,
    create_local_openai_agent_config,
    create_local_openai_client,
    load_agent_config_from_profile,
)


def test_gemini_api_key_precedence_and_no_deprecated_marker() -> None:
    """Verify GEMINI_API_KEY takes precedence over GOOGLE_API_KEY and gemini_client docstring has no deprecated tag."""
    env = {"GEMINI_API_KEY": "primary-gemini-key", "GOOGLE_API_KEY": "secondary-google-key"}
    assert api_key("gemini", environ=env) == "primary-gemini-key"
    assert api_key("google", environ=env) == "primary-gemini-key"

    repo_root = Path(__file__).resolve().parents[2]
    gem_doc = (repo_root / "infrastructure" / "sdks_mcps" / "gemini_client.py").read_text(encoding="utf-8")
    assert "(deprecated)" not in gem_doc


def test_vertex_standard_express_and_priority_service_tier_configs() -> None:
    """Verify LocalAgentConfig supports Vertex Standard (ADC), Vertex Express, and ServiceTier.PRIORITY."""
    std_cfg = create_antigravity_agent_config(
        vertex=True,
        project="agents-prod",
        location="us-central1",
        priority_tier=True,
    )
    assert std_cfg.vertex is True
    assert std_cfg.project == "agents-prod"
    assert std_cfg.location == "us-central1"
    assert std_cfg.endpoint is not None
    assert std_cfg.endpoint.options.service_tier == ServiceTier.PRIORITY

    exp_cfg = create_antigravity_agent_config(vertex=True, api_key="vertex-express-key")
    assert exp_cfg.vertex is True
    assert exp_cfg.api_key == "vertex-express-key"


def test_keyless_local_agent_configs_and_live_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify LiteRTAgentConfig and LocalOpenAIAgentConfig work keylessly without LOCAL_OPENAI_API_KEY."""
    monkeypatch.delenv("LOCAL_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", "http://127.0.0.1:8000/v1")

    litert_cfg = create_litert_agent_config("models/local.litertlm", backend="NPU")
    assert litert_cfg.keyless is True
    assert litert_cfg.backend == LiteRTBackend.NPU
    assert litert_cfg.enable_speculative_decoding is True

    local_oai_cfg = create_local_openai_agent_config(model="local-27b")
    assert local_oai_cfg.keyless is True
    assert local_oai_cfg.is_lightweight is True

    client = create_local_openai_client()
    assert client is not None

    fps = require_live_pipeline(["litert", "local_openai"], environ={})
    assert fps["litert"] == "keyless-local"
    assert fps["local_openai"] == "keyless-local"
    assert resolve_litert_backend("NPU") == "NPU"


def test_profile_loader_and_async_antigravity_gateway_streaming() -> None:
    """Verify load_agent_config_from_profile and ModelCapabilityGateway async Agent streaming."""
    prof_cfg = load_agent_config_from_profile("external_claude_generator", "executive_summary", eval_mode=True)
    assert prof_cfg.skills_paths and prof_cfg.skills_paths[0].endswith(".agents/skills")

    class _FakeStream:
        def __init__(self, items: list[str]) -> None:
            self._items = list(items)

        def __aiter__(self) -> Any:
            async def _gen() -> Any:
                for it in self._items:
                    yield it

            return _gen()

    class _FakeResponse:
        def __init__(self) -> None:
            self.thoughts = _FakeStream(["deliberating step 1"])
            self._tokens = ["Verified ", "SDK ", "output."]

        def __aiter__(self) -> Any:
            async def _gen() -> Any:
                for tok in self._tokens:
                    yield tok

            return _gen()

    class _FakeAgent:
        def __init__(self, config: Any) -> None:
            self.config = config

        async def __aenter__(self) -> _FakeAgent:
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def chat(self, prompt: str) -> _FakeResponse:
            return _FakeResponse()

    gateway = ModelCapabilityGateway()
    snapshot = ContextSnapshot(
        snapshot_id="snap-w2",
        items=(ContextItem(source_id="s1", source_type=ContextSourceType.REQUEST, content="Test SDK agent"),),
        max_token_budget=1000,
    )
    req = CapabilityRequest(capability_name="sdk_stream", prompt_snapshot=snapshot, model_tier=ModelTier.REASONING)
    resp = asyncio.run(gateway.async_execute_with_antigravity_agent(req, config=prof_cfg, agent_cls=_FakeAgent))
    assert resp.status == "SUCCESS"
    assert resp.provider == "google_antigravity"
    assert resp.content == "Verified SDK output."
