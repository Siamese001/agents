"""Unit tests for canonical shared `infrastructure.sdks_mcps.agy_cli_transport` and model registry extraction."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from infrastructure.sdks_mcps import agy_cli_transport as shared_t
from tools.hitl_governance import load_approved_provider_models


def _ok_stream(model: str = "gemini-4-argon-medium") -> str:
    evts = [
        {"event": "init", "init": {"model": model, "permission_mode": "request-review"}},
        {
            "event": "result",
            "result": {
                "conversation_id": "conv_shared_001",
                "status": "SUCCESS",
                "response": '{"ok": true}',
                "structured_output": {"ok": True},
                "duration_seconds": 0.4,
                "usage": {"total_tokens": 42},
            },
        },
    ]
    return "\n".join(json.dumps(e) for e in evts) + "\n"


def test_shared_transport_strips_keys_and_returns_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    for var in shared_t.KEY_ENV_VARS:
        monkeypatch.setenv(var, "secret-token")

    def fake_run(argv, **kw):
        captured["argv"] = argv
        captured["env"] = kw["env"]
        return subprocess.CompletedProcess(argv, 0, _ok_stream(), "")

    monkeypatch.setattr(shared_t.subprocess, "run", fake_run)
    monkeypatch.setattr(shared_t, "resolve_agy_bin", lambda b=None: "/fake/agy")

    res = shared_t.run_agy("grade candidate", model="gemini-4-argon-medium", json_schema={"type": "object"})
    assert res.status == "SUCCESS"
    assert res.conversation_id == "conv_shared_001"
    assert res.usage["total_tokens"] == 42
    assert not (set(shared_t.KEY_ENV_VARS) & set(captured["env"]))  # type: ignore[arg-type]


def test_shared_transport_quota_cooldown_lifecycle() -> None:
    shared_t.clear_agy_quota_cooldowns()
    assert not shared_t.is_agy_model_quota_cooled_down("gemini-3.8-flash-medium")
    wait_s = shared_t.mark_agy_model_quota_exhausted("gemini-3.8-flash-medium", "429 resets in 2m", ttl_s=60.0)
    assert wait_s == 60.0
    assert shared_t.is_agy_model_quota_cooled_down("gemini-3.8-flash-medium")
    shared_t.clear_agy_quota_cooldowns()
    assert not shared_t.is_agy_model_quota_cooled_down("gemini-3.8-flash-medium")


def test_load_approved_provider_models_includes_ide_cli_pins() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    approved = load_approved_provider_models(repo_root)
    for expected in (
        "gemini-4-argon-high",
        "gemini-4-argon-medium",
        "gemini-3.8-flash-medium",
        "gemini-4-neon-medium",
        "gpt-oss-120b-medium",
    ):
        assert expected in approved, f"Missing IDE CLI model pin {expected!r} in load_approved_provider_models"
