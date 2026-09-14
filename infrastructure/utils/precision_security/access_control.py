"""Precision access controller with zero-trust principles."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from .types import (
    PrecisionDataClassification,
    PrecisionSecurityContext,
    PrecisionSecurityLevel,
)

logger = logging.getLogger(__name__)


class PrecisionAccessController:
    """Precision access controller with zero-trust principles."""

    def __init__(self) -> None:
        self.role_permissions: dict[str, set[str]] = {}
        self.user_roles: dict[str, set[str]] = {}
        self.resource_policies: dict[str, dict[str, Any]] = {}
        self.access_logs: list[dict[str, Any]] = []
        self.access_metrics = {
            "access_requests": 0,
            "access_granted": 0,
            "access_denied": 0,
            "policy_violations": 0,
        }

        # Initialize default roles and permissions
        self._initialize_default_policies()

    def _initialize_default_policies(self) -> None:
        """Initialize default security policies."""
        # Define roles and their permissions
        self.role_permissions = {
            "admin": {
                "read",
                "write",
                "delete",
                "manage_users",
                "manage_policies",
                "view_audit_logs",
                "system_config",
                "encrypt_data",
                "decrypt_data",
            },
            "developer": {
                "read",
                "write",
                "deploy",
                "view_logs",
                "encrypt_data",
                "decrypt_data",
            },
            "analyst": {
                "read",
                "view_reports",
                "export_data",
                "decrypt_data",
            },
            "user": {
                "read",
                "view_own_data",
            },
            "auditor": {
                "read",
                "view_audit_logs",
                "export_audit_logs",
            },
        }

        # Define resource policies
        self.resource_policies = {
            "user_data": {
                "required_permissions": ["read"],
                "security_level": PrecisionSecurityLevel.CONFIDENTIAL,
                "data_classification": PrecisionDataClassification.SENSITIVE_DATA,
            },
            "system_config": {
                "required_permissions": ["manage_policies"],
                "security_level": PrecisionSecurityLevel.SECRET,
                "data_classification": PrecisionDataClassification.RESTRICTED_DATA,
            },
            "audit_logs": {
                "required_permissions": ["view_audit_logs"],
                "security_level": PrecisionSecurityLevel.SECRET,
                "data_classification": PrecisionDataClassification.RESTRICTED_DATA,
            },
            "encryption_keys": {
                "required_permissions": ["encrypt_data", "decrypt_data"],
                "security_level": PrecisionSecurityLevel.TOP_SECRET,
                "data_classification": PrecisionDataClassification.CRITICAL_DATA,
            },
        }

    def assign_role(self, user_id: str, role: str) -> bool:
        """Assign role to user."""
        if role not in self.role_permissions:
            logger.warning(f"Unknown role: {role}")
            return False

        if user_id not in self.user_roles:
            self.user_roles[user_id] = set()

        self.user_roles[user_id].add(role)
        logger.info(f"Assigned role {role} to user {user_id}")
        return True

    def revoke_role(self, user_id: str, role: str) -> bool:
        """Revoke role from user."""
        if user_id in self.user_roles and role in self.user_roles[user_id]:
            self.user_roles[user_id].remove(role)
            logger.info(f"Revoked role {role} from user {user_id}")
            return True
        return False

    def check_access(self, context: PrecisionSecurityContext, resource: str, action: str) -> tuple[bool, str]:
        """Check access using zero-trust principles."""
        self.access_metrics["access_requests"] += 1

        access_log = {
            "timestamp": datetime.now().isoformat(),
            "user_id": context.user_id,
            "resource": resource,
            "action": action,
            "outcome": "denied",
            "reason": "",
        }

        try:
            # Check if resource exists
            if resource not in self.resource_policies:
                access_log["reason"] = "Resource not found"
                self.access_metrics["access_denied"] += 1
                self.access_logs.append(access_log)
                return False, "Resource not found"

            policy = self.resource_policies[resource]

            # Check security level requirements
            if not context.meets_security_level(policy["security_level"]):
                access_log["reason"] = (
                    f"Insufficient security level. Required: {policy['security_level'].name}"
                )
                self.access_metrics["access_denied"] += 1
                self.access_logs.append(access_log)
                return False, "Insufficient security level"

            # Check required permissions
            required_permissions = set(policy["required_permissions"])
            user_permissions = set(context.permissions)

            # Add role-based permissions
            for role in context.roles:
                if role in self.role_permissions:
                    user_permissions.update(self.role_permissions[role])

            if not required_permissions.issubset(user_permissions):
                missing_perms = required_permissions - user_permissions
                access_log["reason"] = f"Missing permissions: {missing_perms}"
                self.access_metrics["access_denied"] += 1
                self.access_logs.append(access_log)
                return False, f"Missing permissions: {missing_perms}"

            # Access granted
            access_log["outcome"] = "granted"
            self.access_metrics["access_granted"] += 1
            self.access_logs.append(access_log)

            return True, "Access granted"

        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
            access_log["reason"] = f"Access check error: {e}"
            self.access_metrics["access_denied"] += 1
            self.access_logs.append(access_log)
            return False, f"Access check error: {e}"

    def get_user_permissions(self, user_id: str) -> set[str]:
        """Get all permissions for user."""
        permissions = set()

        if user_id in self.user_roles:
            for role in self.user_roles[user_id]:
                if role in self.role_permissions:
                    permissions.update(self.role_permissions[role])

        return permissions

    def get_access_metrics(self) -> dict[str, Any]:
        """Get access control metrics."""
        total_requests = self.access_metrics["access_requests"]
        grant_rate = self.access_metrics["access_granted"] / max(1, total_requests)

        return {
            "total_users": len(self.user_roles),
            "total_roles": len(self.role_permissions),
            "total_resources": len(self.resource_policies),
            "metrics": self.access_metrics,
            "grant_rate": grant_rate,
            "recent_access_logs": len(
                [
                    log
                    for log in self.access_logs
                    if datetime.fromisoformat(log["timestamp"]) > datetime.now() - timedelta(hours=1)
                ]
            ),
        }


__all__ = ["PrecisionAccessController"]
