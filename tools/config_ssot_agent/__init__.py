"""Config SSOT Enforcement Agent.

Specialized static and dynamic analysis tool for detecting violations of Single
Source of Truth for configuration (hardcoded models/timeouts, duplicate variables,
and raw environment reads).
"""

from .ast_rules import SSOTViolation, ViolationSeverity, ViolationType
from .exemptions import ExemptionManager
from .registry import ConfigDomain, SSOTRegistry
from .reporter import SSOTReporter
from .scanner import ScanResult, ScanStats, SSOTScanner

ConfigSSOTScanner = SSOTScanner

__all__ = [
    "ConfigDomain",
    "ConfigSSOTScanner",
    "ExemptionManager",
    "SSOTRegistry",
    "SSOTReporter",
    "SSOTScanner",
    "SSOTViolation",
    "ScanResult",
    "ScanStats",
    "ViolationSeverity",
    "ViolationType",
]

__version__ = "1.0.0"
