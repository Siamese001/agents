"""Acceptance tests for single-run W1 evidence extraction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.runtime.single_run_rca_w1 import emit_single_run_w1_evidence_packet


def _sha(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _inputs(root: Path) -> tuple[Path, Path, Path]:
    evidence_root = root / "w5"
    artifact = evidence_root / "i" / "case" / "w0.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"status":"PASS"}\n', encoding="utf-8")
    payload = artifact.read_bytes()
    run_id = "e2e_test"
    freeze = root / "freeze.json"
    freeze.write_text(json.dumps({"status": "PASS", "wave": "W0", "next_wave_authorized": True, "source_run_id": run_id, "source_manifest_sha256": "sha256:source"}) + "\n", encoding="utf-8")
    case = {
        "source_run_id": run_id, "status": "PASS", "artifacts": [{"artifact_ref": "i/case/w0.json", "artifact_role": "w0", "byte_length": len(payload), "sha256": _sha(payload)}],
        "checks": {"all_docs_semantic": True},
        "l0_parallel": {"lane_results": [{"artifact_replay_complete": True} for _ in range(11)]},
        "historical_saved_judges": {"results": [{} for _ in range(21)], "passing_result_count": 21},
        "contract_handoffs": {"entries": [{} for _ in range(21)]},
        "apps_eval": {"execution_complete": True, "verdict": "fail"},
        "l6": {"execution_complete": True, "binding_closure_status": "FAIL"},
        "terminal": {"terminal_closed": True, "terminal_outcome": "BLOCKED_NON_PRODUCT", "x2_aggregation_status": "PASS"},
    }
    integrated = evidence_root / "integrated.json"
    integrated.write_text(json.dumps({"status": "PASS", "cases": [case]}) + "\n", encoding="utf-8")
    return freeze, integrated, evidence_root


def test_extracts_one_complete_bound_case(tmp_path: Path) -> None:
    freeze, integrated, evidence_root = _inputs(tmp_path)
    result = emit_single_run_w1_evidence_packet(w0_freeze_path=freeze, integrated_manifest_path=integrated, w5_evidence_root=evidence_root, output_dir=tmp_path / "output")
    assert result["status"] == "PASS"
    assert result["extracted_counts"] == {"generation_lanes": 11, "judges": 21, "contract_handoffs": 21}
    assert result["verified_w5_artifacts"][0]["verified"] is True
    assert result["historical_run"]["terminal"]["terminal_outcome"] == "BLOCKED_NON_PRODUCT"


def test_rejects_missing_bound_artifact(tmp_path: Path) -> None:
    freeze, integrated, evidence_root = _inputs(tmp_path)
    (evidence_root / "i" / "case" / "w0.json").unlink()
    with pytest.raises(ValueError, match="missing"):
        emit_single_run_w1_evidence_packet(w0_freeze_path=freeze, integrated_manifest_path=integrated, w5_evidence_root=evidence_root, output_dir=tmp_path / "output")
