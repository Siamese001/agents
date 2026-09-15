"""Unit tests verifying modularization and facade parity of the precision security framework."""

from __future__ import annotations

from datetime import datetime
import pytest

# Test import from original facade
from infrastructure.utils import precision_security_framework as facade
# Test import from new modular package
from infrastructure.utils import precision_security as modular


def test_facade_import_parity():
    """Verify that all 11 classes exported by the facade match the modular package exactly."""
    expected_symbols = [
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

    for symbol in expected_symbols:
        assert hasattr(facade, symbol), f"Facade missing {symbol}"
        assert hasattr(modular, symbol), f"Modular package missing {symbol}"
        facade_obj = getattr(facade, symbol)
        modular_obj = getattr(modular, symbol)
        assert facade_obj is modular_obj, f"Object mismatch for {symbol}: facade and modular are not identical"


def test_cryptography_manager_roundtrip():
    """Verify symmetric and asymmetric cryptographic operations."""
    mgr = facade.PrecisionCryptographyManager()

    # 1. Symmetric AES-GCM
    key_id = mgr.generate_symmetric_key("sym_test_key", 256)
    plaintext = b"Sensitive production payload data"
    ciphertext, tag = mgr.encrypt_symmetric(key_id, plaintext)
    decrypted = mgr.decrypt_symmetric(key_id, ciphertext, tag)
    assert decrypted == plaintext

    # 2. Asymmetric RSA-OAEP
    asym_id = mgr.generate_asymmetric_key_pair("asym_test_key", 2048)
    asym_cipher = mgr.encrypt_asymmetric(asym_id, plaintext)
    asym_decrypted = mgr.decrypt_asymmetric(asym_id, asym_cipher)
    assert asym_decrypted == plaintext

    metrics = mgr.get_cryptography_metrics()
    assert metrics["metrics"]["encryptions"] == 2
    assert metrics["metrics"]["decryptions"] == 2


def test_access_controller():
    """Verify zero-trust RBAC access controls."""
    controller = facade.PrecisionAccessController()
    user_id = "agent_operator_001"

    assert controller.assign_role(user_id, "developer")
    permissions = controller.get_user_permissions(user_id)
    assert "deploy" in permissions
    assert "read" in permissions

    ctx = facade.PrecisionSecurityContext(
        user_id=user_id,
        session_id="sess_123456",
        roles=["developer"],
        permissions=list(permissions),
        security_level=facade.PrecisionSecurityLevel.CONFIDENTIAL,
        region="us-east-1",
        timestamp=datetime.now(),
    )
    assert ctx.verify_integrity()

    # User data requires CONFIDENTIAL and read permission
    allowed, reason = controller.check_access(ctx, "user_data", "read")
    assert allowed
    assert reason == "Access granted"

    # Revoke role and verify permissions change
    assert controller.revoke_role(user_id, "developer")
    assert "deploy" not in controller.get_user_permissions(user_id)


def test_privacy_engine():
    """Verify data masking, anonymization, and PII detection."""
    engine = facade.PrecisionPrivacyEngine()

    raw_payload = {
        "email": "agent.smith@example.com",
        "phone": "555-123-4567",
        "account_id": "acc_987654",
    }
    field_types = {
        "email": "email",
        "phone": "phone",
    }

    masked = engine.mask_data(raw_payload, field_types)
    assert masked["email"].startswith("ag***@")
    assert masked["phone"] == "***-4567"
    assert masked["account_id"] == "acc_987654"

    anonymized = engine.anonymize_data(raw_payload, ["account_id"])
    assert anonymized["account_id"] != "acc_987654"

    detected_pii = engine.detect_pii("Contact me at user@testcorp.org or call 555-123-4567.")
    assert "email" in detected_pii
    assert "phone" in detected_pii


def test_audit_logger_chain_integrity():
    """Verify cryptographic hash chaining in audit logging."""
    logger = facade.PrecisionAuditLogger()

    log1_id = logger.log_event(
        event_type="access",
        user_id="user_1",
        session_id="sess_1",
        action="read",
        resource="res_1",
        outcome="granted",
    )
    log2_id = logger.log_event(
        event_type="access",
        user_id="user_2",
        session_id="sess_2",
        action="write",
        resource="res_2",
        outcome="granted",
    )

    assert log1_id.startswith("audit_")
    assert log2_id.startswith("audit_")
    assert logger.verify_audit_chain()

    logs = logger.query_logs({"user_id": "user_1"})
    assert len(logs) == 1
    assert logs[0].user_id == "user_1"


def test_compliance_manager():
    """Verify regulatory compliance checks and violation resolution."""
    mgr = facade.PrecisionComplianceManager()

    system_data_pass = {
        "data_fields_count": 10,
        "encryption_enabled": True,
        "access_controls": {"implemented": True},
        "audit_logging": {"enabled": True},
    }

    result = mgr.check_compliance(facade.PrecisionComplianceFramework.GDPR, system_data_pass)
    assert result["overall_compliant"]
    assert result["score"] > 0.0

    # Test violation tracking
    system_data_fail = {
        "data_fields_count": 50,  # Excessive
        "encryption_enabled": False,  # Missing encryption
        "access_controls": {"implemented": False},
        "audit_logging": {"enabled": False},
    }

    fail_result = mgr.check_compliance(facade.PrecisionComplianceFramework.GDPR, system_data_fail)
    assert not fail_result["overall_compliant"]
    assert len(fail_result["requirements_violated"]) > 0


import asyncio


def test_security_gateway_pipeline():
    """Verify end-to-end request processing through the security gateway."""
    gateway = facade.PrecisionSecurityGateway()

    # Pre-configure user role so permissions resolve
    gateway.access_controller.assign_role("agent_user", "developer")

    auth_data = {
        "user_id": "agent_user",
        "session_id": "session_999",
        "token": "a" * 32,  # 32-char token
        "multi_factor": True,
        "region": "us-west-2",
    }

    request_payload = {
        "email": "developer@corp.local",
        "code_snippet": "print('hello')",
        "field_types": {"email": "email"},
    }

    result = asyncio.run(
        gateway.process_request(
            auth_data=auth_data,
            resource="user_data",
            action="read",
            request_data=request_payload,
        )
    )

    assert result["success"]
    assert result["stage"] == "completed"
    assert result["context"]["user_id"] == "agent_user"
    assert result["processed_data"]["email"].startswith("de***@")

