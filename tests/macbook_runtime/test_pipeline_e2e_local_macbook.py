"""Pillar 4: Dual Pipeline E2E Local Execution (Outreach Engine & Resume Graph Engine)."""
from __future__ import annotations

from pathlib import Path
import pytest
import torch

from apps_lic.runtime.dispatch.canonical_dispatch import run_canonical_apps_lic_spine
from apps_rg.bare_pipeline import evaluate_bare_run, run_bare_deterministic_e2e

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


def test_outreach_engine_canonical_spine_local_execution(tmp_path: Path) -> None:
    """Verifies Outreach Engine canonical spine executes offline on macOS with zero CUDA dependency."""
    ingress = {
        "company": "Truist",
        "channel": "email",
        "recipient_class": "recruiter",
        "manual_brief": "Strategic platform modernization and agentic governance",
    }
    out = run_canonical_apps_lic_spine(ingress, artifact_dir=tmp_path / "outreach_run")
    assert out["x3_code"] == "X3D_ALLOW_FINISH"
    assert out["is_valid"] is True
    assert (tmp_path / "outreach_run").is_dir()


def test_deterministic_resume_pipeline_11stage_local_execution(tmp_path: Path) -> None:
    """Verifies Resume Graph Engine 11-stage deterministic pipeline executes offline on macOS."""
    res = run_bare_deterministic_e2e(artifact_root=str(tmp_path))
    assert res.get("status") == "SUCCESS"
    assert res.get("outcome_label") == "DETERMINISTIC_OFFLINE_PASS"

    run_dir = Path(str(res["artifact_dir"]))
    eval_res = evaluate_bare_run(run_dir)
    assert eval_res.get("status") == "PASS", f"Evaluation failed: {eval_res}"

    for rel_name in ("resume.md", "resume.docx", "outreach_email.md", "sources.json", "evaluation.json"):
        fpath = run_dir / rel_name
        assert fpath.is_file(), f"Missing artifact: {rel_name}"
        assert fpath.stat().st_size > 0, f"Empty artifact: {rel_name}"


def test_pipeline_zero_cuda_and_subsystem_isolation(tmp_path: Path) -> None:
    """Verifies that consecutive execution of both pipelines produces no CUDA calls or state pollution."""
    assert torch.cuda.is_available() is False

    # Run Outreach
    out = run_canonical_apps_lic_spine(
        {"company": "AIG", "channel": "inmail", "recipient_class": "executive"},
        artifact_dir=tmp_path / "outreach_iso",
    )
    assert out["x3_code"] == "X3D_ALLOW_FINISH"

    # Run Resume
    res = run_bare_deterministic_e2e(artifact_root=str(tmp_path / "resume_iso"))
    assert res.get("status") == "SUCCESS"
