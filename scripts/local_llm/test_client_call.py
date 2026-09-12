#!/usr/bin/env python3
"""Test harness demonstrating local Qwen 27B client call via infrastructure wrappers."""

import asyncio
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from infrastructure.sdks_mcps.client_wrappers import create_local_openai_client


async def test_narrative_generation():
    client = create_local_openai_client()
    model = "qwen-3.8-27b"
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
        print(f"\n[Usage Tokens]: {response.usage.total_tokens} total ({response.usage.prompt_tokens} prompt, {response.usage.completion_tokens} completion)")
        return True
    except Exception as exc:
        print(f"Error calling local endpoint: {exc}")
        print("Note: Ensure the local server is running with: python scripts/local_llm/serve_qwen_m5.py")
        return False


if __name__ == "__main__":
    asyncio.run(test_narrative_generation())
