"""Repository-wide pytest isolation for generated runtime caches."""

from __future__ import annotations

import os

import pytest


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
def _reset_operator_otel_environment_between_tests() -> None:
    """Remove OTel values reloaded from the home dotenv by a prior unit test."""
    for name in _OTEL_HOME_DOTENV_KEYS:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name in _OTEL_HOME_DOTENV_KEYS:
            os.environ.pop(name, None)


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
