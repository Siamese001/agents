"""Unit & counterfactual tests for cross-family `agents_graph_hygiene` PR Judge v3 receipt gate."""
from __future__ import annotations

import json
from pathlib import Path

from apps_eval.contracts.digests import sha256_file
from tools.pr_governance_core.judge_receipt_gate import (
    DEFAULT_JUDGE_GOVERNED_SURFACES,
    verify_diff_judge_receipts,
)


def _write_receipt_pair(
    worktree: Path,
    *,
    families: list[str],
    tamper_artifact_after: bool = False,
    verdict: str = "PASS",
    llm_executed: bool = True,
) -> tuple[Path, Path]:
    art = worktree / "artifacts/eval_harness/judge_receipts/agents_graph_hygiene_artifact.json"
    rec = worktree / "artifacts/eval_harness/judge_receipts/agents_graph_hygiene_receipt.json"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps({"diff_packet": {"applied": 3}}, indent=2) + "\n", encoding="utf-8")
    art_sha = sha256_file(art)

    payload = {
        "schema_version": "agents.graph_hygiene_promotion_judge_receipt.v1",
        "surface_id": "agents_graph_hygiene",
        "evaluator_kind": "llm_judge",
        "llm_judge_executed": llm_executed,
        "author_model_family": "anthropic",
        "judge_model_id": "gemini-4-argon-high",
        "judge_model_family": families[0] if families else "",
        "judge_model_families": families,
        "distinct_families": len(set(families)),
        "bundle_digest": "a" * 64,
        "artifact_sha256": art_sha,
        "deterministic_priming_stripped": True,
        "judge_input_keys": ["diff_packet", "generated_at_utc", "schema_version"],
        "external_http_call_count": 0,
        "normalized_unit_score": 0.95 if verdict == "PASS" else 0.50,
        "passed": verdict == "PASS",
        "verdict": verdict,
        "status": verdict,
    }
    rec.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if tamper_artifact_after:
        art.write_text(json.dumps({"diff_packet": {"applied": 999}}, indent=2) + "\n", encoding="utf-8")
    return rec, art


def test_graph_hygiene_pr_judge_receipt_gate_fail_closed_and_2family_pass(tmp_path: Path) -> None:
    changed = ["resume_graph_engine/src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"]

    # 1. Missing receipt fails closed
    res_missing = verify_diff_judge_receipts(changed, tmp_path, surfaces=DEFAULT_JUDGE_GOVERNED_SURFACES)
    assert res_missing["status"] == "FAIL"
    assert res_missing["violations"][0]["surface_id"] == "agents_graph_hygiene"
    assert "MISSING_BOUND_JUDGE_RECEIPT" in res_missing["violations"][0]["reasons"]

    # 2. Single-family receipt fails closed (requires min_distinct_families=2)
    _write_receipt_pair(tmp_path, families=["argon"])
    res_single = verify_diff_judge_receipts(changed, tmp_path, surfaces=DEFAULT_JUDGE_GOVERNED_SURFACES)
    assert res_single["status"] == "FAIL"
    assert any("INSUFFICIENT_DISTINCT_FAMILIES" in r for r in res_single["violations"][0]["reasons"])

    # 3. Stale/tampered disk artifact SHA-256 fails closed
    _write_receipt_pair(tmp_path, families=["argon", "openai"], tamper_artifact_after=True)
    res_stale = verify_diff_judge_receipts(changed, tmp_path, surfaces=DEFAULT_JUDGE_GOVERNED_SURFACES)
    assert res_stale["status"] == "FAIL"
    assert "STALE_ARTIFACT_RECEIPT_SHA256" in res_stale["violations"][0]["reasons"]

    # 4. Authentic disk-hash-matched 2-family receipt passes
    _write_receipt_pair(tmp_path, families=["argon", "openai"], tamper_artifact_after=False)
    res_ok = verify_diff_judge_receipts(changed, tmp_path, surfaces=DEFAULT_JUDGE_GOVERNED_SURFACES)
    assert res_ok["status"] == "PASS", res_ok
    assert res_ok["triggered_surfaces"][0]["surface_id"] == "agents_graph_hygiene"


def test_graph_hygiene_stub_label_canonicalizer_and_draft_id_guard() -> None:
    from tools.apply_graph_hygiene_remediation import _canonicalize_repo_stub_label
    from tools.graph_hygiene_judge_v3 import _validate_drafted_descriptions

    used: set[str] = set()
    lbl_root = _canonicalize_repo_stub_label("Agents", relpath="AGENTS.md", node_id="repo_a", used_labels=used)
    lbl_rg_1 = _canonicalize_repo_stub_label(
        "Agents", relpath="apps_rg/AGENTS.md", node_id="repo_b", linked_skill_labels=["Overlay Binding"], used_labels=used
    )
    lbl_rg_2 = _canonicalize_repo_stub_label(
        "Agents", relpath="apps_rg/AGENTS.md", node_id="repo_c", linked_skill_labels=["Control Plane"], used_labels=used
    )
    lbl_x2 = _canonicalize_repo_stub_label(
        "Executive Summary X2", relpath="apps_rg/runtime/validators/executive_summary_x2.py", node_id="repo_d", used_labels=used
    )
    assert len({lbl_root.lower(), lbl_rg_1.lower(), lbl_rg_2.lower(), lbl_x2.lower()}) == 4
    assert "Apps Rg" not in lbl_rg_1
    assert "Gate X2 Validator" in lbl_x2

    _, errs = _validate_drafted_descriptions(
        [{"skill_id": "s1", "description": "Measures rho hedging supported by archive-verified evidence in fact_quant_hpc_003."}],
        target_ids=["s1"],
        used_descriptions=set(),
    )
    assert any("fact_quant_hpc_003" in e for e in errs)

    drafted, ok_errs = _validate_drafted_descriptions(
        [{"skill_id": "s1", "description": "Measures interest-rate sensitivity through rho and applies rho hedging across early-career actuarial portfolios."}],
        target_ids=["s1"],
        used_descriptions=set(),
    )
    assert not ok_errs
    assert "s1" in drafted
