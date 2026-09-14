"""Precision security gateway with zero-trust architecture."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .access_control import PrecisionAccessController
from .audit import PrecisionAuditLogger
from .compliance import PrecisionComplianceManager
from .crypto import PrecisionCryptographyManager
from .privacy import PrecisionPrivacyEngine
from .types import (
    PrecisionComplianceFramework,
    PrecisionSecurityContext,
    PrecisionSecurityLevel,
)


class PrecisionSecurityGateway:
    """Precision security gateway with zero-trust architecture."""

    def __init__(self) -> None:
        self.cryptography_manager = PrecisionCryptographyManager()
        self.access_controller = PrecisionAccessController()
        self.privacy_engine = PrecisionPrivacyEngine()
        self.audit_logger = PrecisionAuditLogger()
        self.compliance_manager = PrecisionComplianceManager()

        self.gateway_metrics = {
            "total_requests": 0,
            "authenticated_requests": 0,
            "authorized_requests": 0,
            "blocked_requests": 0,
        }

    async def authenticate_request(self, auth_data: dict[str, Any]) -> PrecisionSecurityContext | None:
        """Authenticate request with zero-trust principles."""
        try:
            # Extract authentication data
            user_id = auth_data.get("user_id")
            session_id = auth_data.get("session_id")
            token = auth_data.get("token")

            if not user_id or not session_id:
                return None

            # Validate token (simplified)
            if not token or len(token) < 32:
                return None

            # Get user roles and permissions
            user_roles = self.access_controller.user_roles.get(user_id, set())
            user_permissions = self.access_controller.get_user_permissions(user_id)

            # Determine security level based on authentication method
            security_level = PrecisionSecurityLevel.INTERNAL
            if auth_data.get("multi_factor", False):
                security_level = PrecisionSecurityLevel.CONFIDENTIAL
            if auth_data.get("hardware_token", False):
                security_level = PrecisionSecurityLevel.SECRET

            # Create security context
            context = PrecisionSecurityContext(
                user_id=user_id,
                session_id=session_id,
                roles=list(user_roles),
                permissions=list(user_permissions),
                security_level=security_level,
                region=auth_data.get("region", "unknown"),
                timestamp=datetime.now(),
                metadata=auth_data.get("metadata", {}),
            )

            # Verify context integrity
            if not context.verify_integrity():
                return None

            # Log authentication event
            self.audit_logger.log_event(
                event_type="authentication",
                user_id=user_id,
                session_id=session_id,
                action="authenticate",
                resource="security_gateway",
                outcome="success",
                details={"security_level": security_level.name},
            )

            self.gateway_metrics["authenticated_requests"] += 1
            return context

        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
            self.audit_logger.log_event(
                event_type="authentication_failure",
                user_id=auth_data.get("user_id", "unknown"),
                session_id=auth_data.get("session_id", "unknown"),
                action="authenticate",
                resource="security_gateway",
                outcome="failure",
                details={"error": str(e)},
            )
            return None

    async def authorize_request(
        self, context: PrecisionSecurityContext, resource: str, action: str
    ) -> tuple[bool, str]:
        """Authorize request using zero-trust access control."""
        try:
            # Check access using access controller
            authorized, reason = self.access_controller.check_access(context, resource, action)

            # Log authorization event
            self.audit_logger.log_event(
                event_type="authorization",
                user_id=context.user_id,
                session_id=context.session_id,
                action=action,
                resource=resource,
                outcome="granted" if authorized else "denied",
                details={"reason": reason, "security_level": context.security_level.name},
            )

            if authorized:
                self.gateway_metrics["authorized_requests"] += 1
            else:
                self.gateway_metrics["blocked_requests"] += 1

            return authorized, reason

        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as e:
            self.audit_logger.log_event(
                event_type="authorization_error",
                user_id=context.user_id,
                session_id=context.session_id,
                action=action,
                resource=resource,
                outcome="error",
                details={"error": str(e)},
            )
            return False, f"Authorization error: {e}"

    async def process_request(
        self, auth_data: dict[str, Any], resource: str, action: str, request_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Process request through complete security pipeline."""
        self.gateway_metrics["total_requests"] += 1

        # Step 1: Authentication
        context = await self.authenticate_request(auth_data)
        if not context:
            return {
                "success": False,
                "error": "Authentication failed",
                "stage": "authentication",
            }

        # Step 2: Authorization
        authorized, reason = await self.authorize_request(context, resource, action)
        if not authorized:
            return {
                "success": False,
                "error": f"Authorization failed: {reason}",
                "stage": "authorization",
            }

        # Step 3: Privacy processing
        processed_data = self.privacy_engine.mask_data(
            request_data,
            request_data.get("field_types", {}),
        )

        # Step 4: Compliance check
        compliance_result = self.compliance_manager.check_compliance(
            PrecisionComplianceFramework.GDPR,
            {
                "data_fields_count": len(processed_data),
                "encryption_enabled": True,
                "access_controls": {"implemented": True},
                "audit_logging": {"enabled": True},
            },
        )

        # Step 5: Return success with processed data
        return {
            "success": True,
            "context": {
                "user_id": context.user_id,
                "security_level": context.security_level.name,
                "roles": context.roles,
            },
            "processed_data": processed_data,
            "compliance": compliance_result,
            "stage": "completed",
        }

    def get_gateway_status(self) -> dict[str, Any]:
        """Get comprehensive gateway status."""
        return {
            "metrics": self.gateway_metrics,
            "cryptography": self.cryptography_manager.get_cryptography_metrics(),
            "access_control": self.access_controller.get_access_metrics(),
            "privacy": self.privacy_engine.get_privacy_metrics(),
            "audit": self.audit_logger.get_audit_metrics(),
            "compliance": self.compliance_manager.get_compliance_summary(),
        }


__all__ = ["PrecisionSecurityGateway"]
