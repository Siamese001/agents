from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from apps_model_telemetry.external_model_usage import (
    LEDGER_FILENAME,
    append_external_model_usage,
    external_model_usage_scope,
    normalize_usage,
)
from apps_model_telemetry.execution_evidence import REMOTE_OUTCOME_UNKNOWN, provider_attempt
from apps_rg.runtime.providers.external_provider import ExternalProvider
from apps_rg.runtime.providers.provider_gateway import ProviderProfile
from apps_rg.runtime.judges.executive_summary_x1d import _call_gemini


class _Prompt:
    prompt_blocks = ()
    system_preamble = "System must not be written."
    user_instruction = "Human content must not be written."


def _events(artifact_dir: Path) -> list[dict]:
    path = artifact_dir / LEDGER_FILENAME
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_normalize_usage_preserves_provider_reported_thinking_and_cache() -> None:
    assert normalize_usage(
        "gemini",
        {
            "promptTokenCount": 11,
            "candidatesTokenCount": 13,
            "thoughtsTokenCount": 17,
            "cachedContentTokenCount": 19,
            "totalTokenCount": 41,
        },
    ) == {
        "prompt_tokens": 11,
        "output_tokens": 13,
        "thought_tokens": 17,
        "cached_tokens": 19,
        "cache_write_tokens": None,
        "total_tokens": 41,
    }


def test_append_only_event_uses_digest_and_never_persists_prompt_text(tmp_path: Path) -> None:
    event = append_external_model_usage(
        artifact_dir=tmp_path,
        provider="openai",
        model="gpt-test",
        request_digest="a" * 64,
        outcome="SUCCESS",
        usage={"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
        stage="L2.test",
    )

    assert event is not None
    assert event["event_digest"]
    assert _events(tmp_path) == [event]
    rendered = (tmp_path / LEDGER_FILENAME).read_text(encoding="utf-8")
    assert "prompt text" not in rendered.lower()
    assert "a" * 64 in rendered


def test_provider_attempt_records_unknown_remote_outcome_after_pre_response_timeout(
    tmp_path: Path,
) -> None:
    with provider_attempt(
        artifact_dir=str(tmp_path),
        run_id="run-1",
        trace_id="trace-1",
        app_id="apps_rg",
        stage="L2.section_generation",
        section_id="competencies",
        provider="external_claude",
        requested_model="claude-test",
        request_digest="b" * 64,
    ) as attempt:
        attempt.mark_request_written()
        attempt.finish(failure_phase="WAIT_RESPONSE_HEADERS", error_class="TimeoutError")

    events = _events(tmp_path)
    assert [event["evidence_event"] for event in events] == [
        "ATTEMPT_STARTED",
        "REQUEST_WRITTEN",
        "ATTEMPT_FINISHED",
    ]
    assert events[-1]["remote_outcome"] == REMOTE_OUTCOME_UNKNOWN
    assert events[-1]["failure_phase"] == "WAIT_RESPONSE_HEADERS"
    assert events[-1]["attempt_id"] == events[0]["attempt_id"]


def test_external_provider_writes_usage_to_the_bound_run_ledger(tmp_path: Path) -> None:
    def transport(_request: dict) -> dict:
        return {
            "text": "generated",
            "model": "gpt-test-actual",
            "raw_response": {
                "id": "resp_123",
                "usage": {
                    "input_tokens": 31,
                    "output_tokens": 17,
                    "total_tokens": 48,
                    "input_tokens_details": {"cached_tokens": 8},
                    "output_tokens_details": {"reasoning_tokens": 5},
                },
            },
        }

    provider = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_OPENAI,
        model="gpt-test",
        transport=transport,
        environ={"OPENAI_API_KEY": "test-only"},
    )
    with external_model_usage_scope(
        artifact_dir=tmp_path,
        run_id="run-token-test",
        stage="L2.section_generation",
        section_id="competencies",
    ):
        result = provider.generate(_Prompt(), token_budget=77)

    assert result.runtime_generation_status == "REAL_LLM"
    event = next(event for event in _events(tmp_path) if event["outcome"] == "SUCCESS")
    assert event["provider"] == "external_openai"
    assert event["model"] == "gpt-test-actual"
    assert event["run_id"] == "run-token-test"
    assert event["section_id"] == "competencies"
    assert event["prompt_tokens"] == 31
    assert event["output_tokens"] == 17
    assert event["thought_tokens"] == 5
    assert event["cached_tokens"] == 8
    assert event["total_tokens"] == 48


def test_x1d_gemini_writes_provider_reported_thinking_usage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    payload = {
        "responseId": "gemini-x1d-1",
        "modelVersion": "gemini-3.1-pro-preview",
        "usageMetadata": {
            "promptTokenCount": 47,
            "candidatesTokenCount": 19,
            "thoughtsTokenCount": 23,
            "cachedContentTokenCount": 5,
            "totalTokenCount": 89,
        },
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "score_scale": "0_to_5",
                                    "score": 4.5,
                                    "threshold": 4.0,
                                    "pass": True,
                                    "decisive_failure": False,
                                    "findings": ["ok"],
                                    "cited_sentence_indexes": [1],
                                    "remediation_suggestions": [],
                                }
                            )
                        }
                    ]
                },
            }
        ],
    }
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    monkeypatch.setattr(
        "apps_rg.runtime.judges.executive_summary_x1d._judge_live_https_allowed_under_pytest",
        lambda: True,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.judges.executive_summary_x1d.urllib.request.urlopen",
        lambda _request, timeout: response,
    )

    result = _call_gemini(
        "test-key",
        "grade this candidate",
        "gemini-3.1-pro-preview",
        "judge-input-digest",
        "gemini_pro",
        artifact_base=tmp_path,
        thinking_level="high",
        section_id="competencies",
    )

    assert result.evaluator_mode == "MODEL_BACKED"
    event = _events(tmp_path)[0]
    assert event["stage"] == "L2.X1D_judge"
    assert event["prompt_tokens"] == 47
    assert event["output_tokens"] == 19
    assert event["thought_tokens"] == 23
    assert event["cached_tokens"] == 5
    assert event["total_tokens"] == 89
