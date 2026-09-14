"""Typed Persistence Exceptions for Sovereign Agentic Platform.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
"""

from __future__ import annotations


class PersistenceError(Exception):
    """Base exception for all persistence layer errors."""


class RecordNotFoundError(PersistenceError):
    """Raised when a requested run state, checkpoint, or event is not found."""


class ConcurrencyError(PersistenceError):
    """Raised when an optimistic concurrency check fails on write."""


class TamperDetectionError(PersistenceError):
    """Raised when cryptographic verification detects altered data or broken chains."""
