"""Bounded X1D judge retries and OpenAI empty-content (reasoning budget) handling."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.helpers import apps_rg_model_pins as pins

from apps_rg.runtime.judges.executive_summary_x1d import (
    JudgeOutput,
    _call_openai,
    _extract_json_from_text,
    _invoke_judge_with_bounded_retries,
    _is_retriable_judge_output,
    _resolved_openai_judge_max_completion_tokens,
)


def test_openai_completion_token_budget_escalates_on_retry() -> None:
    assert _resolved_openai_judge_max_completion_tokens(attempt=1) >= 4096
    assert _resolved_openai_judge_max_completion_tokens(attempt=2) >= _resolved_openai_judge_max_completion_tokens(
        attempt=1
    )


@patch("apps_rg.runtime.judges.executive_summary_x1d._judge_live_https_allowed_under_pytest", return_value=True)
@patch("apps_rg.runtime.judges.executive_summary_x1d.urllib.request.urlopen")
def test_sol_judge_uses_responses_api_with_high_effort(
    mock_urlopen: MagicMock,
    _pytest_net: MagicMock,
    tmp_path: Path,
) -> None:
    result = {
        "score_scale": "0_to_5",
        "score": 4.5,
        "threshold": 4.0,
        "pass": True,
        "decisive_failure": False,
        "findings": ["ok"],
        "cited_sentence_indexes": [1],
        "remediation_suggestions": [],
    }
    response = MagicMock()
    response.read.return_value = json.dumps(
        {"model": pins.OPENAI_PROOF_JUDGE_MODEL, "status": "completed", "output_text": json.dumps(result)}
    ).encode()
    response.__enter__.return_value = response
    mock_urlopen.return_value = response

    out = _call_openai(
        "sk-test",
        "grade this section",
        pins.OPENAI_PROOF_JUDGE_MODEL,
        "sol-input-hash",
        "openai_chatgpt",
        artifact_base=tmp_path,
        reasoning_effort="high",
        section_id="executive_summary",
    )

    request = mock_urlopen.call_args.args[0]
    body = json.loads(request.data)
    assert request.full_url == "https://api.openai.com/v1/responses"
    assert body["model"] == pins.OPENAI_PROOF_JUDGE_MODEL
    assert body["reasoning"] == {"effort": "high"}
    assert body["max_output_tokens"] >= 4096
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    schema = body["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    dimensions = schema["properties"]["dimension_verdicts"]
    assert dimensions["additionalProperties"] is False
    assert set(dimensions["required"]) == set(dimensions["properties"])
    for verdict in dimensions["properties"].values():
        assert verdict["additionalProperties"] is False
        assert set(verdict["required"]) == set(verdict["properties"])
    assert "messages" not in body
    assert out.evaluator_mode == "MODEL_BACKED"


def test_is_retriable_parse_error() -> None:
    out = JudgeOutput(
        judge_id="x1d_openai_chatgpt_headline",
        provider_name="OpenAI",
        provider_key="openai_chatgpt",
        evaluator_mode="BLOCKED_RESPONSE_PARSE_ERROR",
        provider_status="BLOCKED_RESPONSE_PARSE_ERROR",
        model_name=pins.COMPETENCIES_SELECTOR_MODEL,
        provider_available=False,
        provider_blocked=True,
        exact_provider_error="Failed to extract JSON from openai_chatgpt response",
    )
    assert _is_retriable_judge_output(out) is True


def test_bounded_retries_stop_after_success() -> None:
    calls: list[int] = []

    def invoke(attempt: int) -> JudgeOutput:
        calls.append(attempt)
        if attempt < 2:
            return JudgeOutput(
                judge_id="x1d_openai",
                provider_name="OpenAI",
                provider_key="openai_chatgpt",
                evaluator_mode="BLOCKED_RESPONSE_PARSE_ERROR",
                provider_status="BLOCKED_RESPONSE_PARSE_ERROR",
                model_name=pins.COMPETENCIES_SELECTOR_MODEL,
                provider_available=False,
                provider_blocked=True,
                exact_provider_error="Failed to extract JSON from openai_chatgpt response",
            )
        return JudgeOutput(
            judge_id="x1d_openai",
            provider_name="OpenAI",
            provider_key="openai_chatgpt",
            evaluator_mode="MODEL_BACKED",
            provider_status="MODEL_BACKED_PASS",
            model_name=pins.COMPETENCIES_SELECTOR_MODEL,
            provider_available=True,
            provider_blocked=False,
            exact_provider_error=None,
            pass_=True,
        )

    with (
        patch.dict("os.environ", {"APPS_RG_X1D_JUDGE_MAX_ATTEMPTS": "3"}),
        patch("apps_rg.runtime.judges.executive_summary_x1d.time.sleep"),
    ):
        out = _invoke_judge_with_bounded_retries(invoke, provider_key="openai_chatgpt")
    assert out.pass_ is True
    assert calls == [1, 2]


def test_extract_json_from_markdown_fence() -> None:
    text = '```json\n{"score_scale":"0_to_5","score":4.0,"threshold":4.0,"pass":true,"decisive_failure":false,"findings":[],"cited_sentence_indexes":[],"remediation_suggestions":[]}\n```'
    parsed = _extract_json_from_text(text)
    assert parsed is not None
    assert parsed.get("score_scale") == "0_to_5"


@patch("apps_rg.runtime.judges.executive_summary_x1d._judge_live_https_allowed_under_pytest", return_value=True)
@patch("apps_rg.runtime.judges.executive_summary_x1d.urllib.request.urlopen")
def test_openai_empty_length_finish_reason_is_retriable_message(
    mock_urlopen: MagicMock,
    _pytest_net: MagicMock,
    tmp_path: Path,
) -> None:
    empty_completion = {
        "status": "incomplete",
        "output_text": "",
        "usage": {"output_tokens": 900, "output_tokens_details": {"reasoning_tokens": 900}},
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(empty_completion).encode()
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    out = _call_openai(
        "sk-test",
        "grade this headline",
        pins.OPENAI_PROOF_JUDGE_MODEL,
        "abc123",
        "openai_chatgpt",
        artifact_base=tmp_path,
        reasoning_effort="high",
        attempt=1,
    )
    assert out.provider_status == "BLOCKED_RESPONSE_PARSE_ERROR"
    assert _is_retriable_judge_output(out)
    assert "finish_reason=incomplete" in (out.exact_provider_error or "").lower()


@patch("apps_rg.runtime.judges.executive_summary_x1d._judge_live_https_allowed_under_pytest", return_value=True)
@patch("apps_rg.runtime.judges.executive_summary_x1d.urllib.request.urlopen")
def test_openai_retry_escalates_max_completion_tokens(
    mock_urlopen: MagicMock,
    _pytest_net: MagicMock,
    tmp_path: Path,
) -> None:
    good = {
        "status": "completed",
        "output_text": json.dumps(
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
        ),
    }
    empty = {"status": "incomplete", "output_text": ""}
    payloads: list[int] = []

    def side_effect(req: object, timeout: float = 60) -> MagicMock:
        body = json.loads(getattr(req, "data", b"{}"))
        if body.get("max_output_tokens"):
            payloads.append(int(body["max_output_tokens"]))
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            empty if len(payloads) == 1 else good
        ).encode()
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    mock_urlopen.side_effect = side_effect

    with (
        patch.dict("os.environ", {"APPS_RG_X1D_JUDGE_MAX_ATTEMPTS": "2"}),
        patch("apps_rg.runtime.judges.executive_summary_x1d.time.sleep"),
    ):
        out = _invoke_judge_with_bounded_retries(
            lambda attempt: _call_openai(
                "sk-test",
                "grade",
                pins.OPENAI_PROOF_JUDGE_MODEL,
                "hash1",
                "openai_chatgpt",
                artifact_base=tmp_path,
                reasoning_effort="high",
                attempt=attempt,
            ),
            provider_key="openai_chatgpt",
        )
    assert out.evaluator_mode == "MODEL_BACKED"
    assert len(payloads) == 2
    assert payloads[1] >= payloads[0]
