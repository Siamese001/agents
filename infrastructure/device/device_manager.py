"""Unified device resolution and hardware acceleration management abstraction.

Provides cross-platform device resolution prioritizing Apple Silicon (MPS / Metal)
on macOS with graceful CPU fallback, while retaining CUDA support on Linux.
"""

from __future__ import annotations

import logging
import os
import resource
import sys
from typing import Any

_logger = logging.getLogger(__name__)


def is_mps_available() -> bool:
    """Check if Apple Silicon MPS is built and available in PyTorch."""
    try:
        import torch

        return bool(
            hasattr(torch.backends, "mps")
            and torch.backends.mps.is_built()
            and torch.backends.mps.is_available()
        )
    except (ImportError, AttributeError, RuntimeError):
        return False


def is_cuda_available() -> bool:
    """Check if NVIDIA CUDA is available in PyTorch."""
    try:
        import torch

        return bool(hasattr(torch, "cuda") and torch.cuda.is_available())
    except (ImportError, AttributeError, RuntimeError):
        return False


def resolve_optimal_device(requested: str | None = None) -> str:
    """Resolve the optimal computing device for the host platform.

    Precedence order:
    1. Explicit `requested` argument (if non-empty).
    2. Environment overrides: `DEVICE`, `EMBEDDING_DEVICE`,
       `APPS_RG_HYDRATION_DEVICE`, `VECTOR_DB_DEVICE`.
    3. Platform auto-resolution:
       - On Darwin (macOS): `mps` if MPS is available, else `cpu`.
       - On Linux / other OS: `cuda` if CUDA is available, else `cpu`.

    Returns:
        Canonical device string ("mps", "cuda", "cpu", or explicit indexed device e.g. "cuda:0").
    """
    override = (
        requested
        or os.environ.get("DEVICE")
        or os.environ.get("EMBEDDING_DEVICE")
        or os.environ.get("APPS_RG_HYDRATION_DEVICE")
        or os.environ.get("VECTOR_DB_DEVICE")
        or ""
    ).strip().lower()

    if override:
        if override in {"mps", "cuda", "cpu"}:
            return override
        if override.startswith("cuda:") or override.startswith("mps:"):
            return override
        if "mps" in override:
            return "mps"
        if "cuda" in override:
            return "cuda"
        if "cpu" in override:
            return "cpu"

    if sys.platform == "darwin":
        if is_mps_available():
            return "mps"
        return "cpu"

    if is_cuda_available():
        return "cuda"
    return "cpu"


def synchronize(device: str | None = None) -> None:
    """Block until all outstanding kernels/operations on device finish."""
    target = (device or resolve_optimal_device()).strip().lower()
    try:
        import torch

        if target.startswith("mps") and hasattr(torch, "mps") and hasattr(torch.mps, "synchronize"):
            torch.mps.synchronize()
        elif target.startswith("cuda") and hasattr(torch, "cuda") and torch.cuda.is_available():
            torch.cuda.synchronize()
    except (ImportError, RuntimeError) as exc:
        _logger.debug("synchronize failed on %s: %s", target, exc)


def empty_cache(device: str | None = None) -> None:
    """Release unallocated cached memory held by device allocator back to the OS."""
    target = (device or resolve_optimal_device()).strip().lower()
    try:
        import torch

        if target.startswith("mps") and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()
        elif target.startswith("cuda") and hasattr(torch, "cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()
    except (ImportError, RuntimeError) as exc:
        _logger.debug("empty_cache failed on %s: %s", target, exc)


def allocated_memory_bytes(device: str | None = None) -> int:
    """Return active allocated memory in bytes on device, or host process RSS on CPU."""
    target = (device or resolve_optimal_device()).strip().lower()
    try:
        import torch

        if target.startswith("mps") and hasattr(torch, "mps") and hasattr(torch.mps, "current_allocated_memory"):
            return int(torch.mps.current_allocated_memory())
        if target.startswith("cuda") and hasattr(torch, "cuda") and torch.cuda.is_available():
            return int(torch.cuda.memory_allocated())
    except (ImportError, RuntimeError):
        pass

    try:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return int(rss)  # macOS ru_maxrss is in bytes
        return int(rss * 1024)  # Linux ru_maxrss is in KiB
    except (OSError, ValueError):
        return 0


def get_device_telemetry(device: str | None = None) -> dict[str, Any]:
    """Return structured telemetry describing device status and active allocation."""
    target = resolve_optimal_device(device)
    allocated = allocated_memory_bytes(target)
    telemetry: dict[str, Any] = {
        "device": target,
        "platform": sys.platform,
        "mps_available": is_mps_available(),
        "cuda_available": is_cuda_available(),
        "allocated_bytes": allocated,
        "allocated_mib": round(allocated / (1024.0 * 1024.0), 3),
    }
    try:
        import torch

        telemetry["torch_version"] = str(torch.__version__)
    except ImportError:
        telemetry["torch_version"] = None
    return telemetry
