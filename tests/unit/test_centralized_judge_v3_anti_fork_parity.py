"""Unit tests enforcing centralized `core-governance` Judge v3 anti-fork parity and receipt-gate globs."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml

from apps_eval.graders.judge.external_rubric_store import VALID_JUDGE_SURFACES
from tools.audit_multi_ssot_judge_gate_drift import audit_multi_ssot_judge_gate_drift
from tools.pr_governance_core.judge_receipt_gate import (
    DEFAULT_JUDGE_GOVERNED_SURFACES,
    verify_diff_judge_receipts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_all_five_core_governance_bridge_accessors_wired_in_apps_eval() -> None:
    """Verify every accessor in `_core_governance_bridge.py` has live AST call sites in `apps_eval/graders/judge/`."""
    required = {
        "get_judge_v3_rigor_engine",
        "get_judge_ide_router_v3",
        "get_judge_blind_protocol_v3",
        "get_judge_disjoint_jury_v3",
        "get_studio_session_contract",
    }
    called: set[str] = set()
    judge_dir = REPO_ROOT / "apps_eval" / "graders" / "judge"
    for py_file in sorted(judge_dir.glob("*.py")):
        if py_file.name == "_core_governance_bridge.py":
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in required:
                called.add(node.func.id)
    assert called == required


def test_policy_registry_codifies_centralized_judge_v3_and_14px_studio_invariants() -> None:
    """Verify `policy_registry.yaml` codifies 14px Studio, centralized Judge v3 core, and non-degenerate weights."""
    reg_doc = yaml.safe_load((REPO_ROOT / "config" / "governance" / "policy_registry.yaml").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in reg_doc["policies"]}
    assert "14px" in by_id["INV-CENTRALIZED-LABELING-STUDIO-ONLY"]["title"]
    assert "18px" not in by_id["INV-CENTRALIZED-LABELING-STUDIO-ONLY"]["title"]
    assert by_id["INV-CENTRALIZED-JUDGE-V3-CORE"]["enforcer"] == "tools/audit_multi_ssot_judge_gate_drift.py"
    assert by_id["INV-JUDGE-NON-DEGENERATE-WEIGHTS"]["enforcer"] == "tools/validate_judge_rubrics_v3.py"


def test_all_12_enabled_profiles_in_valid_surfaces_and_multi_ssot_audit_passes() -> None:
    """Verify 100% of enabled Judge v3 profiles are valid human store surfaces and pass multi-SSOT audit."""
    manifest = json.loads((REPO_ROOT / "config" / "governance" / "judge_rubrics_v3.json").read_text(encoding="utf-8"))
    enabled = set(manifest["enabled_profiles"])
    assert len(enabled) == 12
    assert enabled.issubset(VALID_JUDGE_SURFACES)

    report = audit_multi_ssot_judge_gate_drift(REPO_ROOT)
    assert report["status"] == "PASS", report["violations"]
    assert report["vectors"]["V8_JUDGE_V3_CLEAN_SLATE_PARITY"] == "PASS"


def test_expanded_judge_receipt_gate_covers_active_v3_judge_and_section_paths(tmp_path: Path) -> None:
    """Verify `DEFAULT_JUDGE_GOVERNED_SURFACES` triggers on active v2 sections, judges, coherence, LIC, and research."""
    sample_paths = [
        "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_v2/blind_judge_and_loop.py",
        "resume_graph_engine/src/apps_rg/runtime/judges/v3_section_judge.py",
        "resume_graph_engine/src/apps_rg/runtime/assembly/full_resume_llm_coherence.py",
        "outreach_engine/src/apps_lic/judges/ide_cli_judge.py",
        "outreach_engine/src/apps_lic/judges/evaluator_pkg/x1d_quorum.py",
        "apps_research/engines/judges/v3_brief_judge.py",
    ]
    res = verify_diff_judge_receipts(sample_paths, tmp_path, surfaces=DEFAULT_JUDGE_GOVERNED_SURFACES)
    assert res["status"] == "FAIL"
    triggered_ids = {s["surface_id"] for s in res["triggered_surfaces"]}
    assert triggered_ids == {
        "apps_rg_executive_summary",
        "apps_rg_whole_coherence",
        "apps_lic_outreach_sequence",
        "apps_research_company_brief",
    }
