"""P1-W4 track-weighted graph expansion — weights, hops, hybrid contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.fact_inventory.augmented_skills_graph import assert_skills_not_broad_ledger_authority
from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    default_arsenal_ledger_path,
    load_master_skills_arsenal_ledger,
)
from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    HYBRID_JD_FIXTURE,
    SINGLE_TRACK_JD_FIXTURE,
    TrackWeightedExpansionContractError,
    build_track_weighted_expansion,
    resolve_career_track_weights,
    write_p1_w4_receipts,
)

REPO = Path(__file__).resolve().parents[4]
LEDGER_PATH = default_arsenal_ledger_path(REPO)
SINGLE_TRACK_WEIGHT_OVERRIDE = {
    "track_actuarial_risk_derivatives": 1.0,
    "track_data_tech_cloud_ml": 0.0,
    "track_genai_agentic": 0.0,
}


@pytest.fixture
def ledger() -> dict:
    return load_master_skills_arsenal_ledger(path=LEDGER_PATH)


def test_svp_agentic_default_track_weights() -> None:
    w = resolve_career_track_weights(role_family_key="SVP_ENGINEERING_AI_PLATFORM")
    assert w["track_actuarial_risk_derivatives"] == pytest.approx(0.10, abs=0.01)
    assert w["track_data_tech_cloud_ml"] == pytest.approx(0.25, abs=0.01)
    assert w["track_genai_agentic"] == pytest.approx(0.65, abs=0.01)
    assert sum(w.values()) == pytest.approx(1.0, abs=0.01)


def test_hybrid_jd_selects_at_least_two_tracks(ledger: dict) -> None:
    out = build_track_weighted_expansion(
        graph=ledger,
        role_family_key="SVP_ENGINEERING_AI_PLATFORM",
        jd_text=HYBRID_JD_FIXTURE,
        enforce_hybrid_contract=True,
        min_tracks_with_facts=2,
    )
    tracks = out["tracks_with_facts"]
    assert len(tracks) >= 2
    assert out["selected_fact_count_by_track"]["track_genai_agentic"] >= 1
    assert sum(out["selected_fact_count_by_track"].values()) >= 2
    assert out["broad_skills_ledger_used_as_authority"] is False
    assert out["cross_track_causal_claims"] is False
    assert_skills_not_broad_ledger_authority(out)
    hops = out.get("graph_hop_paths_sample") or []
    assert hops
    assert hops[0][0]["edge_type"] == "career_track_contains_pillar"
    assert out["c03_graph_bound_status"] == "BOUND"
    assert out["c03_graph_hop_paths_count"] >= 1
    assert out["non_graph_evidence_items_count"] == 0
    assert out["graph_expansion_mode"] == "TRACK_WEIGHTED_MULTI_HOP"
    assert len(out.get("c03_selected_tracks") or []) >= 2


def test_single_track_weight_override_fails_hybrid_contract(ledger: dict) -> None:
    with pytest.raises(TrackWeightedExpansionContractError):
        build_track_weighted_expansion(
            graph=ledger,
            role_family_key="QUANT_TRADING",
            jd_text=SINGLE_TRACK_JD_FIXTURE,
            weight_override=SINGLE_TRACK_WEIGHT_OVERRIDE,
            enforce_hybrid_contract=True,
            min_tracks_with_facts=2,
        )


def test_graph_hop_path_uses_skill_supported_by_fact_when_edge_exists(ledger: dict) -> None:
    out = build_track_weighted_expansion(
        graph=ledger,
        role_family_key="SVP_ENGINEERING_AI_PLATFORM",
        jd_text=HYBRID_JD_FIXTURE,
        enforce_hybrid_contract=False,
    )
    skill_hops = [s for s in out["selected_skills"] if s.get("graph_hop_path")]
    assert skill_hops
    edge_types = {step["edge_type"] for step in skill_hops[0]["graph_hop_path"]}
    assert "career_track_contains_pillar" in edge_types
    assert "skill_supported_by_fact" in edge_types or "skill_row_fact_id_links" in edge_types


def test_seed_fact_ids_are_hard_allowlist_for_selected_facts(ledger: dict) -> None:
    expanded = build_track_weighted_expansion(
        graph=ledger,
        role_family_key="SVP_ENGINEERING_AI_PLATFORM",
        jd_text=HYBRID_JD_FIXTURE,
        enforce_hybrid_contract=False,
    )
    seed_fact = str(expanded["selected_facts"][0]["fact_id"])
    out = build_track_weighted_expansion(
        graph=ledger,
        role_family_key="SVP_ENGINEERING_AI_PLATFORM",
        jd_text=HYBRID_JD_FIXTURE,
        seed_fact_ids=[seed_fact],
        enforce_hybrid_contract=False,
    )
    selected = {str(row.get("fact_id")) for row in out["selected_facts"]}
    assert selected == {seed_fact}


def test_write_p1_w4_receipts_on_disk(tmp_path: Path) -> None:
    paths = write_p1_w4_receipts(repo_root=REPO, out_dir=tmp_path)
    receipt = Path(paths["receipt_json"])
    md = Path(paths["receipt_md"])
    closeout = Path(paths["closeout_json"])
    assert receipt.is_file()
    assert md.is_file()
    assert closeout.is_file()
    markdown = md.read_text(encoding="utf-8")
    assert "Receipt mode:** TEST_ONLY_NONCANONICAL_OUTPUT" in markdown
    assert "Certification eligible:** False" in markdown
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["receipt_mode"] == "TEST_ONLY_NONCANONICAL_OUTPUT"
    assert data["certification_eligible"] is False
    hybrid = data["hybrid_fixture"]
    assert len(hybrid["tracks_with_facts"]) >= 2
    assert data["c03_binding_proof"]["c03_graph_bound_status"] == "BOUND"
    iso = data["apps_rg_runtime_isolation"]
    assert iso["touched_by_this_wave"] is False
