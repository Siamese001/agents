"""apps-test-model: APP CONTRACT.

CI gate coverage for apps_rg R1B/L4 best-practice invariants.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GATE_SCRIPT = _REPO_ROOT / "ops_scripts" / "ci" / "check_apps_rg_l4_best_practices.py"

pytestmark = pytest.mark.skipif(
    not _GATE_SCRIPT.is_file(),
    reason="standalone source baseline excludes the monorepo-owned L4 best-practices gate",
)


def test_apps_rg_l4_best_practices_gate_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_GATE_SCRIPT)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "[check_apps_rg_l4_best_practices] PASS" in result.stdout
