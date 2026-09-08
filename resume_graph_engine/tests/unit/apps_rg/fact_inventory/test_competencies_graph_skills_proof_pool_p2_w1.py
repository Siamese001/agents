"""P2-W1 competencies graph-skills proof pool."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.fact_inventory.competencies_graph_skills_proof_pool import (
    C03_STATUS_COMPETENCIES_GRAPH_PROOF,
    build_competencies_graph_skills_proof_payload,
    validate_competencies_graph_skills_proof_payload,
    write_p2_w1_competencies_graph_proof_pool_receipt,
    CompetenciesGraphProofPoolError,
)
from apps_rg.fact_inventory.track_weighted_graph_expansion import ROOT
from apps_rg.runtime.proof_pool_resolver import (
    PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH,
    resolve_section_proof_pool,
)

REPO = ROOT


@pytest.fixture(autouse=True)
def _proof_pool_fixture_dev_bypass() -> None:
    from apps_rg.runtime.spine.front_contracts import (
        activate_fixture_dev_bypass,
        deactivate_fixture_dev_bypass,
    )

    activate_fixture_dev_bypass(non_product_certified=True)
    yield
    deactivate_fixture_dev_bypass()


HYBRID_JD = (
    "SVP Engineering — Agentic AI platform leader for regulated financial services. "
    "Must show governed agentic runtime, GraphRAG, multi-agent orchestration, and policy gates. "
    "Also value actuarial rigor, derivatives risk, and Basel/CCAR lineage plus "
    "AWS cloud data platform and partner GTM co-sell experience."
)


def _write_test_upstream_receipts(base: Path) -> tuple[Path, Path]:
    upstream_dir = base / "upstream"
    upstream_dir.mkdir()
    p1_w4 = upstream_dir / "career_track_p1_w4_closeout_receipt.json"
    p1_w5 = upstream_dir / "career_track_p1_w5_track_balanced_sections_receipt.json"
    p1_w4.write_text(
        json.dumps(
            {
                "schema": "career_track_p1_w4_closeout_receipt_v1",
                "receipt_mode": "TEST_ONLY_NONCANONICAL_OUTPUT",
                "certification_eligible": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    p1_w5.write_text(
        json.dumps(
            {
                "schema": "career_track_p1_w5_track_balanced_sections_receipt_v1",
                "receipt_mode": "TEST_ONLY_NONCANONICAL_OUTPUT",
                "certification_eligible": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return p1_w4, p1_w5


def test_graph_proof_pool_resolves_augmented_skills_graph() -> None:
    pool = resolve_section_proof_pool(
        section="competencies",
        repo_root=REPO,
        target_role="SVP Engineering Agentic AI",
        jd_text=HYBRID_JD,
    )
    assert pool.proof_source == PROOF_SOURCE_AUGMENTED_SKILLS_GRAPH
    meta = pool.proof_pool_metadata
    assert meta.get("proof_pool_type") == "augmented_skills_graph"
    assert meta.get("broad_skills_ledger_used_as_authority") is False
    assert meta.get("graph_skills_proof_pool") is True
    c03 = str(meta.get("c03_graph_bound_status") or "")
    if c03 == "BOUND":
        assert int(meta.get("c03_graph_hop_paths_count") or 0) > 0


def test_broad_skills_authority_fails_on_graph_payload() -> None:
    payload = build_competencies_graph_skills_proof_payload(repo_root=REPO)
    bad = {**payload, "broad_skills_ledger_used_as_authority": True}
    with pytest.raises(CompetenciesGraphProofPoolError):
        validate_competencies_graph_skills_proof_payload(bad)


def test_every_skill_has_fact_links_and_graph_support() -> None:
    payload = build_competencies_graph_skills_proof_payload(repo_root=REPO)
    for sk in payload.get("selected_skill_rows") or []:
        assert sk.get("fact_id_links"), sk.get("skill_id")
        assert sk.get("graph_hop_path") or sk.get("graph_support_ref")


def test_p2_w1_receipt_written_and_validates(tmp_path) -> None:
    # out_dir=tmp_path (RCA 2026-06-10): tests must never regenerate the tracked
    # docs/reports receipts — that side effect kept the tree dirty and broke a stash pop.
    p1_w4, p1_w5 = _write_test_upstream_receipts(tmp_path)
    out_dir = tmp_path / "p2"
    out = write_p2_w1_competencies_graph_proof_pool_receipt(
        repo_root=REPO,
        out_dir=out_dir,
        p1_w4_closeout_path=p1_w4,
        p1_w5_projection_path=p1_w5,
    )
    receipt_json = Path(out["receipt_json"])
    assert receipt_json.is_file() and receipt_json.parent == out_dir
    receipt = json.loads(receipt_json.read_text(encoding="utf-8"))
    markdown = Path(out["receipt_md"]).read_text(encoding="utf-8")
    assert "Receipt mode:** TEST_ONLY_NONCANONICAL_OUTPUT" in markdown
    assert "Certification eligible:** False" in markdown
    assert receipt["receipt_mode"] == "TEST_ONLY_NONCANONICAL_OUTPUT"
    assert receipt["certification_eligible"] is False
    assert receipt["proof_pool_type"] == "augmented_skills_graph"
    assert receipt["section_id"] == "competencies"
    assert receipt["every_skill_has_fact_id_links"] is True
    assert receipt["every_skill_has_graph_support"] is True
    assert receipt["broad_skills_ledger_used_as_authority"] is False
    assert receipt["c03_graph_bound_status"] in (C03_STATUS_COMPETENCIES_GRAPH_PROOF, "BOUND")
    assert receipt.get("broad_skills_ledger_default") is False
    assert receipt["p1_w4_closeout_receipt_ref"] == str(p1_w4.resolve())
    assert receipt["p1_w4_closeout_receipt_raw_sha256"] == hashlib.sha256(
        p1_w4.read_bytes()
    ).hexdigest()
    assert receipt["p1_w5_projection_receipt_ref"] == str(p1_w5.resolve())
    assert receipt["p1_w5_projection_receipt_raw_sha256"] == hashlib.sha256(
        p1_w5.read_bytes()
    ).hexdigest()


def test_p2_w1_receipt_fails_closed_when_upstream_receipt_is_missing(tmp_path: Path) -> None:
    p1_w4, p1_w5 = _write_test_upstream_receipts(tmp_path)
    p1_w4.unlink()
    out_dir = tmp_path / "p2"
    with pytest.raises(CompetenciesGraphProofPoolError, match="missing required upstream receipt"):
        write_p2_w1_competencies_graph_proof_pool_receipt(
            repo_root=REPO,
            out_dir=out_dir,
            p1_w4_closeout_path=p1_w4,
            p1_w5_projection_path=p1_w5,
        )
    assert not out_dir.exists()


def test_p2_w1_canonical_receipt_fails_closed_when_logical_upstreams_are_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        CompetenciesGraphProofPoolError,
        match="docs.*career_track_p1_w4_closeout_receipt.json",
    ):
        write_p2_w1_competencies_graph_proof_pool_receipt(repo_root=tmp_path)


def test_p2_w1_canonical_output_rejects_noncanonical_upstream_override(
    tmp_path: Path,
) -> None:
    p1_w4, p1_w5 = _write_test_upstream_receipts(tmp_path)
    with pytest.raises(CompetenciesGraphProofPoolError, match="only for TEST_ONLY output"):
        write_p2_w1_competencies_graph_proof_pool_receipt(
            repo_root=REPO,
            p1_w4_closeout_path=p1_w4,
            p1_w5_projection_path=p1_w5,
        )
    assert not (
        tmp_path / "competencies_graph_proof_pool_p2_w1_receipt.json"
    ).exists()
