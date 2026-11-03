"""Behavioral fault-injection tests for the 8-pillar Cost, Cache & Token Budget Auditor.

Proves that breaking cache key sensitivity, weakening UWG Chroma quarantine,
degrading Anthropic cache read multipliers, bypassing token budget caps, or
introducing malformed YAML triggers non-zero failure even when all legacy
source keywords and symbol names remain present in source text.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from tools.cost_token_budget_auditor import (
    MIN_REQUIRED_ROI_MULTIPLE,
    main as auditor_main,
    run_eight_pillar_cost_token_audit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _build_shadow_repo(tmp_path: Path, mutated_rel_path: str) -> tuple[Path, Path]:
    """Create a lightweight shadow repo symlinking unchanged trees and copying one file for mutation."""
    shadow = tmp_path / "shadow_repo"
    shadow.mkdir(parents=True, exist_ok=True)
    rel_parts = Path(mutated_rel_path).parts
    top_mutated = rel_parts[0]

    for child in REPO_ROOT.iterdir():
        if child.name in {".git", ".worktrees", ".pytest_cache", ".ruff_cache", "__pycache__"}:
            continue
        dest = shadow / child.name
        if child.name != top_mutated:
            os.symlink(child, dest)

    # Materialize parent chain along mutated_rel_path, symlinking sibling entries at each level
    cur_src = REPO_ROOT
    cur_dst = shadow
    for depth, part in enumerate(rel_parts[:-1]):
        cur_src = cur_src / part
        cur_dst = cur_dst / part
        cur_dst.mkdir(parents=True, exist_ok=True)
        next_part = rel_parts[depth + 1]
        for sib in cur_src.iterdir():
            if sib.name == "__pycache__":
                continue
            sib_dst = cur_dst / sib.name
            if sib.name != next_part and not sib_dst.exists():
                os.symlink(sib, sib_dst)

    src_file = REPO_ROOT / mutated_rel_path
    dst_file = shadow / mutated_rel_path
    shutil.copy2(src_file, dst_file)
    return shadow, dst_file


def test_live_cost_token_budget_auditor_passes_and_emits_pure_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify live 8-pillar execution exits 0, emits pure JSON, and contains zero legacy YAML hacks."""
    rc = auditor_main(["--repo-root", str(REPO_ROOT), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "PASS"
    assert payload["is_clean"] is True
    assert payload["pillars_passing"] == 8
    assert payload["total_gaps"] == 0
    assert payload["roi_benchmark"]["roi_multiple"] >= MIN_REQUIRED_ROI_MULTIPLE
    assert payload["roi_benchmark"]["briefing_cache_hits_verified"] >= 5

    auditor_src = (REPO_ROOT / "tools" / "cost_token_budget_auditor.py").read_text(encoding="utf-8")
    assert "_parse_simple_yaml" not in auditor_src
    assert "if marker not in" not in auditor_src


def test_broken_cache_identity_collision_fails_with_keywords_intact(tmp_path: Path) -> None:
    """Injecting a constant SHA-256 collision into CacheIdentity.compute_key must fail Pillar 4."""
    rel = "resume_graph_engine/src/apps_rg/cache/cache_identity.py"
    shadow, target = _build_shadow_repo(tmp_path, rel)
    original = target.read_text(encoding="utf-8")
    mutated = original.replace(
        "return hashlib.sha256(encoded).hexdigest()",
        'return "a" * 64  # constant collision bug with all symbol names preserved',
    )
    assert mutated != original
    target.write_text(mutated, encoding="utf-8")

    report = run_eight_pillar_cost_token_audit(repo_root=shadow)
    assert report["status"] == "ACTION_REQUIRED"
    assert report["is_clean"] is False
    p4_gaps = "\n".join(report["pillars"][3]["gaps"])
    assert "CacheIdentity" in p4_gaps
    assert auditor_main(["--repo-root", str(shadow)]) == 1


def test_weakened_uwg_quarantine_allowing_shadow_chroma_fails_pillar_3(tmp_path: Path) -> None:
    """Bypassing NON_DURABLE_INDEX_WRITE classification on uncommitted runs must fail Pillar 3."""
    rel = "resume_graph_engine/src/apps_rg/runtime/semantic_cache_persistence_quarantine.py"
    shadow, target = _build_shadow_repo(tmp_path, rel)
    original = target.read_text(encoding="utf-8")
    mutated = original.replace(
        "return CHROMA_CLASS_NON_DURABLE",
        "return CHROMA_CLASS_GOVERNED_REFRESH",
    )
    assert mutated != original
    target.write_text(mutated, encoding="utf-8")

    report = run_eight_pillar_cost_token_audit(repo_root=shadow)
    assert report["status"] == "ACTION_REQUIRED"
    p3_gaps = "\n".join(report["pillars"][2]["gaps"])
    assert "NON_DURABLE_INDEX_WRITE" in p3_gaps


def test_degraded_cache_read_multiplier_fails_pillar_2(tmp_path: Path) -> None:
    """Mutating CACHE_READ_INPUT_MULTIPLIER from 0.10 to 1.00 must fail Pillar 2 live math."""
    rel = "resume_graph_engine/src/apps_rg/runtime/providers/anthropic_prompt_cache.py"
    shadow, target = _build_shadow_repo(tmp_path, rel)
    original = target.read_text(encoding="utf-8")
    mutated = original.replace("CACHE_READ_INPUT_MULTIPLIER = 0.10", "CACHE_READ_INPUT_MULTIPLIER = 1.00")
    assert mutated != original
    target.write_text(mutated, encoding="utf-8")

    report = run_eight_pillar_cost_token_audit(repo_root=shadow)
    assert report["status"] == "ACTION_REQUIRED"
    p2_gaps = "\n".join(report["pillars"][1]["gaps"])
    assert "multipliers drifted" in p2_gaps or "wrong read math" in p2_gaps


def test_token_budget_overrun_bypass_fails_pillar_7(tmp_path: Path) -> None:
    """Allowing input tokens > max_input_tokens_per_attempt in reserve_token_budget must fail Pillar 7."""
    rel = "apps_model_telemetry/token_budget_governor.py"
    shadow, target = _build_shadow_repo(tmp_path, rel)
    original = target.read_text(encoding="utf-8")
    mutated = original.replace(
        "if estimated_input > policy.max_input_tokens_per_attempt:",
        "if False and estimated_input > policy.max_input_tokens_per_attempt:",
    )
    assert mutated != original
    target.write_text(mutated, encoding="utf-8")

    report = run_eight_pillar_cost_token_audit(repo_root=shadow)
    assert report["status"] == "ACTION_REQUIRED"
    p7_gaps = "\n".join(report["pillars"][6]["gaps"])
    assert "max_input_tokens_per_attempt" in p7_gaps


def test_malformed_yaml_fails_closed_in_pillar_1(tmp_path: Path) -> None:
    """Invalid YAML syntax in provider_profiles.yaml must fail closed rather than silently returning {}."""
    rel = "config/provider_profiles.yaml"
    shadow, target = _build_shadow_repo(tmp_path, rel)
    target.write_text("profiles:\n  broken: [unclosed_list\n", encoding="utf-8")

    report = run_eight_pillar_cost_token_audit(repo_root=shadow)
    assert report["status"] == "ACTION_REQUIRED"
    p1_gaps = "\n".join(report["pillars"][0]["gaps"])
    assert "Malformed YAML" in p1_gaps
