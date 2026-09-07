"""Acceptance tests for W3 non-product RCA semantics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.single_run_rca_w3 import emit_single_run_w3_acceptance_decision


def _rca(path: Path) -> Path:
    value = {
        "status": "PASS", "wave": "W2", "source_run_id": "e2e_test", "source_manifest_sha256": "sha256:source",
        "terminal_state": {"pipeline_reconstructed": True, "terminal_outcome": "BLOCKED_NON_PRODUCT", "production_authority_granted": False, "publication_allowed": False},
        "root_causes": {"model_identity": {"affected_lanes": 11}},
        "timeline": {"post_runtime": {"apps_eval_verdict": "fail", "l6_binding_closure_status": "FAIL", "human_labels_present": False, "l6_calibration_status": "NOT_MEASURED"}},
    }
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    return path


def test_seals_evidence_only_w6_contract(tmp_path: Path) -> None:
    result = emit_single_run_w3_acceptance_decision(w2_manifest_path=_rca(tmp_path / "w2.json"), output_dir=tmp_path / "out")
    assert result["status"] == "PASS"
    assert result["evidence_acceptance"]["status"] == "PIPELINE_RECONSTRUCTED"
    assert result["product_authority"]["status"] == "DENIED"
    assert result["w6_contract"]["status"] == "AUTHORIZED_EVIDENCE_ACCEPTANCE_ONLY"
    assert result["w6_contract"]["executed"] is False


def test_refuses_to_accept_a_product_authorized_rca(tmp_path: Path) -> None:
    rca = _rca(tmp_path / "w2.json")
    value = json.loads(rca.read_text(encoding="utf-8"))
    value["terminal_state"]["production_authority_granted"] = True
    rca.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-product"):
        emit_single_run_w3_acceptance_decision(w2_manifest_path=rca, output_dir=tmp_path / "out")
