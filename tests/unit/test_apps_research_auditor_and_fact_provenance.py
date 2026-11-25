"""Counterfactual rigor tests for Agent 3 (Fact Provenance / Graph Hygiene) and Agent 6 (apps_research Auditor)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from apps_research.engines.base_research_engine import BaseResearchEngine
from apps_research.integrations.observability_adapter import ObservabilityAdapter
from apps_research.runtime.profile_builder_adapter import (
    build_app_runtime_contract,
    exit_finalize_apps_research_ingress,
    pa_assemble_apps_research,
    parse_payload,
)
from tools.apps_research_auditor import run_apps_research_audit
from tools.audit_graph_hygiene_and_consolidation import (
    resolve_graph_db_path,
    run_pre_promotion_regression_gates,
)
from tools.audit_resume_fact_provenance import audit_fact_provenance

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_apps_research_auditor_passes_all_6_pillars_and_public_adapters_load() -> None:
    report = run_apps_research_audit(REPO_ROOT, read_only=True)
    assert report["status"] == "PASS", report["gaps"]
    assert report["is_clean"] is True
    assert report["passing_pillars"] == 6
    assert report["pillars"]["pillar_3_injection_airlock"]["injection_signals_detected"]
    assert report["pillars"]["pillar_6_handoffs_and_ast_hygiene"]["scanned_files"] >= 100

    # Exercise public research adapters directly
    assert BaseResearchEngine is not None
    assert ObservabilityAdapter is not None
    assert callable(parse_payload)
    assert callable(exit_finalize_apps_research_ingress)
    assert callable(pa_assemble_apps_research)
    assert callable(build_app_runtime_contract)


def test_fact_provenance_general_numeric_entailment_catches_unverified_numbers(tmp_path: Path) -> None:
    live_rep = audit_fact_provenance(REPO_ROOT)
    assert live_rep["status"] == "PASS", live_rep["violations"]

    # Negative control: inject an arbitrary unentailed metric ("26%" / "$4.7M") not in FORBIDDEN_UNVERIFIED_TOKENS_RE
    sandbox = tmp_path / "prov_sandbox"
    rg_base = REPO_ROOT / "resume_graph_engine" / "src" / "apps_rg"
    dst_base = sandbox / "resume_graph_engine" / "src" / "apps_rg"
    shutil.copytree(rg_base / "resume" / "base", dst_base / "resume" / "base")
    shutil.copytree(rg_base / "fact_inventory", dst_base / "fact_inventory")

    bundle_file = sorted((dst_base / "fact_inventory").glob("*_role_episode_bundles.json"))[0]
    doc = json.loads(bundle_file.read_text(encoding="utf-8"))
    nodes = doc.get("metric_outcome_nodes") or {}
    if isinstance(nodes, dict):
        for _k, v in nodes.items():
            if isinstance(v, dict) and v.get("approved") and v.get("support_level") == "verified_base_resume":
                v["metric"] = "26% synthetic margin lift ($4.7M)"
                break
    bundle_file.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    bad_rep = audit_fact_provenance(sandbox)
    assert bad_rep["status"] == "FAIL"
    assert any(v["code"] == "UNENTAILED_NUMERIC_TOKEN_IN_APPROVED_METRIC" for v in bad_rep["violations"])


def test_graph_hygiene_pre_promotion_gate_strict_zero_debt_detects_open_debt() -> None:
    db_path = resolve_graph_db_path(REPO_ROOT)
    assert db_path.is_file()
    gate = run_pre_promotion_regression_gates(db_path, strict_zero_debt=True)
    topo = gate["topology_non_regression"]
    assert "exact_skill_twins_count" in topo
    if topo["exact_skill_twins_count"] > 0 or topo["stranded_verified_metrics_count"] > 0:
        assert topo["status"] == "FAIL"
        assert gate["status"] == "FAIL"
