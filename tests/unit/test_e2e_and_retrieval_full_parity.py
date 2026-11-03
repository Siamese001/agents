"""Unit tests for Wave 3 Dual-Engine E2E Smoke and Retrieval Surface Parity (Agents 3 & 4)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from ops_scripts.run_e2e_authoritative_smoke import run_smoke
from tools.e2e_functionality_auditor import (
    AUDITED_PACKAGES,
    run_e2e_functionality_audit,
    scan_unguarded_silent_swallows,
)
from tools.retrieval_surface_auditor import (
    RETRIEVAL_PACKAGES,
    run_retrieval_surface_audit,
    scan_untyped_public_retrieval_callables,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_authoritative_smoke_defaults_to_dual_engine_without_skip_resume(tmp_path: Path) -> None:
    sig = inspect.signature(run_smoke)
    assert sig.parameters["skip_resume"].default is False

    receipt_path = tmp_path / "smoke_receipt.json"
    rc = run_smoke(
        read_only=True,
        receipt_out=receipt_path,
        repo_root=REPO_ROOT,
        quiet=True,
    )
    assert rc == 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "PASSED"
    assert receipt["skip_resume"] is False
    assert receipt["stages"]["resume_tailoring"]["status"] == "PASSED"
    assert receipt["stages"]["executive_outreach"]["status"] == "PASSED"
    verified = receipt["verified_artifacts"]
    assert "final_resume" in verified
    assert "outreach_campaign" in verified
    assert "resume_pipeline::resume.md" in verified
    assert "resume_pipeline::resume.docx" in verified


def test_e2e_auditor_scans_all_11_roots_for_silent_swallows(tmp_path: Path) -> None:
    expected = {
        "agents",
        "apps_eval",
        "apps_model_telemetry",
        "apps_research",
        "infrastructure",
        "ops_scripts",
        "outreach_engine",
        "resume_engine",
        "resume_graph_engine",
        "scripts",
        "tools",
    }
    assert set(AUDITED_PACKAGES) == expected
    assert scan_unguarded_silent_swallows(REPO_ROOT) == []

    # Synthetic unguarded silent swallow inside ops_scripts/ and tools/ must fail closed
    ops_dir = tmp_path / "ops_scripts"
    ops_dir.mkdir(parents=True)
    (ops_dir / "bad_ops.py").write_text(
        "def run_job() -> dict:\n"
        "    try:\n"
        "        return {'ok': True}\n"
        "    except Exception:\n"
        "        return {}\n",
        encoding="utf-8",
    )
    findings = scan_unguarded_silent_swallows(tmp_path)
    assert len(findings) == 1
    assert findings[0]["file"] == "ops_scripts/bad_ops.py"


def test_retrieval_auditor_enforces_return_types_without_filename_regex_bypass(tmp_path: Path) -> None:
    assert "infrastructure" in RETRIEVAL_PACKAGES
    assert "outreach_engine" in RETRIEVAL_PACKAGES
    assert "resume_graph_engine" in RETRIEVAL_PACKAGES
    assert scan_untyped_public_retrieval_callables(REPO_ROOT) == []

    # File with non-retrieval name inside infrastructure/ must NOT be skipped
    infra_dir = tmp_path / "infrastructure" / "utils"
    infra_dir.mkdir(parents=True)
    (infra_dir / "plain_helper_module.py").write_text(
        "def compute_metric(x: int):\n"
        "    return x + 1\n",
        encoding="utf-8",
    )
    missing = scan_untyped_public_retrieval_callables(tmp_path)
    assert len(missing) == 1
    assert missing[0]["callable"] == "compute_metric"


def test_live_e2e_and_retrieval_auditors_pass_all_pillars() -> None:
    e2e_report = run_e2e_functionality_audit(REPO_ROOT, read_only=True)
    assert e2e_report["is_clean"] is True, e2e_report["gaps"]
    assert e2e_report["passing_pillars"] == 6
    assert e2e_report["pillars"]["pillar_1_research_to_outreach_handoff"]["unauthorized_outreach_dispatch_blocked"] is True
    assert e2e_report["pillars"]["pillar_3_authoritative_e2e_smoke"]["skip_resume"] is False

    ret_report = run_retrieval_surface_audit(REPO_ROOT, read_only=True)
    assert ret_report["is_clean"] is True, ret_report["gaps"]
    assert ret_report["passing_pillars"] == 7
    assert ret_report["pillars"]["pillar_5_empty_result_fail_closed_abstention"]["outreach_failure_reason"] != ""
    assert ret_report["pillars"]["pillar_7_cross_subsystem_typing_contract"]["untyped_public_callable_count"] == 0
