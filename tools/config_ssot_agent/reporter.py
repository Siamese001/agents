"""Reporters for formatting and exporting SSOT violation findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .scanner import ScanResult


class SSOTReporter:
    """Formats and exports scan results into JSON, Markdown, and text."""

    def __init__(self, result: ScanResult) -> None:
        self.result = result

    def to_dict(self) -> dict[str, Any]:
        """Convert entire scan result to a dictionary representation."""
        return {
            "stats": {
                "files_scanned": self.result.stats.files_scanned,
                "files_skipped": self.result.stats.files_skipped,
                "files_with_violations": self.result.stats.files_with_violations,
                "total_violations": self.result.stats.total_violations,
                "duration_seconds": round(self.result.stats.duration_seconds, 3),
                "parse_errors": self.result.stats.parse_errors,
            },
            "violations_by_type": {k: len(v) for k, v in self.result.violations_by_type().items()},
            "violations": [v.to_dict() for v in self.result.violations],
        }

    def write_json(self, output_path: Path | str) -> None:
        """Write scan results to a formatted JSON file."""
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def to_markdown(self) -> str:
        """Render a clean GitHub markdown report of the violations."""
        stats = self.result.stats
        by_type = self.result.violations_by_type()
        by_file = self.result.violations_by_file()

        lines: list[str] = [
            "# Config SSOT Violation Scan Report",
            "",
            "## Summary",
            "",
            f"- **Files Scanned**: {stats.files_scanned}",
            f"- **Files Skipped (Exempt)**: {stats.files_skipped}",
            f"- **Files With Violations**: {stats.files_with_violations}",
            f"- **Total Violations Detected**: {stats.total_violations}",
            f"- **Scan Duration**: {stats.duration_seconds:.2f}s",
            "",
            "### Violations by Type",
            "",
            "| Violation Type | Count | Severity | Suggested SSOT Remediation |",
            "|---|---|---|---|",
        ]

        for vtype, viols in sorted(by_type.items(), key=lambda item: len(item[1]), reverse=True):
            sample = viols[0]
            lines.append(
                f"| `{vtype}` | {len(viols)} | `{sample.severity.value}` | `{sample.suggested_ssot}` |"
            )

        lines.extend(
            [
                "",
                "## Violations by File",
                "",
            ]
        )

        for fpath, viols in sorted(by_file.items()):
            lines.append(f"### `{fpath}` ({len(viols)} violations)")
            lines.append("")
            lines.append("| Line:Col | Type | Value | Rule ID | Suggested SSOT |")
            lines.append("|---|---|---|---|---|")
            for v in viols:
                val_repr = v.detected_value.replace("\n", " ")[:30]
                lines.append(
                    f"| L{v.line}:{v.column} | `{v.violation_type.value}` | `{val_repr}` | `{v.rule_id}` | `{v.suggested_ssot}` |"
                )
            lines.append("")

        return "\n".join(lines)

    def write_markdown(self, output_path: Path | str) -> None:
        """Write scan results to a markdown document."""
        target = Path(output_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_markdown(), encoding="utf-8")

    def render_cli_summary(self) -> str:
        """Render a concise console-friendly summary string."""
        stats = self.result.stats
        by_type = self.result.violations_by_type()

        lines = [
            "==================================================",
            "        CONFIG SSOT ENFORCEMENT SCAN SUMMARY      ",
            "==================================================",
            f"Files Scanned:        {stats.files_scanned}",
            f"Files Skipped:        {stats.files_skipped}",
            f"Files with Issues:    {stats.files_with_violations}",
            f"Total Violations:     {stats.total_violations}",
            f"Scan Duration:        {stats.duration_seconds:.2f}s",
            "--------------------------------------------------",
        ]

        if not by_type:
            lines.append("✓ No SSOT violations detected! Repository is clean.")
        else:
            lines.append("Violations Breakdown:")
            for vtype, viols in sorted(by_type.items(), key=lambda item: len(item[1]), reverse=True):
                lines.append(f"  - {vtype:<30} : {len(viols):>4}")

        lines.append("==================================================")
        return "\n".join(lines)
