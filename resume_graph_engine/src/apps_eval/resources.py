"""Resolve logical ``apps_eval/...`` resources in the standalone src layout."""

from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent


def resolve_apps_eval_resource(path: str | Path) -> Path:
    """Map a logical package-relative path to its standalone filesystem path.

    Registry values remain stable ``apps_eval/...`` identifiers so their
    digests do not depend on checkout layout. Absolute and caller-owned paths
    (for example pytest temporary directories) pass through unchanged.
    """

    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    parts = candidate.parts
    if parts and parts[0] == "apps_eval":
        return _PACKAGE_ROOT.joinpath(*parts[1:])
    return candidate
