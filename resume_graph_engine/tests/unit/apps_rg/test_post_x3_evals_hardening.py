"""Unit tests verifying Wave 4 post-X3, evals, and observability hardening."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    import pytest
except ModuleNotFoundError:
    class _MonkeyPatchShim:
        def __init__(self) -> None:
            self._env_backup = dict(os.environ)

        def setenv(self, key: str, val: str) -> None:
            os.environ[key] = val

        def delenv(self, key: str, raising: bool = True) -> None:
            os.environ.pop(key, None)

        def undo(self) -> None:
            os.environ.clear()
            os.environ.update(self._env_backup)

    class _PytestShim:
        MonkeyPatch = _MonkeyPatchShim

    pytest = _PytestShim()  # type: ignore[assignment]

from apps_rg.runtime.c0.c02_fact_vector_ingest import INGEST_RECEIPT_NAME
from apps_rg.runtime.post_x3_completion import (
    _complete_fact_vector_writeback_after_x3,
    _emit_l6_section_apps_eval_bindings,
)


def test_post_x3_deferred_promotion_falls_back_to_repo_cache_when_chroma_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When CHROMA_PERSIST_DIR is unset, deferred vector promotion uses default repo cache rather than failing."""
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)

    artifact_dir = tmp_path / "run_deferred"
    artifact_dir.mkdir(parents=True)

    # Create dummy ingest receipt so candidate_run_ids has an item
    ingest_dir = artifact_dir / "lanes" / "competencies"
    ingest_dir.mkdir(parents=True)
    (ingest_dir / INGEST_RECEIPT_NAME).write_text(
        json.dumps({"run_id": "run_candidate_1"}),
        encoding="utf-8",
    )

    result = {
        "x3_disposition": "X3D_ALLOW_FINISH",
    }

    mock_promotion = {
        "status": "PASS",
        "reason": "promoted",
        "promoted_count": 5,
        "uwg": {"status": "ADMITTED"},
        "retrieval_proof": {"status": "PASS"},
    }

    with patch(
        "apps_rg.runtime.c0.fact_vector_write_back.promote_staged_fact_vectors",
        return_value=mock_promotion,
    ):
        payload = _complete_fact_vector_writeback_after_x3(
            artifact_dir=artifact_dir,
            result=result,
        )

    assert payload.get("status") == "PASS"
    assert payload.get("chroma_path") is not None
    assert "chromadb" in str(payload.get("chroma_path"))
    assert len(payload.get("promotions", [])) == 1
    assert payload["promotions"][0]["status"] == "PASS"


def test_post_x3_deferred_promotion_uses_explicit_chroma_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When CHROMA_PERSIST_DIR is explicitly configured, deferred vector promotion uses that path."""
    custom_chroma = tmp_path / "custom_chroma"
    custom_chroma.mkdir()
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(custom_chroma))

    artifact_dir = tmp_path / "run_explicit_chroma"
    artifact_dir.mkdir(parents=True)

    ingest_dir = artifact_dir / "lanes" / "competencies"
    ingest_dir.mkdir(parents=True)
    (ingest_dir / INGEST_RECEIPT_NAME).write_text(
        json.dumps({"run_id": "run_candidate_2"}),
        encoding="utf-8",
    )

    mock_promotion = {
        "status": "PASS",
        "reason": "promoted",
        "promoted_count": 2,
        "uwg": {"status": "ADMITTED"},
        "retrieval_proof": {"status": "PASS"},
    }

    with patch(
        "apps_rg.runtime.c0.fact_vector_write_back.promote_staged_fact_vectors",
        return_value=mock_promotion,
    ):
        payload = _complete_fact_vector_writeback_after_x3(
            artifact_dir=artifact_dir,
            result={"x3_disposition": "X3D_ALLOW_FINISH"},
        )

    assert payload.get("status") == "PASS"
    assert payload.get("chroma_path") == str(custom_chroma)


def test_post_x3_deferred_promotion_empty_when_no_candidates(tmp_path: Path) -> None:
    """When no ingest receipts exist, returns status EMPTY."""
    artifact_dir = tmp_path / "run_no_candidates"
    artifact_dir.mkdir(parents=True)

    payload = _complete_fact_vector_writeback_after_x3(
        artifact_dir=artifact_dir,
        result={"x3_disposition": "X3D_ALLOW_FINISH"},
    )
    assert payload.get("status") == "EMPTY"
    assert payload.get("reason") == "no_deferred_grounded_fact_vectors"


def test_post_x3_deferred_promotion_skipped_when_mode_not_deferred(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When APPS_RG_FACT_VECTOR_PROMOTION_MODE is not deferred, returns SKIPPED."""
    monkeypatch.setenv("APPS_RG_FACT_VECTOR_PROMOTION_MODE", "immediate")

    artifact_dir = tmp_path / "run_immediate"
    artifact_dir.mkdir(parents=True)
    ingest_dir = artifact_dir / "lanes" / "competencies"
    ingest_dir.mkdir(parents=True)
    (ingest_dir / INGEST_RECEIPT_NAME).write_text(
        json.dumps({"run_id": "run_candidate_3"}),
        encoding="utf-8",
    )

    payload = _complete_fact_vector_writeback_after_x3(
        artifact_dir=artifact_dir,
        result={"x3_disposition": "X3D_ALLOW_FINISH"},
    )
    assert payload.get("status") == "SKIPPED"
    assert payload.get("reason") == "promotion_mode_not_deferred"


def test_l6_grain_parity_summary_tracks_whole_run_rows(tmp_path: Path) -> None:
    """L6 grain parity summary accurately tracks both section-level and whole-run scorecard rows."""
    artifact_dir = tmp_path / "run_eval"
    artifact_dir.mkdir(parents=True)

    # Mock eval_record with 2 section rows and 2 whole-run (unassigned) rows
    scorecard_rows = [
        {"row_id": "r1", "lane_id": "competencies", "required": True},
        {"row_id": "r2", "lane_id": "competencies", "required": True},
        {"row_id": "r3", "lane_id": "", "grader_id": "ats_format_grader", "required": True},
        {"row_id": "r4", "lane_id": None, "grader_id": "page_budget_grader", "required": True},
    ]
    eval_record = SimpleNamespace(
        record_id="eval_001",
        scorecard=SimpleNamespace(scorecard_rows=scorecard_rows),
        artifact_paths={"eval_record": "eval_record.json", "scorecard_rows": "scorecard.json"},
    )

    result = _emit_l6_section_apps_eval_bindings(
        artifact_dir=artifact_dir,
        eval_record=eval_record,
    )

    summary = result.get("l6_section_apps_eval_bindings_summary", {})
    assert summary.get("scorecard_rows_total") == 4
    assert summary.get("whole_run_scorecard_rows_count") == 2
    assert summary.get("sections_total") == 1  # competencies


def test_l6_grain_parity_reports_failure_when_package_missing(tmp_path: Path) -> None:
    """When a required section lacks an L6 shadow eval package, grain parity reports FAIL."""
    artifact_dir = tmp_path / "run_eval_missing"
    artifact_dir.mkdir(parents=True)

    scorecard_rows = [
        {"row_id": "r1", "lane_id": "competencies", "required": True},
    ]
    eval_record = SimpleNamespace(
        record_id="eval_002",
        scorecard=SimpleNamespace(scorecard_rows=scorecard_rows),
        artifact_paths={"eval_record": "eval_record.json", "scorecard_rows": "scorecard.json"},
    )

    result = _emit_l6_section_apps_eval_bindings(
        artifact_dir=artifact_dir,
        eval_record=eval_record,
    )

    summary = result.get("l6_section_apps_eval_bindings_summary", {})
    assert summary.get("grain_parity_status") == "FAIL"
    assert summary.get("apps_eval_rows_bound") is False
    assert result.get("apps_eval_rows_bound") is False


def test_post_x3_deferred_promotion_fails_when_chroma_cache_mkdir_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When CHROMA_PERSIST_DIR is unset and fallback dir creation fails, report FAIL with descriptive reason."""
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)

    artifact_dir = tmp_path / "run_mkdir_fail"
    artifact_dir.mkdir(parents=True)

    ingest_dir = artifact_dir / "lanes" / "competencies"
    ingest_dir.mkdir(parents=True)
    (ingest_dir / INGEST_RECEIPT_NAME).write_text(
        json.dumps({"run_id": "run_candidate_mkdir_fail"}),
        encoding="utf-8",
    )

    with patch.object(Path, "mkdir", side_effect=OSError("disk read only")):
        payload = _complete_fact_vector_writeback_after_x3(
            artifact_dir=artifact_dir,
            result={"x3_disposition": "X3D_ALLOW_FINISH"},
        )

    assert payload.get("status") == "FAIL"
    assert "CHROMA_PERSIST_DIR unset and cache dir creation failed" in str(payload.get("reason"))


def test_post_x3_deferred_promotion_no_candidate_runs_skips(tmp_path: Path) -> None:
    """When candidate_run_ids is empty, fact vector writeback returns cleanly without promotions."""
    artifact_dir = tmp_path / "run_no_candidates"
    artifact_dir.mkdir(parents=True)

    payload = _complete_fact_vector_writeback_after_x3(
        artifact_dir=artifact_dir,
        result={"x3_disposition": "X3D_ALLOW_FINISH"},
    )

    assert payload.get("candidate_run_ids") == []
    assert payload.get("promotions") == []
    assert "status" not in payload or payload.get("status") != "FAIL"


class TestPostX3EvalsHardening(unittest.TestCase):
    def test_post_x3_deferred_promotion_falls_back_to_repo_cache(self) -> None:
        mp = pytest.MonkeyPatch()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                test_post_x3_deferred_promotion_falls_back_to_repo_cache_when_chroma_unset(Path(tmpdir), mp)
        finally:
            mp.undo()

    def test_post_x3_deferred_promotion_uses_explicit_chroma_env(self) -> None:
        mp = pytest.MonkeyPatch()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                test_post_x3_deferred_promotion_uses_explicit_chroma_env(Path(tmpdir), mp)
        finally:
            mp.undo()

    def test_post_x3_deferred_promotion_empty_when_no_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            test_post_x3_deferred_promotion_empty_when_no_candidates(Path(tmpdir))

    def test_post_x3_deferred_promotion_skipped_when_mode_not_deferred(self) -> None:
        mp = pytest.MonkeyPatch()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                test_post_x3_deferred_promotion_skipped_when_mode_not_deferred(Path(tmpdir), mp)
        finally:
            mp.undo()

    def test_l6_grain_parity_summary_tracks_whole_run_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            test_l6_grain_parity_summary_tracks_whole_run_rows(Path(tmpdir))

    def test_l6_grain_parity_reports_failure_when_package_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            test_l6_grain_parity_reports_failure_when_package_missing(Path(tmpdir))

    def test_post_x3_deferred_promotion_fails_when_chroma_cache_mkdir_fails(self) -> None:
        mp = pytest.MonkeyPatch()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                test_post_x3_deferred_promotion_fails_when_chroma_cache_mkdir_fails(Path(tmpdir), mp)
        finally:
            mp.undo()

    def test_post_x3_deferred_promotion_no_candidate_runs_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            test_post_x3_deferred_promotion_no_candidate_runs_skips(Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
