from __future__ import annotations

import json
from pathlib import Path

from apps_rg.fact_inventory.graph_evolution_author_gate import author_gate_decision, candidate_digest
from apps_rg.fact_inventory.graph_evolution_candidate_intake import intake_graph_evolution_candidate
from apps_rg.fact_inventory.graph_evolution_candidate_projection import build_candidate_cluster_projection, load_ge_w5_candidate_projection_contract, validate_ge_w5_candidate_projection_contract
from apps_rg.fact_inventory.graph_evolution_graph_validation import validate_admitted_candidate_graph_version
from apps_rg.fact_inventory.graph_evolution_uwg_commit import GraphEvolutionUwgGateway, commit_author_approved_candidate
from tests.unit.apps_rg.l5_uwg_fixture import verified_l5_exit_metadata

ROOT = Path(__file__).resolve().parents[4]


def _fake_embedder(texts: list[str]):
    return ({"fallback_used": False, "vector_count": len(texts), "dimension": 1024, "device": "test"}, [[1.0] + [0.0] * 1023 for _ in texts])


def _version_and_receipt(tmp_path: Path):
    candidate = intake_graph_evolution_candidate({"assertion_text": "Built co-selling frameworks with SI and ISV partners.", "source_type": "base_resume", "proof_status": "proof_eligible", "source_document_id": "resume:2026-08", "source_span_ref": "resume:p1:bullet4", "source_excerpt": "Built co-selling frameworks with SI and ISV partners.", "source_file_sha256": "a" * 64, "proposed_skill_ids": ["skill_partner_co_selling"], "producer_run_id": "ge-w5-test"}, repo_root=ROOT)["candidate"]
    digest = candidate_digest(candidate)
    checks = {key: True for key in ("source_fidelity", "assertion_atomicity", "graph_linkage_fit", "claim_policy_fit")}
    reviews = [{"schema_version":"apps_rg.graph_evolution_author_review.v1","candidate_id":candidate["candidate_id"],"candidate_sha256":digest,"reviewer_ref":"human-reviewer://evidence","role":"EVIDENCE_REVIEWER","decision":"APPROVE","checks":checks,"rationale":"source reviewed"},{"schema_version":"apps_rg.graph_evolution_author_review.v1","candidate_id":candidate["candidate_id"],"candidate_sha256":digest,"reviewer_ref":"human-reviewer://steward","role":"GRAPH_STEWARD","decision":"APPROVE","checks":checks,"rationale":"graph reviewed"}]
    decision = author_gate_decision(candidate, reviews, repo_root=ROOT)["decision"]
    l5 = verified_l5_exit_metadata(request_id="ge-w5", run_id="ge-w5", trace_id="ge-w5")["l5_certification_packet_ref"]
    path = tmp_path / "candidate.json"
    committed = commit_author_approved_candidate(candidate, decision, repo_root=ROOT, candidate_version_path=path, l5_certification_ref=l5, gateway=GraphEvolutionUwgGateway())
    assert committed["route"] == "UWG_COMMITTED_CANDIDATE"
    version = json.loads(path.read_text())
    validated = validate_admitted_candidate_graph_version(version, repo_root=ROOT)
    assert validated["route"] == "GRAPH_VALIDATED"
    return version, validated["receipt"]


def _model():
    return {"model_id":"BAAI/bge-m3","revision":"test","artifact_sha256":"b" * 64,"dimension":1024,"normalization":"l2"}


def test_ge_w5_contract_locks_cluster_unit_and_no_activation():
    contract = load_ge_w5_candidate_projection_contract(ROOT)
    assert validate_ge_w5_candidate_projection_contract(contract) == []
    assert contract["retrieval_unit"]["per_node_vectors_forbidden"] is True


def test_rebuilds_full_candidate_universe_with_one_overlay_cluster(tmp_path: Path):
    version, receipt = _version_and_receipt(tmp_path)
    result = build_candidate_cluster_projection(version, receipt, repo_root=ROOT, output_dir=tmp_path / "projection", model_manifest=_model(), embedder=_fake_embedder)
    assert result["route"] == "PROJECTION_BUILT"
    assert result["cluster_count"] == 39
    registry = json.loads(Path(result["registry_path"]).read_text())
    projection = json.loads(Path(result["projection_path"]).read_text())
    assert len(registry["clusters"]) == len(projection["vectors"]) == 39
    assert registry["clusters"][-1]["cluster_kind"] == "candidate_assertion_overlay"
    assert registry["active_runtime_pointer_changed"] is False
    assert projection["activation_created"] is False


def test_rejects_runtime_fallback_before_writing_outputs(tmp_path: Path):
    version, receipt = _version_and_receipt(tmp_path)
    def fallback(texts): return ({"fallback_used": True, "vector_count":len(texts), "dimension":1024}, [[1.0]+[0.0]*1023 for _ in texts])
    result = build_candidate_cluster_projection(version, receipt, repo_root=ROOT, output_dir=tmp_path / "blocked", model_manifest=_model(), embedder=fallback)
    assert result["route"] == "BLOCKED"
    assert not (tmp_path / "blocked").exists()
