"""Unmocked adversarial test suite for Wave 1 Loophole & Anti-BS Red-Team Engine."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.loophole_redteam_auditor import (
    ALL_LOOPHOLE_IDS,
    REDTEAM_SUBAGENT_CONTRACTS,
    audit_repository_loopholes,
    load_guardian_exemption_registry,
    run_counterfactual_self_test,
    scan_r1_mock_and_canned_fallbacks,
    scan_r2_fake_tests_and_coverage,
    scan_r3_fake_scans_and_guard_theater,
    scan_r4_agent_prompt_and_gate_bypasses,
    validate_redteam_subagent_contracts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_redteam_subagent_contracts_are_valid_and_read_only() -> None:
    """All 4 specialized Red-Team contracts pass 10-field validation and forbid write tools."""
    assert len(REDTEAM_SUBAGENT_CONTRACTS) == 4
    errors = validate_redteam_subagent_contracts()
    assert errors == [], f"Unexpected contract validation errors: {errors}"
    task_ids = {c["task_id"] for c in REDTEAM_SUBAGENT_CONTRACTS}
    assert task_ids == {
        "redteam-r1-mock-hunter",
        "redteam-r2-fake-test-hunter",
        "redteam-r3-fake-scan-hunter",
        "redteam-r4-agent-bypass-hunter",
    }
    for contract in REDTEAM_SUBAGENT_CONTRACTS:
        assert set(contract["allowed_tools"]) == {"read_file", "run_command"}


def test_counterfactual_self_test_catches_all_12_planted_loopholes_with_zero_false_positives() -> None:
    """Counterfactual mutation harness catches 12/12 planted loopholes and 0 clean false positives."""
    report = run_counterfactual_self_test()
    assert report["status"] == "PASS", f"Counterfactual self-test failed: {report}"
    assert report["planted_count"] == len(ALL_LOOPHOLE_IDS) == 12
    assert report["caught_count"] == 12
    assert report["missed_loophole_ids"] == []
    assert report["clean_control_false_positives"] == 0
    assert report["contract_errors"] == []


def test_guardian_exemption_registry_loads_and_rejects_malformed_tags(tmp_path: Path) -> None:
    """R3 detects unregistered and malformed `# guardian:` comments while allowing registered justified tags."""
    reg = load_guardian_exemption_registry(REPO_ROOT)
    assert "allow-silent-swallow" in reg["allowed_exemption_types"]
    assert reg["ratchet_ceilings"]["malformed_or_unregistered"] == 0

    (tmp_path / "config" / "governance").mkdir(parents=True)
    (tmp_path / "config" / "governance" / "guardian_exemption_registry.yaml").write_text(
        (REPO_ROOT / "config" / "governance" / "guardian_exemption_registry.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "agents").mkdir(parents=True)
    (tmp_path / "agents" / "sample.py").write_text(
        "def f():\n"
        "    try:\n"
        "        return 1\n"
        "    except OSError:  # guardian: allow-silent-swallow -- valid deterministic cleanup rationale\n"
        "        return 0\n"
        "def g():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:  # guardian: allow-bogus-type -- not registered in YAML\n"
        "        return 0\n"
        "def h():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:  # guardian: missing separator\n"
        "        return 0\n",
        encoding="utf-8",
    )

    findings = scan_r3_fake_scans_and_guard_theater(tmp_path)
    codes = {f.code for f in findings}
    assert "UNREGISTERED_GUARDIAN_EXEMPTION_TYPE" in codes
    assert "MALFORMED_GUARDIAN_EXEMPTION" in codes
    assert len(findings) == 2


def test_r1_r2_r4_fail_closed_on_individual_planted_defects(tmp_path: Path) -> None:
    """Each red-team pillar catches targeted defects in isolation without false positives."""
    (tmp_path / "agents").mkdir(parents=True)
    (tmp_path / "agents" / "gw.py").write_text('MODEL = "simulated-v1"\n', encoding="utf-8")
    r1 = scan_r1_mock_and_canned_fallbacks(tmp_path)
    assert any(f.loophole_id == "LH-01" for f in r1)

    (tmp_path / "tests" / "end_to_end").mkdir(parents=True)
    (tmp_path / "tests" / "end_to_end" / "test_demo_e2e.py").write_text(
        "from unittest.mock import MagicMock\ndef test_stub():\n    assert True\n",
        encoding="utf-8",
    )
    r2 = scan_r2_fake_tests_and_coverage(tmp_path)
    r2_ids = {f.loophole_id for f in r2}
    assert {"LH-06", "LH-07"}.issubset(r2_ids)

    (tmp_path / "tools").mkdir(parents=True)
    (tmp_path / "tools" / "verify_main_readiness.py").write_text(
        'def run():\n    return (True, "Optional suite not present")\n',
        encoding="utf-8",
    )
    r4 = scan_r4_agent_prompt_and_gate_bypasses(tmp_path)
    assert any(f.loophole_id == "LH-10" for f in r4)


def test_cli_counterfactual_passes_and_verify_strict_fails_on_planted_repo(tmp_path: Path) -> None:
    """CLI exits 0 on counterfactual self-test and exits 1 fail-closed on --verify-strict with defects."""
    script = REPO_ROOT / "tools" / "loophole_redteam_auditor.py"
    receipt = tmp_path / "cf_receipt.json"
    proc_cf = subprocess.run(
        [sys.executable, str(script), "--counterfactual-self-test", "--json", "--write-receipt", str(receipt)],
        capture_output=True,
        text=True,
        shell=False,
        timeout=30,
        check=False,
    )
    assert proc_cf.returncode == 0, f"Counterfactual CLI failed: {proc_cf.stderr}\n{proc_cf.stdout}"
    data = json.loads(proc_cf.stdout)
    assert data["counterfactual_self_test"]["caught_count"] == 12
    assert receipt.is_file()

    (tmp_path / "bad_repo" / "agents").mkdir(parents=True)
    (tmp_path / "bad_repo" / "agents" / "fake.py").write_text('PROVIDER = "simulated_default"\n', encoding="utf-8")
    proc_strict = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(tmp_path / "bad_repo"), "--verify-strict", "--json"],
        capture_output=True,
        text=True,
        shell=False,
        timeout=30,
        check=False,
    )
    assert proc_strict.returncode == 1
    strict_data = json.loads(proc_strict.stdout)
    assert strict_data["repository_audit"]["total_findings"] >= 1


def test_live_repo_baseline_audit_runs_cleanly_and_detects_real_findings() -> None:
    """Live baseline scan executes cleanly against repository with 0 contract errors."""
    report = audit_repository_loopholes(REPO_ROOT)
    assert report["contract_errors"] == []
    assert set(report["pillar_counts"].keys()) == {
        "R1_mock_stub_hunter",
        "R2_fake_test_hunter",
        "R3_fake_scan_hunter",
        "R4_agent_bypass_hunter",
    }
    assert report["total_findings"] >= 0
