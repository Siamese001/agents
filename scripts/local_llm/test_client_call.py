#!/usr/bin/env python3
"""Test harness and deterministic unit checks for local 27B client wrappers."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from infrastructure.live_execution import LiveExecutionError
from infrastructure.sdks_mcps.client_wrappers import create_local_openai_client


def _resolve_local_model_id(catalog_override: Path | None = None) -> str:
    catalog_path = catalog_override or (_REPO_ROOT / "config" / "model_catalog.json")
    if catalog_path.is_file():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            for section in catalog.values():
                if isinstance(section, dict) and "local_model_id" in section:
                    model_id = str(section.get("local_model_id") or "").strip()
                    if model_id:
                        return model_id
        except (OSError, ValueError, TypeError):
            pass
    return "local-default-27b"


def test_resolve_local_model_id_and_client_wrapper(tmp_path: Path, monkeypatch: object) -> None:
    import pytest

    model_id = _resolve_local_model_id()
    assert isinstance(model_id, str) and len(model_id) > 0

    fallback_cat = tmp_path / "broken_catalog.json"
    fallback_cat.write_text("{invalid", encoding="utf-8")
    assert _resolve_local_model_id(fallback_cat) == "local-default-27b"

    mp = monkeypatch  # type: ignore[assignment]
    mp.delenv("LOCAL_OPENAI_API_KEY", raising=False)
    mp.delenv("LOCAL_OPENAI_BASE_URL", raising=False)
    with pytest.raises(LiveExecutionError, match="LOCAL_PROVIDER_ERROR"):
        create_local_openai_client()

    mp.setenv("LOCAL_OPENAI_API_KEY", "local-test-token")
    mp.setenv("LOCAL_OPENAI_BASE_URL", "http://127.0.0.1:8000/v1")
    client = create_local_openai_client()
    assert client is not None
    assert str(client.base_url).startswith("http://127.0.0.1:8000")


async def run_narrative_generation_demo() -> bool:
    client = create_local_openai_client()
    model = _resolve_local_model_id()
    print(f"Connecting to local model endpoint: {client.base_url} (model: {model})")

    system_prompt = (
        "You are an executive resume writer. Output exactly one high-altitude transition "
        "sentence bridging the candidate's leadership at Slalom Consulting to an SVP AI Platforms role."
    )
    user_prompt = (
        "Candidate Facts: Scaled multi-agent orchestration platforms, deterministic routing, "
        "and runtime governance across enterprise financial clients. Target: SVP AI Platforms."
    )

    start = time.time()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=256,
        )
        elapsed = time.time() - start
        content = response.choices[0].message.content
        print(f"\n[Generated Output in {elapsed:.2f}s]:\n{content}")
        print(
            f"\n[Usage Tokens]: {response.usage.total_tokens} total "
            f"({response.usage.prompt_tokens} prompt, {response.usage.completion_tokens} completion)"
        )
        return True
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error calling local endpoint: {exc}")
        print("Note: Ensure the local inference server is running on the configured port.")
        return False


if __name__ == "__main__":
    asyncio.run(run_narrative_generation_demo())
