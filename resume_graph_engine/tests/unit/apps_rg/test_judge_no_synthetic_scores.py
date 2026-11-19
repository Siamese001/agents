"""Wave 2 guard: no code path may emit a synthetic judge score or disguise a deterministic screen as a model call."""
from __future__ import annotations

import io
import pathlib
import urllib.error
from pathlib import Path

from apps_rg.runtime.judges import executive_summary_x1d as x
from apps_rg.runtime.judges import inprocess_proof_judge as stub_mod


def test_judge_stub_functions_no_longer_exist():
    assert not hasattr(stub_mod, "evaluate_argon_x1d_judge")
    assert not hasattr(stub_mod, "is_argon_model")


def test_handoff_screen_is_explicitly_marked_deterministic_non_model():
    res = stub_mod.evaluate_argon_handoff_payload(
        model="handoff-screen",
        body=b'{"claims": ["Grounded fact."], "company_name": "Acme"}',
    )
    assert res["x_deterministic_screen"] is True
    assert res["x_model_call"] is False


def test_argon_model_name_no_longer_short_circuits_the_http_path(monkeypatch, tmp_path: Path):
    """With the keyed transport selected, an Argon pin must reach the HTTP layer, not a constant-score shortcut."""
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "external_api")
    reached: dict[str, str] = {}

    def fake_urlopen(req, timeout=None):
        url = getattr(req, "full_url", "")
        reached["url"] = url
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, io.BytesIO(b"forbidden in test"))

    monkeypatch.setattr(x, "urlopen_provider_request", fake_urlopen)
    monkeypatch.setattr(x, "_is_test_environment", lambda: False, raising=False)
    monkeypatch.setattr(x, "_judge_live_https_allowed_under_pytest", lambda: True)
    out = x._call_gemini(
        "fake-key",
        "P",
        "gemini-4-argon-high",
        "h",
        "gemini_pro",
        artifact_base=tmp_path,
        thinking_level="high",
    )
    assert reached.get("url", "").startswith("https://generativelanguage.googleapis.com/")
    assert out.score is None and out.provider_blocked


def test_no_source_file_constructs_an_argon_response_id_for_judges():
    root = pathlib.Path(x.__file__).resolve().parents[2]
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if '"argon-" +' in text or "argon-' +" in text or 'f"argon-{' in text:
            offenders.append(str(path))
    assert offenders == []
