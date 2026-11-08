"""Device and hardware acceleration management package."""

from __future__ import annotations

from infrastructure.device.device_manager import (
    allocated_memory_bytes,
    empty_cache,
    get_device_telemetry,
    is_cuda_available,
    is_mps_available,
    resolve_optimal_device,
    synchronize,
)

__all__ = [
    "allocated_memory_bytes",
    "empty_cache",
    "get_device_telemetry",
    "is_cuda_available",
    "is_mps_available",
    "resolve_optimal_device",
    "synchronize",
]
