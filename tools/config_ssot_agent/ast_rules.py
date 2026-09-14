"""AST visitors and violation detection rules for SSOT enforcement."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from .exemptions import ExemptionManager
from .registry import ConfigDomain, SSOTRegistry


class ViolationType(str, Enum):
    """Types of configuration SSOT violations."""

    HARDCODED_MODEL_LITERAL = "HARDCODED_MODEL_LITERAL"
    HARDCODED_TIMEOUT = "HARDCODED_TIMEOUT"
    HARDCODED_TOKEN_LIMIT = "HARDCODED_TOKEN_LIMIT"
    DIRECT_ENV_ACCESS = "DIRECT_ENV_ACCESS"
    DUPLICATE_CONFIG = "DUPLICATE_CONFIG"


class ViolationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class SSOTViolation:
    """Individual SSOT violation record."""

    file_path: str
    line: int
    column: int
    violation_type: ViolationType
    severity: ViolationSeverity
    detected_value: str
    message: str
    suggested_ssot: str
    rule_id: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "violation_type": self.violation_type.value,
            "severity": self.severity.value,
            "detected_value": self.detected_value,
            "message": self.message,
            "suggested_ssot": self.suggested_ssot,
            "rule_id": self.rule_id,
        }


class SSOTASTVisitor(ast.NodeVisitor):
    """AST visitor traversing Python source to flag SSOT configuration violations."""

    def __init__(
        self,
        file_path: Path | str,
        source_lines: Sequence[str],
        registry: SSOTRegistry,
        exemption_manager: ExemptionManager | None = None,
        exemption_mgr: ExemptionManager | None = None,
    ) -> None:
        self.file_path = file_path
        self.file_str = str(file_path).replace("\\", "/")
        self.source_lines = source_lines
        self.registry = registry
        self.exemption_mgr = exemption_manager or exemption_mgr or ExemptionManager()
        self.violations: list[SSOTViolation] = []
        self.is_bootstrap = self.exemption_mgr.is_bootstrap_owner(self.file_path)

    def _is_inline_exempt(self, line_no: int, rule_id: str) -> bool:
        if 1 <= line_no <= len(self.source_lines):
            line = self.source_lines[line_no - 1]
            return self.exemption_mgr.has_inline_exemption(line, rule_id)
        return False

    @staticmethod
    def _is_process_or_sync_timeout_call(node: ast.Call) -> bool:
        """Ignore timeouts on process execution or low-level locks (e.g. subprocess.run, sqlite3.connect)."""
        func = node.func
        if isinstance(func, ast.Attribute):
            attr = func.attr
            if attr in {"run", "call", "check_output", "Popen", "check_call"}:
                return True
            if attr == "connect" and isinstance(func.value, ast.Name) and "sqlite" in func.value.id.lower():
                return True
            if (
                attr in {"wait", "acquire"}
                and isinstance(func.value, ast.Name)
                and func.value.id in {"barrier", "lock", "event"}
            ):
                return True
        return False

    def visit_Constant(self, node: ast.Constant) -> None:
        """Inspect string constants for hardcoded model IDs."""
        if not self.is_bootstrap and isinstance(node.value, str):
            val = node.value.strip()
            if self.registry.is_known_model_literal(val):
                if not self._is_inline_exempt(node.lineno, ViolationType.HARDCODED_MODEL_LITERAL.value):
                    owner = self.registry.get_owner(ConfigDomain.MODEL_IDENTITY)
                    self.violations.append(
                        SSOTViolation(
                            file_path=self.file_str,
                            line=node.lineno,
                            column=node.col_offset + 1,
                            violation_type=ViolationType.HARDCODED_MODEL_LITERAL,
                            severity=ViolationSeverity.WARNING,
                            detected_value=val,
                            message=f"Hardcoded model literal '{val}' found outside model catalog SSOT.",
                            suggested_ssot=f"Resolve from {owner.owner_relative_path} via {owner.canonical_reader}()",
                            rule_id="SSOT001_HARDCODED_MODEL",
                        )
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Inspect function calls for raw os.environ access and hardcoded timeout/token limits."""
        # 1. Check for os.getenv("...") or os.environ.get("...")
        if not self.is_bootstrap:
            func_name = ""
            if isinstance(node.func, ast.Attribute) and node.func.attr == "getenv":
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                    func_name = "os.getenv"
            elif isinstance(node.func, ast.Name) and node.func.id == "getenv":
                func_name = "getenv"
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                val = node.func.value
                if isinstance(val, ast.Attribute) and val.attr == "environ":
                    if isinstance(val.value, ast.Name) and val.value.id == "os":
                        func_name = "os.environ.get"
                elif isinstance(val, ast.Name) and val.id == "environ":
                    func_name = "environ.get"

            if func_name:
                if not self._is_inline_exempt(node.lineno, ViolationType.DIRECT_ENV_ACCESS.value):
                    owner = self.registry.get_owner(ConfigDomain.ENVIRONMENT_NAMES)
                    env_arg = (
                        node.args[0].value
                        if (
                            node.args
                            and isinstance(node.args[0], ast.Constant)
                            and isinstance(node.args[0].value, str)
                        )
                        else "<dynamic>"
                    )
                    self.violations.append(
                        SSOTViolation(
                            file_path=self.file_str,
                            line=node.lineno,
                            column=node.col_offset + 1,
                            violation_type=ViolationType.DIRECT_ENV_ACCESS,
                            severity=ViolationSeverity.ERROR,
                            detected_value=f"{func_name}({env_arg!r})",
                            message=f"Direct environment read '{func_name}' bypasses canonical env bootstrap.",
                            suggested_ssot=f"Load via {owner.canonical_reader}() in {owner.owner_relative_path}",
                            rule_id="SSOT002_DIRECT_ENV_ACCESS",
                        )
                    )

        # 2. Check call keywords for hardcoded timeouts or max tokens
        for kw in node.keywords:
            arg = str(kw.arg or "")
            # Check timeout keywords
            if arg in {"timeout", "timeout_s", "timeout_seconds"}:
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
                    num_val = kw.value.value
                    if (
                        num_val > 0
                        and not self.is_bootstrap
                        and not self._is_process_or_sync_timeout_call(node)
                    ):
                        if not self._is_inline_exempt(kw.value.lineno, ViolationType.HARDCODED_TIMEOUT.value):
                            owner = self.registry.get_owner(ConfigDomain.RUNTIME_LIMITS)
                            self.violations.append(
                                SSOTViolation(
                                    file_path=self.file_str,
                                    line=kw.value.lineno,
                                    column=kw.value.col_offset + 1,
                                    violation_type=ViolationType.HARDCODED_TIMEOUT,
                                    severity=ViolationSeverity.WARNING,
                                    detected_value=f"{arg}={num_val}",
                                    message=f"Hardcoded timeout parameter '{arg}={num_val}' in call.",
                                    suggested_ssot=f"Read from {owner.owner_relative_path} via {owner.canonical_reader}()",
                                    rule_id="SSOT003_HARDCODED_TIMEOUT",
                                )
                            )

            # Check max token limits
            elif arg in {"max_tokens", "max_output_tokens", "max_completion_tokens"}:
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
                    tok_val = kw.value.value
                    if tok_val >= 512 and not self.is_bootstrap:
                        if not self._is_inline_exempt(
                            kw.value.lineno, ViolationType.HARDCODED_TOKEN_LIMIT.value
                        ):
                            owner = self.registry.get_owner(ConfigDomain.RUNTIME_LIMITS)
                            self.violations.append(
                                SSOTViolation(
                                    file_path=self.file_str,
                                    line=kw.value.lineno,
                                    column=kw.value.col_offset + 1,
                                    violation_type=ViolationType.HARDCODED_TOKEN_LIMIT,
                                    severity=ViolationSeverity.WARNING,
                                    detected_value=f"{arg}={tok_val}",
                                    message=f"Hardcoded token limit '{arg}={tok_val}' in call.",
                                    suggested_ssot=f"Read from {owner.owner_relative_path} via {owner.canonical_reader}()",
                                    rule_id="SSOT004_HARDCODED_TOKEN_LIMIT",
                                )
                            )

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Inspect subscripts for os.environ[...] loads."""
        if not self.is_bootstrap:
            is_environ = False
            # node.value is os.environ
            if isinstance(node.value, ast.Attribute) and node.value.attr == "environ":
                if isinstance(node.value.value, ast.Name) and node.value.value.id == "os":
                    is_environ = True
            elif isinstance(node.value, ast.Name) and node.value.id == "environ":
                is_environ = True

            if is_environ and isinstance(node.ctx, ast.Load):
                if not self._is_inline_exempt(node.lineno, ViolationType.DIRECT_ENV_ACCESS.value):
                    owner = self.registry.get_owner(ConfigDomain.ENVIRONMENT_NAMES)
                    key_val = (
                        node.slice.value
                        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)
                        else "<dynamic>"
                    )
                    self.violations.append(
                        SSOTViolation(
                            file_path=self.file_str,
                            line=node.lineno,
                            column=node.col_offset + 1,
                            violation_type=ViolationType.DIRECT_ENV_ACCESS,
                            severity=ViolationSeverity.ERROR,
                            detected_value=f"os.environ[{key_val!r}]",
                            message="Direct subscript access to 'os.environ' bypasses canonical env bootstrap.",
                            suggested_ssot=f"Load via {owner.canonical_reader}() in {owner.owner_relative_path}",
                            rule_id="SSOT002_DIRECT_ENV_ACCESS",
                        )
                    )

        self.generic_visit(node)
