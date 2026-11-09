"""Verification of live multi-hop resume graph traversal in Agents sidecar prompts and probe runner."""
from __future__ import annotations

from pathlib import Path

from tools.run_resume_graph_traversal_probe import run_resume_graph_traversal_probe
from tools.validate_sidecar_separation import validate_sidecar_separation


def test_resume_graph_traversal_probe_executes_multi_hop_sandbox_walk() -> None:
    receipt = run_resume_graph_traversal_probe(max_paths=100)
    assert receipt["status"] == "PASS"
    assert receipt["direct_graph_traversal"] is True
    assert receipt["integrity_check"] == "ok"
    assert receipt["two_hop_path_count"] > 0
    assert receipt["domain_skill_evidence_path_count"] > 0
    assert receipt["research_max_hops"] == 2
    assert len(receipt["sample_two_hop_nodes"]) == 3


def test_agents_retrieval_and_outreach_sidecar_prompts_bind_live_graph_probe() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    prompts_dir = repo_root / "automations" / "prompts"

    for fname in (
        "agents_research_retrieval_surface_agent.md",
        "agents_domain_applications_pipeline_agent.md",
    ):
        text = (prompts_dir / fname).read_text(encoding="utf-8")
        assert "python3 tools/run_resume_graph_traversal_probe.py" in text
        assert "direct_graph_traversal" in text

    sep = validate_sidecar_separation(repo_root=repo_root)
    assert sep["is_clean"] is True, sep["violations"]
