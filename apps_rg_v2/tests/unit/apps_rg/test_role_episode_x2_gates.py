"""Unit tests for InsurTech/EY role-episode deterministic X2 gates."""
# apps-test-model: APP CONTRACT

from __future__ import annotations

from pathlib import Path

import pytest

from apps_rg.runtime.sections import role_episode_lane
from apps_rg.runtime.sections.role_episode_lane import (
    ROLE_EPISODE_X2_GATE_IDS_BY_RUN_FUNCTION,
    _narrative_source_ids_for_claim,
    _parsed_claim_ledger_source_ids_for_narrative,
    run_ey_bullets_x2_gates,
    run_ey_narrative_x2_gates,
    run_insurtech_bullets_x2_gates,
    run_insurtech_narrative_x2_gates,
)
from apps_rg.runtime.sections.section_product_shape_ssot import (
    NARRATIVE_MAX_CHARS,
    NARRATIVE_MAX_WORDS,
    product_shape_gate_ids_for_lane,
)
from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
    check_experience_bullet_evidence_density,
)


def _gate_map(gates: list[dict]) -> dict[str, bool]:
    return {str(g["gate_id"]): bool(g["pass"]) for g in gates}


def _gate_by_id(gates: list[dict]) -> dict[str, dict]:
    return {str(g["gate_id"]): g for g in gates}


def _valid_bullets(prefix: str) -> list[dict]:
    return [
        {
            "bullet_id": f"{prefix}_{i:03d}",
            "bullet_text": f"Outcome {i} for regulated delivery.",
            "source_fact_ids": [f"{prefix}_{i:03d}"],
        }
        for i in range(1, 4)
    ]


def test_insurtech_bullets_valid_payload_passes_core_gates() -> None:
    bullets = _valid_bullets("bul_insurtech")[:2]
    allowed = [b["bullet_id"] for b in bullets]
    l2 = {
        "bullets": bullets,
        "claim_ledger": [{"claim_text": b["bullet_text"], "source_fact_ids": b["source_fact_ids"]} for b in bullets],
        "role_episode_bundle_consumed": True,
    }
    gates = run_insurtech_bullets_x2_gates(
        l2=l2,
        allowed=allowed,
        runtime_generation_status="REAL_LLM",
    )
    by_id = _gate_map(gates)
    assert by_id["x2_insurtech_bullets_bullet_count_2"] is True
    assert by_id["x2_insurtech_bullets_graph_role_episode_bundle_consumed"] is True
    assert by_id["x2_insurtech_bullets_source_fact_ids_supported"] is True
    assert by_id["x2_no_first_person"] is True


def test_insurtech_bullet_lane_uses_truncation_safe_output_budget() -> None:
    cfg = role_episode_lane._ROLE_LANES["insurtech_bullets"]
    narrative_cfg = role_episode_lane._ROLE_LANES["insurtech_narrative"]

    assert role_episode_lane._max_output_tokens_for_lane(cfg) >= 2200
    assert (
        role_episode_lane._max_output_tokens_for_lane(narrative_cfg)
        == role_episode_lane.MAX_OUTPUT_TOKENS
    )


def test_ey_narrative_valid_sentence_passes_budget_gates() -> None:
    narrative = "Led enterprise risk analytics modernization across regulated insurance programs."
    l2 = {
        "narrative_sentence": narrative,
        "claim_ledger": [{"claim_text": narrative, "source_fact_ids": ["bul_ey_001"]}],
    }
    gates = run_ey_narrative_x2_gates(
        l2=l2,
        allowed=["bul_ey_001", "bul_ey_002", "bul_ey_003"],
        runtime_generation_status="REAL_LLM",
    )
    by_id = _gate_map(gates)
    assert by_id["x2_ey_narrative_exactly_one_sentence"] is True
    assert by_id["x2_ey_narrative_word_budget"] is True
    assert by_id["x2_ey_narrative_char_budget"] is True
    assert len(narrative.split()) <= NARRATIVE_MAX_WORDS
    assert len(narrative) <= NARRATIVE_MAX_CHARS


def test_insurtech_narrative_source_ids_reconcile_material_claims() -> None:
    narrative = (
        "Founded and led a cloud-native insurer modernization firm that turned regulated AWS "
        "demand into repeatable partner-ready delivery, pairing safety-first control design with "
        "lean execution, cloud economics, and founder-led GTM to make complex workloads "
        "deployable at scale."
    )
    allowed = [
        "reb_insurtech_founder_led_market_creation",
        "reb_insurtech_founder_led_gtm_revenue",
        "reb_insurtech_lean_delivery_operating_model",
        "reb_insurtech_aws_cloud_economics",
        "reb_insurtech_aws_migration_execution",
        "reb_insurtech_aws_shared_responsibility_operating_model",
        "reb_insurtech_regulated_aws_control_implementation",
    ]
    selected_fact_plan = {
        "facts": [
            {"fact_id": fid, "claim_text": f"{fid} claim"}
            for fid in allowed
        ]
    }

    source_ids, added = _narrative_source_ids_for_claim(
        narrative=narrative,
        raw_source_ids=["reb_insurtech_founder_led_market_creation"],
        allowed=allowed,
        selected_fact_plan=selected_fact_plan,
    )

    assert "reb_insurtech_founder_led_gtm_revenue" in source_ids
    assert "reb_insurtech_lean_delivery_operating_model" in source_ids
    assert "reb_insurtech_aws_cloud_economics" in source_ids
    assert "reb_insurtech_aws_migration_execution" in source_ids
    assert "reb_insurtech_aws_shared_responsibility_operating_model" in source_ids
    assert "reb_insurtech_regulated_aws_control_implementation" in source_ids
    assert set(added).issubset(set(allowed))

    gates = run_insurtech_narrative_x2_gates(
        l2={
            "narrative_sentence": narrative,
            "claim_ledger": [{"claim_text": narrative, "source_fact_ids": source_ids}],
        },
        allowed=allowed,
        runtime_generation_status="REAL_LLM",
    )
    assert all(g["pass"] for g in gates)


def test_ey_narrative_preserves_parsed_claim_ledger_source_ids_for_x1d_support() -> None:
    narrative = (
        "Architected governed modernization programs that translated complex risk and insurance "
        "operations into auditable, scalable workflows with traceable controls, enabling enterprise "
        "stakeholders to adopt new capabilities without sacrificing model risk discipline or deployment quality."
    )
    allowed = [
        "reb_ey_regulatory_analytics_modernization",
        "reb_ey_capital_optimization_solvency",
        "reb_ey_ccar_capital_liquidity_stress_testing",
        "reb_ey_insurance_core_modernization",
        "reb_ey_erm_risk_governance",
    ]
    parsed = {
        "narrative_sentence": narrative,
        "claim_ledger": [
            {
                "claim_text": (
                    "Architected governed modernization programs that translated complex risk "
                    "and insurance operations into auditable, scalable workflows."
                ),
                "source_fact_ids": [
                    "reb_ey_regulatory_analytics_modernization",
                    "reb_ey_insurance_core_modernization",
                    "reb_ey_erm_risk_governance",
                ],
            },
            {
                "claim_text": (
                    "Enabled enterprise stakeholders to adopt new capabilities without sacrificing "
                    "model risk discipline or deployment quality."
                ),
                "source_fact_ids": [
                    "reb_ey_ccar_capital_liquidity_stress_testing",
                    "reb_ey_capital_optimization_solvency",
                    "reb_ey_erm_risk_governance",
                ],
            },
        ],
    }
    selected_fact_plan = {"facts": [{"fact_id": fid, "claim_text": fid} for fid in allowed]}

    parsed_ids = _parsed_claim_ledger_source_ids_for_narrative(
        parsed=parsed,
        narrative=narrative,
        allowed=allowed,
    )
    source_ids, added = _narrative_source_ids_for_claim(
        narrative=narrative,
        raw_source_ids=parsed_ids,
        allowed=allowed,
        selected_fact_plan=selected_fact_plan,
    )

    assert "reb_ey_insurance_core_modernization" in parsed_ids
    assert "reb_ey_insurance_core_modernization" in source_ids
    assert "reb_ey_erm_risk_governance" in source_ids
    assert set(added).issubset(set(allowed))
    gates = run_ey_narrative_x2_gates(
        l2={
            "narrative_sentence": narrative,
            "claim_ledger": [{"claim_text": narrative, "source_fact_ids": source_ids}],
        },
        allowed=allowed,
        runtime_generation_status="REAL_LLM",
    )
    assert all(g["pass"] for g in gates)


@pytest.mark.parametrize(
    "run_fn,lane",
    [
        (run_insurtech_bullets_x2_gates, "insurtech_bullets"),
        (run_insurtech_narrative_x2_gates, "insurtech_narrative"),
        (run_ey_bullets_x2_gates, "ey_bullets"),
        (run_ey_narrative_x2_gates, "ey_narrative"),
    ],
)
def test_role_episode_gate_registry_matches_product_shape_ssot(run_fn, lane: str) -> None:
    fn_name = run_fn.__name__
    advertised = ROLE_EPISODE_X2_GATE_IDS_BY_RUN_FUNCTION[fn_name]
    assert advertised == product_shape_gate_ids_for_lane(lane) | {
        "x2_x1d_required_judges_present",
        "x2_x1d_schema_valid",
    }


def test_role_episode_empty_llm_bullets_fail_closed_without_graph_render() -> None:
    cfg = role_episode_lane._ROLE_LANES["insurtech_bullets"]
    parsed, parse_error = role_episode_lane._parse_json_object("")
    facts = [
        {
            "fact_id": f"bul_insurtech_{idx:03d}",
            "claim_text": f"Delivered regulated platform control outcome {idx}.",
        }
        for idx in range(1, 4)
    ]

    bullets, receipt = role_episode_lane._materialize_bullet_generation(
        cfg=cfg,
        parsed=parsed,
        parse_error=parse_error,
        provider_runtime_generation_status="REAL_LLM",
        facts=facts,
        allowed=[f["fact_id"] for f in facts],
        graph_packet_digest="digest://graph-packet",
    )

    assert bullets == []
    assert receipt["generation_method"] == "model_output_invalid"
    assert receipt["llm_generation_status"] == "empty_output"
    assert receipt["llm_output_used"] is False
    assert receipt["evidence_authority"] == "augmented_skills_graph"
    assert receipt["source_fact_ids"] == []
    assert receipt["graph_packet_digest"] == "digest://graph-packet"
    assert receipt["renderer_version"] == ""
    assert receipt["rendered_source_fact_ids_within_allowed_packet"] is True


def test_role_episode_bullet_normalization_strips_targeting_only_tail_claim() -> None:
    cfg = role_episode_lane._ROLE_LANES["ey_bullets"]
    parsed = {
        "bullets": [
            {
                "bullet_id": "bul_ey_001",
                "bullet_text": (
                    "Led CCAR-era capital and liquidity controls for regulated financial institutions, "
                    "mirroring the enterprise-grade rigor required to enable partner-led deployments "
                    "of frontier AI at scale."
                ),
                "source_fact_ids": ["reb_ey_ccar_capital_liquidity_stress_testing"],
            }
        ]
    }

    bullets = role_episode_lane._normalize_bullets(
        parsed,
        cfg=cfg,
        allowed=["reb_ey_ccar_capital_liquidity_stress_testing"],
    )

    assert bullets[0]["bullet_text"] == (
        "Led CCAR-era capital and liquidity controls for regulated financial institutions."
    )
    assert role_episode_lane._targeting_only_experience_hits(bullets[0]["bullet_text"]) == []


def test_role_episode_x2_catches_unstripped_targeting_only_experience_claim() -> None:
    text = (
        "Led CCAR-era capital controls while enabling partner-led deployments "
        "of frontier AI at scale."
    )
    l2 = {
        "bullets": [
            {
                "bullet_id": "bul_ey_001",
                "bullet_text": text,
                "source_fact_ids": ["reb_ey_ccar_capital_liquidity_stress_testing"],
            },
            {
                "bullet_id": "bul_ey_002",
                "bullet_text": "Architected enterprise risk-governance operating models.",
                "source_fact_ids": ["reb_ey_erm_risk_governance"],
            },
            {
                "bullet_id": "bul_ey_003",
                "bullet_text": "Directed regulatory analytics modernization for global banks.",
                "source_fact_ids": ["reb_ey_regulatory_analytics_modernization"],
            },
        ],
        "claim_ledger": [
            {"claim_text": text, "source_fact_ids": ["reb_ey_ccar_capital_liquidity_stress_testing"]},
            {
                "claim_text": "Architected enterprise risk-governance operating models.",
                "source_fact_ids": ["reb_ey_erm_risk_governance"],
            },
            {
                "claim_text": "Directed regulatory analytics modernization for global banks.",
                "source_fact_ids": ["reb_ey_regulatory_analytics_modernization"],
            },
        ],
        "role_episode_bundle_consumed": True,
    }
    gates = run_ey_bullets_x2_gates(
        l2=l2,
        allowed=[
            "reb_ey_ccar_capital_liquidity_stress_testing",
            "reb_ey_erm_risk_governance",
            "reb_ey_regulatory_analytics_modernization",
        ],
        runtime_generation_status="REAL_LLM",
    )
    by_id = {g["gate_id"]: g for g in gates}

    assert by_id["x2_ey_bullets_targeting_only_not_experience_claim"]["pass"] is False
    assert "frontier_ai_as_experience" in by_id[
        "x2_ey_bullets_targeting_only_not_experience_claim"
    ]["observed_value"]


def test_role_episode_deterministic_graph_render_excludes_out_of_packet_facts() -> None:
    cfg = role_episode_lane._ROLE_LANES["ey_bullets"]
    facts = [
        {"fact_id": "bul_ey_001", "claim_text": "Led audited delivery controls."},
        {"fact_id": "outside_fact_999", "claim_text": "This fact is not allowed."},
    ]

    bullets = role_episode_lane._deterministic_graph_bullet_render(
        cfg=cfg,
        facts=facts,
        allowed=["bul_ey_001"],
    )

    assert [b["source_fact_ids"] for b in bullets] == [["bul_ey_001"]]
    assert all("outside_fact_999" not in b["source_fact_ids"] for b in bullets)


def test_role_episode_bullet_path_has_no_fallback_bullet_symbol() -> None:
    source = Path(role_episode_lane.__file__).read_text(encoding="utf-8")

    assert "_fallback_bullets_from_facts" not in source
    assert "deterministic_graph_render" in source


def test_role_episode_display_file_is_written_before_x2_and_x3_binding() -> None:
    source = Path(role_episode_lane.__file__).read_text(encoding="utf-8")
    main_idx = source.index("def run_role_episode_lane_execution")
    output_write_idx = source.index("(artifact_dir / cfg.output_filename).write_text", main_idx)
    x2_write_idx = source.index('artifact_dir / "x2_gate_outputs.json"', output_write_idx)
    x3_finalize_idx = source.index("x3 = finalize_section_lane_x3(", x2_write_idx)

    assert output_write_idx < x2_write_idx < x3_finalize_idx


def test_role_episode_l6_handoff_is_built_after_sealed_runtime_exit() -> None:
    """Shared role lanes must expose the same source identity as dedicated lanes."""
    source = Path(role_episode_lane.__file__).read_text(encoding="utf-8")
    main_idx = source.index("def run_role_episode_lane_execution")
    l2_finalize_idx = source.index("finalize_section_l2_after_output(", main_idx)
    exhaust_idx = source.index("finalize_section_runtime_exhaust_before_l6(", l2_finalize_idx)
    l6_gate_idx = source.index("gate_section_l6_shadow_after_exhaust(", exhaust_idx)
    l6_build_idx = source.index("build_l6_shadow_handoff_dict(", l6_gate_idx)
    l6_write_idx = source.index(
        'write_json(artifact_dir / "l6_shadow_eval_package.json", l6_package)',
        l6_build_idx,
    )

    assert l2_finalize_idx < exhaust_idx < l6_gate_idx < l6_build_idx < l6_write_idx


def test_ey_model_bullet_target_overwrite_is_discarded_before_display() -> None:
    cfg = role_episode_lane._ROLE_LANES["ey_bullets"]
    facts = [
        {
            "fact_id": "reb_ey_regulatory_analytics_modernization",
            "claim_text": "EY graph evidence supports regulatory analytics data domains mapped through lineage controls.",
        },
        {
            "fact_id": "reb_ey_capital_optimization_solvency",
            "claim_text": "EY graph evidence supports capital stress scenarios run for hedge design.",
        },
        {
            "fact_id": "reb_ey_erm_risk_governance",
            "claim_text": "EY graph evidence supports risk metric definitions standardized across reporting stakeholders.",
        },
    ]
    allowed = [str(f["fact_id"]) for f in facts]
    parsed = {
        "bullets": [
            {
                "bullet_text": "Led partner-led deployments of frontier AI at scale.",
                "source_fact_ids": [allowed[0]],
            },
            {
                "bullet_text": "Scaled target-role AI operating models for an AIG transformation.",
                "source_fact_ids": [allowed[1]],
            },
            {
                "bullet_text": "Drove alliance-led AI adoption for insurance executives.",
                "source_fact_ids": [allowed[2]],
            },
        ],
        "claim_ledger": [],
    }

    bullets, receipt = role_episode_lane._materialize_bullet_generation(
        cfg=cfg,
        parsed=parsed,
        parse_error="",
        provider_runtime_generation_status="REAL_LLM",
        facts=facts,
        allowed=allowed,
        graph_packet_digest="digest://ey-proof",
    )

    display_text = "\n".join(b["bullet_text"] for b in bullets)
    assert "partner-led deployments of frontier AI at scale" not in display_text
    assert "target-role" not in display_text
    assert [b["bullet_text"] for b in bullets] == [role_episode_lane._sentence(f["claim_text"]) for f in facts]
    assert receipt["generation_method"] == "llm_selected_proof_render"
    assert receipt["llm_output_used"] is False
    assert receipt["llm_selection_used"] is True
    assert receipt["model_display_text_discarded"] is True
    assert receipt["display_text_authority"] == "selected_fact_plan_claim_text"

    l2 = {
        "bullets": bullets,
        "claim_ledger": [
            {"claim_text": b["bullet_text"], "source_fact_ids": b["source_fact_ids"]}
            for b in bullets
        ],
        "selected_fact_plan": {"facts": facts},
        "role_episode_bundle_consumed": True,
        **receipt,
    }
    gates = run_ey_bullets_x2_gates(
        l2=l2,
        allowed=allowed,
        runtime_generation_status="REAL_LLM",
    )

    gate = _gate_by_id(gates)["x2_ey_bullets_display_text_proof_authorized"]
    assert gate["pass"] is True


def test_ey_erm_model_surface_gets_graph_bound_outcome_completion_before_x2() -> None:
    """A live-shaped ERM bullet cannot ship as a detail-only activity statement."""
    cfg = role_episode_lane._ROLE_LANES["ey_bullets"]
    facts = [
        {
            "fact_id": "bul_ey_001",
            "claim_text": "Led capital and liquidity stress-testing work for regulated institutions.",
        },
        {
            "fact_id": "bul_ey_002",
            "claim_text": "Directed regulatory analytics modernization with traceable controls.",
        },
        {
            "fact_id": "bul_ey_003",
            "role_episode_bundle_id": "reb_ey_erm_risk_governance",
            "claim_text": (
                "Architected ERM operating models and BCBS 239-aligned risk-data aggregation "
                "by defining three-lines-of-defense accountability, metadata standards, "
                "and auditable risk metrics."
            ),
            "claim_scope": "Regulated banking and insurance clients.",
            "allowed_graph_evidence_ids": [
                "reb_ey_erm_risk_governance",
                "metric_ey_risk_metric_definition_count",
            ],
        },
    ]
    parsed = {
        "bullets": [
            {
                "bullet_id": "bul_ey_001",
                "bullet_text": facts[0]["claim_text"],
                "source_fact_ids": ["bul_ey_001"],
            },
            {
                "bullet_id": "bul_ey_002",
                "bullet_text": facts[1]["claim_text"],
                "source_fact_ids": ["bul_ey_002"],
            },
            {
                "bullet_id": "bul_ey_003",
                "bullet_text": facts[2]["claim_text"],
                "source_fact_ids": ["bul_ey_003"],
            },
        ]
    }

    bullets, receipt = role_episode_lane._materialize_bullet_generation(
        cfg=cfg,
        parsed=parsed,
        parse_error="",
        provider_runtime_generation_status="REAL_LLM",
        facts=facts,
        allowed=[str(fact["fact_id"]) for fact in facts],
        graph_packet_digest="digest://ey-erm-outcome",
    )

    repaired = bullets[2]["bullet_text"]
    assert "regulated banking and insurance clients" in repaired
    assert "standardized risk-metric definitions" in repaired
    assert check_experience_bullet_evidence_density("bul_ey_003", repaired).passed
    assert receipt["graph_bound_evidence_density_repairs"] == [
        {
            "bullet_id": "bul_ey_003",
            "role_episode_bundle_id": "reb_ey_erm_risk_governance",
            "reason": "graph_bound_evidence_density_completion",
        }
    ]


def test_ey_capital_model_surface_gets_graph_bound_outcome_completion_before_x2() -> None:
    """A late reselected EY bullet cannot bypass the experience-evidence floor."""
    cfg = role_episode_lane._ROLE_LANES["ey_bullets"]
    facts = [
        {
            "fact_id": "bul_ey_001",
            "role_episode_bundle_id": "reb_ey_capital_optimization_solvency",
            "claim_text": (
                "Led quantitative derivatives, variable-annuity hedging, and insurance-capital "
                "work using exotic pricing, liability Greeks, higher-order stress testing, "
                "and hedge design."
            ),
            "claim_scope": "Regulated insurance portfolios.",
            "allowed_graph_evidence_ids": [
                "reb_ey_capital_optimization_solvency",
                "metric_ey_greek_cross_greek_scenario_count",
            ],
        },
        {
            "fact_id": "bul_ey_002",
            "claim_text": "Led CCAR model-validation work, establishing audit-ready evidence.",
        },
        {
            "fact_id": "bul_ey_003",
            "claim_text": "Architected BCBS 239 risk-data aggregation, enabling auditable controls.",
        },
    ]
    parsed = {
        "bullets": [
            {
                "bullet_id": fact["fact_id"],
                "bullet_text": fact["claim_text"],
                "source_fact_ids": [fact["fact_id"]],
            }
            for fact in facts
        ]
    }

    bullets, receipt = role_episode_lane._materialize_bullet_generation(
        cfg=cfg,
        parsed=parsed,
        parse_error="",
        provider_runtime_generation_status="REAL_LLM",
        facts=facts,
        allowed=[str(fact["fact_id"]) for fact in facts],
        graph_packet_digest="digest://ey-capital-outcome",
    )

    repaired = bullets[0]["bullet_text"]
    assert "higher-order stress scenarios" in repaired
    assert "delivering risk visibility" in repaired
    assert check_experience_bullet_evidence_density("bul_ey_001", repaired).passed
    assert receipt["graph_bound_evidence_density_repairs"] == [
        {
            "bullet_id": "bul_ey_001",
            "role_episode_bundle_id": "reb_ey_capital_optimization_solvency",
            "reason": "graph_bound_evidence_density_completion",
        }
    ]


def test_insurtech_graph_bound_model_surface_preserves_selected_outcome_detail() -> None:
    cfg = role_episode_lane._ROLE_LANES["insurtech_bullets"]
    facts = [
        {
            "fact_id": "bul_insurtech_001",
            "claim_text": "Implemented SOC 2-aligned AWS controls for regulated insurers adopting analytics and ML.",
        },
        {
            "fact_id": "bul_insurtech_002",
            "claim_text": "Built safety operating-model framing around AWS shared responsibility and insurer-owned controls.",
        },
    ]
    allowed = [str(fact["fact_id"]) for fact in facts]
    parsed = {
        "bullets": [
            {
                "bullet_text": "Implemented SOC 2-aligned AWS controls for regulated insurers, establishing an auditable baseline for production adoption.",
                "source_fact_ids": ["bul_insurtech_001"],
            },
            {
                "bullet_text": "Built an AWS shared-responsibility operating model for insurer-owned controls, establishing repeatable governance for regulated cloud adoption.",
                "source_fact_ids": ["bul_insurtech_002"],
            },
        ]
    }

    bullets, receipt = role_episode_lane._materialize_bullet_generation(
        cfg=cfg,
        parsed=parsed,
        parse_error="",
        provider_runtime_generation_status="REAL_LLM",
        facts=facts,
        allowed=allowed,
        graph_packet_digest="digest://insurtech-proof",
    )

    assert receipt["generation_method"] == "llm_selected_graph_bound_surface"
    assert receipt["llm_output_used"] is True
    assert receipt["model_display_text_discarded"] is False
    assert [row["bullet_text"] for row in bullets] == [
        row["bullet_text"] for row in parsed["bullets"]
    ]
    assert all(
        check_experience_bullet_evidence_density(row["bullet_id"], row["bullet_text"]).passed
        for row in bullets
    )

    l2 = {
        "bullets": bullets,
        "claim_ledger": [
            {"claim_text": row["bullet_text"], "source_fact_ids": row["source_fact_ids"]}
            for row in bullets
        ],
        "selected_fact_plan": {"facts": facts},
        "role_episode_bundle_consumed": True,
        **receipt,
    }
    display_gate = _gate_by_id(
        run_insurtech_bullets_x2_gates(
            l2=l2,
            allowed=allowed,
            runtime_generation_status="REAL_LLM",
        )
    )["x2_insurtech_bullets_display_text_proof_authorized"]
    assert display_gate["pass"] is True


def test_ey_duplicate_selected_source_fact_reselects_unique_proof_fact_before_display() -> None:
    cfg = role_episode_lane._ROLE_LANES["ey_bullets"]
    facts = [
        {
            "fact_id": "reb_ey_ccar_capital_liquidity_stress_testing",
            "claim_text": "Led CCAR-era capital, liquidity, and stress-testing initiatives with audit-ready governance evidence.",
        },
        {
            "fact_id": "reb_ey_erm_risk_governance",
            "claim_text": "Architected enterprise risk-governance operating models aligned to BCBS 239 accountability.",
        },
        {
            "fact_id": "reb_ey_regulatory_analytics_modernization",
            "claim_text": "Led regulatory analytics modernization by linking predictive risk analytics and lineage-backed workflows.",
        },
    ]
    allowed = [str(f["fact_id"]) for f in facts]
    parsed = {
        "bullets": [
            {
                "bullet_text": "Duplicate path variant A.",
                "source_fact_ids": [allowed[0]],
            },
            {
                "bullet_text": "Duplicate path variant B.",
                "source_fact_ids": [allowed[0]],
            },
            {
                "bullet_text": "Regulatory analytics variant.",
                "source_fact_ids": [allowed[2]],
            },
        ],
        "claim_ledger": [],
    }

    bullets, receipt = role_episode_lane._materialize_bullet_generation(
        cfg=cfg,
        parsed=parsed,
        parse_error="",
        provider_runtime_generation_status="REAL_LLM",
        facts=facts,
        allowed=allowed,
        graph_packet_digest="digest://ey-proof",
    )

    contract = receipt["final_materialized_selection_contract"]
    assert receipt["final_materialized_acceptance_ok"] is True
    assert contract["duplicate_source_fact_ids_ignored"] == [allowed[0]]
    assert contract["deterministic_reselect_source_fact_ids"] == [allowed[1]]
    assert [b["source_fact_ids"][0] for b in bullets] == [allowed[0], allowed[2], allowed[1]]
    assert len({b["source_fact_ids"][0] for b in bullets}) == 3


def test_role_episode_materializer_preserves_canonical_slot_source_identity() -> None:
    cfg = role_episode_lane._ROLE_LANES["insurtech_bullets"]
    facts = [
        {
            "fact_id": f"bul_insurtech_{index:03d}",
            "claim_text": "Led AWS modernization execution for insurance platforms."
            if index in (2, 3)
            else "Implemented SOC 2-aligned AWS controls for regulated insurers.",
        }
        for index in range(1, 3)
    ]
    selected_order = ["bul_insurtech_002", "bul_insurtech_001"]
    parsed = {
        "bullets": [
            {"bullet_text": f"Candidate {source_id}", "source_fact_ids": [source_id]}
            for source_id in selected_order
        ]
    }

    bullets, receipt = role_episode_lane._materialize_bullet_generation(
        cfg=cfg,
        parsed=parsed,
        parse_error="",
        provider_runtime_generation_status="REAL_LLM",
        facts=facts,
        allowed=selected_order,
        graph_packet_digest="digest://slot-bound-proof",
    )

    assert [row["bullet_id"] for row in bullets] == [
        "bul_insurtech_001",
        "bul_insurtech_002",
    ]
    assert [row["source_fact_ids"][0] for row in bullets] == [
        "bul_insurtech_001",
        "bul_insurtech_002",
    ]
    assert receipt["final_materialized_selection_contract"]["slot_bound_ordering_applied"] is True


def test_insurtech_legacy_modernization_leaf_has_a_distinct_bound_surface() -> None:
    fact = {
        "fact_id": "bul_insurtech_003",
        "claim_text": "Led AWS modernization execution for monolithic policy administration and insurance platform workloads.",
        "domain": "AWS Migration Execution for Legacy Insurance Platforms",
        "role_episode_bundle_id": "reb_insurtech_aws_migration_execution",
        "graph_skill_node_ids": ["skill_sr_insurtech_legacy_cloud_modernization"],
        "allowed_graph_evidence_ids": [
            "reb_insurtech_aws_migration_execution",
            "skill_sr_insurtech_legacy_cloud_modernization",
            "bul_insurtech_003",
        ],
    }

    rendered = role_episode_lane._proof_fact_text(fact)

    assert rendered == "Led legacy cloud modernization for AWS insurance platforms."
    assert role_episode_lane._proof_fact_composition_is_bound(rendered, fact) is True


def test_role_episode_display_text_gate_rejects_valid_id_with_unbacked_phrase() -> None:
    fact = {
        "fact_id": "reb_insurtech_founder_led_market_creation",
        "claim_text": "InsurTech graph evidence supports founder-led insurance market creation.",
    }
    l2 = {
        "narrative_sentence": "Led partner-led deployments of frontier AI at scale.",
        "claim_ledger": [
            {
                "claim_text": "Led partner-led deployments of frontier AI at scale.",
                "source_fact_ids": [fact["fact_id"]],
            }
        ],
        "selected_fact_plan": {"facts": [fact]},
        "display_text_authority": "selected_fact_plan_claim_text",
    }

    gates = run_insurtech_narrative_x2_gates(
        l2=l2,
        allowed=[fact["fact_id"]],
        runtime_generation_status="REAL_LLM",
    )

    gate = _gate_by_id(gates)["x2_insurtech_narrative_display_text_proof_authorized"]
    assert gate["pass"] is False
    assert gate["observed_value"]["status"] == "FAIL"


def test_insurtech_bullets_display_text_gate_rejects_valid_id_with_unbacked_phrase() -> None:
    facts = [
        {
            "fact_id": "reb_insurtech_founder_led_market_creation",
            "claim_text": "InsurTech graph evidence supports founder-led insurance market creation.",
        },
        {
            "fact_id": "reb_insurtech_aws_migration_execution",
            "claim_text": "InsurTech graph evidence supports AWS migration execution governance.",
        },
        {
            "fact_id": "reb_insurtech_regulated_aws_control_implementation",
            "claim_text": "InsurTech graph evidence supports regulated AWS control implementation.",
        },
    ]
    bullets = [
        {
            "bullet_text": "Led partner-led deployments of frontier AI at scale.",
            "source_fact_ids": [facts[0]["fact_id"]],
        },
        {
            "bullet_text": facts[1]["claim_text"],
            "source_fact_ids": [facts[1]["fact_id"]],
        },
        {
            "bullet_text": facts[2]["claim_text"],
            "source_fact_ids": [facts[2]["fact_id"]],
        },
    ]
    l2 = {
        "bullets": bullets,
        "claim_ledger": [
            {"claim_text": b["bullet_text"], "source_fact_ids": b["source_fact_ids"]}
            for b in bullets
        ],
        "selected_fact_plan": {"facts": facts},
        "display_text_authority": "selected_fact_plan_claim_text",
        "role_episode_bundle_consumed": True,
    }

    gates = run_insurtech_bullets_x2_gates(
        l2=l2,
        allowed=[f["fact_id"] for f in facts],
        runtime_generation_status="REAL_LLM",
    )

    gate = _gate_by_id(gates)["x2_insurtech_bullets_display_text_proof_authorized"]
    assert gate["pass"] is False
    assert gate["observed_value"]["status"] == "FAIL"


def test_ey_narrative_display_text_gate_rejects_valid_id_with_unbacked_phrase() -> None:
    fact = {
        "fact_id": "reb_ey_regulatory_analytics_modernization",
        "claim_text": "EY graph evidence supports regulatory analytics modernization.",
    }
    l2 = {
        "narrative_sentence": "Led partner-led deployments of frontier AI at scale.",
        "claim_ledger": [
            {
                "claim_text": "Led partner-led deployments of frontier AI at scale.",
                "source_fact_ids": [fact["fact_id"]],
            }
        ],
        "selected_fact_plan": {"facts": [fact]},
        "display_text_authority": "selected_fact_plan_claim_text",
        "role_episode_bundle_consumed": True,
    }

    gates = run_ey_narrative_x2_gates(
        l2=l2,
        allowed=[fact["fact_id"]],
        runtime_generation_status="REAL_LLM",
    )

    gate = _gate_by_id(gates)["x2_ey_narrative_display_text_proof_authorized"]
    assert gate["pass"] is False
    assert gate["observed_value"]["status"] == "FAIL"


def test_role_episode_payload_hash_excludes_private_l2_authority_objects() -> None:
    """L2's frozen in-process room must not make durable provenance hashing fail."""

    class _FrozenRoom:
        pass

    public_payload = {"section_id": "insurtech_bullets", "run_id": "run_1"}
    prepared_payload = {
        **public_payload,
        "_canonical_l2_frozen_room": _FrozenRoom(),
    }

    assert role_episode_lane._json_hash(prepared_payload) == role_episode_lane._json_hash(
        public_payload
    )
