"""Non-mock End-to-End Test for DIE-Parity QRELS Studio, Coverage Gate, and 4-Simplex Calibration."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

from apps_eval.qrels.qrels_human_store import ExternalQrelsHumanStore
from apps_eval.qrels.qrels_rubric_contract import (
    BLIND_FORBIDDEN_FIELDS,
    load_and_verify_qrels_rubric,
)
from apps_eval.qrels.qrels_studio_server import create_qrels_studio_server
from apps_eval.qrels.weight_calibration import (
    CANONICAL_QRELS_RRF_WEIGHTS,
    run_holdout_isolated_weight_calibration,
)
from ops_scripts.build_qrels_benchmark import (
    _assign_calibrated_grade,
    _extract_claim_focus,
    _extract_employer,
    _resolve_sqlite_path,
)
from ops_scripts.qrels_calibration_cli import main as qrels_cli_main
from tools.audit_qrels_coverage import audit_qrels_coverage
from tools.retrieval_surface_auditor import run_retrieval_surface_audit

REPO_ROOT = Path(__file__).resolve().parents[2]
QRELS_DIR = REPO_ROOT / "data" / "qrels"
RUBRIC_PATH = REPO_ROOT / "config" / "governance" / "external_qrels_rubric_v1.json"


def test_qrels_end_to_end_studio_coverage_simplex_and_retrieval_auditor(tmp_path: Path) -> None:
    # 1. Verify sealed external QRELS rubric & tracked 50-query corpus artifacts
    rubric = load_and_verify_qrels_rubric(RUBRIC_PATH)
    assert rubric["rubric_id"] == "external_qrels_rubric_v1"

    pool_path = QRELS_DIR / "qrels_authentic_candidate_pool.v1.json"
    part_path = QRELS_DIR / "qrels_partitions.v1.json"
    gt_path = QRELS_DIR / "qrels_independent_ground_truth.v1.json"
    wt_path = QRELS_DIR / "qrels_weight_calibration_results.v1.json"
    for fp in (pool_path, part_path, gt_path, wt_path):
        assert fp.is_file(), f"Missing tracked QRELS artifact: {fp}"

    # 2. Verify fail-closed coverage gate on tracked 50-query 4-channel corpus
    cov = audit_qrels_coverage(part_path, gt_path, pool_path)
    assert cov["gate_status"] == "PASS", cov["failures"]
    assert cov["ground_truth_audit"]["total_queries"] == 50
    assert cov["ground_truth_audit"]["total_candidates_judged"] >= 1000
    assert cov["ground_truth_audit"]["unanswerable_probes"] == 5
    assert cov["family_leakage_audit"]["has_leakage"] is False
    assert cov["kappa_calibration_audit"]["is_valid"] is True
    assert cov["kappa_calibration_audit"]["cohens_kappa"] >= 0.80

    # 3. Verify holdout-isolated 1,771-point 4-simplex calibration live
    gt_data = json.loads(gt_path.read_text(encoding="utf-8"))
    part_data = json.loads(part_path.read_text(encoding="utf-8"))
    live_wt = run_holdout_isolated_weight_calibration(
        gt_data, part_data, canonical_weights=CANONICAL_QRELS_RRF_WEIGHTS
    )
    assert live_wt["is_validated"] is True
    assert live_wt["verdict"] == "VALIDATED"
    assert live_wt["total_configurations_evaluated"] == 1771
    assert live_wt["tuning_holdout_overlap"] == []
    assert live_wt["abstention_calibration"]["false_abstains"] == 0
    assert live_wt["abstention_calibration"]["negative_probe_abstention_rate"] == 1.0
    holdout = live_wt["final_holdout_evaluation"]
    assert holdout["canonical_hybrid"]["mean_ndcg_10"] > holdout["bm25_only"]["mean_ndcg_10"]
    assert holdout["canonical_hybrid"]["mean_ndcg_10"] > holdout["dense_only"]["mean_ndcg_10"]

    # 4. Serve live Pure-White (#ffffff) QRELS Studio against the real tracked pool
    store_path = tmp_path / "e2e_qrels_store.json"
    server = create_qrels_studio_server(
        pool_path,
        store_path=store_path,
        rubric_path=RUBRIC_PATH,
        port=0,
        annotator_id="amit.ayer",
        seed=42,
        max_items=6,
    )
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            page = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "no-store" in resp.headers.get("Cache-Control", "")
            assert "background: #ffffff !important" in page
            assert "Quick Start Guide" in page
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5) as resp:
            state = json.loads(resp.read().decode("utf-8"))
            assert len(state["items"]) == 6
            first = state["items"][0]
            assert not (set(first.keys()) & BLIND_FORBIDDEN_FIELDS)

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/grade",
            data=json.dumps(
                {
                    "pair_id": first["pair_id"],
                    "query_id": first["query_id"],
                    "record_id": first["record_id"],
                    "surface": first["surface"],
                    "topic_family": first["topic_family"],
                    "partition": first["partition"],
                    "artifact_sha256": first["artifact_sha256"],
                    "relevance_grade": 2,
                    "atomic_checks": {"core_answers_query": True, "not_boilerplate_stub": True},
                    "notes": "Verified supporting evidence",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            saved = json.loads(resp.read().decode("utf-8"))
            assert saved["status"] == "PASS"

        store = ExternalQrelsHumanStore(store_path, rubric_path=RUBRIC_PATH)
        assert store.verify_integrity() is True
        assert len(store.load_records()) == 1
    finally:
        server.shutdown()
        server.server_close()

    # 5. Exercise CLI audit + 1-by-1 blind chat panel + benchmark helper functions
    assert qrels_cli_main(["qrels-audit", "--partitions", str(part_path), "--ground-truth", str(gt_path), "--pool", str(pool_path)]) == 0
    assert qrels_cli_main(["qrels-anchor-chat", "--pool", str(pool_path), "--query-id", "q_su_01", "--json"]) == 0
    assert _resolve_sqlite_path(REPO_ROOT).is_file()
    assert _extract_employer("[Unit] engagement_episode · Slalom · epoch | [Claim] Built AI") == "Slalom"
    assert "Built AI" in _extract_claim_focus("[Unit] x · Slalom | [Claim] Built AI.")
    g3, _ = _assign_calibrated_grade({"answerable": True, "query_text": "test"}, {"is_verified_target": True, "core_statement": "test", "employer": "Slalom"}, "Slalom")
    assert g3 == 3

    # 6. Verify retrieval_surface_auditor passes all 7 pillars including live QRELS gate
    ret_audit = run_retrieval_surface_audit(REPO_ROOT, read_only=True)
    assert ret_audit["is_clean"] is True, ret_audit["gaps"]
    assert ret_audit["passing_pillars"] == 7
    p3 = ret_audit["pillars"]["pillar_3_graphdb_traversal_and_embeddings"]
    assert p3["qrels_coverage_passed"] is True
    assert p3["qrels_weight_verdict"] == "VALIDATED"
