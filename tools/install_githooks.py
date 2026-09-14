#!/usr/bin/env python3
"""Configures Git to use versioned hooks in .githooks/.

Enforces deterministic local pre-commit and pre-push verification.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GITHOOKS_DIR = ROOT / ".githooks"


def install_hooks() -> int:
    """Configure core.hooksPath and make hook scripts executable."""
    if not GITHOOKS_DIR.is_dir():
        print(f"Error: {GITHOOKS_DIR} does not exist.", file=sys.stderr)
        return 1

    # 1. Ensure hooks are executable
    for hook in GITHOOKS_DIR.iterdir():
        if hook.is_file() and not hook.name.startswith("."):
            mode = hook.stat().st_mode
            hook.chmod(mode | 0o755)
            print(f"[chmod +x] {hook.name}")

    # 2. Set git config core.hooksPath
    try:
        subprocess.run(
            ["git", "config", "core.hooksPath", ".githooks"],
            cwd=str(ROOT),
            check=True,
            timeout=10,
        )
        print("[git config] core.hooksPath set to .githooks")
    except Exception as exc:
        print(f"Error configuring git hooks path: {exc}", file=sys.stderr)
        return 1

    print("Git hooks successfully installed and active.")
    return 0


if __name__ == "__main__":
    sys.exit(install_hooks())
