"""Precision privacy engine with advanced data masking and anonymization."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from typing import Any, Callable


class PrecisionPrivacyEngine:
    """Precision privacy engine with advanced data masking and anonymization."""

    def __init__(self) -> None:
        self.masking_rules: dict[str, Callable[[str], str]] = {}
        self.anonymization_strategies: dict[str, Callable] = {}
        self.privacy_metrics = {
            "data_masked": 0,
            "data_anonymized": 0,
            "privacy_violations": 0,
        }

        # Initialize default masking rules
        self._initialize_masking_rules()

    def _initialize_masking_rules(self) -> None:
        """Initialize default data masking rules."""
        self.masking_rules = {
            "email": lambda x: x[:2] + "***@" + x.split("@")[1] if "@" in x else "***",
            "phone": lambda x: "***-" + x[-4:] if len(x) > 7 else "***",
            "ssn": lambda x: "***-**-" + x[-4:] if len(x) == 9 else "***",
            "credit_card": lambda x: "****-****-****-" + x[-4:] if len(x) == 16 else "***",
            "ip_address": lambda x: x[:3] + "***" if "." in x else "***",
            "name": lambda x: x[0] + "***" + x[-1] if len(x) > 2 else "***",
        }

    def mask_data(self, data: dict[str, Any], field_types: dict[str, str]) -> dict[str, Any]:
        """Mask sensitive data based on field types."""
        masked_data = data.copy()

        for field, field_type in field_types.items():
            if field in masked_data and field_type in self.masking_rules:
                original_value = str(masked_data[field])
                masked_value = self.masking_rules[field_type](original_value)
                masked_data[field] = masked_value
                self.privacy_metrics["data_masked"] += 1

        return masked_data

    def anonymize_data(self, data: dict[str, Any], identifiers: list[str]) -> dict[str, Any]:
        """Anonymize data by removing or hashing identifiers."""
        anonymized_data = data.copy()

        for identifier in identifiers:
            if identifier in anonymized_data:
                # Hash the identifier with salt
                salt = secrets.token_bytes(32)
                value = str(anonymized_data[identifier]).encode()
                hashed_value = hashlib.pbkdf2_hmac("sha256", value, salt, 100000)
                anonymized_data[identifier] = base64.b64encode(hashed_value).decode()
                self.privacy_metrics["data_anonymized"] += 1

        return anonymized_data

    def detect_pii(self, text: str) -> list[str]:
        """Detect personally identifiable information in text."""
        pii_types = []

        # Email detection
        if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text):
            pii_types.append("email")

        # Phone detection
        if re.search(r"\b\d{3}-\d{3}-\d{4}\b", text):
            pii_types.append("phone")

        # SSN detection
        if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text):
            pii_types.append("ssn")

        # Credit card detection
        if re.search(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", text):
            pii_types.append("credit_card")

        return pii_types

    def get_privacy_metrics(self) -> dict[str, Any]:
        """Get privacy engine metrics."""
        return {
            "masking_rules": len(self.masking_rules),
            "metrics": self.privacy_metrics,
            "supported_pii_types": list(self.masking_rules.keys()),
        }


__all__ = ["PrecisionPrivacyEngine"]
