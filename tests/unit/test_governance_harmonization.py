"""Unit and fault-injection tests for tools/audit_governance_harmonization.py."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.audit_governance_harmonization import audit_governance_harmonization

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_current_repository_passes_governance_harmonization() -> None:
    report = audit_governance_harmonization(REPO_ROOT)
    assert report["status"] == "PASS", f"Harmonization failed: {report['findings']}"
    assert report["critical_count"] == 0
    assert report["broken_refs"] == []
    assert report["agents_md_lines"] <= 200
    assert report["skills_tokens"] < 4000


def test_detects_threshold_drift_and_broken_script_ref(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (tmp_path / ".agents" / "rules").mkdir(parents=True)
    (tmp_path / ".agents" / "skills" / "demo").mkdir(parents=True)
    (tmp_path / ".agents" / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Short skill description.\n---\n# Demo\n",
        encoding="utf-8",
    )
    (tmp_path / ".agents" / "rules" / "bad_rule.md").write_text(
        "Use `tools/nonexistent_ghost_gate.py` for validation.\n",
        encoding="utf-8",
    )
    (tmp_path / ".agents" / "hooks.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tools").mkdir(parents=True)
    (tmp_path / "tools" / "hook_dispatch.py").write_text("# dispatch\n", encoding="utf-8")
    (tmp_path / "config" / "governance").mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "config" / "governance" / "policy_registry.yaml",
        tmp_path / "config" / "governance" / "policy_registry.yaml",
    )
    (tmp_path / "config" / "governance" / "risk_lanes_policy.json").write_text(
        json.dumps({"default_unrecognized_lane": 0, "lanes": {}}),
        encoding="utf-8",
    )

    report = audit_governance_harmonization(tmp_path)
    assert report["status"] == "FAIL"
    categories = {f["category"] for f in report["findings"]}
    assert "threshold_drift" in categories
    assert "broken_reference" in categories
    assert any("nonexistent_ghost_gate.py" in ref for ref in report["broken_refs"])


def test_rebaselined_learning_policies_flywheel_locks_and_graph_presence_ratchet(tmp_path: Path) -> None:
    from agents.learning.policy_router import load_auto_apply_policy
    from tools.audit_eval_construct_validity import scan_fact_inventory_graph_presence_ratchet
    from tools.audit_governance_harmonization import REQUIRED_AI_SDLC_POLICY_IDS
    from tools.validate_turn_gates import load_policy_registry

    policies = load_policy_registry(REPO_ROOT)
    for pid in REQUIRED_AI_SDLC_POLICY_IDS:
        assert pid in policies, f"Missing policy {pid}"
        assert (REPO_ROOT / policies[pid]["enforcer"]).is_file()
        assert (REPO_ROOT / policies[pid]["rule_reference"]).is_file()

    auto_pol = load_auto_apply_policy(REPO_ROOT)
    forbidden = tuple((auto_pol.get("tier_c_pr_only") or {}).get("forbidden_auto_apply_prefixes") or ())
    assert "resume_graph_engine/src/apps_rg/fact_inventory/" in forbidden
    truth_locks = auto_pol.get("immutable_human_truth_surfaces") or {}
    assert truth_locks.get("forbid_candidate_fact_synthesis") is True
    assert truth_locks.get("forbid_literal_prose_splicing_repair_hints") is True
    assert float(truth_locks.get("forbid_blind_judge_floor_reduction_below", 0.0)) == 4.7

    count, ceiling, violations = scan_fact_inventory_graph_presence_ratchet(REPO_ROOT)
    assert count <= ceiling
    assert violations == []

    # Fault injection: exceeding ratchet ceiling must fail closed.
    (tmp_path / "config" / "governance").mkdir(parents=True)
    (tmp_path / "config" / "governance" / "policy_registry.yaml").write_text(
        'version: "1.1.0"\npolicies:\n  - id: "INV-FACT-GRAPH-NO-AGENT-SYNTHESIS"\n    threshold: 1\n',
        encoding="utf-8",
    )
    inv_dir = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "fact_inventory"
    inv_dir.mkdir(parents=True)
    (inv_dir / "ibm_role_episode_bundles.json").write_text(
        '{"a": "approved_by_graph_presence", "b": "approved_by_graph_presence"}\n',
        encoding="utf-8",
    )
    bad_count, bad_ceiling, bad_violations = scan_fact_inventory_graph_presence_ratchet(tmp_path)
    assert bad_count == 2 and bad_ceiling == 1
    assert len(bad_violations) == 1
    assert bad_violations[0]["code"] == "AGENT_SYNTHESIZED_GRAPH_PRESENCE_EXCEEDS_RATCHET"
