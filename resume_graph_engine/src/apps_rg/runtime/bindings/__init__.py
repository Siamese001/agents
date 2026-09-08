"""apps_rg runtime bindings."""
from __future__ import annotations

__all__ = [
    "APPS_RG_C0_CERT_REF",
    "c0_retrieve_apps_rg",
]


def __getattr__(name: str):
    """Load legacy package-level C0 exports without eager import cycles."""

    if name in __all__:
        from apps_rg.runtime.bindings import c0_binding

        return getattr(c0_binding, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
