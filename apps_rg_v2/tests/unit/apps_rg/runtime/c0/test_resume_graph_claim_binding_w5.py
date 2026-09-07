"""W5 exact final-claim binding and metric/path negative controls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.c0.resume_graph_allocation import (
    ALL_CLAIM_BEARING_SECTIONS,
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
)
from apps_rg.runtime.c0.resume_graph_claim_binding import (
    GRAPH_CLAIM_BINDING_GATE_ID,
    _claim_rows,
    _explicit_claim_unit,
    bind_final_claims_to_resume_graph_allocation,
    build_pre_x2_resume_graph_claim_binding_gate,
    merge_resume_graph_claim_binding_fields,
    validate_claim_rows_against_resume_graph_allocation,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _claim_unit(section_id: str) -> str:
    if section_id.endswith("_bullets"):
        employer = section_id.removesuffix("_bullets")
        return f"{section_id}:bul_{employer}_001"
    if section_id.endswith("_narrative"):
        return f"{section_id}:derived:01"
    if section_id == "competencies":
        return "competencies:skill:01"
    if section_id == "executive_summary":
        return "executive_summary:claim:01"
    return "headline:skill:01"


def _artifact_fixture(
    root: Path,
    *,
    section_id: str,
    claim_text: str = "Governed platform delivery.",
    source_id: str = "fact_1",
    assignments: list[dict] | None = None,
) -> list[dict]:
    unit = _claim_unit(section_id)
    if assignments is None:
        assignments = [
            {
                "section_id": section_id,
                "claim_unit_id": unit,
                "skill_id": "skill_1",
                "skill_label": "governed platform delivery",
                "fact_id": source_id,
                "root_id": "root_1",
                "metric_outcome_id": "",
                "metric_value": "",
                "metric_unit": "",
                "normalized_metric_signature": "",
                "graph_path_ids": ["root:root_1", "root:root_1/skill:skill_1"],
                "edge_ids": ["edge_1"],
                "citation_refs": [source_id],
                "proof_strength_raw": 1.0,
                "target_alignment_score": 0.5,
                "claim_entailment_score": 1.0,
                "metric_binding_score": 0.0,
                "path_confidence_raw": 1.0,
                "source_independence_score": 1.0,
                "selection_margin": 0.2,
                "counts_toward_global_uniqueness": not section_id.endswith(
                    "_narrative"
                ),
            }
        ]
    plan = {
        "section_id": section_id,
        "allocation_scope": "WHOLE_RESUME",
        "allocation_plan_digest": "a" * 64,
        "allocation_assignments": assignments,
        "facts": [
            {
                "fact_id": "root_1",
                "role_episode_bundle_id": "root_1",
                "allowed_graph_evidence_ids": [
                    source_id,
                    *[str(row.get("skill_id") or "") for row in assignments],
                    *[str(row.get("metric_outcome_id") or "") for row in assignments],
                ],
            }
        ],
    }
    ledger = [{"claim_text": claim_text, "source_fact_ids": [source_id]}]
    l2 = {
        "section_id": section_id,
        "claim_ledger": ledger,
        "selected_fact_plan": plan,
    }
    if section_id.endswith("_bullets"):
        l2["bullets"] = [
            {
                "bullet_id": unit.rsplit(":", 1)[-1],
                "bullet_text": claim_text,
                "source_fact_ids": [source_id],
            }
        ]
    _write_json(root / "selected_fact_plan.json", plan)
    _write_json(root / "l2_output.json", l2)
    _write_json(root / "claim_ledger.json", ledger)
    _write_json(
        root / "canonical_claim_ledger_v2.json",
        {
            "schema": "canonical_claim_ledger_v2",
            "claims": [
                {
                    "claim_id": f"{section_id}_claim_1",
                    "claim_text": claim_text,
                    "source_fact_ids": [source_id],
                }
            ],
        },
    )
    upstream = {
        "section_id": section_id,
        "resume_graph_allocation_plan_digest": "a" * 64,
    }
    _write_json(root / "compiled_prompt_artifact.json", upstream)
    _write_json(root / "final_evidence_contract.json", upstream)
    _write_json(root / "x1d_llm_judge_outputs.json", {"judges": []})
    _write_json(
        root / "x2_gate_outputs.json",
        {"gates": [{"gate_id": "x2_existing", "pass": True}]},
    )
    (root / "command_output.txt").write_text(claim_text + "\n", encoding="utf-8")
    return assignments


def test_graph_slot_source_precedes_duplicate_display_text_when_deriving_claim_unit(
    tmp_path: Path,
) -> None:
    same_text = "Led AWS modernization execution for insurance platforms."
    _write_json(
        tmp_path / "claim_ledger.json",
        [
            {"claim_text": same_text, "source_fact_ids": ["bul_insurtech_001"]},
            {"claim_text": same_text, "source_fact_ids": ["bul_insurtech_002"]},
        ],
    )
    l2 = {
        "bullets": [
            {"bullet_id": "bul_insurtech_001", "bullet_text": same_text},
            {"bullet_id": "bul_insurtech_002", "bullet_text": same_text},
        ]
    }

    rows = _claim_rows(tmp_path, l2)

    assert [row.get("bullet_id") for row in rows] == [None, None]
    assert [
        _explicit_claim_unit(row, section_id="insurtech_bullets") for row in rows
    ] == [
        "insurtech_bullets:bul_insurtech_001",
        "insurtech_bullets:bul_insurtech_002",
    ]


def test_graph_binding_prefers_current_l2_display_over_stale_command_transcript(
    tmp_path: Path,
) -> None:
    current = "Current repaired executive summary claim."
    _artifact_fixture(tmp_path, section_id="executive_summary", claim_text=current)
    (tmp_path / "command_output.txt").write_text(
        "Stale pre-repair executive summary claim.\n", encoding="utf-8"
    )
    l2 = json.loads((tmp_path / "l2_output.json").read_text(encoding="utf-8"))
    l2["resume_display_text"] = current
    _write_json(tmp_path / "l2_output.json", l2)

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="executive_summary",
    )

    assert contract["pass"] is True
    assert contract["rendered_claim_reconciliation_pass"] is True


@pytest.mark.parametrize("section_id", ALL_CLAIM_BEARING_SECTIONS)
def test_all_eleven_lanes_bind_visible_claims_to_exact_paths(
    tmp_path: Path,
    section_id: str,
) -> None:
    _artifact_fixture(tmp_path, section_id=section_id)

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id=section_id,
    )

    assert contract["pass"] is True
    assert contract["binding_coverage"] == 1.0
    assert contract["orphan_allocation_claim_unit_ids"] == []
    binding = contract["bindings"][0]
    assert binding["skill_ids"] == ["skill_1"]
    assert binding["fact_ids"] == ["fact_1"]
    assert binding["graph_path_ids"]
    assert binding["edge_ids"]
    assert binding["citation_refs"]

    x2 = json.loads((tmp_path / "x2_gate_outputs.json").read_text(encoding="utf-8"))
    graph_gate = next(
        row for row in x2["gates"] if row["gate_id"] == GRAPH_CLAIM_BINDING_GATE_ID
    )
    assert graph_gate["pass"] is True
    for name in (
        "l2_output.json",
        "canonical_claim_ledger_v2.json",
        "x1d_llm_judge_outputs.json",
    ):
        doc = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert doc["resume_graph_allocation_plan_digest"] == "a" * 64
        assert doc["graph_claim_binding_contract_digest"] == contract["contract_digest"]
        if name == "l2_output.json":
            assert doc["resume_graph_claim_binding_active"] is True
            assert doc["resume_graph_claim_binding_pass"] is True
            assert doc["graph_claim_bindings_ref"] == "graph_claim_bindings.json"
            assert "graph_claim_bindings" not in doc
    for name in ("compiled_prompt_artifact.json", "final_evidence_contract.json"):
        doc = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert doc["resume_graph_allocation_plan_digest"] == "a" * 64
        assert "graph_claim_binding_contract_digest" not in doc


def test_post_x3_metadata_merge_preserves_exact_graph_binding(tmp_path: Path) -> None:
    _artifact_fixture(tmp_path, section_id="executive_summary")
    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="executive_summary",
    )
    stale_in_memory_l2 = {
        "section_id": "executive_summary",
        "claim_ledger": [
            {
                "claim_text": "Governed platform delivery.",
                "source_fact_ids": ["fact_1"],
            }
        ],
        "proof_status": "PASS",
    }

    merged = merge_resume_graph_claim_binding_fields(
        stale_in_memory_l2,
        artifact_dir=tmp_path,
    )

    assert merged["proof_status"] == "PASS"
    assert merged["resume_graph_claim_binding_active"] is True
    assert merged["resume_graph_claim_binding_pass"] is True
    assert merged["resume_graph_allocation_plan_digest"] == "a" * 64
    assert merged["graph_claim_binding_contract_digest"] == contract["contract_digest"]
    assert merged["graph_claim_bindings_ref"] == "graph_claim_bindings.json"
    assert "graph_claim_bindings" not in merged


def test_deferred_l2_binding_persistence_does_not_create_interim_write_baseline(
    tmp_path: Path,
) -> None:
    _artifact_fixture(tmp_path, section_id="ibm_bullets")
    l2_path = tmp_path / "l2_output.json"
    before = l2_path.read_bytes()

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="ibm_bullets",
        persist_l2_envelope=False,
    )

    assert contract["pass"] is True
    assert l2_path.read_bytes() == before
    assert (tmp_path / "graph_claim_bindings.json").is_file()

    final_l2 = json.loads(before)
    final_l2["product_quality_status"] = "PASS"
    merged = merge_resume_graph_claim_binding_fields(
        final_l2,
        artifact_dir=tmp_path,
    )
    assert merged["resume_graph_claim_binding_pass"] is True
    assert merged["graph_claim_bindings_ref"] == "graph_claim_bindings.json"


def test_rendered_metric_requires_exact_allocated_value_and_unit(tmp_path: Path) -> None:
    assignments = _artifact_fixture(
        tmp_path,
        section_id="executive_summary",
        claim_text="Improved joint revenue growth by 21%.",
    )
    assignments[0].update(
        {
            "metric_outcome_id": "metric_growth_20pct",
            "metric_text": "20% joint revenue growth",
            "metric_value": "20",
            "metric_unit": "PERCENT",
            "normalized_metric_signature": "20 pct joint revenue growth",
            "metric_binding_score": 1.0,
        }
    )
    plan = json.loads((tmp_path / "selected_fact_plan.json").read_text(encoding="utf-8"))
    plan["allocation_assignments"] = assignments
    _write_json(tmp_path / "selected_fact_plan.json", plan)
    l2 = json.loads((tmp_path / "l2_output.json").read_text(encoding="utf-8"))
    l2["selected_fact_plan"] = plan
    _write_json(tmp_path / "l2_output.json", l2)

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="executive_summary",
    )

    assert contract["pass"] is False
    assert contract["metric_exactness_pass"] is False
    assert any(
        "rendered_metric_exact_value_unit_binding_failed" in reason
        for reason in contract["failure_reasons"]
    )
    x2 = json.loads((tmp_path / "x2_gate_outputs.json").read_text(encoding="utf-8"))
    assert GRAPH_CLAIM_BINDING_GATE_ID in x2["failed_gates"]


def test_unrendered_allocation_is_an_orphan_and_blocks(tmp_path: Path) -> None:
    assignments = _artifact_fixture(tmp_path, section_id="headline")
    assignments.append(
        {
            **assignments[0],
            "claim_unit_id": "headline:skill:02",
            "skill_id": "skill_2",
            "skill_label": "unrendered capability",
            "fact_id": "fact_2",
            "citation_refs": ["fact_2"],
            "graph_path_ids": ["root:root_2", "root:root_2/skill:skill_2"],
            "edge_ids": ["edge_2"],
            "root_id": "root_2",
        }
    )
    plan = json.loads((tmp_path / "selected_fact_plan.json").read_text(encoding="utf-8"))
    plan["allocation_assignments"] = assignments
    plan["facts"].append(
        {
            "fact_id": "root_2",
            "role_episode_bundle_id": "root_2",
            "allowed_graph_evidence_ids": ["fact_2", "skill_2"],
        }
    )
    _write_json(tmp_path / "selected_fact_plan.json", plan)
    l2 = json.loads((tmp_path / "l2_output.json").read_text(encoding="utf-8"))
    l2["selected_fact_plan"] = plan
    _write_json(tmp_path / "l2_output.json", l2)

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="headline",
    )

    assert contract["pass"] is False
    assert contract["orphan_allocation_claim_unit_ids"] == ["headline:skill:02"]


def test_unrendered_narrative_alternative_is_not_an_orphan(tmp_path: Path) -> None:
    assignments = _artifact_fixture(tmp_path, section_id="ibm_narrative")
    assignments.append(
        {
            **assignments[0],
            "claim_unit_id": "ibm_narrative:derived:02",
            "skill_id": "skill_alternative",
            "fact_id": "fact_alternative",
            "root_id": "root_alternative",
            "citation_refs": ["fact_alternative"],
            "graph_path_ids": ["root:root_alternative", "root:root_alternative/skill:skill_alternative"],
            "edge_ids": ["edge_alternative"],
            "counts_toward_global_uniqueness": False,
        }
    )
    plan = json.loads((tmp_path / "selected_fact_plan.json").read_text(encoding="utf-8"))
    plan["allocation_assignments"] = assignments
    _write_json(tmp_path / "selected_fact_plan.json", plan)
    l2 = json.loads((tmp_path / "l2_output.json").read_text(encoding="utf-8"))
    l2["selected_fact_plan"] = plan
    _write_json(tmp_path / "l2_output.json", l2)

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="ibm_narrative",
    )

    assert contract["pass"] is True
    assert contract["allocated_claim_unit_count"] == 2
    assert contract["required_allocated_claim_unit_count"] == 0
    assert contract["orphan_allocation_claim_unit_ids"] == []


def test_upstream_compiled_prompt_digest_drift_is_not_repaired(tmp_path: Path) -> None:
    _artifact_fixture(tmp_path, section_id="headline")
    compiled_path = tmp_path / "compiled_prompt_artifact.json"
    compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
    compiled["resume_graph_allocation_plan_digest"] = "b" * 64
    _write_json(compiled_path, compiled)

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="headline",
    )

    assert contract["pass"] is False
    assert (
        "compiled_prompt_artifact.json:upstream_allocation_digest_mismatch"
        in contract["failure_reasons"]
    )
    after = json.loads(compiled_path.read_text(encoding="utf-8"))
    assert after["resume_graph_allocation_plan_digest"] == "b" * 64


def test_unallocated_legacy_lane_is_not_reclassified(tmp_path: Path) -> None:
    _write_json(tmp_path / "l2_output.json", {"section_id": "headline"})
    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="headline",
    )
    assert contract["active"] is False
    assert contract["pass"] is True
    assert not (tmp_path / "graph_claim_bindings.json").exists()


def test_runtime_frozen_plan_survives_lane_specific_selection_echo(
    tmp_path: Path,
) -> None:
    _artifact_fixture(tmp_path, section_id="ibm_narrative")
    frozen_plan = json.loads(
        (tmp_path / "selected_fact_plan.json").read_text(encoding="utf-8")
    )
    lane_echo = {
        "through_line": "Partner-led platform transformation",
        "selected_theme_families": ["alliances"],
    }
    _write_json(tmp_path / "selected_fact_plan.json", lane_echo)
    l2 = json.loads((tmp_path / "l2_output.json").read_text(encoding="utf-8"))
    l2["selected_fact_plan"] = lane_echo
    _write_json(tmp_path / "l2_output.json", l2)
    _write_json(tmp_path / "runtime_payload.json", {"selected_fact_plan": frozen_plan})

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="ibm_narrative",
    )

    assert contract["active"] is True
    assert contract["pass"] is True
    assert contract["allocation_plan_digest"] == "a" * 64
    assert (tmp_path / "graph_claim_bindings.json").is_file()


def test_narrative_companion_bullet_ids_bind_to_reserved_derived_ordinals(
    tmp_path: Path,
) -> None:
    assignments = _artifact_fixture(
        tmp_path,
        section_id="ibm_narrative",
        source_id="fact_1",
    )
    assignments.append(
        {
            **assignments[0],
            "claim_unit_id": "ibm_narrative:derived:02",
            "skill_id": "skill_2",
            "fact_id": "fact_2",
            "root_id": "root_2",
            "citation_refs": ["fact_2"],
            "graph_path_ids": ["root:root_2", "root:root_2/skill:skill_2"],
            "edge_ids": ["edge_2"],
        }
    )
    plan = json.loads(
        (tmp_path / "selected_fact_plan.json").read_text(encoding="utf-8")
    )
    plan["allocation_assignments"] = assignments
    plan["facts"].append(
        {
            "fact_id": "root_2",
            "role_episode_bundle_id": "root_2",
            "allowed_graph_evidence_ids": ["fact_2", "skill_2"],
        }
    )
    _write_json(tmp_path / "selected_fact_plan.json", plan)
    ledger = [
        {
            "claim_text": "Governed platform delivery.",
            "source_fact_ids": ["bul_ibm_001", "bul_ibm_002"],
        }
    ]
    _write_json(tmp_path / "claim_ledger.json", ledger)
    l2 = json.loads((tmp_path / "l2_output.json").read_text(encoding="utf-8"))
    l2["selected_fact_plan"] = plan
    l2["claim_ledger"] = ledger
    _write_json(tmp_path / "l2_output.json", l2)

    contract = bind_final_claims_to_resume_graph_allocation(
        tmp_path,
        section_id="ibm_narrative",
    )

    assert contract["pass"] is True
    assert contract["bound_claim_count"] == 1
    assert contract["bindings"][0]["allocation_claim_unit_ids"] == [
        "ibm_narrative:derived:01",
        "ibm_narrative:derived:02",
    ]


def test_real_graph_allocation_slices_bind_for_all_eleven_lanes(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[5]
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo_root,
        target_role="SVP Agentic Engineering",
        jd_text="agentic platform governance revenue growth margin",
        briefing_text="enterprise platform operating model",
    )
    plan = bundle["allocation_plan"]
    for section_id in ALL_CLAIM_BEARING_SECTIONS:
        section_dir = tmp_path / section_id
        section_dir.mkdir()
        sliced = slice_section_plan_for_allocation(
            section_plan=bundle["section_plans"][section_id],
            allocation_plan=plan,
            final_evidence_contract=bundle["section_final_evidence_contracts"][section_id],
            section_id=section_id,
        )
        assignments = sliced["allocation_assignments"]
        claims: list[dict] = []
        bullets: list[dict] = []
        visible: list[str] = []
        for index, assignment in enumerate(assignments, start=1):
            label = str(
                assignment.get("skill_label") or assignment.get("skill_id") or "capability"
            )
            metric = str(assignment.get("metric_text") or "")
            text = f"{label} delivered {metric}." if metric else f"Demonstrated {label}."
            claim = {
                "claim_id": f"{section_id}_claim_{index}",
                "claim_unit_id": assignment["claim_unit_id"],
                "claim_text": text,
                "source_fact_ids": [assignment["fact_id"]],
            }
            claims.append(claim)
            visible.append(text)
            if section_id.endswith("_bullets"):
                bullets.append(
                    {
                        "bullet_id": str(assignment["claim_unit_id"]).rsplit(":", 1)[-1],
                        "bullet_text": text,
                        "source_fact_ids": [assignment["fact_id"]],
                    }
                )
        l2 = {
            "section_id": section_id,
            "selected_fact_plan": sliced,
            "claim_ledger": claims,
            "bullets": bullets,
        }
        _write_json(section_dir / "selected_fact_plan.json", sliced)
        _write_json(section_dir / "l2_output.json", l2)
        _write_json(section_dir / "claim_ledger.json", claims)
        _write_json(
            section_dir / "canonical_claim_ledger_v2.json",
            {"schema": "canonical_claim_ledger_v2", "claims": claims},
        )
        _write_json(section_dir / "x2_gate_outputs.json", {"gates": []})
        _write_json(section_dir / "x1d_llm_judge_outputs.json", {"judges": []})
        upstream = {
            "resume_graph_allocation_plan_digest": plan["allocation_plan_digest"]
        }
        _write_json(section_dir / "compiled_prompt_artifact.json", upstream)
        _write_json(section_dir / "final_evidence_contract.json", upstream)
        (section_dir / "command_output.txt").write_text(
            "\n".join(visible) + "\n", encoding="utf-8"
        )

        contract = bind_final_claims_to_resume_graph_allocation(
            section_dir,
            section_id=section_id,
        )

        assert contract["pass"] is True, (section_id, contract["failure_reasons"])
        assert contract["bound_claim_count"] == len(assignments)
        assert contract["orphan_allocation_claim_unit_ids"] == []
        assert contract["allocation_plan_digest"] == plan["allocation_plan_digest"]


def test_pre_x2_projection_blocks_causal_merge_across_unrelated_roots() -> None:
    assignments = [
        {
            "section_id": "executive_summary",
            "claim_unit_id": "executive_summary:claim:01",
            "root_id": "root_revenue",
            "fact_id": "fact_revenue",
            "citation_refs": ["fact_revenue"],
            "counts_toward_global_uniqueness": True,
        },
        {
            "section_id": "executive_summary",
            "claim_unit_id": "executive_summary:claim:02",
            "root_id": "root_team",
            "fact_id": "fact_team",
            "citation_refs": ["fact_team"],
            "counts_toward_global_uniqueness": True,
        },
    ]
    plan = {
        "allocation_plan_digest": "b" * 64,
        "allocation_assignments": assignments,
        "facts": [
            {
                "fact_id": "root_revenue",
                "role_episode_bundle_id": "root_revenue",
                "allowed_graph_evidence_ids": ["fact_revenue"],
            },
            {
                "fact_id": "root_team",
                "role_episode_bundle_id": "root_team",
                "allowed_graph_evidence_ids": ["fact_team"],
            },
        ],
    }
    claims = [
        {
            "claim_text": "Revenue growth generated team scale.",
            "source_fact_ids": ["fact_revenue", "fact_team"],
        }
    ]

    failures = validate_claim_rows_against_resume_graph_allocation(
        section_id="executive_summary",
        claim_rows=claims,
        selected_fact_plan=plan,
    )
    gate = build_pre_x2_resume_graph_claim_binding_gate(
        section_id="executive_summary",
        claim_rows=claims,
        selected_fact_plan=plan,
    )

    assert "claim_1:causal_claim_merges_unrelated_graph_roots" in failures
    assert gate is not None
    assert gate["gate_id"] == GRAPH_CLAIM_BINDING_GATE_ID
    assert gate["pass"] is False


def test_slot_rooted_metric_derivative_binds_to_exact_frozen_bullet_unit() -> None:
    plan = {
        "allocation_plan_digest": "unify-derivative-plan",
        "facts": [
            {
                "fact_id": "reb_unify_agentic_platform_architecture",
                "role_episode_bundle_id": "reb_unify_agentic_platform_architecture",
                "linked_source_fact_ids": ["fact_engineering_platform_001"],
            }
        ],
        "allocation_assignments": [
            {
                "section_id": "unify_bullets",
                "claim_unit_id": "unify_bullets:bul_unify_001",
                "root_id": "reb_unify_agentic_platform_architecture",
                "skill_id": "skill_unify_agentic_l0_route_policy_dispatch",
                "fact_id": "fact_engineering_platform_001",
                "metric_outcome_id": "metric_unify_policy_gated_agent_execution_surface",
                "metric_value": "",
                "metric_unit": "",
                "counts_toward_global_uniqueness": True,
            }
        ],
    }
    failures = validate_claim_rows_against_resume_graph_allocation(
        section_id="unify_bullets",
        claim_rows=[
            {
                "claim_text": "Established a policy-gated agent execution surface.",
                "source_fact_ids": [
                    "bul_unify_001",
                    "fact_engineering_platform_001",
                    "bul_unify_001_metric_a50f35f7",
                ],
            }
        ],
        selected_fact_plan=plan,
    )

    assert failures == []
