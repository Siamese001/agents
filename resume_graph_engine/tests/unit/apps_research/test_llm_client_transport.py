"""Transport bounds for the Apps Research OpenAI client boundary."""

from __future__ import annotations

import sys
import types

from apps_research.integrations import llm_client


def test_sync_client_uses_profile_aligned_bounded_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("APPS_RESEARCH_OPENAI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))

    llm_client.create_openai_sync_client()

    assert captured == {
        "api_key": "test-key",
        "timeout": 120.0,
        "max_retries": 1,
    }


def test_timeout_override_is_bounded(monkeypatch) -> None:
    monkeypatch.setenv("APPS_RESEARCH_OPENAI_TIMEOUT_SECONDS", "5000")
    assert llm_client._openai_timeout_seconds() == 600.0

    monkeypatch.setenv("APPS_RESEARCH_OPENAI_TIMEOUT_SECONDS", "invalid")
    assert llm_client._openai_timeout_seconds() == 120.0
