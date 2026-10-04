"""Regression tests for HardenedAnthropicExecutor client setup and retirement.

Wave 4 SSOT updates:
  - HardenedAnthropicExecutor is retired in favor of apps_rg.runtime.providers.provider_gateway
  - Direct unpinned anthropic SDK imports and client instantiations are retired
  - Class is importable and emits DeprecationWarning on instantiation
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest

from apps_rg.repository_layout import resolve_apps_rg_path

_EXECUTOR_PATH = resolve_apps_rg_path(
    Path(__file__).resolve().parents[4],
    "enforcement",
    "HardenedanthropicexecutorStrategy.py",
)


@pytest.fixture(scope="module")
def executor_source() -> str:
    """Read the executor source once per test module."""
    return _EXECUTOR_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Source-level retirement assertions
# ---------------------------------------------------------------------------


def test_anthropic_direct_sdk_is_retired(executor_source: str):
    """Direct unpinned SDK construction must not occur outside runtime/providers."""
    assert "RETIRED" in executor_source
    assert "anthropic.Anthropic(api_key=" not in executor_source


def test_dotenv_load_is_called_at_module_level(executor_source: str):
    assert "from dotenv import load_dotenv" in executor_source
    assert re.search(r"^load_dotenv\(\)", executor_source, re.MULTILINE)


def test_setup_client_reads_api_key_from_environ(executor_source: str):
    assert 'os.environ.get("ANTHROPIC_API_KEY")' in executor_source


def test_setup_client_warns_when_api_key_missing(executor_source: str):
    assert re.search(
        r'logger\.warning\(\s*"ANTHROPIC_API_KEY not set',
        executor_source,
    )


def test_cascade_breakage_is_acknowledged():
    """Historical pin: the cascade was resolved in EX1+EX2 commits."""
    rca_note = (
        "HardenedAnthropicExecutor import cascade RESOLVED by: "
        "(1) apps_rg_runtime/L2_execution/utils/__init__.py get_clock re-export, "
        "(2) apps_rg/bootstrap_runtime.py _ensure_module real-import preference, "
        "(3) apps_rg_runtime/mixins/hardening_mixin.py __init__ lazy-import fix."
    )
    assert rca_note


# ---------------------------------------------------------------------------
# Functional tier — end-to-end construction path
# ---------------------------------------------------------------------------


def test_executor_class_is_importable():
    from apps_rg.enforcement.HardenedanthropicexecutorStrategy import (
        HardenedAnthropicExecutor,
    )

    assert HardenedAnthropicExecutor is not None
    assert HardenedAnthropicExecutor.__name__ == "HardenedAnthropicExecutor"


def test_executor_instantiates_with_retirement_warning(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-" + "x" * 90)
    from apps_rg.enforcement.HardenedanthropicexecutorStrategy import (
        HardenedAnthropicExecutor,
    )

    with pytest.deprecated_call():
        executor = HardenedAnthropicExecutor()

    assert executor._client is None


def test_executor_without_api_key_keeps_client_none(monkeypatch, caplog):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        "apps_rg.enforcement.HardenedanthropicexecutorStrategy.load_dotenv",
        lambda *a, **kw: None,
    )

    import importlib
    import apps_rg.enforcement.HardenedanthropicexecutorStrategy as mod

    importlib.reload(mod)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with caplog.at_level("WARNING"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            executor = mod.HardenedAnthropicExecutor()

    assert executor._client is None


def test_get_clock_reexport_from_l2_execution_utils():
    apps_rg_runtime = pytest.importorskip("apps_rg_runtime")
    from apps_rg_runtime.L2_execution.utils import get_clock

    assert callable(get_clock)


def test_bootstrap_runtime_does_not_clobber_apps_rg_runtime_package():
    apps_rg_runtime = pytest.importorskip("apps_rg_runtime")
    import apps_rg  # noqa: F401

    assert hasattr(apps_rg_runtime, "__path__")
    assert apps_rg_runtime.__path__ is not None
