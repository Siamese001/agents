"""Acceptance tests for the single-run zero-LLM RCA W0 freeze."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.single_run_rca_w0 import emit_single_run_w0_freeze
from apps_rg.runtime.post_runtime_replay import build_source_manifest


def _inputs(root: Path) -> tuple[Path, Path, Path]:
    source = root / "e2e_test"
    source.mkdir()
    (source / "lane.json").write_text('{"status":"saved"}\n', encoding="utf-8")
    completion = root / "w5_completion.json"
    completion.write_text(
        json.dumps({"status": "PASS", "scope_complete": True, "real_run_ids": [source.name]}) + "\n",
        encoding="utf-8",
    )
    integrated = root / "integrated.json"
    integrated.write_text('{"status":"PASS"}\n', encoding="utf-8")
    return source, completion, integrated


def test_freeze_binds_source_and_existing_w5_evidence(tmp_path: Path) -> None:
    source, completion, integrated = _inputs(tmp_path)
    first = emit_single_run_w0_freeze(
        source_run=source,
        w5_completion_path=completion,
        integrated_manifest_path=integrated,
        output_dir=tmp_path / "output",
        source_manifest_builder=build_source_manifest,
    )
    second = emit_single_run_w0_freeze(
        source_run=source,
        w5_completion_path=completion,
        integrated_manifest_path=integrated,
        output_dir=tmp_path / "output",
        source_manifest_builder=build_source_manifest,
    )

    assert first["status"] == "PASS"
    assert first["semantic_digest"] == second["semantic_digest"]
    assert first["source_run_id"] == source.name
    assert first["historical_scope"] == {"generation_lanes": 11, "judges": 21, "contract_handoffs": 21}
    assert first["next_wave_authorized"] is True


def test_freeze_rejects_unbound_source_run(tmp_path: Path) -> None:
    source, completion, integrated = _inputs(tmp_path)
    completion.write_text('{"status":"PASS","scope_complete":true,"real_run_ids":[]}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="not bound"):
        emit_single_run_w0_freeze(
            source_run=source,
            w5_completion_path=completion,
            integrated_manifest_path=integrated,
            output_dir=tmp_path / "output",
            source_manifest_builder=build_source_manifest,
        )
