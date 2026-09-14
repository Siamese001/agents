"""File system scanner and orchestrator for SSOT violation detection."""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

from .ast_rules import SSOTASTVisitor, SSOTViolation
from .exemptions import ExemptionManager
from .registry import SSOTRegistry


@dataclass
class ScanStats:
    """Statistics summarizing an SSOT scan run."""

    files_scanned: int = 0
    files_skipped: int = 0
    files_with_violations: int = 0
    total_violations: int = 0
    duration_seconds: float = 0.0
    parse_errors: int = 0


@dataclass
class ScanResult:
    """Comprehensive result of an SSOT scan."""

    violations: list[SSOTViolation] = field(default_factory=list)
    stats: ScanStats = field(default_factory=ScanStats)
    scanned_paths: list[str] = field(default_factory=list)

    def violations_by_type(self) -> dict[str, list[SSOTViolation]]:
        grouped: dict[str, list[SSOTViolation]] = {}
        for v in self.violations:
            grouped.setdefault(v.violation_type.value, []).append(v)
        return grouped

    def violations_by_file(self) -> dict[str, list[SSOTViolation]]:
        grouped: dict[str, list[SSOTViolation]] = {}
        for v in self.violations:
            grouped.setdefault(v.file_path, []).append(v)
        return grouped


class SSOTScanner:
    """Scans Python files across directory trees to enforce SSOT configuration."""

    def __init__(
        self,
        registry: SSOTRegistry | None = None,
        exemption_manager: ExemptionManager | None = None,
    ) -> None:
        self.registry = registry or SSOTRegistry()
        self.exemption_manager = exemption_manager or ExemptionManager()

    def _discover_python_files(self, target_path: Path) -> Iterator[Path]:
        """Yield all .py files under target_path, ignoring common noise dirs."""
        ignored_dir_names = {
            ".git",
            ".venv",
            "venv",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".antigravity",
            "build",
            "dist",
            "node_modules",
            ".tox",
        }

        if target_path.is_file():
            if target_path.suffix == ".py":
                yield target_path
            return

        for path in target_path.rglob("*.py"):
            parts = set(path.parts)
            if ignored_dir_names.intersection(parts):
                continue
            yield path

    def scan_file(self, file_path: Path) -> list[SSOTViolation]:
        """Scan a single Python file for SSOT violations."""
        if self.exemption_manager.is_path_exempt(file_path):
            return []

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []

        lines = content.splitlines()

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return []

        visitor = SSOTASTVisitor(
            file_path=file_path,
            source_lines=lines,
            registry=self.registry,
            exemption_manager=self.exemption_manager,
        )
        visitor.visit(tree)
        return visitor.violations

    def scan(self, target_paths: Sequence[Path | str]) -> ScanResult:
        """Scan a sequence of paths (files or directories)."""
        start_time = time.perf_counter()
        stats = ScanStats()
        all_violations: list[SSOTViolation] = []
        scanned_files: list[str] = []
        files_with_issues: set[str] = set()

        for raw_path in target_paths:
            path = Path(raw_path).resolve()
            if not path.exists():
                continue

            for py_file in self._discover_python_files(path):
                if self.exemption_manager.is_path_exempt(py_file):
                    stats.files_skipped += 1
                    continue

                stats.files_scanned += 1
                scanned_files.append(str(py_file))

                violations = self.scan_file(py_file)
                if violations:
                    files_with_issues.add(str(py_file))
                    all_violations.extend(violations)

        stats.duration_seconds = time.perf_counter() - start_time
        stats.total_violations = len(all_violations)
        stats.files_with_violations = len(files_with_issues)

        return ScanResult(
            violations=all_violations,
            stats=stats,
            scanned_paths=scanned_files,
        )
