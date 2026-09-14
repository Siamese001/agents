"""Precise security types, enums, contexts, and log records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PrecisionSecurityLevel(Enum):
    """Precise security level enumeration with mathematical ordering."""

    PUBLIC = 1
    INTERNAL = 2
    CONFIDENTIAL = 3
    SECRET = 4
    TOP_SECRET = 5

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PrecisionSecurityLevel):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: object) -> bool:
        if not isinstance(other, PrecisionSecurityLevel):
            return NotImplemented
        return self.value <= other.value


class PrecisionComplianceFramework(Enum):
    """Precise compliance framework enumeration."""

    GDPR = 1
    HIPAA = 2
    SOX = 3
    PCI_DSS = 4
    ISO_27001 = 5
    NIST_CSF = 6

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PrecisionComplianceFramework):
            return NotImplemented
        return self.value < other.value


class PrecisionDataClassification(Enum):
    """Precise data classification with total ordering."""

    PUBLIC_DATA = 1
    INTERNAL_DATA = 2
    SENSITIVE_DATA = 3
    RESTRICTED_DATA = 4
    CRITICAL_DATA = 5

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PrecisionDataClassification):
            return NotImplemented
        return self.value < other.value


@dataclass(frozen=True)
class PrecisionSecurityContext:
    """Immutable security context with cryptographic integrity."""

    user_id: str
    session_id: str
    roles: list[str]
    permissions: list[str]
    security_level: PrecisionSecurityLevel
    region: str
    timestamp: datetime
    checksum: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate required fields
        if not self.user_id or not isinstance(self.user_id, str):
            raise ValueError("user_id must be non-empty string")
        if not self.session_id or not isinstance(self.session_id, str):
            raise ValueError("session_id must be non-empty string")
        if not isinstance(self.roles, list):
            raise ValueError("roles must be a list")
        if not isinstance(self.permissions, list):
            raise ValueError("permissions must be a list")

        # Generate deterministic checksum
        content = json.dumps(
            {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "roles": sorted(self.roles),
                "permissions": sorted(self.permissions),
                "security_level": self.security_level.value,
                "region": self.region,
                "timestamp": self.timestamp.isoformat(),
                "metadata": self.metadata,
            },
            sort_keys=True,
        )
        checksum = hashlib.sha256(content.encode()).hexdigest()
        object.__setattr__(self, "checksum", checksum)

    def verify_integrity(self) -> bool:
        """Verify cryptographic integrity."""
        content = json.dumps(
            {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "roles": sorted(self.roles),
                "permissions": sorted(self.permissions),
                "security_level": self.security_level.value,
                "region": self.region,
                "timestamp": self.timestamp.isoformat(),
                "metadata": self.metadata,
            },
            sort_keys=True,
        )
        expected = hashlib.sha256(content.encode()).hexdigest()
        return self.checksum == expected

    def has_permission(self, permission: str) -> bool:
        """Check if context has specific permission."""
        return permission in self.permissions

    def has_role(self, role: str) -> bool:
        """Check if context has specific role."""
        return role in self.roles

    def meets_security_level(self, required_level: PrecisionSecurityLevel) -> bool:
        """Check if context meets required security level."""
        return self.security_level.value >= required_level.value


@dataclass
class PrecisionAuditLog:
    """Precision audit log with cryptographic chain of custody."""

    log_id: str
    timestamp: datetime
    event_type: str
    user_id: str
    session_id: str
    action: str
    resource: str
    outcome: str
    details: dict[str, Any]
    previous_log_hash: str = ""
    log_hash: str = ""
    signature: str = ""

    def __post_init__(self) -> None:
        # Generate log hash
        content = json.dumps(
            {
                "log_id": self.log_id,
                "timestamp": self.timestamp.isoformat(),
                "event_type": self.event_type,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "action": self.action,
                "resource": self.resource,
                "outcome": self.outcome,
                "details": self.details,
                "previous_log_hash": self.previous_log_hash,
            },
            sort_keys=True,
            default=str,
        )
        self.log_hash = hashlib.sha256(content.encode()).hexdigest()

    def verify_chain_integrity(self, previous_hash: str) -> bool:
        """Verify chain integrity with previous log."""
        return self.previous_log_hash == previous_hash


__all__ = [
    "PrecisionSecurityLevel",
    "PrecisionComplianceFramework",
    "PrecisionDataClassification",
    "PrecisionSecurityContext",
    "PrecisionAuditLog",
]
