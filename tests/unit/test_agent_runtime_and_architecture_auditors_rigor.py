"""Counterfactual rigor tests for Agent 1 (Architecture/Cost) and Agent 2 (Core Runtime) auditors."""
from __future__ import annotations

import shutil
from pathlib import Path

from tools.agent_runtime_auditor import (
    audit_pillar_1_delegation_contracts,
    audit_pillar_5_exception_hygiene,
    audit_pillar_6_provider_resilience_and_sla_hierarchy,
    run_agent_runtime_audit,
)
from tools.cost_token_budget_auditor import (
    _audit_pillar_1_provider_pinning_and_effort,
    _load_registry_pricing,
)
from tools.cost_token_budget_probes import load_yaml_strict
from tools.ssot_boundary_auditor import run_ssot_boundary_audit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_agent1_ssot_auditor_passes_zero_uncentralized_env_lookup() -> None:
    ssot_rep = run_ssot_boundary_audit(repo_root=REPO_ROOT)
    assert ssot_rep["status"] == "PASS", ssot_rep["hardcoding_and_parity_scan"]
    assert ssot_rep["is_clean"] is True


def test_agent1_cost_auditor_catches_expired_pin_review_after(tmp_path: Path) -> None:
    pricing_map, _ = _load_registry_pricing(REPO_ROOT)
    live_prof, live_err = load_yaml_strict(REPO_ROOT / "config" / "provider_profiles.yaml")
    p1_live = _audit_pillar_1_provider_pinning_and_effort(REPO_ROOT, live_prof, live_err, pricing_map)
    assert p1_live["status"] == "PASS", p1_live["gaps"]

    sandbox = tmp_path / "expired_pin_repo"
    (sandbox / "config").mkdir(parents=True)
    raw = (REPO_ROOT / "config" / "provider_profiles.yaml").read_text(encoding="utf-8")
    expired_path = sandbox / "config" / "provider_profiles.yaml"
    expired_path.write_text(
        raw.replace('pin_review_after: "2027-02-25"', 'pin_review_after: "2020-01-01"'),
        encoding="utf-8",
    )
    bad_prof, bad_err = load_yaml_strict(expired_path)
    p1_bad = _audit_pillar_1_provider_pinning_and_effort(sandbox, bad_prof, bad_err, pricing_map)
    assert p1_bad["status"] == "ACTION_REQUIRED"
    assert any("pin_review_after '2020-01-01' is expired" in g for g in p1_bad["gaps"])


def test_agent2_runtime_auditor_blocks_vacuous_zero_contract_and_scans_transport(tmp_path: Path) -> None:
    rep = run_agent_runtime_audit(REPO_ROOT)
    assert rep["status"] == "PASS", rep["gaps"]
    assert rep["pillars"]["pillar_1_delegation_contracts"]["runtime_enforcers_verified"] >= 1
    assert rep["pillars"]["pillar_5_exception_hygiene"]["scanned_files"] > 70
    assert rep["pillars"]["pillar_6_provider_resilience_and_sla_hierarchy"]["behavioral_probes_passed"] >= 1

    # Negative control 1: empty repo with 0 contracts and 0 hook enforcers fails closed
    empty_repo = tmp_path / "empty_contracts"
    empty_repo.mkdir()
    p1_empty = audit_pillar_1_delegation_contracts(empty_repo)
    assert p1_empty["passed"] is False
    assert any("vacuous pass blocked" in g for g in p1_empty["gaps"])

    # Negative control 2: silent swallow in infrastructure/sdks_mcps/ fails Pillar 5 closed
    swallow_repo = tmp_path / "swallow_transport"
    (swallow_repo / "agents").mkdir(parents=True)
    (swallow_repo / "infrastructure" / "sdks_mcps").mkdir(parents=True)
    (swallow_repo / "agents" / "__init__.py").write_text("", encoding="utf-8")
    (swallow_repo / "infrastructure" / "sdks_mcps" / "bad_transport.py").write_text(
        "def run() -> None:\n    try:\n        raise RuntimeError('x')\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    p5_bad = audit_pillar_5_exception_hygiene(swallow_repo)
    assert p5_bad["passed"] is False
    assert any("bad_transport.py" in g for g in p5_bad["gaps"])

    # Negative control 3: Pillar 6 detects <=45s regen timeout clamp via AST
    clamp_repo = tmp_path / "clamp_repo"
    target = clamp_repo / "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_regen_dispatch.py"
    target.parent.mkdir(parents=True)
    target.write_text("def clamp(x: float) -> float:\n    return min(x, 45)\n", encoding="utf-8")
    p6_bad = audit_pillar_6_provider_resilience_and_sla_hierarchy(clamp_repo)
    assert p6_bad["passed"] is False
    assert any("<=45s" in g for g in p6_bad["gaps"])
