"""Unit tests verifying hermetic wire cassette replay testing.

Demonstrates:
1. Replay of authentic wire cassette with zero network egress and zero live API keys.
2. Replacement of fragile, hand-crafted unittest.mock.MagicMock with authentic wire replay.
3. Fail-closed guarantee: unmatched requests raise CassetteNotFoundError immediately.
4. Token accounting and telemetry preservation across frozen wire exchanges.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from infrastructure.sdks_mcps.wire_cassette import (
    CassetteNotFoundError,
    CassetteRegistry,
    CassetteTransport,
    create_replay_openai_client,
)

FIXTURE_PATH = Path("tests/fixtures/cassettes/executive_repair_wire_trace.json")


def test_wire_cassette_loads_and_indexes():
    """Verify that sealed wire cassette loads cleanly from disk."""
    assert FIXTURE_PATH.exists(), f"Missing fixture at {FIXTURE_PATH}"
    registry = CassetteRegistry(FIXTURE_PATH)
    assert registry.count >= 1
    assert registry.count == 1


def test_authentic_wire_replay_replaces_synthetic_mock():
    """Demonstrate wire cassette replay replacing synthetic MagicMock.

    Traditional anti-pattern:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = {"fake": "dict"}
        -> Only tests that Python code can call a mocked object, not the wire protocol.

    Hermetic Wire Replay pattern:
        Wired through authentic httpx transport interceptor with sealed HTTP exchange.
        Executes standard OpenAI SDK client, real response deserialization, real header parsing.
    """
    client = create_replay_openai_client(
        cassette_path=FIXTURE_PATH,
        api_key="hermetic-test-token",
    )

    # Invoke standard OpenAI SDK method with the recorded parameters
    completion = client.chat.completions.create(
        model="gpt-5.6-luna",
        messages=[
            {
                "role": "system",
                "content": "You are the Executive Voice Repair Agent. Align executive summary and competencies to high-rigor corporate narrative.",
            },
            {
                "role": "user",
                "content": "Repair the following unaligned section: Leadership and engineering execution across multi-agent workflows.",
            },
        ],
        response_format={"type": "json_object"},
        extra_body={"reasoning_effort": "medium"},
    )

    # 1. Authentic response envelope
    assert completion.id == "chatcmpl-luna-replay-8f3a2c991e"
    assert completion.model == "gpt-5.6-luna"
    assert len(completion.choices) == 1

    # 2. Authentic payload parsing
    content_raw = completion.choices[0].message.content
    assert content_raw is not None
    payload = json.loads(content_raw)
    assert payload["status"] == "REPAIRED"
    assert "Architected and delivered multi-agent" in payload["executive_summary"]
    assert len(payload["competencies"]) == 2
    assert payload["confidence_score"] == 0.96

    # 3. Authentic token accounting telemetry preserved
    assert completion.usage is not None
    assert completion.usage.prompt_tokens == 128
    assert completion.usage.completion_tokens == 84
    assert completion.usage.completion_tokens_details.reasoning_tokens == 48


def test_unrecorded_request_fails_closed():
    """Verify fail-closed invariant: outbound requests with missing cassettes raise CassetteNotFoundError."""
    client = create_replay_openai_client(
        cassette_path=FIXTURE_PATH,
        api_key="hermetic-test-token",
    )

    # Attempt request with an altered, unrecorded prompt
    with pytest.raises(Exception) as exc_info:
        client.chat.completions.create(
            model="gpt-5.6-luna",
            messages=[
                {"role": "user", "content": "An unrecorded novel prompt that has no wire cassette."}
            ],
        )

    # Verify that the underlying root cause was CassetteNotFoundError
    root_cause = exc_info.value.__cause__ if exc_info.value.__cause__ else exc_info.value
    assert isinstance(root_cause, CassetteNotFoundError)
    err_msg = str(root_cause)
    assert "CASSETTE_NOT_FOUND" in err_msg
    assert "Fail-closed invariant enforced" in err_msg


def test_tampered_model_parameter_fails_closed():
    """Verify that changing model parameters (e.g. requesting different model) fails closed."""
    client = create_replay_openai_client(
        cassette_path=FIXTURE_PATH,
        api_key="hermetic-test-token",
    )

    with pytest.raises(Exception) as exc_info:
        client.chat.completions.create(
            model="unrecorded-model-variant",
            messages=[
                {
                    "role": "system",
                    "content": "You are the Executive Voice Repair Agent. Align executive summary and competencies to high-rigor corporate narrative.",
                },
                {
                    "role": "user",
                    "content": "Repair the following unaligned section: Leadership and engineering execution across multi-agent workflows.",
                },
            ],
            response_format={"type": "json_object"},
        )

    root_cause = exc_info.value.__cause__ if exc_info.value.__cause__ else exc_info.value
    assert isinstance(root_cause, CassetteNotFoundError)
    assert "CASSETTE_NOT_FOUND" in str(root_cause)

