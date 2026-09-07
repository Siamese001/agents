"""Subprocess proof that bare Python resolves this standalone checkout first."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_bare_python_prefers_local_src_packages() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    expected_src = (repo_root / "src").resolve()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    script = (
        "import apps_eval, apps_research, apps_rg, json, sys; "
        "print(json.dumps({"
        "'apps_rg': apps_rg.__file__, "
        "'apps_research': apps_research.__file__, "
        "'apps_eval': apps_eval.__file__, "
        "'path': sys.path[:4]"
        "}))"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    for package_name in ("apps_rg", "apps_research", "apps_eval"):
        package_path = Path(payload[package_name]).resolve()
        assert package_path.is_relative_to(expected_src), payload
    assert Path(payload["path"][0]).resolve() == expected_src
