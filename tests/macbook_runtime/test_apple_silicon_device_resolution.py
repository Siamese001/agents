"""Pillar 2: MPS Hardware Acceleration & Graceful Fallback."""
from __future__ import annotations

import sys
import pytest
import torch

from infrastructure.device.device_manager import (
    allocated_memory_bytes,
    empty_cache,
    resolve_optimal_device,
    synchronize,
)

pytestmark = [pytest.mark.unit]


def test_device_manager_resolves_mps_on_apple_silicon() -> None:
    """Asserts that on Darwin with MPS available, optimal device is 'mps'."""
    if sys.platform == "darwin" and torch.backends.mps.is_available():
        assert resolve_optimal_device() == "mps"


def test_device_manager_explicit_requested_device_override() -> None:
    """Verifies explicit requested device overrides auto-detection."""
    assert resolve_optimal_device(requested="cpu") == "cpu"
    assert resolve_optimal_device(requested="mps") == "mps"


def test_device_manager_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies environment variables override auto-detection."""
    monkeypatch.setenv("DEVICE", "cpu")
    assert resolve_optimal_device() == "cpu"
    monkeypatch.delenv("DEVICE", raising=False)

    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    assert resolve_optimal_device() == "cpu"
    monkeypatch.delenv("EMBEDDING_DEVICE", raising=False)


def test_graceful_cpu_fallback_when_mps_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies graceful fallback to CPU when MPS is unavailable."""
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    assert resolve_optimal_device() == "cpu"


def test_device_manager_synchronize_and_empty_cache() -> None:
    """Verifies synchronization and empty cache execute without error on mps and cpu."""
    synchronize("mps")
    synchronize("cpu")
    synchronize(None)

    empty_cache("mps")
    empty_cache("cpu")
    empty_cache(None)


def test_device_manager_allocated_memory_bytes() -> None:
    """Verifies allocated_memory_bytes returns non-negative integer on all devices."""
    if torch.backends.mps.is_available():
        mps_mem = allocated_memory_bytes("mps")
        assert isinstance(mps_mem, int)
        assert mps_mem >= 0

    cpu_mem = allocated_memory_bytes("cpu")
    assert isinstance(cpu_mem, int)
    assert cpu_mem > 0


def test_mps_tensor_execution_and_numerical_parity() -> None:
    """Verifies that MPS matrix operations match CPU results within FP32 tolerance."""
    if not torch.backends.mps.is_available():
        pytest.skip("MPS not available on this host")

    torch.manual_seed(42)
    x = torch.randn(64, 64, dtype=torch.float32)
    out_cpu = x @ x
    out_mps = (x.to("mps") @ x.to("mps")).cpu()

    assert torch.allclose(out_mps, out_cpu, atol=1e-5), "MPS matrix multiplication diverged from CPU"
