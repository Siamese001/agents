"""W1B derived-cluster tests use current source authority read-only."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from apps_rg.evals.owner_solo import c03_full_resume_qrel_derived_clusters as subject
from apps_rg.evals.owner_solo.c03_full_resume_qrel_derived_clusters import (
    build_derived_bundle_registry,
    validate_derived_bundle_registry,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import canonical_sha256


ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _algorithm_test_uses_explicit_non_authorizing_scope_override(monkeypatch) -> None:
    monkeypatch.setattr(subject, "validate_full_resume_scope", lambda *_args, **_kwargs: [])


def test_w1b_materializes_bundle_units_without_singleton_vectors() -> None:
    registry = build_derived_bundle_registry(ROOT)

    assert validate_derived_bundle_registry(registry, ROOT) == []
    assert registry["coverage"] == {
        "headline": 8,
        "ibm_bullets": 8,
        "ibm_narrative": 8,
        "cluster_count": 16,
        "held_candidate_count": 2,
    }
    assert all(len(row["member_node_ids"]) >= 2 for row in registry["clusters"])
    assert all(row["future_vector_count"] == 1 for row in registry["clusters"])
    assert all(row["activation_status"] == "DERIVED_REVIEW_ONLY" for row in registry["clusters"])


def test_w1b_detects_tampered_registry_digest() -> None:
    registry = copy.deepcopy(build_derived_bundle_registry(ROOT))
    registry["coverage"]["headline"] = 7
    registry["derived_registry_sha256"] = canonical_sha256(
        {key: value for key, value in registry.items() if key != "derived_registry_sha256"}
    )

    assert "SECTION_COVERAGE" in validate_derived_bundle_registry(registry, ROOT)
