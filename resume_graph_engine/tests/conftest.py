"""Repository-wide pytest isolation for generated runtime caches."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_RG_SRC = _REPO_ROOT / "resume_graph_engine" / "src"
if str(_RG_SRC) not in sys.path:
    sys.path.insert(0, str(_RG_SRC))

_RG_TESTS = str(_REPO_ROOT / "resume_graph_engine" / "tests")
try:
    import tests
    if hasattr(tests, "__path__") and _RG_TESTS not in tests.__path__:
        tests.__path__.append(_RG_TESTS)
except ImportError:
    pass

try:
    import tools
except ImportError:
    pass


_OTEL_HOME_DOTENV_KEYS = (
    "APPS_OTEL_EXPORTER_OTLP_ENDPOINT",
    "APPS_OTEL_COLLECTOR_SPANS_FILE",
    "APPS_OTEL_COLLECTOR_FILE",
    "OTEL_COLLECTOR_SPANS_FILE",
)
_ORIGINAL_OTEL_TEST_ENV = {
    name: os.environ.get(name) for name in _OTEL_HOME_DOTENV_KEYS
}


@pytest.fixture(scope="session", autouse=True)
def _isolate_operator_otel_environment() -> None:
    """Keep collection-time home-dotenv loading out of unit-test telemetry state."""
    for name in _OTEL_HOME_DOTENV_KEYS:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in _ORIGINAL_OTEL_TEST_ENV.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture(autouse=True)
def _reset_operator_otel_environment_between_tests(tmp_path: Path) -> None:
    """Remove OTel values reloaded from the home dotenv and isolate per-test cache root."""
    for name in _OTEL_HOME_DOTENV_KEYS:
        os.environ.pop(name, None)
    prev_cache = os.environ.get("APPS_RG_R1B_CACHE_ROOT")
    os.environ["APPS_RG_R1B_CACHE_ROOT"] = str(tmp_path / "r1b_cache")
    try:
        yield
    finally:
        for name in _OTEL_HOME_DOTENV_KEYS:
            os.environ.pop(name, None)
        if prev_cache is None:
            os.environ.pop("APPS_RG_R1B_CACHE_ROOT", None)
        else:
            os.environ["APPS_RG_R1B_CACHE_ROOT"] = prev_cache


@pytest.fixture(scope="session", autouse=True)
def _isolate_runtime_cache_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Never let a test create the default repository-owned R1B cache."""
    env_name = "APPS_RG_R1B_CACHE_ROOT"
    previous = os.environ.get(env_name)
    os.environ[env_name] = str(tmp_path_factory.mktemp("apps_rg_runtime_cache"))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = previous
