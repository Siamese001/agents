"""Assembly gap placeholders — incomplete lanes must not abort glue before judges."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from apps_rg.runtime.assembly.final_resume_manifest import FinalResumePaths, resolve_default_paths
from apps_rg.runtime.internal.final_resume_assembler import (
    _resolve_full_resume_targeting_context,
    assemble_final_resume,
)
from apps_rg.runtime.locked_copy.locked_copy_manifest import find_repo_root


def test_missing_rollup_lane_emits_assembly_gap_not_raise(tmp_path: Path) -> None:
    base = resolve_default_paths(find_repo_root())
    if not base.rollup_json.is_file():
        pytest.skip("rollup missing")
    rollup = json.loads(base.rollup_json.read_text(encoding="utf-8"))
    lanes = dict(rollup.get("lanes") or {})
    lanes.pop("headline", None)
    rollup["lanes"] = lanes
    rollup_path = tmp_path / "rollup_gap.json"
    rollup_path.write_text(json.dumps(rollup), encoding="utf-8")
    out = tmp_path / "asm_out"
    paths = FinalResumePaths(
        repo_root=base.repo_root,
        rollup_json=rollup_path,
        locked_manifest=base.locked_manifest,
        locked_x2=base.locked_x2,
        base_resume=base.base_resume,
        output_dir=out,
    )
    prev_struct = os.environ.get("APPS_RG_ASSEMBLY_STRUCTURAL_ONLY")
    prev_coherence = os.environ.get("APPS_RG_FULL_RESUME_LLM_COHERENCE_REVIEW")
    os.environ["APPS_RG_ASSEMBLY_STRUCTURAL_ONLY"] = "1"
    os.environ["APPS_RG_FULL_RESUME_LLM_COHERENCE_REVIEW"] = "0"
    try:
        result = assemble_final_resume(paths, skip_preflight=True)
    finally:
        if prev_struct is None:
            os.environ.pop("APPS_RG_ASSEMBLY_STRUCTURAL_ONLY", None)
        else:
            os.environ["APPS_RG_ASSEMBLY_STRUCTURAL_ONLY"] = prev_struct
        if prev_coherence is None:
            os.environ.pop("APPS_RG_FULL_RESUME_LLM_COHERENCE_REVIEW", None)
        else:
            os.environ["APPS_RG_FULL_RESUME_LLM_COHERENCE_REVIEW"] = prev_coherence
    assert result["gates_all_pass"] is False
    blob = json.loads((out / "final_resume.json").read_text(encoding="utf-8"))
    headline = next(s for s in blob["sections"] if s.get("section_id") == "headline")
    snap = headline.get("l2_output_snapshot") or {}
    assert snap.get("assembly_gap") is True
    assert "rollup missing lane headline" in str(snap.get("assembly_gap_reason") or "")


def test_full_resume_targeting_falls_back_to_root_ingress(tmp_path: Path, monkeypatch) -> None:
    run_root = tmp_path / "run"
    output_dir = run_root / "modular_r4" / "final_resume_assembly"
    output_dir.mkdir(parents=True)
    (run_root / "ingress_raw.json").write_text(
        json.dumps(
            {
                "target_company": "Anthropic",
                "target_role": "Manager of Applied AI Architecture, Partnerships",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("APPS_RG_TARGET_COMPANY", raising=False)
    monkeypatch.delenv("APPS_RG_TARGET_ROLE", raising=False)

    company, role, source = _resolve_full_resume_targeting_context(
        output_dir=output_dir,
        rollup_blob={"lanes": {}},
    )

    assert company == "Anthropic"
    assert role == "Manager of Applied AI Architecture, Partnerships"
    assert source == "ingress_raw.json"
