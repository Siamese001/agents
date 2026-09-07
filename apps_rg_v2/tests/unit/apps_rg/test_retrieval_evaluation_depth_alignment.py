"""Production retrieval fan-out must match the configured evaluation cutoff."""
from __future__ import annotations

from pathlib import Path

import yaml


_APPS_RG_ROOT = Path(__file__).resolve().parents[3] / "src" / "apps_rg"


def test_production_retrieval_fanout_matches_evaluation_gate_k() -> None:
    evaluation = yaml.safe_load(
        (_APPS_RG_ROOT / "config" / "domain_contract" / "resume_graph_evaluation_profile.yaml").read_text(
            encoding="utf-8"
        )
    )
    production = yaml.safe_load(
        (_APPS_RG_ROOT / "config" / "domain_contract" / "section_retrieval_profile.yaml").read_text(
            encoding="utf-8"
        )
    )

    gate_k = int(evaluation["retrieval"]["gate_k"])

    assert int(production["sparse_lane_defaults"]["sparse_top_k"]) == gate_k
    assert production["sections"]
    for section in production["sections"]:
        assert int(section["dense_top_k"]) == gate_k, section["section_id"]
        assert int(section["max_k"]) == gate_k, section["section_id"]
