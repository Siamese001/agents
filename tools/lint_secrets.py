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
    ("Google API Key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("OpenAI API Key", re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b")),
    ("Anthropic API Key", re.compile(r"\bsk-ant-[a-zA-Z0-9_-]{20,}\b")),
    ("GitHub Personal Access Token", re.compile(r"\bghp_[a-zA-Z0-9]{36}\b")),
    ("GitHub Fine-Grained Token", re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{50,}\b")),
    ("Notion API Token", re.compile(r"\b(?:ntn_[0-9A-Za-z]{40,}|secret_[0-9A-Za-z]{43})\b")),
    ("Slack Token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{24,}\b")),
    (
        "Hardcoded Bearer Token",
        re.compile(r"""(?i)authorization['"]?\s*[:=]\s*['"]bearer\s+([a-zA-Z0-9_\-\.]{24,})['"]"""),
    ),
    ("Generic High-Entropy Secret", re.compile(r"""(?i)(?:api_key|apikey|secret_key|auth_token|access_token)\s*=\s*['"]([a-zA-Z0-9_\-]{24,})['"]""")),
)

STAGED_FORBIDDEN_ENV_FILES: tuple[str, ...] = (
    ".env",
    ".env.local",
    "env_agents",
)

EXCLUDED_FILENAMES: tuple[str, ...] = (
    ".env.example",
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
)

EXCLUDED_DIR_PARTS: tuple[str, ...] = (
    ".git",
    ".venv",
    ".worktrees",
    "artifacts",
    "docs/archive",
    "fixtures",
)

DUMMY_SECRET_MARKERS: tuple[str, ...] = (
    "example",
    "dummy",
    "placeholder",
    "mock",
    "fake",
    "xxx",
    "<your_",
    "your-api-key",
    "redacted",
)

EXPLICIT_TEST_TOKEN_MARKERS: tuple[str, ...] = (
    "sk-test-",
    "sk_test_",
    "sk-ant-test",
    "-test-",
    "_test_",
    "test_key",
    "test-key",
    "test_token",
    "test-token",
    "testsecret",
    "testapikey",
)


FAST_SECRET_TRIGGERS: tuple[str, ...] = (
    "private key",
    "akia",
    "aiza",
    "sk-",
    "ghp_",
    "github_pat_",
    "ntn_",
    "secret_",
    "xox",
    "bearer ",
    "api_key",
    "apikey",
    "secret_key",
    "auth_token",
    "access_token",
)


def _is_dummy_token(matched_str: str) -> bool:
    """Return True only for unambiguous placeholder or delimited test fixture tokens."""
    matched_lower = matched_str.lower()
    if any(marker in matched_lower for marker in DUMMY_SECRET_MARKERS):
        return True
    return any(marker in matched_lower for marker in EXPLICIT_TEST_TOKEN_MARKERS)


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


def check_file_for_secrets(
    file_path: Path,
    repo_root: Path,
    *,
    explicitly_targeted: bool = False,
) -> list[tuple[int, str, str]]:
    """Scan a single file for exposed secrets.

    Returns:
        List of (line_number, secret_type, snippet)
    """
    if explicitly_targeted and (
        file_path.name in STAGED_FORBIDDEN_ENV_FILES
        or (file_path.name.startswith(".env.") and file_path.name != ".env.example")
    ):
        return [
            (
                1,
                "Forbidden Environment Credential File",
                f"Sensitive credential file '{file_path.name}' must never be staged or committed.",
            )
        ]

    if not file_path.exists() or file_path.is_dir():
        return []

    # Fast relative path calculation
    try:
        rel = file_path.as_posix()
        root_posix = repo_root.as_posix()
        if rel.startswith(root_posix):
            rel = rel[len(root_posix):].lstrip("/")
    except Exception:
        rel = str(file_path)

    if any(part in rel.split("/") for part in EXCLUDED_DIR_PARTS):
        return []

    if file_path.name in EXCLUDED_FILENAMES:
        return []

    if not explicitly_targeted and (
        file_path.name in STAGED_FORBIDDEN_ENV_FILES
        or file_path.name.startswith(".env.")
    ):
        return []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    content_lower = content.lower()
    if not any(trigger in content_lower for trigger in FAST_SECRET_TRIGGERS):
        return []

    lines = content.splitlines()
    violations: list[tuple[int, str, str]] = []

    for idx, line in enumerate(lines, start=1):
        # Check for inline exemption
        if "# allow-secret" in line or "# pragma: allow-secret" in line or "guardian: allow-secret" in line:
            continue

        line_lower = line.lower()
        if not any(trigger in line_lower for trigger in FAST_SECRET_TRIGGERS):
            continue

        for secret_name, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                matched_str = match.group(0)
                if _is_dummy_token(matched_str):
                    continue

                if secret_name in ("Generic High-Entropy Secret", "Hardcoded Bearer Token"):
                    token_val = match.group(1) if match.groups() else matched_str
                    if _is_dummy_token(token_val) or not is_shannon_entropy_high(token_val):
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
    explicitly_targeted = bool(args.files)

    if args.files:
        files_to_scan = [Path(f) if Path(f).is_absolute() else repo_root / f for f in args.files]
    else:
        # Scan source files and config files with fast pruned os.walk
        import os

        files_to_scan = []
        excluded_parts_set = set(EXCLUDED_DIR_PARTS)
        for root, dirs, files_in_dir in os.walk(repo_root):
            dirs[:] = [d for d in dirs if d not in excluded_parts_set]
            for f in files_in_dir:
                ext = Path(f).suffix.lower()
                if ext in (".py", ".json", ".yaml", ".yml", ".sh", ".toml", ".md", ".jsonl"):
                    files_to_scan.append(Path(root) / f)

    def scan_one(f: Path) -> list[tuple[str, int, str, str]]:
        if not explicitly_targeted and not f.is_file():
            return []
        v = check_file_for_secrets(f, repo_root, explicitly_targeted=explicitly_targeted)
        try:
            rel = str(f.relative_to(repo_root))
        except ValueError:
            rel = str(f)
        return [(rel, lineno, stype, msg) for lineno, stype, msg in v]

    import os
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as executor:
        results = executor.map(scan_one, files_to_scan)
        for res in results:
            violations.extend(res)

    if violations:
        print(f"[FAIL] Secrets detected ({len(violations)} occurrences):", file=sys.stderr)
        for rel, lineno, stype, msg in violations:
            print(f"  - {rel}:{lineno}: {msg}", file=sys.stderr)
        return 1

    print(f"[PASS] Secrets scan clean (no unredacted credentials or keys detected).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
