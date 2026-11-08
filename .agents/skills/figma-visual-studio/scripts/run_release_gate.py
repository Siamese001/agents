#!/usr/bin/env python3
"""CLI wrapper to run the Figma 4K Visual Governance release gate.

Invokes the fail-closed machine release authority in:
Figma/Figma_4K_Visual_Governance_v1.0.0_20260904/runtime/govern.py
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
FIGMA_PKG = REPO_ROOT / "Figma" / "Figma_4K_Visual_Governance_v1.0.0_20260904"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Figma 4K Visual Governance release gate.")
    parser.add_argument("--receipt", type=Path, required=True, help="Path to RELEASE.json")
    parser.add_argument("--diagnostic", action="store_true", help="Run in diagnostic mode (validate only)")
    args = parser.parse_args()

    receipt_path = Path(args.receipt).resolve()
    if not receipt_path.is_file():
        print(f"Error: Receipt file not found: {receipt_path}", file=sys.stderr)
        return 1

    cmd_type = "validate" if args.diagnostic else "release"
    cmd = [
        sys.executable,
        "-m",
        "runtime.govern",
        cmd_type,
        "--receipt",
        str(receipt_path),
    ]

    env = dict(sys.modules.get("os", {}).environ if hasattr(sys, "modules") else {})
    import os
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    proc = subprocess.run(
        cmd,
        cwd=str(FIGMA_PKG),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)

    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
