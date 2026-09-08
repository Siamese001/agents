"""SP-002: executive_summary demo harness env gate (W7A)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from apps_rg.runtime.non_product_proof_stamp import DEMO_HARNESS_ENV

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE = "tests.fixtures.apps_rg.demo_harness_fixture"


def test_demo_harness_module_fails_without_env() -> None:
    env = os.environ.copy()
    env.pop(DEMO_HARNESS_ENV, None)
    proc = subprocess.run(
        [sys.executable, "-m", MODULE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 2
    assert DEMO_HARNESS_ENV in (proc.stderr or "")


def test_demo_harness_module_runs_with_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = os.environ.copy()
    env[DEMO_HARNESS_ENV] = "1"
    import_roots = (str(REPO_ROOT), str(REPO_ROOT / "src"))
    env["PYTHONPATH"] = os.pathsep.join(
        (*import_roots, env.get("PYTHONPATH", ""))
    ).rstrip(os.pathsep)
    proc = subprocess.run(
        [sys.executable, "-m", MODULE],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0
    assert (tmp_path / "demo_harness_proof.json").is_file()
