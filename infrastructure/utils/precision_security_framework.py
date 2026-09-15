"""Phase D Reimplementation: Advanced Security and Compliance with Zero-Trust Architecture.

Backwards-compatibility facade re-exporting modular components from
infrastructure.utils.precision_security.
"""

from __future__ import annotations

from infrastructure.utils.precision_security import (
    PrecisionAccessController,
    PrecisionAuditLog,
    PrecisionAuditLogger,
    PrecisionComplianceFramework,
    PrecisionComplianceManager,
    PrecisionCryptographyManager,
    PrecisionDataClassification,
    PrecisionPrivacyEngine,
    PrecisionSecurityContext,
    PrecisionSecurityGateway,
    PrecisionSecurityLevel,
)

__all__ = [
    "PrecisionSecurityLevel",
    "PrecisionComplianceFramework",
    "PrecisionDataClassification",
    "PrecisionSecurityContext",
    "PrecisionAuditLog",
    "PrecisionCryptographyManager",
    "PrecisionAccessController",
    "PrecisionPrivacyEngine",
    "PrecisionAuditLogger",
    "PrecisionComplianceManager",
    "PrecisionSecurityGateway",
]
