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
