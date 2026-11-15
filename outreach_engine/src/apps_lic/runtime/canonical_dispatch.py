"""Pure re-export facade for canonical dispatch on the 10-stage spine."""

from __future__ import annotations

from apps_lic.runtime.dispatch.canonical_dispatch import (
    build_cli_ingress_raw,
    run_canonical_apps_lic_spine,
)

__all__ = [
    "build_cli_ingress_raw",
    "run_canonical_apps_lic_spine",
]
