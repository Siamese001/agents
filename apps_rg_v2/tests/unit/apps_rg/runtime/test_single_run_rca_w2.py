"""Acceptance tests for canonical single-run W2 RCA rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.single_run_rca_w2 import emit_single_run_w2_canonical_rca


def _packet(path: Path) -> Path:
    lanes = [{"lane": f"lane-{index}"} for index in range(11)]
    packet = {
        "status": "PASS", "wave": "W1", "next_wave_authorized": True, "source_run_id": "e2e_test",
        "source_manifest_sha256": "sha256:source", "extracted_counts": {"generation_lanes": 11, "judges": 21, "contract_handoffs": 21},
        "verified_w5_artifacts": [{"artifact_ref": "i/w0.json", "verified": True}],
        "historical_run": {
            "historical_model_routes": {"apps_research": {"usage_event_count": 17, "successful_attempt_count": 3, "claude_usage_event_count": 0}, "apps_rg_generation": {
                "lane_count": 11, "target_claude_lane_count": 11, "actual_claude_lane_count": 0, "model_mismatch_lane_count": 11,
                "recorded_token_budget_failure_lane_count": 11, "recomputed_output_token_budget_failure_lane_count": 0,
                "token_accounting_false_failure_lane_count": 11, "lanes": lanes}},
            "historical_saved_judges": {"result_count": 21, "passing_result_count": 21, "actual_claude_judge_result_count": 0, "results": [{} for _ in range(21)]},
            "contract_handoffs": {"entries": [{} for _ in range(21)]},
            "l0_parallel": {"max_active_workers_observed": 5, "parallel_overlap_proven": True},
            "apps_eval": {"execution_complete": True, "verdict": "fail"},
            "l6": {"execution_complete": True, "binding_closure_status": "FAIL", "calibration_status": "NOT_MEASURED", "human_labels_present": False},
            "terminal": {"terminal_outcome": "BLOCKED_NON_PRODUCT", "x2_aggregation_status": "PASS"},
        },
    }
    path.write_text(json.dumps(packet) + "\n", encoding="utf-8")
    return path


def test_renders_canonical_rca_and_summary(tmp_path: Path) -> None:
    result = emit_single_run_w2_canonical_rca(w1_packet_path=_packet(tmp_path / "w1.json"), output_dir=tmp_path / "out")
    assert result["status"] == "PASS"
    assert result["root_causes"]["model_identity"]["affected_lanes"] == 11
    assert result["root_causes"]["token_accounting"]["recomputed_output_token_failures"] == 0
    assert "BLOCKED_NON_PRODUCT" in Path(result["summary_path"]).read_text(encoding="utf-8")


def test_rejects_model_route_count_drift(tmp_path: Path) -> None:
    packet = _packet(tmp_path / "w1.json")
    value = json.loads(packet.read_text(encoding="utf-8"))
    value["historical_run"]["historical_model_routes"]["apps_rg_generation"]["model_mismatch_lane_count"] = 10
    packet.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="model-route RCA"):
        emit_single_run_w2_canonical_rca(w1_packet_path=packet, output_dir=tmp_path / "out")
