"""Concurrency-safe propagation of the committed fresh-E2E run identity.

The pinned core intentionally projects only generic recipe fields.  The
application still needs the producer/consumer identity at each nested section
lane so its runtime-exhaust and L6 evidence can be bound to the product run.
This module provides that app-owned dynamic boundary without modifying core or
recovering authority from mutable files.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_REQUIRED_FIELDS = frozenset(
    {
        "producer_app_id",
        "consumer_app_id",
        "parent_run_id",
        "child_run_id",
        "request_id",
        "trace_root",
        "tenant_id",
        "target_company",
        "target_role",
        "jd_sha256",
        "brief_sha256",
        "policy_hash",
        "blueprint_hash",
        "schema_version",
    }
)
_DIGEST_FIELDS = ("jd_sha256", "brief_sha256", "policy_hash", "blueprint_hash")
_CURRENT_CANONICAL_IDENTITY: ContextVar[dict[str, Any] | None] = ContextVar(
    "apps_rg_current_canonical_run_identity",
    default=None,
)


def validate_canonical_run_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Return an isolated identity copy or raise on an untrusted projection."""

    missing = sorted(
        field for field in _REQUIRED_FIELDS if not str(identity.get(field) or "").strip()
    )
    if missing:
        raise ValueError("canonical run identity is incomplete: " + ", ".join(missing))
    if identity.get("schema_version") != "apps_research_rg_run_identity.v1":
        raise ValueError("canonical run identity schema_version is invalid")
    if identity.get("producer_app_id") != "apps_research":
        raise ValueError("canonical run identity producer_app_id is invalid")
    if identity.get("consumer_app_id") != "apps_rg":
        raise ValueError("canonical run identity consumer_app_id is invalid")
    for field in _DIGEST_FIELDS:
        value = str(identity.get(field) or "")
        if len(value) != 71 or not value.startswith("sha256:"):
            raise ValueError(f"canonical run identity {field} is not sha256-bound")
        try:
            int(value[7:], 16)
        except ValueError as exc:
            raise ValueError(
                f"canonical run identity {field} is not sha256-bound"
            ) from exc
    return dict(identity)


@contextmanager
def canonical_run_identity_scope(
    identity: Mapping[str, Any] | None,
) -> Iterator[None]:
    """Expose a validated identity only during the nested core callback."""

    normalized = None if identity is None else validate_canonical_run_identity(identity)
    token = _CURRENT_CANONICAL_IDENTITY.set(normalized)
    try:
        yield
    finally:
        _CURRENT_CANONICAL_IDENTITY.reset(token)


def current_canonical_run_identity() -> dict[str, Any]:
    """Return an isolated copy of the dynamically bound identity, if any."""

    identity = _CURRENT_CANONICAL_IDENTITY.get()
    return dict(identity) if identity is not None else {}


def canonical_identity_for_recipe_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve explicit recipe identity first, then the app-owned core boundary."""

    explicit = context.get("canonical_run_identity")
    if isinstance(explicit, Mapping):
        return validate_canonical_run_identity(explicit)
    return current_canonical_run_identity()


__all__ = [
    "canonical_identity_for_recipe_context",
    "canonical_run_identity_scope",
    "current_canonical_run_identity",
    "validate_canonical_run_identity",
]
