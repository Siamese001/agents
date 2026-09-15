#!/usr/bin/env python3
"""Deterministic secrets and credentials scanner.

Prevents accidental commits of API keys, access tokens, private keys, and obvious credentials.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Sequence

# Regex patterns for high-confidence secrets
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Private Key", re.compile(r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----")),
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("OpenAI API Key", re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b")),
    ("Anthropic API Key", re.compile(r"\bsk-ant-[a-zA-Z0-9_-]{20,}\b")),
    ("GitHub Personal Access Token", re.compile(r"\bghp_[a-zA-Z0-9]{36}\b")),
    ("GitHub Fine-Grained Token", re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{50,}\b")),
    ("Generic High-Entropy Secret", re.compile(r"""(?i)(?:api_key|apikey|secret_key|auth_token|access_token)\s*=\s*['"]([a-zA-Z0-9_\-]{24,})['"]""")),
)

EXCLUDED_FILENAMES: tuple[str, ...] = (
    ".env",
    ".env.local",
    "env_agents",
    ".env.example",
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
)

EXCLUDED_DIR_PARTS: tuple[str, ...] = (
    ".git",
    ".venv",
    "artifacts",
    "docs/archive",
    "fixtures",
)

DUMMY_SECRET_MARKERS: tuple[str, ...] = (
    "example",
    "dummy",
    "placeholder",
    "mock",
    "test",
    "fake",
    "xxx",
    "<your_",
    "your-api-key",
)


def is_shannon_entropy_high(s: str, threshold: float = 3.5) -> bool:
    """Calculate Shannon entropy to filter low-entropy strings."""
    if not s or len(s) < 16:
        return False
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    entropy = 0.0
    for count in freq.values():
        p = count / len(s)
        entropy -= p * math.log2(p)
    return entropy >= threshold


def check_file_for_secrets(file_path: Path, repo_root: Path) -> list[tuple[int, str, str]]:
    """Scan a single file for exposed secrets.

    Returns:
        List of (line_number, secret_type, snippet)
    """
    if not file_path.exists() or file_path.is_dir():
        return []

    try:
        rel = str(file_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        rel = str(file_path)

    if any(part in rel.split("/") for part in EXCLUDED_DIR_PARTS):
        return []

    if file_path.name in EXCLUDED_FILENAMES:
        return []

    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []

    violations: list[tuple[int, str, str]] = []

    for idx, line in enumerate(lines, start=1):
        # Check for inline exemption
        if "# allow-secret" in line or "# pragma: allow-secret" in line or "guardian: allow-secret" in line:
            continue

        for secret_name, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                matched_str = match.group(0)
                matched_lower = matched_str.lower()
                if any(marker in matched_lower for marker in DUMMY_SECRET_MARKERS):
                    continue

                if secret_name == "Generic High-Entropy Secret":
                    token_val = match.group(1) if match.groups() else matched_str
                    if not is_shannon_entropy_high(token_val):
                        continue

                redacted = matched_str[:4] + "..." + matched_str[-4:] if len(matched_str) > 8 else "***"
                violations.append((idx, secret_name, f"Potential {secret_name} detected: {redacted}"))

    return violations


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic secrets and credentials scanner.")
    parser.add_argument("--files", nargs="*", help="Specific files to scan")
    parser.add_argument("--all", action="store_true", help="Scan repository files")
    parser.add_argument("--repo-root", default=".", help="Root of repository")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    violations: list[tuple[str, int, str, str]] = []

    if args.files:
        files_to_scan = [Path(f) if Path(f).is_absolute() else repo_root / f for f in args.files]
    else:
        # Scan source files and config files
        files_to_scan = []
        for ext in ("*.py", "*.json", "*.yaml", "*.yml", "*.sh"):
            for f in repo_root.rglob(ext):
                files_to_scan.append(f)

    for f in files_to_scan:
        if f.is_file():
            v = check_file_for_secrets(f, repo_root)
            for lineno, stype, msg in v:
                rel = str(f.relative_to(repo_root)) if f.is_relative_to(repo_root) else str(f)
                violations.append((rel, lineno, stype, msg))

    if violations:
        print(f"[FAIL] Secrets detected ({len(violations)} occurrences):", file=sys.stderr)
        for rel, lineno, stype, msg in violations:
            print(f"  - {rel}:{lineno}: {msg}", file=sys.stderr)
        return 1

    print(f"[PASS] Secrets scan clean (no unredacted credentials or keys detected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
