#!/usr/bin/env python3
"""Local Health-Check Command for the Sovereign Agentic Platform.

Usage:
    python tools/health_check.py [--verbose] [--json] [--domain DOMAIN]
    python -m agents check [--verbose] [--json]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path and shared .venv packages are available in worktrees
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv

bootstrap_shared_venv(_REPO_ROOT)

from agents.health import main

if __name__ == "__main__":
    sys.exit(main())
