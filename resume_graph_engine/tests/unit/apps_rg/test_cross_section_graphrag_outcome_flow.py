"""End-to-end regression tests for cross-section GraphRAG outcome flow, IBM grounding, and CLI concurrency."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

RGE_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = RGE_ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"


def _ensure_skills_graph_db() -> Path:
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        if DB_PATH.exists():
            DB_PATH.unlink()
        from apps_rg.fact_inventory.skills_graph.materializer import (
            materialize_augmented_skills_graph_sqlite,
        )

        materialize_augmented_skills_graph_sqlite(repo_root=RGE_ROOT, db_path=DB_PATH)
    return DB_PATH


@pytest.mark.unit
def test_ibm_qualitative_slot_never_advertises_unassigned_numeric_metrics() -> None:
    """Wave 1: qualitative ibm_bullets slots must not list unassigned numeric bundle metrics."""
    from apps_rg.runtime.sections.ibm_role_episode_evidence import format_ibm_role_episode_evidence_pack

    plan = {
        "facts": [
            {
                "fact_id": "bul_ibm_001",
                "role_episode_bundle_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "claim_text": "Led IBM-AWS alliance co-sell architecture for financial services.",
                "metric_raw": "",
                "metric_outcome_id": "",
            },
            {
                "fact_id": "bul_ibm_002",
                "role_episode_bundle_id": "reb_ibm_devsecops_release_resilience",
                "claim_text": "Engineered DevSecOps release guardrails for regulated workloads.",
                "metric_raw": "",
                "metric_outcome_id": "",
            },
        ]
    }
    pack = format_ibm_role_episode_evidence_pack(
        {"selected_fact_plan": plan, "allowed_source_fact_ids": ["bul_ibm_001", "bul_ibm_002"]},
        section_id="ibm_bullets",
    )
    assert "(none - qualitative slot; do NOT emit any numeric metric)" in pack
    assert "all active slots are qualitative" in pack
    assert "20% joint revenue growth" not in pack
    assert "graph_business_outcome:" in pack


@pytest.mark.unit
def test_ibm_frozen_allocation_covers_all_bundle_skill_leaves() -> None:
    """Wave 1: every (reb_ibm_*, skill_*) leaf in ibm_role_episode_bundles.json has a fallback composition."""
    from apps_rg.runtime.sections.ibm_bullets.frozen_allocation import _IBM_FROZEN_ALLOCATION_DISPLAY_COMPOSITIONS

    doc = json.loads((RGE_ROOT / "src/apps_rg/fact_inventory/ibm_role_episode_bundles.json").read_text(encoding="utf-8"))
    missing = [
        (b["role_episode_bundle_id"], sid)
        for b in doc["bundles"]
        for sid in (b.get("graph_skill_node_ids") or [])
        if (b["role_episode_bundle_id"], sid) not in _IBM_FROZEN_ALLOCATION_DISPLAY_COMPOSITIONS
    ]
    assert missing == [], f"Missing IBM frozen-allocation display compositions: {missing}"


@pytest.mark.unit
def test_agy_cli_dynamic_concurrency_budget_and_queue_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wave 1: headless Antigravity CLI transport honors dynamic AGY_CLI_MAX_CONCURRENCY and measures queue wait."""
    from apps_rg.runtime.providers import agy_cli_transport as mod

    monkeypatch.setenv("AGY_CLI_MAX_CONCURRENCY", "2")
    assert mod.resolve_agy_max_concurrency() == 2

    active = 0
    peak = 0
    waits: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        nonlocal active, peak
        with mod._acquire_cli_slot() as wait_s:
            with lock:
                waits.append(wait_s)
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert peak <= 2, f"Peak concurrency exceeded cap=2: {peak}"
    assert len(waits) == 5
    assert max(waits) >= 0.04


@pytest.mark.unit
def test_unify_and_insurtech_bundles_emit_concrete_graph_business_outcomes() -> None:
    """Waves 2A/2C: Unify (10) and InsurTech (12) bundles emit concrete non-boilerplate outcomes."""
    from apps_rg.runtime.sections.insurtech_role_episode_evidence import build_insurtech_role_episode_section_packet
    from apps_rg.runtime.sections.role_episode.prompt_compiler import _role_episode_evidence_block
    from apps_rg.runtime.sections.unify_role_episode_evidence import build_unify_role_episode_section_packet

    upkt = build_unify_role_episode_section_packet("unify_bullets")
    assert len(upkt["role_episode_bundles"]) == 10
    for b in upkt["role_episode_bundles"]:
        out = str(b.get("claim_outcome") or "")
        assert out and not out.lower().startswith("frame as"), f"Meta-instruction outcome in {b['role_episode_bundle_id']}"

    ipkt = build_insurtech_role_episode_section_packet("insurtech_bullets")
    assert len(ipkt["role_episode_bundles"]) == 12
    for b in ipkt["role_episode_bundles"]:
        out = str(b.get("claim_outcome") or "")
        assert out and "use only role_episode_bundle_id-bound evidence" not in out.lower()

    block = _role_episode_evidence_block({"proof_pool_metadata": ipkt, "selected_fact_plan": {}})
    assert block.count("graph_business_outcome:") == 12


@pytest.mark.unit
def test_competencies_zero_phantom_ids_and_slalom_bound() -> None:
    """Wave 3: competency_capability_bundles.json has 0 phantom skill/REB IDs and binds all 10 Slalom REBs."""
    ccb = json.loads((RGE_ROOT / "src/apps_rg/fact_inventory/competency_capability_bundles.json").read_text(encoding="utf-8"))
    conn = sqlite3.connect(_ensure_skills_graph_db())
    live_nodes = {r[0] for r in conn.execute("SELECT node_id FROM graph_nodes").fetchall()}
    conn.close()

    missing_skills = [
        (b["competency_bundle_id"], s)
        for b in ccb["bundles"]
        for s in (b.get("graph_skill_node_ids") or [])
        if s not in live_nodes
    ]
    missing_rebs = [
        (b["competency_bundle_id"], r)
        for b in ccb["bundles"]
        for r in (b.get("role_episode_bindings") or [])
        if r not in live_nodes
    ]
    bound_slalom = {
        r
        for b in ccb["bundles"]
        for r in (b.get("role_episode_bindings") or [])
        if r.startswith("reb_slalom_")
    }
    assert missing_skills == []
    assert missing_rebs == []
    assert len(bound_slalom) == 10


@pytest.mark.unit
def test_metric_outcome_story_semantic_units_expose_exec_summary_and_competencies() -> None:
    """Wave 4: metric_outcome_story semantic units derive section eligibility from graph edges."""
    conn = sqlite3.connect(_ensure_skills_graph_db())
    rows = conn.execute(
        "SELECT allowed_sections_json FROM semantic_unit WHERE unit_type = 'metric_outcome_story'"
    ).fetchall()
    conn.close()
    assert rows, "No metric_outcome_story rows in semantic_unit"
    exec_eligible = sum(1 for (s,) in rows if "executive_summary" in json.loads(s or "[]"))
    comp_eligible = sum(1 for (s,) in rows if "competencies" in json.loads(s or "[]"))
    assert exec_eligible >= 50, f"Expected >=50 executive_summary-eligible metric stories, got {exec_eligible}"
    assert comp_eligible >= 50, f"Expected >=50 competencies-eligible metric stories, got {comp_eligible}"
