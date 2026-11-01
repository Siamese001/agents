"""
Unified PR promotion and submission workflow.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional


def cmd_promote(args: argparse.Namespace) -> int:
    """CLI handler for `pr_governance.py promote <branch> --title <title>` (delegates to cmd_merge)."""
    from .lifecycle import cmd_merge

    return cmd_merge(args)


def cmd_submit(args: argparse.Namespace) -> int:
    """CLI handler for `pr_governance.py submit <branch> --title <title>` (delegates to cmd_merge)."""
    from .lifecycle import cmd_merge

    return cmd_merge(args)
