"""CLI interface for Config SSOT Enforcement Agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .exemptions import ExemptionManager
from .ratchet import SSOTRatchetGate
from .registry import SSOTRegistry
from .reporter import SSOTReporter
from .scanner import SSOTScanner


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for SSOT CLI tool."""
    parser = argparse.ArgumentParser(
        prog="config_ssot_agent",
        description="Scans codebase for Single Source of Truth (SSOT) configuration violations.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # scan subcommand
    scan_parser = subparsers.add_parser("scan", help="Scan paths for SSOT violations")
    scan_parser.add_argument(
        "-p",
        "--path",
        action="append",
        dest="paths",
        help="Path(s) to scan (directories or files). Can be specified multiple times.",
    )
    scan_parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="Output file path to save report (e.g. artifacts/ssot_violations.json)",
    )
    scan_parser.add_argument(
        "--format",
        choices=["summary", "json", "markdown", "all"],
        default="summary",
        help="Output format (default: summary)",
    )
    scan_parser.add_argument(
        "--fail-on-violation",
        action="store_true",
        default=False,
        help="Exit with non-zero code if any violations are found (for CI/pre-commit).",
    )
    scan_parser.add_argument(
        "--ratchet",
        dest="ratchet_path",
        help="Path to baseline ratchet JSON file. Fails if current violations exceed baseline.",
    )
    scan_parser.add_argument(
        "--update-ratchet",
        action="store_true",
        default=False,
        help="Update ratchet baseline file with new lower counts if scan passes.",
    )
    scan_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Enforce zero tolerance on models, timeouts, and tokens, plus ratchet ceiling.",
    )
    scan_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Print detailed file-by-file violation listings.",
    )

    # check subcommand (for pre-commit on staged files)
    check_parser = subparsers.add_parser(
        "check", help="Check specific files for SSOT violations (fails on any violation)"
    )
    check_parser.add_argument(
        "files",
        nargs="*",
        help="List of files to check (passed by pre-commit).",
    )
    check_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Print detailed file-by-file violation listings.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for config_ssot_agent."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.subcommand or args.subcommand == "scan":
        target_paths = args.paths or ["resume_graph_engine/src/apps_rg"]
        registry = SSOTRegistry()
        exemption_mgr = ExemptionManager()
        scanner = SSOTScanner(registry=registry, exemption_manager=exemption_mgr)

        result = scanner.scan(target_paths)
        reporter = SSOTReporter(result)

        # Print console summary
        print(reporter.render_cli_summary())

        if getattr(args, "verbose", False) and result.violations:
            print("\nDetailed Findings:")
            for v in result.violations:
                print(f"  {v.file_path}:{v.line}:{v.column} [{v.violation_type.value}] {v.message}")

        # Save to output file if requested
        if args.output:
            out_path = Path(args.output)
            if out_path.suffix == ".json" or args.format == "json":
                reporter.write_json(out_path)
                print(f"\n[+] Saved JSON report to: {out_path}")
            elif out_path.suffix == ".md" or args.format == "markdown":
                reporter.write_markdown(out_path)
                print(f"\n[+] Saved Markdown report to: {out_path}")
            else:
                # default to JSON if extension unclear
                reporter.write_json(out_path)
                print(f"\n[+] Saved report to: {out_path}")

        # Ratchet check
        ratchet_path = getattr(args, "ratchet_path", None)
        if ratchet_path or getattr(args, "strict", False):
            gate = SSOTRatchetGate(ratchet_path=ratchet_path)
            passed, failures = gate.evaluate(result)
            if not passed:
                print("\n[!] Config SSOT Ratchet Gate FAILED:")
                for f in failures:
                    print(f"  - {f}")
                return 1
            print(f"\n[✓] Config SSOT Ratchet Gate PASSED: {result.stats.total_violations} <= baseline threshold.")

            if getattr(args, "update_ratchet", False) and ratchet_path:
                gate.save_baseline(result, ratchet_path)
                print(f"[+] Updated ratchet baseline at: {ratchet_path}")

        if args.fail_on_violation and result.stats.total_violations > 0:
            return 1

        return 0

    if args.subcommand == "check":
        files = args.files or []
        if not files:
            return 0
        registry = SSOTRegistry()
        exemption_mgr = ExemptionManager()
        scanner = SSOTScanner(registry=registry, exemption_manager=exemption_mgr)
        result = scanner.scan(files)
        if result.violations:
            reporter = SSOTReporter(result)
            print(reporter.render_cli_summary())
            print("\n[!] Pre-commit Config SSOT Gate Failed! Violations found in checked files:")
            for v in result.violations:
                print(f"  {v.file_path}:{v.line}:{v.column} [{v.violation_type.value}] {v.message}")
                if v.suggested_ssot:
                    print(f"    --> Suggestion: {v.suggested_ssot}")
            return 1
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
