"""Acceptance tests for W6 local evidence acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.runtime.single_run_rca_w6 import emit_single_run_w6_local_acceptance


def _closeout(path: Path) -> Path:
    zero = {"provider_calls": 0, "model_calls": 0, "judge_calls": 0, "embedding_calls": 0, "network_attempts": 0, "subprocess_attempts": 0}
    value = {
        "status": "PASS", "scope_complete": True, "source_run_id": "e2e_test", "source_manifest_sha256": "sha256:source",
        "w6_authorized": True, "w6_contract": "EVIDENCE_ACCEPTANCE_ONLY", "terminal_state": "BLOCKED_NON_PRODUCT",
        "production_authority_granted": False, "publication_allowed": False,
        "zero_llm_runtime": {"primary_guard_counters": zero, "finalization_guard_counters": zero},
    }
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    path.write_text(json.dumps({**value, "semantic_digest": "sha256:" + hashlib.sha256(body).hexdigest()}) + "\n", encoding="utf-8")
    return path


def test_accepts_local_evidence_only(tmp_path: Path) -> None:
    result = emit_single_run_w6_local_acceptance(
        w5_closeout_path=_closeout(tmp_path / "w5.json"), branch_name="codex/test", pre_acceptance_head="a" * 40,
        verified_commit_ids=["1" * 7, "2" * 7, "3" * 7, "4" * 7, "5" * 7, "6" * 7], output_dir=tmp_path / "out",
    )
    assert result["status"] == "PASS"
    assert result["acceptance_status"] == "LOCAL_EVIDENCE_ACCEPTED"
    assert result["publication_allowed"] is False


def test_rejects_missing_commit_proof(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="prerequisites"):
        emit_single_run_w6_local_acceptance(
            w5_closeout_path=_closeout(tmp_path / "w5.json"), branch_name="codex/test", pre_acceptance_head="a" * 40,
            verified_commit_ids=["1" * 7], output_dir=tmp_path / "out",
        )
