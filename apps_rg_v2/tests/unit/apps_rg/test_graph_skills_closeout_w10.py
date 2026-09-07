"""W10 contract: closeout JSON schema and honest non-claims."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.fact_inventory.graph_skills_quality_enhancement_closeout import (
    PLAN_ID,
    SCHEMA,
    build_closeout,
)

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def isolated_graph_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(
        "APPS_RG_AUGMENTED_SKILLS_GRAPH_SQLITE_PATH",
        str(tmp_path / "augmented_skills_graph.sqlite"),
    )
    monkeypatch.setenv(
        "APPS_RG_C03_GRAPH_SQLITE_CONTEXT_RECEIPT_DIR",
        str(tmp_path / "c03_graph_sqlite_context"),
    )
    return tmp_path


def test_closeout_builder_schema(isolated_graph_runtime: Path) -> None:
    doc = build_closeout(REPO, git_commit="test")
    assert doc["schema"] == SCHEMA
    assert doc["plan_id"] == PLAN_ID
    assert doc["claims_release_eligible"] is False
    assert doc["claims_dynamic_graphrag_traverse"] is False
    assert doc["claims_c03_unified_pipeline_bound"] is False
    matrix = doc["proof_classification_matrix"]
    dod_ids = {row["dod_id"] for row in matrix}
    assert dod_ids >= {f"D{i}" for i in range(1, 17)}
    d6 = doc["d6_lane_matrix"]
    assert len(d6) == 7
    for row in d6:
        assert "x3_code_raw" in row
        assert "x3_normalized" in row
        assert "live_x3_allow_claimed" in row
    d16 = next(r for r in matrix if r["dod_id"] == "D16")
    assert d16["status"] == "BLOCKED"
    assert d16["primary_proof_class"] == "REAL_LLM_RUNTIME_PROOF"


def test_closeout_on_disk_after_emit(isolated_graph_runtime: Path) -> None:
    closeout = isolated_graph_runtime / "graph_skills_quality_enhancement_closeout.json"
    emitted = build_closeout(REPO)
    closeout.write_text(json.dumps(emitted, indent=2) + "\n", encoding="utf-8")
    doc = json.loads(closeout.read_text(encoding="utf-8"))
    assert doc["wave_receipt_paths"]
    assert any(
        p.endswith("graph_skills_quality_w10_ag_receipt.json") for p in doc["wave_receipt_paths"]
    )
    assert doc["brown_fixture_digests"]["pass"] is True
