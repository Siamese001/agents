from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APPS_LIC_SPEC = importlib.util.find_spec("apps_lic")
if (
    _APPS_LIC_SPEC is None
    or _APPS_LIC_SPEC.origin is None
    or _REPO_ROOT not in Path(_APPS_LIC_SPEC.origin).resolve().parents
):
    pytest.skip(
        "apps_lic snapshots and source are excluded from the apps_rg_v2 standalone scope",
        allow_module_level=True,
    )

def test_apps_lic_dev_suite_passes_from_snapshots(tmp_path: Path) -> None:
    from apps_eval.contracts import EvalRequest
    from apps_eval.runner.core import run_eval

    record = run_eval(
        EvalRequest(
            suite_id="apps_lic.dev.outreach_message",
            mode="snapshot",
            deterministic_only=True,
            out_dir=str(tmp_path),
        )
    )
    assert record.app_id == "apps_lic"
    assert record.scorecard.verdict == "pass"
    assert record.scorecard.block_failures == 0
    for key in ["eval_record", "scorecard", "report", "manifest", "grader_findings", "regression", "regression_flywheel"]:
        assert Path(record.artifact_paths[key]).is_file()
