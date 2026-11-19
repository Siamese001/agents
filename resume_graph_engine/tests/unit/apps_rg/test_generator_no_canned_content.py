"""Wave 3 guard: canned generator stub is gone and 5-5- model pins never bypass real transport."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

from apps_rg.runtime.providers import external_provider as ep
from apps_rg.runtime.providers.external_provider import ExternalProvider
from apps_rg.runtime.providers.provider_gateway import ProviderProfile


def test_inprocess_ide_provider_module_no_longer_exists():
    assert importlib.util.find_spec("apps_rg.runtime.providers.inprocess_ide_provider") is None
    providers_dir = Path(ep.__file__).resolve().parent
    assert not (providers_dir / "inprocess_ide_provider.py").exists()


def test_no_source_file_imports_inprocess_ide_provider_or_emits_msg_ide_id():
    src_root = Path(ep.__file__).resolve().parents[2]
    offenders: list[str] = []
    for py in src_root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "inprocess_ide_provider" in text or "msg_ide_" in text or "_synthesize_executive_summary" in text:
            offenders.append(str(py))
    assert offenders == []


def test_sonnet_5_5_model_under_external_api_hits_http_never_canned_content(monkeypatch):
    """Under external_api transport, a `5-5-` model id must reach HTTP (or fail closed), never canned content."""
    reached: dict[str, str] = {}

    def fake_urlopen(req, timeout=None):
        url = getattr(req, "full_url", "")
        reached["url"] = url
        raise HTTPError(url, 401, "Unauthorized", None, io.BytesIO(b"invalid api key"))

    monkeypatch.setattr(ep.urllib.request, "urlopen", fake_urlopen)
    prov = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
        model="claude-sonnet-5-5-high",
        environ={
            "APPS_RG_GENERATION_TRANSPORT": "external_api",
            "ANTHROPIC_API_KEY": "sk-ant-fake",
        },
    )
    compiled = SimpleNamespace(
        user_instruction="Generate executive summary JSON",
    )
    res = prov.generate(compiled, token_budget=600, timeout_seconds=15)
    assert reached.get("url") == "https://api.anthropic.com/v1/messages"
    assert res.runtime_generation_status == "BLOCKED"
    assert res.raw_model_output == ""


def test_sonnet_5_5_model_under_ide_cli_blocks_when_cli_unconfigured():
    prov = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
        model="claude-sonnet-5-5-high",
        environ={"APPS_RG_GENERATION_TRANSPORT": "ide_cli", "AGY_CLI_BIN": ""},
    )
    compiled = SimpleNamespace(
        user_instruction="Generate executive summary JSON",
    )
    res = prov.generate(compiled, token_budget=600, timeout_seconds=15)
    assert res.runtime_generation_status == "BLOCKED"
    assert res.provider_attempted is False
    assert res.raw_model_output == ""
    assert "IDE CLI generation session unavailable" in (res.exact_provider_error or "")
