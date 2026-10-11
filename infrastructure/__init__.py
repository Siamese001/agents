"""Infrastructure package - system hardening and cross-cutting optimization modules."""

from __future__ import annotations


def emit_package_boot_telemetry() -> None:
    """Emit package boot telemetry explicitly instead of at import time."""
    # Package boot telemetry hook point (no-op)


__all__ = ["emit_package_boot_telemetry"]

