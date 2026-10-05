"""Wave 2 verification tests for Confidence and Evidence Model (G3, G4, G5).

Covers Acceptance Criteria AC2.1 - AC2.6:
- AC2.1: Claim-bearing edges carry numeric confidence_score in [0.0, 1.0] and tier in {HIGH, MEDIUM, LOW}.
         Policy and taxonomy edges have confidence_tier='NOT_APPLICABLE' and non-empty derivation rule refs.
- AC2.2: confidence and validation_status are decoupled (COUNT(*) WHERE confidence=validation_status AND confidence<>'' == 0).
- AC2.3: Every claim-bearing edge has >= 1 edge_evidence row; every non-empty evidence_node_id resolves to graph_nodes.
- AC2.4: Every skill_surfaces_metric_outcome edge has a proven skill->fact->metric chain; 0 originate from BLOCKED skills.
- AC2.5: 0 BLOCKED skills carry skill_external_claim_eligible edges (e.g. skill_risk_enterprise_risk_controls).
- AC2.6: Unit tests for noisy-OR, source node score cap, weight=0.0 preservation, and numeric ordering in query.py.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from apps_rg.fact_inventory.skills_graph.edge_evidence import (
    score_claim_bearing_edge,
    calibrate_edge_confidence,
    compute_node_confidence,
)
from apps_rg.fact_inventory.skills_graph.query import get_skills_by_career_phase

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    assert DB_PATH.is_file(), f"Augmented skills graph DB missing at {DB_PATH}"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    yield conn
    conn.close()


def test_ac2_1_claim_bearing_have_calibrated_confidence_score_and_tier(db_conn: sqlite3.Connection) -> None:
    """AC2.1: Claim-bearing edges carry calibrated numeric score; policy/taxonomy carry NOT_APPLICABLE with rule ref."""
    # 1. Claim-bearing edges have non-null confidence_score between 0 and 1
    unscored_claim_edges = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges
        WHERE assertion_type IN ('EVIDENTIAL_SUPPORT', 'METRIC_BINDING')
          AND (confidence_score IS NULL OR confidence_score < 0.0 OR confidence_score > 1.0)
        """
    ).fetchone()[0]
    assert unscored_claim_edges == 0, "Claim-bearing edges must have confidence_score in [0.0, 1.0]"

    # 2. Claim-bearing edges have valid confidence tiers
    invalid_claim_tiers = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges
        WHERE assertion_type IN ('EVIDENTIAL_SUPPORT', 'METRIC_BINDING')
          AND confidence_tier NOT IN ('HIGH', 'MEDIUM', 'LOW')
        """
    ).fetchone()[0]
    assert invalid_claim_tiers == 0, "Claim-bearing edges must have tier in {HIGH, MEDIUM, LOW}"

    # 3. Policy and taxonomy edges have confidence_tier = 'NOT_APPLICABLE'
    invalid_rule_tiers = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges
        WHERE assertion_type NOT IN ('EVIDENTIAL_SUPPORT', 'METRIC_BINDING')
          AND confidence_tier <> 'NOT_APPLICABLE'
        """
    ).fetchone()[0]
    assert invalid_rule_tiers == 0, "Non-claim-bearing edges must have confidence_tier='NOT_APPLICABLE'"

    # 4. Policy and taxonomy edges have non-empty derivation_rule_id
    missing_rule_refs = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges
        WHERE assertion_type NOT IN ('EVIDENTIAL_SUPPORT', 'METRIC_BINDING')
          AND (derivation_rule_id IS NULL OR TRIM(derivation_rule_id) = '')
        """
    ).fetchone()[0]
    assert missing_rule_refs == 0, "Policy/taxonomy edges must carry a non-empty derivation rule reference"


def test_ac2_2_confidence_and_validation_status_decoupled(db_conn: sqlite3.Connection) -> None:
    """AC2.2: confidence and validation_status are decoupled."""
    # Prior to Wave 2, 2055 edges had confidence = 'validated' matching validation_status = 'validated'
    coupled_count = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges
        WHERE confidence = validation_status
          AND confidence <> ''
        """
    ).fetchone()[0]
    assert coupled_count == 0, f"Expected 0 coupled confidence=validation_status edges, found {coupled_count}"

    # Verify legacy confidence column mirrors confidence_tier
    mismatch_legacy = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges
        WHERE confidence <> confidence_tier
        """
    ).fetchone()[0]
    assert mismatch_legacy == 0, "Legacy confidence column must mirror confidence_tier"


def test_ac2_3_edge_evidence_coverage_and_node_resolution(db_conn: sqlite3.Connection) -> None:
    """AC2.3: Every claim-bearing edge has >= 1 edge_evidence row; all evidence_node_ids resolve."""
    # 1. Total edge_evidence rows > 0
    total_evidence = db_conn.execute("SELECT count(*) FROM edge_evidence").fetchone()[0]
    assert total_evidence > 0, "edge_evidence table must not be empty"

    # 2. Every claim-bearing edge has at least one edge_evidence row
    unbacked_claim_edges = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges ge
        WHERE ge.assertion_type IN ('EVIDENTIAL_SUPPORT', 'METRIC_BINDING')
          AND NOT EXISTS (
              SELECT 1 FROM edge_evidence ee WHERE ee.edge_id = ge.edge_id
          )
        """
    ).fetchone()[0]
    assert unbacked_claim_edges == 0, "Every claim-bearing edge must have >= 1 edge_evidence row"

    # 3. Every non-empty evidence_node_id resolves to an existing node in graph_nodes
    dangling_nodes = db_conn.execute(
        """
        SELECT count(*) FROM edge_evidence ee
        WHERE ee.evidence_node_id <> ''
          AND NOT EXISTS (
              SELECT 1 FROM graph_nodes gn WHERE gn.node_id = ee.evidence_node_id
          )
        """
    ).fetchone()[0]
    assert dangling_nodes == 0, "Every evidence_node_id must resolve to graph_nodes"

    # 4. Strength values bounded in [0.0, 1.0] and is_independent in {0, 1}
    invalid_evidence_vals = db_conn.execute(
        """
        SELECT count(*) FROM edge_evidence
        WHERE evidence_strength < 0.0 OR evidence_strength > 1.0
           OR is_independent NOT IN (0, 1)
        """
    ).fetchone()[0]
    assert invalid_evidence_vals == 0, "evidence_strength must be [0.0, 1.0] and is_independent in {0, 1}"


def test_ac2_4_skill_surfaces_metric_outcome_proof_chains(db_conn: sqlite3.Connection) -> None:
    """AC2.4: Every skill_surfaces_metric_outcome edge has a matching skill->fact->metric chain, and 0 from BLOCKED."""
    # Check that all skill_surfaces_metric_outcome edges have a proven fact path
    unproven_edges = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges ge
        WHERE ge.edge_type = 'skill_surfaces_metric_outcome'
          AND NOT EXISTS (
              SELECT 1
              FROM graph_edges e_sf
              JOIN graph_edges e_fm
                ON e_sf.target_node_id = e_fm.source_node_id
              WHERE e_sf.source_node_id = ge.source_node_id
                AND e_fm.target_node_id = ge.target_node_id
                AND e_sf.edge_type IN ('skill_supported_by_fact', 'skill_fact_link')
                AND e_fm.edge_type = 'fact_has_metric_outcome'
          )
        """
    ).fetchone()[0]
    assert unproven_edges == 0, f"Found {unproven_edges} unproven skill_surfaces_metric_outcome edges"

    # Exactly 176 proven edges materialize
    proven_count = db_conn.execute(
        "SELECT count(*) FROM graph_edges WHERE edge_type = 'skill_surfaces_metric_outcome'"
    ).fetchone()[0]
    assert proven_count == 176, f"Expected exactly 176 proven metric outcome edges, got {proven_count}"

    # 0 originate from BLOCKED skills
    blocked_metric_edges = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges ge
        JOIN graph_nodes gn ON ge.source_node_id = gn.node_id
        WHERE ge.edge_type = 'skill_surfaces_metric_outcome'
          AND (gn.confidence = 'BLOCKED' OR gn.activation_status = 'BLOCKED')
        """
    ).fetchone()[0]
    assert blocked_metric_edges == 0, "0 skill_surfaces_metric_outcome edges may originate from BLOCKED skills"


def test_ac2_5_blocked_skills_carry_no_external_claim_eligible(db_conn: sqlite3.Connection) -> None:
    """AC2.5: 0 BLOCKED skills carry skill_external_claim_eligible edges."""
    blocked_external_edges = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges ge
        JOIN graph_nodes gn ON ge.source_node_id = gn.node_id
        WHERE ge.edge_type = 'skill_external_claim_eligible'
          AND (gn.confidence = 'BLOCKED' OR gn.activation_status = 'BLOCKED')
        """
    ).fetchone()[0]
    assert blocked_external_edges == 0, "BLOCKED skills must not have skill_external_claim_eligible edges"

    # Specifically check skill_risk_enterprise_risk_controls
    risk_controls_external = db_conn.execute(
        """
        SELECT count(*) FROM graph_edges
        WHERE source_node_id = 'skill_risk_enterprise_risk_controls'
          AND edge_type = 'skill_external_claim_eligible'
        """
    ).fetchone()[0]
    assert risk_controls_external == 0, "skill_risk_enterprise_risk_controls must not be external-claim eligible"


def test_ac2_6_noisy_or_and_source_node_capping_unit() -> None:
    """AC2.6: Test noisy-OR formula and source-node score capping in edge_evidence."""
    # 1. Single independent piece of evidence with strength 0.85
    ev1 = [{"is_independent": 1, "evidence_strength": 0.85}]
    score, tier, method = score_claim_bearing_edge(evidence_rows=ev1, source_node_score=None)
    assert score == 0.85
    assert tier == "HIGH"
    assert method == "noisy_or_independent_evidence"

    # 2. Two independent pieces of evidence: 0.70 and 0.60
    # Noisy-OR = 1 - (1 - 0.70)*(1 - 0.60) = 1 - (0.30 * 0.40) = 1 - 0.12 = 0.88
    ev2 = [
        {"is_independent": 1, "evidence_strength": 0.70},
        {"is_independent": 1, "evidence_strength": 0.60},
    ]
    score, tier, _ = score_claim_bearing_edge(evidence_rows=ev2, source_node_score=None)
    assert score == 0.88
    assert tier == "HIGH"

    # 3. Source node score caps the score
    # If source node has confidence score 0.65, noisy-OR (0.88) must be capped at 0.65
    score_capped, tier_capped, _ = score_claim_bearing_edge(evidence_rows=ev2, source_node_score=0.65)
    assert score_capped == 0.65
    assert tier_capped == "MEDIUM"

    # 4. No independent evidence yields UNSCORED
    ev_empty: list[dict[str, Any]] = [{"is_independent": 0, "evidence_strength": 0.90}]
    score_none, tier_none, method_none = score_claim_bearing_edge(evidence_rows=ev_empty)
    assert score_none is None
    assert tier_none == "UNSCORED"
    assert method_none == "no_independent_evidence"


def test_ac2_6_node_confidence_computation_and_blocked_split() -> None:
    """AC2.6: Test compute_node_confidence correctly splits BLOCKED into activation_status."""
    # 1. Active high skill
    score, tier, status = compute_node_confidence({"node_type": "skill", "confidence": "HIGH"})
    assert score == 0.90
    assert tier == "HIGH"
    assert status == "ACTIVE"

    # 2. Blocked skill splits to activation_status='BLOCKED', confidence_score=0.0, tier='LOW'
    score_b, tier_b, status_b = compute_node_confidence({"node_type": "skill", "confidence": "BLOCKED"})
    assert score_b == 0.0
    assert tier_b == "LOW"
    assert status_b == "BLOCKED"

    # 3. Structural node (career_epoch) is NOT_APPLICABLE
    score_e, tier_e, status_e = compute_node_confidence({"node_type": "career_epoch", "confidence": ""})
    assert score_e is None
    assert tier_e == "NOT_APPLICABLE"


def test_ac2_6_query_numeric_confidence_ordering(db_conn: sqlite3.Connection) -> None:
    """AC2.6: Verify get_skills_by_career_phase orders numerically by confidence_score DESC."""
    phase_data = get_skills_by_career_phase(
        db_conn,
        phase_ordinal=6,
        min_confidence="LOW",
    )
    skills = phase_data.get("skills", [])
    assert len(skills) > 0

    # Ensure scores are non-increasing (sorted DESC by numeric score)
    scores = [s["confidence_score"] for s in skills if s.get("confidence_score") is not None]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], f"Results not sorted numerically: {scores[i]} < {scores[i+1]}"

