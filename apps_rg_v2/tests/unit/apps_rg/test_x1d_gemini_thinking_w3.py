"""W3 controlled Gemini thinking-effort optimization tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps_rg.runtime.judges import executive_summary_x1d as subject
from apps_rg.runtime.section_judge_policy import policy_matrix_export


def test_w3_gemini_thinking_level_is_mandatory() -> None:
    with pytest.raises(ValueError, match="thinking_level must be explicit"):
        subject._gemini_generation_config(thinking_level="", section_id="headline")


def test_w3_gemini_thinking_uses_source_controlled_tier_levels() -> None:
    standard = subject._gemini_generation_config(
        thinking_level="low",
        section_id="headline",
    )
    enhanced = subject._gemini_generation_config(
        thinking_level="medium",
        section_id="executive_summary",
    )

    assert standard["thinkingConfig"] == {"thinkingLevel": "low"}
    assert enhanced["thinkingConfig"] == {"thinkingLevel": "medium"}
    matrix = policy_matrix_export()
    assert matrix["headline"]["judge_runtime_profile"]["gemini_thinking_level"] == "low"
    assert matrix["executive_summary"]["judge_runtime_profile"]["gemini_thinking_level"] == "medium"


def test_w3_gemini_request_and_receipt_disclose_applied_thinking_level(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(subject, "_judge_live_https_allowed_under_pytest", lambda: True)
    response_doc = {
        "candidates": [
            {
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
                                    "findings": ["grounded"],
                                    "cited_sentence_indexes": [],
                                    "remediation_suggestions": [],
                                }
                            )
                        }
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 20,
            "thoughtsTokenCount": 50,
            "totalTokenCount": 170,
        },
    }
    http_response = MagicMock()
    http_response.read.return_value = json.dumps(response_doc).encode("utf-8")
    http_response.__enter__.return_value = http_response
    monkeypatch.setattr(subject.urllib.request, "urlopen", lambda *_args, **_kwargs: http_response)

    output = subject._call_gemini(
        "test-key",
        "Judge this compact resume output.",
        "gemini-3.1-pro-preview",
        "input-hash",
        "gemini_pro",
        artifact_base=tmp_path,
        thinking_level="low",
        section_id="headline",
    )

    assert output.provider_status == "MODEL_BACKED_PASS"
    request_docs = list(tmp_path.glob("*gemini*provider_request*.json"))
    assert len(request_docs) == 1
    request_doc = json.loads(request_docs[0].read_text(encoding="utf-8"))
    assert request_doc["payload"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert request_doc["gemini_thinking_config"] == {"thinkingLevel": "low"}
    assert request_doc["gemini_thinking_optimization_enabled"] is True
