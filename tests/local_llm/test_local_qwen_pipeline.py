"""Unit tests for local Qwen 27B inference server and client integration."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.local_llm.serve_qwen_m5 import app, init_engine
from infrastructure.sdks_mcps.client_wrappers import (
    create_local_openai_client,
    create_local_openai_sync_client,
)


@pytest.fixture(scope="module")
def client():
    init_engine(None)  # Initialize mock/fast engine for unit testing
    return TestClient(app)


def test_healthz_endpoint(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["context_window"] == 32768


def test_list_models_endpoint(client):
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    model_ids = [m["id"] for m in data["data"]]
    assert "qwen-3.8-27b" in model_ids


def test_chat_completions_role_narrative(client):
    payload = {
        "model": "qwen-3.8-27b",
        "messages": [
            {"role": "system", "content": "You are a professional executive resume writer. Output one transition sentence."},
            {"role": "user", "content": "Write a transition sentence for Slalom Consulting bridging to AI Platform Director."}
        ],
        "temperature": 0.3,
        "max_tokens": 512,
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "qwen-3.8-27b"
    assert len(data["choices"]) == 1
    content = data["choices"][0]["message"]["content"]
    assert len(content) > 20
    assert data["usage"]["total_tokens"] > 0


def test_local_openai_client_wrapper_contract():
    # Verify environment variable default fallback
    client = create_local_openai_client()
    assert client.base_url.host in ("localhost", "127.0.0.1")
    assert client.base_url.port in (8000, 11434, 8080)
    
    sync_client = create_local_openai_sync_client()
    assert sync_client.base_url.host in ("localhost", "127.0.0.1")
