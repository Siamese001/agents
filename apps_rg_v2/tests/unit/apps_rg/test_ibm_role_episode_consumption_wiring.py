"""IBM role episode consumption wiring — C0, proof pool, config, and X2 guards."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from apps_rg.repository_layout import resolve_apps_rg_path

REPO = Path(__file__).resolve().parents[3]
PROFILE_PATH = resolve_apps_rg_path(
    REPO, "config", "domain_contract", "section_retrieval_profile.yaml"
)


def _section_profiles(section_id: str) -> list[dict]:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        profile = yaml.safe_load(f)
    sections = profile.get("sections", []) if isinstance(profile, dict) else []
    return [p for p in sections if isinstance(p, dict) and p.get("section_id") == section_id]


class TestRoleEpisodeEvidencePack:
    def test_format_bullets_pack_includes_bundle_ids(self) -> None:
        from apps_rg.runtime.sections.ibm_role_episode_evidence import (
            IBM_BULLET_SLOT_BUNDLE_MAP,
            format_ibm_role_episode_evidence_pack,
        )

        payload: dict = {"allowed_fact_ids": ["bul_ibm_001"], "selected_fact_plan": {}}
        text = format_ibm_role_episode_evidence_pack(payload, section_id="ibm_bullets")
        assert "role_episode_bundle_id:" in text
        assert "proof_authority = graph_role_episode_bundles_plus_linked_source_facts" in text
        assert "base_resume_usage = calibration_only" in text
        for slot, bundle_id in IBM_BULLET_SLOT_BUNDLE_MAP.items():
            assert bundle_id in text
        assert payload.get("role_episode_bundle_ids")

    def test_format_narrative_pack_no_canonical_facts_header(self) -> None:
        from apps_rg.runtime.sections.ibm_role_episode_evidence import (
            format_ibm_role_episode_evidence_pack,
        )

        payload: dict = {"selected_fact_plan": {"facts": []}, "allowed_fact_ids": []}
        text = format_ibm_role_episode_evidence_pack(payload, section_id="ibm_narrative")
        assert "CANONICAL IBM FACTS" not in text
        assert "ROLE_EPISODE_BUNDLE" in text

    def test_flat_skill_only_packet_detected(self) -> None:
        from apps_rg.runtime.sections.ibm_role_episode_evidence import (
            is_flat_skill_only_graph_packet,
        )

        assert is_flat_skill_only_graph_packet({"graph_skill_node_ids": ["skill_x"]}) is True
        assert is_flat_skill_only_graph_packet(
            {"role_episode_bundle_id": "reb_ibm_cloud_modernization"}
        ) is False

    def test_assert_bundle_id_raises_without_id(self) -> None:
        from apps_rg.runtime.sections.ibm_graph_role_episode_registry import (
            assert_role_episode_bundle_id_present,
        )

        with pytest.raises(ValueError, match="role_episode_bundle_id"):
            assert_role_episode_bundle_id_present({})


class TestProofPoolAttachment:
    def test_attach_role_episode_bundles_to_meta(self) -> None:
        from apps_rg.runtime.sections.ibm_role_episode_evidence import (
            attach_role_episode_bundles_to_proof_pool_metadata,
        )

        meta = attach_role_episode_bundles_to_proof_pool_metadata(
            {}, section_id="ibm_bullets"
        )
        assert meta.get("role_episode_bundle_consumption") is True
        assert len(meta.get("role_episode_bundles") or []) >= 5
        assert meta.get("flat_skill_only_graph_context_forbidden") is True


class TestConfigEnablement:
    @pytest.mark.parametrize("section_id", ["ibm_bullets", "ibm_narrative"])
    def test_graph_expansion_allowed_with_bundle_consumption(self, section_id: str) -> None:
        profiles = _section_profiles(section_id)
        assert profiles, f"{section_id} not in profile"
        for p in profiles:
            assert p.get("graph_expansion_allowed") is True
            assert p.get("role_episode_bundle_consumption") == "required"
            assert p.get("graph_expansion_mode") == "role_episode_bundle_only"


class TestX2RoleEpisodeGates:
    def _minimal_bullets_output(self) -> dict:
        from apps_rg.runtime.sections.ibm_role_episode_evidence import (
            IBM_BULLET_SLOT_BUNDLE_MAP,
        )

        bullets = []
        change_log = []
        for bid in (
            "bul_ibm_001",
            "bul_ibm_002",
            "bul_ibm_003",
            "bul_ibm_004",
            "bul_ibm_005",
        ):
            reb = IBM_BULLET_SLOT_BUNDLE_MAP[bid]
            bullets.append(
                {
                    "bullet_id": bid,
                    "bullet_text": (
                        f"Led enterprise cloud modernization delivering measurable outcomes for {bid}."
                    ),
                    "has_metric": bid == "bul_ibm_005",
                    "metric_raw": "20% joint revenue growth" if bid == "bul_ibm_005" else "",
                    "source_fact_ids": [bid],
                }
            )
            change_log.append(
                {
                    "bullet_id": bid,
                    "role_episode_bundle_id": reb,
                    "graph_skill_node_ids": ["skill_partner_ibm_aws_alliance_joint_revenue"],
                    "fact_ids_used": [bid],
                    "metric_outcome_ids": (
                        ["metric_ibm_20pct_joint_revenue_growth"] if bid == "bul_ibm_005" else []
                    ),
                }
            )
        return {
            "bullets": bullets,
            "change_log": change_log,
            "claim_ledger": [
                {"claim_text": b["bullet_text"], "source_fact_ids": b["source_fact_ids"]}
                for b in bullets
            ],
            "jd_alignment": {"targeting_only": True},
            "gap_notes": [],
            "self_check": {"bullets_composed_from_role_episode_bundles": True},
            "selected_fact_plan": {"facts": [], "selection_method": "ibm_track_ranked"},
        }

    @staticmethod
    def _graph_proof_meta(section_id: str) -> dict:
        from apps_rg.runtime.sections.ibm_role_episode_evidence import (
            attach_role_episode_bundles_to_proof_pool_metadata,
        )

        base = {
            "proof_pool_type": "augmented_skills_graph",
            "graph_skills_proof_pool": True,
            "selection_method": "augmented_skills_graph_ibm_bullets_phase2_track_ranked",
        }
        return attach_role_episode_bundles_to_proof_pool_metadata(
            base, section_id=section_id
        )

    def test_x2_bundle_id_gate_passes_with_bundles(self) -> None:
        from apps_rg.runtime.validators.ibm_bullets_x2 import run_ibm_bullets_x2_gates
        po = self._minimal_bullets_output()
        meta = self._graph_proof_meta("ibm_bullets")
        gates = run_ibm_bullets_x2_gates(
            bullets=po["bullets"],
            parsed_output=po,
            claim_ledger=po["claim_ledger"],
            allowed_fact_ids={f"bul_ibm_{i:03d}" for i in range(1, 6)},
            jd_text="",
            runtime_generation_status="REAL_LLM",
            proof_pool_metadata=meta,
        )
        gate = next(g for g in gates if g.gate_id == "x2_ibm_bullet_role_episode_bundle_id_required")
        assert gate.pass_ is True

    def test_x2_bundle_id_gate_uses_frozen_allocation_when_present(self) -> None:
        from apps_rg.runtime.sections.ibm_bullets_lane import (
            _bind_ibm_change_log_to_frozen_allocation,
        )
        from apps_rg.runtime.validators.ibm_bullets_x2 import run_ibm_bullets_x2_gates

        po = self._minimal_bullets_output()
        allocations = []
        for index, row in enumerate(po["change_log"], start=1):
            bullet_id = row["bullet_id"]
            root_id = f"reb_ibm_frozen_{index:03d}"
            allocations.append(
                {
                    "section_id": "ibm_bullets",
                    "claim_unit_id": f"ibm_bullets:{bullet_id}",
                    "root_id": root_id,
                    "skill_id": row["graph_skill_node_ids"][0],
                }
            )
        _bind_ibm_change_log_to_frozen_allocation(
            po,
            selected_fact_plan={"allocation_assignments": allocations},
        )
        assert [row["role_episode_bundle_id"] for row in po["change_log"]] == [
            f"reb_ibm_frozen_{index:03d}" for index in range(1, 6)
        ]
        gates = run_ibm_bullets_x2_gates(
            bullets=po["bullets"],
            parsed_output=po,
            claim_ledger=po["claim_ledger"],
            allowed_fact_ids={f"bul_ibm_{i:03d}" for i in range(1, 6)},
            jd_text="",
            runtime_generation_status="REAL_LLM",
            proof_pool_metadata=self._graph_proof_meta("ibm_bullets"),
            runtime_payload={
                "selected_fact_plan": {"allocation_assignments": allocations}
            },
        )

        gate = next(g for g in gates if g.gate_id == "x2_ibm_bullet_role_episode_bundle_id_required")
        assert gate.pass_ is True

    def test_frozen_allocation_rehydrates_display_and_ledger_by_slot(self) -> None:
        from apps_rg.runtime.sections.ibm_bullets_lane import (
            _materialize_ibm_bullets_from_frozen_allocation,
        )

        parsed = self._minimal_bullets_output()
        for row in parsed["bullets"]:
            row["bullet_text"] = "Model prose from the wrong slot."
        allocations = [
            {
                "section_id": "ibm_bullets",
                "claim_unit_id": f"ibm_bullets:bul_ibm_{index:03d}",
                "root_claim_text": f"Frozen graph claim for slot {index}.",
            }
            for index in range(1, 6)
        ]

        changed = _materialize_ibm_bullets_from_frozen_allocation(
            parsed,
            selected_fact_plan={"allocation_assignments": allocations},
        )

        assert changed is True
        assert [row["bullet_text"] for row in parsed["bullets"]] == [
            f"Frozen graph claim for slot {index}." for index in range(1, 6)
        ]
        assert [row["source_fact_ids"] for row in parsed["claim_ledger"]] == [
            [f"bul_ibm_{index:03d}"] for index in range(1, 6)
        ]

    def test_frozen_allocation_rehydrates_distinct_source_bound_mechanisms_and_metric(self) -> None:
        from apps_rg.runtime.sections.ibm_bullets_graph_evidence import (
            IBM_BULLET_MECHANISM_VOCAB,
        )
        from apps_rg.runtime.sections.ibm_bullets_lane import (
            _materialize_ibm_bullets_from_frozen_allocation,
        )
        from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
            run_bullet_quality_floor_gates,
        )

        parsed = self._minimal_bullets_output()
        allocations = [
            {
                "section_id": "ibm_bullets",
                "claim_unit_id": "ibm_bullets:bul_ibm_001",
                "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "skill_id": "skill_sr_w12_hyperscaler_alliance_co_sell",
                "root_claim_text": "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities",
                "metric_text": "20% joint revenue growth",
            },
            {
                "section_id": "ibm_bullets",
                "claim_unit_id": "ibm_bullets:bul_ibm_002",
                "root_id": "reb_ibm_data_modeling_bi_decision_support",
                "skill_id": "skill_sr_cloud_data_platform_engineering",
                "root_claim_text": "Built decision-support data models and BI views that connected modernization programs to executive operating decisions",
            },
            {
                "section_id": "ibm_bullets",
                "claim_unit_id": "ibm_bullets:bul_ibm_003",
                "root_id": "reb_ibm_revenue_sales_target_execution",
                "skill_id": "skill_partner_pnl_oversight",
                "root_claim_text": "Owned quota-aligned solution leadership across enterprise pursuits and client portfolio expansion motions",
            },
            {
                "section_id": "ibm_bullets",
                "claim_unit_id": "ibm_bullets:bul_ibm_004",
                "root_id": "reb_ibm_data_modeling_bi_decision_support",
                "skill_id": "skill_p2_tech_reference_architecture",
                "root_claim_text": "Built decision-support data models and BI views that connected modernization programs to executive operating decisions",
            },
            {
                "section_id": "ibm_bullets",
                "claim_unit_id": "ibm_bullets:bul_ibm_005",
                "root_id": "reb_ibm_presales_solution_engineering",
                "skill_id": "skill_p2_gtm_executive_buyer_alignment",
                "root_claim_text": "Led technical discovery and solution mapping for enterprise financial-services pursuits",
            },
        ]

        changed = _materialize_ibm_bullets_from_frozen_allocation(
            parsed,
            selected_fact_plan={"allocation_assignments": allocations},
        )

        assert changed is True
        by_id = {row["bullet_id"]: row for row in parsed["bullets"]}
        assert "20% joint revenue growth" in by_id["bul_ibm_001"]["bullet_text"]
        assert by_id["bul_ibm_001"]["has_metric"] is True
        assert "P&L oversight" in by_id["bul_ibm_003"]["bullet_text"]
        assert "reference architectures" in by_id["bul_ibm_004"]["bullet_text"]
        assert by_id["bul_ibm_004"]["has_metric"] is False
        _, _, technical_pass, technical_results, _, _ = run_bullet_quality_floor_gates(
            parsed["bullets"],
            section_id="ibm_bullets",
            mechanism_vocab_by_slot=IBM_BULLET_MECHANISM_VOCAB,
        )
        assert technical_pass, [row.failure_reason for row in technical_results]

    def test_x2_hold_metric_fails_on_forbidden_output(self) -> None:
        from apps_rg.runtime.validators.ibm_bullets_x2 import run_ibm_bullets_x2_gates
        po = self._minimal_bullets_output()
        po["bullets"][0]["bullet_text"] = "Reduced costs by 40% across the platform."
        meta = self._graph_proof_meta("ibm_bullets")
        gates = run_ibm_bullets_x2_gates(
            bullets=po["bullets"],
            parsed_output=po,
            claim_ledger=po["claim_ledger"],
            allowed_fact_ids={f"bul_ibm_{i:03d}" for i in range(1, 6)},
            jd_text="",
            runtime_generation_status="REAL_LLM",
            proof_pool_metadata=meta,
        )
        gate = next(g for g in gates if g.gate_id == "x2_ibm_hold_metric_forbidden_in_output")
        assert gate.pass_ is False

    def test_x2_flat_skill_only_fails_without_bundles(self) -> None:
        from apps_rg.runtime.validators.ibm_bullets_x2 import run_ibm_bullets_x2_gates

        po = self._minimal_bullets_output()
        gates = run_ibm_bullets_x2_gates(
            bullets=po["bullets"],
            parsed_output=po,
            claim_ledger=po["claim_ledger"],
            allowed_fact_ids={f"bul_ibm_{i:03d}" for i in range(1, 6)},
            jd_text="",
            runtime_generation_status="REAL_LLM",
            proof_pool_metadata={
                "graph_skill_node_ids": ["skill_x"],
                "proof_pool_type": "augmented_skills_graph",
                "graph_skills_proof_pool": True,
            },
        )
        gate = next(g for g in gates if g.gate_id == "x2_ibm_role_episode_bundles_in_proof_pool")
        assert gate.pass_ is False

    def test_x2_narrative_requires_bundles(self) -> None:
        from apps_rg.runtime.validators.ibm_narrative_x2 import run_ibm_narrative_x2_gates
        meta = self._graph_proof_meta("ibm_narrative")
        gates = run_ibm_narrative_x2_gates(
            narrative_sentence=(
                "At IBM, led cloud and data platform modernization for financial services clients."
            ),
            companion_bullet_texts="",
            parsed_output={
                "change_log": [{"role_episode_bundle_id": "reb_ibm_cloud_modernization"}],
                "role_episode_bundle_ids": meta["role_episode_bundle_ids"],
                "claim_ledger": [
                    {
                        "claim_text": "IBM cloud modernization leadership.",
                        "source_fact_ids": ["bul_ibm_001"],
                    }
                ],
            },
            claim_ledger=[
                {
                    "claim_text": "IBM cloud modernization leadership.",
                    "source_fact_ids": ["bul_ibm_001"],
                }
            ],
            jd_text="",
            runtime_generation_status="REAL_LLM",
            proof_pool_metadata=meta,
            allowed_fact_ids=["bul_ibm_001"],
        )
        gate = next(
            g for g in gates if g.gate_id == "x2_ibm_narrative_role_episode_bundle_id_required"
        )
        assert gate.pass_ is True


def test_current_ibm_presales_and_deal_support_allocations_surface_mechanisms() -> None:
    from apps_rg.runtime.sections.ibm_bullets_graph_evidence import (
        IBM_BULLET_MECHANISM_VOCAB,
    )
    from apps_rg.runtime.sections.ibm_bullets_lane import (
        _materialize_ibm_bullets_from_frozen_allocation,
    )
    from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
        run_bullet_quality_floor_gates,
    )

    parsed = {
        "bullets": [
            {"bullet_id": f"bul_ibm_{index:03d}", "bullet_text": "placeholder"}
            for index in range(1, 6)
        ]
    }
    allocations = [
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": f"ibm_bullets:bul_ibm_{index:03d}",
            "root_id": root_id,
            "skill_id": skill_id,
            "root_claim_text": text,
        }
        for index, (root_id, skill_id, text) in enumerate(
            (
                ("root_1", "skill_1", "Architected AWS alliance solutions"),
                ("root_2", "skill_2", "Built BI decision-support data models"),
                (
                    "reb_ibm_presales_solution_engineering",
                    "skill_p2_gtm_solution_mapping",
                    "Led technical discovery and solution mapping for enterprise pursuits",
                ),
                (
                    "reb_ibm_revenue_sales_target_execution",
                    "skill_p2_gtm_enterprise_deal_support",
                    "Owned quota-aligned solution leadership across enterprise pursuits",
                ),
                ("root_5", "skill_5", "Architected AI reference architectures"),
            ),
            start=1,
        )
    ]

    assert _materialize_ibm_bullets_from_frozen_allocation(
        parsed, selected_fact_plan={"allocation_assignments": allocations}
    )
    by_id = {row["bullet_id"]: row["bullet_text"] for row in parsed["bullets"]}
    assert "delivery-ready solution handoffs" in by_id["bul_ibm_003"]
    assert "pipeline discipline" in by_id["bul_ibm_004"]
    _, _, technical_pass, technical_rows, _, _ = run_bullet_quality_floor_gates(
        parsed["bullets"],
        section_id="ibm_bullets",
        mechanism_vocab_by_slot=IBM_BULLET_MECHANISM_VOCAB,
    )
    assert technical_pass, [row.failure_reason for row in technical_rows]


class TestForbiddenMetricsScan:
    def test_scan_detects_hold_metrics(self) -> None:
        from apps_rg.runtime.sections.ibm_role_episode_evidence import (
            scan_forbidden_metrics_in_text,
        )

        hits = scan_forbidden_metrics_in_text("Delivered $15M in incremental revenue with 40% gain.")
        assert any("15" in h or "40" in h for h in hits)
