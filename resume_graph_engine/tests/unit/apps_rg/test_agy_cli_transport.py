"""Unit tests for apps_rg.runtime.providers.agy_cli_transport using a faked subprocess (no CLI, no network)."""
from __future__ import annotations

import json
import subprocess

import pytest

from apps_rg.runtime.providers import agy_cli_transport as t


def _stream(model="claude-sonnet-5-5-medium", status="SUCCESS", tool=False, structured=None, response="OK\n",
            conversation_id="c1", total_tokens=10):
    evts = [{"event": "init", "init": {"model": model, "permission_mode": "request-review"}}]
    if tool:  # one call is reported as ACTIVE then DONE: must count as ONE distinct call
        for state in ("ACTIVE", "DONE"):
            evts.append({"event": "step_update", "step_update": {"step_index": 3, "state": state, "step_type": "tool", "tool_name": "write_file"}})
    result = {"conversation_id": conversation_id, "status": status, "response": response, "duration_seconds": 1.5,
              "usage": {"total_tokens": total_tokens}}
    if structured is not None:
        result["structured_output"] = structured
    if status != "SUCCESS":
        result["error"] = "boom"
    evts.append({"event": "result", "result": result})
    return "\n".join(json.dumps(e) for e in evts) + "\n"


@pytest.fixture
def fake(monkeypatch):
    calls = {}

    def install(stdout, returncode=0):
        def fake_run(argv, **kw):
            calls["argv"], calls["kw"] = argv, kw
            return subprocess.CompletedProcess(argv, returncode, stdout, "")
        monkeypatch.setattr(t.subprocess, "run", fake_run)
        monkeypatch.setattr(t, "resolve_agy_bin", lambda b=None: "/fake/agy")
        return calls
    return install


def test_parse_stream_counts_one_tool_call_for_active_and_done():
    parsed = t.parse_stream(_stream(tool=True))
    assert parsed["tool_calls"] == ["write_file"]
    assert parsed["init_model"] == "claude-sonnet-5-5-medium"
    assert parsed["result"]["status"] == "SUCCESS"


def test_parse_stream_rejects_non_json_line():
    with pytest.raises(t.AgyTransportError, match="non-JSON"):
        t.parse_stream("not json\n")


def test_success_returns_structured_output_usage_and_conversation_id(fake):
    fake(_stream(structured={"k": 1}))
    r = t.run_agy("hi", model="claude-sonnet-5-5-medium", json_schema={"type": "object"})
    assert r.structured_output == {"k": 1}
    assert r.model_reported == "claude-sonnet-5-5-medium"
    assert r.usage == {"total_tokens": 10}
    assert r.conversation_id == "c1"


def test_api_key_env_vars_are_stripped_from_child_env(fake, monkeypatch):
    for k in t.KEY_ENV_VARS:
        monkeypatch.setenv(k, "SECRET")
    calls = fake(_stream())
    t.run_agy("hi", model="claude-sonnet-5-5-medium")
    assert not (set(t.KEY_ENV_VARS) & set(calls["kw"]["env"]))


def test_call_uses_deny_all_settings_isolated_cwd_and_explicit_timeout(fake):
    calls = fake(_stream())
    t.run_agy("hi", model="claude-sonnet-5-5-medium", timeout_s=77)
    argv = calls["argv"]
    assert "--settings" in argv and argv[argv.index("--model") + 1] == "claude-sonnet-5-5-medium"
    assert calls["kw"]["timeout"] == 77 and calls["kw"]["shell"] is False
    assert "agy_transport_" in calls["kw"]["cwd"]
    assert "write_file(*)" in t.NO_TOOLS_SETTINGS["permissions"]["deny"]
    assert t.NO_TOOLS_SETTINGS["permissions"]["allow"] == []


def test_tool_call_in_stream_fails_the_call(fake):
    fake(_stream(tool=True))
    with pytest.raises(t.AgyTransportError, match="tool calls attempted"):
        t.run_agy("hi", model="claude-sonnet-5-5-medium")


def test_model_mismatch_fails_the_call(fake):
    fake(_stream(model="gemini-4-argon-high"))
    with pytest.raises(t.AgyTransportError, match="model mismatch"):
        t.run_agy("hi", model="claude-sonnet-5-5-medium")


def test_error_status_fails_the_call(fake):
    fake(_stream(status="ERROR"))
    with pytest.raises(t.AgyTransportError, match="status=ERROR"):
        t.run_agy("hi", model="claude-sonnet-5-5-medium")


def test_nonzero_exit_without_result_fails(fake):
    fake("", returncode=1)
    with pytest.raises(t.AgyTransportError, match="exit=1"):
        t.run_agy("hi", model="claude-sonnet-5-5-medium")


def test_missing_conversation_id_fails_the_call(fake):
    fake(_stream(conversation_id=""))
    with pytest.raises(t.AgyTransportError, match="conversation id"):
        t.run_agy("hi", model="claude-sonnet-5-5-medium")


@pytest.mark.parametrize("tokens", [0, -5])
def test_missing_real_usage_fails_the_call(fake, tokens):
    fake(_stream(total_tokens=tokens))
    with pytest.raises(t.AgyTransportError, match="token usage"):
        t.run_agy("hi", model="claude-sonnet-5-5-medium")


def test_timeout_is_reported(monkeypatch):
    monkeypatch.setattr(t, "resolve_agy_bin", lambda b=None: "/fake/agy")

    def boom(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw["timeout"])
    monkeypatch.setattr(t.subprocess, "run", boom)
    with pytest.raises(t.AgyTransportError, match="timed out"):
        t.run_agy("hi", model="m", timeout_s=1)


def test_empty_and_oversize_prompts_rejected():
    with pytest.raises(t.AgyTransportError, match="empty"):
        t.run_agy("   ", model="m")
    with pytest.raises(t.AgyTransportError, match="too large"):
        t.run_agy("x" * (t.MAX_PROMPT_CHARS + 1), model="m")


def test_resolve_rejects_ide_launcher_banner(monkeypatch):
    monkeypatch.setattr(
        t.subprocess, "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "Antigravity IDE 1.107.0\nUsage: antigravity-ide [options]", ""),
    )
    with pytest.raises(t.AgyTransportError, match="not the headless"):
        t.resolve_agy_bin("/some/agy")


def test_resolve_requires_explicit_binary(monkeypatch):
    monkeypatch.delenv(t.AGY_CLI_ENV_VAR, raising=False)
    with pytest.raises(t.AgyTransportError, match="not given"):
        t.resolve_agy_bin(None)


def test_resolve_accepts_real_cli_banner(monkeypatch):
    monkeypatch.setattr(
        t.subprocess, "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "Usage of agy:\n  --print  Run a single prompt", ""),
    )
    assert t.resolve_agy_bin("/some/agy") == "/some/agy"


def test_ide_cli_ready_reports_reason_when_unset_or_wrong(monkeypatch):
    t._ready_cached.cache_clear()
    monkeypatch.delenv(t.AGY_CLI_ENV_VAR, raising=False)
    ok, why = t.ide_cli_ready()
    assert not ok and t.AGY_CLI_ENV_VAR in why
    monkeypatch.setattr(
        t.subprocess, "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "Antigravity IDE 1.107.0", ""),
    )
    t._ready_cached.cache_clear()
    ok, why = t.ide_cli_ready("/ide/launcher")
    assert not ok and "not the headless" in why
    t._ready_cached.cache_clear()


def test_suffixed_model_omits_conflicting_effort_flag_while_base_alias_passes_it(fake):
    calls = fake(_stream(model="claude-sonnet-5-5-high"))
    t.run_agy("hi", model="claude-sonnet-5-5-high", effort="medium")
    assert "--effort" not in calls["argv"]

    calls2 = fake(_stream(model="gemini-pro-orchestrator"))
    t.run_agy("hi", model="gemini-pro-orchestrator", effort="medium")
    assert calls2["argv"][calls2["argv"].index("--effort") + 1] == "medium"
