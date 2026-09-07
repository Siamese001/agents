"""Acceptance tests for W5 zero-LLM closeout."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.runtime.single_run_rca_w5 import emit_single_run_w5_zero_llm_closeout


def _seal(value: dict[str, object]) -> dict[str, object]:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return {**value, "semantic_digest": "sha256:" + hashlib.sha256(body).hexdigest()}


def _write(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(_seal(value)) + "\n", encoding="utf-8")
    return path


def _inputs(root: Path) -> dict[str, Path]:
    run_id = "e2e_test"
    digest = "sha256:source"
    w2 = _write(root / "w2.json", {"status": "PASS", "source_run_id": run_id, "source_manifest_sha256": digest, "terminal_state": {"terminal_outcome": "BLOCKED_NON_PRODUCT", "production_authority_granted": False}})
    w3 = _write(root / "w3.json", {"status": "PASS", "source_run_id": run_id, "w6_contract": {"status": "AUTHORIZED_EVIDENCE_ACCEPTANCE_ONLY", "executed": False}})
    w4 = _write(root / "w4.json", {"status": "PASS", "source_run_id": run_id, "next_wave_authorized": True, "checks": {"identity": True, "authority": True}})
    counters = {"provider_calls": 0, "model_calls": 0, "judge_calls": 0, "embedding_calls": 0, "network_attempts": 0, "subprocess_attempts": 0}
    guard = _write(root / "guard.json", {"status": "PASS", "source_unchanged": True, "attempt_counters": counters})
    return {"w2": w2, "w3": w3, "w4": w4, "guard": guard}


def test_closes_verified_zero_llm_chain(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    counters = {"provider_calls": 0, "model_calls": 0, "judge_calls": 0, "embedding_calls": 0, "network_attempts": 0, "subprocess_attempts": 0}
    result = emit_single_run_w5_zero_llm_closeout(w2_manifest_path=paths["w2"], w3_decision_path=paths["w3"], w4_verification_path=paths["w4"], w5_guard_receipt_path=paths["guard"], finalization_counters=counters, output_dir=tmp_path / "out")
    assert result["status"] == "PASS"
    assert result["scope_complete"] is True
    assert result["w6_authorized"] is True
    assert result["production_authority_granted"] is False


def test_rejects_nonzero_provider_counter(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    counters = {"provider_calls": 1, "model_calls": 0, "judge_calls": 0, "embedding_calls": 0, "network_attempts": 0, "subprocess_attempts": 0}
    with pytest.raises(ValueError, match="prerequisites"):
        emit_single_run_w5_zero_llm_closeout(w2_manifest_path=paths["w2"], w3_decision_path=paths["w3"], w4_verification_path=paths["w4"], w5_guard_receipt_path=paths["guard"], finalization_counters=counters, output_dir=tmp_path / "out")
