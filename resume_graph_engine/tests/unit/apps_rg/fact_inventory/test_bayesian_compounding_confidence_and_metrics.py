"""Wave 3 verification tests for Bayesian Compounding Confidence & Quantified Metric Unification."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from apps_rg.fact_inventory.c03_graph_kpi_health import evaluate_confidence_calibration_health
from apps_rg.fact_inventory.graph_metric_heterogeneity_policy import infer_metric_bucket
from apps_rg.fact_inventory.skills_graph.edge_evidence import (
    compute_compounding_skill_confidence,
    score_claim_bearing_edge,
)
from apps_rg.runtime.contracts.metric_lexical_primitives import (
    extract_exact_metric_value_unit,
    section_allows_hold_metric_scrub,
)
from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
    _has_technical_specificity,
    _score_bullet_seniority,
)

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    assert DB_PATH.is_file(), f"Augmented skills graph DB missing at {DB_PATH}"
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    yield conn
    conn.close()


def test_w3_continuous_compounding_confidence_and_zero_quarantine_leaks(db_conn: sqlite3.Connection) -> None:
    """Confidence distribution breaks the 0.90 plateau (<=0.35 bucket share) with 0 quarantined leaks."""
    health = evaluate_confidence_calibration_health(db_conn)
    assert health["status"] == "PASS", f"Confidence calibration health failed: {health}"
    assert health["confidence_bucket_concentration"] <= 0.35
    assert health["distinct_confidence_scores"] >= 10
    assert health["quarantined_high_confidence_leaks"] == 0
    assert health["quarantined_traversable_edges"] == 0


def test_w3_career_compounding_monotonic_zero_age_decay() -> None:
    """Multi-epoch actuarial skill with credential + facts compounds upward with zero age decay."""
    single_epoch, _, _ = compute_compounding_skill_confidence(
        {"node_type": "skill", "confidence": "HIGH", "activation_status": "ACTIVE_CONFIRMED"},
        fact_count=1,
        quote_backed_facts=1,
        distinct_employers=1,
        distinct_epochs=1,
        has_credential=False,
    )
    multi_epoch_cred, tier, _ = compute_compounding_skill_confidence(
        {"node_type": "skill", "confidence": "HIGH", "activation_status": "ACTIVE_CONFIRMED"},
        fact_count=3,
        quote_backed_facts=3,
        distinct_employers=3,
        distinct_epochs=4,
        has_credential=True,
        human_confirmed=True,
    )
    assert multi_epoch_cred > single_epoch
    assert tier == "HIGH"
    assert multi_epoch_cred <= 0.99

    # Decorrelated Noisy-OR penalizes duplicate source_doc vs independent docs
    same_doc = [
        {"is_independent": 1, "evidence_strength": 0.70, "source_doc": "doc_a.json"},
        {"is_independent": 1, "evidence_strength": 0.70, "source_doc": "doc_a.json"},
    ]
    diff_doc = [
        {"is_independent": 1, "evidence_strength": 0.70, "source_doc": "doc_a.json"},
        {"is_independent": 1, "evidence_strength": 0.70, "source_doc": "doc_b.json"},
    ]
    s_same, _, m_same = score_claim_bearing_edge(evidence_rows=same_doc, correlation_rho=0.25)
    s_diff, _, _ = score_claim_bearing_edge(evidence_rows=diff_doc, correlation_rho=0.25)
    assert s_same is not None and s_diff is not None
    assert s_diff > s_same
    assert m_same == "bayesian_noisy_or_compounding_v1"


def test_w3_metric_bucket_reordering_hold_scoping_and_actuarial_quality_floor() -> None:
    """Insurance/financial metrics classify accurately, HOLD scrubs only IBM, and actuarial/latency primitives pass."""
    assert infer_metric_bucket("Optimized Solvency II and AG43 actuarial capital reserves by 12%") == "insurance_risk"
    assert infer_metric_bucket("Directed Basel BCBS 239 and CCAR derivatives risk program") == "financial_services"
    assert section_allows_hold_metric_scrub("ibm_bullets") is True
    assert section_allows_hold_metric_scrub("unify_bullets") is False
    assert section_allows_hold_metric_scrub("insurtech_bullets") is False

    assert extract_exact_metric_value_unit("<250ms Live Copilot latency") == ("250", "LATENCY_MS")
    assert extract_exact_metric_value_unit("Migrated 14TB Oracle/SQL Server databases") == ("14", "DATA_VOLUME")

    actuarial_bullet = (
        "Optimized Solvency II and AG43 capital reserves across regulated insurers by 12% "
        "using stochastic actuarial and Guidewire underwriting models."
    )
    score, _ = _score_bullet_seniority(actuarial_bullet)
    assert score >= 2
    assert _has_technical_specificity(actuarial_bullet) is True
