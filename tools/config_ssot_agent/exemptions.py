"""Exemption rules and path filters for the Config SSOT Enforcement Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

DEFAULT_EXEMPT_PATH_SUBSTRINGS: tuple[str, ...] = (
    "/tests/",
    "tests/",
    "/.venv/",
    ".venv/",
    "/artifacts/",
    "artifacts/",
    "/docs/",
    "docs/",
    "tools/config_ssot_agent/",
    ".git/",
)

# Files that legitimately define or bootstrap configuration
CANONICAL_BOOTSTRAP_FILES: tuple[str, ...] = (
    "env_bootstrap.py",
    "model_capabilities.py",
    "model_pin_ownership.py",
    "section_model_limits.py",
    "section_judge_policy.py",
    "credentials.py",
)


class ExemptionManager:
    """Evaluates whether a file or code location is exempt from SSOT rules."""

    def __init__(
        self,
        exempt_path_substrings: Sequence[str] | None = None,
        bootstrap_files: Sequence[str] | None = None,
    ) -> None:
        self.exempt_path_substrings = tuple(exempt_path_substrings or DEFAULT_EXEMPT_PATH_SUBSTRINGS)
        self.bootstrap_files = tuple(bootstrap_files or CANONICAL_BOOTSTRAP_FILES)

    def is_file_exempt(self, path: Path | str) -> bool:
        norm = str(path).replace("\\", "/")
        for sub in self.exempt_path_substrings:
            if sub in norm:
                return True
        return False

    is_path_exempt = is_file_exempt

    def is_bootstrap_owner(self, path: Path | str) -> bool:
        norm = str(path).replace("\\", "/")
        for bf in self.bootstrap_files:
            if norm.endswith(bf) or f"/{bf}" in norm:
                return True
        return False

    def has_inline_exemption(self, line: str, rule_id: str | None = None) -> bool:
        comment_idx = line.find("#")
        if comment_idx == -1:
            return False
        comment = line[comment_idx:].lower()
        if "ssot-exempt" in comment or "ssot: exempt" in comment or "ssot:exempt" in comment:
            if rule_id is None:
                return True
            rule_lower = rule_id.lower()
            return rule_lower in comment or "all" in comment
        if "noqa: ssot" in comment:
            return True
        return False

    def is_line_exempt(self, line: str, violation_type: Any = None) -> bool:
        rule_str = str(getattr(violation_type, "value", violation_type or ""))
        return self.has_inline_exemption(line, rule_str)
