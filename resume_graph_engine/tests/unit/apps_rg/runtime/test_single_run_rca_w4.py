"""Acceptance tests for W4 deterministic RCA verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.runtime.single_run_rca_w4 import verify_single_run_w4


def _seal(value: dict[str, object]) -> dict[str, object]:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return {**value, "semantic_digest": "sha256:" + hashlib.sha256(body).hexdigest()}


def _binding(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {"artifact_ref": path.name, "byte_length": len(payload), "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(), "semantic_digest": json.loads(payload)["semantic_digest"]}


def _inputs(root: Path) -> dict[str, Path]:
    source = root / "e2e_test"
    source.mkdir()
    (source / "saved.json").write_text("{}\n", encoding="utf-8")
    source_digest = _manifest(source)["content_sha256"]
    w5 = root / "w5"
    artifact = w5 / "i" / "artifact.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")
    artifact_row = {"artifact_ref": "i/artifact.json", "byte_length": len(artifact.read_bytes()), "sha256": "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest(), "verified": True}
    w0 = root / "w0.json"; w0.write_text(json.dumps(_seal({"status": "PASS", "wave": "W0", "source_run_id": source.name, "source_manifest_sha256": source_digest})) + "\n", encoding="utf-8")
    w1 = root / "w1.json"; w1.write_text(json.dumps(_seal({"status": "PASS", "wave": "W1", "source_run_id": source.name, "source_manifest_sha256": source_digest, "w0_freeze": _binding(w0), "extracted_counts": {"generation_lanes": 11, "judges": 21, "contract_handoffs": 21}, "verified_w5_artifacts": [artifact_row for _ in range(14)]})) + "\n", encoding="utf-8")
    w2 = root / "w2.json"; w2.write_text(json.dumps(_seal({"status": "PASS", "wave": "W2", "source_run_id": source.name, "source_manifest_sha256": source_digest, "w1_packet": _binding(w1), "root_causes": {"model_identity": {"affected_lanes": 11}, "token_accounting": {"affected_lanes": 11, "recomputed_output_token_failures": 0}}, "terminal_state": {"terminal_outcome": "BLOCKED_NON_PRODUCT", "production_authority_granted": False, "publication_allowed": False}})) + "\n", encoding="utf-8")
    w3 = root / "w3.json"; w3.write_text(json.dumps(_seal({"status": "PASS", "wave": "W3", "source_run_id": source.name, "canonical_rca": _binding(w2), "product_authority": {"status": "DENIED"}, "w6_contract": {"status": "AUTHORIZED_EVIDENCE_ACCEPTANCE_ONLY", "executed": False}})) + "\n", encoding="utf-8")
    return {"source": source, "w0": w0, "w1": w1, "w2": w2, "w3": w3, "w5": w5}


def _manifest(source: Path) -> dict[str, object]:
    row = source / "saved.json"
    content = {"directories": [], "files": [{"path": "saved.json", "byte_length": row.stat().st_size, "sha256": "sha256:" + hashlib.sha256(row.read_bytes()).hexdigest()}]}
    return {"content_sha256": "sha256:" + hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()}


def test_verifies_complete_chain(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    result = verify_single_run_w4(source_run=paths["source"], w0_freeze_path=paths["w0"], w1_packet_path=paths["w1"], w2_manifest_path=paths["w2"], w3_decision_path=paths["w3"], w5_evidence_root=paths["w5"], output_dir=tmp_path / "out", source_manifest_builder=_manifest)
    assert result["status"] == "PASS"
    assert result["verified_w5_artifact_count"] == 14
    assert all(result["checks"].values())


def test_rejects_interwave_binding_drift(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    value = json.loads(paths["w3"].read_text(encoding="utf-8"))
    value["canonical_rca"]["sha256"] = "sha256:wrong"
    paths["w3"].write_text(json.dumps(_seal({key: value[key] for key in value if key != "semantic_digest"})) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="w3_binds_w2"):
        verify_single_run_w4(source_run=paths["source"], w0_freeze_path=paths["w0"], w1_packet_path=paths["w1"], w2_manifest_path=paths["w2"], w3_decision_path=paths["w3"], w5_evidence_root=paths["w5"], output_dir=tmp_path / "out", source_manifest_builder=_manifest)
