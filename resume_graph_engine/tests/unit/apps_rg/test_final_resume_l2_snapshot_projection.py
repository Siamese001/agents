from __future__ import annotations

import json

import pytest

from apps_rg.runtime.assembly.l2_snapshot_projection import (
    L2_SNAPSHOT_PROJECTION_SCHEMA,
    omitted_l2_projection_paths,
    project_l2_output_for_final_resume,
)


def test_projection_omits_only_verbose_plan_exhaust_and_preserves_authority() -> None:
    source = {
        "headline_line": "SVP Engineering | Partner Pursuits | Runtime Governance | Platform Scale",
        "claim_ledger": [
            {"claim_text": "Partner Pursuits", "source_fact_ids": ["fact_partner"]}
        ],
        "graph_claim_bindings": {"pass": True, "bindings": [{"fact_id": "fact_partner"}]},
        "selected_fact_plan": {
            "schema_version": "apps_rg.selected_fact_plan.v1",
            "plan_digest": "sha256:plan",
            "allocation_plan_digest": "sha256:allocation",
            "facts": [
                {
                    "fact_id": "fact_partner",
                    "claim_text": "Owned partner pursuits",
                    "graph_skill_node_ids": ["skill_partner"],
                }
            ],
            "selected_skill_ids": ["skill_partner"],
            "allowed_graph_evidence_ids": ["fact_partner", "skill_partner"],
            "graph_candidate_decision_ledger": [{"candidate": "x" * 100_000}],
            "allocation_source_traversal_evidence": {"rows": ["y" * 100_000]},
            "graph_traversal_receipt": {"rows": ["z" * 100_000]},
        },
    }

    projected = project_l2_output_for_final_resume(source)

    assert projected["headline_line"] == source["headline_line"]
    assert projected["claim_ledger"] == source["claim_ledger"]
    assert projected["graph_claim_bindings"] == source["graph_claim_bindings"]
    assert projected["selected_fact_plan"]["facts"] == source["selected_fact_plan"]["facts"]
    assert projected["selected_fact_plan"]["allocation_plan_digest"] == "sha256:allocation"
    assert projected["selected_fact_plan"]["selected_skill_ids"] == ["skill_partner"]
    assert "graph_candidate_decision_ledger" not in projected["selected_fact_plan"]
    assert "allocation_source_traversal_evidence" not in projected["selected_fact_plan"]
    assert "graph_traversal_receipt" not in projected["selected_fact_plan"]
    assert source["selected_fact_plan"]["graph_candidate_decision_ledger"]
    assert len(json.dumps(projected)) < len(json.dumps(source)) // 10
    assert omitted_l2_projection_paths(source) == [
        "selected_fact_plan.allocation_source_traversal_evidence",
        "selected_fact_plan.graph_candidate_decision_ledger",
        "selected_fact_plan.graph_traversal_receipt",
    ]
    assert L2_SNAPSHOT_PROJECTION_SCHEMA == "apps_rg.final_resume_l2_projection.v1"


def test_projection_preserves_unknown_non_diagnostic_plan_fields() -> None:
    source = {"selected_fact_plan": {"future_material_authority_field": {"fact_id": "f1"}}}
    projected = project_l2_output_for_final_resume(source)
    assert projected == source


def test_projection_hydrates_digest_bound_graph_binding_sidecar() -> None:
    source = {
        "resume_graph_claim_binding_active": True,
        "resume_graph_claim_binding_pass": True,
        "graph_claim_binding_contract_digest": "sha256:binding",
        "graph_claim_bindings_ref": "graph_claim_bindings.json",
    }
    contract = {
        "active": True,
        "pass": True,
        "contract_digest": "sha256:binding",
        "bindings": [{"visible_claim_text": "Governed platform delivery."}],
    }

    projected = project_l2_output_for_final_resume(
        source,
        graph_claim_binding_contract=contract,
    )

    assert "graph_claim_bindings" not in source
    assert projected["graph_claim_bindings"] == contract["bindings"]


def test_projection_fails_closed_on_graph_binding_sidecar_digest_mismatch() -> None:
    source = {
        "resume_graph_claim_binding_active": True,
        "resume_graph_claim_binding_pass": True,
        "graph_claim_binding_contract_digest": "sha256:expected",
        "graph_claim_bindings_ref": "graph_claim_bindings.json",
    }

    with pytest.raises(ValueError, match="digest mismatch"):
        project_l2_output_for_final_resume(
            source,
            graph_claim_binding_contract={
                "active": True,
                "pass": True,
                "contract_digest": "sha256:other",
                "bindings": [],
            },
        )
