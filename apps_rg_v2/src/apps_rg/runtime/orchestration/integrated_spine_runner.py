"""Apps RG boundary for the app-owned single-action spine runner."""

from __future__ import annotations

from typing import Any

from apps_rg.repository_layout import resolve_apps_rg_path
from apps_rg.runtime.orchestration.app_single_action_spine import (
    run_apps_rg_single_action_spine,
)


def _load_apps_rg_route_id() -> str:
    """Resolve the app route without relying on monorepo-shaped cwd lookup."""

    import yaml

    path = resolve_apps_rg_path(None, "config", "route_registry.yaml")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return ""
    routes = payload.get("routes") if isinstance(payload, dict) else None
    if not isinstance(routes, list):
        return ""
    candidates = [row for row in routes if isinstance(row, dict)]
    if not candidates:
        return ""

    def priority(row: dict[str, Any]) -> int:
        try:
            return int(row.get("priority", 9999))
        except (TypeError, ValueError):
            return 9999

    return str(min(candidates, key=priority).get("route_id") or "").strip()


def run_integrated_single_action_spine(*args: Any, **kwargs: Any) -> Any:
    """Run the app-owned integrated spine behind the stable public seam."""
    if (
        str(kwargs.get("app_name") or "") == "apps_rg"
        and not str(kwargs.get("route_id") or "").strip()
    ):
        route_id = _load_apps_rg_route_id()
        if route_id:
            kwargs["route_id"] = route_id
    from apps_rg.runtime.orchestration.canonical_identity_context import (
        canonical_run_identity_scope,
        current_canonical_run_identity,
    )

    raw_request = kwargs.get("raw_request")
    canonical_identity = (
        raw_request.get("canonical_run_identity")
        if isinstance(raw_request, dict)
        else None
    )
    if canonical_identity is None:
        canonical_identity = current_canonical_run_identity() or None
    with canonical_run_identity_scope(canonical_identity):
        return run_apps_rg_single_action_spine(*args, **kwargs)


__all__ = ["run_integrated_single_action_spine"]
