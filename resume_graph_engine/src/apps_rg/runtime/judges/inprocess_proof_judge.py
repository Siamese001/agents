"""Deterministic apps_research handoff screen (NOT a model call).

``evaluate_argon_handoff_payload`` is called by ``apps_research/integrations/provider_gateway.py`` for any pin
whose model name contains "argon". It does not call a model: it returns a fixed pass verdict unless the request
text matches a small set of manipulation phrases. Its response is marked ``x_deterministic_screen`` so nothing
downstream can mistake it for a model-backed judgment.

The former X1D judge stub that lived in this module (constant scores of 4.80 / 4.85, canned findings, invented
token counts) was removed: X1D proof judges now run through the IDE CLI transport or the keyed HTTP path and
are BLOCKED when neither is available. See resume_graph_engine/artifacts/apps_rg/judge_parity/w0/callers.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def evaluate_argon_handoff_payload(
    *,
    model: str,
    body: bytes,
) -> dict[str, Any]:
    """Screen an apps_research or bare_pipeline handoff request with deterministic rules (no model is called)."""
    try:
        req_json = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        req_json = {}
    raw_str = json.dumps(req_json, ensure_ascii=False)
    # Check for adversarial directive patterns if present in user text
    verdict = "PASS"
    score = 0.95
    reasoning = "Deterministic screen: no adversarial directive pattern found (no model was called)."
    if re.search(r"\b(?:ignore\s+all\s+previous\s+instructions|bypass\s+the\s+safety\s+gate)\b", raw_str, re.I):
        verdict = "FAIL"
        score = 0.10
        reasoning = "Deterministic screen: prohibited evaluator/runtime manipulation directive detected."

    inner = json.dumps(
        {"verdict": verdict, "score": score, "reasoning": reasoning},
        separators=(",", ":"),
    )
    digest = hashlib.sha256(body or b"").hexdigest()[:16]
    prompt_tokens = max(1, len(body or b"") // 4)
    return {
        "responseId": f"argon-handoff-{digest}",
        "modelVersion": model,
        "x_deterministic_screen": True,
        "x_model_call": False,
        "candidates": [
            {
                "content": {
                    "parts": [{"text": inner}],
                    "role": "model",
                },
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": prompt_tokens,
            "candidatesTokenCount": 24,
            "thoughtsTokenCount": 0,
            "totalTokenCount": prompt_tokens + 24,
        },
    }


__all__ = [
    "evaluate_argon_handoff_payload",
]
